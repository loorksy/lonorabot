from lonora_api.env import Settings
from lonora_db.client import Database
from lonora_gateway.service import Gateway


def create_gateway(settings: Settings) -> tuple[Database, Gateway]:
    db = Database.connect(settings.database_url)
    gateway = Gateway(
        db,
        settings.encryption_key.get_secret_value(),
        settings.artifact_root,
        settings.run_lease_seconds,
        settings.maximum_tool_rounds,
        settings.maximum_subagents,
        settings.worker_poll_seconds,
        voice_configuration={
            "url": settings.livekit_internal_url,
            "key": settings.livekit_api_key or "",
            "secret": settings.livekit_api_secret.get_secret_value()
            if settings.livekit_api_secret
            else "",
        },
    )
    return db, gateway
