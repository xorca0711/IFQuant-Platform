import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ifquant_platform.backends import candidate_backends, get_backend  # noqa: E402
from ifquant_platform.canonical import ContractError  # noqa: E402


class BackendRegistryTests(unittest.TestCase):
    def test_all_initial_candidates_are_registered_without_equivalence_metadata(self):
        descriptors = candidate_backends()
        self.assertEqual(
            {descriptor.backend_id for descriptor in descriptors},
            {"native_qupath", "stardist", "instanseg"},
        )
        for descriptor in descriptors:
            self.assertEqual(descriptor.status, "candidate")
            self.assertFalse(hasattr(descriptor, "equivalent_to"))

    def test_model_backends_require_explicit_model_identity(self):
        for backend_id in ("stardist", "instanseg"):
            with self.subTest(backend_id=backend_id):
                with self.assertRaisesRegex(ContractError, "model descriptor"):
                    get_backend(backend_id).validate_run_identity({"backend_id": backend_id})
                with self.assertRaisesRegex(ContractError, "model-weights identity"):
                    get_backend(backend_id).validate_run_identity(
                        {"backend_id": backend_id, "model": {"weights_sha256": None}}
                    )
                get_backend(backend_id).validate_run_identity(
                    {"backend_id": backend_id, "model": {"weights_sha256": "0" * 64}}
                )

    def test_native_backend_uses_detector_identity_not_fabricated_model(self):
        native = get_backend("native_qupath")
        native.validate_run_identity(
            {"backend_id": "native_qupath", "model": {"weights_sha256": None}}
        )
        with self.assertRaisesRegex(ContractError, "null weights_sha256"):
            native.validate_run_identity(
                {"backend_id": "native_qupath", "model": {"weights_sha256": "0" * 64}}
            )

    def test_unknown_backend_fails_closed(self):
        with self.assertRaisesRegex(ContractError, "unknown segmentation backend"):
            get_backend("universal_cnn")


if __name__ == "__main__":
    unittest.main()
