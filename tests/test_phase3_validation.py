import hashlib
import importlib.util
import json
from copy import deepcopy
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ifquant_platform.canonical import (  # noqa: E402
    ContractError,
    canonical_json_bytes,
    canonical_sha256,
)
from ifquant_platform.phase3_validation import (  # noqa: E402
    compute_held_out_reference_content_sha256,
    validate_nuclear_reference_set,
    validate_split_manifest,
)


FIXTURE = ROOT / "validation" / "fixtures" / "minimal-phase3-reference-split"
EXPECTED_REFERENCE_SET_SHA256 = (
    "f0137f493ef2cecede86f933729d12ac169a528608bfc69b96d82e457f0fb935"
)
EXPECTED_SPLIT_MANIFEST_SHA256 = (
    "43c32b9c947257b79bd00ae59b09adf64883e0b7554606aaa700b2e6a0d3b47d"
)
EXPECTED_HELD_OUT_IMAGE_IDS_SHA256 = (
    "44f3c019439012f5f0136129747a02e98a83354a84e42120f565cd9cdaa70f67"
)
EXPECTED_HELD_OUT_REFERENCE_CONTENT_SHA256 = (
    "a16120a41f7bf114a4c1608cca05757c09a119f50d290abd5e09861645a25900"
)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def canonical_ndjson(records) -> bytes:
    return b"".join(canonical_json_bytes(record) + b"\n" for record in records)


