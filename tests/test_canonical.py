import json
import math
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
    load_strict_json,
    parse_strict_json,
)


class CanonicalJsonTests(unittest.TestCase):
    def test_object_order_formatting_and_integral_float_share_identity(self):
        first = {"schema_version": "1.0.0", "nested": {"b": 2.0, "a": [True, None]}}
        second = {"nested": {"a": [True, None], "b": 2}, "schema_version": "1.0.0"}
        self.assertEqual(canonical_json_bytes(first), canonical_json_bytes(second))
        self.assertEqual(canonical_sha256(first), canonical_sha256(second))

    def test_array_order_remains_semantic(self):
        self.assertNotEqual(canonical_sha256({"items": [1, 2]}), canonical_sha256({"items": [2, 1]}))

    def test_unicode_controls_and_small_numbers_have_one_cross_runtime_form(self):
        value = {
            "z": "한글",
            "a": "ä\n\"\\",
            "small": 1e-7,
            "less_small": 1e-5,
        }
        self.assertEqual(
            canonical_json_bytes(value),
            '{"a":"ä\\n\\"\\\\","less_small":0.00001,"small":0.0000001,"z":"한글"}'.encode(
                "utf-8"
            ),
        )

    def test_unpaired_unicode_surrogates_are_rejected(self):
        with self.assertRaisesRegex(ContractError, "unpaired surrogate"):
            canonical_json_bytes({"value": "\ud800"})

    def test_committed_cross_runtime_golden_vectors(self):
        vectors = load_strict_json(ROOT / "contracts" / "canonicalization-vectors.json")
        for vector in vectors["vectors"]:
            with self.subTest(vector=vector["name"]):
                self.assertEqual(
                    canonical_json_bytes(vector["value"]),
                    vector["canonical_utf8"].encode("utf-8"),
                )
                self.assertEqual(canonical_sha256(vector["value"]), vector["sha256"])

    def test_duplicate_keys_are_rejected_before_validation(self):
        with self.assertRaisesRegex(ContractError, "duplicate JSON key"):
            parse_strict_json(b'{"value":1,"value":2}')

    def test_lexical_and_in_memory_negative_zero_are_rejected(self):
        with self.assertRaisesRegex(ContractError, "negative zero"):
            parse_strict_json(b'{"value":-0.0}')
        with self.assertRaisesRegex(ContractError, "negative zero"):
            canonical_json_bytes({"value": -0.0})

    def test_nonfinite_underflow_and_unsafe_numbers_are_rejected(self):
        for payload in (b'{"value":NaN}', b'{"value":Infinity}', b'{"value":1e-400}'):
            with self.subTest(payload=payload):
                with self.assertRaises(ContractError):
                    parse_strict_json(payload)
        for value in (math.inf, math.nan, 2**54):
            with self.subTest(value=value):
                with self.assertRaises(ContractError):
                    canonical_json_bytes({"value": value})

    def test_raw_file_format_can_differ_while_canonical_identity_matches(self):
        with tempfile.TemporaryDirectory() as temporary:
            pretty = Path(temporary) / "pretty.json"
            compact = Path(temporary) / "compact.json"
            pretty.write_text(json.dumps({"b": 2, "a": 1}, indent=2), encoding="utf-8")
            compact.write_text('{"a":1,"b":2}', encoding="utf-8")
            self.assertEqual(
                canonical_sha256(load_strict_json(pretty)),
                canonical_sha256(load_strict_json(compact)),
            )
            self.assertNotEqual(pretty.read_bytes(), compact.read_bytes())


if __name__ == "__main__":
    unittest.main()
