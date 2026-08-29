import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ifquant_platform.canonical import ContractError, canonical_json_bytes  # noqa: E402
from ifquant_platform.package_validation import validate_cell_package  # noqa: E402


FIXTURE = ROOT / "validation" / "fixtures" / "minimal-cell-package"
EXPECTED_PACKAGE_SHA256 = "11257c1560e7a948407751b5fdfd0fbf463b2ee9893e235bedfcebcf8c95d392"
EXPECTED_METHOD_SHA256 = "6c47eda4968b78ec47df0253205dfb9bae40ad5677964def25a0ed1ac0938d3d"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


class PackageValidationTests(unittest.TestCase):
    def copy_fixture(self, temporary: str) -> Path:
        destination = Path(temporary) / "package"
        shutil.copytree(FIXTURE, destination)
        return destination

    def test_minimal_package_passes_with_nonclaim_report(self):
        report = validate_cell_package(FIXTURE)
        self.assertEqual(report.status, "valid")
        self.assertEqual(report.package_canonical_sha256, EXPECTED_PACKAGE_SHA256)
        self.assertEqual(report.method_instance_sha256, EXPECTED_METHOD_SHA256)
        self.assertEqual(report.object_count, 1)
        self.assertEqual(report.authorization, "none")
        self.assertFalse(report.scientific_validation)
        self.assertFalse(report.backend_equivalence)
        self.assertFalse(report.model_universality)
        self.assertIn("unattested", " ".join(report.warnings))

    def test_artifact_tampering_is_detected_before_object_use(self):
        with tempfile.TemporaryDirectory() as temporary:
            package_root = self.copy_fixture(temporary)
            object_path = package_root / "cell_objects.jsonl"
            object_path.write_bytes(object_path.read_bytes().replace(b'"value":120', b'"value":121'))
            with self.assertRaisesRegex(ContractError, "artifact SHA-256 mismatch"):
                validate_cell_package(package_root)

    def test_source_artifact_bytes_are_attested(self):
        with tempfile.TemporaryDirectory() as temporary:
            package_root = self.copy_fixture(temporary)
            (package_root / "source-pixels.bin").write_bytes(b"tampered pixels")
            with self.assertRaisesRegex(
                ContractError, "source artifact (size|SHA-256) mismatch"
            ):
                validate_cell_package(package_root)

    def test_source_artifact_cannot_escape_package_by_relative_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            package_root = self.copy_fixture(temporary)
            image_path = package_root / "manifests" / "image-manifest.json"
            image = read_json(image_path)
            image["source_artifact"]["source_uri"] = "../outside.bin"
            write_json(image_path, image)
            package = read_json(package_root / "package.json")
            from ifquant_platform.canonical import canonical_sha256

            package["image"]["manifest_sha256"] = canonical_sha256(image)
            write_json(package_root / "package.json", package)
            with self.assertRaisesRegex(ContractError, "must stay inside"):
                validate_cell_package(package_root)

    def test_geometry_tampering_cannot_keep_the_old_object_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            package_root = self.copy_fixture(temporary)
            object_path = package_root / "cell_objects.jsonl"
            record = json.loads(object_path.read_text(encoding="utf-8"))
            record["geometry"]["cell"]["wkt"] = (
                "POLYGON ((40 40, 61 40, 61 60, 40 60, 40 40))"
            )
            payload = canonical_json_bytes(record) + b"\n"
            object_path.write_bytes(payload)
            package = read_json(package_root / "package.json")
            package["cell_objects_artifact"]["sha256"] = hashlib.sha256(payload).hexdigest()
            package["cell_objects_artifact"]["size_bytes"] = len(payload)
            write_json(package_root / "package.json", package)
            with self.assertRaisesRegex(ContractError, "object_id does not match"):
                validate_cell_package(package_root)

    def test_malformed_wkt_is_rejected_even_when_hashes_are_recomputed(self):
        with tempfile.TemporaryDirectory() as temporary:
            package_root = self.copy_fixture(temporary)
            object_path = package_root / "cell_objects.jsonl"
            record = json.loads(object_path.read_text(encoding="utf-8"))
            record["geometry"]["cell"]["wkt"] = "POLYGON (garbage)"
            from ifquant_platform.package_validation import expected_object_id

            record["object_id"] = expected_object_id(record)
            payload = canonical_json_bytes(record) + b"\n"
            object_path.write_bytes(payload)
            package = read_json(package_root / "package.json")
            package["cell_objects_artifact"]["sha256"] = hashlib.sha256(payload).hexdigest()
            package["cell_objects_artifact"]["size_bytes"] = len(payload)
            write_json(package_root / "package.json", package)
            with self.assertRaisesRegex(ContractError, "not valid 2D WKT1"):
                validate_cell_package(package_root)

    def test_manifest_hash_and_method_instance_drift_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            package_root = self.copy_fixture(temporary)
            package = read_json(package_root / "package.json")
            package["channel_map"]["manifest_sha256"] = "0" * 64
            write_json(package_root / "package.json", package)
            with self.assertRaisesRegex(ContractError, "channel-map hash mismatch"):
                validate_cell_package(package_root)

        with tempfile.TemporaryDirectory() as temporary:
            package_root = self.copy_fixture(temporary)
            package = read_json(package_root / "package.json")
            package["measurement_method"]["method_instance_sha256"] = "0" * 64
            write_json(package_root / "package.json", package)
            with self.assertRaisesRegex(ContractError, "method-instance hash mismatch"):
                validate_cell_package(package_root)

    def test_object_measurements_must_match_the_bound_definition(self):
        with tempfile.TemporaryDirectory() as temporary:
            package_root = self.copy_fixture(temporary)
            object_path = package_root / "cell_objects.jsonl"
            record = json.loads(object_path.read_text(encoding="utf-8"))
            record["intensity_measurements"][0]["measurement_id"] = "undeclared_cell_mean"
            payload = canonical_json_bytes(record) + b"\n"
            object_path.write_bytes(payload)
            package = read_json(package_root / "package.json")
            package["cell_objects_artifact"]["sha256"] = hashlib.sha256(payload).hexdigest()
            package["cell_objects_artifact"]["size_bytes"] = len(payload)
            write_json(package_root / "package.json", package)
            with self.assertRaisesRegex(ContractError, "not declared as an intensity feature"):
                validate_cell_package(package_root)

    def test_measurement_semantics_match_channel_intensity_contract(self):
        with tempfile.TemporaryDirectory() as temporary:
            package_root = self.copy_fixture(temporary)
            channel_path = package_root / "manifests" / "channel-map.json"
            channel_map = read_json(channel_path)
            channel_map["channels"][0]["intensity"].update(
                {
                    "representation": "floating_point",
                    "bit_depth": 32,
                    "transform": "linear",
                    "unit": "normalized_intensity",
                }
            )
            write_json(channel_path, channel_map)
            package = read_json(package_root / "package.json")
            from ifquant_platform.canonical import canonical_sha256

            package["channel_map"]["manifest_sha256"] = canonical_sha256(channel_map)
            write_json(package_root / "package.json", package)
            with self.assertRaisesRegex(ContractError, "intensity coordinate disagrees"):
                validate_cell_package(package_root)

    def test_linear_channel_transform_requires_nonzero_scale(self):
        with tempfile.TemporaryDirectory() as temporary:
            package_root = self.copy_fixture(temporary)
            channel_path = package_root / "manifests" / "channel-map.json"
            channel_map = read_json(channel_path)
            channel_map["channels"][0]["intensity"].update(
                {
                    "representation": "floating_point",
                    "bit_depth": 32,
                    "transform": "linear",
                    "scale": 0,
                    "unit": "normalized_intensity",
                }
            )
            write_json(channel_path, channel_map)
            package = read_json(package_root / "package.json")
            from ifquant_platform.canonical import canonical_sha256

            package["channel_map"]["manifest_sha256"] = canonical_sha256(channel_map)
            write_json(package_root / "package.json", package)
            with self.assertRaisesRegex(ContractError, "nonzero scale"):
                validate_cell_package(package_root)

    def test_canonical_v1_rejects_multiplane_images(self):
        with tempfile.TemporaryDirectory() as temporary:
            package_root = self.copy_fixture(temporary)
            image_path = package_root / "manifests" / "image-manifest.json"
            image = read_json(image_path)
            image["dimensions"]["z_planes"] = 2
            write_json(image_path, image)
            package = read_json(package_root / "package.json")
            from ifquant_platform.canonical import canonical_sha256

            package["image"]["manifest_sha256"] = canonical_sha256(image)
            write_json(package_root / "package.json", package)
            with self.assertRaisesRegex(ContractError, "singleton Z/T"):
                validate_cell_package(package_root)

    def test_package_qc_and_review_ledgers_must_reconcile_to_objects(self):
        with tempfile.TemporaryDirectory() as temporary:
            package_root = self.copy_fixture(temporary)
            package = read_json(package_root / "package.json")
            package["qc"]["pass_count"] = 1
            package["qc"]["not_evaluated_count"] = 0
            package["qc"]["status"] = "pass"
            write_json(package_root / "package.json", package)
            with self.assertRaisesRegex(ContractError, "status counts do not match"):
                validate_cell_package(package_root)

        with tempfile.TemporaryDirectory() as temporary:
            package_root = self.copy_fixture(temporary)
            package = read_json(package_root / "package.json")
            package["review"]["reviewed_object_count"] = 1
            write_json(package_root / "package.json", package)
            with self.assertRaisesRegex(ContractError, "does not match cell-object review"):
                validate_cell_package(package_root)

    def test_zero_cell_package_is_valid_and_explicitly_not_evaluated(self):
        with tempfile.TemporaryDirectory() as temporary:
            package_root = self.copy_fixture(temporary)
            object_path = package_root / "cell_objects.jsonl"
            object_path.write_bytes(b"")
            package = read_json(package_root / "package.json")
            package["cell_objects_artifact"].update(
                {
                    "sha256": hashlib.sha256(b"").hexdigest(),
                    "size_bytes": 0,
                    "record_count": 0,
                }
            )
            package["qc"].update(
                {
                    "status": "not_evaluated",
                    "object_count": 0,
                    "pass_count": 0,
                    "warning_count": 0,
                    "fail_count": 0,
                    "not_evaluated_count": 0,
                }
            )
            write_json(package_root / "package.json", package)
            report = validate_cell_package(package_root)
            self.assertEqual(report.object_count, 0)
            self.assertIn("not_evaluated", " ".join(report.warnings))

    def test_relative_paths_cannot_escape_package(self):
        with tempfile.TemporaryDirectory() as temporary:
            package_root = self.copy_fixture(temporary)
            package = read_json(package_root / "package.json")
            package["image"]["manifest_relative_path"] = "../image-manifest.json"
            write_json(package_root / "package.json", package)
            with self.assertRaisesRegex(ContractError, "must stay inside"):
                validate_cell_package(package_root)

    def test_native_and_learned_backend_weight_rules_are_distinct(self):
        with tempfile.TemporaryDirectory() as temporary:
            package_root = self.copy_fixture(temporary)
            run_path = package_root / "manifests" / "segmentation-run.json"
            run = read_json(run_path)
            run["model"]["weights_sha256"] = "f" * 64
            write_json(run_path, run)
            package = read_json(package_root / "package.json")
            from ifquant_platform.canonical import canonical_sha256

            package["segmentation_run"]["manifest_sha256"] = canonical_sha256(run)
            package["segmentation_run"]["weights_sha256"] = "f" * 64
            write_json(package_root / "package.json", package)
            with self.assertRaisesRegex(ContractError, "null weights_sha256"):
                validate_cell_package(package_root)

    def test_cli_success_and_hash_failure_are_machine_readable_without_traceback(self):
        bootstrap = (
            "import sys; sys.path.insert(0, 'src'); "
            "from ifquant_platform.cli import main; raise SystemExit(main(sys.argv[1:]))"
        )
        success = subprocess.run(
            [sys.executable, "-c", bootstrap, "validate", str(FIXTURE)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(success.returncode, 0, success.stderr)
        self.assertEqual(json.loads(success.stdout)["package_canonical_sha256"], EXPECTED_PACKAGE_SHA256)

        failure = subprocess.run(
            [
                sys.executable,
                "-c",
                bootstrap,
                "validate",
                str(FIXTURE),
                "--expect-package-sha256",
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

    def test_cli_malformed_object_is_a_contract_error_without_traceback(self):
        with tempfile.TemporaryDirectory() as temporary:
            package_root = self.copy_fixture(temporary)
            object_path = package_root / "cell_objects.jsonl"
            payload = canonical_json_bytes({"unexpected": "object"}) + b"\n"
            object_path.write_bytes(payload)
            package = read_json(package_root / "package.json")
            package["cell_objects_artifact"].update(
                {
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "size_bytes": len(payload),
                }
            )
            write_json(package_root / "package.json", package)
            bootstrap = (
                "import sys; sys.path.insert(0, 'src'); "
                "from ifquant_platform.cli import main; raise SystemExit(main(sys.argv[1:]))"
            )
            result = subprocess.run(
                [sys.executable, "-c", bootstrap, "validate", str(package_root)],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("IFQUANT_PLATFORM_VALIDATION_ERROR", result.stderr)
            self.assertNotIn("Traceback", result.stderr)

    def test_all_schema_objects_are_closed_and_parseable(self):
        schemas = sorted((ROOT / "contracts").rglob("*.schema.json"))
        self.assertEqual(len(schemas), 8)

        def walk(value):
            if isinstance(value, dict):
                if value.get("type") == "object":
                    self.assertIs(value.get("additionalProperties"), False)
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)

        for path in schemas:
            with self.subTest(path=path):
                walk(read_json(path))


if __name__ == "__main__":
    unittest.main()
