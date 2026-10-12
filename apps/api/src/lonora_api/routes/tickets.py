from lonora_db.tickets import TicketRepository

from . import resource_router

router = resource_router("/tickets", TicketRepository())
