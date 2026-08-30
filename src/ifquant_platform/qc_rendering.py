"""Deterministic, non-scientific DAPI QC rendering for canonical packages.

The renderer deliberately keeps Pillow and NumPy optional.  Package and
candidate-ledger validation can be imported and tested in a core-only Python
environment; imaging dependencies are loaded only by :func:`render_qc`.
"""

from __future__ import annotations

import hashlib
import math
import platform
import re
import shutil
import tempfile
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

from .canonical import (
    ContractError,
    canonical_json_bytes,
    canonical_sha256,
    file_sha256,
    load_strict_json,
    parse_strict_json,
)
from .package_validation import validate_cell_package

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
WKT_TOKEN_RE = re.compile(
    r"\s*(?:(?P<number>[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)|(?P<punct>[(),]))"
)

RECORD_FIELDS = frozenset(
    {
        "schema_version",
        "candidate_id",
        "candidate_index",
        "package_id",
        "image_id",
        "annotation_set_id",
        "segmentation_run_id",
        "coordinate_space_id",
        "annotation_id",
        "accepted_object_id",
        "source_detection_id",
        "disposition",
        "reason",
        "geometry",
        "centroids",
        "touches_annotation_boundary",
        "nucleus_not_covered_by_cell_geometry_warning",
        "nucleus_area_outside_cell_px2",
        "nucleus_area_outside_cell_fraction",
    }
)
MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "pilot_status",
        "package_id",
        "image_id",
        "annotation_set_id",
        "segmentation_run_id",
        "coordinate_space_id",
        "artifact",
        "disposition_counts",
        "reason_counts",
        "geometry_warning_counts",
        "bindings",
        "claims",
    }
)
ARTIFACT_FIELDS = frozenset(
    {"relative_path", "media_type", "sha256", "size_bytes", "record_count", "ordering"}
)
BINDING_FIELDS = frozenset(
    {
        "script_sha256",
        "run_config_sha256",
        "source_artifact_sha256",
        "annotation_content_sha256",
    }
)
CLAIM_FIELDS = frozenset(
    {"scientific_validation", "backend_equivalence", "model_universality", "authorization"}
)
GEOMETRY_WARNING_CODE = "nucleus_not_covered_by_cell_geometry"
BOUNDARY_REASON = "cell_touches_annotation_boundary"
CANDIDATE_RECORD_SCHEMA = "ifquant.qc-candidate-disposition/1.0.0"
CANDIDATE_MANIFEST_SCHEMA = "ifquant.qc-candidate-dispositions-manifest/1.0.0"
SUPPORTED_PILOT_STATUS = "unvalidated_engineering_pilot"


@dataclass(frozen=True, slots=True)
class WktGeometry:
    """Parsed 2D polygon geometry: polygons -> rings -> (x, y) points."""

    geometry_type: str
    polygons: tuple[tuple[tuple[tuple[float, float], ...], ...], ...]


@dataclass(frozen=True, slots=True)
class CandidateLedger:
    """A fully reconciled candidate-disposition sidecar."""

    package_root: Path
    package_path: Path
    manifest_path: Path
    artifact_path: Path
    package: Mapping[str, Any]
    image_manifest: Mapping[str, Any]
    channel_map: Mapping[str, Any]
    annotation_set: Mapping[str, Any]
    segmentation_run: Mapping[str, Any]
    package_canonical_sha256: str
    manifest_canonical_sha256: str
    records: tuple[Mapping[str, Any], ...]
    disposition_counts: Mapping[str, int]
    reason_counts: Mapping[str, int]
    warning_count: int


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def _mapping(value: Any, location: str) -> Mapping[str, Any]:
    _require(isinstance(value, Mapping), f"{location} must be an object")
    return value


def _sequence(value: Any, location: str) -> list[Any]:
    _require(
        isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)),
        f"{location} must be an array",
    )
    return list(value)


def _exact(value: Mapping[str, Any], fields: frozenset[str], location: str) -> None:
    missing = sorted(fields - set(value))
    unknown = sorted(set(value) - fields)
    _require(not missing, f"{location} is missing: {', '.join(missing)}")
    _require(not unknown, f"{location} has unknown fields: {', '.join(unknown)}")


def _string(value: Any, location: str) -> str:
    _require(isinstance(value, str) and bool(value.strip()), f"{location} must be non-empty")
    return value


def _identifier(value: Any, location: str) -> str:
    text = _string(value, location)
    _require(bool(IDENTIFIER_RE.fullmatch(text)), f"{location} is not a valid identifier")
    return text


def _sha256(value: Any, location: str) -> str:
    _require(isinstance(value, str) and bool(SHA256_RE.fullmatch(value)), f"{location} must be lowercase SHA-256")
    return value


def _integer(value: Any, location: str) -> int:
    _require(isinstance(value, int) and not isinstance(value, bool) and value >= 0, f"{location} must be a nonnegative integer")
    return value


def _finite(value: Any, location: str) -> float:
    _require(isinstance(value, (int, float)) and not isinstance(value, bool), f"{location} must be numeric")
    result = float(value)
    _require(math.isfinite(result), f"{location} must be finite")
    return result


def _strict_relative(root: Path, value: Any, location: str) -> Path:
    text = _string(value, location)
    _require("\\" not in text, f"{location} must use '/' separators")
    relative = PurePosixPath(text)
    _require(not relative.is_absolute() and ".." not in relative.parts, f"{location} must stay inside the package")
    _require(not (relative.parts and ":" in relative.parts[0]), f"{location} must not be a drive path")
    candidate = (root / Path(*relative.parts)).resolve()
    _require(candidate.is_relative_to(root.resolve()), f"{location} escapes the package root")
    return candidate


