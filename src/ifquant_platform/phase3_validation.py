"""Fail-closed validation for Phase 3 nuclear references and split designs.

The validators in this module are intentionally read-only.  They validate a
reviewed DAPI nuclear-instance reference ledger and an image-level split
manifest while recursively retaining the Phase 2 governed-observation
boundary.  Passing either validator is an engineering integrity result; it is
not biological ground truth, scientific validation, or downstream
authorization.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from .canonical import (
    ContractError,
    canonical_json_bytes,
    canonical_sha256,
    file_sha256,
    parse_strict_json,
)
from .dataset_governance import (
    GOVERNED_OBSERVATION_SET_SCHEMA,
    GovernedObservationSetReport,
    validate_governed_observation_set,
)
from .package_validation import (
    _array,
    _enum,
    _exact,
    _identifier,
    _integer,
    _load_mapping,
    _nonempty,
    _object,
    _require,
    _safe_relative,
    _semver,
    _sha256,
    _timestamp,
    _tokenize_wkt,
    _validate_wkt,
)


NUCLEAR_REFERENCE_OBJECT_SCHEMA = (
    "https://ifquant.org/contracts/platform/v1/nuclear-reference-object.schema.json"
)
REFERENCE_IGNORE_REGION_SCHEMA = (
    "https://ifquant.org/contracts/platform/v1/reference-ignore-region.schema.json"
)
NUCLEAR_REFERENCE_SET_SCHEMA = (
    "https://ifquant.org/contracts/platform/v1/nuclear-reference-set.schema.json"
)
SPLIT_MANIFEST_SCHEMA = (
    "https://ifquant.org/contracts/platform/v1/split-manifest.schema.json"
)

_PARTITIONS = ("train", "tuning", "held_out_test")
_HARD_SEPARATION_KEYS = ("mouse_id", "slide_id", "source_family_id")
_DOMAIN_KEYS = ("batch_id", "scanner_id")
_IGNORE_CODES = {
    "physical_edge": {"physical_image_edge", "physical_specimen_edge"},
    "ambiguity": {
        "ambiguous_nuclear_boundary",
        "overlapping_nuclei_not_separable",
    },
    "artifact": {
        "acquisition_artifact",
        "staining_artifact",
        "processing_artifact",
    },
    "unscorable": {
        "insufficient_dapi_signal",
        "saturated_dapi_signal",
        "out_of_focus",
        "other_unscorable",
    },
}


@dataclass(frozen=True, slots=True)
class NuclearReferenceSetReport:
    """Deterministic summary of Phase 3 nuclear-reference integrity checks."""

    status: str
    reference_set_id: str
    study_id: str
    revision: int
    reference_set_sha256: str
    governed_observation_set_id: str
    governed_observation_set_revision: int
    governed_observation_set_sha256: str
    image_count: int
    source_family_count: int
    region_count: int
    nuclear_reference_object_count: int
    reference_ignore_region_count: int
    model_assisted_object_count: int
    model_assisted_single_review_count: int
    confirmatory_reference_ready: bool
    authorization: str = "none"
    scientific_validation: bool = False
    biological_ground_truth: bool = False
    validation_scope: str = (
        "reviewed nuclear-reference structure, lineage, canonical records, source-family "
        "coverage, and byte integrity only; not biological ground truth, scientific "
        "validation, holdout independence, or downstream authorization"
    )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SplitManifestReport:
    """Deterministic summary of Phase 3 image-split integrity checks."""

    status: str
    split_manifest_id: str
    study_id: str
    revision: int
    split_manifest_sha256: str
    reference_set_id: str
    reference_set_revision: int
    reference_set_sha256: str
    assignment_count: int
    train_count: int
    tuning_count: int
    held_out_test_count: int
    held_out_test_image_ids_sha256: str
    held_out_test_locked: bool
    hard_separation_keys: tuple[str, ...] = _HARD_SEPARATION_KEYS
    hard_group_overlap_count: int = 0
    authorization: str = "none"
    scientific_validation: bool = False
    biological_ground_truth: bool = False
    validation_scope: str = (
        "exact image assignment, declared group/domain separation, recursive reference "
        "integrity, and held-out commitment only; not proof of hidden relatedness, "
        "statistical adequacy, scientific validation, or downstream authorization"
    )

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["hard_separation_keys"] = list(self.hard_separation_keys)
        return value


@dataclass(frozen=True, slots=True)
class _ImageContext:
    image_id: str
    biological_unit_id: str
    coordinate_space_id: str
    mouse_id: str
    slide_id: str
    batch_id: str
    scanner_id: str
    source_sha256: str
    include_annotation_ids: frozenset[str]


@dataclass(frozen=True, slots=True)
class _GovernedContext:
    report: GovernedObservationSetReport
    document: Mapping[str, Any]
    images: Mapping[str, _ImageContext]


@dataclass(frozen=True, slots=True)
class _ReferenceContext:
    report: NuclearReferenceSetReport
    document: Mapping[str, Any]
    governed: _GovernedContext
    source_family_by_image: Mapping[str, str]
    reference_image_ids: frozenset[str]
    confirmatory_ready_by_image: Mapping[str, bool]


@dataclass(frozen=True, slots=True)
class _SplitContext:
    report: SplitManifestReport
    document: Mapping[str, Any]
    assignments_by_image: Mapping[str, Mapping[str, Any]]


def _canonical_decimal(token: str) -> str:
    number = Decimal(token)
    text = format(number, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"", "-0"} else text


def _canonical_wkt(geometry_type: str, wkt: str, location: str) -> str:
    """Return the repository's narrow deterministic spelling for valid WKT1."""

    prefix = geometry_type
    _require(wkt.startswith(prefix), f"{location}.wkt does not match geometry_type")
    tokens = _tokenize_wkt(wkt[len(prefix) :], location)
    cursor = 0

    def consume(expected: str | None = None) -> str:
        nonlocal cursor
        _require(cursor < len(tokens), f"{location}.wkt ends unexpectedly")
        token = tokens[cursor]
        if expected is not None:
            _require(token == expected, f"{location}.wkt expected '{expected}'")
        cursor += 1
        return token

    def coordinate() -> tuple[str, str]:
        x = consume()
        y = consume()
        _require(x not in {"(", ")", ","} and y not in {"(", ")", ","},
                 f"{location}.wkt coordinate is incomplete")
        return _canonical_decimal(x), _canonical_decimal(y)

    def ring() -> list[tuple[str, str]]:
        consume("(")
        points = [coordinate()]
        while cursor < len(tokens) and tokens[cursor] == ",":
            consume(",")
            points.append(coordinate())
        consume(")")
        return points

    def polygon() -> list[list[tuple[str, str]]]:
        consume("(")
        rings = [ring()]
        while cursor < len(tokens) and tokens[cursor] == ",":
            consume(",")
            rings.append(ring())
        consume(")")
        return rings

    consume("(")
    if geometry_type == "POLYGON":
        polygons = [[ring()]]
        while cursor < len(tokens) and tokens[cursor] == ",":
            consume(",")
            polygons[0].append(ring())
    else:
        polygons = [polygon()]
        while cursor < len(tokens) and tokens[cursor] == ",":
            consume(",")
            polygons.append(polygon())
    consume(")")
    _require(cursor == len(tokens), f"{location}.wkt has trailing tokens")

    def render_ring(points: list[tuple[str, str]]) -> str:
        return "(" + ", ".join(f"{x} {y}" for x, y in points) + ")"

    def render_polygon(rings: list[list[tuple[str, str]]]) -> str:
        return "(" + ", ".join(render_ring(points) for points in rings) + ")"

    if geometry_type == "POLYGON":
        body = render_polygon(polygons[0])
    else:
        body = "(" + ", ".join(render_polygon(polygon_rings) for polygon_rings in polygons) + ")"
    return f"{geometry_type} {body}"


