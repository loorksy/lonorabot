from lonora_contracts.chart import ChartState
from lonora_db.client import Database
from lonora_db.cloud_charts import CloudChartRepository


async def load_chart_state(db: Database, owner_id: str, chart_id: str) -> ChartState:
    async with db.sessions() as session:
        row = await CloudChartRepository().get(session, owner_id, chart_id)
        return ChartState.model_validate(row.payload)