def _package_source(path: str | Path) -> tuple[Path, Path]:
    requested = Path(path)
    package_path = requested / "package.json" if requested.is_dir() else requested
    _require(package_path.is_file(), f"package does not exist: {package_path}")
    return package_path.resolve(), package_path.resolve().parent


def _referenced_json(package_root: Path, reference: Mapping[str, Any], location: str) -> Mapping[str, Any]:
    path = _strict_relative(package_root, reference["manifest_relative_path"], f"{location}.manifest_relative_path")
    _require(path.is_file(), f"{location} manifest does not exist: {path}")
    return _mapping(load_strict_json(path), location)


def _load_canonical_jsonl(path: Path, *, location: str) -> tuple[list[Mapping[str, Any]], bytes]:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise ContractError(f"cannot read {location} {path}: {exc}") from exc
    if not payload:
        return [], payload
    _require(b"\r" not in payload, f"{location} must use LF line endings")
    _require(payload.endswith(b"\n"), f"{location} must end with LF")
    records: list[Mapping[str, Any]] = []
    for index, line in enumerate(payload[:-1].split(b"\n")):
        _require(bool(line), f"{location} line {index + 1} is blank")
        record = _mapping(parse_strict_json(line, source=f"{path}:{index + 1}"), f"{location}[{index}]")
        _require(canonical_json_bytes(record) == line, f"{location} line {index + 1} is not canonical JSON")
        records.append(record)
    return records, payload


class _WktParser:
    def __init__(self, text: str, location: str) -> None:
        self.location = location
        self.tokens: list[str] = []
        position = 0
        stripped = text.strip()
        while position < len(stripped):
            match = WKT_TOKEN_RE.match(stripped, position)
            _require(match is not None, f"{location} is not valid 2D WKT1")
            self.tokens.append(match.group("number") or match.group("punct"))
            position = match.end()
        self.cursor = 0

    def consume(self, expected: str | None = None) -> str:
        _require(self.cursor < len(self.tokens), f"{self.location} ends unexpectedly")
        token = self.tokens[self.cursor]
        if expected is not None:
            _require(token == expected, f"{self.location} expected '{expected}'")
        self.cursor += 1
        return token

    def coordinate(self) -> tuple[float, float]:
        values: list[float] = []
        for _ in range(2):
            token = self.consume()
            _require(token not in {"(", ")", ","}, f"{self.location} coordinate is incomplete")
            try:
                number = float(token)
            except ValueError as exc:
                raise ContractError(f"{self.location} coordinate is invalid") from exc
            _require(math.isfinite(number), f"{self.location} coordinate must be finite")
            values.append(number)
        _require(
            self.cursor >= len(self.tokens) or self.tokens[self.cursor] in {",", ")"},
            f"{self.location} coordinates must be two-dimensional",
        )
        return values[0], values[1]

    def ring(self) -> tuple[tuple[float, float], ...]:
        self.consume("(")
        points = [self.coordinate()]
        while self.cursor < len(self.tokens) and self.tokens[self.cursor] == ",":
            self.consume(",")
            points.append(self.coordinate())
        self.consume(")")
        _require(len(points) >= 4, f"{self.location} ring must have at least four points")
        _require(points[0] == points[-1], f"{self.location} ring must be closed")
        _require(len(set(points[:-1])) >= 3, f"{self.location} ring must have three distinct vertices")
        return tuple(points)

    def polygon(self) -> tuple[tuple[tuple[float, float], ...], ...]:
        self.consume("(")
        rings = [self.ring()]
        while self.cursor < len(self.tokens) and self.tokens[self.cursor] == ",":
            self.consume(",")
            rings.append(self.ring())
        self.consume(")")
        return tuple(rings)

    def parse(self, geometry_type: str) -> WktGeometry:
        if geometry_type == "POLYGON":
            polygons = (self.polygon(),)
        else:
            self.consume("(")
            values = [self.polygon()]
            while self.cursor < len(self.tokens) and self.tokens[self.cursor] == ",":
                self.consume(",")
                values.append(self.polygon())
            self.consume(")")
            polygons = tuple(values)
        _require(self.cursor == len(self.tokens), f"{self.location} has trailing tokens")
        return WktGeometry(geometry_type=geometry_type, polygons=polygons)


def parse_wkt(value: Any, *, location: str = "geometry") -> WktGeometry:
    """Parse the platform's POLYGON/MULTIPOLYGON subset without Shapely."""

    geometry = _mapping(value, location)
    _exact(geometry, frozenset({"encoding", "geometry_type", "wkt"}), location)
    _require(geometry["encoding"] == "WKT1", f"{location}.encoding must be WKT1")
    geometry_type = geometry["geometry_type"]
    _require(geometry_type in {"POLYGON", "MULTIPOLYGON"}, f"{location}.geometry_type is unsupported")
    wkt = _string(geometry["wkt"], f"{location}.wkt")
    match = re.match(r"^(POLYGON|MULTIPOLYGON)\s*", wkt)
    _require(match is not None and match.group(1) == geometry_type, f"{location}.wkt type mismatch")
    return _WktParser(wkt[match.end() :], f"{location}.wkt").parse(geometry_type)


def _annotation_content_sha256(annotation_set: Mapping[str, Any]) -> str:
    content = []
    for raw in _sequence(annotation_set["annotations"], "annotation_set.annotations"):
        annotation = _mapping(raw, "annotation_set.annotation")
        content.append(
            {
                "annotation_id": annotation["annotation_id"],
                "label": annotation["label"],
                "inclusion_policy": annotation["inclusion_policy"],
                "geometry": annotation["geometry"],
            }
        )
    content.sort(key=lambda item: item["annotation_id"])
    return canonical_sha256(
        {
            "contract": "ifquant-platform-annotation-content/v1",
            "annotation_set_id": annotation_set["annotation_set_id"],
            "image_id": annotation_set["image_id"],
            "coordinate_space_id": annotation_set["coordinate_space_id"],
            "revision": annotation_set["revision"],
            "annotations": content,
        }
    )


