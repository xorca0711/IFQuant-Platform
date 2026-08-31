"""IFQuant Platform's backend-neutral contracts and validation tools."""

from .backends import BackendDescriptor, candidate_backends, get_backend
from .canonical import ContractError, canonical_json_bytes, load_strict_json
from .dataset_governance import (
    GovernedObservationSetReport,
    validate_governed_observation_set,
)
from .package_validation import PackageValidationReport, validate_cell_package
from .phase3_validation import (
    HELD_OUT_REFERENCE_CONTENT_PROFILE,
    NuclearReferenceSetReport,
    SplitManifestReport,
    compute_held_out_reference_content_sha256,
    validate_nuclear_reference_set,
    validate_split_manifest,
)
from .phase4_evaluation import Phase4EvaluationReport, evaluate_segmentation

__all__ = [
    "HELD_OUT_REFERENCE_CONTENT_PROFILE",
    "BackendDescriptor",
    "ContractError",
    "GovernedObservationSetReport",
    "NuclearReferenceSetReport",
    "PackageValidationReport",
    "Phase4EvaluationReport",
    "SplitManifestReport",
    "candidate_backends",
    "canonical_json_bytes",
    "compute_held_out_reference_content_sha256",
    "evaluate_segmentation",
    "get_backend",
    "load_strict_json",
    "validate_cell_package",
    "validate_governed_observation_set",
    "validate_nuclear_reference_set",
    "validate_split_manifest",
]

__version__ = "0.1.0"