def _validate_canonical_geometry(raw: Any, location: str) -> Mapping[str, Any]:
    geometry = _object(raw, location)
    wkt = _validate_wkt(geometry, location)
    canonical = _canonical_wkt(str(geometry["geometry_type"]), wkt, location)
    _require(wkt == canonical, f"{location}.wkt is not in canonical WKT1 form")
    return geometry


def _validate_adjudicated_review(raw: Any, location: str) -> tuple[str, ...]:
    review = _object(raw, location)
    _exact(review, {"state", "reviewer_ids", "reviewed_at", "adjudication"}, location)
    _require(review["state"] == "accepted", f"{location}.state must be accepted")
    reviewers = tuple(
        _identifier(value, f"{location}.reviewer_ids[{index}]")
        for index, value in enumerate(_array(review["reviewer_ids"], f"{location}.reviewer_ids"))
    )
    _require(bool(reviewers), f"{location}.reviewer_ids must not be empty")
    _require(
        list(reviewers) == sorted(reviewers) and len(reviewers) == len(set(reviewers)),
        f"{location}.reviewer_ids must be unique and ascending",
    )
    _timestamp(review["reviewed_at"], f"{location}.reviewed_at")

    adjudication = _object(review["adjudication"], f"{location}.adjudication")
    _exact(adjudication, {"method", "adjudicator_id", "notes"}, f"{location}.adjudication")
    method = _enum(
        adjudication["method"],
        {"unanimous", "consensus", "adjudicator_decision"},
        f"{location}.adjudication.method",
    )
    if method == "adjudicator_decision":
        _identifier(adjudication["adjudicator_id"], f"{location}.adjudication.adjudicator_id")
    else:
        _require(
            adjudication["adjudicator_id"] is None,
            f"{location}.adjudication.adjudicator_id must be null unless an adjudicator decided",
        )
    if method == "consensus":
        _require(len(reviewers) >= 2, f"{location}: consensus requires at least two reviewers")
    if adjudication["notes"] is not None:
        _nonempty(adjudication["notes"], f"{location}.adjudication.notes")
    return reviewers


