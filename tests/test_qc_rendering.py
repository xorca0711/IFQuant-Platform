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

from ifquant_platform.canonical import (  # noqa: E402
    ContractError,
    canonical_json_bytes,
    canonical_sha256,
    file_sha256,
)
from ifquant_platform.qc_rendering import (  # noqa: E402
    _annotation_content_sha256,
    expected_candidate_id,
    image_boundary_sides,
    parse_wkt,
    render_qc,
    validate_candidate_dispositions,
)


FIXTURE = ROOT / "validation" / "fixtures" / "minimal-cell-package"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_canonical(path: Path, value) -> None:
    path.write_bytes(canonical_json_bytes(value) + b"\n")


class QcRenderingTests(unittest.TestCase):
    def copy_fixture(self, temporary: str) -> Path:
        destination = Path(temporary) / "package"
        shutil.copytree(FIXTURE, destination)
        return destination

    def add_candidate_ledger(self, package_root: Path) -> tuple[Path, Path]:
        package = read_json(package_root / "package.json")
        image = read_json(package_root / package["image"]["manifest_relative_path"])
        annotations = read_json(package_root / package["annotation_set"]["manifest_relative_path"])
        run = read_json(package_root / package["segmentation_run"]["manifest_relative_path"])
        cell_object = json.loads((package_root / "cell_objects.jsonl").read_text(encoding="utf-8"))
        record = {
            "schema_version": "ifquant.qc-candidate-disposition/1.0.0",
            "candidate_id": "pending",
            "candidate_index": 0,
            "package_id": package["package_id"],
            "image_id": image["image_id"],
            "annotation_set_id": annotations["annotation_set_id"],
            "segmentation_run_id": run["segmentation_run_id"],
            "coordinate_space_id": image["coordinate_space"]["coordinate_space_id"],
            "annotation_id": cell_object["annotation_id"],
            "accepted_object_id": cell_object["object_id"],
            "source_detection_id": cell_object["provenance"]["source_detection_id"],
            "disposition": "accepted",
            "reason": "accepted",
            "geometry": cell_object["geometry"],
            "centroids": cell_object["centroids"],
            "touches_annotation_boundary": False,
            "nucleus_not_covered_by_cell_geometry_warning": False,
            "nucleus_area_outside_cell_px2": 0,
            "nucleus_area_outside_cell_fraction": 0,
        }
        record["candidate_id"] = expected_candidate_id(record)
        qc_directory = package_root / "qc"
        qc_directory.mkdir()
        artifact_path = qc_directory / "candidate-dispositions.jsonl"
        artifact_payload = canonical_json_bytes(record) + b"\n"
        artifact_path.write_bytes(artifact_payload)
        manifest = {
            "schema_version": "ifquant.qc-candidate-dispositions-manifest/1.0.0",
            "pilot_status": "unvalidated_engineering_pilot",
            "package_id": package["package_id"],
            "image_id": image["image_id"],
            "annotation_set_id": annotations["annotation_set_id"],
            "segmentation_run_id": run["segmentation_run_id"],
            "coordinate_space_id": image["coordinate_space"]["coordinate_space_id"],
            "artifact": {
                "relative_path": "qc/candidate-dispositions.jsonl",
                "media_type": "application/x-ndjson",
                "sha256": hashlib.sha256(artifact_payload).hexdigest(),
                "size_bytes": len(artifact_payload),
                "record_count": 1,
                "ordering": "candidate_index_ascending",
            },
            "disposition_counts": {"accepted": 1, "excluded": 0},
            "reason_counts": {"accepted": 1},
            "geometry_warning_counts": {"nucleus_not_covered_by_cell_geometry": 0},
            "bindings": {
                "script_sha256": run["execution"]["script_sha256"],
                "run_config_sha256": run["execution"]["run_config_sha256"],
                "source_artifact_sha256": image["source_artifact"]["sha256"],
                "annotation_content_sha256": _annotation_content_sha256(annotations),
            },
            "claims": {
                "scientific_validation": False,
                "backend_equivalence": False,
                "model_universality": False,
                "authorization": "none",
            },
        }
        manifest_path = qc_directory / "candidate-dispositions-manifest.json"
        write_canonical(manifest_path, manifest)
        return artifact_path, manifest_path

    def rewrite_artifact_binding(self, manifest_path: Path, artifact_path: Path) -> None:
        manifest = read_json(manifest_path)
        payload = artifact_path.read_bytes()
        manifest["artifact"]["sha256"] = hashlib.sha256(payload).hexdigest()
        manifest["artifact"]["size_bytes"] = len(payload)
        manifest["artifact"]["record_count"] = len(payload.rstrip(b"\n").split(b"\n")) if payload else 0
        write_canonical(manifest_path, manifest)

    def bind_full_frame_policy(self, package_root: Path) -> None:
        image = read_json(package_root / "manifests" / "image-manifest.json")
        width = image["dimensions"]["width_pixels"]
        height = image["dimensions"]["height_pixels"]
        annotation_path = package_root / "manifests" / "annotation-set.json"
        annotations = read_json(annotation_path)
        annotations["annotations"][0]["geometry"] = {
            "encoding": "WKT1",
            "geometry_type": "POLYGON",
            "wkt": (
                f"POLYGON ((0 0, 0 {height}, {width} {height}, "
                f"{width} 0, 0 0))"
            ),
        }
        write_canonical(annotation_path, annotations)

        run_path = package_root / "manifests" / "segmentation-run.json"
        run = read_json(run_path)
        run["boundary_policy"] = "exclude_touching_annotation_or_image_boundary"
        write_canonical(run_path, run)

        package_path = package_root / "package.json"
        package = read_json(package_path)
        package["annotation_set"]["manifest_sha256"] = canonical_sha256(annotations)
        package["segmentation_run"]["manifest_sha256"] = canonical_sha256(run)
        write_canonical(package_path, package)

    def append_left_edge_candidate(
        self, package_root: Path, artifact_path: Path, manifest_path: Path
    ) -> None:
        package = read_json(package_root / "package.json")
        image = read_json(package_root / package["image"]["manifest_relative_path"])
        annotations = read_json(
            package_root / package["annotation_set"]["manifest_relative_path"]
        )
        run = read_json(
            package_root / package["segmentation_run"]["manifest_relative_path"]
        )
        annotation_id = annotations["annotations"][0]["annotation_id"]
        record = {
            "schema_version": "ifquant.qc-candidate-disposition/1.0.0",
            "candidate_id": "pending",
            "candidate_index": 1,
            "package_id": package["package_id"],
            "image_id": image["image_id"],
            "annotation_set_id": annotations["annotation_set_id"],
            "segmentation_run_id": run["segmentation_run_id"],
            "coordinate_space_id": image["coordinate_space"]["coordinate_space_id"],
            "annotation_id": annotation_id,
            "accepted_object_id": None,
            "source_detection_id": "detection-edge-left",
            "disposition": "excluded",
            "reason": "cell_touches_image_boundary",
            "geometry": {
                "cell": {
                    "encoding": "WKT1",
                    "geometry_type": "POLYGON",
                    "wkt": "POLYGON ((0 40, 5 40, 5 45, 0 45, 0 40))",
                },
                "nucleus": None,
            },
            "centroids": {
                "cell_x": 2.5,
                "cell_y": 42.5,
                "nucleus_x": None,
                "nucleus_y": None,
                "unit": "pixel",
            },
            "touches_annotation_boundary": True,
            "nucleus_not_covered_by_cell_geometry_warning": False,
            "nucleus_area_outside_cell_px2": None,
            "nucleus_area_outside_cell_fraction": None,
        }
        record["candidate_id"] = expected_candidate_id(record)
        payload = artifact_path.read_bytes() + canonical_json_bytes(record) + b"\n"
        artifact_path.write_bytes(payload)
        manifest = read_json(manifest_path)
        manifest["disposition_counts"] = {"accepted": 1, "excluded": 1}
        manifest["reason_counts"] = {
            "accepted": 1,
            "cell_touches_image_boundary": 1,
        }
        write_canonical(manifest_path, manifest)
        self.rewrite_artifact_binding(manifest_path, artifact_path)

    def test_polygon_and_multipolygon_are_parsed_without_shapely(self):
        polygon = parse_wkt(
            {
                "encoding": "WKT1",
                "geometry_type": "POLYGON",
                "wkt": "POLYGON ((0 0, 4 0, 4 4, 0 0), (1 1, 2 1, 1 2, 1 1))",
            }
        )
        self.assertEqual(len(polygon.polygons), 1)
        self.assertEqual(len(polygon.polygons[0]), 2)
        multipolygon = parse_wkt(
            {
                "encoding": "WKT1",
                "geometry_type": "MULTIPOLYGON",
                "wkt": "MULTIPOLYGON (((0 0, 2 0, 0 2, 0 0)), ((3 3, 5 3, 3 5, 3 3)))",
            }
        )
        self.assertEqual(len(multipolygon.polygons), 2)

    def test_physical_image_edges_are_classified_symmetrically(self):
        edge_geometry = parse_wkt(
            {
                "encoding": "WKT1",
                "geometry_type": "POLYGON",
                "wkt": (
                    "POLYGON ((0 0, 100.3 0, 100.3 100.000001, "
                    "0 100.000001, 0 0))"
                ),
            }
        )
        self.assertEqual(
            image_boundary_sides(edge_geometry, 100, 100),
            ("top", "right", "bottom", "left"),
        )
        interior = parse_wkt(
            {
                "encoding": "WKT1",
                "geometry_type": "POLYGON",
                "wkt": "POLYGON ((1 1, 99 1, 99 99, 1 99, 1 1))",
            }
        )
        self.assertEqual(image_boundary_sides(interior, 100, 100), ())

    def test_candidate_ledger_reconciles_to_package_and_bindings(self):
        with tempfile.TemporaryDirectory() as temporary:
            package_root = self.copy_fixture(temporary)
            self.add_candidate_ledger(package_root)
            ledger = validate_candidate_dispositions(package_root)
            self.assertEqual(len(ledger.records), 1)
            self.assertEqual(ledger.disposition_counts, {"accepted": 1, "excluded": 0})
            self.assertEqual(ledger.warning_count, 0)

    def test_unknown_record_field_fails_closed_even_with_rebound_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            package_root = self.copy_fixture(temporary)
            artifact_path, manifest_path = self.add_candidate_ledger(package_root)
            record = json.loads(artifact_path.read_text(encoding="utf-8"))
            record["unexpected"] = True
            artifact_path.write_bytes(canonical_json_bytes(record) + b"\n")
            self.rewrite_artifact_binding(manifest_path, artifact_path)
            with self.assertRaisesRegex(ContractError, "unknown fields"):
                validate_candidate_dispositions(package_root)

    def test_false_image_boundary_reason_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            package_root = self.copy_fixture(temporary)
            artifact_path, manifest_path = self.add_candidate_ledger(package_root)
            record = json.loads(artifact_path.read_text(encoding="utf-8"))
            record["reason"] = "cell_touches_image_boundary"
            artifact_path.write_bytes(canonical_json_bytes(record) + b"\n")
            manifest = read_json(manifest_path)
            manifest["reason_counts"] = {"cell_touches_image_boundary": 1}
            write_canonical(manifest_path, manifest)
            self.rewrite_artifact_binding(manifest_path, artifact_path)
            with self.assertRaisesRegex(ContractError, "physical image-edge contact"):
                validate_candidate_dispositions(package_root)

    def test_full_frame_policy_accepts_bound_edge_reason_and_rejects_mislabeling(self):
        with tempfile.TemporaryDirectory() as temporary:
            package_root = self.copy_fixture(temporary)
            self.bind_full_frame_policy(package_root)
            artifact_path, manifest_path = self.add_candidate_ledger(package_root)
            self.append_left_edge_candidate(package_root, artifact_path, manifest_path)
            ledger = validate_candidate_dispositions(package_root)
            self.assertEqual(ledger.image_boundary_side_counts["left"], 1)

            records = [
                json.loads(line)
                for line in artifact_path.read_text(encoding="utf-8").splitlines()
            ]
            records[1]["reason"] = "cell_not_covered_by_annotation"
            artifact_path.write_bytes(
                b"".join(canonical_json_bytes(record) + b"\n" for record in records)
            )
            manifest = read_json(manifest_path)
            manifest["reason_counts"] = {
                "accepted": 1,
                "cell_not_covered_by_annotation": 1,
            }
            write_canonical(manifest_path, manifest)
            self.rewrite_artifact_binding(manifest_path, artifact_path)
            with self.assertRaisesRegex(ContractError, "image-edge candidate"):
                validate_candidate_dispositions(package_root)

    def test_full_frame_policy_rejects_accepted_edge_candidate(self):
        with tempfile.TemporaryDirectory() as temporary:
            package_root = self.copy_fixture(temporary)
            self.bind_full_frame_policy(package_root)
            artifact_path, manifest_path = self.add_candidate_ledger(package_root)
            self.append_left_edge_candidate(package_root, artifact_path, manifest_path)
            records = [
                json.loads(line)
                for line in artifact_path.read_text(encoding="utf-8").splitlines()
            ]
            records[1]["disposition"] = "accepted"
            records[1]["reason"] = "accepted"
            artifact_path.write_bytes(
                b"".join(canonical_json_bytes(record) + b"\n" for record in records)
            )
            manifest = read_json(manifest_path)
            manifest["disposition_counts"] = {"accepted": 2, "excluded": 0}
            manifest["reason_counts"] = {"accepted": 2}
            write_canonical(manifest_path, manifest)
            self.rewrite_artifact_binding(manifest_path, artifact_path)
            with self.assertRaisesRegex(ContractError, "image-edge candidate"):
                validate_candidate_dispositions(package_root)

    def test_candidate_identity_and_false_claims_are_enforced(self):
        with tempfile.TemporaryDirectory() as temporary:
            package_root = self.copy_fixture(temporary)
            artifact_path, manifest_path = self.add_candidate_ledger(package_root)
            record = json.loads(artifact_path.read_text(encoding="utf-8"))
            record["candidate_id"] = "cand_" + "0" * 64
            artifact_path.write_bytes(canonical_json_bytes(record) + b"\n")
            self.rewrite_artifact_binding(manifest_path, artifact_path)
            with self.assertRaisesRegex(ContractError, "canonical geometry identity"):
                validate_candidate_dispositions(package_root)

        with tempfile.TemporaryDirectory() as temporary:
            package_root = self.copy_fixture(temporary)
            _, manifest_path = self.add_candidate_ledger(package_root)
            manifest = read_json(manifest_path)
            manifest["claims"]["scientific_validation"] = True
            write_canonical(manifest_path, manifest)
            with self.assertRaisesRegex(ContractError, "must be false"):
                validate_candidate_dispositions(package_root)

        with tempfile.TemporaryDirectory() as temporary:
            package_root = self.copy_fixture(temporary)
            _, manifest_path = self.add_candidate_ledger(package_root)
            manifest = read_json(manifest_path)
            manifest["pilot_status"] = "validated"
            write_canonical(manifest_path, manifest)
            with self.assertRaisesRegex(ContractError, "pilot_status is unsupported"):
                validate_candidate_dispositions(package_root)

    def test_core_import_does_not_import_optional_imaging_dependencies(self):
        code = (
            "import sys; sys.path.insert(0, 'src'); "
            "import ifquant_platform.qc_rendering; "
            "assert 'PIL' not in sys.modules; assert 'numpy' not in sys.modules"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_renderer_writes_three_deterministic_images_and_bound_manifest(self):
        try:
            import numpy as np
            from PIL import Image
        except ImportError:
            self.skipTest("optional QC dependencies are not installed")

        with tempfile.TemporaryDirectory() as temporary:
            package_root = self.copy_fixture(temporary)
            source = package_root / "source.ome.tif"
            plane = np.arange(10000, dtype=np.uint16).reshape(100, 100)
            Image.fromarray(plane).save(source, format="TIFF", compression="tiff_deflate")
            image_path = package_root / "manifests" / "image-manifest.json"
            image = read_json(image_path)
            image["source_artifact"].update(
                {
                    "source_uri": "source.ome.tif",
                    "sha256": file_sha256(source),
                    "size_bytes": source.stat().st_size,
                    "media_type": "image/ome-tiff",
                }
            )
            write_canonical(image_path, image)
            package_path = package_root / "package.json"
            package = read_json(package_path)
            package["image"]["manifest_sha256"] = canonical_sha256(image)
            package["image"]["source_sha256"] = image["source_artifact"]["sha256"]
            write_canonical(package_path, package)
            self.add_candidate_ledger(package_root)

            first = Path(temporary) / "render-one"
            second = Path(temporary) / "render-two"
            manifest = render_qc(package_root, first, montage_per_group=1, montage_crop_size=64)
            render_qc(package_root, second, montage_per_group=1, montage_crop_size=64)
            names = [
                "dapi-overview.png",
                "dapi-candidate-disposition.png",
                "dapi-review-montage.png",
                "qc-manifest.json",
            ]
            self.assertEqual(sorted(path.name for path in first.iterdir()), sorted(names))
            for name in names:
                self.assertEqual((first / name).read_bytes(), (second / name).read_bytes())
            self.assertEqual(manifest["status"], "rendered_unvalidated_engineering_qc")
            self.assertEqual(
                manifest["producer"]["implementation_sha256"],
                file_sha256(ROOT / "src" / "ifquant_platform" / "qc_rendering.py"),
            )
            self.assertFalse(manifest["claims"]["scientific_validation"])
            self.assertFalse(manifest["claims"]["human_review_completed"])
            self.assertEqual(
                manifest["counts"]["dispositions"], {"accepted": 1, "excluded": 0}
            )
            self.assertEqual(len(manifest["outputs"]), 3)
            self.assertEqual(
                manifest["counts"]["image_boundary_sides"],
                {"top": 0, "right": 0, "bottom": 0, "left": 0},
            )

    def test_full_frame_roi_has_four_visible_display_edges(self):
        try:
            import numpy as np
            from PIL import Image
        except ImportError:
            self.skipTest("optional QC dependencies are not installed")

        with tempfile.TemporaryDirectory() as temporary:
            package_root = self.copy_fixture(temporary)
            source = package_root / "source.ome.tif"
            Image.fromarray(np.arange(10000, dtype=np.uint16).reshape(100, 100)).save(
                source, format="TIFF", compression="tiff_deflate"
            )
            image_path = package_root / "manifests" / "image-manifest.json"
            image = read_json(image_path)
            image["source_artifact"].update(
                {
                    "source_uri": "source.ome.tif",
                    "sha256": file_sha256(source),
                    "size_bytes": source.stat().st_size,
                    "media_type": "image/ome-tiff",
                }
            )
            write_canonical(image_path, image)

            annotation_path = package_root / "manifests" / "annotation-set.json"
            annotations = read_json(annotation_path)
            annotations["annotations"][0]["geometry"] = {
                "encoding": "WKT1",
                "geometry_type": "POLYGON",
                "wkt": "POLYGON ((0 0, 0 100, 100 100, 100 0, 0 0))",
            }
            write_canonical(annotation_path, annotations)

            package_path = package_root / "package.json"
            package = read_json(package_path)
            package["image"]["manifest_sha256"] = canonical_sha256(image)
            package["image"]["source_sha256"] = image["source_artifact"]["sha256"]
            package["annotation_set"]["manifest_sha256"] = canonical_sha256(annotations)
            write_canonical(package_path, package)
            self.add_candidate_ledger(package_root)

            output = Path(temporary) / "full-frame-render"
            manifest = render_qc(
                package_root, output, montage_per_group=1, montage_crop_size=64
            )
            with Image.open(output / "dapi-overview.png") as overview:
                cyan = (0, 220, 255)
                self.assertEqual(overview.getpixel((50, 0)), cyan)
                self.assertEqual(overview.getpixel((99, 50)), cyan)
                self.assertEqual(overview.getpixel((50, 99)), cyan)
                self.assertEqual(overview.getpixel((0, 50)), cyan)
            self.assertEqual(
                manifest["display"]["roi_boundary_display"],
                "clamped_to_visible_pixel_extent",
            )

    def test_renderer_requires_a_fresh_output_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            package_root = self.copy_fixture(temporary)
            self.add_candidate_ledger(package_root)
            output = Path(temporary) / "already-there"
            output.mkdir()
            with self.assertRaisesRegex(ContractError, "must be fresh"):
                render_qc(package_root, output)


if __name__ == "__main__":
    unittest.main()