def expected_candidate_id(record: Mapping[str, Any]) -> str:
    """Return the candidate identity defined by the QuPath sidecar contract."""

    geometry = _mapping(record["geometry"], "candidate.geometry")
    cell = _mapping(geometry["cell"], "candidate.geometry.cell")
    nucleus_raw = geometry["nucleus"]
    nucleus_wkt = None
    if nucleus_raw is not None:
        nucleus_wkt = _mapping(nucleus_raw, "candidate.geometry.nucleus")["wkt"]
    return "cand_" + canonical_sha256(
        {
            "cell_wkt": cell["wkt"],
            "coordinate_space_id": record["coordinate_space_id"],
            "image_id": record["image_id"],
            "nucleus_wkt": nucleus_wkt,
            "segmentation_run_id": record["segmentation_run_id"],
        }
    )


def _validate_count_map(value: Any, location: str) -> dict[str, int]:
    mapping = _mapping(value, location)
    result: dict[str, int] = {}
    for key, raw in mapping.items():
        _identifier(key, f"{location} key")
        result[key] = _integer(raw, f"{location}.{key}")
    return result


def _resolve_source_artifact(package_root: Path, source_uri: Any) -> Path:
    text = _string(source_uri, "image_manifest.source_artifact.source_uri")
    direct = Path(text)
    if direct.is_absolute():
        return direct.resolve()
    parsed = urlparse(text)
    if parsed.scheme:
        _require(parsed.scheme == "file", "source image URI must be local")
        _require(parsed.netloc in {"", "localhost"}, "source image URI must not name a remote host")
        return Path(url2pathname(unquote(parsed.path))).resolve()
    return _strict_relative(package_root, text, "image_manifest.source_artifact.source_uri")


