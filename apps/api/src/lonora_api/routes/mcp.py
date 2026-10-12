from lonora_contracts.mcp import McpConnection
from lonora_db.schema import McpConnectionRow
from lonora_db.transactions import ResourceRepository

from . import resource_router


class McpRepository(ResourceRepository):
    row_type = McpConnectionRow
    payload_model = McpConnection
    kind = "mcp"


router = resource_router("/mcp", McpRepository())
