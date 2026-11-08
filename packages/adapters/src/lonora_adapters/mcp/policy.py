"""Operator declarations or the owner's reviewed trust, never remote annotations,
authorize MCP calls; a tool that can trade or move money is never trusted."""

import hashlib
import json
import re
from typing import Any, cast

from jsonschema import Draft202012Validator, validate
from jsonschema.exceptions import SchemaError, ValidationError
from lonora_contracts.mcp import McpToolDeclaration
from lonora_core.user_error import LonoraError
from lonora_security.network import endpoint_sha256 as endpoint_sha256

MAX_SCHEMA_BYTES = 64 * 1024
MAX_ARGUMENT_BYTES = 128 * 1024


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
    return pinned_schema(declaration.input_schema_sha256, advertised)


def advertised_schema_sha256(advertised: dict[str, Any]) -> str:
    schema = advertised.get("inputSchema")
    if not isinstance(schema, dict):
        raise LonoraError("mcp_schema_invalid", 422)
    return schema_sha256(cast(dict[str, Any], schema))


def pinned_schema(expected_sha256: str, advertised: dict[str, Any]) -> Draft202012Validator:
    """The advertised input schema, only while it is exactly the reviewed one."""
    if advertised_schema_sha256(advertised) != expected_sha256:
        raise LonoraError("mcp_schema_changed", 409)
    return validate_schema(cast(dict[str, Any], advertised["inputSchema"]))


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


# A tool that can trade or move money is never trusted, whatever its server or tier says:
# money moves only through Lonora's one executor. Names are split into words
# (snake_case, kebab-case, camelCase); descriptions are checked for explicit phrases.
FINANCIAL_WORDS = frozenset(
    {
        "buy",
        "sell",
        "order",
        "orders",
        "trade",
        "trades",
        "trading",
        "position",
        "positions",
        "withdraw",
        "withdrawal",
        "deposit",
        "transfer",
        "payment",
        "payments",
        "pay",
        "payout",
        "wallet",
        "swap",
        "stake",
        "unstake",
        "checkout",
        "purchase",
        "refund",
        "charge",
        "invoice",
        "broker",
        "brokerage",
        "margin",
        "leverage",
        "liquidate",
        "funds",
    }
)
FINANCIAL_PHRASE = re.compile(
    r"\b(?:place|submit|execute|send|open|close|cancel|modify)\s+(?:an?\s+|the\s+|your\s+)?"
    r"(?:market\s+|limit\s+|stop\s+)?(?:order|trade|position|payment|transfer)s?\b"
    r"|\b(?:transfer|withdraw|deposit|send|move)\s+(?:the\s+|your\s+)?"
    r"(?:funds|money|crypto|assets|tokens|coins)\b",
    re.IGNORECASE,
)


def name_words(name: str) -> set[str]:
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name)
    return {word for word in re.split(r"[^A-Za-z0-9]+", spaced.casefold()) if word}


def financial_tool(item: dict[str, Any]) -> bool:
    """Whether an advertised tool could trade or move money (then it is never trusted)."""
    name = item.get("name")
    if not isinstance(name, str) or name_words(name) & FINANCIAL_WORDS:
        return True
    for key in ("title", "description"):
        value = item.get(key)
        if isinstance(value, str) and (
            FINANCIAL_PHRASE.search(value) or name_words(value) & {"broker", "brokerage"}
        ):
            return True
    return False


def review_digest(endpoint: str, tools: dict[str, str], blocked: list[str]) -> str:
    """One fingerprint of a review: the endpoint, each trusted schema and the blocked names."""
    value = json.dumps(
        {"endpoint": endpoint, "tools": dict(sorted(tools.items())), "blocked": sorted(blocked)},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(value.encode()).hexdigest()


# Names a card can show and an execution can match exactly (the MCP naming convention).
SAFE_TOOL_NAME = re.compile(r"^[A-Za-z0-9_.\-/]{1,128}$")


def review_tools(advertised: list[dict[str, Any]]) -> tuple[dict[str, str], list[str], int]:
    """What a review may trust: {name: input schema sha256} of the tools that cannot
    move money and have a supported schema, the names that can (blocked, shown as such)
    and how many others were left out (an unsupported name or schema)."""
    trusted: dict[str, str] = {}
    blocked: list[str] = []
    unsupported = 0
    for item in advertised:
        name = item.get("name")
        if not isinstance(name, str) or not SAFE_TOOL_NAME.match(name):
            unsupported += 1
            continue
        if financial_tool(item):
            blocked.append(name)
            continue
        try:
            digest = advertised_schema_sha256(item)
            validate_schema(cast(dict[str, Any], item["inputSchema"]))
        except LonoraError:
            unsupported += 1
            continue
        trusted[name] = digest
    return trusted, sorted(blocked), unsupported