def validate_candidate_dispositions(
    package: str | Path,
    *,
    candidate_manifest: str | Path | None = None,
    candidate_dispositions: str | Path | None = None,
) -> CandidateLedger:
    """Validate and reconcile the full detector candidate ledger.

    This performs no imaging imports.  It first validates the canonical package,
    then fails closed on unknown fields, sidecar byte drift, candidate identity
    drift, accepted-object linkage, or aggregate-count drift.
    """

    package_path, package_root = _package_source(package)
    report = validate_cell_package(package_path)
    package_doc = _mapping(load_strict_json(package_path), "package")
    image = _referenced_json(package_root, _mapping(package_doc["image"], "package.image"), "image_manifest")
    channel_map = _referenced_json(package_root, _mapping(package_doc["channel_map"], "package.channel_map"), "channel_map")
    annotation_set = _referenced_json(
        package_root, _mapping(package_doc["annotation_set"], "package.annotation_set"), "annotation_set"
    )
    run = _referenced_json(
        package_root, _mapping(package_doc["segmentation_run"], "package.segmentation_run"), "segmentation_run"
    )

    manifest_path = (
        Path(candidate_manifest).resolve()
        if candidate_manifest is not None
        else (package_root / "qc" / "candidate-dispositions-manifest.json").resolve()
    )
    _require(manifest_path.is_file(), f"candidate manifest does not exist: {manifest_path}")
    manifest = _mapping(load_strict_json(manifest_path), "candidate_manifest")
    _exact(manifest, MANIFEST_FIELDS, "candidate_manifest")
    _require(
        manifest["schema_version"] == CANDIDATE_MANIFEST_SCHEMA,
        "candidate_manifest.schema_version is unsupported",
    )
    _require(
        manifest["pilot_status"] == SUPPORTED_PILOT_STATUS,
        "candidate_manifest.pilot_status is unsupported",
    )

    expected_ids = {
        "package_id": package_doc["package_id"],
        "image_id": image["image_id"],
        "annotation_set_id": annotation_set["annotation_set_id"],
        "segmentation_run_id": run["segmentation_run_id"],
        "coordinate_space_id": image["coordinate_space"]["coordinate_space_id"],
    }
    for field, expected in expected_ids.items():
        _require(manifest[field] == expected, f"candidate_manifest.{field} does not match package")

    artifact = _mapping(manifest["artifact"], "candidate_manifest.artifact")
    _exact(artifact, ARTIFACT_FIELDS, "candidate_manifest.artifact")
    expected_artifact = _strict_relative(
        package_root, artifact["relative_path"], "candidate_manifest.artifact.relative_path"
    )
    artifact_path = Path(candidate_dispositions).resolve() if candidate_dispositions is not None else expected_artifact
    _require(artifact_path == expected_artifact, "candidate dispositions path does not match manifest relative_path")
    _require(artifact_path.is_file(), f"candidate dispositions do not exist: {artifact_path}")
    _require(artifact["media_type"] == "application/x-ndjson", "candidate artifact media_type is unsupported")
    _require(artifact["ordering"] == "candidate_index_ascending", "candidate artifact ordering is unsupported")
    _require(file_sha256(artifact_path) == _sha256(artifact["sha256"], "candidate_manifest.artifact.sha256"), "candidate artifact SHA-256 mismatch")
    _require(artifact_path.stat().st_size == _integer(artifact["size_bytes"], "candidate_manifest.artifact.size_bytes"), "candidate artifact size mismatch")

    records, payload = _load_canonical_jsonl(artifact_path, location="candidate_dispositions")
    _require(len(payload) == artifact["size_bytes"], "candidate artifact size changed during validation")
    _require(len(records) == _integer(artifact["record_count"], "candidate_manifest.artifact.record_count"), "candidate artifact record count mismatch")

    object_path = _strict_relative(
        package_root,
        package_doc["cell_objects_artifact"]["relative_path"],
        "package.cell_objects_artifact.relative_path",
    )
    objects, _ = _load_canonical_jsonl(object_path, location="cell_objects")
    objects_by_id = {item["object_id"]: item for item in objects}
    annotations_by_id = {item["annotation_id"]: item for item in annotation_set["annotations"]}

    candidate_ids: set[str] = set()
    indices: set[int] = set()
    accepted_ids: list[str] = []
    observed_dispositions: Counter[str] = Counter({"accepted": 0, "excluded": 0})
    observed_reasons: Counter[str] = Counter()
    warning_count = 0
    for row, raw in enumerate(records):
        location = f"candidate_dispositions[{row}]"
        _exact(raw, RECORD_FIELDS, location)
        _require(
            raw["schema_version"] == CANDIDATE_RECORD_SCHEMA,
            f"{location}.schema_version is unsupported",
        )
        index = _integer(raw["candidate_index"], f"{location}.candidate_index")
        _require(index == row, f"{location}.candidate_index must be contiguous and ascending")
        _require(index not in indices, f"duplicate candidate_index {index}")
        indices.add(index)
        for field, expected in expected_ids.items():
            _require(raw[field] == expected, f"{location}.{field} does not match package")

        candidate_id = _string(raw["candidate_id"], f"{location}.candidate_id")
        _require(candidate_id.startswith("cand_") and bool(SHA256_RE.fullmatch(candidate_id[5:])), f"{location}.candidate_id is invalid")
        _require(candidate_id == expected_candidate_id(raw), f"{location}.candidate_id does not match canonical geometry identity")
        _require(candidate_id not in candidate_ids, f"duplicate candidate_id {candidate_id}")
        candidate_ids.add(candidate_id)

        annotation_id = raw["annotation_id"]
        if annotation_id is not None:
            _identifier(annotation_id, f"{location}.annotation_id")
            _require(annotation_id in annotations_by_id, f"{location}.annotation_id is absent from annotation set")
        _string(raw["source_detection_id"], f"{location}.source_detection_id")
        disposition = raw["disposition"]
        _require(disposition in {"accepted", "excluded"}, f"{location}.disposition is unsupported")
        reason = _identifier(raw["reason"], f"{location}.reason")
        observed_dispositions[disposition] += 1
        observed_reasons[reason] += 1

        geometry = _mapping(raw["geometry"], f"{location}.geometry")
        _exact(geometry, frozenset({"cell", "nucleus"}), f"{location}.geometry")
        parse_wkt(geometry["cell"], location=f"{location}.geometry.cell")
        if geometry["nucleus"] is not None:
            parse_wkt(geometry["nucleus"], location=f"{location}.geometry.nucleus")
        centroids = _mapping(raw["centroids"], f"{location}.centroids")
        _exact(
            centroids,
            frozenset({"cell_x", "cell_y", "nucleus_x", "nucleus_y", "unit"}),
            f"{location}.centroids",
        )
        _finite(centroids["cell_x"], f"{location}.centroids.cell_x")
        _finite(centroids["cell_y"], f"{location}.centroids.cell_y")
        _require(centroids["unit"] == "pixel", f"{location}.centroids.unit must be pixel")
        for field in ("nucleus_x", "nucleus_y"):
            if centroids[field] is not None:
                _finite(centroids[field], f"{location}.centroids.{field}")
        _require(
            (centroids["nucleus_x"] is None) == (centroids["nucleus_y"] is None),
            f"{location}.centroids nucleus coordinates must both be null or numeric",
        )
        _require(
            (geometry["nucleus"] is None) == (centroids["nucleus_x"] is None),
            f"{location} nucleus geometry and centroid availability disagree",
        )
        _require(isinstance(raw["touches_annotation_boundary"], bool), f"{location}.touches_annotation_boundary must be boolean")
        warning = raw["nucleus_not_covered_by_cell_geometry_warning"]
        _require(isinstance(warning, bool), f"{location}.nucleus_not_covered_by_cell_geometry_warning must be boolean")
        outside_area = raw["nucleus_area_outside_cell_px2"]
        outside_fraction = raw["nucleus_area_outside_cell_fraction"]
        if geometry["nucleus"] is None:
            _require(
                outside_area is None and outside_fraction is None,
                f"{location} nucleus-outside-cell metrics must be null without nucleus geometry",
            )
            _require(not warning, f"{location} cannot carry a nucleus geometry warning without a nucleus")
        else:
            area_value = _finite(outside_area, f"{location}.nucleus_area_outside_cell_px2")
            fraction_value = _finite(
                outside_fraction, f"{location}.nucleus_area_outside_cell_fraction"
            )
            _require(area_value >= 0, f"{location}.nucleus_area_outside_cell_px2 must be nonnegative")
            _require(
                0 <= fraction_value <= 1,
                f"{location}.nucleus_area_outside_cell_fraction must be between zero and one",
            )
            _require(
                warning or (area_value == 0 and fraction_value == 0),
                f"{location} positive nucleus-outside-cell metrics require the geometry warning",
            )
        warning_count += int(warning)
        if reason == BOUNDARY_REASON:
            _require(
                raw["touches_annotation_boundary"],
                f"{location} boundary-exclusion reason requires a true boundary flag",
            )

        accepted_object_id = raw["accepted_object_id"]
        if disposition == "accepted":
            _require(reason == "accepted", f"{location} accepted candidate must use reason accepted")
            _require(not raw["touches_annotation_boundary"], f"{location} accepted candidate cannot touch boundary")
            _require(annotation_id is not None, f"{location} accepted candidate requires annotation_id")
            object_id = _string(accepted_object_id, f"{location}.accepted_object_id")
            _require(object_id in objects_by_id, f"{location}.accepted_object_id is absent from package")
            accepted_ids.append(object_id)
            cell_object = objects_by_id[object_id]
            _require(annotation_id == cell_object["annotation_id"], f"{location} annotation link disagrees with accepted object")
            _require(geometry == cell_object["geometry"], f"{location} geometry disagrees with accepted object")
            _require(centroids == cell_object["centroids"], f"{location} centroids disagree with accepted object")
            _require(
                raw["source_detection_id"] == cell_object["provenance"]["source_detection_id"],
                f"{location} source detection disagrees with accepted object",
            )
            object_warning = any(
                flag["code"] == GEOMETRY_WARNING_CODE for flag in cell_object["qc"]["flags"]
            )
            _require(warning == object_warning, f"{location} geometry-warning flag disagrees with accepted object")
        else:
            _require(reason != "accepted", f"{location} excluded candidate cannot use reason accepted")
            _require(accepted_object_id is None, f"{location} excluded candidate cannot link an accepted object")

    _require(len(accepted_ids) == len(set(accepted_ids)), "accepted_object_id values must be unique")
    _require(set(accepted_ids) == set(objects_by_id), "candidate ledger does not account for every accepted package object")

    manifest_dispositions = _validate_count_map(manifest["disposition_counts"], "candidate_manifest.disposition_counts")
    manifest_reasons = _validate_count_map(manifest["reason_counts"], "candidate_manifest.reason_counts")
    _require(manifest_dispositions == dict(observed_dispositions), "candidate disposition counts do not match records")
    _require(manifest_reasons == dict(observed_reasons), "candidate reason counts do not match records")
    warning_counts = _mapping(manifest["geometry_warning_counts"], "candidate_manifest.geometry_warning_counts")
    _exact(warning_counts, frozenset({GEOMETRY_WARNING_CODE}), "candidate_manifest.geometry_warning_counts")
    _require(
        _integer(warning_counts[GEOMETRY_WARNING_CODE], f"candidate_manifest.geometry_warning_counts.{GEOMETRY_WARNING_CODE}") == warning_count,
        "candidate geometry-warning count does not match records",
    )

    bindings = _mapping(manifest["bindings"], "candidate_manifest.bindings")
    _exact(bindings, BINDING_FIELDS, "candidate_manifest.bindings")
    expected_bindings = {
        "script_sha256": run["execution"]["script_sha256"],
        "run_config_sha256": run["execution"]["run_config_sha256"],
        "source_artifact_sha256": image["source_artifact"]["sha256"],
        "annotation_content_sha256": _annotation_content_sha256(annotation_set),
    }
    for field, expected in expected_bindings.items():
        _require(_sha256(bindings[field], f"candidate_manifest.bindings.{field}") == expected, f"candidate manifest {field} binding mismatch")

    claims = _mapping(manifest["claims"], "candidate_manifest.claims")
    _exact(claims, CLAIM_FIELDS, "candidate_manifest.claims")
    for field in ("scientific_validation", "backend_equivalence", "model_universality"):
        _require(claims[field] is False, f"candidate_manifest.claims.{field} must be false")
    _require(claims["authorization"] == "none", "candidate_manifest.claims.authorization must be none")

    return CandidateLedger(
        package_root=package_root,
        package_path=package_path,
        manifest_path=manifest_path,
        artifact_path=artifact_path,
        package=package_doc,
        image_manifest=image,
        channel_map=channel_map,
        annotation_set=annotation_set,
        segmentation_run=run,
        package_canonical_sha256=report.package_canonical_sha256,
        manifest_canonical_sha256=canonical_sha256(manifest),
        records=tuple(records),
        disposition_counts=dict(observed_dispositions),
        reason_counts=dict(observed_reasons),
        warning_count=warning_count,
    )


