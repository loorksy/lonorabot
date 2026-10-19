from lonora_api.env import Settings
from lonora_charts.visual import ChartVisualRuntime
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
        chart_visual=ChartVisualRuntime(
            settings.chart_renderer_url,
            str(settings.chart_browser_executable) if settings.chart_browser_executable else None,
            chromium_sandbox=settings.chart_browser_sandbox,
        )
        if settings.chart_renderer_url
        else None,
    )
    return db, gateway
