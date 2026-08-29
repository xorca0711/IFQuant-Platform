"""Independent validation of canonical IFQuant cell-object packages."""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

from .backends import get_backend
from .canonical import (
    ContractError,
    canonical_json_bytes,
    canonical_sha256,
    file_sha256,
    load_strict_json,
    parse_strict_json,
)
from .method_contracts import (
    load_measurement_definition,
    load_parameter_set,
    resolve_method,
)

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
WKT_RE = re.compile(r"^(POLYGON|MULTIPOLYGON)\s*\(")
WKT_TOKEN_RE = re.compile(
    r"\s*(?:(?P<number>[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)|(?P<punct>[(),]))"
)
RFC3339_UTC_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$"
)
SEMVER_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")

PACKAGE_SCHEMA = "https://ifquant.org/contracts/platform/v1/cell-object-package.schema.json"
IMAGE_SCHEMA = "https://ifquant.org/contracts/platform/v1/image-manifest.schema.json"
CHANNEL_SCHEMA = "https://ifquant.org/contracts/platform/v1/channel-map.schema.json"
ANNOTATION_SCHEMA = "https://ifquant.org/contracts/platform/v1/annotation-set.schema.json"
RUN_SCHEMA = "https://ifquant.org/contracts/platform/v1/segmentation-run.schema.json"
OBJECT_SCHEMA = "https://ifquant.org/contracts/platform/v1/cell-object.schema.json"


@dataclass(frozen=True, slots=True)
class PackageValidationReport:
    status: str
    package_id: str
    package_canonical_sha256: str
    object_count: int
    backend_id: str
    method_instance_sha256: str
    warnings: tuple[str, ...]
    authorization: str = "none"
    scientific_validation: bool = False
    backend_equivalence: bool = False
    model_universality: bool = False
    validation_scope: str = (
        "structural, referential, and byte-integrity validation only; "
        "not biological or scientific validation"
    )

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["warnings"] = list(self.warnings)
        return value


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def _object(value: Any, location: str) -> Mapping[str, Any]:
    _require(isinstance(value, Mapping), f"{location} must be an object")
    return value


def _array(value: Any, location: str) -> list[Any]:
    _require(
        isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)),
        f"{location} must be an array",
    )
    return list(value)


def _exact(
    value: Mapping[str, Any],
    required: set[str] | frozenset[str],
    location: str,
    *,
    optional: set[str] | frozenset[str] = frozenset(),
) -> None:
    actual = set(value)
    missing = sorted(required - actual)
    unknown = sorted(actual - required - optional)
    _require(not missing, f"{location} is missing: {', '.join(missing)}")
    _require(not unknown, f"{location} has unknown fields: {', '.join(unknown)}")


def _identifier(value: Any, location: str) -> str:
    _require(isinstance(value, str) and bool(IDENTIFIER_RE.fullmatch(value)), f"{location} is not a valid identifier")
    return value


def _nullable_identifier(value: Any, location: str) -> str | None:
    if value is None:
        return None
    return _identifier(value, location)


def _sha256(value: Any, location: str) -> str:
    _require(isinstance(value, str) and bool(SHA256_RE.fullmatch(value)), f"{location} must be lowercase SHA-256")
    return value


def _nonempty(value: Any, location: str) -> str:
    _require(isinstance(value, str) and bool(value.strip()), f"{location} must be a non-empty string")
    return value


def _integer(value: Any, location: str, *, minimum: int = 0) -> int:
    _require(isinstance(value, int) and not isinstance(value, bool), f"{location} must be an integer")
    _require(value >= minimum, f"{location} must be at least {minimum}")
    return value


def _number(value: Any, location: str, *, positive: bool = False) -> float:
    _require(isinstance(value, (int, float)) and not isinstance(value, bool), f"{location} must be numeric")
    number = float(value)
    _require(math.isfinite(number), f"{location} must be finite")
    if positive:
        _require(number > 0, f"{location} must be positive")
    return number


def _timestamp(value: Any, location: str) -> datetime:
    text = _nonempty(value, location)
    _require(
        bool(RFC3339_UTC_RE.fullmatch(text)),
        f"{location} must be an RFC 3339 UTC timestamp ending in Z",
    )
    try:
        parsed = datetime.fromisoformat(text.removesuffix("Z") + "+00:00")
    except ValueError as exc:
        raise ContractError(f"{location} is not a valid RFC 3339 timestamp") from exc
    _require(parsed.tzinfo == timezone.utc, f"{location} must use UTC")
    return parsed


def _semver(value: Any, location: str) -> str:
    text = _nonempty(value, location)
    _require(bool(SEMVER_RE.fullmatch(text)), f"{location} must be MAJOR.MINOR.PATCH")
    return text


def _enum(value: Any, allowed: set[str], location: str) -> str:
    _require(isinstance(value, str) and value in allowed, f"{location} must be one of: {', '.join(sorted(allowed))}")
    return value


def _validate_qc(value: Any, location: str) -> Mapping[str, Any]:
    qc = _object(value, location)
    _exact(qc, {"status", "flags"}, location)
    _enum(qc["status"], {"pass", "warn", "fail", "not_evaluated"}, f"{location}.status")
    for index, raw in enumerate(_array(qc["flags"], f"{location}.flags")):
        flag_location = f"{location}.flags[{index}]"
        flag = _object(raw, flag_location)
        _exact(flag, {"code", "severity", "message"}, flag_location)
        _identifier(flag["code"], f"{flag_location}.code")
        _enum(flag["severity"], {"info", "warning", "error"}, f"{flag_location}.severity")
        _nonempty(flag["message"], f"{flag_location}.message")
    return qc


def _validate_calibration(value: Any, location: str) -> Mapping[str, Any]:
    calibration = _object(value, location)
    _exact(
        calibration,
        {"calibration_id", "pixel_width_um", "pixel_height_um", "z_spacing_um", "unit"},
        location,
    )
    _identifier(calibration["calibration_id"], f"{location}.calibration_id")
    _number(calibration["pixel_width_um"], f"{location}.pixel_width_um", positive=True)
    _number(calibration["pixel_height_um"], f"{location}.pixel_height_um", positive=True)
    if calibration["z_spacing_um"] is not None:
        _number(calibration["z_spacing_um"], f"{location}.z_spacing_um", positive=True)
    _require(calibration["unit"] == "um", f"{location}.unit must be 'um'")
    return calibration


def _validate_coordinate_space(value: Any, location: str) -> Mapping[str, Any]:
    coordinate = _object(value, location)
    _exact(
        coordinate,
        {
            "coordinate_space_id",
            "dimension",
            "geometry_unit",
            "axis_order",
            "origin",
            "x_axis_direction",
            "y_axis_direction",
        },
        location,
    )
    _identifier(coordinate["coordinate_space_id"], f"{location}.coordinate_space_id")
    _require(coordinate["dimension"] == "2d", f"{location}.dimension must be '2d'")
    _require(coordinate["geometry_unit"] == "pixel", f"{location}.geometry_unit must be 'pixel'")
    _require(coordinate["axis_order"] == ["x", "y"], f"{location}.axis_order must be ['x', 'y']")
    _require(coordinate["origin"] == "top_left", f"{location}.origin must be 'top_left'")
    _require(coordinate["x_axis_direction"] == "right", f"{location}.x_axis_direction must be 'right'")
    _require(coordinate["y_axis_direction"] == "down", f"{location}.y_axis_direction must be 'down'")
    return coordinate


