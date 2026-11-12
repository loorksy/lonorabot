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
        mcp_declarations=settings.mcp_declarations,
        mcp_owner_trust=settings.mcp_owner_trust,
        searxng_url=settings.searxng_url,
        browser_url=settings.browser_url,
        expo_access_token=settings.expo_access_token.get_secret_value()
        if settings.expo_access_token
        else None,
        chart_visual=ChartVisualRuntime(
            settings.chart_renderer_url,
            str(settings.chart_browser_executable) if settings.chart_browser_executable else None,
            chromium_sandbox=settings.chart_browser_sandbox,
        )
        if settings.chart_renderer_url
        else None,
    )
    return db, gateway
