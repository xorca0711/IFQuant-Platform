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

from ifquant_platform.canonical import ContractError, canonical_sha256  # noqa: E402
from ifquant_platform.dataset_governance import (  # noqa: E402
    validate_governed_observation_set,
)


FIXTURE = ROOT / "validation" / "fixtures" / "minimal-governed-observation-set"
EXPECTED_OBSERVATION_SET_SHA256 = (
    "7ab3b32754aa5fecb1d29318074122a8a81b63f55458ef9f209d24d83777e35b"
)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


class DatasetGovernanceTests(unittest.TestCase):
    def copy_fixture(self, temporary: str) -> Path:
        destination = Path(temporary) / "observation-set"
        shutil.copytree(FIXTURE, destination)
        return destination

    def test_minimal_governed_observation_set_passes_with_nonclaim_report(self):
        report = validate_governed_observation_set(FIXTURE)
        self.assertEqual(report.status, "valid")
        self.assertEqual(report.observation_set_sha256, EXPECTED_OBSERVATION_SET_SHA256)
        self.assertEqual(report.observation_count, 1)
        self.assertEqual(report.annotation_revision_count, 1)
        self.assertEqual(report.mouse_count, 1)
        self.assertTrue(report.observation_set_contract_valid)
        self.assertEqual(report.authorization, "none")
        self.assertFalse(report.scientific_validation)
        self.assertFalse(report.biological_ground_truth)

    def test_required_identity_cannot_be_null_or_disagree_with_source_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            manifest_path = root / "observation-set.json"
            document = read_json(manifest_path)
            document["observations"][0]["biological_unit"]["mouse_id"] = None
            write_json(manifest_path, document)
            with self.assertRaisesRegex(ContractError, "mouse_id is not a valid identifier"):
                validate_governed_observation_set(root)

        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            manifest_path = root / "observation-set.json"
            document = read_json(manifest_path)
            document["observations"][0]["biological_unit"]["mouse_id"] = "synthetic-mouse-002"
            write_json(manifest_path, document)
            with self.assertRaisesRegex(ContractError, "mouse_id does not match image_manifest"):
                validate_governed_observation_set(root)

    def test_source_bytes_are_attested(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            (root / "source-pixels.bin").write_bytes(b"tampered")
            with self.assertRaisesRegex(ContractError, "source (size|bytes)"):
                validate_governed_observation_set(root)

    def test_producer_code_bytes_are_attested(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            (root / "producer-code.txt").write_text("tampered producer code\n", encoding="utf-8")
            with self.assertRaisesRegex(ContractError, "code_artifact.(size_bytes|sha256)"):
                validate_governed_observation_set(root)

    def test_successor_recursively_validates_its_immediate_parent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            manifest_path = root / "observation-set.json"
            parent_path = root / "parent-observation-set.json"
            parent = read_json(manifest_path)
            write_json(parent_path, parent)

            successor = deepcopy(parent)
            successor["revision"] = 1
            successor["revision_reason"] = "Exercise immediate-parent lineage validation."
            successor["parent"] = {
                "observation_set_id": parent["observation_set_id"],
                "manifest_relative_path": parent_path.name,
                "manifest_sha256": canonical_sha256(parent),
            }
            write_json(manifest_path, successor)
            report = validate_governed_observation_set(root)
            self.assertEqual(report.revision, 1)

            parent["unexpected"] = True
            write_json(parent_path, parent)
            successor["parent"]["manifest_sha256"] = canonical_sha256(parent)
            write_json(manifest_path, successor)
            with self.assertRaisesRegex(ContractError, "unknown fields: unexpected"):
                validate_governed_observation_set(root)

    def test_ids_are_unique_across_observations(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            manifest_path = root / "observation-set.json"
            document = read_json(manifest_path)
            document["observations"].append(deepcopy(document["observations"][0]))
            write_json(manifest_path, document)
            with self.assertRaisesRegex(ContractError, "channel_map_id values must be unique"):
                validate_governed_observation_set(root)

        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            manifest_path = root / "observation-set.json"
            document = read_json(manifest_path)
            second = deepcopy(document["observations"][0])
            channel = read_json(root / "manifests" / "channel-map.json")
            channel["channel_map_id"] = "governed-channel-map-002"
            second_channel_path = root / "manifests" / "channel-map-002.json"
            write_json(second_channel_path, channel)
            second["channel_map"] = {
                "channel_map_id": channel["channel_map_id"],
                "manifest_relative_path": "manifests/channel-map-002.json",
                "manifest_sha256": canonical_sha256(channel),
            }
            document["observations"].append(second)
            write_json(manifest_path, document)
            with self.assertRaisesRegex(ContractError, "annotation_set_id values must be unique"):
                validate_governed_observation_set(root)

    def test_stable_biological_identity_cannot_acquire_a_second_unit_id(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            manifest_path = root / "observation-set.json"
            document = read_json(manifest_path)
            second = deepcopy(document["observations"][0])
            image = read_json(root / "manifests" / "image-manifest.json")
            image["image_id"] = "governed-image-002"
            image["biological_unit_id"] = "governed-unit-002"
            second_image_path = root / "manifests" / "image-manifest-002.json"
            write_json(second_image_path, image)
            second["image"] = {
                "image_id": image["image_id"],
                "manifest_relative_path": "manifests/image-manifest-002.json",
                "manifest_sha256": canonical_sha256(image),
                "source_sha256": image["source_artifact"]["sha256"],
            }
            second["biological_unit"]["biological_unit_id"] = "governed-unit-002"
            document["observations"].append(second)
            write_json(manifest_path, document)
            with self.assertRaisesRegex(ContractError, "stable identity is assigned to multiple"):
                validate_governed_observation_set(root)

    def test_study_scoped_hierarchy_ids_cannot_change_parent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            manifest_path = root / "observation-set.json"
            document = read_json(manifest_path)
            second = deepcopy(document["observations"][0])
            image = read_json(root / "manifests" / "image-manifest.json")
            image["image_id"] = "governed-image-002"
            image["biological_unit_id"] = "governed-unit-002"
            image["acquisition"]["mouse_id"] = "synthetic-mouse-002"
            second_image_path = root / "manifests" / "image-manifest-002.json"
            write_json(second_image_path, image)
            second["image"] = {
                "image_id": image["image_id"],
                "manifest_relative_path": "manifests/image-manifest-002.json",
                "manifest_sha256": canonical_sha256(image),
                "source_sha256": image["source_artifact"]["sha256"],
            }
            second["biological_unit"]["biological_unit_id"] = "governed-unit-002"
            second["biological_unit"]["mouse_id"] = "synthetic-mouse-002"
            document["observations"].append(second)
            write_json(manifest_path, document)
            with self.assertRaisesRegex(ContractError, "slide_id is assigned to multiple mouse_id"):
                validate_governed_observation_set(root)

    def test_selected_annotation_revision_must_be_reviewed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            annotation_path = root / "manifests" / "annotation-set.json"
            annotation = read_json(annotation_path)
            annotation["annotations"][0]["review"] = {
                "state": "unreviewed",
                "reviewer_id": None,
                "reviewed_at": None,
            }
            write_json(annotation_path, annotation)

            document_path = root / "observation-set.json"
            document = read_json(document_path)
            document["observations"][0]["annotation_lineage"][0]["manifest_sha256"] = (
                canonical_sha256(annotation)
            )
            write_json(document_path, document)
            with self.assertRaisesRegex(
                ContractError,
                "review.state must be accepted or corrected",
            ):
                validate_governed_observation_set(root)

    def test_annotation_lineage_root_cannot_claim_a_parent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            document_path = root / "observation-set.json"
            document = read_json(document_path)
            document["observations"][0]["annotation_lineage"][0]["parent_manifest_sha256"] = (
                "a" * 64
            )
            write_json(document_path, document)
            with self.assertRaisesRegex(ContractError, "parent_manifest_sha256 must be null"):
                validate_governed_observation_set(root)

    def test_contract_is_closed_and_paths_cannot_escape(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            document_path = root / "observation-set.json"
            document = read_json(document_path)
            document["unexpected"] = True
            write_json(document_path, document)
            with self.assertRaisesRegex(ContractError, "unknown fields: unexpected"):
                validate_governed_observation_set(root)

        with tempfile.TemporaryDirectory() as temporary:
            root = self.copy_fixture(temporary)
            document_path = root / "observation-set.json"
            document = read_json(document_path)
            document["observations"][0]["image"]["manifest_relative_path"] = (
                "../image-manifest.json"
            )
            write_json(document_path, document)
            with self.assertRaisesRegex(ContractError, "must stay inside"):
                validate_governed_observation_set(root)

    def test_cli_is_read_only_and_hash_check_is_machine_readable(self):
        bootstrap = (
            "import sys; sys.path.insert(0, 'src'); "
            "from ifquant_platform.cli import main; raise SystemExit(main(sys.argv[1:]))"
        )
        before = {
            path.relative_to(FIXTURE): path.read_bytes()
            for path in FIXTURE.rglob("*")
            if path.is_file()
        }
        success = subprocess.run(
            [sys.executable, "-c", bootstrap, "validate-observation-set", str(FIXTURE)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(success.returncode, 0, success.stderr)
        self.assertEqual(
            json.loads(success.stdout)["observation_set_sha256"],
            EXPECTED_OBSERVATION_SET_SHA256,
        )
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
                "validate-observation-set",
                str(FIXTURE),
                "--expect-observation-set-sha256",
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

    def test_governance_import_has_no_optional_imaging_dependencies(self):
        bootstrap = (
            "import sys; sys.path.insert(0, 'src'); "
            "import ifquant_platform.dataset_governance; "
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


if __name__ == "__main__":
    unittest.main()
