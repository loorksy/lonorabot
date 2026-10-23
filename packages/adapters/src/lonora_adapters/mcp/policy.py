"""Operator declarations, never remote annotations, authorize MCP research calls."""

import hashlib
import json
from typing import Any, cast
from urllib.parse import urlsplit, urlunsplit

from jsonschema import Draft202012Validator, validate
from jsonschema.exceptions import SchemaError, ValidationError
from lonora_contracts.mcp import McpToolDeclaration
from lonora_core.user_error import LonoraError

MAX_SCHEMA_BYTES = 64 * 1024
MAX_ARGUMENT_BYTES = 128 * 1024


def endpoint_sha256(url: str) -> str:
    """Fingerprint the exact HTTPS resource, normalizing only origin spelling."""
    try:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
            or parsed.port not in {None, 443}
            or any(ord(char) < 33 for char in url)
        ):
            raise ValueError("unsafe endpoint")
        host = parsed.hostname.lower()
        if ":" in host:
            host = "[" + host + "]"
        canonical = urlunsplit(("https", host, parsed.path or "/", parsed.query, ""))
    except ValueError:
        raise LonoraError("unsafe_remote_url", 422) from None
    return hashlib.sha256(canonical.encode()).hexdigest()


def schema_sha256(schema: dict[str, Any]) -> str:
    try:
        value = json.dumps(
            schema, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
    except (TypeError, ValueError, RecursionError):
        raise LonoraError("mcp_schema_invalid", 422) from None
    if len(value) > MAX_SCHEMA_BYTES:
        raise LonoraError("mcp_schema_too_large", 422)
    return hashlib.sha256(value).hexdigest()


def declaration_for(
    declarations: tuple[McpToolDeclaration, ...],
    *,
    owner_id: str,
    connection_id: str,
    url: str,
    tool_name: str,
) -> McpToolDeclaration:
    fingerprint = endpoint_sha256(url)
    matches = [
        declaration
        for declaration in declarations
        if declaration.owner_id == owner_id
        and declaration.connection_id == connection_id
        and declaration.endpoint_sha256 == fingerprint
        and declaration.tool_name == tool_name
        and declaration.effect == "read_only"
        and declaration.credential_scope == "integration"
    ]
    if len(matches) != 1:
        raise LonoraError("mcp_tool_not_authorized", 403)
    return matches[0]


def validate_schema(schema: dict[str, Any]) -> Draft202012Validator:
    # All references are currently unsupported. This deliberately avoids implicit
    # network resolution and recursive local schemas until explicitly supported.
    schema_sha256(schema)
    stack: list[tuple[Any, int]] = [(schema, 0)]
    visited = 0
    while stack:
        value, depth = stack.pop()
        visited += 1
        if depth > 24 or visited > 5000:
            raise LonoraError("mcp_schema_too_complex", 422)
        if isinstance(value, dict):
            if any(key in value for key in ("$ref", "$dynamicRef", "$recursiveRef")):
                raise LonoraError("mcp_schema_reference_unsupported", 422)
            stack.extend((item, depth + 1) for item in cast(dict[str, Any], value).values())
        elif isinstance(value, list):
            stack.extend((item, depth + 1) for item in cast(list[Any], value))
    if schema.get("type") != "object" or schema.get("$schema") not in {
        None,
        "https://json-schema.org/draft/2020-12/schema",
    }:
        raise LonoraError("mcp_schema_unsupported", 422)
    try:
        Draft202012Validator.check_schema(schema)
        return Draft202012Validator(schema)
    except (SchemaError, RecursionError):
        raise LonoraError("mcp_schema_invalid", 422) from None


def approved_schema(
    declaration: McpToolDeclaration, advertised: dict[str, Any]
) -> Draft202012Validator:
    schema = advertised.get("inputSchema")
    if not isinstance(schema, dict):
        raise LonoraError("mcp_schema_invalid", 422)
    typed_schema = cast(dict[str, Any], schema)
    if schema_sha256(typed_schema) != declaration.input_schema_sha256:
        raise LonoraError("mcp_schema_changed", 409)
    return validate_schema(typed_schema)


def validate_input(validator: Draft202012Validator, arguments: dict[str, Any]) -> None:
    try:
        serialized = json.dumps(arguments, allow_nan=False).encode()
    except (TypeError, ValueError, RecursionError):
        raise LonoraError("mcp_arguments_invalid", 422) from None
    if len(serialized) > MAX_ARGUMENT_BYTES:
        raise LonoraError("mcp_arguments_too_large", 422)
    try:
        validate(arguments, validator.schema, cls=Draft202012Validator)
    except (ValidationError, RecursionError):
        # Validation messages include submitted values. Only the stable code is
        # safe for persistence, model context and owner-visible diagnostics.
        raise LonoraError("mcp_arguments_invalid", 422) from None
