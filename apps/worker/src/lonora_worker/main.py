import asyncio

from lonora_adapter_kit.tokenization import cached_encoding
from lonora_api.env import get_settings
from lonora_logging.logger import configure_logging

from .runtime import create_gateway
from .signals import install_signals


async def serve() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    db, gateway = create_gateway(settings)
    install_signals(gateway.request_stop)
    try:
        # These only read hash-verified setup caches. Pay cold encoding setup
        # before readiness, never in the owner's first conversational request.
        for encoding in ("cl100k_base", "o200k_base"):
            await asyncio.to_thread(cached_encoding, encoding)
        await gateway.serve()
    finally:
        await db.close()


def main() -> None:
    asyncio.run(serve())


if __name__ == "__main__":
    main()
