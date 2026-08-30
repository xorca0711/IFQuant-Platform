"""Fail-closed validation for governed biological observation sets.

The Phase 2 contract binds reviewed biological and acquisition identities to
immutable image, channel, and annotation manifests. Validation is read-only
and never derives, fills, or rewrites an identifier.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .canonical import canonical_sha256, file_sha256
from .package_validation import (
    _array,
    _enum,
    _exact,
    _identifier,
    _integer,
    _load_mapping,
    _nonempty,
    _nullable_identifier,
    _object,
    _require,
    _safe_relative,
    _semver,
    _sha256,
    _source_artifact_path,
    _timestamp,
    _validate_annotation_set,
    _validate_channel_map,
    _validate_image,
)

GOVERNED_OBSERVATION_SET_SCHEMA = (
    "https://ifquant.org/contracts/platform/v1/governed-observation-set.schema.json"
)


@dataclass(frozen=True, slots=True)
class GovernedObservationSetReport:
    """Deterministic summary of Phase 2 structural and integrity checks."""

    status: str
    observation_set_id: str
    study_id: str
    revision: int
    observation_set_sha256: str
    observation_count: int
    annotation_revision_count: int
    mouse_count: int
    slide_count: int
    batch_count: int
    scanner_count: int
    observation_set_contract_valid: bool = True
    authorization: str = "none"
    scientific_validation: bool = False
    biological_ground_truth: bool = False
    validation_scope: str = (
        "reviewed identity, manifest lineage, referential integrity, and byte integrity only; "
        "not biological ground truth, scientific validation, or downstream authorization"
    )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _manifest_reference(
    root: Path,
    raw: Any,
    location: str,
    *,
    id_field: str,
) -> tuple[Mapping[str, Any], Mapping[str, Any], str]:
    reference = _object(raw, location)
    required = {id_field, "manifest_relative_path", "manifest_sha256"}
    _exact(reference, required, location)
    _identifier(reference[id_field], f"{location}.{id_field}")
    path = _safe_relative(
        root,
        reference["manifest_relative_path"],
        f"{location}.manifest_relative_path",
    )
    manifest = _load_mapping(path, f"{location}.manifest")
    digest = canonical_sha256(manifest)
    _sha256(reference["manifest_sha256"], f"{location}.manifest_sha256")
    _require(
        digest == reference["manifest_sha256"],
        f"{location}.manifest_sha256 does not match the canonical manifest",
    )
    return reference, manifest, digest


def _validate_parent(
    root: Path,
    document: Mapping[str, Any],
    revision: int,
    ancestor_paths: frozenset[Path],
) -> None:
    raw = document["parent"]
    if revision == 0:
        _require(raw is None, "parent must be null for revision 0")
        return

    _require(raw is not None, "parent is required after revision 0")
    reference = _object(raw, "parent")
    _exact(
        reference,
        {"observation_set_id", "manifest_relative_path", "manifest_sha256"},
        "parent",
    )
    _identifier(reference["observation_set_id"], "parent.observation_set_id")
    expected_digest = _sha256(reference["manifest_sha256"], "parent.manifest_sha256")
    parent_path = _safe_relative(
        root,
        reference["manifest_relative_path"],
        "parent.manifest_relative_path",
    )
    parent_report = _validate_governed_observation_set_path(
        parent_path,
        ancestor_paths,
    )
    _require(
        parent_report.observation_set_sha256 == expected_digest,
        "parent.manifest_sha256 does not match the canonical manifest",
    )
    _require(
        parent_report.observation_set_id == reference["observation_set_id"],
        "parent.observation_set_id does not match its manifest",
    )
    _require(
        reference["observation_set_id"] == document["observation_set_id"],
        "parent must retain observation_set_id",
    )
    _require(parent_report.study_id == document["study_id"], "parent must retain study_id")
    _require(
        parent_report.revision == revision - 1,
        "parent revision must immediately precede revision",
    )


def _validate_artifact_reference(root: Path, raw: Any, location: str) -> str:
    artifact = _object(raw, location)
    _exact(artifact, {"relative_path", "media_type", "sha256", "size_bytes"}, location)
    path = _safe_relative(root, artifact["relative_path"], f"{location}.relative_path")
    _nonempty(artifact["media_type"], f"{location}.media_type")
    expected_hash = _sha256(artifact["sha256"], f"{location}.sha256")
    expected_size = _integer(artifact["size_bytes"], f"{location}.size_bytes")
    _require(
        path.stat().st_size == expected_size,
        f"{location}.size_bytes does not match the artifact",
    )
    _require(file_sha256(path) == expected_hash, f"{location}.sha256 does not match the artifact")
    return expected_hash


def _validate_provenance(root: Path, raw: Any) -> None:
    provenance = _object(raw, "provenance")
    _exact(
        provenance,
        {
            "created_at",
            "producer_id",
            "producer_version",
            "code_sha256",
            "code_artifact",
            "identity_source",
        },
        "provenance",
    )
    _timestamp(provenance["created_at"], "provenance.created_at")
    _identifier(provenance["producer_id"], "provenance.producer_id")
    _semver(provenance["producer_version"], "provenance.producer_version")
    code_sha256 = _sha256(provenance["code_sha256"], "provenance.code_sha256")
    code_artifact_sha256 = _validate_artifact_reference(
        root,
        provenance["code_artifact"],
        "provenance.code_artifact",
    )
    _require(
        code_sha256 == code_artifact_sha256,
        "provenance.code_sha256 does not match provenance.code_artifact",
    )

    source = _object(provenance["identity_source"], "provenance.identity_source")
    _exact(source, {"kind", "artifact"}, "provenance.identity_source")
    kind = _enum(
        source["kind"],
        {"registry_artifact", "reviewed_manual_assertion"},
        "provenance.identity_source.kind",
    )
    if kind == "registry_artifact":
        _require(
            source["artifact"] is not None,
            "registry_artifact identity source requires an artifact",
        )
        _validate_artifact_reference(
            root,
            source["artifact"],
            "provenance.identity_source.artifact",
        )
    else:
        _require(
            source["artifact"] is None,
            "reviewed_manual_assertion identity source must not name an artifact",
        )


def _validate_claims(raw: Any) -> None:
    claims = _object(raw, "claims")
    _exact(claims, {"scientific_validation", "biological_ground_truth", "authorization"}, "claims")
    _require(claims["scientific_validation"] is False, "claims.scientific_validation must be false")
    _require(
        claims["biological_ground_truth"] is False,
        "claims.biological_ground_truth must be false",
    )
    _require(claims["authorization"] == "none", "claims.authorization must be 'none'")


def _validate_biological_unit(
    raw: Any,
    image_manifest: Mapping[str, Any],
    location: str,
) -> tuple[str, str, str, str, tuple[str | None, ...]]:
    unit = _object(raw, location)
    fields = {
        "biological_unit_id",
        "mouse_id",
        "specimen_id",
        "section_id",
        "slide_id",
        "batch_id",
        "scanner_id",
    }
    _exact(unit, fields, location)
    biological_unit_id = _identifier(unit["biological_unit_id"], f"{location}.biological_unit_id")
    mouse_id = _identifier(unit["mouse_id"], f"{location}.mouse_id")
    specimen_id = _nullable_identifier(unit["specimen_id"], f"{location}.specimen_id")
    section_id = _nullable_identifier(unit["section_id"], f"{location}.section_id")
    slide_id = _identifier(unit["slide_id"], f"{location}.slide_id")
    batch_id = _identifier(unit["batch_id"], f"{location}.batch_id")
    scanner_id = _identifier(unit["scanner_id"], f"{location}.scanner_id")

    _require(
        biological_unit_id == image_manifest["biological_unit_id"],
        f"{location}.biological_unit_id does not match image_manifest",
    )
    acquisition = image_manifest["acquisition"]
    for field in ("mouse_id", "specimen_id", "section_id", "slide_id", "batch_id", "scanner_id"):
        _require(
            unit[field] == acquisition[field],
            f"{location}.{field} does not match image_manifest",
        )
    stable_identity = (mouse_id, specimen_id, section_id, slide_id)
    return mouse_id, slide_id, batch_id, scanner_id, stable_identity


def _validate_identity_review(raw: Any, location: str) -> None:
    review = _object(raw, location)
    _exact(review, {"state", "reviewer_id", "reviewed_at", "notes"}, location)
    _require(review["state"] == "accepted", f"{location}.state must be accepted")
    _identifier(review["reviewer_id"], f"{location}.reviewer_id")
    _timestamp(review["reviewed_at"], f"{location}.reviewed_at")
    if review["notes"] is not None:
        _nonempty(review["notes"], f"{location}.notes")


def _validate_image_reference(
    root: Path,
    raw: Any,
    location: str,
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    reference = _object(raw, location)
    _exact(
        reference,
        {"image_id", "manifest_relative_path", "manifest_sha256", "source_sha256"},
        location,
    )
    image_id = _identifier(reference["image_id"], f"{location}.image_id")
    path = _safe_relative(
        root,
        reference["manifest_relative_path"],
        f"{location}.manifest_relative_path",
    )
    manifest = _load_mapping(path, f"{location}.manifest")
    _validate_image(manifest)
    _require(manifest["image_id"] == image_id, f"{location}.image_id does not match image_manifest")
    manifest_hash = _sha256(reference["manifest_sha256"], f"{location}.manifest_sha256")
    _require(
        canonical_sha256(manifest) == manifest_hash,
        f"{location}.manifest_sha256 does not match image_manifest",
    )
    source_hash = _sha256(reference["source_sha256"], f"{location}.source_sha256")
    _require(
        source_hash == manifest["source_artifact"]["sha256"],
        f"{location}.source_sha256 does not match image_manifest",
    )
    source_path = _source_artifact_path(root, manifest["source_artifact"]["source_uri"])
    _require(
        source_path.stat().st_size == manifest["source_artifact"]["size_bytes"],
        f"{location} source size does not match image_manifest",
    )
    _require(
        file_sha256(source_path) == source_hash,
        f"{location}.source_sha256 does not match source bytes",
    )
    return reference, manifest


def _validate_channel_reference(
    root: Path,
    raw: Any,
    image_id: str,
    location: str,
) -> Mapping[str, Any]:
    reference, manifest, _digest = _manifest_reference(
        root,
        raw,
        location,
        id_field="channel_map_id",
    )
    _validate_channel_map(manifest)
    _require(
        manifest["channel_map_id"] == reference["channel_map_id"],
        f"{location}.channel_map_id does not match channel_map",
    )
    _require(manifest["image_id"] == image_id, f"{location} does not target the observation image")
    return manifest


def _validate_annotation_lineage(
    root: Path,
    raw: Any,
    *,
    image_manifest: Mapping[str, Any],
    selected_annotation_set_id: Any,
    global_annotation_set_ids: set[str],
    location: str,
) -> int:
    revisions = _array(raw, location)
    _require(bool(revisions), f"{location} must not be empty")
    observation_location = location.removesuffix(".annotation_lineage")
    selected_id = _identifier(
        selected_annotation_set_id,
        f"{observation_location}.selected_annotation_set_id",
    )
    expected_coordinate = image_manifest["coordinate_space"]["coordinate_space_id"]
    seen_ids: set[str] = set()
    previous_id: str | None = None
    previous_hash: str | None = None
    selected_manifest: Mapping[str, Any] | None = None
    selected_inclusions: set[str] = set()

    for index, raw_revision in enumerate(revisions):
        revision_location = f"{location}[{index}]"
        reference = _object(raw_revision, revision_location)
        _exact(
            reference,
            {
                "annotation_set_id",
                "revision",
                "manifest_relative_path",
                "manifest_sha256",
                "parent_manifest_sha256",
                "revision_reason",
            },
            revision_location,
        )
        annotation_id = _identifier(
            reference["annotation_set_id"],
            f"{revision_location}.annotation_set_id",
        )
        revision_number = _integer(reference["revision"], f"{revision_location}.revision")
        _require(
            revision_number == index,
            f"{revision_location}.revision must form a contiguous lineage from 0",
        )
        _require(
            annotation_id not in seen_ids,
            f"{location} annotation_set_id values must be unique",
        )
        _require(
            annotation_id not in global_annotation_set_ids,
            "annotation_set_id values must be unique across observations",
        )
        seen_ids.add(annotation_id)
        global_annotation_set_ids.add(annotation_id)
        parent_hash = reference["parent_manifest_sha256"]
        if index == 0:
            _require(
                parent_hash is None,
                f"{revision_location}.parent_manifest_sha256 must be null",
            )
        else:
            _sha256(parent_hash, f"{revision_location}.parent_manifest_sha256")
            _require(
                parent_hash == previous_hash,
                f"{revision_location}.parent_manifest_sha256 does not bind the previous revision",
            )
        _nonempty(reference["revision_reason"], f"{revision_location}.revision_reason")

        path = _safe_relative(
            root,
            reference["manifest_relative_path"],
            f"{revision_location}.manifest_relative_path",
        )
        manifest = _load_mapping(path, f"{revision_location}.manifest")
        included = _validate_annotation_set(manifest)
        manifest_hash = canonical_sha256(manifest)
        _sha256(reference["manifest_sha256"], f"{revision_location}.manifest_sha256")
        _require(
            reference["manifest_sha256"] == manifest_hash,
            f"{revision_location}.manifest_sha256 does not match annotation_set",
        )
        _require(
            manifest["annotation_set_id"] == annotation_id,
            f"{revision_location}.annotation_set_id does not match annotation_set",
        )
        _require(
            manifest["revision"] == revision_number,
            f"{revision_location}.revision does not match annotation_set",
        )
        _require(
            manifest["image_id"] == image_manifest["image_id"],
            f"{revision_location} targets another image",
        )
        _require(
            manifest["coordinate_space_id"] == expected_coordinate,
            f"{revision_location} uses another coordinate space",
        )
        _require(
            manifest["provenance"]["parent_annotation_set_id"] == previous_id,
            f"{revision_location} parent_annotation_set_id does not bind the previous revision",
        )

        previous_id = annotation_id
        previous_hash = manifest_hash
        selected_manifest = manifest
        selected_inclusions = included

    _require(
        selected_id == previous_id,
        "selected_annotation_set_id must name the final annotation revision",
    )
    _require(
        bool(selected_inclusions),
        "selected annotation revision must contain an inclusion annotation",
    )
    assert selected_manifest is not None
    for index, raw_annotation in enumerate(selected_manifest["annotations"]):
        state = raw_annotation["review"]["state"]
        _require(
            state in {"accepted", "corrected"},
            "selected annotation revision "
            f"annotations[{index}].review.state must be accepted or corrected",
        )
    return len(revisions)


def _validate_governed_observation_set_path(
    manifest_path: Path,
    ancestor_paths: frozenset[Path],
) -> GovernedObservationSetReport:
    manifest_path = manifest_path.resolve()
    _require(
        manifest_path not in ancestor_paths,
        "observation-set parent lineage contains a cycle",
    )
    _require(
        len(ancestor_paths) < 256,
        "observation-set parent lineage exceeds 256 revisions",
    )
    ancestor_paths = ancestor_paths | {manifest_path}

    root = manifest_path.parent.resolve()
    document = _load_mapping(manifest_path, "observation_set")
    _exact(
        document,
        {
            "$schema",
            "contract_type",
            "contract_version",
            "observation_set_id",
            "study_id",
            "revision",
            "revision_reason",
            "parent",
            "observations",
            "provenance",
            "claims",
        },
        "observation_set",
    )
    _require(
        document["$schema"] == GOVERNED_OBSERVATION_SET_SCHEMA,
        "observation_set.$schema is unsupported",
    )
    _require(
        document["contract_type"] == "ifquant_platform_governed_observation_set",
        "observation_set.contract_type is unsupported",
    )
    _require(
        document["contract_version"] == "1.0.0",
        "observation_set.contract_version is unsupported",
    )
    observation_set_id = _identifier(
        document["observation_set_id"],
        "observation_set.observation_set_id",
    )
    study_id = _identifier(document["study_id"], "observation_set.study_id")
    revision = _integer(document["revision"], "observation_set.revision")
    _require(revision <= 255, "observation_set.revision must be at most 255")
    _nonempty(document["revision_reason"], "observation_set.revision_reason")
    _validate_parent(root, document, revision, ancestor_paths)
    _validate_provenance(root, document["provenance"])
    _validate_claims(document["claims"])

    observations = _array(document["observations"], "observation_set.observations")
    _require(bool(observations), "observation_set.observations must not be empty")
    image_ids: list[str] = []
    mice: set[str] = set()
    slides: set[str] = set()
    batches: set[str] = set()
    scanners: set[str] = set()
    stable_units: dict[str, tuple[str | None, ...]] = {}
    unit_ids_by_stable_identity: dict[tuple[str | None, ...], str] = {}
    mouse_by_specimen_id: dict[str, str] = {}
    parents_by_section_id: dict[str, tuple[str, str | None, str]] = {}
    mouse_by_slide_id: dict[str, str] = {}
    channel_map_ids: set[str] = set()
    annotation_set_ids: set[str] = set()
    annotation_revision_count = 0

    for index, raw_observation in enumerate(observations):
        location = f"observation_set.observations[{index}]"
        observation = _object(raw_observation, location)
        _exact(
            observation,
            {
                "image",
                "biological_unit",
                "channel_map",
                "annotation_lineage",
                "selected_annotation_set_id",
                "identity_review",
            },
            location,
        )
        image_reference, image_manifest = _validate_image_reference(
            root,
            observation["image"],
            f"{location}.image",
        )
        image_id = image_reference["image_id"]
        image_ids.append(image_id)
        mouse, slide, batch, scanner, stable_identity = _validate_biological_unit(
            observation["biological_unit"],
            image_manifest,
            f"{location}.biological_unit",
        )
        biological_unit_id = observation["biological_unit"]["biological_unit_id"]
        if biological_unit_id in stable_units:
            _require(
                stable_units[biological_unit_id] == stable_identity,
                f"{location}.biological_unit changes the stable identity for biological_unit_id",
            )
        else:
            stable_units[biological_unit_id] = stable_identity
        if stable_identity in unit_ids_by_stable_identity:
            _require(
                unit_ids_by_stable_identity[stable_identity] == biological_unit_id,
                f"{location}.biological_unit stable identity is assigned to "
                "multiple biological_unit_id values",
            )
        else:
            unit_ids_by_stable_identity[stable_identity] = biological_unit_id

        unit_mouse, unit_specimen, unit_section, unit_slide = stable_identity
        assert unit_mouse is not None
        assert unit_slide is not None
        if unit_specimen is not None:
            if unit_specimen in mouse_by_specimen_id:
                _require(
                    mouse_by_specimen_id[unit_specimen] == unit_mouse,
                    f"{location}.biological_unit specimen_id is assigned to "
                    "multiple mouse_id values",
                )
            else:
                mouse_by_specimen_id[unit_specimen] = unit_mouse
        if unit_section is not None:
            section_parents = (unit_mouse, unit_specimen, unit_slide)
            if unit_section in parents_by_section_id:
                _require(
                    parents_by_section_id[unit_section] == section_parents,
                    f"{location}.biological_unit section_id changes biological hierarchy",
                )
            else:
                parents_by_section_id[unit_section] = section_parents
        if unit_slide in mouse_by_slide_id:
            _require(
                mouse_by_slide_id[unit_slide] == unit_mouse,
                f"{location}.biological_unit slide_id is assigned to multiple mouse_id values",
            )
        else:
            mouse_by_slide_id[unit_slide] = unit_mouse
        mice.add(mouse)
        slides.add(slide)
        batches.add(batch)
        scanners.add(scanner)
        _validate_channel_reference(
            root,
            observation["channel_map"],
            image_id,
            f"{location}.channel_map",
        )
        channel_map_id = observation["channel_map"]["channel_map_id"]
        _require(
            channel_map_id not in channel_map_ids,
            "channel_map_id values must be unique across observations",
        )
        channel_map_ids.add(channel_map_id)
        annotation_revision_count += _validate_annotation_lineage(
            root,
            observation["annotation_lineage"],
            image_manifest=image_manifest,
            selected_annotation_set_id=observation["selected_annotation_set_id"],
            global_annotation_set_ids=annotation_set_ids,
            location=f"{location}.annotation_lineage",
        )
        _validate_identity_review(observation["identity_review"], f"{location}.identity_review")

    _require(
        image_ids == sorted(image_ids) and len(image_ids) == len(set(image_ids)),
        "observation_set.observations must have unique ascending image_id",
    )
    return GovernedObservationSetReport(
        status="valid",
        observation_set_id=observation_set_id,
        study_id=study_id,
        revision=revision,
        observation_set_sha256=canonical_sha256(document),
        observation_count=len(observations),
        annotation_revision_count=annotation_revision_count,
        mouse_count=len(mice),
        slide_count=len(slides),
        batch_count=len(batches),
        scanner_count=len(scanners),
    )


def validate_governed_observation_set(
    observation_set: str | Path,
) -> GovernedObservationSetReport:
    """Validate a governed observation-set document and every bound artifact."""

    supplied_path = Path(observation_set)
    manifest_path = (
        supplied_path / "observation-set.json"
        if supplied_path.is_dir()
        else supplied_path
    )
    return _validate_governed_observation_set_path(
        manifest_path,
        frozenset(),
    )
