from dataclasses import dataclass, field

from lonora_charts.visual import ChartVisualRuntime
from lonora_db.client import Database
from lonora_gateway.runtime import OwnerServices

from .env import Settings


@dataclass
class ApiRuntime:
    settings: Settings
    db: Database
    owners: dict[str, OwnerServices] = field(default_factory=dict[str, OwnerServices])

    @classmethod
    def create(cls, settings: Settings) -> "ApiRuntime":
        return cls(settings, Database.connect(settings.database_url))

    def services(self, owner_id: str) -> OwnerServices:
        if owner_id not in self.owners:
            self.owners[owner_id] = OwnerServices.create(
                self.db,
                owner_id,
                self.settings.encryption_key.get_secret_value(),
                chart_visual=ChartVisualRuntime(
                    self.settings.chart_renderer_url,
                    str(self.settings.chart_browser_executable)
                    if self.settings.chart_browser_executable
                    else None,
                    chromium_sandbox=self.settings.chart_browser_sandbox,
                )
                if self.settings.chart_renderer_url
                else None,
            )
        return self.owners[owner_id]

    async def close(self) -> None:
        for services in self.owners.values():
            await services.close()
        await self.db.close()