def _load_canonical_ndjson(
    root: Path,
    raw_reference: Any,
    location: str,
    *,
    record_schema: str,
) -> tuple[list[Mapping[str, Any]], Path]:
    reference = _object(raw_reference, location)
    _exact(
        reference,
        {
            "relative_path",
            "media_type",
            "sha256",
            "size_bytes",
            "record_count",
            "record_schema",
            "canonicalization_profile",
            "ordering",
        },
        location,
    )
    path = _safe_relative(root, reference["relative_path"], f"{location}.relative_path")
    _require(
        reference["media_type"] == "application/x-ndjson",
        f"{location}.media_type must be application/x-ndjson",
    )
    _require(reference["record_schema"] == record_schema, f"{location}.record_schema is unsupported")
    _require(
        reference["canonicalization_profile"] == "ifquant_canonical_json_v1",
        f"{location}.canonicalization_profile is unsupported",
    )
    _require(
        reference["ordering"] == "image_id_annotation_id_record_id_ascending",
        f"{location}.ordering is unsupported",
    )
    expected_hash = _sha256(reference["sha256"], f"{location}.sha256")
    expected_size = _integer(reference["size_bytes"], f"{location}.size_bytes")
    expected_count = _integer(reference["record_count"], f"{location}.record_count")
    payload = path.read_bytes()
    _require(len(payload) == expected_size, f"{location}.size_bytes does not match the artifact")
    _require(file_sha256(path) == expected_hash, f"{location}.sha256 does not match the artifact")

    if not payload:
        raw_lines: list[bytes] = []
    else:
        _require(payload.endswith(b"\n"), f"{location} canonical NDJSON must end with LF")
        raw_lines = payload[:-1].split(b"\n")
        _require(all(raw_lines), f"{location} canonical NDJSON must not contain blank lines")

    records: list[Mapping[str, Any]] = []
    for index, raw_line in enumerate(raw_lines):
        record_location = f"{location}.records[{index}]"
        parsed = parse_strict_json(raw_line, source=f"{path}:{index + 1}")
        record = _object(parsed, record_location)
        _require(
            raw_line == canonical_json_bytes(record),
            f"{record_location} is not canonical JSON",
        )
        records.append(record)
    _require(len(records) == expected_count, f"{location}.record_count does not match the artifact")
    return records, path


