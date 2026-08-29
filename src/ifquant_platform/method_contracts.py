"""Backend-neutral measurement definitions and scope-bound parameter sets.

This module deliberately separates scientific feature meaning from acquisition
channel indices, backend/runtime identity, model weights, governance, and file
paths. A resolved method identity binds a canonical definition to one canonical
parameter set; it does not authorize use or establish scientific validity.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from .canonical import (
    ContractError,
    canonical_json_bytes,
    canonical_sha256,
    file_sha256,
    load_strict_json,
)

SCHEMA_VERSION = "1.0.0"
DEFINITION_SCHEMA_URI = (
    "https://ifquant.org/contracts/platform/v1/measurement-definition.schema.json"
)
PARAMETER_SET_SCHEMA_URI = (
    "https://ifquant.org/contracts/platform/v1/parameter-set.schema.json"
)
DEFINITION_TYPE = "ifquant_platform_measurement_definition"
PARAMETER_SET_TYPE = "ifquant_platform_parameter_set"
METHOD_INSTANCE_DOMAIN = "ifquant-platform-method-instance/v1"
SEMVER_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")

DEFINITION_FIELDS = frozenset(
    {
        "$schema",
        "schema_version",
        "contract_type",
        "definition_id",
        "definition_version",
        "object_type",
        "dimensionality",
        "semantic_inputs",
        "parameter_slots",
        "features",
        "missingness",
        "aggregation",
    }
)
PARAMETER_SET_FIELDS = frozenset(
    {
        "$schema",
        "schema_version",
        "contract_type",
        "parameter_set_id",
        "parameter_set_version",
        "measurement_definition",
        "scope",
        "values",
    }
)


@dataclass(frozen=True, slots=True)
class LoadedContract:
    document: Mapping[str, Any]
    file_sha256: str
    canonical_sha256: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class ResolvedMethod:
    definition_sha256: str
    parameter_set_sha256: str
    method_instance_sha256: str
    parameter_bindings: tuple[tuple[str, bool | int | float | str], ...]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def _object(value: Any, location: str) -> Mapping[str, Any]:
    _require(isinstance(value, Mapping), f"{location} must be an object")
    return value


def _array(value: Any, location: str) -> list[Any]:
    _require(
        isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)),
        f"{location} must be an array",
    )
    return list(value)


def _exact_fields(value: Mapping[str, Any], expected: frozenset[str] | set[str], location: str) -> None:
    _require(all(isinstance(key, str) for key in value), f"{location} keys must be strings")
    actual = set(value)
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    _require(not missing, f"{location} is missing: {', '.join(missing)}")
    _require(not unknown, f"{location} has unknown fields: {', '.join(unknown)}")


def _nonempty(value: Any, location: str) -> str:
    _require(isinstance(value, str) and bool(value.strip()), f"{location} must be non-empty")
    return value


def _identifier(value: Any, location: str) -> str:
    text = _nonempty(value, location)
    _require(bool(ID_RE.fullmatch(text)), f"{location} must be a contract identifier")
    return text


def _enum(value: Any, allowed: set[str], location: str) -> str:
    _require(isinstance(value, str), f"{location} must be a string")
    _require(value in allowed, f"{location} must be one of: {', '.join(sorted(allowed))}")
    return value


def _semver(value: Any, location: str) -> str:
    text = _nonempty(value, location)
    _require(bool(SEMVER_RE.fullmatch(text)), f"{location} must be MAJOR.MINOR.PATCH")
    return text


def _sha256(value: Any, location: str) -> str:
    _require(isinstance(value, str) and bool(SHA256_RE.fullmatch(value)), f"{location} must be lowercase SHA-256")
    return value


def _sorted_unique(ids: list[str], location: str) -> None:
    _require(len(ids) == len(set(ids)), f"{location} IDs must be unique")
    _require(ids == sorted(ids), f"{location} must be sorted by ID")


def _validate_semantic_inputs(value: Any) -> dict[str, Mapping[str, Any]]:
    inputs = _array(value, "definition.semantic_inputs")
    result: dict[str, Mapping[str, Any]] = {}
    ids: list[str] = []
    for index, item in enumerate(inputs):
        location = f"definition.semantic_inputs[{index}]"
        entry = _object(item, location)
        _exact_fields(
            entry,
            {
                "input_id",
                "marker_id",
                "intensity_coordinate",
                "intensity_representation",
                "intensity_transform",
            },
            location,
        )
        input_id = _identifier(entry["input_id"], f"{location}.input_id")
        marker_id = _identifier(entry["marker_id"], f"{location}.marker_id")
        _enum(
            entry["intensity_coordinate"],
            {"native_sample_value", "normalized_unit_interval"},
            f"{location}.intensity_coordinate",
        )
        _enum(
            entry["intensity_representation"],
            {"unsigned_integer", "floating_point"},
            f"{location}.intensity_representation",
        )
        _enum(
            entry["intensity_transform"],
            {"none", "linear_rescale", "log1p"},
            f"{location}.intensity_transform",
        )
        ids.append(input_id)
        result[input_id] = entry
    _sorted_unique(ids, "definition.semantic_inputs")
    return result


def _constraint_value_matches_type(value: Any, value_type: str) -> bool:
    if value_type == "boolean":
        return isinstance(value, bool)
    if value_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if value_type == "number":
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value))
        )
    return isinstance(value, str) if value_type == "string" else False


def _validate_parameter_slots(value: Any) -> dict[str, Mapping[str, Any]]:
    slots = _array(value, "definition.parameter_slots")
    result: dict[str, Mapping[str, Any]] = {}
    ids: list[str] = []
    for index, item in enumerate(slots):
        location = f"definition.parameter_slots[{index}]"
        slot = _object(item, location)
        _exact_fields(
            slot,
            {"parameter_id", "value_type", "unit", "constraints"},
            location,
        )
        parameter_id = _identifier(slot["parameter_id"], f"{location}.parameter_id")
        value_type = _enum(
            slot["value_type"], {"boolean", "integer", "number", "string"}, f"{location}.value_type"
        )
        _identifier(slot["unit"], f"{location}.unit")
        constraints = _object(slot["constraints"], f"{location}.constraints")
        _exact_fields(
            constraints,
            {"minimum", "maximum", "allowed_values"},
            f"{location}.constraints",
        )
        minimum = constraints["minimum"]
        maximum = constraints["maximum"]
        if value_type in {"integer", "number"}:
            if minimum is not None:
                _require(
                    _constraint_value_matches_type(minimum, value_type),
                    f"{location}.constraints.minimum has the wrong value type",
                )
            if maximum is not None:
                _require(
                    _constraint_value_matches_type(maximum, value_type),
                    f"{location}.constraints.maximum has the wrong value type",
                )
            if minimum is not None and maximum is not None:
                _require(minimum <= maximum, f"{location}.constraints minimum exceeds maximum")
        else:
            _require(
                minimum is None and maximum is None,
                f"{location}.constraints minimum/maximum require a numeric value type",
            )
        allowed = constraints["allowed_values"]
        if allowed is not None:
            allowed_values = _array(allowed, f"{location}.constraints.allowed_values")
            _require(bool(allowed_values), f"{location}.constraints.allowed_values must not be empty")
            _require(
                all(_constraint_value_matches_type(item, value_type) for item in allowed_values),
                f"{location}.constraints.allowed_values has the wrong value type",
            )
            canonical_values = [canonical_json_bytes(item) for item in allowed_values]
            _require(
                canonical_values == sorted(set(canonical_values)),
                f"{location}.constraints.allowed_values must be unique and canonically sorted",
            )
            if minimum is not None:
                _require(all(item >= minimum for item in allowed_values), f"{location}.constraints.allowed_values violates minimum")
            if maximum is not None:
                _require(all(item <= maximum for item in allowed_values), f"{location}.constraints.allowed_values violates maximum")
        ids.append(parameter_id)
        result[parameter_id] = slot
    _sorted_unique(ids, "definition.parameter_slots")
    return result


def _validate_features(
    value: Any,
    *,
    semantic_inputs: Mapping[str, Mapping[str, Any]],
    parameter_slots: Mapping[str, Mapping[str, Any]],
) -> None:
    features = _array(value, "definition.features")
    _require(bool(features), "definition.features must not be empty")
    ids: list[str] = []
    morphology_statistics = {
        "area",
        "circularity",
        "eccentricity",
        "major_axis_length",
        "minor_axis_length",
        "nucleus_cell_area_ratio",
        "perimeter",
        "solidity",
    }
    intensity_statistics = {"integrated_intensity", "maximum", "mean", "median", "minimum", "stddev"}
    for index, item in enumerate(features):
        location = f"definition.features[{index}]"
        feature = _object(item, location)
        _exact_fields(
            feature,
            {
                "feature_id",
                "feature_kind",
                "compartment",
                "statistic",
                "unit",
                "source",
                "input_id",
                "parameter_ids",
            },
            location,
        )
        feature_id = _identifier(feature["feature_id"], f"{location}.feature_id")
        feature_kind = _enum(feature["feature_kind"], {"intensity", "morphology"}, f"{location}.feature_kind")
        _enum(
            feature["compartment"],
            {"cell", "cytoplasm", "nucleus"},
            f"{location}.compartment",
        )
        statistic = _identifier(feature["statistic"], f"{location}.statistic")
        unit = _identifier(feature["unit"], f"{location}.unit")
        source = _enum(feature["source"], {"geometry", "semantic_input"}, f"{location}.source")
        input_id = feature["input_id"]
        if feature_kind == "morphology":
            _require(source == "geometry", f"{location}: morphology must derive from geometry")
            _require(input_id is None, f"{location}: morphology input_id must be null")
            _require(statistic in morphology_statistics, f"{location}.statistic is not a v1 morphology statistic")
            expected_unit = (
                "um2"
                if statistic == "area"
                else "um"
                if statistic in {"perimeter", "major_axis_length", "minor_axis_length"}
                else "ratio"
            )
            _require(unit == expected_unit, f"{location}.unit is incompatible with morphology statistic")
        else:
            _require(source == "semantic_input", f"{location}: intensity must derive from a semantic input")
            _require(isinstance(input_id, str) and input_id in semantic_inputs, f"{location}.input_id is undeclared")
            _require(statistic in intensity_statistics, f"{location}.statistic is not a v1 intensity statistic")
            coordinate = semantic_inputs[input_id]["intensity_coordinate"]
            if statistic == "integrated_intensity":
                _require(
                    coordinate == "native_sample_value"
                    and unit == "integrated_native_sample_value",
                    f"{location}.unit is incompatible with integrated intensity",
                )
            else:
                expected_unit = (
                    "native_sample_value"
                    if coordinate == "native_sample_value"
                    else "normalized_intensity"
                )
                _require(unit == expected_unit, f"{location}.unit is incompatible with semantic input")
        parameter_ids = [_identifier(item, f"{location}.parameter_ids") for item in _array(feature["parameter_ids"], f"{location}.parameter_ids")]
        _sorted_unique(parameter_ids, f"{location}.parameter_ids")
        _require(set(parameter_ids) <= set(parameter_slots), f"{location} references an undeclared parameter")
        ids.append(feature_id)
    _sorted_unique(ids, "definition.features")


def validate_measurement_definition(definition: Mapping[str, Any]) -> None:
    root = _object(definition, "definition")
    _exact_fields(root, DEFINITION_FIELDS, "definition")
    _require(root["$schema"] == DEFINITION_SCHEMA_URI, "definition.$schema is unsupported")
    _require(root["schema_version"] == SCHEMA_VERSION, "definition.schema_version is unsupported")
    _require(root["contract_type"] == DEFINITION_TYPE, "definition.contract_type is unsupported")
    _identifier(root["definition_id"], "definition.definition_id")
    _semver(root["definition_version"], "definition.definition_version")
    _enum(root["object_type"], {"cell"}, "definition.object_type")
    _enum(root["dimensionality"], {"2d"}, "definition.dimensionality")
    semantic_inputs = _validate_semantic_inputs(root["semantic_inputs"])
    parameter_slots = _validate_parameter_slots(root["parameter_slots"])
    _validate_features(root["features"], semantic_inputs=semantic_inputs, parameter_slots=parameter_slots)

    missingness = _object(root["missingness"], "definition.missingness")
    _exact_fields(missingness, {"unavailable", "nonfinite"}, "definition.missingness")
    _require(
        missingness["unavailable"] == "reject_package",
        "unavailable required features must reject the package",
    )
    _require(missingness["nonfinite"] == "reject", "non-finite values must be rejected")

    aggregation = _object(root["aggregation"], "definition.aggregation")
    _exact_fields(aggregation, {"method"}, "definition.aggregation")
    _enum(aggregation["method"], {"none", "sum", "ratio_of_sums"}, "definition.aggregation.method")


def validate_parameter_set(parameter_set: Mapping[str, Any]) -> None:
    root = _object(parameter_set, "parameter_set")
    _exact_fields(root, PARAMETER_SET_FIELDS, "parameter_set")
    _require(root["$schema"] == PARAMETER_SET_SCHEMA_URI, "parameter_set.$schema is unsupported")
    _require(root["schema_version"] == SCHEMA_VERSION, "parameter_set.schema_version is unsupported")
    _require(root["contract_type"] == PARAMETER_SET_TYPE, "parameter_set.contract_type is unsupported")
    _identifier(root["parameter_set_id"], "parameter_set.parameter_set_id")
    _semver(root["parameter_set_version"], "parameter_set.parameter_set_version")

    reference = _object(root["measurement_definition"], "parameter_set.measurement_definition")
    _exact_fields(reference, {"definition_id", "definition_version", "canonical_sha256"}, "parameter_set.measurement_definition")
    _identifier(reference["definition_id"], "parameter_set.measurement_definition.definition_id")
    _semver(reference["definition_version"], "parameter_set.measurement_definition.definition_version")
    _sha256(reference["canonical_sha256"], "parameter_set.measurement_definition.canonical_sha256")

    scope = _object(root["scope"], "parameter_set.scope")
    _exact_fields(scope, {"scope_id", "binding", "scope_profile_sha256", "transfer_policy"}, "parameter_set.scope")
    _identifier(scope["scope_id"], "parameter_set.scope.scope_id")
    binding = _enum(scope["binding"], {"content_addressed", "identifier_only_unattested"}, "parameter_set.scope.binding")
    if binding == "content_addressed":
        _sha256(scope["scope_profile_sha256"], "parameter_set.scope.scope_profile_sha256")
    else:
        _require(scope["scope_profile_sha256"] is None, "unattested scope cannot carry a profile hash")
    _require(scope["transfer_policy"] == "declared_scope_only", "parameter transfer must be declared_scope_only")

    values = _array(root["values"], "parameter_set.values")
    ids: list[str] = []
    for index, item in enumerate(values):
        location = f"parameter_set.values[{index}]"
        entry = _object(item, location)
        _exact_fields(entry, {"parameter_id", "value", "unit"}, location)
        ids.append(_identifier(entry["parameter_id"], f"{location}.parameter_id"))
        _identifier(entry["unit"], f"{location}.unit")
        _require(
            isinstance(entry["value"], (bool, int, float, str)),
            f"{location}.value must be a scalar canonical JSON value",
        )
    _sorted_unique(ids, "parameter_set.values")


def definition_sha256(definition: Mapping[str, Any]) -> str:
    validate_measurement_definition(definition)
    return canonical_sha256(definition)


def parameter_set_sha256(parameter_set: Mapping[str, Any]) -> str:
    validate_parameter_set(parameter_set)
    return canonical_sha256(parameter_set)


def _value_matches_type(value: object, value_type: str) -> bool:
    if value_type == "boolean":
        return isinstance(value, bool)
    if value_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if value_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if value_type == "string":
        return isinstance(value, str)
    return False


def _value_satisfies_constraints(
    value: bool | int | float | str,
    slot: Mapping[str, Any],
    parameter_id: str,
) -> None:
    constraints = _object(slot["constraints"], f"parameter {parameter_id!r} constraints")
    minimum = constraints["minimum"]
    maximum = constraints["maximum"]
    allowed_values = constraints["allowed_values"]
    if minimum is not None:
        _require(value >= minimum, f"parameter {parameter_id!r} violates minimum")
    if maximum is not None:
        _require(value <= maximum, f"parameter {parameter_id!r} violates maximum")
    if allowed_values is not None:
        _require(value in allowed_values, f"parameter {parameter_id!r} is not an allowed value")


def resolve_method(definition: Mapping[str, Any], parameter_set: Mapping[str, Any]) -> ResolvedMethod:
    validate_measurement_definition(definition)
    validate_parameter_set(parameter_set)
    definition_hash = definition_sha256(definition)
    parameter_hash = parameter_set_sha256(parameter_set)

    reference = _object(parameter_set["measurement_definition"], "parameter_set.measurement_definition")
    _require(reference["definition_id"] == definition["definition_id"], "parameter set targets the wrong definition_id")
    _require(reference["definition_version"] == definition["definition_version"], "parameter set targets the wrong definition_version")
    _require(reference["canonical_sha256"] == definition_hash, "parameter set definition hash does not match canonical bytes")

    slots = {
        item["parameter_id"]: item
        for item in _array(definition["parameter_slots"], "definition.parameter_slots")
    }
    supplied = {
        item["parameter_id"]: (item["value"], item["unit"])
        for item in _array(parameter_set["values"], "parameter_set.values")
    }
    _require(set(supplied) == set(slots), "parameter set must bind all and only declared parameter slots")
    for parameter_id, (value, unit) in supplied.items():
        slot = slots[parameter_id]
        value_type = slot["value_type"]
        expected_unit = slot["unit"]
        _require(_value_matches_type(value, value_type), f"parameter {parameter_id!r} has the wrong value type")
        _require(unit == expected_unit, f"parameter {parameter_id!r} has the wrong unit")
        _value_satisfies_constraints(value, slot, parameter_id)

    descriptor = {
        "contract": METHOD_INSTANCE_DOMAIN,
        "definition_sha256": definition_hash,
        "parameter_set_sha256": parameter_hash,
    }
    return ResolvedMethod(
        definition_sha256=definition_hash,
        parameter_set_sha256=parameter_hash,
        method_instance_sha256=hashlib.sha256(canonical_json_bytes(descriptor)).hexdigest(),
        parameter_bindings=tuple((key, supplied[key][0]) for key in sorted(supplied)),
    )


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(child) for key, child in value.items()})
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(_freeze(child) for child in value)
    return value


def load_measurement_definition(path: str | Path) -> LoadedContract:
    source = Path(path)
    payload = source.read_bytes()
    document = load_strict_json(source)
    _require(isinstance(document, Mapping), "measurement definition root must be an object")
    validate_measurement_definition(document)
    return LoadedContract(
        document=_freeze(document),
        file_sha256=file_sha256(source),
        canonical_sha256=definition_sha256(document),
        size_bytes=len(payload),
    )


def load_parameter_set(path: str | Path) -> LoadedContract:
    source = Path(path)
    payload = source.read_bytes()
    document = load_strict_json(source)
    _require(isinstance(document, Mapping), "parameter set root must be an object")
    validate_parameter_set(document)
    return LoadedContract(
        document=_freeze(document),
        file_sha256=file_sha256(source),
        canonical_sha256=parameter_set_sha256(document),
        size_bytes=len(payload),
    )
