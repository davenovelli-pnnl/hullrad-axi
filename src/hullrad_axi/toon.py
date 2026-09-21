from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from decimal import Decimal

_SAFE_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")
_NUMERIC_LIKE = re.compile(r"^[+-]?[0-9]+(?:\.[0-9]+)?(?:e[+-]?[0-9]+)?$", re.IGNORECASE)


def _escape(value: str) -> str:
    out: list[str] = []
    for char in value:
        code = ord(char)
        if char == "\\":
            out.append("\\\\")
        elif char == '"':
            out.append('\\"')
        elif char == "\n":
            out.append("\\n")
        elif char == "\r":
            out.append("\\r")
        elif char == "\t":
            out.append("\\t")
        elif code < 0x20:
            out.append(f"\\u{code:04x}")
        else:
            out.append(char)
    return "".join(out)


def _string(value: str, delimiter: str = ",") -> str:
    quote = (
        not value
        or value != value.strip(" \t")
        or value in {"true", "false", "null", "-", "#"}
        or value.startswith(("-", "#"))
        or bool(_NUMERIC_LIKE.fullmatch(value))
        or any(c in value for c in ':"\\[]{}')
        or delimiter in value
        or any(ord(c) < 0x20 for c in value)
    )
    return f'"{_escape(value)}"' if quote else value


def _key(value: str) -> str:
    return value if _SAFE_KEY.fullmatch(value) else f'"{_escape(value)}"'


def _number(value: float) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if not math.isfinite(value):
        return "null"
    if value == 0:
        return "0"
    magnitude = abs(value)
    if 1e-6 <= magnitude < 1e21:
        token = format(Decimal(str(value)), "f")
        return token.rstrip("0").rstrip(".") if "." in token else token
    mantissa, exponent = format(Decimal(str(value)).normalize(), "e").split("e")
    mantissa = mantissa.rstrip("0").rstrip(".")
    sign = "+" if int(exponent) >= 0 else "-"
    return f"{mantissa}e{sign}{abs(int(exponent))}"


def _primitive(value: object, delimiter: str = ",") -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return _number(value)
    return _string(str(value), delimiter)


def _is_primitive(value: object) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _encode_object(value: Mapping[str, object], depth: int, lines: list[str]) -> None:
    indent = "  " * depth
    for raw_key, item in value.items():
        key = _key(str(raw_key))
        if _is_primitive(item):
            lines.append(f"{indent}{key}: {_primitive(item)}")
        elif isinstance(item, Mapping):
            lines.append(f"{indent}{key}:")
            _encode_object(item, depth + 1, lines)
        elif isinstance(item, Sequence) and not isinstance(item, (str, bytes)):
            seq = list(item)
            if not seq:
                lines.append(f"{indent}{key}: []")
            elif all(_is_primitive(v) for v in seq):
                cells = ",".join(_primitive(v) for v in seq)
                lines.append(f"{indent}{key}[{len(seq)}]: {cells}")
            elif all(isinstance(v, Mapping) for v in seq):
                fields = list(seq[0].keys())
                if not fields or any(list(v.keys()) != fields for v in seq) or any(
                    not _is_primitive(v[field]) for v in seq for field in fields
                ):
                    raise TypeError("TOON encoder only supports uniform primitive object rows")
                header = ",".join(_key(str(field)) for field in fields)
                lines.append(f"{indent}{key}[{len(seq)}]{{{header}}}:")
                for row in seq:
                    cells = ",".join(_primitive(row[field]) for field in fields)
                    lines.append(f"{indent}  {cells}")
            else:
                raise TypeError("TOON encoder received an unsupported array shape")
        else:
            raise TypeError(f"TOON encoder received unsupported type: {type(item)!r}")


def dumps(value: Mapping[str, object]) -> str:
    lines: list[str] = []
    _encode_object(value, 0, lines)
    return "\n".join(lines)