def _validate_nuclear_record(
    raw: Mapping[str, Any],
    *,
    reference_set_id: str,
    images: Mapping[str, _ImageContext],
    location: str,
) -> tuple[tuple[str, str, str], bool, bool]:
    _exact(
        raw,
        {
            "$schema",
            "contract_type",
            "contract_version",
            "reference_object_id",
            "reference_set_id",
            "image_id",
            "biological_unit_id",
            "annotation_id",
            "coordinate_space_id",
            "target",
            "geometry",
            "creation_mode",
            "prediction_exposure",
            "review",
        },
        location,
    )
    _require(raw["$schema"] == NUCLEAR_REFERENCE_OBJECT_SCHEMA, f"{location}.$schema is unsupported")
    _require(
        raw["contract_type"] == "ifquant_platform_nuclear_reference_object",
        f"{location}.contract_type is unsupported",
    )
    _require(raw["contract_version"] == "1.0.0", f"{location}.contract_version is unsupported")
    reference_object_id = _sha256(raw["reference_object_id"], f"{location}.reference_object_id")
    _require(raw["reference_set_id"] == reference_set_id, f"{location}.reference_set_id does not match")
    image_id = _identifier(raw["image_id"], f"{location}.image_id")
    _require(image_id in images, f"{location}.image_id is not governed by the reference set")
    image = images[image_id]
    _require(
        raw["biological_unit_id"] == image.biological_unit_id,
        f"{location}.biological_unit_id does not match the governed image",
    )
    annotation_id = _identifier(raw["annotation_id"], f"{location}.annotation_id")
    _require(
        annotation_id in image.include_annotation_ids,
        f"{location}.annotation_id does not resolve to a governed include ROI",
    )
    _require(
        raw["coordinate_space_id"] == image.coordinate_space_id,
        f"{location}.coordinate_space_id does not match the governed image",
    )
    target = _object(raw["target"], f"{location}.target")
    _exact(target, {"object_type", "marker_id", "channel_role"}, f"{location}.target")
    _require(
        target == {"object_type": "nucleus", "marker_id": "DAPI", "channel_role": "nuclear"},
        f"{location}.target must identify a DAPI nuclear instance",
    )
    geometry = _validate_canonical_geometry(raw["geometry"], f"{location}.geometry")
    creation_mode = _enum(
        raw["creation_mode"],
        {"human_drawn", "human_corrected_prediction"},
        f"{location}.creation_mode",
    )
    exposure = raw["prediction_exposure"]
    if creation_mode == "human_drawn":
        _require(exposure is None, f"{location}.prediction_exposure must be null for human_drawn")
    else:
        exposure_object = _object(exposure, f"{location}.prediction_exposure")
        _exact(
            exposure_object,
            {"segmentation_run_id", "predicted_object_id", "predicted_geometry_sha256"},
            f"{location}.prediction_exposure",
        )
        _identifier(exposure_object["segmentation_run_id"], f"{location}.prediction_exposure.segmentation_run_id")
        _sha256(exposure_object["predicted_object_id"], f"{location}.prediction_exposure.predicted_object_id")
        _sha256(
            exposure_object["predicted_geometry_sha256"],
            f"{location}.prediction_exposure.predicted_geometry_sha256",
        )
    reviewers = _validate_adjudicated_review(raw["review"], f"{location}.review")
    descriptor = {
        "annotation_id": annotation_id,
        "geometry": geometry,
        "image_id": image_id,
        "reference_set_id": reference_set_id,
        "target": target,
    }
    _require(
        canonical_sha256(descriptor) == reference_object_id,
        f"{location}.reference_object_id does not match its deterministic descriptor",
    )
    model_assisted = creation_mode == "human_corrected_prediction"
    return (image_id, annotation_id, reference_object_id), model_assisted, (
        model_assisted and len(reviewers) == 1
    )


