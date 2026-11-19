"""The broker endpoints the execution door uses, named in one place.

The MetaApi SDK may talk only to hosts under `METAAPI_SDK_DOMAIN`; the workspace may reach
none of `BROKER_DOMAINS` (7.1.4). Hosts under these domains are discovered at run time
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


def under(host: str, domain: str) -> bool:
    name = host.lower().rstrip(".")
    return name == domain or name.endswith("." + domain)