def _imaging_dependencies() -> tuple[Any, Any, Any, Any, str, str]:
    try:
        import numpy as np
        from PIL import Image, ImageDraw, ImageFont, __version__ as pillow_version
    except ImportError as exc:
        raise ContractError(
            "QC rendering requires optional dependencies; install ifquant-platform[qc] "
            "(Pillow and NumPy)"
        ) from exc
    return np, Image, ImageDraw, ImageFont, pillow_version, np.__version__


def _dapi_channel(channel_map: Mapping[str, Any]) -> Mapping[str, Any]:
    channels = [_mapping(item, "channel_map.channel") for item in channel_map["channels"]]
    nuclear = [item for item in channels if item["role"] == "nuclear_counterstain"]
    if len(nuclear) != 1:
        named = [
            item
            for item in channels
            if item["channel_id"].lower() == "dapi" or item["marker_id"].lower() == "dapi"
        ]
        _require(len(named) == 1, "channel map must identify exactly one DAPI/nuclear-counterstain channel")
        return named[0]
    return nuclear[0]


def _load_dapi_plane(ledger: CandidateLedger, np: Any, Image: Any) -> tuple[Any, Mapping[str, Any], Path]:
    channel = _dapi_channel(ledger.channel_map)
    source = _resolve_source_artifact(
        ledger.package_root, ledger.image_manifest["source_artifact"]["source_uri"]
    )
    _require(source.is_file(), f"source image does not exist: {source}")
    index = channel["source_channel_index"]
    try:
        with Image.open(source) as image:
            if image.n_frames > 1:
                _require(index < image.n_frames, "DAPI source_channel_index exceeds image frame count")
                image.seek(index)
                plane = np.asarray(image).copy()
            else:
                plane = np.asarray(image).copy()
                if plane.ndim == 3:
                    _require(index < plane.shape[-1], "DAPI source_channel_index exceeds image band count")
                    plane = plane[..., index]
    except (OSError, ValueError) as exc:
        raise ContractError(f"cannot read DAPI frame from {source}: {exc}") from exc
    _require(plane.ndim == 2, "DAPI source frame must resolve to one 2D plane")
    dimensions = ledger.image_manifest["dimensions"]
    _require(
        plane.shape == (dimensions["height_pixels"], dimensions["width_pixels"]),
        "DAPI plane dimensions do not match image manifest",
    )
    _require(bool(np.isfinite(plane).all()), "DAPI plane contains non-finite samples")
    return plane, channel, source