def _validate_ignore_record(
    raw: Mapping[str, Any],
    *,
    reference_set_id: str,
    images: Mapping[str, _ImageContext],
    location: str,
) -> tuple[str, str, str]:
    _exact(
        raw,
        {
            "$schema",
            "contract_type",
            "contract_version",
            "ignore_region_id",
            "reference_set_id",
            "image_id",
            "biological_unit_id",
            "annotation_id",
            "coordinate_space_id",
            "geometry",
            "reason",
            "review",
        },
        location,
    )
    _require(raw["$schema"] == REFERENCE_IGNORE_REGION_SCHEMA, f"{location}.$schema is unsupported")
    _require(
        raw["contract_type"] == "ifquant_platform_reference_ignore_region",
        f"{location}.contract_type is unsupported",
    )
    _require(raw["contract_version"] == "1.0.0", f"{location}.contract_version is unsupported")
    ignore_id = _sha256(raw["ignore_region_id"], f"{location}.ignore_region_id")
    _require(raw["reference_set_id"] == reference_set_id, f"{location}.reference_set_id does not match")
    image_id = _identifier(raw["image_id"], f"{location}.image_id")
    _require(image_id in images, f"{location}.image_id is not governed by the reference set")
    image = images[image_id]
    _require(
        raw["biological_unit_id"] == image.biological_unit_id,
        f"{location}.biological_unit_id does not match the governed image",
    )
    annotation_id = _identifier(raw["annotation_id"], f"{location}.annotation_id")
    _require(
        annotation_id in image.include_annotation_ids,
        f"{location}.annotation_id does not resolve to a governed include ROI",
    )
    _require(
        raw["coordinate_space_id"] == image.coordinate_space_id,
        f"{location}.coordinate_space_id does not match the governed image",
    )
    geometry = _validate_canonical_geometry(raw["geometry"], f"{location}.geometry")
    reason = _object(raw["reason"], f"{location}.reason")
    _exact(reason, {"category", "code", "notes"}, f"{location}.reason")
    category = _enum(reason["category"], set(_IGNORE_CODES), f"{location}.reason.category")
    _enum(reason["code"], _IGNORE_CODES[category], f"{location}.reason.code")
    if reason["notes"] is not None:
        _nonempty(reason["notes"], f"{location}.reason.notes")
    _validate_adjudicated_review(raw["review"], f"{location}.review")
    descriptor = {
        "annotation_id": annotation_id,
        "geometry": geometry,
        "image_id": image_id,
        "reason": reason,
        "reference_set_id": reference_set_id,
    }
    _require(
        canonical_sha256(descriptor) == ignore_id,
        f"{location}.ignore_region_id does not match its deterministic descriptor",
    )
    return image_id, annotation_id, ignore_id


def _validate_artifact_reference(root: Path, raw: Any, location: str) -> str:
    artifact = _object(raw, location)
    _exact(artifact, {"relative_path", "media_type", "sha256", "size_bytes"}, location)
    path = _safe_relative(root, artifact["relative_path"], f"{location}.relative_path")
    _nonempty(artifact["media_type"], f"{location}.media_type")
    expected_hash = _sha256(artifact["sha256"], f"{location}.sha256")
    expected_size = _integer(artifact["size_bytes"], f"{location}.size_bytes")
    _require(path.stat().st_size == expected_size, f"{location}.size_bytes does not match the artifact")
    _require(file_sha256(path) == expected_hash, f"{location}.sha256 does not match the artifact")
    return expected_hash