def _tokenize_wkt(text: str, location: str) -> list[str]:
    tokens: list[str] = []
    position = 0
    while position < len(text):
        match = WKT_TOKEN_RE.match(text, position)
        _require(match is not None, f"{location}.wkt is not valid 2D WKT1")
        tokens.append(match.group("number") or match.group("punct"))
        position = match.end()
    return tokens


def _parse_wkt_body(text: str, geometry_type: str, location: str) -> None:
    prefix = re.match(r"^(POLYGON|MULTIPOLYGON)\s*", text)
    _require(prefix is not None and prefix.group(1) == geometry_type, f"{location}.wkt does not match geometry_type")
    tokens = _tokenize_wkt(text[prefix.end() :], location)
    cursor = 0

    def consume(expected: str | None = None) -> str:
        nonlocal cursor
        _require(cursor < len(tokens), f"{location}.wkt ends unexpectedly")
        token = tokens[cursor]
        if expected is not None:
            _require(token == expected, f"{location}.wkt expected '{expected}'")
        cursor += 1
        return token

    def coordinate() -> tuple[Decimal, Decimal]:
        values: list[Decimal] = []
        for _ in range(2):
            token = consume()
            _require(token not in {"(", ")", ","}, f"{location}.wkt coordinate is incomplete")
            try:
                value = Decimal(token)
            except InvalidOperation as exc:
                raise ContractError(f"{location}.wkt coordinate is invalid") from exc
            _require(value.is_finite(), f"{location}.wkt coordinate must be finite")
            values.append(value)
        _require(
            cursor >= len(tokens) or tokens[cursor] in {",", ")"},
            f"{location}.wkt coordinates must be two-dimensional",
        )
        return values[0], values[1]

    def ring() -> None:
        consume("(")
        points = [coordinate()]
        while cursor < len(tokens) and tokens[cursor] == ",":
            consume(",")
            points.append(coordinate())
        consume(")")
        _require(len(points) >= 4, f"{location}.wkt ring must contain at least four points")
        _require(points[0] == points[-1], f"{location}.wkt ring must be closed")
        _require(len(set(points[:-1])) >= 3, f"{location}.wkt ring must contain three distinct vertices")

    def polygon() -> None:
        consume("(")
        ring()
        while cursor < len(tokens) and tokens[cursor] == ",":
            consume(",")
            ring()
        consume(")")

    consume("(")
    if geometry_type == "POLYGON":
        ring()
        while cursor < len(tokens) and tokens[cursor] == ",":
            consume(",")
            ring()
    else:
        polygon()
        while cursor < len(tokens) and tokens[cursor] == ",":
            consume(",")
            polygon()
    consume(")")
    _require(cursor == len(tokens), f"{location}.wkt has trailing tokens")


def _validate_wkt(value: Any, location: str) -> str:
    geometry = _object(value, location)
    _exact(geometry, {"encoding", "geometry_type", "wkt"}, location)
    _require(geometry["encoding"] == "WKT1", f"{location}.encoding must be WKT1")
    geometry_type = _enum(geometry["geometry_type"], {"POLYGON", "MULTIPOLYGON"}, f"{location}.geometry_type")
    wkt = _nonempty(geometry["wkt"], f"{location}.wkt")
    _parse_wkt_body(wkt, geometry_type, location)
    return wkt


def _safe_relative(root: Path, value: Any, location: str) -> Path:
    text = _nonempty(value, location)
    _require("\\" not in text, f"{location} must use '/' separators")
    relative = PurePosixPath(text)
    _require(not relative.is_absolute() and ".." not in relative.parts, f"{location} must stay inside the package")
    _require(not (relative.parts and ":" in relative.parts[0]), f"{location} must not be a drive path")
    candidate = (root / Path(*relative.parts)).resolve()
    resolved_root = root.resolve()
    _require(candidate.is_relative_to(resolved_root), f"{location} escapes the package root")
    _require(candidate.is_file(), f"{location} does not exist: {text}")
    return candidate


def _source_artifact_path(package_root: Path, value: Any) -> Path:
    """Resolve a v1 source URI to a local file whose bytes can be attested."""

    source_uri = _nonempty(value, "image_manifest.source_artifact.source_uri")
    direct_path = Path(source_uri)
    if direct_path.is_absolute():
        candidate = direct_path.resolve()
    else:
        parsed = urlparse(source_uri)
        if parsed.scheme:
            _require(
                parsed.scheme == "file",
                "source_uri must be a local path or file URI for byte attestation",
            )
            _require(
                parsed.netloc in {"", "localhost"},
                "source_uri file URI must not name a remote host",
            )
            candidate = Path(url2pathname(unquote(parsed.path))).resolve()
        else:
            candidate = _safe_relative(
                package_root,
                source_uri,
                "image_manifest.source_artifact.source_uri",
            )
    _require(candidate.is_file(), f"source artifact does not exist: {source_uri}")
    return candidate


def _load_mapping(path: Path, location: str) -> Mapping[str, Any]:
    value = load_strict_json(path)
    return _object(value, location)


def _validate_image(value: Mapping[str, Any]) -> None:
    _exact(
        value,
        {
            "$schema",
            "contract_type",
            "contract_version",
            "image_id",
            "biological_unit_id",
            "source_artifact",
            "dimensions",
            "pixel_calibration",
            "coordinate_space",
            "acquisition",
            "provenance",
        },
        "image_manifest",
    )
    _require(value["$schema"] == IMAGE_SCHEMA, "image_manifest.$schema is unsupported")
    _require(value["contract_type"] == "ifquant_platform_image_manifest", "image_manifest.contract_type is unsupported")
    _require(value["contract_version"] == "1.0.0", "image_manifest.contract_version is unsupported")
    _identifier(value["image_id"], "image_manifest.image_id")
    _identifier(value["biological_unit_id"], "image_manifest.biological_unit_id")

    artifact = _object(value["source_artifact"], "image_manifest.source_artifact")
    _exact(artifact, {"source_uri", "sha256", "size_bytes", "media_type"}, "image_manifest.source_artifact")
    _nonempty(artifact["source_uri"], "image_manifest.source_artifact.source_uri")
    _sha256(artifact["sha256"], "image_manifest.source_artifact.sha256")
    _integer(artifact["size_bytes"], "image_manifest.source_artifact.size_bytes")
    _nonempty(artifact["media_type"], "image_manifest.source_artifact.media_type")

    dimensions = _object(value["dimensions"], "image_manifest.dimensions")
    _exact(dimensions, {"width_pixels", "height_pixels", "z_planes", "timepoints"}, "image_manifest.dimensions")
    for key in dimensions:
        _integer(dimensions[key], f"image_manifest.dimensions.{key}", minimum=1)
    _require(
        dimensions["z_planes"] == 1 and dimensions["timepoints"] == 1,
        "canonical v1 supports only singleton Z/T 2D images",
    )
    _validate_calibration(value["pixel_calibration"], "image_manifest.pixel_calibration")
    _validate_coordinate_space(value["coordinate_space"], "image_manifest.coordinate_space")

    acquisition = _object(value["acquisition"], "image_manifest.acquisition")
    group_fields = {"mouse_id", "specimen_id", "section_id", "slide_id", "batch_id", "scanner_id"}
    _exact(acquisition, group_fields | {"acquired_at"}, "image_manifest.acquisition")
    for key in group_fields:
        _nullable_identifier(acquisition[key], f"image_manifest.acquisition.{key}")
    if acquisition["acquired_at"] is not None:
        _timestamp(acquisition["acquired_at"], "image_manifest.acquisition.acquired_at")

    provenance = _object(value["provenance"], "image_manifest.provenance")
    _exact(provenance, {"created_at", "producer_id", "producer_version", "code_sha256", "ingest_config_sha256"}, "image_manifest.provenance")
    _timestamp(provenance["created_at"], "image_manifest.provenance.created_at")
    _identifier(provenance["producer_id"], "image_manifest.provenance.producer_id")
    _semver(provenance["producer_version"], "image_manifest.provenance.producer_version")
    _sha256(provenance["code_sha256"], "image_manifest.provenance.code_sha256")
    _sha256(provenance["ingest_config_sha256"], "image_manifest.provenance.ingest_config_sha256")


