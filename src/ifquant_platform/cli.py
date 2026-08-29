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
from .method_contracts import (
    load_measurement_definition,
    load_parameter_set,
    resolve_method,
)
from .package_validation import validate_cell_package


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

