"""Strict JSON loading, canonicalization, and content identities.

The canonical form is repository-owned UTF-8 JSON with sorted object keys,
compact separators, direct Unicode, and exponent-free binary64 numbers. It is
intentionally narrow so the same semantic document cannot acquire multiple
identities through formatting, object order, integral-float spelling, runtime
Unicode escaping, or non-portable numeric forms.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any

SAFE_JSON_INTEGER = (1 << 53) - 1


class ContractError(ValueError):
    """Raised when a contract or canonical artifact fails closed validation."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ContractError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _parse_integer(token: str) -> int:
    if token == "-0":
        raise ContractError("lexical negative zero is not canonical")
    try:
        value = int(token)
    except (ValueError, OverflowError) as exc:
        raise ContractError("unreadable JSON integer") from exc
    if abs(value) > SAFE_JSON_INTEGER:
        raise ContractError("JSON integer exceeds the interoperable safe range")
    return value


def _parse_float(token: str) -> float:
    try:
        value = float(token)
    except (ValueError, OverflowError) as exc:
        raise ContractError("unreadable JSON number") from exc
    if not math.isfinite(value):
        raise ContractError("non-finite JSON number is not permitted")
    mantissa = token.lower().split("e", 1)[0].lstrip("+-")
    if value == 0 and any(character in "123456789" for character in mantissa):
        raise ContractError("JSON number underflows binary64")
    if value == 0 and token.startswith("-"):
        raise ContractError("lexical negative zero is not canonical")
    if abs(value) > SAFE_JSON_INTEGER:
        raise ContractError("JSON number exceeds the interoperable safe range")
    return value


def _reject_nonfinite(token: str) -> None:
    raise ContractError(f"non-JSON numeric constant {token!r}")


def parse_strict_json(payload: bytes, *, source: str = "<bytes>") -> Any:
    """Parse UTF-8 JSON while rejecting duplicate keys and unsafe numbers."""

    try:
        text = payload.decode("utf-8-sig")
    except UnicodeError as exc:
        raise ContractError(f"{source}: content is not UTF-8") from exc
    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_int=_parse_integer,
            parse_float=_parse_float,
            parse_constant=_reject_nonfinite,
        )
    except json.JSONDecodeError as exc:
        raise ContractError(f"{source}: invalid JSON: {exc.msg}") from exc


def load_strict_json(path: str | Path) -> Any:
    source = Path(path)
    try:
        payload = source.read_bytes()
    except OSError as exc:
        raise ContractError(f"cannot read {source}: {exc}") from exc
    return parse_strict_json(payload, source=str(source))


def normalize_canonical(value: Any, *, location: str = "$") -> Any:
    """Normalize values into the platform's canonical JSON value domain."""

    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise ContractError(f"{location}: object keys must be strings")
        return {
            key: normalize_canonical(child, location=f"{location}.{key}")
            for key, child in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [
            normalize_canonical(child, location=f"{location}[{index}]")
            for index, child in enumerate(value)
        ]
    if isinstance(value, str):
        if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
            raise ContractError(f"{location}: string contains an unpaired surrogate")
        return value
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        if abs(value) > SAFE_JSON_INTEGER:
            raise ContractError(f"{location}: integer exceeds the interoperable safe range")
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ContractError(f"{location}: number must be finite")
        if value == 0 and math.copysign(1.0, value) < 0:
            raise ContractError(f"{location}: negative zero is not canonical")
        if abs(value) > SAFE_JSON_INTEGER:
            raise ContractError(f"{location}: number exceeds the interoperable safe range")
        return int(value) if value.is_integer() else value
    raise ContractError(f"{location}: unsupported canonical JSON type {type(value).__name__}")


def _plain_float(value: float) -> str:
    """Return exponent-free binary64 text shared with the Groovy exporter."""

    decimal = Decimal(str(value))
    text = format(decimal, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"-0", ""} else text


def _canonical_text(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False, allow_nan=False)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return _plain_float(value)
    if isinstance(value, Mapping):
        return "{" + ",".join(
            f"{json.dumps(key, ensure_ascii=False, allow_nan=False)}:{_canonical_text(value[key])}"
            for key in sorted(value)
        ) + "}"
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return "[" + ",".join(_canonical_text(child) for child in value) + "]"
    raise ContractError(f"cannot canonicalize JSON type {type(value).__name__}")


def canonical_json_bytes(value: Any) -> bytes:
    normalized = normalize_canonical(value)
    try:
        text = _canonical_text(normalized)
        return text.encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ContractError(f"cannot canonicalize JSON: {exc}") from exc


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    source = Path(path)
    try:
        with source.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise ContractError(f"cannot hash {source}: {exc}") from exc
    return digest.hexdigest()
