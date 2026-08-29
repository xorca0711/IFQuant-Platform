"""Candidate segmentation backends behind one identity-bearing interface.

Registration means only that a backend can be represented by the platform's
contracts. It is not evidence of numerical equivalence, biological validity, or
fitness outside the backend's declared scope.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, Mapping

from .canonical import ContractError

BackendId = Literal["native_qupath", "stardist", "instanseg"]


@dataclass(frozen=True, slots=True)
class BackendDescriptor:
    """Stable capability metadata, never a compatibility claim."""

    backend_id: BackendId
    display_name: str
    executor: Literal["qupath"]
    model_weights_required: bool
    extension_id: str | None
    status: Literal["candidate"] = "candidate"

    def validate_run_identity(self, run: Mapping[str, object]) -> None:
        if run.get("backend_id") != self.backend_id:
            raise ContractError(
                f"segmentation run backend_id must be {self.backend_id!r}"
            )
        model = run.get("model")
        if not isinstance(model, Mapping):
            raise ContractError(f"{self.backend_id} requires an explicit model descriptor")
        weights = model.get("weights_sha256")
        if self.model_weights_required and not isinstance(weights, str):
            raise ContractError(f"{self.backend_id} requires an explicit model-weights identity")
        if not self.model_weights_required and weights is not None:
            raise ContractError(
                f"{self.backend_id} uses a detector descriptor and must have null weights_sha256"
            )


_BACKENDS: Mapping[str, BackendDescriptor] = MappingProxyType(
    {
        "native_qupath": BackendDescriptor(
            backend_id="native_qupath",
            display_name="QuPath native cell detection",
            executor="qupath",
            model_weights_required=False,
            extension_id=None,
        ),
        "stardist": BackendDescriptor(
            backend_id="stardist",
            display_name="StarDist for QuPath",
            executor="qupath",
            model_weights_required=True,
            extension_id="qupath-extension-stardist",
        ),
        "instanseg": BackendDescriptor(
            backend_id="instanseg",
            display_name="InstanSeg for QuPath",
            executor="qupath",
            model_weights_required=True,
            extension_id="qupath-extension-instanseg",
        ),
    }
)


def candidate_backends() -> tuple[BackendDescriptor, ...]:
    return tuple(_BACKENDS[key] for key in sorted(_BACKENDS))


def get_backend(backend_id: str) -> BackendDescriptor:
    try:
        return _BACKENDS[backend_id]
    except KeyError as exc:
        choices = ", ".join(sorted(_BACKENDS))
        raise ContractError(f"unknown segmentation backend {backend_id!r}; choose {choices}") from exc