def _validate_channel_map(value: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    _exact(value, {"$schema", "contract_type", "contract_version", "channel_map_id", "image_id", "channels", "provenance"}, "channel_map")
    _require(value["$schema"] == CHANNEL_SCHEMA, "channel_map.$schema is unsupported")
    _require(value["contract_type"] == "ifquant_platform_channel_map", "channel_map.contract_type is unsupported")
    _require(value["contract_version"] == "1.0.0", "channel_map.contract_version is unsupported")
    _identifier(value["channel_map_id"], "channel_map.channel_map_id")
    _identifier(value["image_id"], "channel_map.image_id")
    channels = _array(value["channels"], "channel_map.channels")
    _require(bool(channels), "channel_map.channels must not be empty")
    indices: list[int] = []
    channel_ids: list[str] = []
    descriptors: dict[str, Mapping[str, Any]] = {}
    for index, raw in enumerate(channels):
        location = f"channel_map.channels[{index}]"
        channel = _object(raw, location)
        _exact(channel, {"source_channel_index", "source_channel_name", "channel_id", "marker_id", "role", "intensity"}, location)
        source_index = _integer(channel["source_channel_index"], f"{location}.source_channel_index")
        if channel["source_channel_name"] is not None:
            _nonempty(channel["source_channel_name"], f"{location}.source_channel_name")
        channel_id = _identifier(channel["channel_id"], f"{location}.channel_id")
        marker_id = _identifier(channel["marker_id"], f"{location}.marker_id")
        _enum(channel["role"], {"nuclear_counterstain", "biomarker", "autofluorescence", "other"}, f"{location}.role")
        intensity = _object(channel["intensity"], f"{location}.intensity")
        _exact(intensity, {"representation", "bit_depth", "transform", "scale", "offset", "unit"}, f"{location}.intensity")
        _enum(intensity["representation"], {"unsigned_integer", "floating_point"}, f"{location}.intensity.representation")
        _require(intensity["bit_depth"] in {8, 16, 32, 64}, f"{location}.intensity.bit_depth is unsupported")
        transform = _enum(intensity["transform"], {"none", "linear"}, f"{location}.intensity.transform")
        scale = _number(intensity["scale"], f"{location}.intensity.scale")
        offset = _number(intensity["offset"], f"{location}.intensity.offset")
        if transform == "none":
            _require(scale == 1 and offset == 0, f"{location}: transform none requires scale 1 and offset 0")
        else:
            _require(scale != 0, f"{location}: linear transform requires nonzero scale")
        _enum(intensity["unit"], {"native_sample_value", "normalized_intensity"}, f"{location}.intensity.unit")
        indices.append(source_index)
        channel_ids.append(channel_id)
        descriptors[channel_id] = {
            "marker_id": marker_id,
            "representation": intensity["representation"],
            "transform": transform,
            "unit": intensity["unit"],
        }
    _require(indices == sorted(indices) and len(indices) == len(set(indices)), "channel_map channels must have unique ascending source_channel_index")
    _require(len(channel_ids) == len(set(channel_ids)), "channel_map channel_id values must be unique")

    provenance = _object(value["provenance"], "channel_map.provenance")
    _exact(provenance, {"created_at", "producer_id", "producer_version", "code_sha256", "mapping_config_sha256"}, "channel_map.provenance")
    _timestamp(provenance["created_at"], "channel_map.provenance.created_at")
    _identifier(provenance["producer_id"], "channel_map.provenance.producer_id")
    _semver(provenance["producer_version"], "channel_map.provenance.producer_version")
    _sha256(provenance["code_sha256"], "channel_map.provenance.code_sha256")
    _sha256(provenance["mapping_config_sha256"], "channel_map.provenance.mapping_config_sha256")
    return descriptors


def _validate_review(value: Any, location: str) -> None:
    review = _object(value, location)
    _exact(review, {"state", "reviewer_id", "reviewed_at"}, location)
    state = _enum(review["state"], {"unreviewed", "accepted", "corrected", "rejected"}, f"{location}.state")
    if state == "unreviewed":
        _require(review["reviewer_id"] is None and review["reviewed_at"] is None, f"{location}: unreviewed state cannot name a reviewer or time")
    else:
        _identifier(review["reviewer_id"], f"{location}.reviewer_id")
        _timestamp(review["reviewed_at"], f"{location}.reviewed_at")


def _validate_annotation_set(value: Mapping[str, Any]) -> set[str]:
    _exact(value, {"$schema", "contract_type", "contract_version", "annotation_set_id", "image_id", "coordinate_space_id", "revision", "annotations", "provenance"}, "annotation_set")
    _require(value["$schema"] == ANNOTATION_SCHEMA, "annotation_set.$schema is unsupported")
    _require(value["contract_type"] == "ifquant_platform_annotation_set", "annotation_set.contract_type is unsupported")
    _require(value["contract_version"] == "1.0.0", "annotation_set.contract_version is unsupported")
    _identifier(value["annotation_set_id"], "annotation_set.annotation_set_id")
    _identifier(value["image_id"], "annotation_set.image_id")
    _identifier(value["coordinate_space_id"], "annotation_set.coordinate_space_id")
    _integer(value["revision"], "annotation_set.revision")
    annotations = _array(value["annotations"], "annotation_set.annotations")
    _require(bool(annotations), "annotation_set.annotations must not be empty")
    ids: list[str] = []
    included: set[str] = set()
    for index, raw in enumerate(annotations):
        location = f"annotation_set.annotations[{index}]"
        annotation = _object(raw, location)
        _exact(annotation, {"annotation_id", "label", "inclusion_policy", "geometry", "review"}, location)
        annotation_id = _identifier(annotation["annotation_id"], f"{location}.annotation_id")
        _nonempty(annotation["label"], f"{location}.label")
        policy = _enum(annotation["inclusion_policy"], {"include", "exclude"}, f"{location}.inclusion_policy")
        _validate_wkt(annotation["geometry"], f"{location}.geometry")
        _validate_review(annotation["review"], f"{location}.review")
        ids.append(annotation_id)
        if policy == "include":
            included.add(annotation_id)
    _require(ids == sorted(ids) and len(ids) == len(set(ids)), "annotation_set annotations must have unique ascending annotation_id")

    provenance = _object(value["provenance"], "annotation_set.provenance")
    _exact(provenance, {"created_at", "source_system", "producer_id", "producer_version", "code_sha256", "parent_annotation_set_id"}, "annotation_set.provenance")
    _timestamp(provenance["created_at"], "annotation_set.provenance.created_at")
    _enum(provenance["source_system"], {"qupath", "imported", "generated"}, "annotation_set.provenance.source_system")
    _identifier(provenance["producer_id"], "annotation_set.provenance.producer_id")
    _semver(provenance["producer_version"], "annotation_set.provenance.producer_version")
    _sha256(provenance["code_sha256"], "annotation_set.provenance.code_sha256")
    if provenance["parent_annotation_set_id"] is not None:
        _identifier(provenance["parent_annotation_set_id"], "annotation_set.provenance.parent_annotation_set_id")
    return included


def _validate_segmentation_run(value: Mapping[str, Any]) -> str:
    _exact(value, {"$schema", "contract_type", "contract_version", "segmentation_run_id", "image_id", "channel_map_id", "annotation_set_id", "coordinate_space_id", "backend", "detector", "model", "preprocessing", "boundary_policy", "execution", "qc", "provenance"}, "segmentation_run")
    _require(value["$schema"] == RUN_SCHEMA, "segmentation_run.$schema is unsupported")
    _require(value["contract_type"] == "ifquant_platform_segmentation_run", "segmentation_run.contract_type is unsupported")
    _require(value["contract_version"] == "1.0.0", "segmentation_run.contract_version is unsupported")
    for key in ("segmentation_run_id", "image_id", "channel_map_id", "annotation_set_id", "coordinate_space_id"):
        _identifier(value[key], f"segmentation_run.{key}")

    backend = _object(value["backend"], "segmentation_run.backend")
    _exact(backend, {"kind", "name", "version", "artifact_sha256"}, "segmentation_run.backend")
    backend_id = _enum(backend["kind"], {"native_qupath", "stardist", "instanseg"}, "segmentation_run.backend.kind")
    _nonempty(backend["name"], "segmentation_run.backend.name")
    _nonempty(backend["version"], "segmentation_run.backend.version")
    _sha256(backend["artifact_sha256"], "segmentation_run.backend.artifact_sha256")

    detector = _object(value["detector"], "segmentation_run.detector")
    _exact(detector, {"detector_id", "detector_version", "config_sha256"}, "segmentation_run.detector")
    _identifier(detector["detector_id"], "segmentation_run.detector.detector_id")
    _semver(detector["detector_version"], "segmentation_run.detector.detector_version")
    _sha256(detector["config_sha256"], "segmentation_run.detector.config_sha256")

    model = _object(value["model"], "segmentation_run.model")
    _exact(model, {"model_id", "model_version", "descriptor_sha256", "weights_sha256"}, "segmentation_run.model")
    _identifier(model["model_id"], "segmentation_run.model.model_id")
    _semver(model["model_version"], "segmentation_run.model.model_version")
    _sha256(model["descriptor_sha256"], "segmentation_run.model.descriptor_sha256")
    if model["weights_sha256"] is not None:
        _sha256(model["weights_sha256"], "segmentation_run.model.weights_sha256")
    get_backend(backend_id).validate_run_identity({"backend_id": backend_id, "model": model})

    preprocessing = _object(value["preprocessing"], "segmentation_run.preprocessing")
    _exact(preprocessing, {"profile_id", "profile_sha256"}, "segmentation_run.preprocessing")
    _identifier(preprocessing["profile_id"], "segmentation_run.preprocessing.profile_id")
    _sha256(preprocessing["profile_sha256"], "segmentation_run.preprocessing.profile_sha256")
    _enum(value["boundary_policy"], {"clip_to_annotation", "exclude_touching_annotation_boundary", "include_touching_annotation_boundary"}, "segmentation_run.boundary_policy")

    execution = _object(value["execution"], "segmentation_run.execution")
    _exact(execution, {"script_sha256", "run_config_sha256", "started_at", "completed_at"}, "segmentation_run.execution")
    _sha256(execution["script_sha256"], "segmentation_run.execution.script_sha256")
    _sha256(execution["run_config_sha256"], "segmentation_run.execution.run_config_sha256")
    started = _timestamp(execution["started_at"], "segmentation_run.execution.started_at")
    completed = _timestamp(execution["completed_at"], "segmentation_run.execution.completed_at")
    _require(started <= completed, "segmentation_run execution completes before it starts")
    _validate_qc(value["qc"], "segmentation_run.qc")

    provenance = _object(value["provenance"], "segmentation_run.provenance")
    _exact(provenance, {"created_at", "producer_id", "producer_version", "code_revision", "runtime_sha256"}, "segmentation_run.provenance")
    _timestamp(provenance["created_at"], "segmentation_run.provenance.created_at")
    _identifier(provenance["producer_id"], "segmentation_run.provenance.producer_id")
    _semver(provenance["producer_version"], "segmentation_run.provenance.producer_version")
    _require(isinstance(provenance["code_revision"], str) and bool(re.fullmatch(r"[0-9a-f]{7,64}", provenance["code_revision"])), "segmentation_run.provenance.code_revision must be a lowercase hexadecimal revision")
    _sha256(provenance["runtime_sha256"], "segmentation_run.provenance.runtime_sha256")
    return backend_id


def object_identity_descriptor(record: Mapping[str, Any]) -> dict[str, str]:
    geometry = _object(record["geometry"], "cell_object.geometry")
    cell = _object(geometry["cell"], "cell_object.geometry.cell")
    nucleus = _object(geometry["nucleus"], "cell_object.geometry.nucleus")
    return {
        "annotation_id": str(record["annotation_id"]),
        "cell_wkt": str(cell["wkt"]),
        "image_id": str(record["image_id"]),
        "nucleus_wkt": str(nucleus["wkt"]),
        "segmentation_run_id": str(record["segmentation_run_id"]),
    }


def expected_object_id(record: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(object_identity_descriptor(record))).hexdigest()


def _validate_cell_object(
    record: Mapping[str, Any],
    *,
    package: Mapping[str, Any],
    included_annotations: set[str],
    channel_descriptors: Mapping[str, Mapping[str, Any]],
    semantic_inputs: Mapping[str, Mapping[str, Any]],
    feature_definitions: Mapping[str, Mapping[str, Any]],
    script_sha256: str,
) -> tuple[str, float, float, str]:
    required = {
        "$schema",
        "contract_type",
        "contract_version",
        "object_id",
        "object_index",
        "package_id",
        "image_id",
        "biological_unit_id",
        "annotation_id",
        "segmentation_run_id",
        "coordinate_space_id",
        "geometry",
        "centroids",
        "morphology_measurements",
        "intensity_measurements",
        "qc",
        "review",
        "provenance",
    }
    _exact(record, required, "cell_object", optional={"predictions"})
    _require(record["$schema"] == OBJECT_SCHEMA, "cell_object.$schema is unsupported")
    _require(record["contract_type"] == "ifquant_platform_cell_object", "cell_object.contract_type is unsupported")
    _require(record["contract_version"] == "1.0.0", "cell_object.contract_version is unsupported")
    object_id = _sha256(record["object_id"], "cell_object.object_id")
    _integer(record["object_index"], "cell_object.object_index")
    for key in ("package_id", "image_id", "biological_unit_id", "annotation_id", "segmentation_run_id", "coordinate_space_id"):
        _identifier(record[key], f"cell_object.{key}")
    _require(record["package_id"] == package["package_id"], "cell_object package_id mismatch")
    _require(record["image_id"] == package["image"]["image_id"], "cell_object image_id mismatch")
    _require(record["biological_unit_id"] == package["biological_unit"]["biological_unit_id"], "cell_object biological_unit_id mismatch")
    _require(record["annotation_id"] in included_annotations, "cell_object annotation_id does not resolve to an included annotation")
    _require(record["segmentation_run_id"] == package["segmentation_run"]["segmentation_run_id"], "cell_object segmentation_run_id mismatch")
    _require(record["coordinate_space_id"] == package["coordinate_space"]["coordinate_space_id"], "cell_object coordinate_space_id mismatch")

    geometry = _object(record["geometry"], "cell_object.geometry")
    _exact(geometry, {"cell", "nucleus"}, "cell_object.geometry")
    cell_wkt = _validate_wkt(geometry["cell"], "cell_object.geometry.cell")
    _validate_wkt(geometry["nucleus"], "cell_object.geometry.nucleus")
    _require(object_id == expected_object_id(record), "cell_object object_id does not match canonical geometry identity")

    centroids = _object(record["centroids"], "cell_object.centroids")
    _exact(centroids, {"cell_x", "cell_y", "nucleus_x", "nucleus_y", "unit"}, "cell_object.centroids")
    cell_x = _number(centroids["cell_x"], "cell_object.centroids.cell_x")
    cell_y = _number(centroids["cell_y"], "cell_object.centroids.cell_y")
    _number(centroids["nucleus_x"], "cell_object.centroids.nucleus_x")
    _number(centroids["nucleus_y"], "cell_object.centroids.nucleus_y")
    _require(centroids["unit"] == "pixel", "cell_object.centroids.unit must be pixel")

    morphology_ids: list[str] = []
    morphology = _array(record["morphology_measurements"], "cell_object.morphology_measurements")
    _require(bool(morphology), "cell_object morphology_measurements must not be empty")
    for index, raw in enumerate(morphology):
        location = f"cell_object.morphology_measurements[{index}]"
        measurement = _object(raw, location)
        _exact(measurement, {"measurement_id", "compartment", "feature", "value", "unit"}, location)
        measurement_id = _identifier(measurement["measurement_id"], f"{location}.measurement_id")
        morphology_ids.append(measurement_id)
        compartment = _enum(measurement["compartment"], {"cell", "nucleus", "cytoplasm"}, f"{location}.compartment")
        feature = _enum(measurement["feature"], {"area", "perimeter", "circularity", "solidity", "eccentricity", "major_axis_length", "minor_axis_length", "nucleus_cell_area_ratio"}, f"{location}.feature")
        number = _number(measurement["value"], f"{location}.value")
        _require(number >= 0, f"{location}.value must be nonnegative")
        if feature in {"circularity", "solidity", "nucleus_cell_area_ratio"}:
            _require(number <= 1, f"{location}.value must not exceed 1")
        unit = _enum(measurement["unit"], {"um2", "um", "ratio"}, f"{location}.unit")
        definition = feature_definitions.get(measurement_id)
        _require(definition is not None and definition["feature_kind"] == "morphology", f"{location} is not declared as a morphology feature")
        _require(definition["compartment"] == compartment, f"{location} compartment disagrees with measurement definition")
        _require(definition["statistic"] == feature, f"{location} feature disagrees with measurement definition")
        _require(definition["unit"] == unit, f"{location} unit disagrees with measurement definition")
    _require(morphology_ids == sorted(morphology_ids) and len(morphology_ids) == len(set(morphology_ids)), "morphology measurements must have unique ascending measurement_id")
    expected_morphology = {
        feature_id
        for feature_id, definition in feature_definitions.items()
        if definition["feature_kind"] == "morphology"
    }
    _require(set(morphology_ids) == expected_morphology, "cell_object must carry all and only declared morphology features")

    intensity_ids: list[str] = []
    intensities = _array(record["intensity_measurements"], "cell_object.intensity_measurements")
    _require(bool(intensities), "cell_object intensity_measurements must not be empty")
    for index, raw in enumerate(intensities):
        location = f"cell_object.intensity_measurements[{index}]"
        measurement = _object(raw, location)
        _exact(measurement, {"measurement_id", "channel_id", "marker_id", "compartment", "statistic", "value", "unit"}, location)
        measurement_id = _identifier(measurement["measurement_id"], f"{location}.measurement_id")
        intensity_ids.append(measurement_id)
        channel_id = _identifier(measurement["channel_id"], f"{location}.channel_id")
        marker_id = _identifier(measurement["marker_id"], f"{location}.marker_id")
        channel_descriptor = channel_descriptors.get(channel_id)
        _require(
            channel_descriptor is not None and channel_descriptor["marker_id"] == marker_id,
            f"{location} channel/marker mapping mismatch",
        )
        compartment = _enum(measurement["compartment"], {"cell", "nucleus", "cytoplasm"}, f"{location}.compartment")
        statistic = _enum(measurement["statistic"], {"mean", "median", "minimum", "maximum", "standard_deviation", "sum"}, f"{location}.statistic")
        _number(measurement["value"], f"{location}.value")
        unit = _enum(measurement["unit"], {"native_sample_value", "normalized_intensity", "integrated_native_sample_value"}, f"{location}.unit")
        definition = feature_definitions.get(measurement_id)
        _require(definition is not None and definition["feature_kind"] == "intensity", f"{location} is not declared as an intensity feature")
        statistic_crosswalk = {
            "integrated_intensity": "sum",
            "stddev": "standard_deviation",
        }
        expected_statistic = statistic_crosswalk.get(definition["statistic"], definition["statistic"])
        _require(definition["compartment"] == compartment, f"{location} compartment disagrees with measurement definition")
        _require(expected_statistic == statistic, f"{location} statistic disagrees with measurement definition")
        _require(definition["unit"] == unit, f"{location} unit disagrees with measurement definition")
        _require(definition["input_id"] == channel_id, f"{location} channel_id disagrees with semantic input")
        semantic_input = semantic_inputs.get(channel_id)
        _require(semantic_input is not None, f"{location} semantic input is missing")
        _require(semantic_input["marker_id"] == marker_id, f"{location} marker_id disagrees with semantic input")
        coordinate_crosswalk = {
            "native_sample_value": "native_sample_value",
            "normalized_intensity": "normalized_unit_interval",
        }
        transform_crosswalk = {"none": "none", "linear": "linear_rescale"}
        _require(
            semantic_input["intensity_coordinate"]
            == coordinate_crosswalk[channel_descriptor["unit"]],
            f"{location} intensity coordinate disagrees with channel map",
        )
        _require(
            semantic_input["intensity_representation"]
            == channel_descriptor["representation"],
            f"{location} intensity representation disagrees with channel map",
        )
        _require(
            semantic_input["intensity_transform"]
            == transform_crosswalk[channel_descriptor["transform"]],
            f"{location} intensity transform disagrees with channel map",
        )
    _require(intensity_ids == sorted(intensity_ids) and len(intensity_ids) == len(set(intensity_ids)), "intensity measurements must have unique ascending measurement_id")
    expected_intensity = {
        feature_id
        for feature_id, definition in feature_definitions.items()
        if definition["feature_kind"] == "intensity"
    }
    _require(set(intensity_ids) == expected_intensity, "cell_object must carry all and only declared intensity features")

    prediction_ids: list[str] = []
    for index, raw in enumerate(_array(record.get("predictions", []), "cell_object.predictions")):
        location = f"cell_object.predictions[{index}]"
        prediction = _object(raw, location)
        _exact(prediction, {"prediction_id", "task_id", "model_id", "model_sha256", "label", "score", "calibrated_probability", "abstained", "abstention_reason"}, location)
        prediction_ids.append(_identifier(prediction["prediction_id"], f"{location}.prediction_id"))
        _identifier(prediction["task_id"], f"{location}.task_id")
        _identifier(prediction["model_id"], f"{location}.model_id")
        _sha256(prediction["model_sha256"], f"{location}.model_sha256")
        _require(isinstance(prediction["abstained"], bool), f"{location}.abstained must be boolean")
        if prediction["abstained"]:
            _require(prediction["label"] is None and prediction["score"] is None, f"{location}: abstained prediction cannot carry label or score")
            _nonempty(prediction["abstention_reason"], f"{location}.abstention_reason")
        else:
            _nonempty(prediction["label"], f"{location}.label")
            score = _number(prediction["score"], f"{location}.score")
            _require(0 <= score <= 1, f"{location}.score must be in [0, 1]")
            _require(prediction["abstention_reason"] is None, f"{location}: non-abstained prediction cannot carry an abstention reason")
        if prediction["calibrated_probability"] is not None:
            probability = _number(prediction["calibrated_probability"], f"{location}.calibrated_probability")
            _require(0 <= probability <= 1, f"{location}.calibrated_probability must be in [0, 1]")
    _require(prediction_ids == sorted(prediction_ids) and len(prediction_ids) == len(set(prediction_ids)), "predictions must have unique ascending prediction_id")

    _validate_qc(record["qc"], "cell_object.qc")
    review = _object(record["review"], "cell_object.review")
    _exact(review, {"state", "revision", "reviewer_id", "reviewed_at", "notes", "supersedes_object_id"}, "cell_object.review")
    state = _enum(review["state"], {"unreviewed", "accepted", "corrected", "rejected"}, "cell_object.review.state")
    revision = _integer(review["revision"], "cell_object.review.revision")
    if state == "unreviewed":
        _require(revision == 0, "unreviewed cell_object revision must be zero")
        _require(review["reviewer_id"] is None and review["reviewed_at"] is None, "unreviewed cell_object cannot name reviewer/time")
    else:
        _identifier(review["reviewer_id"], "cell_object.review.reviewer_id")
        _timestamp(review["reviewed_at"], "cell_object.review.reviewed_at")
    if review["notes"] is not None:
        _nonempty(review["notes"], "cell_object.review.notes")
    if state == "corrected":
        _require(revision > 0, "corrected cell_object revision must be positive")
        _sha256(review["supersedes_object_id"], "cell_object.review.supersedes_object_id")
    else:
        _require(review["supersedes_object_id"] is None, "only corrected cell_objects may supersede another object")

    provenance = _object(record["provenance"], "cell_object.provenance")
    _exact(provenance, {"created_at", "source_detection_id", "exporter_id", "exporter_version", "exporter_code_sha256"}, "cell_object.provenance")
    _timestamp(provenance["created_at"], "cell_object.provenance.created_at")
    _nonempty(provenance["source_detection_id"], "cell_object.provenance.source_detection_id")
    _identifier(provenance["exporter_id"], "cell_object.provenance.exporter_id")
    _semver(provenance["exporter_version"], "cell_object.provenance.exporter_version")
    _sha256(provenance["exporter_code_sha256"], "cell_object.provenance.exporter_code_sha256")
    _require(provenance["exporter_code_sha256"] == script_sha256, "cell_object exporter code hash does not match segmentation script")
    return str(record["annotation_id"]), cell_y, cell_x, cell_wkt


def _load_jsonl(path: Path) -> tuple[list[Mapping[str, Any]], bytes]:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise ContractError(f"cannot read cell-object artifact {path}: {exc}") from exc
    if not payload:
        return [], payload
    _require(b"\r" not in payload, "cell-object JSONL must use LF line endings")
    _require(payload.endswith(b"\n"), "cell-object JSONL must end with LF")
    records: list[Mapping[str, Any]] = []
    for index, line in enumerate(payload[:-1].split(b"\n")):
        _require(bool(line), f"cell-object JSONL line {index + 1} is blank")
        value = parse_strict_json(line, source=f"{path}:{index + 1}")
        record = _object(value, f"cell_objects[{index}]")
        _require(canonical_json_bytes(record) == line, f"cell-object JSONL line {index + 1} is not canonical JSON")
        records.append(record)
    return records, payload


def validate_cell_package(package_path: str | Path) -> PackageValidationReport:
    requested = Path(package_path)
    source = requested / "package.json" if requested.is_dir() else requested
    package_root = source.parent
    package = _load_mapping(source, "package")
    package_fields = {
        "$schema",
        "contract_type",
        "contract_version",
        "package_id",
        "image",
        "biological_unit",
        "channel_map",
        "annotation_set",
        "pixel_calibration",
        "coordinate_space",
        "segmentation_run",
        "measurement_method",
        "cell_objects_artifact",
        "qc",
        "review",
        "provenance",
    }
    _exact(package, package_fields, "package")
    _require(package["$schema"] == PACKAGE_SCHEMA, "package.$schema is unsupported")
    _require(package["contract_type"] == "ifquant_platform_cell_object_package", "package.contract_type is unsupported")
    _require(package["contract_version"] == "1.0.0", "package.contract_version is unsupported")
    package_id = _identifier(package["package_id"], "package.package_id")

    image_ref = _object(package["image"], "package.image")
    _exact(image_ref, {"image_id", "manifest_relative_path", "manifest_sha256", "source_sha256"}, "package.image")
    image_path = _safe_relative(package_root, image_ref["manifest_relative_path"], "package.image.manifest_relative_path")
    image = _load_mapping(image_path, "image_manifest")
    _validate_image(image)
    _require(image_ref["image_id"] == image["image_id"], "package image_id does not match image manifest")
    _require(_sha256(image_ref["manifest_sha256"], "package.image.manifest_sha256") == canonical_sha256(image), "package image manifest hash mismatch")
    _require(_sha256(image_ref["source_sha256"], "package.image.source_sha256") == image["source_artifact"]["sha256"], "package source image hash mismatch")
    source_artifact_path = _source_artifact_path(
        package_root, image["source_artifact"]["source_uri"]
    )
    _require(
        source_artifact_path.stat().st_size
        == image["source_artifact"]["size_bytes"],
        "source artifact size mismatch",
    )
    _require(
        file_sha256(source_artifact_path) == image["source_artifact"]["sha256"],
        "source artifact SHA-256 mismatch",
    )

    biological = _object(package["biological_unit"], "package.biological_unit")
    biological_fields = {"biological_unit_id", "mouse_id", "specimen_id", "section_id", "slide_id", "batch_id", "scanner_id"}
    _exact(biological, biological_fields, "package.biological_unit")
    _require(_identifier(biological["biological_unit_id"], "package.biological_unit.biological_unit_id") == image["biological_unit_id"], "package biological_unit_id does not match image manifest")
    for key in biological_fields - {"biological_unit_id"}:
        _nullable_identifier(biological[key], f"package.biological_unit.{key}")
        _require(biological[key] == image["acquisition"][key], f"package biological {key} does not match image manifest")

    calibration = _validate_calibration(package["pixel_calibration"], "package.pixel_calibration")
    coordinate = _validate_coordinate_space(package["coordinate_space"], "package.coordinate_space")
    _require(canonical_json_bytes(calibration) == canonical_json_bytes(image["pixel_calibration"]), "package pixel calibration does not match image manifest")
    _require(canonical_json_bytes(coordinate) == canonical_json_bytes(image["coordinate_space"]), "package coordinate space does not match image manifest")

    channel_ref = _object(package["channel_map"], "package.channel_map")
    _exact(channel_ref, {"channel_map_id", "manifest_relative_path", "manifest_sha256"}, "package.channel_map")
    channel_path = _safe_relative(package_root, channel_ref["manifest_relative_path"], "package.channel_map.manifest_relative_path")
    channel_map = _load_mapping(channel_path, "channel_map")
    channel_descriptors = _validate_channel_map(channel_map)
    _require(channel_ref["channel_map_id"] == channel_map["channel_map_id"], "package channel_map_id mismatch")
    _require(_sha256(channel_ref["manifest_sha256"], "package.channel_map.manifest_sha256") == canonical_sha256(channel_map), "package channel-map hash mismatch")
    _require(channel_map["image_id"] == image["image_id"], "channel map targets the wrong image")

    annotation_ref = _object(package["annotation_set"], "package.annotation_set")
    _exact(annotation_ref, {"annotation_set_id", "manifest_relative_path", "manifest_sha256"}, "package.annotation_set")
    annotation_path = _safe_relative(package_root, annotation_ref["manifest_relative_path"], "package.annotation_set.manifest_relative_path")
    annotation_set = _load_mapping(annotation_path, "annotation_set")
    included_annotations = _validate_annotation_set(annotation_set)
    _require(annotation_ref["annotation_set_id"] == annotation_set["annotation_set_id"], "package annotation_set_id mismatch")
    _require(_sha256(annotation_ref["manifest_sha256"], "package.annotation_set.manifest_sha256") == canonical_sha256(annotation_set), "package annotation-set hash mismatch")
    _require(annotation_set["image_id"] == image["image_id"], "annotation set targets the wrong image")
    _require(annotation_set["coordinate_space_id"] == coordinate["coordinate_space_id"], "annotation set uses the wrong coordinate space")

    run_ref = _object(package["segmentation_run"], "package.segmentation_run")
    run_fields = {"segmentation_run_id", "manifest_relative_path", "manifest_sha256", "backend_kind", "backend_sha256", "model_sha256", "weights_sha256", "detector_config_sha256", "preprocessing_sha256"}
    _exact(run_ref, run_fields, "package.segmentation_run")
    run_path = _safe_relative(package_root, run_ref["manifest_relative_path"], "package.segmentation_run.manifest_relative_path")
    run = _load_mapping(run_path, "segmentation_run")
    backend_id = _validate_segmentation_run(run)
    _require(run_ref["segmentation_run_id"] == run["segmentation_run_id"], "package segmentation_run_id mismatch")
    _require(_sha256(run_ref["manifest_sha256"], "package.segmentation_run.manifest_sha256") == canonical_sha256(run), "package segmentation-run hash mismatch")
    _require(run_ref["backend_kind"] == backend_id, "package segmentation backend mismatch")
    _require(_sha256(run_ref["backend_sha256"], "package.segmentation_run.backend_sha256") == run["backend"]["artifact_sha256"], "package backend hash mismatch")
    _require(_sha256(run_ref["model_sha256"], "package.segmentation_run.model_sha256") == run["model"]["descriptor_sha256"], "package model descriptor hash mismatch")
    if run_ref["weights_sha256"] is not None:
        _sha256(run_ref["weights_sha256"], "package.segmentation_run.weights_sha256")
    _require(run_ref["weights_sha256"] == run["model"]["weights_sha256"], "package model weights hash mismatch")
    _require(_sha256(run_ref["detector_config_sha256"], "package.segmentation_run.detector_config_sha256") == run["detector"]["config_sha256"], "package detector config hash mismatch")
    _require(_sha256(run_ref["preprocessing_sha256"], "package.segmentation_run.preprocessing_sha256") == run["preprocessing"]["profile_sha256"], "package preprocessing hash mismatch")
    _require(run["image_id"] == image["image_id"], "segmentation run targets the wrong image")
    _require(run["channel_map_id"] == channel_map["channel_map_id"], "segmentation run uses the wrong channel map")
    _require(run["annotation_set_id"] == annotation_set["annotation_set_id"], "segmentation run uses the wrong annotation set")
    _require(run["coordinate_space_id"] == coordinate["coordinate_space_id"], "segmentation run uses the wrong coordinate space")

    method_ref = _object(package["measurement_method"], "package.measurement_method")
    _exact(method_ref, {"definition_id", "definition_relative_path", "definition_sha256", "parameter_set_id", "parameter_set_relative_path", "parameter_set_sha256", "method_instance_sha256"}, "package.measurement_method")
    definition_path = _safe_relative(package_root, method_ref["definition_relative_path"], "package.measurement_method.definition_relative_path")
    parameter_path = _safe_relative(package_root, method_ref["parameter_set_relative_path"], "package.measurement_method.parameter_set_relative_path")
    definition = load_measurement_definition(definition_path)
    parameter_set = load_parameter_set(parameter_path)
    resolved = resolve_method(definition.document, parameter_set.document)
    feature_definitions = {
        feature["feature_id"]: feature for feature in definition.document["features"]
    }
    semantic_inputs = {
        semantic_input["input_id"]: semantic_input
        for semantic_input in definition.document["semantic_inputs"]
    }
    _require(method_ref["definition_id"] == definition.document["definition_id"], "package measurement definition_id mismatch")
    _require(_sha256(method_ref["definition_sha256"], "package.measurement_method.definition_sha256") == definition.canonical_sha256, "package measurement definition hash mismatch")
    _require(method_ref["parameter_set_id"] == parameter_set.document["parameter_set_id"], "package parameter_set_id mismatch")
    _require(_sha256(method_ref["parameter_set_sha256"], "package.measurement_method.parameter_set_sha256") == parameter_set.canonical_sha256, "package parameter-set hash mismatch")
    _require(_sha256(method_ref["method_instance_sha256"], "package.measurement_method.method_instance_sha256") == resolved.method_instance_sha256, "package method-instance hash mismatch")

    artifact = _object(package["cell_objects_artifact"], "package.cell_objects_artifact")
    _exact(artifact, {"relative_path", "media_type", "schema_id", "sha256", "size_bytes", "record_count", "ordering"}, "package.cell_objects_artifact")
    _require(artifact["media_type"] == "application/x-ndjson", "cell-object artifact media_type is unsupported")
    _require(artifact["schema_id"] == OBJECT_SCHEMA, "cell-object artifact schema_id is unsupported")
    _require(artifact["ordering"] == "object_index_ascending", "cell-object artifact ordering is unsupported")
    object_path = _safe_relative(package_root, artifact["relative_path"], "package.cell_objects_artifact.relative_path")
    expected_artifact_sha256 = _sha256(
        artifact["sha256"], "package.cell_objects_artifact.sha256"
    )
    expected_artifact_size = _integer(
        artifact["size_bytes"], "package.cell_objects_artifact.size_bytes"
    )
    expected_record_count = _integer(
        artifact["record_count"], "package.cell_objects_artifact.record_count"
    )
    _require(
        object_path.stat().st_size == expected_artifact_size,
        "cell-object artifact size mismatch",
    )
    _require(
        file_sha256(object_path) == expected_artifact_sha256,
        "cell-object artifact SHA-256 mismatch",
    )
    records, payload = _load_jsonl(object_path)
    _require(len(payload) == expected_artifact_size, "cell-object artifact size changed during validation")
    _require(
        len(records) == expected_record_count,
        "cell-object artifact record count mismatch",
    )

    sort_keys: list[tuple[str, float, float, str]] = []
    object_ids: list[str] = []
    object_qc_counts = {"pass": 0, "warn": 0, "fail": 0, "not_evaluated": 0}
    reviewed_record_count = 0
    reviewer_evidence: set[str] = set()
    reviewed_times: list[datetime] = []
    script_sha = run["execution"]["script_sha256"]
    for index, record in enumerate(records):
        sort_key = _validate_cell_object(
            record,
            package=package,
            included_annotations=included_annotations,
            channel_descriptors=channel_descriptors,
            semantic_inputs=semantic_inputs,
            feature_definitions=feature_definitions,
            script_sha256=script_sha,
        )
        _require(
            record["object_index"] == index,
            f"cell_object object_index must be contiguous at row {index}",
        )
        sort_keys.append(sort_key)
        object_ids.append(record["object_id"])
        object_qc_counts[record["qc"]["status"]] += 1
        if record["review"]["state"] != "unreviewed":
            reviewed_record_count += 1
            reviewer_evidence.add(record["review"]["reviewer_id"])
            reviewed_times.append(
                _timestamp(record["review"]["reviewed_at"], "cell_object.review.reviewed_at")
            )
    _require(sort_keys == sorted(sort_keys), "cell-object rows do not follow canonical sort order")
    _require(len(object_ids) == len(set(object_ids)), "cell-object object_id values must be unique")

    package_qc = _object(package["qc"], "package.qc")
    _exact(package_qc, {"status", "object_count", "pass_count", "warning_count", "fail_count", "not_evaluated_count", "flags"}, "package.qc")
    _enum(package_qc["status"], {"pass", "warn", "fail", "not_evaluated"}, "package.qc.status")
    counts = [_integer(package_qc[key], f"package.qc.{key}") for key in ("pass_count", "warning_count", "fail_count", "not_evaluated_count")]
    object_count = _integer(package_qc["object_count"], "package.qc.object_count")
    _require(object_count == len(records), "package QC object_count mismatch")
    _require(sum(counts) == object_count, "package QC status counts do not sum to object_count")
    expected_counts = [
        object_qc_counts["pass"],
        object_qc_counts["warn"],
        object_qc_counts["fail"],
        object_qc_counts["not_evaluated"],
    ]
    _require(counts == expected_counts, "package QC status counts do not match cell-object QC states")
    expected_package_status = (
        "not_evaluated"
        if object_count == 0
        else "fail"
        if object_qc_counts["fail"]
        else "warn"
        if object_qc_counts["warn"]
        else "not_evaluated"
        if object_qc_counts["not_evaluated"]
        else "pass"
    )
    _require(package_qc["status"] == expected_package_status, "package QC status does not match cell-object QC states")
    for index, raw in enumerate(_array(package_qc["flags"], "package.qc.flags")):
        flag = _object(raw, f"package.qc.flags[{index}]")
        _exact(flag, {"code", "severity", "message"}, f"package.qc.flags[{index}]")
        _identifier(flag["code"], f"package.qc.flags[{index}].code")
        _enum(flag["severity"], {"info", "warning", "error"}, f"package.qc.flags[{index}].severity")
        _nonempty(flag["message"], f"package.qc.flags[{index}].message")

    review = _object(package["review"], "package.review")
    _exact(review, {"state", "reviewed_object_count", "reviewer_ids", "last_reviewed_at"}, "package.review")
    review_state = _enum(review["state"], {"unreviewed", "in_review", "reviewed", "requires_revision"}, "package.review.state")
    reviewed_count = _integer(review["reviewed_object_count"], "package.review.reviewed_object_count")
    _require(reviewed_count <= object_count, "package reviewed_object_count exceeds object_count")
    _require(reviewed_count == reviewed_record_count, "package reviewed_object_count does not match cell-object review states")
    reviewer_ids = [_identifier(value, "package.review.reviewer_ids") for value in _array(review["reviewer_ids"], "package.review.reviewer_ids")]
    _require(reviewer_ids == sorted(set(reviewer_ids)), "package reviewer_ids must be unique and sorted")
    _require(
        reviewer_ids == sorted(reviewer_evidence),
        "package reviewer_ids do not match cell-object review evidence",
    )
    if review_state == "unreviewed":
        _require(reviewed_count == 0 and not reviewer_ids and review["last_reviewed_at"] is None, "unreviewed package cannot carry review evidence")
    else:
        _require(bool(reviewer_ids), "reviewed package state requires reviewer_ids")
        last_reviewed_at = _timestamp(
            review["last_reviewed_at"], "package.review.last_reviewed_at"
        )
        _require(
            reviewed_times and last_reviewed_at == max(reviewed_times),
            "package last_reviewed_at does not match cell-object review evidence",
        )
    if review_state == "reviewed":
        _require(reviewed_count == object_count, "reviewed package must account for every cell object")
    if review_state == "in_review":
        _require(0 < reviewed_count < object_count, "in_review package must be partially reviewed")

    provenance = _object(package["provenance"], "package.provenance")
    _exact(provenance, {"created_at", "producer_id", "producer_version", "code_revision", "package_config_sha256", "parent_package_id"}, "package.provenance")
    _timestamp(provenance["created_at"], "package.provenance.created_at")
    _identifier(provenance["producer_id"], "package.provenance.producer_id")
    _semver(provenance["producer_version"], "package.provenance.producer_version")
    _require(isinstance(provenance["code_revision"], str) and bool(re.fullmatch(r"[0-9a-f]{7,64}", provenance["code_revision"])), "package.provenance.code_revision must be a lowercase hexadecimal revision")
    _sha256(provenance["package_config_sha256"], "package.provenance.package_config_sha256")
    if provenance["parent_package_id"] is not None:
        _identifier(provenance["parent_package_id"], "package.provenance.parent_package_id")

    warnings: list[str] = []
    if parameter_set.document["scope"]["binding"] == "identifier_only_unattested":
        warnings.append("measurement parameter scope is identifier-only and unattested")
    if any(biological[key] is None for key in ("mouse_id", "slide_id", "batch_id", "scanner_id")):
        warnings.append("one or more ML split-group identities are absent; package is not split-eligible")
    if package_qc["status"] != "pass":
        warnings.append(f"package QC status is {package_qc['status']}")
    if review_state != "reviewed":
        warnings.append(f"package review state is {review_state}")

    return PackageValidationReport(
        status="valid",
        package_id=package_id,
        package_canonical_sha256=canonical_sha256(package),
        object_count=object_count,
        backend_id=backend_id,
        method_instance_sha256=resolved.method_instance_sha256,
        warnings=tuple(warnings),
    )
