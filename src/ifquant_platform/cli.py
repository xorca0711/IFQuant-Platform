"""Command-line entry point for IFQuant Platform engineering validation."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from . import __version__
from .backends import candidate_backends
from .canonical import ContractError
from .dataset_governance import validate_governed_observation_set
from .method_contracts import (
    load_measurement_definition,
    load_parameter_set,
    resolve_method,
)
from .package_validation import validate_cell_package
from .phase3_validation import (
    validate_nuclear_reference_set,
    validate_split_manifest,
)
from .phase4_evaluation import evaluate_segmentation


def _expect(actual: str, expected: str | None, label: str) -> None:
    if expected is not None and actual != expected:
        raise ContractError(f"expected {label} {expected}, computed {actual}")


def _write_report(report: dict[str, Any]) -> None:
    json.dump(report, sys.stdout, ensure_ascii=False, sort_keys=True, indent=2)
    sys.stdout.write("\n")


def _validate_method(args: argparse.Namespace) -> dict[str, Any]:
    definition = load_measurement_definition(args.definition)
    parameter_set = load_parameter_set(args.parameter_set)
    resolved = resolve_method(definition.document, parameter_set.document)
    _expect(definition.canonical_sha256, args.expect_definition_sha256, "definition SHA-256")
    _expect(parameter_set.canonical_sha256, args.expect_parameter_set_sha256, "parameter-set SHA-256")
    _expect(resolved.method_instance_sha256, args.expect_method_instance_sha256, "method-instance SHA-256")
    return {
        "status": "valid",
        "definition_id": definition.document["definition_id"],
        "definition_file_sha256": definition.file_sha256,
        "definition_sha256": definition.canonical_sha256,
        "parameter_set_id": parameter_set.document["parameter_set_id"],
        "parameter_set_file_sha256": parameter_set.file_sha256,
        "parameter_set_sha256": parameter_set.canonical_sha256,
        "method_instance_sha256": resolved.method_instance_sha256,
        "parameter_bindings": [
            {"parameter_id": key, "value": value}
            for key, value in resolved.parameter_bindings
        ],
        "scope_binding": parameter_set.document["scope"]["binding"],
        "authorization": "none",
        "scientific_validation": False,
        "backend_equivalence": False,
        "validation_scope": (
            "contract closure and deterministic identity only; not endpoint authorization, "
            "biological validity, or backend equivalence"
        ),
    }


def _validate_package(args: argparse.Namespace) -> dict[str, Any]:
    report = validate_cell_package(args.package)
    _expect(report.package_canonical_sha256, args.expect_package_sha256, "package SHA-256")
    _expect(report.method_instance_sha256, args.expect_method_instance_sha256, "method-instance SHA-256")
    return report.as_dict()


def _validate_observation_set(args: argparse.Namespace) -> dict[str, Any]:
    report = validate_governed_observation_set(args.observation_set)
    _expect(
        report.observation_set_sha256,
        args.expect_observation_set_sha256,
        "observation-set SHA-256",
    )
    return report.as_dict()


def _validate_reference_set(args: argparse.Namespace) -> dict[str, Any]:
    report = validate_nuclear_reference_set(args.reference_set)
    _expect(
        report.reference_set_sha256,
        args.expect_reference_set_sha256,
        "reference-set SHA-256",
    )
    _expect(
        report.governed_observation_set_sha256,
        args.expect_observation_set_sha256,
        "observation-set SHA-256",
    )
    return report.as_dict()


def _validate_split(args: argparse.Namespace) -> dict[str, Any]:
    report = validate_split_manifest(args.split_manifest)
    _expect(
        report.split_manifest_sha256,
        args.expect_split_manifest_sha256,
        "split-manifest SHA-256",
    )
    _expect(
        report.reference_set_sha256,
        args.expect_reference_set_sha256,
        "reference-set SHA-256",
    )
    _expect(
        report.held_out_test_image_ids_sha256,
        args.expect_held_out_test_image_ids_sha256,
        "held-out-test image-IDs SHA-256",
    )
    _expect(
        report.held_out_test_reference_content_sha256,
        args.expect_held_out_test_reference_content_sha256,
        "held-out-test reference-content SHA-256",
    )
    return report.as_dict()


def _evaluate_segmentation(args: argparse.Namespace) -> dict[str, Any]:
    report = evaluate_segmentation(args.plan, args.predictions)
    _expect(report.evaluation_plan_sha256, args.expect_plan_sha256, "evaluation-plan SHA-256")
    _expect(report.prediction_instances_sha256, args.expect_predictions_sha256, "prediction-instances SHA-256")
    return report.as_dict()


def _backend_report() -> dict[str, Any]:
    return {
        "status": "ok",
        "interface_claim": "shared package shape only; no backend equivalence",
        "backends": [
            {
                "backend_id": item.backend_id,
                "display_name": item.display_name,
                "executor": item.executor,
                "extension_id": item.extension_id,
                "model_weights_required": item.model_weights_required,
                "status": item.status,
            }
            for item in candidate_backends()
        ],
    }


def _render_qc(args: argparse.Namespace) -> dict[str, Any]:
    # Keep Pillow and NumPy outside the core CLI import path.
    from .qc_rendering import render_qc

    manifest = render_qc(
        args.package,
        args.output,
        candidate_manifest=args.candidate_manifest,
        candidate_dispositions=args.candidate_dispositions,
        lower_percentile=args.lower_percentile,
        upper_percentile=args.upper_percentile,
        montage_per_group=args.montage_per_group,
        montage_crop_size=args.montage_crop_size,
    )
    return {
        "status": manifest["status"],
        "output_directory": str(args.output),
        "manifest_relative_path": "qc-manifest.json",
        "outputs": manifest["outputs"],
        "claims": manifest["claims"],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ifquant-platform",
        description="Validate IFQuant Platform engineering contracts and canonical packages.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    package_parser = subparsers.add_parser(
        "validate-package",
        aliases=["validate"],
        help="validate a package.json file or package directory without modifying it",
    )
    package_parser.add_argument("package")
    package_parser.add_argument("--expect-package-sha256")
    package_parser.add_argument("--expect-method-instance-sha256")
    package_parser.set_defaults(handler=_validate_package)

    observation_set_parser = subparsers.add_parser(
        "validate-observation-set",
        help="validate a governed observation set and its bound artifacts without modifying them",
    )
    observation_set_parser.add_argument(
        "observation_set",
        help="observation-set.json or its containing directory",
    )
    observation_set_parser.add_argument("--expect-observation-set-sha256")
    observation_set_parser.set_defaults(handler=_validate_observation_set)

    reference_set_parser = subparsers.add_parser(
        "validate-reference-set",
        aliases=["validate-nuclear-reference-set"],
        help="validate a frozen DAPI nuclear-reference set and its bound artifacts",
    )
    reference_set_parser.add_argument(
        "reference_set",
        help="nuclear-reference-set.json or its containing directory",
    )
    reference_set_parser.add_argument("--expect-reference-set-sha256")
    reference_set_parser.add_argument("--expect-observation-set-sha256")
    reference_set_parser.set_defaults(handler=_validate_reference_set)

    split_parser = subparsers.add_parser(
        "validate-split",
        aliases=["validate-split-manifest"],
        help="validate a frozen image-level split and its recursive reference boundary",
    )
    split_parser.add_argument(
        "split_manifest",
        help="split-manifest.json or its containing directory",
    )
    split_parser.add_argument("--expect-split-manifest-sha256")
    split_parser.add_argument("--expect-reference-set-sha256")
    split_parser.add_argument("--expect-held-out-test-image-ids-sha256")
    split_parser.add_argument("--expect-held-out-test-reference-content-sha256")
    split_parser.set_defaults(handler=_validate_split)

    evaluation_parser = subparsers.add_parser(
        "evaluate-segmentation",
        help="evaluate native QuPath instance pixels against a frozen Phase 4 plan",
    )
    evaluation_parser.add_argument("plan", help="frozen segmentation evaluation plan")
    evaluation_parser.add_argument("--predictions", required=True, help="ordered prediction-instance JSONL")
    evaluation_parser.add_argument("--expect-plan-sha256")
    evaluation_parser.add_argument("--expect-predictions-sha256")
    evaluation_parser.set_defaults(handler=_evaluate_segmentation)

    method_parser = subparsers.add_parser(
        "validate-method", help="validate and resolve a measurement definition and parameter set"
    )
    method_parser.add_argument("definition")
    method_parser.add_argument("--parameter-set", required=True)
    method_parser.add_argument("--expect-definition-sha256")
    method_parser.add_argument("--expect-parameter-set-sha256")
    method_parser.add_argument("--expect-method-instance-sha256")
    method_parser.set_defaults(handler=_validate_method)

    backend_parser = subparsers.add_parser(
        "backends", help="list candidate segmentation adapters and their identity requirements"
    )
    backend_parser.set_defaults(handler=lambda _args: _backend_report())

    qc_parser = subparsers.add_parser(
        "render-qc",
        help="render deterministic, non-scientific DAPI QC images from a package and candidate ledger",
    )
    qc_parser.add_argument("package", help="package.json or its containing directory")
    qc_parser.add_argument("--output", required=True, help="fresh output directory")
    qc_parser.add_argument(
        "--candidate-manifest",
        help="candidate manifest (default: PACKAGE/qc/candidate-dispositions-manifest.json)",
    )
    qc_parser.add_argument(
        "--candidate-dispositions",
        help="candidate JSONL; if given, it must match the path bound by the candidate manifest",
    )
    qc_parser.add_argument("--lower-percentile", type=float, default=1.0)
    qc_parser.add_argument("--upper-percentile", type=float, default=99.8)
    qc_parser.add_argument("--montage-per-group", type=int, default=8)
    qc_parser.add_argument("--montage-crop-size", type=int, default=192)
    qc_parser.set_defaults(handler=_render_qc)
    # Optional imaging dependencies are loaded only by the selected command.
    from .tissue_cli import add_commands
    add_commands(subparsers)
    from .spatial_cli import add_commands as add_spatial_commands
    add_spatial_commands(subparsers)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        report = args.handler(args)
    except (ContractError, OSError) as exc:
        print(f"IFQUANT_PLATFORM_VALIDATION_ERROR: {exc}", file=sys.stderr)
        return 2
    _write_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
