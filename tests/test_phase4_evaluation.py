from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from ifquant_platform import ContractError, evaluate_segmentation
from ifquant_platform.phase4_evaluation import (
    _Instance,
    _maximum_cardinality_matches,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "validation" / "fixtures" / "minimal-phase4-evaluation"


class Phase4EvaluationTests(unittest.TestCase):
    def test_fixture_evaluates_deterministically_without_scientific_claims(self):
        report = evaluate_segmentation(
            FIXTURE / "evaluation-plan.json", FIXTURE / "prediction-instances.jsonl"
        )
        self.assertEqual(report.status, "valid_engineering_evaluation")
        self.assertEqual((report.reference_count, report.prediction_count), (1, 1))
        self.assertEqual(
            (report.true_positive_count, report.false_positive_count, report.false_negative_count),
            (1, 0, 0),
        )
        self.assertEqual((report.precision, report.recall, report.f1), (1.0, 1.0, 1.0))
        self.assertEqual(report.boundary_f1, 1.0)
        self.assertEqual(report.signed_count_error, 0)
        self.assertEqual(report.measurement_bias["dapi_mean"]["mean_signed_error"], 2.0)
        self.assertTrue(report.acceptance_passed)
        self.assertEqual(report.acceptance_scope, "synthetic_engineering_contract_fixture_only")
        self.assertFalse(report.scientific_validation)
        self.assertEqual(report.authorization, "none")

    def test_plan_fails_closed_when_reference_artifact_hash_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(FIXTURE, root / "phase4")
            shutil.copytree(
                FIXTURE.parent / "minimal-phase3-reference-split",
                root / "minimal-phase3-reference-split",
            )
            plan_path = root / "phase4" / "evaluation-plan.json"
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            plan["reference_instances"]["sha256"] = "0" * 64
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            with self.assertRaisesRegex(
                ContractError, "reference-instance artifact SHA-256 mismatch"
            ):
                evaluate_segmentation(plan_path, root / "phase4" / "prediction-instances.jsonl")

    def test_matching_maximizes_cardinality_at_declared_iou_gate(self):
        def instance(name: str, pixels: set[tuple[int, int]]) -> _Instance:
            return _Instance("image", name, frozenset(pixels), False, {})

        refs = [instance("r1", {(0, 0), (1, 0)}), instance("r2", {(2, 0), (3, 0)})]
        preds = [instance("p1", {(0, 0), (1, 0)}), instance("p2", {(2, 0), (3, 0)})]
        matches = _maximum_cardinality_matches(refs, preds, 0.5)
        self.assertEqual([(left, right) for left, right, _ in matches], [(0, 0), (1, 1)])


if __name__ == "__main__":
    unittest.main()
