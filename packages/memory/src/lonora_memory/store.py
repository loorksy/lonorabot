from lonora_db.client import Database
from lonora_db.memory import memory_data, read_memory


class MemoryStore:
    def __init__(self, db: Database):
        self.db = db

    async def read(self, owner_id: str, agent_id: str) -> dict[str, object]:
        async with self.db.sessions() as session:
            return memory_data(await read_memory(session, owner_id, agent_id))
