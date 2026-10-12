from lonora_db.boards import BoardRepository

from . import resource_router

router = resource_router("/boards", BoardRepository())