def _nearest_rank(values: Any, percentile: float, np: Any) -> float:
    flat = values.reshape(-1)
    _require(flat.size > 0, "DAPI plane is empty")
    rank = max(1, int(math.ceil((percentile / 100.0) * int(flat.size))))
    if values.dtype.kind in {"u", "i"} and int(values.min()) >= 0 and int(values.max()) <= 65535:
        histogram = np.bincount(flat.astype(np.int64), minlength=int(values.max()) + 1)
        return float(np.searchsorted(np.cumsum(histogram, dtype=np.int64), rank, side="left"))
    ordered = np.sort(flat, kind="stable")
    return float(ordered[rank - 1])


def _window_plane(plane: Any, lower_percentile: float, upper_percentile: float, np: Any) -> tuple[Any, float, float]:
    _require(0 <= lower_percentile < upper_percentile <= 100, "window percentiles must satisfy 0 <= lower < upper <= 100")
    low = _nearest_rank(plane, lower_percentile, np)
    high = _nearest_rank(plane, upper_percentile, np)
    _require(high > low, "DAPI percentile window is degenerate")
    scaled = np.clip((plane.astype(np.float64) - low) * (255.0 / (high - low)), 0, 255)
    return scaled.astype(np.uint8), low, high


def _draw_geometry(draw: Any, geometry: WktGeometry, *, color: tuple[int, int, int], width: int = 1, transform: Any | None = None) -> None:
    for polygon in geometry.polygons:
        for ring in polygon:
            points = list(ring)
            if transform is not None:
                points = [transform(x, y) for x, y in points]
            draw.line(points, fill=color, width=width)


def _round_scale_bar(width_pixels: int, pixel_width_um: float) -> tuple[float, int]:
    target_um = width_pixels * pixel_width_um * 0.18
    candidates: list[float] = []
    for exponent in range(-3, 7):
        for multiplier in (1, 2, 5):
            candidates.append(multiplier * (10.0**exponent))
    eligible = [value for value in candidates if value <= target_um]
    length_um = max(eligible) if eligible else min(candidates)
    return length_um, max(1, int(round(length_um / pixel_width_um)))


