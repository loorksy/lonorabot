"""Operator declarations or the owner's reviewed trust, never remote annotations,
authorize MCP calls; a tool that can trade or move money is never trusted."""

import hashlib
import json
import re
from dataclasses import dataclass
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
# money moves only through Lonora's one executor. The check fails closed: a name word,
# a money word next to a sending verb, a description phrase or an input schema shaped
# like a transfer (an amount with a recipient, or a key or seed) is enough to block it.
# Names are split into words (snake_case, kebab-case, camelCase).
FINANCIAL_WORDS = frozenset(
    {
        # Trading and brokerage.
        "buy",
        "sell",
        "order",
        "orders",
        "trade",
        "trades",
        "trading",
        "position",
        "positions",
        "broker",
        "brokerage",
        "margin",
        "leverage",
        "liquidate",
        "forex",
        # Broker platforms and trading terms that only mean money here.
        "mt4",
        "mt5",
        "metatrader",
        "ctrader",
        "metaapi",
        "oanda",
        "ibkr",
        "alpaca",
        "binance",
        "bybit",
        "kraken",
        "coinbase",
        "bitmex",
        "okx",
        "deribit",
        "fxcm",
        "exness",
        "stoploss",
        "takeprofit",
        "hedge",
        "hedging",
        "lot",
        "lots",
        # Payments and transfers.
        "withdraw",
        "withdrawal",
        "deposit",
        "transfer",
        "payment",
        "payments",
        "pay",
        "payout",
        "cashout",
        "checkout",
        "purchase",
        "refund",
        "charge",
        "invoice",
        "remit",
        "donate",
        "funds",
        "currency",
        "currencies",
        "usd",
        "eur",
        "gbp",
        # Crypto assets, wallets and on-chain transactions.
        "wallet",
        "crypto",
        "stablecoin",
        "stablecoins",
        "eth",
        "ether",
        "ethereum",
        "btc",
        "bitcoin",
        "usdc",
        "usdt",
        "sol",
        "solana",
        "sats",
        "satoshi",
        "satoshis",
        "lnurl",
        "utxo",
        "transaction",
        "transactions",
        "transact",
        "tx",
        "txn",
        "sign",
        "mint",
        "swap",
        "bridge",
        "stake",
        "unstake",
        "spender",
        "allowance",
        "zap",
        "zaps",
        "lend",
        "borrow",
        "repay",
        "loan",
        "redeem",
        # Betting.
        "bet",
        "bets",
        "wager",
        "gamble",
    }
)
# Words that move money only next to a sending verb or an amount: "send_tokens",
# "tip_user(amount)", "approve(spender, amount)"; "count_tokens" or "approve_review" pass.
MONEY_CONTEXT_WORDS = frozenset(
    {
        "token",
        "tokens",
        "coin",
        "coins",
        "cash",
        "lightning",
        "tip",
        "approve",
        "spend",
        "fund",
        "bid",
        "exchange",
        "convert",
    }
)
SENDING_VERBS = frozenset({"send", "give", "move", "submit", "place", "broadcast"})
# Trading terms that move money next to an acting verb: "open_long", "go_short",
# "modify_sl", "set_exposure"; "long_description" or "shorten_url" pass.
TRADE_CONTEXT_WORDS = frozenset({"long", "short", "sl", "tp", "exposure", "trailing"})
ACTING_VERBS = frozenset(
    {
        "open",
        "close",
        "go",
        "enter",
        "exit",
        "modify",
        "set",
        "move",
        "adjust",
        "change",
        "update",
        "clear",
        "remove",
        "increase",
        "reduce",
        "flatten",
        "add",
        "cancel",
        "execute",
        "place",
        "submit",
        "take",
        "put",
    }
)
# Broker words that mark a description, title or name as trading, in any spelling
# ("MetaTrader", "meta trader", "cTrader", "MT5").
BROKER_PHRASE = re.compile(
    r"\b(?:brokers?|brokerage|forex|meta\s*trader|meta\s*api|c\s*trader|mt\s*[45])\b",
    re.IGNORECASE,
)
BROKER_NAMES = ("metatrader", "metaapi", "ctrader")
# Input fields of a trading shape: an instrument with a size, or a ticket with a stop or
# a target, whatever the tool is called.
INSTRUMENT_WORDS = frozenset({"symbol", "instrument", "ticker", "pair", "epic"})
SIZE_WORDS = frozenset(
    {"lot", "lots", "size", "units", "quantity", "qty", "volume", "contracts", "notional"}
)
TICKET_WORDS = frozenset({"ticket", "deal", "position", "order"})
PROTECTION_WORDS = frozenset({"sl", "tp", "stop", "stoploss", "takeprofit", "trailing"})
ASSETS = (
    r"(?:funds|money|cash|crypto(?:currency|currencies)?|assets|tokens?|coins?|stablecoins?"
    r"|eth|ether|btc|bitcoin|usdc|usdt|sol|sats|satoshis|lightning|payments?)"
)
FINANCIAL_PHRASE = re.compile(
    r"\b(?:place|submit|execute|send|open|close|cancel|modify)\s+(?:an?\s+|the\s+|your\s+)?"
    r"(?:market\s+|limit\s+|stop\s+)?(?:order|trade|position|payment|transfer)s?\b"
    r"|\b(?:transfer|withdraw|deposit|send|move|pay|tip|zap|bridge|swap|spend|lend|borrow)\s+"
    r"(?:up\s+to\s+)?(?:an?\s+|the\s+|your\s+|some\s+|any\s+)?(?:[\d.,]+\s+)?" + ASSETS + r"\b"
    r"|\b(?:sign|broadcast|submit|send)\s+(?:an?\s+|the\s+)?(?:signed\s+|raw\s+)?"
    r"(?:on-?chain\s+)?transactions?\b"
    r"|\b(?:place|make)\s+(?:an?\s+)?(?:bet|wager)s?\b",
    re.IGNORECASE,
)
# Input fields: an amount together with a recipient is a transfer; a key or seed signs one.
AMOUNT_WORDS = frozenset({"amount", "quantity", "qty", "volume", "lots", "wei", "lamports"})
RECIPIENT_WORDS = frozenset(
    {
        "recipient",
        "destination",
        "address",
        "wallet",
        "iban",
        "account",
        "receiver",
        "payee",
        "beneficiary",
        "spender",
    }
)
SECRET_FIELDS = ("privatekey", "secretkey", "seedphrase", "mnemonic", "signingkey")


