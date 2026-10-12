from lonora_db.scratchpad import ScratchpadRepository

from . import resource_router

router = resource_router("/scratchpad", ScratchpadRepository())
