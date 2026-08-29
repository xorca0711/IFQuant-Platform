"""IFQuant Platform's backend-neutral contracts and validation tools."""

from .backends import BackendDescriptor, candidate_backends, get_backend
from .canonical import ContractError, canonical_json_bytes, load_strict_json
from .package_validation import PackageValidationReport, validate_cell_package

__all__ = [
    "BackendDescriptor",
    "ContractError",
    "PackageValidationReport",
    "canonical_json_bytes",
    "candidate_backends",
    "get_backend",
    "load_strict_json",
    "validate_cell_package",
]

__version__ = "0.1.0"
