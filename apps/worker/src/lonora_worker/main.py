import asyncio

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
        await gateway.serve()
    finally:
        await db.close()


def main() -> None:
    asyncio.run(serve())


if __name__ == "__main__":
    main()
