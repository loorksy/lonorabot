from lonora_contracts.domain import Ticket

from .schema import TicketRow
from .transactions import ResourceRepository


class TicketRepository(ResourceRepository):
    """Transactional, owner-scoped persistence for tickets."""

    row_type = TicketRow
    kind = "tickets"
    payload_model = Ticket
