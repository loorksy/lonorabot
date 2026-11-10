"""The broker provider catalog the connection form renders from.

Each field ``name`` is the key of ``POST /trading/connections``. Entries carry no
owner-visible text; clients label providers and fields in their own catalogs.
"""

from typing import Any

PROVIDERS: tuple[dict[str, Any], ...] = (
    {
        "provider": "alpaca",
        "environment": "paper",
        # Live trading is refused: the adapter reaches only Alpaca's paper host.
        "live_trading": False,
        "markets": ["us_equity", "crypto"],
        "fields": [
            {
                "name": "key_id",
                "kind": "text",
                "required": True,
                "secret": True,
                "direction": "ltr",
            },
            {
                "name": "secret_key",
                "kind": "password",
                "required": True,
                "secret": True,
                "direction": "ltr",
            },
        ],
    },
    {
        "provider": "metaapi",
        "environment": "live",
        "live_trading": True,
        "markets": [],
        "fields": [
            {
                "name": "api_key",
                "kind": "password",
                "required": True,
                "secret": True,
                "direction": "ltr",
            },
            {
                "name": "account_id",
                "kind": "text",
                "required": True,
                "secret": False,
                "direction": "ltr",
            },
            {
                "name": "region",
                "kind": "text",
                "required": False,
                "secret": False,
                "direction": "ltr",
            },
        ],
    },
    {
        "provider": "simulation",
        "environment": "simulation",
        "live_trading": False,
        "markets": [],
        "fields": [
            {
                "name": "account_id",
                "kind": "text",
                "required": True,
                "secret": False,
                "direction": "ltr",
            },
        ],
    },
)


def provider_catalog() -> list[dict[str, Any]]:
    return [{**entry, "fields": [dict(field) for field in entry["fields"]]} for entry in PROVIDERS]