def _validate_provenance(root: Path, raw: Any, location: str = "provenance") -> None:
    provenance = _object(raw, location)
    _exact(
        provenance,
        {"created_at", "producer_id", "producer_version", "code_sha256", "code_artifact"},
        location,
    )
    _timestamp(provenance["created_at"], f"{location}.created_at")
    _identifier(provenance["producer_id"], f"{location}.producer_id")
    _semver(provenance["producer_version"], f"{location}.producer_version")
    code_sha256 = _sha256(provenance["code_sha256"], f"{location}.code_sha256")
    artifact_sha256 = _validate_artifact_reference(
        root,
        provenance["code_artifact"],
        f"{location}.code_artifact",
    )
    _require(code_sha256 == artifact_sha256, f"{location}.code_sha256 does not match code_artifact")


def _validate_claims(raw: Any, location: str = "claims") -> None:
    claims = _object(raw, location)
    _exact(
        claims,
        {
            "scientific_validation",
            "biological_ground_truth",
            "backend_equivalence",
            "model_universality",
            "authorization",
        },
        location,
    )
    for field in (
        "scientific_validation",
        "biological_ground_truth",
        "backend_equivalence",
        "model_universality",
    ):
        _require(claims[field] is False, f"{location}.{field} must be false")
    _require(claims["authorization"] == "none", f"{location}.authorization must be 'none'")


def _load_governed_context(
    root: Path,
    raw_reference: Any,
    *,
    study_id: str,
) -> _GovernedContext:
    location = "governed_observation_set"
    reference = _object(raw_reference, location)
    _exact(
        reference,
        {"observation_set_id", "revision", "manifest_relative_path", "manifest_sha256"},
        location,
    )
    observation_set_id = _identifier(reference["observation_set_id"], f"{location}.observation_set_id")
    revision = _integer(reference["revision"], f"{location}.revision")
    expected_hash = _sha256(reference["manifest_sha256"], f"{location}.manifest_sha256")
    path = _safe_relative(root, reference["manifest_relative_path"], f"{location}.manifest_relative_path")
    report = validate_governed_observation_set(path)
    _require(report.observation_set_id == observation_set_id, f"{location}.observation_set_id does not match")
    _require(report.revision == revision, f"{location}.revision does not match")
    _require(report.study_id == study_id, f"{location}.study_id does not match the reference set")
    _require(report.observation_set_sha256 == expected_hash, f"{location}.manifest_sha256 does not match")

    document = _load_mapping(path, location)
    _require(document["$schema"] == GOVERNED_OBSERVATION_SET_SCHEMA, f"{location}.$schema is unsupported")
    governed_root = path.parent.resolve()
    images: dict[str, _ImageContext] = {}
    for index, raw_observation in enumerate(document["observations"]):
        observation = _object(raw_observation, f"{location}.observations[{index}]")
        image_reference = _object(observation["image"], f"{location}.observations[{index}].image")
        image_path = _safe_relative(
            governed_root,
            image_reference["manifest_relative_path"],
            f"{location}.observations[{index}].image.manifest_relative_path",
        )
        image_manifest = _load_mapping(image_path, f"{location}.observations[{index}].image.manifest")
        image_id = str(image_manifest["image_id"])
        annotation_reference = _object(
            _array(observation["annotation_lineage"], f"{location}.observations[{index}].annotation_lineage")[-1],
            f"{location}.observations[{index}].annotation_lineage[-1]",
        )
        annotation_path = _safe_relative(
            governed_root,
            annotation_reference["manifest_relative_path"],
            f"{location}.observations[{index}].annotation_lineage[-1].manifest_relative_path",
        )
        annotation_manifest = _load_mapping(
            annotation_path,
            f"{location}.observations[{index}].annotation_lineage[-1].manifest",
        )
        include_ids = frozenset(
            str(annotation["annotation_id"])
            for annotation in annotation_manifest["annotations"]
            if annotation["inclusion_policy"] == "include"
        )
        biological = _object(observation["biological_unit"], f"{location}.observations[{index}].biological_unit")
        acquisition = _object(image_manifest["acquisition"], f"{location}.observations[{index}].image.acquisition")
        images[image_id] = _ImageContext(
            image_id=image_id,
            biological_unit_id=str(biological["biological_unit_id"]),
            coordinate_space_id=str(image_manifest["coordinate_space"]["coordinate_space_id"]),
            mouse_id=str(acquisition["mouse_id"]),
            slide_id=str(acquisition["slide_id"]),
            batch_id=str(acquisition["batch_id"]),
            scanner_id=str(acquisition["scanner_id"]),
            source_sha256=str(image_manifest["source_artifact"]["sha256"]),
            include_annotation_ids=include_ids,
        )
    _require(len(images) == report.observation_count, "governed observation image identities are not unique")
    return _GovernedContext(report=report, document=document, images=images)


