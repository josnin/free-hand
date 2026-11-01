"""Validation for the strict Free-hand JSON response protocol."""
import json
from typing import Any

class ProtocolError(ValueError):
    """Raised when a tool-call response violates the protocol."""

def parse_response(raw: str) -> dict[str, Any]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        message = f"Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        if exc.msg == "Invalid \\escape":
            # JSON does not permit escapes such as \*, \d, or \w. A literal
            # backslash must be written as \\ in the JSON source.
            start = max(0, exc.pos - 24)
            end = min(len(raw), exc.pos + 24)
            snippet = raw[start:end].replace("\n", "\\n").replace("\r", "\\r")
            message += (
                ". JSON strings do not support this backslash escape. "
                "If the backslash is intentional, double it (write \\\\ in the JSON text); "
                "otherwise remove it. For example, use \"*\" rather than \"\\*\" "
                "for a wildcard pattern."
                f" Near: {snippet!r}"
            )
        raise ProtocolError(message) from exc
    if not isinstance(data, dict) or set(data) != {"version", "tool_calls", "final_message"}:
        raise ProtocolError("Response must be an object containing exactly version, tool_calls, final_message.")
    if type(data["version"]) is not int or data["version"] != 1:
        raise ProtocolError("version must be the integer 1.")
    if not isinstance(data["tool_calls"], list):
        raise ProtocolError("tool_calls must be an array.")
    if data["final_message"] is not None and not isinstance(data["final_message"], str):
        raise ProtocolError("final_message must be a string or null.")
    seen = set()
    for i, call in enumerate(data["tool_calls"]):
        where = f"tool_calls[{i}]"
        if not isinstance(call, dict) or set(call) != {"id", "type", "function"}:
            raise ProtocolError(f"{where} must contain exactly id, type, function.")
        if not isinstance(call["id"], str) or not call["id"].strip():
            raise ProtocolError(f"{where}.id must be a non-empty string.")
        if call["id"] in seen:
            raise ProtocolError(f"Duplicate tool-call id: {call['id']}")
        seen.add(call["id"])
        if call["type"] != "function":
            raise ProtocolError(f"{where}.type must be 'function'.")
        fn = call["function"]
        if not isinstance(fn, dict) or set(fn) != {"name", "arguments"}:
            raise ProtocolError(f"{where}.function must contain exactly name and arguments.")
        if not isinstance(fn["name"], str) or not fn["name"].strip():
            raise ProtocolError(f"{where}.function.name must be a non-empty string.")
        if not isinstance(fn["arguments"], dict):
            raise ProtocolError(f"{where}.function.arguments must be an object.")
    return data

def clean_response(raw: str) -> str:
    """Extract one valid Free-hand response object without rewriting its JSON.

    Accepts surrounding prose and Markdown code fences. JSON string contents are
    never repaired or unescaped; invalid JSON remains an error.
    """
    candidate_text = raw.lstrip("\ufeff\r\n\t ").rstrip()
    original_error: ProtocolError | None = None
    try:
        parse_response(candidate_text)
        return candidate_text
    except ProtocolError as exc:
        original_error = exc

    decoder = json.JSONDecoder()
    matches: list[str] = []
    for start, char in enumerate(candidate_text):
        if char != "{":
            continue
        # Find this object's end while respecting quoted strings and escapes.
        depth = 0
        in_string = False
        escaped = False
        end = None
        for index in range(start, len(candidate_text)):
            current = candidate_text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif current == "\\":
                    escaped = True
                elif current == '"':
                    in_string = False
                continue
            if current == '"':
                in_string = True
            elif current == "{":
                depth += 1
            elif current == "}":
                depth -= 1
                if depth == 0:
                    end = index + 1
                    break
        if end is None:
            continue
        candidate = candidate_text[start:end]
        try:
            parsed = decoder.decode(candidate)
        except json.JSONDecodeError as exc:
            # If this looks like a Free-hand envelope, surface the precise parser
            # error (especially invalid backslash escapes) instead of masking it.
            if '"version"' in candidate and '"tool_calls"' in candidate and '"final_message"' in candidate:
                parse_response(candidate)
            continue
        if isinstance(parsed, dict) and {"version", "tool_calls", "final_message"}.issubset(parsed):
            parse_response(candidate)
            matches.append(candidate)

    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise ProtocolError(
            "Found multiple Free-hand JSON response objects. Copy only the intended response, "
            "then run `fh run --clipboard` again."
        )

    # Preserve a targeted JSON syntax message for plain malformed JSON.
    if candidate_text.startswith("{"):
        parse_response(candidate_text)
    raise ProtocolError(
        "Could not find a valid Free-hand JSON response. Copy the complete response, "
        "including its JSON object; Markdown fences and surrounding explanatory text are okay."
    ) from original_error

