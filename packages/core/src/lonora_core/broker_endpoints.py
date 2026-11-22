"""The broker endpoints the execution door uses, named in one place.

The MetaApi SDK may talk only to hosts under `METAAPI_SDK_DOMAIN`; the workspace may reach
none of `BROKER_DOMAINS` (7.1.4) and none of `OTHER_VENUE_DOMAINS` (owner Amendment 2). Hosts under these domains are discovered at run time
(regions, instances), so both rules match by suffix. `METAAPI_KNOWN_HOSTS` are resolved
by the workspace network guard so that a program that skips name resolution and dials a
known address is refused as well.
"""

METAAPI_SDK_DOMAIN = "agiliumtrade.ai"
BROKER_DOMAINS = (METAAPI_SDK_DOMAIN, "metaapi.cloud")
METAAPI_REGIONS = ("new-york", "london", "singapore", "vint-hill")
METAAPI_KNOWN_HOSTS = (
    "mt-provisioning-api-v1.agiliumtrade.agiliumtrade.ai",
    "profile-api-v1.agiliumtrade.agiliumtrade.ai",
    *(
        f"{api}.{region}{instance}.{METAAPI_SDK_DOMAIN}"
        for api in ("mt-client-api-v1", "mt-market-data-client-api-v1")
        for region in METAAPI_REGIONS
        for instance in ("", "-a", "-b")
    ),
    "metaapi.cloud",
    "app.metaapi.cloud",
)


# Trading venues other than the MetaTrader accounts behind MetaApi (owner Amendment 2: Lonora
# trades MetaTrader only). The workspace may reach none of these, matched by suffix like
# BROKER_DOMAINS. Defence in depth, not a complete list: the rule itself is the mandate and the
# agent's manual. Crypto venues are listed by domain; brokers that also offer MetaTrader
# accounts or public sites are listed by their trading API hosts only.
OTHER_VENUE_DOMAINS = (
    "binance.com",
    "binance.us",
    "binance.vision",
    "binancefuture.com",
    "bybit.com",
    "bytick.com",
    "okx.com",
    "okex.com",
    "coinbase.com",
    "kraken.com",
    "cryptofacilities.com",
    "kucoin.com",
    "bitget.com",
    "gate.io",
    "gateio.ws",
    "mexc.com",
    "htx.com",
    "huobi.pro",
    "hbdm.com",
    "bitfinex.com",
    "bitstamp.net",
    "gemini.com",
    "crypto.com",
    "deribit.com",
    "bitmex.com",
    "upbit.com",
    "bithumb.com",
    "bingx.com",
    "phemex.com",
    "poloniex.com",
    "bitflyer.com",
    "hyperliquid.xyz",
    "dydx.exchange",
    "dydx.trade",
    "alpaca.markets",
    "interactivebrokers.com",
    "ibkr.com",
    "api-fxtrade.oanda.com",
    "api-fxpractice.oanda.com",
    "stream-fxtrade.oanda.com",
    "stream-fxpractice.oanda.com",
    "api.tradier.com",
    "sandbox.tradier.com",
    "api.schwabapi.com",
    "api.tastyworks.com",
    "api.tastytrade.com",
    "gateway.saxobank.com",
    "api.tradestation.com",
    "api.etrade.com",
    "trading.robinhood.com",
)


def under(host: str, domain: str) -> bool:
    name = host.lower().rstrip(".")
    return name == domain or name.endswith("." + domain)
