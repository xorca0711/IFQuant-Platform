import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ifquant_platform.canonical import ContractError, load_strict_json  # noqa: E402
from ifquant_platform.method_contracts import (  # noqa: E402
    definition_sha256,
    load_measurement_definition,
    load_parameter_set,
    parameter_set_sha256,
    resolve_method,
    validate_measurement_definition,
    validate_parameter_set,
)


DEFINITION_PATH = ROOT / "contracts" / "examples" / "cell-morphology-intensity-v1.json"
PARAMETER_SET_PATH = (
    ROOT / "contracts" / "examples" / "cell-morphology-intensity-engineering-v1.json"
)
EXPECTED_DEFINITION_SHA256 = "b4699d43736ad279718126bdb0b87733c1c370d903a28d01335515af852c99e6"
EXPECTED_PARAMETER_SET_SHA256 = "0ab144834e8e57b3ce21787bcfc99f2fe6bf661d695184814a07375876c83027"
EXPECTED_METHOD_INSTANCE_SHA256 = "6c47eda4968b78ec47df0253205dfb9bae40ad5677964def25a0ed1ac0938d3d"


class MethodContractTests(unittest.TestCase):
    def setUp(self):
        self.definition = load_strict_json(DEFINITION_PATH)
        self.parameter_set = load_strict_json(PARAMETER_SET_PATH)

    def test_example_contracts_have_stable_separate_identities(self):
        self.assertEqual(definition_sha256(self.definition), EXPECTED_DEFINITION_SHA256)
        self.assertEqual(parameter_set_sha256(self.parameter_set), EXPECTED_PARAMETER_SET_SHA256)
        resolved = resolve_method(self.definition, self.parameter_set)
        self.assertEqual(resolved.method_instance_sha256, EXPECTED_METHOD_INSTANCE_SHA256)
        self.assertEqual(resolved.parameter_bindings, ())

    def test_semantic_change_changes_definition_and_resolved_method(self):
        changed = copy.deepcopy(self.definition)
        changed["features"][1]["statistic"] = "solidity"
        changed_hash = definition_sha256(changed)
        self.assertNotEqual(changed_hash, EXPECTED_DEFINITION_SHA256)
        rebound = copy.deepcopy(self.parameter_set)
        rebound["measurement_definition"]["canonical_sha256"] = changed_hash
        self.assertNotEqual(
            resolve_method(changed, rebound).method_instance_sha256,
            EXPECTED_METHOD_INSTANCE_SHA256,
        )

    def test_scope_bound_parameter_changes_do_not_change_definition_identity(self):
        definition = copy.deepcopy(self.definition)
        definition["parameter_slots"] = [
            {
                "parameter_id": "minimum_reportable_area",
                "value_type": "number",
                "unit": "um2",
                "constraints": {
                    "minimum": 0,
                    "maximum": 1000,
                    "allowed_values": None,
                },
            }
        ]
        definition["features"][0]["parameter_ids"] = ["minimum_reportable_area"]
        definition_hash = definition_sha256(definition)

        first = copy.deepcopy(self.parameter_set)
        first["measurement_definition"]["canonical_sha256"] = definition_hash
        first["values"] = [
            {"parameter_id": "minimum_reportable_area", "value": 1, "unit": "um2"}
        ]
        second = copy.deepcopy(first)
        second["values"][0]["value"] = 2

        self.assertEqual(definition_sha256(definition), definition_hash)
        self.assertNotEqual(parameter_set_sha256(first), parameter_set_sha256(second))
        self.assertNotEqual(
            resolve_method(definition, first).method_instance_sha256,
            resolve_method(definition, second).method_instance_sha256,
        )

    def test_backend_acquisition_governance_and_paths_do_not_enter_definition(self):
        for location, field, value in (
            ("root", "backend", "QuPath"),
            ("root", "authorization", "approved"),
            ("root", "output_path", "D:/somewhere"),
            ("input", "channel_index", 0),
        ):
            with self.subTest(field=field):
                changed = copy.deepcopy(self.definition)
                target = changed if location == "root" else changed["semantic_inputs"][0]
                target[field] = value
                with self.assertRaisesRegex(ContractError, "unknown fields"):
                    validate_measurement_definition(changed)

    def test_parameter_binding_is_exact_and_typed(self):
        definition = copy.deepcopy(self.definition)
        definition["parameter_slots"] = [
            {
                "parameter_id": "integer_parameter",
                "value_type": "integer",
                "unit": "count",
                "constraints": {
                    "minimum": 0,
                    "maximum": 10,
                    "allowed_values": None,
                },
            }
        ]
        definition["features"][0]["parameter_ids"] = ["integer_parameter"]
        definition_hash = definition_sha256(definition)

        missing = copy.deepcopy(self.parameter_set)
        missing["measurement_definition"]["canonical_sha256"] = definition_hash
        with self.assertRaisesRegex(ContractError, "all and only"):
            resolve_method(definition, missing)

        boolean = copy.deepcopy(missing)
        boolean["values"] = [
            {"parameter_id": "integer_parameter", "value": True, "unit": "count"}
        ]
        with self.assertRaisesRegex(ContractError, "wrong value type"):
            resolve_method(definition, boolean)

        wrong_unit = copy.deepcopy(boolean)
        wrong_unit["values"][0] = {
            "parameter_id": "integer_parameter",
            "value": 1,
            "unit": "um2",
        }
        with self.assertRaisesRegex(ContractError, "wrong unit"):
            resolve_method(definition, wrong_unit)

        below_minimum = copy.deepcopy(wrong_unit)
        below_minimum["values"][0] = {
            "parameter_id": "integer_parameter",
            "value": -1,
            "unit": "count",
        }
        with self.assertRaisesRegex(ContractError, "violates minimum"):
            resolve_method(definition, below_minimum)

        above_maximum = copy.deepcopy(wrong_unit)
        above_maximum["values"][0] = {
            "parameter_id": "integer_parameter",
            "value": 11,
            "unit": "count",
        }
        with self.assertRaisesRegex(ContractError, "violates maximum"):
            resolve_method(definition, above_maximum)

    def test_parameter_allowed_values_are_closed_and_enforced(self):
        definition = copy.deepcopy(self.definition)
        definition["parameter_slots"] = [
            {
                "parameter_id": "summary_mode",
                "value_type": "string",
                "unit": "category",
                "constraints": {
                    "minimum": None,
                    "maximum": None,
                    "allowed_values": ["mean", "median"],
                },
            }
        ]
        definition["features"][0]["parameter_ids"] = ["summary_mode"]
        definition_hash = definition_sha256(definition)
        parameters = copy.deepcopy(self.parameter_set)
        parameters["measurement_definition"]["canonical_sha256"] = definition_hash
        parameters["values"] = [
            {"parameter_id": "summary_mode", "value": "maximum", "unit": "category"}
        ]
        with self.assertRaisesRegex(ContractError, "not an allowed value"):
            resolve_method(definition, parameters)

    def test_scope_binding_and_profile_hash_are_coherent(self):
        unattested_with_hash = copy.deepcopy(self.parameter_set)
        unattested_with_hash["scope"]["scope_profile_sha256"] = "0" * 64
        with self.assertRaisesRegex(ContractError, "unattested scope"):
            validate_parameter_set(unattested_with_hash)

        addressed_without_hash = copy.deepcopy(self.parameter_set)
        addressed_without_hash["scope"]["binding"] = "content_addressed"
        with self.assertRaisesRegex(ContractError, "lowercase SHA-256"):
            validate_parameter_set(addressed_without_hash)

    def test_loaded_documents_are_deeply_immutable(self):
        loaded_definition = load_measurement_definition(DEFINITION_PATH)
        loaded_parameters = load_parameter_set(PARAMETER_SET_PATH)
        with self.assertRaises(TypeError):
            loaded_definition.document["definition_id"] = "changed"
        with self.assertRaises(TypeError):
            loaded_parameters.document["scope"]["scope_id"] = "changed"


if __name__ == "__main__":
    unittest.main()