def word_list(name: str) -> list[str]:
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name)
    return [word for word in re.split(r"[^A-Za-z0-9]+", spaced.casefold()) if word]


def name_words(name: str) -> set[str]:
    return set(word_list(name))


def schema_fields(schema: Any) -> list[str]:
    """Every property name an input schema declares, at any depth (bounded)."""
    fields: list[str] = []
    stack: list[tuple[Any, int]] = [(schema, 0)]
    visited = 0
    while stack and visited < 5000:
        value, depth = stack.pop()
        visited += 1
        if depth > 24:
            continue
        if isinstance(value, dict):
            item = cast(dict[str, Any], value)
            properties = item.get("properties")
            if isinstance(properties, dict):
                fields.extend(str(key) for key in cast(dict[str, Any], properties))
            stack.extend((child, depth + 1) for child in item.values())
        elif isinstance(value, list):
            stack.extend((child, depth + 1) for child in cast(list[Any], value))
    return fields


def transfer_shaped(schema: Any) -> tuple[bool, bool]:
    """(an amount field, a transfer or signing shape) of an input schema."""
    amount = recipient = False
    for field in schema_fields(schema):
        ordered = word_list(field)
        words, flat = set(ordered), "".join(ordered)
        if any(secret in flat for secret in SECRET_FIELDS) or flat == "seed":
            return True, True
        amount = amount or bool(words & AMOUNT_WORDS) or flat == "value"
        recipient = recipient or bool(words & RECIPIENT_WORDS) or flat == "to"
    return amount, amount and recipient


def trading_shaped(schema: Any) -> bool:
    """Whether an input schema looks like an order or a position change: an instrument
    with a size, or a ticket with a stop or a target."""
    words: set[str] = set()
    for field in schema_fields(schema):
        ordered = word_list(field)
        words.update(ordered)
        words.add("".join(ordered))
    return bool(
        (words & INSTRUMENT_WORDS and words & SIZE_WORDS)
        or (words & TICKET_WORDS and words & PROTECTION_WORDS)
    )


def financial_tool(item: dict[str, Any]) -> bool:
    """Whether an advertised tool could trade or move money (then it is never trusted)."""
    name = item.get("name")
    if not isinstance(name, str):
        return True
    words = name_words(name)
    amount, transfer = transfer_shaped(item.get("inputSchema"))
    if (
        any(broker in "".join(word_list(name)) for broker in BROKER_NAMES)
        or words & FINANCIAL_WORDS
        or transfer
        or trading_shaped(item.get("inputSchema"))
        or (words & MONEY_CONTEXT_WORDS and (words & SENDING_VERBS or amount))
        or (words & TRADE_CONTEXT_WORDS and words & ACTING_VERBS)
    ):
        return True
    annotations = item.get("annotations")
    titles = [item.get("title"), item.get("description")]
    if isinstance(annotations, dict):
        titles.append(cast(dict[str, Any], annotations).get("title"))
    return any(
        isinstance(value, str) and (FINANCIAL_PHRASE.search(value) or BROKER_PHRASE.search(value))
        for value in titles
    )


def marked_read_only(item: dict[str, Any]) -> bool:
    """The server says this tool only reads (MCP ``readOnlyHint``). It decides nothing
    alone: it can keep a tool to the read tier, never widen what the owner trusted."""
    annotations = item.get("annotations")
    return (
        isinstance(annotations, dict)
        and cast(dict[str, Any], annotations).get("readOnlyHint") is True
    )


def review_digest(
    endpoint: str, tools: dict[str, str], blocked: list[str], read_only: list[str]
) -> str:
    """One fingerprint of a review: the endpoint, each trusted schema, the tools the server
    marks read-only and the blocked names."""
    value = json.dumps(
        {
            "endpoint": endpoint,
            "tools": dict(sorted(tools.items())),
            "read_only": sorted(read_only),
            "blocked": sorted(blocked),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(value.encode()).hexdigest()


# Names a card can show and an execution can match exactly (the MCP naming convention).
SAFE_TOOL_NAME = re.compile(r"^[A-Za-z0-9_.\-/]{1,128}$")


@dataclass(frozen=True)
class ToolReview:
    """What a review may trust: {name: input schema sha256} of the tools that cannot move
    money and have a supported schema, which of those the server marks read-only (the only
    ones the read tier runs), the names that can move money (blocked, shown as such) and
    how many others were left out (an unsupported name or schema)."""

    tools: dict[str, str]
    read_only: list[str]
    blocked: list[str]
    unsupported: int

    @property
    def writes(self) -> list[str]:
        """Trusted tools that may change something: they run only at the write tier."""
        return sorted(set(self.tools) - set(self.read_only))


def review_tools(advertised: list[dict[str, Any]]) -> ToolReview:
    trusted: dict[str, str] = {}
    read_only: list[str] = []
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
        if marked_read_only(item):
            read_only.append(name)
    return ToolReview(trusted, sorted(read_only), sorted(blocked), unsupported)
