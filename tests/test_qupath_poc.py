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
STARDIST_CONFIG = ROOT / "qupath" / "config" / "stardist.example.json"
STARDIST_DESCRIPTOR = (
    ROOT / "qupath" / "models" / "stardist" / "dsb2018-heavy-augment.descriptor.json"
)
STARDIST_PREPROCESSING = (
    ROOT / "qupath" / "models" / "stardist" / "dapi-local-percentile.preprocessing.json"
)
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
            "exclude_touching_annotation_or_image_boundary",
        )
        self.assertEqual(self.config["execution"]["script_version"], "1.3.0")
        self.assertEqual(self.config["provenance"]["exporter_version"], "1.3.0")
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
            "exclude_touching_annotation_or_image_boundary",
            "exactly one full-image annotation",
            "complete image extent",
            "one_processing_pixel",
            "effectiveProcessingMicrons",
            "Math.max(",
            "usesImageBoundaryGuard",
            "SEGMENTATION_CONTRACT_VERSION",
            "cell_within_image_boundary_guard",
            'sides.add("top")',
            'sides.add("right")',
            'sides.add("bottom")',
            'sides.add("left")',
            "CANDIDATE_BACKEND_NOT_IMPLEMENTED",
            "STARDIST_EXTENSION_NOT_AVAILABLE",
            "runStarDist(",
            "StarDist normalization percentiles",
            "loaded StarDist extension artifact does not equal configured",
            "ifquant_platform_cell_object_package",
            "ifquant_platform_cell_object",
            "pluginStartedAt.toString()",
            "pluginCompletedAt.toString()",
            "sourceDetectionId",
            "cell.getID()",
            "appendJsonString(",
            "countObjectQcFlags(",
            "objects_nucleus_not_covered_by_cell_geometry",
            "object_qc_flag_counts",
            "toPlainString()",
            "552826a2f58ca54e04be7b10fe1c3a349aba62618f370e6d80f384bf60d38111",
            "452d85ac99d2fe777a0511646a392e96f37b79b1a0b73f03914b7b4f75cf7e24",
        )
        for fragment in required_fragments:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, self.script)
        for forbidden_path in ("X:\\", "D:\\", "C:\\"):
            self.assertNotIn(forbidden_path, self.script)
        self.assertNotIn("groovy.json", self.script)
        self.assertNotIn("produced no cells", self.script.lower())
        readme = QUPATH_README.read_text(encoding="utf-8")
        self.assertIn("Project-only execution", readme)
        self.assertNotIn("Standalone image, Windows PowerShell", readme)

    def test_stardist_example_binds_distinct_runtime_and_model_identities(self):
        config = load_strict_json(STARDIST_CONFIG)
        segmentation = config["segmentation"]
        self.assertEqual(segmentation["backend"]["kind"], "stardist")
        self.assertEqual(segmentation["backend"]["version"], "0.6.0")
        self.assertEqual(
            segmentation["backend"]["artifact_sha256"],
            "8c8be80fc9169802a5ef58f7d73f8c0474f7dbbfd13709d24e18d3cc445ff73b",
        )
        self.assertEqual(
            segmentation["model"]["weights_sha256"],
            "fc1f1148f22180bf2874346d14926e7baf8486088cb66277e13cb22ddccfe01b",
        )
        self.assertEqual(segmentation["plugin_class"], "qupath.ext.stardist.StarDist2D")
        self.assertEqual(segmentation["runtime_inputs"]["qupath_version"], "0.7.0")
        self.assertTrue(segmentation["parameters"]["constrainToParent"])
        self.assertTrue(segmentation["parameters"]["measureIntensity"])
        self.assertTrue(segmentation["parameters"]["includeProbability"])
        self.assertNotEqual(
            segmentation["backend"]["artifact_sha256"],
            segmentation["model"]["weights_sha256"],
        )
        self.assertEqual(
            segmentation["model"]["descriptor_sha256"],
            hashlib.sha256(STARDIST_DESCRIPTOR.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            segmentation["preprocessing"]["profile_sha256"],
            hashlib.sha256(STARDIST_PREPROCESSING.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            config["execution"]["expected_script_sha256"],
            hashlib.sha256(self.script_bytes).hexdigest(),
        )

    def test_script_publishes_complete_candidate_disposition_qc_sidecars(self):
        required_fragments = (
            '"qc/candidate-dispositions.jsonl"',
            '"qc/candidate-dispositions-manifest.json"',
            "buildCandidateDispositionLedger(",
            "buildCandidateDispositionManifest(",
            '"candidate disposition ledger does not account for every new detection"',
            "candidate_index_ascending",
            "accepted_object_id: acceptedObjectId",
            "source_detection_id: sourceDetectionId",
            "touches_annotation_boundary:",
            "nucleus_not_covered_by_cell_geometry_warning:",
            "nucleus_area_outside_cell_px2: nucleusAreaOutsideCell",
            "nucleus_area_outside_cell_fraction:",
            "fixedPrecisionDifferenceArea(",
            "OverlayNG.DIFFERENCE",
            "source_artifact_sha256: sourceArtifactSha256",
            "annotation_content_sha256: annotationContentSha256",
            "scientific_validation: false",
            "backend_equivalence: false",
            "model_universality: false",
            'authorization: "none"',
        )
        for fragment in required_fragments:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, self.script)

        readme = QUPATH_README.read_text(encoding="utf-8")
        self.assertIn("Every newly detected `PathCellObject`", readme)
        self.assertIn("do not change or extend the canonical package schema", readme)
        self.assertIn("relative to `output_directory`", readme)


if __name__ == "__main__":
    unittest.main()