def _draw_scale_bar(image: Any, ImageDraw: Any, ImageFont: Any, pixel_width_um: float) -> tuple[float, int]:
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    length_um, length_px = _round_scale_bar(image.width, pixel_width_um)
    margin = max(12, image.width // 100)
    bar_height = max(4, image.height // 300)
    x1 = image.width - margin
    x0 = x1 - length_px
    y1 = image.height - margin
    y0 = y1 - bar_height
    label = f"{length_um:g} um"
    box = draw.textbbox((0, 0), label, font=font)
    label_width = box[2] - box[0]
    background_x0 = min(x0, x1 - label_width) - 8
    draw.rectangle((background_x0, y0 - 22, x1 + 5, y1 + 5), fill=(0, 0, 0))
    draw.rectangle((x0, y0, x1, y1), fill=(255, 255, 255))
    draw.text((x1 - label_width, y0 - 18), label, fill=(255, 255, 255), font=font)
    return length_um, length_px


def _draw_rois(image: Any, annotation_set: Mapping[str, Any], ImageDraw: Any, *, color: tuple[int, int, int] = (0, 220, 255)) -> None:
    draw = ImageDraw.Draw(image)
    for index, annotation in enumerate(annotation_set["annotations"]):
        if annotation["inclusion_policy"] == "include":
            geometry = parse_wkt(annotation["geometry"], location=f"annotation_set.annotations[{index}].geometry")
            _draw_geometry(draw, geometry, color=color, width=3)


def _draw_legend(image: Any, ImageDraw: Any, ImageFont: Any) -> None:
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    entries = [
        ("accepted", (0, 255, 100)),
        ("excluded", (255, 100, 0)),
        ("boundary exclusion", (255, 0, 200)),
        ("geometry warning", (255, 221, 0)),
        ("ROI", (0, 220, 255)),
    ]
    width = 174
    height = 10 + 17 * len(entries)
    draw.rectangle((8, 8, 8 + width, 8 + height), fill=(0, 0, 0))
    for row, (label, color) in enumerate(entries):
        y = 15 + row * 17
        draw.line((16, y + 5, 40, y + 5), fill=color, width=3)
        draw.text((47, y), label, fill=(255, 255, 255), font=font)


def _cell_color(record: Mapping[str, Any]) -> tuple[int, int, int]:
    if record["disposition"] == "accepted":
        return (0, 255, 100)
    if record["reason"] == BOUNDARY_REASON:
        return (255, 0, 200)
    return (255, 100, 0)


def _nucleus_color(record: Mapping[str, Any]) -> tuple[int, int, int]:
    if record["nucleus_not_covered_by_cell_geometry_warning"]:
        return (255, 221, 0)
    return _cell_color(record)


def _rank_records(records: Sequence[Mapping[str, Any]], seed: str) -> list[Mapping[str, Any]]:
    return sorted(
        records,
        key=lambda item: (
            hashlib.sha256(f"{seed}:{item['candidate_id']}".encode("utf-8")).hexdigest(),
            item["candidate_id"],
        ),
    )


def _rank_warnings(records: Sequence[Mapping[str, Any]], seed: str) -> list[Mapping[str, Any]]:
    """Prioritize largest outside-cell fractions, then break ties by stable hash."""

    return sorted(
        records,
        key=lambda item: (
            -float(item["nucleus_area_outside_cell_fraction"] or 0),
            -float(item["nucleus_area_outside_cell_px2"] or 0),
            hashlib.sha256(f"{seed}:{item['candidate_id']}".encode("utf-8")).hexdigest(),
            item["candidate_id"],
        ),
    )


def _montage(
    base: Any,
    records: Sequence[Mapping[str, Any]],
    *,
    seed: str,
    per_group: int,
    crop_size: int,
    Image: Any,
    ImageDraw: Any,
    ImageFont: Any,
) -> tuple[Any, dict[str, Any]]:
    _require(per_group >= 1, "montage_per_group must be at least 1")
    _require(crop_size >= 32, "montage_crop_size must be at least 32 pixels")
    warnings = [
        item
        for item in records
        if item["disposition"] == "accepted" and item["nucleus_not_covered_by_cell_geometry_warning"]
    ]
    controls = [
        item
        for item in records
        if item["disposition"] == "accepted" and not item["nucleus_not_covered_by_cell_geometry_warning"]
    ]
    selected_warning = _rank_warnings(warnings, seed + ":warning")[:per_group]
    selected_control = _rank_records(controls, seed + ":control")[:per_group]
    selected = [("WARNING", item) for item in selected_warning] + [
        ("CONTROL", item) for item in selected_control
    ]

    columns = 4
    tile_width = 256
    header_height = 48
    tile_height = header_height + 256
    rows = max(1, math.ceil(len(selected) / columns))
    montage = Image.new("RGB", (columns * tile_width, rows * tile_height), (12, 12, 12))
    font = ImageFont.load_default()
    if not selected:
        ImageDraw.Draw(montage).text(
            (16, 16), "No accepted warning/control objects available", fill=(255, 255, 255), font=font
        )
    for slot, (group, record) in enumerate(selected):
        column = slot % columns
        row = slot // columns
        origin_x = column * tile_width
        origin_y = row * tile_height
        cx = float(record["centroids"]["cell_x"])
        cy = float(record["centroids"]["cell_y"])
        left = int(math.floor(cx - crop_size / 2))
        top = int(math.floor(cy - crop_size / 2))
        crop = base.crop((left, top, left + crop_size, top + crop_size)).resize(
            (256, 256), resample=Image.Resampling.BILINEAR
        )
        crop_draw = ImageDraw.Draw(crop)
        scale = 256.0 / crop_size

        def transform(x: float, y: float) -> tuple[float, float]:
            return (x - left) * scale, (y - top) * scale

        cell_color = _cell_color(record)
        nucleus_color = _nucleus_color(record)
        cell_geometry = parse_wkt(record["geometry"]["cell"], location="montage.cell")
        _draw_geometry(
            crop_draw, cell_geometry, color=cell_color, width=2, transform=transform
        )
        if record["geometry"]["nucleus"] is not None:
            nucleus_geometry = parse_wkt(record["geometry"]["nucleus"], location="montage.nucleus")
            _draw_geometry(
                crop_draw,
                nucleus_geometry,
                color=nucleus_color,
                width=1,
                transform=transform,
            )
        montage.paste(crop, (origin_x, origin_y + header_height))
        header = ImageDraw.Draw(montage)
        object_id = record["accepted_object_id"]
        header_color = (255, 221, 0) if group == "WARNING" else cell_color
        header.text(
            (origin_x + 4, origin_y + 2),
            f"{group} object_id",
            fill=header_color,
            font=font,
        )
        header.text((origin_x + 4, origin_y + 15), object_id[:32], fill=(255, 255, 255), font=font)
        header.text((origin_x + 4, origin_y + 28), object_id[32:], fill=(255, 255, 255), font=font)
        if group == "WARNING":
            fraction = 100.0 * float(record["nucleus_area_outside_cell_fraction"] or 0)
            header.text(
                (origin_x + 164, origin_y + 2),
                f"outside={fraction:.2f}%",
                fill=header_color,
                font=font,
            )

    selection = {
        "algorithm": "warning_fraction_desc_then_sha256_rank_v1",
        "seed": seed,
        "requested_per_group": per_group,
        "crop_size_pixels": crop_size,
        "warning_eligible_count": len(warnings),
        "control_eligible_count": len(controls),
        "selected_warning": [
            {"candidate_id": item["candidate_id"], "object_id": item["accepted_object_id"]}
            for item in selected_warning
        ],
        "selected_control": [
            {"candidate_id": item["candidate_id"], "object_id": item["accepted_object_id"]}
            for item in selected_control
        ],
    }
    return montage, selection


def _png_bytes(image: Any) -> bytes:
    stream = BytesIO()
    image.save(stream, format="PNG", compress_level=9, optimize=False)
    return stream.getvalue()


def render_qc(
    package: str | Path,
    output_directory: str | Path,
    *,
    candidate_manifest: str | Path | None = None,
    candidate_dispositions: str | Path | None = None,
    lower_percentile: float = 1.0,
    upper_percentile: float = 99.8,
    montage_per_group: int = 8,
    montage_crop_size: int = 192,
) -> dict[str, Any]:
    """Render a deterministic engineering QC image set into a fresh directory."""

    ledger = validate_candidate_dispositions(
        package,
        candidate_manifest=candidate_manifest,
        candidate_dispositions=candidate_dispositions,
    )
    output = Path(output_directory).resolve()
    _require(not output.exists(), f"QC output directory must be fresh: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    np, Image, ImageDraw, ImageFont, pillow_version, numpy_version = _imaging_dependencies()
    plane, channel, source_path = _load_dapi_plane(ledger, np, Image)
    displayed, low, high = _window_plane(plane, lower_percentile, upper_percentile, np)
    base = Image.fromarray(displayed, mode="L").convert("RGB")
    calibration = ledger.image_manifest["pixel_calibration"]

    overview = base.copy()
    _draw_rois(overview, ledger.annotation_set, ImageDraw)
    scale_bar_um, scale_bar_pixels = _draw_scale_bar(
        overview, ImageDraw, ImageFont, float(calibration["pixel_width_um"])
    )

    disposition = base.copy()
    _draw_rois(disposition, ledger.annotation_set, ImageDraw)
    disposition_draw = ImageDraw.Draw(disposition)
    for record in ledger.records:
        cell_color = _cell_color(record)
        nucleus_color = _nucleus_color(record)
        _draw_geometry(
            disposition_draw,
            parse_wkt(record["geometry"]["cell"], location="candidate.geometry.cell"),
            color=cell_color,
            width=2,
        )
        if record["geometry"]["nucleus"] is not None:
            _draw_geometry(
                disposition_draw,
                parse_wkt(record["geometry"]["nucleus"], location="candidate.geometry.nucleus"),
                color=nucleus_color,
                width=1,
            )
    _draw_legend(disposition, ImageDraw, ImageFont)
    _draw_scale_bar(disposition, ImageDraw, ImageFont, float(calibration["pixel_width_um"]))

    selection_seed = ledger.package_canonical_sha256
    montage, selection = _montage(
        base,
        ledger.records,
        seed=selection_seed,
        per_group=montage_per_group,
        crop_size=montage_crop_size,
        Image=Image,
        ImageDraw=ImageDraw,
        ImageFont=ImageFont,
    )

    images = [
        ("dapi-overview.png", overview),
        ("dapi-candidate-disposition.png", disposition),
        ("dapi-review-montage.png", montage),
    ]
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}.tmp-", dir=output.parent))
    try:
        output_records: list[dict[str, Any]] = []
        for name, image in images:
            payload = _png_bytes(image)
            destination = temporary / name
            destination.write_bytes(payload)
            output_records.append(
                {
                    "relative_path": name,
                    "media_type": "image/png",
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "size_bytes": len(payload),
                    "width_pixels": image.width,
                    "height_pixels": image.height,
                }
            )

        package_payload = ledger.package_path.read_bytes()
        manifest_payload = ledger.manifest_path.read_bytes()
        artifact = ledger.package["cell_objects_artifact"]
        qc_manifest: dict[str, Any] = {
            "schema_version": "ifquant.dapi-qc-render/1.0.0",
            "status": "rendered_unvalidated_engineering_qc",
            "producer": {
                "producer_id": "ifquant_platform.qc_rendering",
                "producer_version": "1.0.0",
                "implementation_sha256": file_sha256(Path(__file__).resolve()),
                "python_version": platform.python_version(),
            },
            "inputs": {
                "package": {
                    "package_id": ledger.package["package_id"],
                    "canonical_sha256": ledger.package_canonical_sha256,
                    "file_sha256": hashlib.sha256(package_payload).hexdigest(),
                    "size_bytes": len(package_payload),
                },
                "cell_objects": {
                    "sha256": artifact["sha256"],
                    "size_bytes": artifact["size_bytes"],
                    "record_count": artifact["record_count"],
                },
                "candidate_dispositions": {
                    "manifest_canonical_sha256": ledger.manifest_canonical_sha256,
                    "manifest_file_sha256": hashlib.sha256(manifest_payload).hexdigest(),
                    "manifest_size_bytes": len(manifest_payload),
                    "artifact_sha256": file_sha256(ledger.artifact_path),
                    "artifact_size_bytes": ledger.artifact_path.stat().st_size,
                    "record_count": len(ledger.records),
                },
                "source_image": {
                    "image_id": ledger.image_manifest["image_id"],
                    "source_sha256": ledger.image_manifest["source_artifact"]["sha256"],
                    "source_size_bytes": ledger.image_manifest["source_artifact"]["size_bytes"],
                    "verified_local_path_sha256": file_sha256(source_path),
                },
                "channel_map": {
                    "channel_map_id": ledger.channel_map["channel_map_id"],
                    "canonical_sha256": canonical_sha256(ledger.channel_map),
                    "channel_id": channel["channel_id"],
                    "marker_id": channel["marker_id"],
                    "role": channel["role"],
                    "source_channel_index": channel["source_channel_index"],
                    "source_channel_name": channel["source_channel_name"],
                },
            },
            "display": {
                "windowing": {
                    "algorithm": "nearest_rank_histogram_v1",
                    "lower_percentile": lower_percentile,
                    "upper_percentile": upper_percentile,
                    "lower_sample_value": low,
                    "upper_sample_value": high,
                    "output_range": [0, 255],
                },
                "pixel_calibration": {
                    "pixel_width_um": calibration["pixel_width_um"],
                    "pixel_height_um": calibration["pixel_height_um"],
                },
                "scale_bar": {"length_um": scale_bar_um, "length_pixels": scale_bar_pixels},
                "colors_rgb": {
                    "accepted": [0, 255, 100],
                    "excluded": [255, 100, 0],
                    "boundary_exclusion": [255, 0, 200],
                    "geometry_warning": [255, 221, 0],
                    "roi": [0, 220, 255],
                },
                "dependency_versions": {"pillow": pillow_version, "numpy": numpy_version},
            },
            "selection": selection,
            "counts": {
                "dispositions": dict(ledger.disposition_counts),
                "reasons": dict(ledger.reason_counts),
                "geometry_warnings": {GEOMETRY_WARNING_CODE: ledger.warning_count},
            },
            "outputs": output_records,
            "claims": {
                "authorization": "none",
                "scientific_validation": False,
                "backend_equivalence": False,
                "model_universality": False,
                "human_review_completed": False,
                "scope": "deterministic engineering visualization only; no visual or scientific QC decision",
            },
        }
        (temporary / "qc-manifest.json").write_bytes(canonical_json_bytes(qc_manifest) + b"\n")
        temporary.replace(output)
    except BaseException:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    return qc_manifest