def _validate_reference_parent(
    root: Path,
    document: Mapping[str, Any],
    revision: int,
    ancestor_paths: frozenset[Path],
) -> _ReferenceContext | None:
    raw = document["parent"]
    if revision == 0:
        _require(raw is None, "parent must be null for reference-set revision 0")
        return None
    _require(raw is not None, "parent is required after reference-set revision 0")
    parent = _object(raw, "parent")
    _exact(parent, {"reference_set_id", "revision", "manifest_relative_path", "manifest_sha256"}, "parent")
    parent_id = _identifier(parent["reference_set_id"], "parent.reference_set_id")
    parent_revision = _integer(parent["revision"], "parent.revision")
    parent_hash = _sha256(parent["manifest_sha256"], "parent.manifest_sha256")
    parent_path = _safe_relative(root, parent["manifest_relative_path"], "parent.manifest_relative_path")
    context = _validate_nuclear_reference_set_path(parent_path, ancestor_paths)
    _require(context.report.reference_set_id == parent_id, "parent.reference_set_id does not match")
    _require(context.report.revision == parent_revision, "parent.revision does not match")
    _require(context.report.reference_set_sha256 == parent_hash, "parent.manifest_sha256 does not match")
    _require(parent_id == document["reference_set_id"], "parent must retain reference_set_id")
    _require(context.report.study_id == document["study_id"], "parent must retain study_id")
    _require(parent_revision == revision - 1, "parent revision must immediately precede revision")
    return context


def _validate_task_and_policies(root: Path, document: Mapping[str, Any]) -> None:
    task = _object(document["task"], "task")
    _exact(task, {"task_id", "task_type", "target"}, "task")
    _identifier(task["task_id"], "task.task_id")
    _require(task["task_type"] == "dapi_nucleus_instance_segmentation", "task.task_type is unsupported")
    target = _object(task["target"], "task.target")
    _exact(target, {"object_type", "marker_id", "channel_role"}, "task.target")
    _require(
        target == {"object_type": "nucleus", "marker_id": "DAPI", "channel_role": "nuclear"},
        "task.target must identify DAPI nuclei",
    )

    evaluation = _object(document["evaluation_policy"], "evaluation_policy")
    _exact(
        evaluation,
        {
            "evaluation_policy_id",
            "evaluation_policy_version",
            "detector_guard_inherited",
            "evaluation_extent",
            "ignore_region_handling",
            "unreviewed_region_policy",
            "artifact",
        },
        "evaluation_policy",
    )
    _identifier(evaluation["evaluation_policy_id"], "evaluation_policy.evaluation_policy_id")
    _semver(evaluation["evaluation_policy_version"], "evaluation_policy.evaluation_policy_version")
    _require(evaluation["detector_guard_inherited"] is False, "evaluation_policy must not inherit a detector guard")
    _require(
        evaluation["evaluation_extent"] == "reviewed_reference_regions_only",
        "evaluation_policy.evaluation_extent is unsupported",
    )
    _require(
        evaluation["ignore_region_handling"]
        == "exclude_explicit_reference_ignore_regions_before_scoring",
        "evaluation_policy.ignore_region_handling is unsupported",
    )
    _require(
        evaluation["unreviewed_region_policy"] == "not_evaluated",
        "evaluation_policy.unreviewed_region_policy is unsupported",
    )
    _validate_artifact_reference(root, evaluation["artifact"], "evaluation_policy.artifact")

    protocol = _object(document["selection_protocol"], "selection_protocol")
    _exact(protocol, {"protocol_id", "protocol_version", "artifact"}, "selection_protocol")
    _identifier(protocol["protocol_id"], "selection_protocol.protocol_id")
    _semver(protocol["protocol_version"], "selection_protocol.protocol_version")
    _validate_artifact_reference(root, protocol["artifact"], "selection_protocol.artifact")


