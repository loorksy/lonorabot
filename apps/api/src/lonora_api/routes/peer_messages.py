from lonora_db.peer_messages import PeerMessageRepository

from . import resource_router

router = resource_router("/peer-messages", PeerMessageRepository())
