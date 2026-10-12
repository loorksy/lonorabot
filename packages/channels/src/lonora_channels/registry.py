from .base import ChannelManifest
from .telegram.manifest import MANIFEST as TELEGRAM
from .webhook.manifest import MANIFEST as WEBHOOK
from .websocket.manifest import MANIFEST as WEBSOCKET


def manifests() -> list[ChannelManifest]:
    return [TELEGRAM, WEBSOCKET, WEBHOOK]
