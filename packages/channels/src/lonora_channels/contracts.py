from lonora_contracts.domain import Contract
from pydantic import Field


class IncomingMessage(Contract):
    external_id: str
    destination: str
    content: str = Field(min_length=1, max_length=30000)
    thread_id: str