class Phase3ValidationTests(unittest.TestCase):
    def copy_fixture(self, temporary: str) -> Path:
        destination = Path(temporary) / "phase3"
        shutil.copytree(FIXTURE, destination)
        return destination

    def write_reference_artifact(self, root: Path, field: str, records) -> None:
        manifest_path = root / "nuclear-reference-set.json"
        manifest = read_json(manifest_path)
        artifact = manifest["artifacts"][field]
        payload = canonical_ndjson(records)
        (root / artifact["relative_path"]).write_bytes(payload)
        artifact["sha256"] = hashlib.sha256(payload).hexdigest()
        artifact["size_bytes"] = len(payload)
        artifact["record_count"] = len(records)
        write_json(manifest_path, manifest)

    def set_nuclear_geometry(self, record, geometry_type: str, wkt: str) -> None:
        record["geometry"] = {
            "encoding": "WKT1",
            "geometry_type": geometry_type,
            "wkt": wkt,
        }
        descriptor = {
            "annotation_id": record["annotation_id"],
            "geometry": record["geometry"],
            "image_id": record["image_id"],
            "reference_set_id": record["reference_set_id"],
            "target": record["target"],
        }
        record["reference_object_id"] = canonical_sha256(descriptor)

    def set_ignore_geometry_and_reason(
        self,
        record,
        *,
        geometry_type: str | None = None,
        wkt: str | None = None,
        category: str | None = None,
        code: str | None = None,
    ) -> None:
        if geometry_type is not None:
            record["geometry"]["geometry_type"] = geometry_type
        if wkt is not None:
            record["geometry"]["wkt"] = wkt
        if category is not None:
            record["reason"]["category"] = category
        if code is not None:
            record["reason"]["code"] = code
        descriptor = {
            "annotation_id": record["annotation_id"],
            "geometry": record["geometry"],
            "image_id": record["image_id"],
            "reason": record["reason"],
            "reference_set_id": record["reference_set_id"],
        }
        record["ignore_region_id"] = canonical_sha256(descriptor)

    def attest_reference_artifact_bytes(self, root: Path, field: str) -> None:
        manifest_path = root / "nuclear-reference-set.json"
        manifest = read_json(manifest_path)
        artifact = manifest["artifacts"][field]
        payload = (root / artifact["relative_path"]).read_bytes()
        artifact["sha256"] = hashlib.sha256(payload).hexdigest()
        artifact["size_bytes"] = len(payload)
        artifact["record_count"] = len(payload.rstrip(b"\n").split(b"\n")) if payload else 0
        write_json(manifest_path, manifest)

    def bind_split_to_reference(self, root: Path) -> None:
        reference = read_json(root / "nuclear-reference-set.json")
        split_path = root / "split-manifest.json"
        split = read_json(split_path)
        split["reference_set"].update(
            {
                "reference_set_id": reference["reference_set_id"],
                "revision": reference["revision"],
                "manifest_sha256": canonical_sha256(reference),
            }
        )
        write_json(split_path, split)

    def rebind_split_content_commitment_raw(self, root: Path) -> None:
        reference = read_json(root / "nuclear-reference-set.json")
        observation_set = read_json(
            root / reference["governed_observation_set"]["manifest_relative_path"]
        )
        observations = {
            observation["image"]["image_id"]: observation
            for observation in observation_set["observations"]
        }
        family_by_image = {
            image_id: family["source_family_id"]
            for family in reference["source_family_ledger"]["families"]
            for image_id in family["image_ids"]
        }
        nuclear_records = read_jsonl(
            root / reference["artifacts"]["nuclear_reference_objects"]["relative_path"]
        )
        ignore_records = read_jsonl(
            root / reference["artifacts"]["reference_ignore_regions"]["relative_path"]
        )
        split_path = root / "split-manifest.json"
        split = read_json(split_path)
        image_ids = split["held_out_test_commitment"]["image_ids"]
        descriptor = {
            "profile": "ifquant_held_out_reference_content_v1",
            "task": reference["task"],
            "evaluation_policy": reference["evaluation_policy"],
            "selection_protocol": reference["selection_protocol"],
            "images": [
                {
                    "image_id": image_id,
                    "observation": observations[image_id],
                    "source_family_id": family_by_image[image_id],
                    "regions": sorted(
                        (
                            region
                            for region in reference["region_ledger"]["regions"]
                            if region["image_id"] == image_id
                        ),
                        key=lambda region: (region["annotation_id"], region["region_id"]),
                    ),
                    "nuclear_reference_objects": sorted(
                        (
                            record
                            for record in nuclear_records
                            if record["image_id"] == image_id
                        ),
                        key=lambda record: (
                            record["annotation_id"],
                            record["reference_object_id"],
                        ),
                    ),
                    "reference_ignore_regions": sorted(
                        (
                            record
                            for record in ignore_records
                            if record["image_id"] == image_id
                        ),
                        key=lambda record: (
                            record["annotation_id"],
                            record["ignore_region_id"],
                        ),
                    ),
                }
                for image_id in image_ids
            ],
        }
        split["reference_set"]["manifest_sha256"] = canonical_sha256(reference)
        split["reference_set"]["revision"] = reference["revision"]
        split["held_out_test_commitment"]["reference_content_sha256"] = (
            canonical_sha256(descriptor)
        )
        write_json(split_path, split)

    def bind_reference_to_observation_set(self, root: Path) -> None:
        observation_set = read_json(root / "observation-set.json")
        reference_path = root / "nuclear-reference-set.json"
        reference = read_json(reference_path)
        reference["governed_observation_set"].update(
            {
                "observation_set_id": observation_set["observation_set_id"],
                "revision": observation_set["revision"],
                "manifest_sha256": canonical_sha256(observation_set),
            }
        )
        write_json(reference_path, reference)

    def make_reference_successor(self, root: Path) -> None:
        manifest_path = root / "nuclear-reference-set.json"
        parent = read_json(manifest_path)
        parent_path = root / "parent-nuclear-reference-set.json"
        write_json(parent_path, parent)
        successor = deepcopy(parent)
        for field, artifact in successor["artifacts"].items():
            original_path = root / artifact["relative_path"]
            successor_name = f"revision-001-{original_path.name}"
            shutil.copyfile(original_path, root / successor_name)
            successor["artifacts"][field]["relative_path"] = successor_name
        successor["revision"] = 1
        successor["revision_reason"] = "Exercise immediate reference-set lineage."
        successor["parent"] = {
            "reference_set_id": parent["reference_set_id"],
            "revision": parent["revision"],
            "manifest_relative_path": parent_path.name,
            "manifest_sha256": canonical_sha256(parent),
        }
        write_json(manifest_path, successor)

    def make_linked_reference_and_split_successors(self, root: Path) -> None:
        original_split = read_json(root / "split-manifest.json")
        self.make_reference_successor(root)

        parent_split = deepcopy(original_split)
        parent_split["reference_set"]["manifest_relative_path"] = (
            "parent-nuclear-reference-set.json"
        )
        parent_split_path = root / "parent-split-manifest.json"
        write_json(parent_split_path, parent_split)

        reference = read_json(root / "nuclear-reference-set.json")
        successor = deepcopy(original_split)
        successor["revision"] = 1
        successor["revision_reason"] = "Exercise linked reference and split lineage."
        successor["parent"] = {
            "split_manifest_id": parent_split["split_manifest_id"],
            "revision": parent_split["revision"],
            "manifest_relative_path": parent_split_path.name,
            "manifest_sha256": canonical_sha256(parent_split),
        }
        successor["reference_set"].update(
            {
                "revision": reference["revision"],
                "manifest_relative_path": "nuclear-reference-set.json",
                "manifest_sha256": canonical_sha256(reference),
            }
        )
        write_json(root / "split-manifest.json", successor)

    def make_observation_successor(self, root: Path):
        parent = read_json(root / "observation-set.json")
        successor = deepcopy(parent)
        successor["revision"] = 1
        successor["revision_reason"] = "Exercise held-out observation lineage."
        successor["parent"] = {
            "observation_set_id": parent["observation_set_id"],
            "manifest_relative_path": "observation-set.json",
            "manifest_sha256": canonical_sha256(parent),
        }
        successor_path = root / "observation-set-r1.json"
        write_json(successor_path, successor)
        reference_path = root / "nuclear-reference-set.json"
        reference = read_json(reference_path)
        reference["governed_observation_set"].update(
            {
                "revision": 1,
                "manifest_relative_path": successor_path.name,
                "manifest_sha256": canonical_sha256(successor),
            }
        )
        write_json(reference_path, reference)
        return successor_path, successor

    def bind_reference_to_observation_successor(
        self,
        root: Path,
        successor_path: Path,
        successor,
    ) -> None:
        write_json(successor_path, successor)
        reference_path = root / "nuclear-reference-set.json"
        reference = read_json(reference_path)
        reference["governed_observation_set"]["manifest_sha256"] = canonical_sha256(
            successor
        )
        write_json(reference_path, reference)

    def make_split_successor(self, root: Path) -> None:
        manifest_path = root / "split-manifest.json"
        parent = read_json(manifest_path)
        parent_path = root / "parent-split-manifest.json"
        write_json(parent_path, parent)
        successor = deepcopy(parent)
        successor["revision"] = 1
        successor["revision_reason"] = "Exercise immediate split lineage."
        successor["parent"] = {
            "split_manifest_id": parent["split_manifest_id"],
            "revision": parent["revision"],
            "manifest_relative_path": parent_path.name,
            "manifest_sha256": canonical_sha256(parent),
        }
        write_json(manifest_path, successor)

    def test_fixture_reports_exact_scope_and_nonclaims(self):
        reference = validate_nuclear_reference_set(FIXTURE)
        split = validate_split_manifest(FIXTURE)

        self.assertEqual(reference.status, "valid")
        self.assertEqual(reference.reference_set_sha256, EXPECTED_REFERENCE_SET_SHA256)
        self.assertEqual(reference.image_count, 4)
        self.assertEqual(reference.source_family_count, 3)
        self.assertEqual(reference.region_count, 4)
        self.assertEqual(reference.nuclear_reference_object_count, 4)
        self.assertEqual(reference.reference_ignore_region_count, 1)
        self.assertEqual(reference.model_assisted_object_count, 1)
        self.assertEqual(reference.model_assisted_single_review_count, 1)
        self.assertFalse(reference.confirmatory_reference_ready)
        self.assertEqual(reference.authorization, "none")
        self.assertFalse(reference.scientific_validation)
        self.assertFalse(reference.biological_ground_truth)

        self.assertEqual(split.status, "valid")
        self.assertEqual(split.split_manifest_sha256, EXPECTED_SPLIT_MANIFEST_SHA256)
        self.assertEqual(split.assignment_count, 4)
        self.assertEqual((split.train_count, split.tuning_count, split.held_out_test_count), (2, 1, 1))
        self.assertTrue(split.held_out_test_locked)
        self.assertEqual(
            split.held_out_test_image_ids_sha256,
            EXPECTED_HELD_OUT_IMAGE_IDS_SHA256,
        )
        self.assertEqual(
            split.held_out_test_reference_content_sha256,
            EXPECTED_HELD_OUT_REFERENCE_CONTENT_SHA256,
        )
        self.assertEqual(
            compute_held_out_reference_content_sha256(
                FIXTURE,
                ["phase3-image-004"],
            ),
            EXPECTED_HELD_OUT_REFERENCE_CONTENT_SHA256,
        )
        self.assertEqual(split.hard_separation_keys, ("mouse_id", "slide_id", "source_family_id"))
        self.assertEqual(split.hard_group_overlap_count, 0)
        self.assertEqual(split.authorization, "none")
        self.assertFalse(split.scientific_validation)
        self.assertFalse(split.biological_ground_truth)

    def test_reference_artifact_tampering_and_noncanonical_ndjson_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            path = root / "nuclear-reference-objects.jsonl"
            path.write_bytes(path.read_bytes().replace(b"10 10", b"11 10", 1))
            with self.assertRaisesRegex(ContractError, "sha256 does not match"):
                validate_nuclear_reference_set(root)

        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            records = read_jsonl(root / "nuclear-reference-objects.jsonl")
            payload = b"".join(
                (json.dumps(record, ensure_ascii=False, separators=(", ", ": ")) + "\n").encode("utf-8")
                for record in records
            )
            (root / "nuclear-reference-objects.jsonl").write_bytes(payload)
            self.attest_reference_artifact_bytes(root, "nuclear_reference_objects")
            with self.assertRaisesRegex(ContractError, "not canonical JSON"):
                validate_nuclear_reference_set(root)

    def test_geometry_tampering_cannot_retain_reference_object_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            records = read_jsonl(root / "nuclear-reference-objects.jsonl")
            records[0]["geometry"]["wkt"] = (
                "POLYGON ((21 21, 31 21, 31 31, 21 31, 21 21))"
            )
            self.write_reference_artifact(root, "nuclear_reference_objects", records)
            with self.assertRaisesRegex(ContractError, "reference_object_id does not match"):
                validate_nuclear_reference_set(root)

    def test_nuclear_and_ignore_geometry_must_stay_inside_image_and_governed_roi(self):
        cases = (
            (
                "nuclear_reference_objects",
                "outside-image",
                "POLYGON ((-1 10, 10 10, 10 20, -1 20, -1 10))",
                "extends outside image dimensions",
            ),
            (
                "nuclear_reference_objects",
                "outside-roi",
                "POLYGON ((1 10, 4 10, 4 20, 1 20, 1 10))",
                "extends outside its governed inclusion ROI",
            ),
            (
                "reference_ignore_regions",
                "outside-image",
                "POLYGON ((-1 42, 4 42, 4 45, -1 45, -1 42))",
                "extends outside image dimensions",
            ),
            (
                "reference_ignore_regions",
                "outside-roi",
                "POLYGON ((1 42, 4 42, 4 45, 1 45, 1 42))",
                "extends outside its governed inclusion ROI",
            ),
        )
        for artifact, case, wkt, message in cases:
            with self.subTest(artifact=artifact, case=case), tempfile.TemporaryDirectory() as temporary:
                root = self.copy_fixture(temporary)
                filename = (
                    "nuclear-reference-objects.jsonl"
                    if artifact == "nuclear_reference_objects"
                    else "reference-ignore-regions.jsonl"
                )
                records = read_jsonl(root / filename)
                if artifact == "nuclear_reference_objects":
                    self.set_nuclear_geometry(records[0], "POLYGON", wkt)
                else:
                    self.set_ignore_geometry_and_reason(records[0], wkt=wkt)
                self.write_reference_artifact(root, artifact, records)
                with self.assertRaisesRegex(ContractError, message):
                    validate_nuclear_reference_set(root)

    def test_self_intersecting_and_degenerate_reference_geometry_is_rejected(self):
        cases = (
            (
                "self-intersecting",
                "POLYGON ((10 10, 30 30, 10 30, 30 10, 10 20, 10 10))",
                "self-intersects",
            ),
            (
                "degenerate",
                "POLYGON ((10 10, 20 20, 30 30, 10 10))",
                "is degenerate",
            ),
        )
        for case, wkt, message in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = self.copy_fixture(temporary)
                records = read_jsonl(root / "nuclear-reference-objects.jsonl")
                self.set_nuclear_geometry(records[0], "POLYGON", wkt)
                self.write_reference_artifact(root, "nuclear_reference_objects", records)
                with self.assertRaisesRegex(ContractError, message):
                    validate_nuclear_reference_set(root)

    def test_equivalent_noncanonical_geometry_spellings_cannot_create_new_objects(self):
        cases = (
            (
                "cyclic-ring-start",
                "POLYGON",
                "POLYGON ((20 10, 20 20, 10 20, 10 10, 20 10))",
                "not in canonical WKT1 form",
            ),
            (
                "reverse-orientation",
                "POLYGON",
                "POLYGON ((10 10, 10 20, 20 20, 20 10, 10 10))",
                "not in canonical WKT1 form",
            ),
            (
                "redundant-collinear-vertex",
                "POLYGON",
                "POLYGON ((10 10, 15 10, 20 10, 20 20, 10 20, 10 10))",
                "(?:redundant|noncanonical) collinear vertex",
            ),
            (
                "single-member-multipolygon",
                "MULTIPOLYGON",
                "MULTIPOLYGON (((10 10, 20 10, 20 20, 10 20, 10 10)))",
                "must use POLYGON for a single polygon member",
            ),
        )
        for case, geometry_type, wkt, message in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = self.copy_fixture(temporary)
                records = read_jsonl(root / "nuclear-reference-objects.jsonl")
                equivalent = deepcopy(records[0])
                self.set_nuclear_geometry(equivalent, geometry_type, wkt)
                records.insert(1, equivalent)
                reference_path = root / "nuclear-reference-set.json"
                reference = read_json(reference_path)
                reference["region_ledger"]["regions"][0]["counts"][
                    "nuclear_reference_objects"
                ] += 1
                reference["region_ledger"]["counts"]["nuclear_reference_objects"] += 1
                write_json(reference_path, reference)
                self.write_reference_artifact(root, "nuclear_reference_objects", records)
                with self.assertRaisesRegex(ContractError, message):
                    validate_nuclear_reference_set(root)

        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            records = read_jsonl(root / "nuclear-reference-objects.jsonl")
            records.insert(1, deepcopy(records[0]))
            reference_path = root / "nuclear-reference-set.json"
            reference = read_json(reference_path)
            reference["region_ledger"]["regions"][0]["counts"][
                "nuclear_reference_objects"
            ] += 1
            reference["region_ledger"]["counts"]["nuclear_reference_objects"] += 1
            write_json(reference_path, reference)
            self.write_reference_artifact(root, "nuclear_reference_objects", records)
            with self.assertRaisesRegex(ContractError, "duplicate nuclear geometry"):
                validate_nuclear_reference_set(root)

    def test_physical_edge_ignore_reasons_require_the_corresponding_boundary(self):
        cases = (
            (
                "physical_image_edge",
                "physical image boundary",
            ),
            (
                "physical_specimen_edge",
                "governed ROI boundary",
            ),
        )
        for code, message in cases:
            with self.subTest(code=code), tempfile.TemporaryDirectory() as temporary:
                root = self.copy_fixture(temporary)
                records = read_jsonl(root / "reference-ignore-regions.jsonl")
                self.set_ignore_geometry_and_reason(
                    records[0],
                    category="physical_edge",
                    code=code,
                )
                self.write_reference_artifact(root, "reference_ignore_regions", records)
                with self.assertRaisesRegex(ContractError, message):
                    validate_nuclear_reference_set(root)

    def test_held_out_nuclear_geometry_cannot_overlap_or_touch_ignore_geometry(self):
        cases = (
            (
                "fully-covered",
                "POLYGON ((65 65, 85 65, 85 85, 65 85, 65 65))",
            ),
            (
                "boundary-contact",
                "POLYGON ((80 70, 85 70, 85 80, 80 80, 80 70))",
            ),
        )
        for case, ignore_wkt in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = self.copy_fixture(temporary)
                records = read_jsonl(root / "reference-ignore-regions.jsonl")
                ignore = deepcopy(records[0])
                ignore.update(
                    {
                        "image_id": "phase3-image-004",
                        "biological_unit_id": "phase3-unit-004",
                        "annotation_id": "phase3-roi-004",
                        "coordinate_space_id": "phase3-pixels-004",
                    }
                )
                self.set_ignore_geometry_and_reason(
                    ignore,
                    wkt=ignore_wkt,
                    category="ambiguity",
                    code="ambiguous_nuclear_boundary",
                )
                records.append(ignore)
                records.sort(
                    key=lambda record: (
                        record["image_id"],
                        record["annotation_id"],
                        record["ignore_region_id"],
                    )
                )
                reference_path = root / "nuclear-reference-set.json"
                reference = read_json(reference_path)
                reference["region_ledger"]["regions"][3]["counts"][
                    "reference_ignore_regions"
                ] += 1
                reference["region_ledger"]["counts"]["reference_ignore_regions"] += 1
                write_json(reference_path, reference)
                self.write_reference_artifact(root, "reference_ignore_regions", records)
                self.rebind_split_content_commitment_raw(root)
                with self.assertRaisesRegex(
                    ContractError,
                    "nuclear reference geometry intersects a same-image reference ignore geometry",
                ):
                    validate_split_manifest(root)

    def test_duplicate_nuclear_geometry_across_overlapping_include_annotations_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            annotation_path = root / "manifests" / "annotations-001.json"
            annotation_set = read_json(annotation_path)
            overlapping = deepcopy(annotation_set["annotations"][0])
            overlapping["annotation_id"] = "phase3-roi-001-overlap"
            overlapping["label"] = "Synthetic overlapping reference scope 001"
            annotation_set["annotations"].append(overlapping)
            write_json(annotation_path, annotation_set)

            observation_path = root / "observation-set.json"
            observation_set = read_json(observation_path)
            observation_set["observations"][0]["annotation_lineage"][-1][
                "manifest_sha256"
            ] = canonical_sha256(annotation_set)
            write_json(observation_path, observation_set)
            self.bind_reference_to_observation_set(root)

            reference_path = root / "nuclear-reference-set.json"
            reference = read_json(reference_path)
            region = deepcopy(reference["region_ledger"]["regions"][0])
            region["region_id"] = "phase3-region-001-overlap"
            region["annotation_id"] = overlapping["annotation_id"]
            reference["region_ledger"]["regions"].insert(1, region)
            reference["region_ledger"]["counts"]["regions_total"] += 1
            reference["region_ledger"]["counts"]["include"] += 1
            reference["region_ledger"]["counts"]["nuclear_reference_objects"] += 1
            write_json(reference_path, reference)

            records = read_jsonl(root / "nuclear-reference-objects.jsonl")
            duplicate = deepcopy(records[0])
            duplicate["annotation_id"] = overlapping["annotation_id"]
            self.set_nuclear_geometry(
                duplicate,
                duplicate["geometry"]["geometry_type"],
                duplicate["geometry"]["wkt"],
            )
            records.append(duplicate)
            records.sort(
                key=lambda record: (
                    record["image_id"],
                    record["annotation_id"],
                    record["reference_object_id"],
                )
            )
            self.write_reference_artifact(root, "nuclear_reference_objects", records)
            with self.assertRaisesRegex(ContractError, "duplicate nuclear geometry within an image"):
                validate_nuclear_reference_set(root)

    def test_prediction_exposure_is_complete_and_adjudication_controls_readiness(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            records = read_jsonl(root / "nuclear-reference-objects.jsonl")
            del records[0]["prediction_exposure"]["package_sha256"]
            self.write_reference_artifact(root, "nuclear_reference_objects", records)
            with self.assertRaisesRegex(ContractError, "prediction_exposure is missing: package_sha256"):
                validate_nuclear_reference_set(root)

        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            records = read_jsonl(root / "nuclear-reference-objects.jsonl")
            records[0]["review"]["adjudication"]["method"] = "independent_second_review"
            self.write_reference_artifact(root, "nuclear_reference_objects", records)
            with self.assertRaisesRegex(ContractError, "requires at least two reviewers"):
                validate_nuclear_reference_set(root)

        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            records = read_jsonl(root / "nuclear-reference-objects.jsonl")
            records[0]["review"]["adjudication"]["method"] = "independent_second_review"
            records[0]["review"]["reviewer_ids"] = [
                "synthetic-reviewer-001",
                "synthetic-reviewer-002",
            ]
            self.write_reference_artifact(root, "nuclear_reference_objects", records)
            report = validate_nuclear_reference_set(root)
            self.assertEqual(report.model_assisted_object_count, 1)
            self.assertEqual(report.model_assisted_single_review_count, 0)
            self.assertTrue(report.confirmatory_reference_ready)

    def test_adjudicator_must_be_independent_and_can_supply_confirmatory_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            records = read_jsonl(root / "nuclear-reference-objects.jsonl")
            records[0]["review"]["adjudication"] = {
                "method": "adjudicator_decision",
                "adjudicator_id": "synthetic-reviewer-001",
                "notes": "Invalid self-adjudication fixture mutation.",
            }
            self.write_reference_artifact(root, "nuclear_reference_objects", records)
            with self.assertRaisesRegex(ContractError, "must be distinct from all reviewers"):
                validate_nuclear_reference_set(root)

        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            records = read_jsonl(root / "nuclear-reference-objects.jsonl")
            records[0]["review"]["adjudication"] = {
                "method": "adjudicator_decision",
                "adjudicator_id": "synthetic-adjudicator-001",
                "notes": "Independent adjudication fixture mutation.",
            }
            self.write_reference_artifact(root, "nuclear_reference_objects", records)
            report = validate_nuclear_reference_set(root)
            self.assertEqual(report.model_assisted_object_count, 1)
            self.assertEqual(report.model_assisted_single_review_count, 0)
            self.assertTrue(report.confirmatory_reference_ready)

    def test_reference_requires_positive_nuclear_content_per_evaluation_image(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            reference_path = root / "nuclear-reference-set.json"
            reference = read_json(reference_path)
            for region in reference["region_ledger"]["regions"]:
                region["counts"]["nuclear_reference_objects"] = 0
            reference["region_ledger"]["counts"]["nuclear_reference_objects"] = 0
            write_json(reference_path, reference)
            self.write_reference_artifact(root, "nuclear_reference_objects", [])
            with self.assertRaisesRegex(ContractError, "at least one nuclear reference object"):
                validate_nuclear_reference_set(root)

        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            records = read_jsonl(root / "nuclear-reference-objects.jsonl")
            records = [record for record in records if record["image_id"] != "phase3-image-004"]
            reference_path = root / "nuclear-reference-set.json"
            reference = read_json(reference_path)
            reference["region_ledger"]["regions"][3]["counts"][
                "nuclear_reference_objects"
            ] = 0
            reference["region_ledger"]["counts"]["nuclear_reference_objects"] -= 1
            write_json(reference_path, reference)
            self.write_reference_artifact(root, "nuclear_reference_objects", records)
            report = validate_nuclear_reference_set(root)
            self.assertFalse(report.confirmatory_reference_ready)

            self.bind_split_to_reference(root)
            with self.assertRaisesRegex(ContractError, "requires positive nuclear instances"):
                validate_split_manifest(root)

    def test_held_out_partition_rejects_model_assisted_single_review_reference(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            records = read_jsonl(root / "nuclear-reference-objects.jsonl")
            held_out = records[-1]
            held_out["creation_mode"] = "human_corrected_prediction"
            held_out["prediction_exposure"] = {
                "package_id": "synthetic-predictions-heldout",
                "package_sha256": "1" * 64,
                "segmentation_run_id": "synthetic-run-heldout",
                "predicted_object_id": "2" * 64,
                "predicted_geometry_sha256": "3" * 64,
            }
            held_out["review"]["reviewer_ids"] = ["synthetic-reviewer-001"]
            held_out["review"]["adjudication"] = {
                "method": "single_reviewer",
                "adjudicator_id": None,
                "notes": "Synthetic held-out readiness failure.",
            }
            self.write_reference_artifact(root, "nuclear_reference_objects", records)
            self.bind_split_to_reference(root)
            with self.assertRaisesRegex(ContractError, "not held-out-test ready"):
                validate_split_manifest(root)

    def test_region_ledger_must_be_exhaustive_and_counts_must_match_records(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            path = root / "nuclear-reference-set.json"
            reference = read_json(path)
            reference["region_ledger"]["regions"].pop()
            reference["region_ledger"]["counts"]["regions_total"] -= 1
            reference["region_ledger"]["counts"]["include"] -= 1
            reference["region_ledger"]["counts"]["nuclear_reference_objects"] -= 1
            write_json(path, reference)
            with self.assertRaisesRegex(ContractError, "exhaustively cover every governed include ROI"):
                validate_nuclear_reference_set(root)

        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            path = root / "nuclear-reference-set.json"
            reference = read_json(path)
            reference["region_ledger"]["counts"]["nuclear_reference_objects"] += 1
            write_json(path, reference)
            with self.assertRaisesRegex(ContractError, "does not match the region ledger"):
                validate_nuclear_reference_set(root)

        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            path = root / "nuclear-reference-set.json"
            reference = read_json(path)
            reference["region_ledger"]["regions"][0]["counts"]["nuclear_reference_objects"] += 1
            reference["region_ledger"]["counts"]["nuclear_reference_objects"] += 1
            write_json(path, reference)
            with self.assertRaisesRegex(ContractError, "artifact count does not match the region ledger"):
                validate_nuclear_reference_set(root)

    def test_excluded_regions_require_reason_and_cannot_bind_reference_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            path = root / "nuclear-reference-set.json"
            reference = read_json(path)
            region = reference["region_ledger"]["regions"][0]
            region["disposition"] = "exclude"
            region["exclusion_reason"] = None
            write_json(path, reference)
            with self.assertRaisesRegex(ContractError, "exclusion_reason must be one of"):
                validate_nuclear_reference_set(root)

        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            path = root / "nuclear-reference-set.json"
            reference = read_json(path)
            region = reference["region_ledger"]["regions"][0]
            region["disposition"] = "exclude"
            region["exclusion_reason"] = "outside_reference_sampling_scope"
            reference["region_ledger"]["counts"]["include"] -= 1
            reference["region_ledger"]["counts"]["exclude"] += 1
            write_json(path, reference)
            with self.assertRaisesRegex(ContractError, "excluded regions cannot bind reference artifacts"):
                validate_nuclear_reference_set(root)

    def test_source_family_ledger_covers_every_governed_image_once(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            path = root / "nuclear-reference-set.json"
            reference = read_json(path)
            reference["source_family_ledger"]["families"].pop()
            write_json(path, reference)
            with self.assertRaisesRegex(ContractError, "cover every governed image exactly once"):
                validate_nuclear_reference_set(root)

    def test_split_assignments_are_complete_unique_and_ordered(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            path = root / "split-manifest.json"
            split = read_json(path)
            split["image_assignments"].pop()
            write_json(path, split)
            with self.assertRaisesRegex(ContractError, "cover every included reference image"):
                validate_split_manifest(root)

        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            path = root / "split-manifest.json"
            split = read_json(path)
            split["image_assignments"].reverse()
            write_json(path, split)
            with self.assertRaisesRegex(ContractError, "ascending image_id order"):
                validate_split_manifest(root)

        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            path = root / "split-manifest.json"
            split = read_json(path)
            split["image_assignments"].append(deepcopy(split["image_assignments"][0]))
            write_json(path, split)
            with self.assertRaisesRegex(ContractError, "image_id values must be unique"):
                validate_split_manifest(root)

    def test_mouse_hard_group_cannot_cross_partitions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            path = root / "split-manifest.json"
            split = read_json(path)
            split["image_assignments"][1]["partition"] = "tuning"
            write_json(path, split)
            with self.assertRaisesRegex(ContractError, "connected component crosses split partitions"):
                validate_split_manifest(root)

    def test_mouse_and_slide_hard_groups_are_bound_to_governed_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            image_path = root / "manifests" / "image-003.json"
            image = read_json(image_path)
            image["acquisition"]["mouse_id"] = "phase3-mouse-001"
            image["acquisition"]["specimen_id"] = "phase3-specimen-003"
            image["acquisition"]["slide_id"] = "phase3-slide-001"
            image["acquisition"]["batch_id"] = "phase3-batch-tuning"
            image["acquisition"]["scanner_id"] = "phase3-scanner-tuning"
            write_json(image_path, image)

            observation_path = root / "observation-set.json"
            observation_set = read_json(observation_path)
            observation = observation_set["observations"][2]
            observation["biological_unit"]["mouse_id"] = "phase3-mouse-001"
            observation["biological_unit"]["specimen_id"] = "phase3-specimen-003"
            observation["biological_unit"]["slide_id"] = "phase3-slide-001"
            observation["biological_unit"]["batch_id"] = "phase3-batch-tuning"
            observation["biological_unit"]["scanner_id"] = "phase3-scanner-tuning"
            observation["image"]["manifest_sha256"] = canonical_sha256(image)
            write_json(observation_path, observation_set)
            self.bind_reference_to_observation_set(root)

            split_path = root / "split-manifest.json"
            split = read_json(split_path)
            assignment = split["image_assignments"][2]
            assignment["mouse_id"] = "phase3-mouse-001"
            assignment["slide_id"] = "phase3-slide-001"
            assignment["batch_id"] = "phase3-batch-tuning"
            assignment["scanner_id"] = "phase3-scanner-tuning"
            write_json(split_path, split)
            self.bind_split_to_reference(root)
            with self.assertRaisesRegex(ContractError, "connected component crosses split partitions"):
                validate_split_manifest(root)

    def test_source_family_hard_group_cannot_cross_partitions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            reference_path = root / "nuclear-reference-set.json"
            reference = read_json(reference_path)
            images = [f"phase3-image-{index:03d}" for index in range(1, 5)]
            family_by_image = {
                images[0]: "phase3-source-family-001",
                images[1]: "phase3-source-family-002",
                images[2]: "phase3-source-family-001",
                images[3]: "phase3-source-family-004",
            }
            reference["source_family_ledger"]["families"] = [
                {
                    "source_family_id": "phase3-source-family-001",
                    "description": "Synthetic related sources spanning images 001 and 003.",
                    "image_ids": [images[0], images[2]],
                },
                {
                    "source_family_id": "phase3-source-family-002",
                    "description": "Synthetic singleton source family 002.",
                    "image_ids": [images[1]],
                },
                {
                    "source_family_id": "phase3-source-family-004",
                    "description": "Synthetic singleton source family 004.",
                    "image_ids": [images[3]],
                },
            ]
            for region in reference["region_ledger"]["regions"]:
                region["source_family_id"] = family_by_image[region["image_id"]]
            write_json(reference_path, reference)

            split_path = root / "split-manifest.json"
            split = read_json(split_path)
            for assignment in split["image_assignments"]:
                assignment["source_family_id"] = family_by_image[assignment["image_id"]]
            write_json(split_path, split)
            self.bind_split_to_reference(root)
            with self.assertRaisesRegex(ContractError, "connected component crosses split partitions"):
                validate_split_manifest(root)

    def test_excluded_governed_image_still_bridges_hard_groups_transitively(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            reference_path = root / "nuclear-reference-set.json"
            reference = read_json(reference_path)
            reference["source_family_ledger"]["families"] = [
                {
                    "source_family_id": "phase3-source-family-001",
                    "description": "Synthetic train source family.",
                    "image_ids": ["phase3-image-001"],
                },
                {
                    "source_family_id": "phase3-source-family-002",
                    "description": "Synthetic tuning source family.",
                    "image_ids": ["phase3-image-003"],
                },
                {
                    "source_family_id": "phase3-source-family-003",
                    "description": "Excluded bridge and held-out source family.",
                    "image_ids": ["phase3-image-002", "phase3-image-004"],
                },
            ]
            bridge_region = reference["region_ledger"]["regions"][1]
            bridge_region["source_family_id"] = "phase3-source-family-003"
            bridge_region["disposition"] = "exclude"
            bridge_region["exclusion_reason"] = "outside_reference_sampling_scope"
            bridge_region["counts"] = {
                "nuclear_reference_objects": 0,
                "reference_ignore_regions": 0,
            }
            reference["region_ledger"]["counts"]["include"] -= 1
            reference["region_ledger"]["counts"]["exclude"] += 1
            reference["region_ledger"]["counts"]["nuclear_reference_objects"] -= 1
            reference["region_ledger"]["counts"]["reference_ignore_regions"] -= 1
            write_json(reference_path, reference)

            nuclear_records = [
                record
                for record in read_jsonl(root / "nuclear-reference-objects.jsonl")
                if record["image_id"] != "phase3-image-002"
            ]
            ignore_records = [
                record
                for record in read_jsonl(root / "reference-ignore-regions.jsonl")
                if record["image_id"] != "phase3-image-002"
            ]
            self.write_reference_artifact(
                root,
                "nuclear_reference_objects",
                nuclear_records,
            )
            self.write_reference_artifact(
                root,
                "reference_ignore_regions",
                ignore_records,
            )

            split_path = root / "split-manifest.json"
            split = read_json(split_path)
            split["image_assignments"] = [
                assignment
                for assignment in split["image_assignments"]
                if assignment["image_id"] != "phase3-image-002"
            ]
            write_json(split_path, split)
            self.bind_split_to_reference(root)
            with self.assertRaisesRegex(ContractError, "connected component crosses split partitions"):
                validate_split_manifest(root)

    def test_zero_byte_policy_and_provenance_artifacts_fail_after_honest_rebinding(self):
        for policy_field in ("evaluation_policy", "selection_protocol"):
            with self.subTest(policy=policy_field), tempfile.TemporaryDirectory() as temporary:
                root = self.copy_fixture(temporary)
                reference_path = root / "nuclear-reference-set.json"
                reference = read_json(reference_path)
                artifact = reference[policy_field]["artifact"]
                artifact_path = root / artifact["relative_path"]
                artifact_path.write_bytes(b"")
                artifact["sha256"] = hashlib.sha256(b"").hexdigest()
                artifact["size_bytes"] = 0
                write_json(reference_path, reference)
                with self.assertRaisesRegex(ContractError, "size_bytes must be at least 1"):
                    validate_nuclear_reference_set(root)

        for manifest_name, validator in (
            ("nuclear-reference-set.json", validate_nuclear_reference_set),
            ("split-manifest.json", validate_split_manifest),
        ):
            with self.subTest(provenance=manifest_name), tempfile.TemporaryDirectory() as temporary:
                root = self.copy_fixture(temporary)
                path = root / manifest_name
                document = read_json(path)
                empty_path = root / f"empty-{manifest_name}.bin"
                empty_path.write_bytes(b"")
                empty_hash = hashlib.sha256(b"").hexdigest()
                document["provenance"]["code_sha256"] = empty_hash
                document["provenance"]["code_artifact"] = {
                    "relative_path": empty_path.name,
                    "media_type": "application/octet-stream",
                    "sha256": empty_hash,
                    "size_bytes": 0,
                }
                write_json(path, document)
                with self.assertRaisesRegex(ContractError, "size_bytes must be at least 1"):
                    validator(root)

    def test_batch_and_scanner_domain_controls_are_enforced(self):
        for field, wrong_value in (
            ("batch_id", "phase3-batch-shared"),
            ("scanner_id", "phase3-scanner-shared"),
        ):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                root = self.copy_fixture(temporary)
                path = root / "split-manifest.json"
                split = read_json(path)
                split["design"]["domain_controls"][field]["leave_out_values"] = [wrong_value]
                write_json(path, split)
                with self.assertRaisesRegex(ContractError, "leave_out_values must exactly equal"):
                    validate_split_manifest(root)

        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            path = root / "split-manifest.json"
            split = read_json(path)
            split["design"]["domain_controls"]["batch_id"] = {
                "mode": "partition_disjoint",
                "leave_out_values": [],
            }
            write_json(path, split)
            with self.assertRaisesRegex(ContractError, "batch_id value crosses train and tuning"):
                validate_split_manifest(root)

    def test_held_out_commitment_matches_exact_assignments_and_hash(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            path = root / "split-manifest.json"
            split = read_json(path)
            split["held_out_test_commitment"]["image_ids"] = ["phase3-image-003"]
            write_json(path, split)
            with self.assertRaisesRegex(ContractError, "exactly match held-out-test assignments"):
                validate_split_manifest(root)

        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            path = root / "split-manifest.json"
            split = read_json(path)
            split["held_out_test_commitment"]["image_ids_sha256"] = "0" * 64
            write_json(path, split)
            with self.assertRaisesRegex(ContractError, "does not match canonical image_ids"):
                validate_split_manifest(root)

        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            path = root / "split-manifest.json"
            split = read_json(path)
            del split["held_out_test_commitment"]["reference_content_profile"]
            write_json(path, split)
            with self.assertRaisesRegex(ContractError, "is missing: reference_content_profile"):
                validate_split_manifest(root)

        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            path = root / "split-manifest.json"
            split = read_json(path)
            split["held_out_test_commitment"]["reference_content_profile"] = "unsupported"
            write_json(path, split)
            with self.assertRaisesRegex(ContractError, "reference_content_profile is unsupported"):
                validate_split_manifest(root)

        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            path = root / "split-manifest.json"
            split = read_json(path)
            split["held_out_test_commitment"]["reference_content_sha256"] = "0" * 64
            write_json(path, split)
            with self.assertRaisesRegex(ContractError, "does not match exact held-out reference content"):
                validate_split_manifest(root)

    def test_reference_and_split_chronology_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            path = root / "nuclear-reference-set.json"
            reference = read_json(path)
            reference["provenance"]["created_at"] = "2026-08-31T00:00:00Z"
            write_json(path, reference)
            with self.assertRaisesRegex(ContractError, "provenance.created_at must not follow"):
                validate_nuclear_reference_set(root)

        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            path = root / "nuclear-reference-set.json"
            reference = read_json(path)
            reference["region_ledger"]["regions"][0]["review"]["reviewed_at"] = (
                "2026-08-31T00:00:00Z"
            )
            write_json(path, reference)
            with self.assertRaisesRegex(ContractError, "review.reviewed_at must not follow"):
                validate_nuclear_reference_set(root)

        for field, filename, message in (
            (
                "nuclear_reference_objects",
                "nuclear-reference-objects.jsonl",
                "nuclear_reference_objects.*review.reviewed_at must not follow",
            ),
            (
                "reference_ignore_regions",
                "reference-ignore-regions.jsonl",
                "reference_ignore_regions.*review.reviewed_at must not follow",
            ),
        ):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                root = self.copy_fixture(temporary)
                records = read_jsonl(root / filename)
                records[0]["review"]["reviewed_at"] = "2026-08-31T00:00:00Z"
                self.write_reference_artifact(root, field, records)
                with self.assertRaisesRegex(ContractError, message):
                    validate_nuclear_reference_set(root)

        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            reference_path = root / "nuclear-reference-set.json"
            reference = read_json(reference_path)
            reference["state"]["frozen_at"] = "2026-08-31T00:00:00Z"
            write_json(reference_path, reference)
            self.bind_split_to_reference(root)
            with self.assertRaisesRegex(ContractError, "reference_set.state.frozen_at must not follow"):
                validate_split_manifest(root)

        for field, message in (
            ("commitment", "committed_at must not follow state.frozen_at"),
            ("provenance", "provenance.created_at must not follow state.frozen_at"),
        ):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                root = self.copy_fixture(temporary)
                path = root / "split-manifest.json"
                split = read_json(path)
                if field == "commitment":
                    split["held_out_test_commitment"]["committed_at"] = (
                        "2026-08-31T00:00:00Z"
                    )
                else:
                    split["provenance"]["created_at"] = "2026-08-31T00:00:00Z"
                write_json(path, split)
                with self.assertRaisesRegex(ContractError, message):
                    validate_split_manifest(root)

    def test_governed_upstream_reviews_and_provenance_cannot_postdate_reference_freeze(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            observation_path = root / "observation-set.json"
            observation_set = read_json(observation_path)
            observation_set["observations"][0]["identity_review"]["reviewed_at"] = (
                "2026-08-31T00:00:00Z"
            )
            write_json(observation_path, observation_set)
            self.bind_reference_to_observation_set(root)
            with self.assertRaisesRegex(ContractError, "must not follow reference state.frozen_at"):
                validate_nuclear_reference_set(root)

    def test_observation_parent_chain_is_validated_for_chronology_and_nonempty_code(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            _child_path, _child = self.make_observation_successor(root)
            report = validate_nuclear_reference_set(root)
            self.assertEqual(report.governed_observation_set_revision, 1)

        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            child_path, child = self.make_observation_successor(root)
            parent_path = root / "observation-set.json"
            parent = read_json(parent_path)
            parent["provenance"]["created_at"] = "2026-08-31T00:00:00Z"
            child["provenance"]["created_at"] = "2026-09-01T00:00:00Z"
            write_json(parent_path, parent)
            child["parent"]["manifest_sha256"] = canonical_sha256(parent)
            self.bind_reference_to_observation_successor(root, child_path, child)
            with self.assertRaisesRegex(ContractError, "must not follow reference state.frozen_at"):
                validate_nuclear_reference_set(root)

        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            child_path, child = self.make_observation_successor(root)
            parent_path = root / "observation-set.json"
            parent = read_json(parent_path)
            parent["provenance"]["created_at"] = "2026-08-30T01:00:00Z"
            child["provenance"]["created_at"] = "2026-08-30T00:30:00Z"
            write_json(parent_path, parent)
            child["parent"]["manifest_sha256"] = canonical_sha256(parent)
            self.bind_reference_to_observation_successor(root, child_path, child)
            reference_path = root / "nuclear-reference-set.json"
            reference = read_json(reference_path)
            reference["state"]["frozen_at"] = "2026-08-31T00:00:00Z"
            write_json(reference_path, reference)
            with self.assertRaisesRegex(
                ContractError,
                r"parent\.manifest\.provenance\.created_at must not follow its direct child",
            ):
                validate_nuclear_reference_set(root)

        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            child_path, child = self.make_observation_successor(root)
            parent_path = root / "observation-set.json"
            parent = read_json(parent_path)
            parent["observations"][0]["identity_review"]["reviewed_at"] = (
                "2026-08-31T00:00:00Z"
            )
            write_json(parent_path, parent)
            child["parent"]["manifest_sha256"] = canonical_sha256(parent)
            self.bind_reference_to_observation_successor(root, child_path, child)
            with self.assertRaisesRegex(ContractError, "must not follow reference state.frozen_at"):
                validate_nuclear_reference_set(root)

        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            child_path, child = self.make_observation_successor(root)
            parent_path = root / "observation-set.json"
            parent = read_json(parent_path)
            original_annotation_path = root / "manifests" / "annotations-001.json"
            original_annotation = read_json(original_annotation_path)
            child_annotation_path = root / "manifests" / "annotations-001-child.json"
            write_json(child_annotation_path, original_annotation)
            child["observations"][0]["annotation_lineage"][0].update(
                {
                    "manifest_relative_path": "manifests/annotations-001-child.json",
                    "manifest_sha256": canonical_sha256(original_annotation),
                }
            )

            original_annotation["annotations"][0]["review"]["reviewed_at"] = (
                "2026-08-31T00:00:00Z"
            )
            write_json(original_annotation_path, original_annotation)
            parent["observations"][0]["annotation_lineage"][0]["manifest_sha256"] = (
                canonical_sha256(original_annotation)
            )
            write_json(parent_path, parent)
            child["parent"]["manifest_sha256"] = canonical_sha256(parent)
            self.bind_reference_to_observation_successor(root, child_path, child)
            with self.assertRaisesRegex(ContractError, "must not follow reference state.frozen_at"):
                validate_nuclear_reference_set(root)

        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            child_path, child = self.make_observation_successor(root)
            parent_path = root / "observation-set.json"
            parent = read_json(parent_path)
            empty_path = root / "empty-parent-observation-code.bin"
            empty_path.write_bytes(b"")
            empty_hash = hashlib.sha256(b"").hexdigest()
            parent["provenance"]["code_sha256"] = empty_hash
            parent["provenance"]["code_artifact"] = {
                "relative_path": empty_path.name,
                "media_type": "application/octet-stream",
                "sha256": empty_hash,
                "size_bytes": 0,
            }
            write_json(parent_path, parent)
            child["parent"]["manifest_sha256"] = canonical_sha256(parent)
            self.bind_reference_to_observation_successor(root, child_path, child)
            with self.assertRaisesRegex(ContractError, "size_bytes must be at least 1"):
                validate_nuclear_reference_set(root)

        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            observation_path = root / "observation-set.json"
            observation_set = read_json(observation_path)
            observation_set["provenance"]["created_at"] = "2026-08-31T00:00:00Z"
            write_json(observation_path, observation_set)
            self.bind_reference_to_observation_set(root)
            with self.assertRaisesRegex(ContractError, "must not follow reference state.frozen_at"):
                validate_nuclear_reference_set(root)

        for timestamp_field in ("provenance", "acquisition"):
            with self.subTest(image_timestamp=timestamp_field), tempfile.TemporaryDirectory() as temporary:
                root = self.copy_fixture(temporary)
                image_path = root / "manifests" / "image-001.json"
                image = read_json(image_path)
                if timestamp_field == "provenance":
                    image["provenance"]["created_at"] = "2026-08-31T00:00:00Z"
                else:
                    image["acquisition"]["acquired_at"] = "2026-08-31T00:00:00Z"
                write_json(image_path, image)
                observation_path = root / "observation-set.json"
                observation_set = read_json(observation_path)
                observation_set["observations"][0]["image"]["manifest_sha256"] = (
                    canonical_sha256(image)
                )
                write_json(observation_path, observation_set)
                self.bind_reference_to_observation_set(root)
                with self.assertRaisesRegex(ContractError, "must not follow reference state.frozen_at"):
                    validate_nuclear_reference_set(root)

        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            channel_path = root / "manifests" / "channels-001.json"
            channel = read_json(channel_path)
            channel["provenance"]["created_at"] = "2026-08-31T00:00:00Z"
            write_json(channel_path, channel)
            observation_path = root / "observation-set.json"
            observation_set = read_json(observation_path)
            observation_set["observations"][0]["channel_map"]["manifest_sha256"] = (
                canonical_sha256(channel)
            )
            write_json(observation_path, observation_set)
            self.bind_reference_to_observation_set(root)
            with self.assertRaisesRegex(ContractError, "must not follow reference state.frozen_at"):
                validate_nuclear_reference_set(root)

        for timestamp_field in ("review", "provenance"):
            with self.subTest(annotation_timestamp=timestamp_field), tempfile.TemporaryDirectory() as temporary:
                root = self.copy_fixture(temporary)
                annotation_path = root / "manifests" / "annotations-001.json"
                annotation = read_json(annotation_path)
                if timestamp_field == "review":
                    annotation["annotations"][0]["review"]["reviewed_at"] = (
                        "2026-08-31T00:00:00Z"
                    )
                else:
                    annotation["provenance"]["created_at"] = "2026-08-31T00:00:00Z"
                write_json(annotation_path, annotation)
                observation_path = root / "observation-set.json"
                observation_set = read_json(observation_path)
                observation_set["observations"][0]["annotation_lineage"][-1][
                    "manifest_sha256"
                ] = canonical_sha256(annotation)
                write_json(observation_path, observation_set)
                self.bind_reference_to_observation_set(root)
                with self.assertRaisesRegex(ContractError, "must not follow reference state.frozen_at"):
                    validate_nuclear_reference_set(root)

        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            old_path = root / "manifests" / "annotations-001.json"
            old_annotation = read_json(old_path)
            new_annotation = deepcopy(old_annotation)
            new_annotation["annotation_set_id"] = "phase3-annotations-001-r1"
            new_annotation["revision"] = 1
            new_annotation["provenance"]["parent_annotation_set_id"] = (
                old_annotation["annotation_set_id"]
            )
            new_path = root / "manifests" / "annotations-001-r1.json"
            write_json(new_path, new_annotation)
            old_annotation["annotations"][0]["review"]["reviewed_at"] = (
                "2026-08-31T00:00:00Z"
            )
            write_json(old_path, old_annotation)

            observation_path = root / "observation-set.json"
            observation_set = read_json(observation_path)
            observation = observation_set["observations"][0]
            old_lineage = observation["annotation_lineage"][0]
            old_lineage["manifest_sha256"] = canonical_sha256(old_annotation)
            observation["annotation_lineage"].append(
                {
                    "annotation_set_id": new_annotation["annotation_set_id"],
                    "revision": 1,
                    "manifest_relative_path": "manifests/annotations-001-r1.json",
                    "manifest_sha256": canonical_sha256(new_annotation),
                    "parent_manifest_sha256": old_lineage["manifest_sha256"],
                    "revision_reason": "Exercise older-lineage chronology.",
                }
            )
            observation["selected_annotation_set_id"] = new_annotation["annotation_set_id"]
            write_json(observation_path, observation_set)
            self.bind_reference_to_observation_set(root)
            with self.assertRaisesRegex(ContractError, "must not follow reference state.frozen_at"):
                validate_nuclear_reference_set(root)

    def test_reference_successor_requires_immediate_recursive_lineage(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            self.make_reference_successor(root)
            report = validate_nuclear_reference_set(root)
            self.assertEqual(report.revision, 1)

            manifest_path = root / "nuclear-reference-set.json"
            successor = read_json(manifest_path)
            successor["parent"]["revision"] = 9
            write_json(manifest_path, successor)
            with self.assertRaisesRegex(ContractError, "parent.revision does not match"):
                validate_nuclear_reference_set(root)

    def test_split_successor_preserves_commitment_and_every_prior_assignment(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            self.make_split_successor(root)
            report = validate_split_manifest(root)
            self.assertEqual(report.revision, 1)

        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            self.make_split_successor(root)
            path = root / "split-manifest.json"
            split = read_json(path)
            split["held_out_test_commitment"]["committed_by"] = "synthetic-reviewer-002"
            write_json(path, split)
            with self.assertRaisesRegex(ContractError, "retain the exact held-out-test commitment"):
                validate_split_manifest(root)

        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            self.make_split_successor(root)
            path = root / "split-manifest.json"
            split = read_json(path)
            split["image_assignments"][0]["partition"] = "tuning"
            split["image_assignments"][1]["partition"] = "tuning"
            split["image_assignments"][2]["partition"] = "train"
            write_json(path, split)
            with self.assertRaisesRegex(ContractError, "cannot change a prior image assignment"):
                validate_split_manifest(root)

    def test_split_successor_locks_held_out_reference_content_but_allows_train_additions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            self.make_linked_reference_and_split_successors(root)
            reference = read_json(root / "nuclear-reference-set.json")
            nuclear_path = root / reference["artifacts"]["nuclear_reference_objects"][
                "relative_path"
            ]
            records = read_jsonl(nuclear_path)
            added = deepcopy(records[1])
            added["review"]["adjudication"]["notes"] = "Synthetic train-only addition."
            self.set_nuclear_geometry(
                added,
                "POLYGON",
                "POLYGON ((22 22, 28 22, 28 28, 22 28, 22 22))",
            )
            records.append(added)
            records.sort(
                key=lambda record: (
                    record["image_id"],
                    record["annotation_id"],
                    record["reference_object_id"],
                )
            )
            reference["region_ledger"]["regions"][1]["counts"][
                "nuclear_reference_objects"
            ] += 1
            reference["region_ledger"]["counts"]["nuclear_reference_objects"] += 1
            write_json(root / "nuclear-reference-set.json", reference)
            self.write_reference_artifact(root, "nuclear_reference_objects", records)
            self.bind_split_to_reference(root)
            report = validate_split_manifest(root)
            self.assertEqual(report.revision, 1)
            self.assertEqual(
                report.held_out_test_reference_content_sha256,
                EXPECTED_HELD_OUT_REFERENCE_CONTENT_SHA256,
            )

        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            self.make_linked_reference_and_split_successors(root)
            reference = read_json(root / "nuclear-reference-set.json")
            nuclear_path = root / reference["artifacts"]["nuclear_reference_objects"][
                "relative_path"
            ]
            records = read_jsonl(nuclear_path)
            self.set_nuclear_geometry(
                records[-1],
                "POLYGON",
                "POLYGON ((71 71, 81 71, 81 81, 71 81, 71 71))",
            )
            self.write_reference_artifact(root, "nuclear_reference_objects", records)
            self.bind_split_to_reference(root)
            with self.assertRaisesRegex(ContractError, "exact held-out reference content"):
                validate_split_manifest(root)

        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            self.make_linked_reference_and_split_successors(root)
            path = root / "nuclear-reference-set.json"
            reference = read_json(path)
            reference["evaluation_policy"]["evaluation_policy_id"] = (
                "phase3-synthetic-evaluation-002"
            )
            write_json(path, reference)
            self.bind_split_to_reference(root)
            with self.assertRaisesRegex(ContractError, "exact held-out reference content"):
                validate_split_manifest(root)

    def test_split_successor_locks_held_out_source_and_annotation_lineage(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            self.make_linked_reference_and_split_successors(root)
            observation_path, observation_set = self.make_observation_successor(root)
            source_payload = b"synthetic changed held-out source bytes\n"
            source_path = root / "source-004-r1.bin"
            source_path.write_bytes(source_payload)
            image = read_json(root / "manifests" / "image-004.json")
            image["source_artifact"].update(
                {
                    "source_uri": source_path.name,
                    "sha256": hashlib.sha256(source_payload).hexdigest(),
                    "size_bytes": len(source_payload),
                }
            )
            image_path = root / "manifests" / "image-004-r1.json"
            write_json(image_path, image)
            observation_set["observations"][3]["image"].update(
                {
                    "manifest_relative_path": "manifests/image-004-r1.json",
                    "manifest_sha256": canonical_sha256(image),
                    "source_sha256": image["source_artifact"]["sha256"],
                }
            )
            self.bind_reference_to_observation_successor(
                root,
                observation_path,
                observation_set,
            )
            self.bind_split_to_reference(root)
            with self.assertRaisesRegex(ContractError, "exact held-out reference content"):
                validate_split_manifest(root)

    def test_later_dated_successor_can_preserve_lock_during_train_only_evolution(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            self.make_linked_reference_and_split_successors(root)
            reference_path = root / "nuclear-reference-set.json"
            reference = read_json(reference_path)
            reference["provenance"]["created_at"] = "2026-09-01T00:00:00Z"
            reference["state"]["frozen_at"] = "2026-09-01T01:00:00Z"
            nuclear_path = root / reference["artifacts"]["nuclear_reference_objects"][
                "relative_path"
            ]
            records = read_jsonl(nuclear_path)
            added = deepcopy(records[1])
            self.set_nuclear_geometry(
                added,
                "POLYGON",
                "POLYGON ((22 22, 28 22, 28 28, 22 28, 22 22))",
            )
            records.append(added)
            records.sort(
                key=lambda record: (
                    record["image_id"],
                    record["annotation_id"],
                    record["reference_object_id"],
                )
            )
            reference["region_ledger"]["regions"][1]["counts"][
                "nuclear_reference_objects"
            ] += 1
            reference["region_ledger"]["counts"]["nuclear_reference_objects"] += 1
            write_json(reference_path, reference)
            self.write_reference_artifact(root, "nuclear_reference_objects", records)

            split_path = root / "split-manifest.json"
            split = read_json(split_path)
            split["provenance"]["created_at"] = "2026-09-02T00:00:00Z"
            split["state"]["frozen_at"] = "2026-09-02T01:00:00Z"
            write_json(split_path, split)
            self.bind_split_to_reference(root)
            report = validate_split_manifest(root)
            self.assertEqual(report.revision, 1)
            self.assertEqual(
                report.held_out_test_reference_content_sha256,
                EXPECTED_HELD_OUT_REFERENCE_CONTENT_SHA256,
            )

    def test_parent_reference_and_split_cannot_be_frozen_after_successor_creation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            self.make_linked_reference_and_split_successors(root)
            parent_path = root / "parent-nuclear-reference-set.json"
            parent = read_json(parent_path)
            parent["state"]["frozen_at"] = "2026-09-03T00:00:00Z"
            write_json(parent_path, parent)
            child_path = root / "nuclear-reference-set.json"
            child = read_json(child_path)
            child["parent"]["manifest_sha256"] = canonical_sha256(parent)
            write_json(child_path, child)
            self.bind_split_to_reference(root)
            with self.assertRaisesRegex(
                ContractError,
                "parent reference state.frozen_at must not follow successor provenance.created_at",
            ):
                validate_nuclear_reference_set(root)

        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            self.make_linked_reference_and_split_successors(root)
            parent_path = root / "parent-split-manifest.json"
            parent = read_json(parent_path)
            parent["state"]["frozen_at"] = "2026-09-03T00:00:00Z"
            write_json(parent_path, parent)
            child_path = root / "split-manifest.json"
            child = read_json(child_path)
            child["parent"]["manifest_sha256"] = canonical_sha256(parent)
            write_json(child_path, child)
            with self.assertRaisesRegex(
                ContractError,
                "parent split state.frozen_at must not follow successor provenance.created_at",
            ):
                validate_split_manifest(root)

        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            self.make_linked_reference_and_split_successors(root)
            observation_path, observation_set = self.make_observation_successor(root)
            observation = observation_set["observations"][3]
            prior_lineage = observation["annotation_lineage"][-1]
            annotation = read_json(root / "manifests" / "annotations-004.json")
            annotation["annotation_set_id"] = "phase3-annotations-004-r1"
            annotation["revision"] = 1
            annotation["annotations"][0]["label"] = "Revised held-out scope label"
            annotation["provenance"]["parent_annotation_set_id"] = (
                prior_lineage["annotation_set_id"]
            )
            annotation_path = root / "manifests" / "annotations-004-r1.json"
            write_json(annotation_path, annotation)
            observation["annotation_lineage"].append(
                {
                    "annotation_set_id": annotation["annotation_set_id"],
                    "revision": 1,
                    "manifest_relative_path": "manifests/annotations-004-r1.json",
                    "manifest_sha256": canonical_sha256(annotation),
                    "parent_manifest_sha256": prior_lineage["manifest_sha256"],
                    "revision_reason": "Exercise held-out annotation-content lock.",
                }
            )
            observation["selected_annotation_set_id"] = annotation["annotation_set_id"]
            self.bind_reference_to_observation_successor(
                root,
                observation_path,
                observation_set,
            )
            self.bind_split_to_reference(root)
            with self.assertRaisesRegex(ContractError, "exact held-out reference content"):
                validate_split_manifest(root)

    def test_reference_and_split_nonclaims_are_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            path = root / "nuclear-reference-set.json"
            reference = read_json(path)
            reference["claims"]["scientific_validation"] = True
            write_json(path, reference)
            with self.assertRaisesRegex(ContractError, "scientific_validation must be false"):
                validate_nuclear_reference_set(root)

        for field in (
            "scientific_validation",
            "biological_ground_truth",
            "backend_equivalence",
            "model_universality",
            "split_optimality",
            "population_representativeness",
            "domain_generalizability",
        ):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                root = self.copy_fixture(temporary)
                path = root / "split-manifest.json"
                split = read_json(path)
                split["claims"][field] = True
                write_json(path, split)
                with self.assertRaisesRegex(ContractError, f"{field} must be false"):
                    validate_split_manifest(root)

    def test_cli_is_read_only_and_hash_expectations_are_machine_readable(self):
        reference_hash = EXPECTED_REFERENCE_SET_SHA256
        split_hash = EXPECTED_SPLIT_MANIFEST_SHA256
        bootstrap = (
            "import sys; sys.path.insert(0, 'src'); "
            "from ifquant_platform.cli import main; raise SystemExit(main(sys.argv[1:]))"
        )
        before = {
            path.relative_to(FIXTURE): path.read_bytes()
            for path in FIXTURE.rglob("*")
            if path.is_file()
        }
        reference_result = subprocess.run(
            [
                sys.executable,
                "-c",
                bootstrap,
                "validate-nuclear-reference-set",
                str(FIXTURE),
                "--expect-reference-set-sha256",
                reference_hash,
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(reference_result.returncode, 0, reference_result.stderr)
        self.assertEqual(json.loads(reference_result.stdout)["reference_set_sha256"], reference_hash)

        split_result = subprocess.run(
            [
                sys.executable,
                "-c",
                bootstrap,
                "validate-split-manifest",
                str(FIXTURE),
                "--expect-split-manifest-sha256",
                split_hash,
                "--expect-reference-set-sha256",
                reference_hash,
                "--expect-held-out-test-reference-content-sha256",
                EXPECTED_HELD_OUT_REFERENCE_CONTENT_SHA256,
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(split_result.returncode, 0, split_result.stderr)
        self.assertEqual(json.loads(split_result.stdout)["split_manifest_sha256"], split_hash)
        after = {
            path.relative_to(FIXTURE): path.read_bytes()
            for path in FIXTURE.rglob("*")
            if path.is_file()
        }
        self.assertEqual(after, before)

        failure = subprocess.run(
            [
                sys.executable,
                "-c",
                bootstrap,
                "validate-split-manifest",
                str(FIXTURE),
                "--expect-split-manifest-sha256",
                "0" * 64,
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(failure.returncode, 2)
        self.assertIn("IFQUANT_PLATFORM_VALIDATION_ERROR", failure.stderr)
        self.assertNotIn("Traceback", failure.stderr)

    def test_phase3_validator_import_has_no_optional_imaging_dependencies(self):
        bootstrap = (
            "import sys; sys.path.insert(0, 'src'); "
            "import ifquant_platform.phase3_validation; "
            "assert 'numpy' not in sys.modules; assert 'PIL' not in sys.modules"
        )
        result = subprocess.run(
            [sys.executable, "-c", bootstrap],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(
        importlib.util.find_spec("jsonschema") is not None,
        "jsonschema is not installed; runtime validators remain authoritative",
    )
    def test_phase3_schemas_are_valid_and_accept_the_canonical_fixture(self):
        from jsonschema import FormatChecker
        from jsonschema.validators import validator_for

        cases = (
            (
                ROOT / "contracts" / "nuclear-reference-object.schema.json",
                read_jsonl(FIXTURE / "nuclear-reference-objects.jsonl"),
            ),
            (
                ROOT / "contracts" / "reference-ignore-region.schema.json",
                read_jsonl(FIXTURE / "reference-ignore-regions.jsonl"),
            ),
            (
                ROOT / "contracts" / "nuclear-reference-set.schema.json",
                [read_json(FIXTURE / "nuclear-reference-set.json")],
            ),
            (
                ROOT / "contracts" / "split-manifest.schema.json",
                [read_json(FIXTURE / "split-manifest.json")],
            ),
        )
        for schema_path, instances in cases:
            with self.subTest(schema=schema_path.name):
                schema = read_json(schema_path)
                validator_type = validator_for(schema)
                validator_type.check_schema(schema)
                validator = validator_type(
                    schema,
                    format_checker=FormatChecker(),
                )
                for instance in instances:
                    validator.validate(instance)


if __name__ == "__main__":
    unittest.main()
