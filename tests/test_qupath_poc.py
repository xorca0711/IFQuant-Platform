import hashlib
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ifquant_platform.canonical import load_strict_json  # noqa: E402
from ifquant_platform.method_contracts import (  # noqa: E402
    load_measurement_definition,
    load_parameter_set,
    resolve_method,
)


SCRIPT = ROOT / "qupath" / "scripts" / "DetectCellsAndExport.groovy"
CONFIG = ROOT / "qupath" / "config" / "pilot.example.json"
QUPATH_README = ROOT / "qupath" / "README.md"


class QuPathProofOfConceptTests(unittest.TestCase):
    def setUp(self):
        self.script_bytes = SCRIPT.read_bytes()
        self.script = self.script_bytes.decode("utf-8")
        self.config = load_strict_json(CONFIG)

    def test_script_hash_is_pinned_to_exact_lf_bytes(self):
        observed = hashlib.sha256(self.script_bytes).hexdigest()
        self.assertNotIn(b"\r", self.script_bytes)
        self.assertEqual(self.config["execution"]["expected_script_sha256"], observed)
        self.assertEqual(QUPATH_README.read_text(encoding="utf-8").count(observed), 1)

    def test_example_is_generic_but_binds_final_method_contracts(self):
        self.assertEqual(
            self.config["schema_version"], "ifquant.qupath-pilot-config/1.0.0"
        )
        serialized = CONFIG.read_text(encoding="utf-8")
        for workstation_fragment in ("X:\\GitHub", "D:\\Microscopy", "C:\\Users"):
            self.assertNotIn(workstation_fragment, serialized)
        self.assertFalse(Path(self.config["output_directory"]).is_absolute())
        self.assertFalse(Path(self.config["execution"]["script_path"]).is_absolute())
        self.assertNotIn("execution", self.config["segmentation"])
        self.assertEqual(
            self.config["segmentation"]["boundary_policy"],
            "exclude_touching_annotation_boundary",
        )
        self.assertEqual(self.config["segmentation"]["backend"]["kind"], "native_qupath")

        method = self.config["measurement_method"]
        definition_path = (CONFIG.parent / method["definition_source_path"]).resolve()
        parameter_path = (CONFIG.parent / method["parameter_set_source_path"]).resolve()
        definition = load_measurement_definition(definition_path)
        parameters = load_parameter_set(parameter_path)
        resolved = resolve_method(definition.document, parameters.document)
        self.assertEqual(method["expected_definition_sha256"], definition.canonical_sha256)
        self.assertEqual(method["expected_parameter_set_sha256"], parameters.canonical_sha256)
        self.assertEqual(
            method["expected_method_instance_sha256"], resolved.method_instance_sha256
        )

        for channel in self.config["channel_map"]["channels"]:
            self.assertEqual(
                channel["intensity"],
                {
                    "representation": "unsigned_integer",
                    "bit_depth": 16,
                    "transform": "none",
                    "scale": 1,
                    "offset": 0,
                    "unit": "native_sample_value",
                },
            )

    def test_script_contains_the_fail_closed_v1_execution_boundary(self):
        required_fragments = (
            "ScriptAttributes.FILE_PATH",
            "QP.getProject()",
            "QP.getProjectEntry()",
            "QP.runPlugin(",
            "imageData.isFluorescence()",
            "server.getPixelType()",
            "server.nZSlices()",
            "server.nTimepoints()",
            "exclude_touching_annotation_boundary",
            "CANDIDATE_BACKEND_NOT_IMPLEMENTED",
            "ifquant_platform_cell_object_package",
            "ifquant_platform_cell_object",
            "pluginStartedAt.toString()",
            "pluginCompletedAt.toString()",
            "sourceDetectionId",
            "cell.getID()",
            "disableUnicodeEscaping()",
            "toPlainString()",
            "552826a2f58ca54e04be7b10fe1c3a349aba62618f370e6d80f384bf60d38111",
            "452d85ac99d2fe777a0511646a392e96f37b79b1a0b73f03914b7b4f75cf7e24",
        )
        for fragment in required_fragments:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, self.script)
        for forbidden_path in ("X:\\", "D:\\", "C:\\"):
            self.assertNotIn(forbidden_path, self.script)
        self.assertNotIn("produced no cells", self.script.lower())
        readme = QUPATH_README.read_text(encoding="utf-8")
        self.assertIn("Project-only execution", readme)
        self.assertNotIn("Standalone image, Windows PowerShell", readme)


if __name__ == "__main__":
    unittest.main()