def _validate_source_families(
    raw: Any,
    images: Mapping[str, _ImageContext],
) -> dict[str, str]:
    ledger = _object(raw, "source_family_ledger")
    _exact(ledger, {"completeness", "ordering", "families"}, "source_family_ledger")
    _require(
        ledger["completeness"] == "complete_for_governed_observation_set",
        "source_family_ledger.completeness is unsupported",
    )
    _require(
        ledger["ordering"] == "source_family_id_ascending_with_image_id_ascending",
        "source_family_ledger.ordering is unsupported",
    )
    families = _array(ledger["families"], "source_family_ledger.families")
    _require(bool(families), "source_family_ledger.families must not be empty")
    family_ids: list[str] = []
    family_by_image: dict[str, str] = {}
    family_by_source_sha256: dict[str, str] = {}
    for index, raw_family in enumerate(families):
        location = f"source_family_ledger.families[{index}]"
        family = _object(raw_family, location)
        _exact(family, {"source_family_id", "description", "image_ids"}, location)
        family_id = _identifier(family["source_family_id"], f"{location}.source_family_id")
        _nonempty(family["description"], f"{location}.description")
        image_ids = [
            _identifier(value, f"{location}.image_ids[{item_index}]")
            for item_index, value in enumerate(_array(family["image_ids"], f"{location}.image_ids"))
        ]
        _require(bool(image_ids), f"{location}.image_ids must not be empty")
        _require(
            image_ids == sorted(image_ids) and len(image_ids) == len(set(image_ids)),
            f"{location}.image_ids must be unique and ascending",
        )
        for image_id in image_ids:
            _require(image_id in images, f"{location}.image_ids contains an unknown governed image")
            _require(image_id not in family_by_image, "source-family image membership must be unique")
            family_by_image[image_id] = family_id
            source_sha256 = images[image_id].source_sha256
            if source_sha256 in family_by_source_sha256:
                _require(
                    family_by_source_sha256[source_sha256] == family_id,
                    "identical source SHA-256 values must not be assigned to conflicting source families",
                )
            else:
                family_by_source_sha256[source_sha256] = family_id
        family_ids.append(family_id)
    _require(
        family_ids == sorted(family_ids) and len(family_ids) == len(set(family_ids)),
        "source families must have unique ascending source_family_id",
    )
    _require(set(family_by_image) == set(images), "source-family ledger must cover every governed image exactly once")
    return family_by_image


def _validate_region_review(raw: Any, location: str) -> None:
    review = _object(raw, location)
    _exact(review, {"state", "reviewer_ids", "reviewed_at", "notes"}, location)
    _require(review["state"] == "accepted", f"{location}.state must be accepted")
    reviewer_ids = [
        _identifier(value, f"{location}.reviewer_ids[{index}]")
        for index, value in enumerate(_array(review["reviewer_ids"], f"{location}.reviewer_ids"))
    ]
    _require(bool(reviewer_ids), f"{location}.reviewer_ids must not be empty")
    _require(
        reviewer_ids == sorted(reviewer_ids) and len(reviewer_ids) == len(set(reviewer_ids)),
        f"{location}.reviewer_ids must be unique and ascending",
    )
    _timestamp(review["reviewed_at"], f"{location}.reviewed_at")
    if review["notes"] is not None:
        _nonempty(review["notes"], f"{location}.notes")
