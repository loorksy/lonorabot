"""Light agent goals (Q41) and knowledge links (Q40): owner resources of one agent."""

from fastapi import APIRouter
from lonora_db.agent_goals import AgentGoalRepository, KnowledgeLinkRepository

from . import resource_router

router = APIRouter()
router.include_router(resource_router("/agent-goals", AgentGoalRepository()))
router.include_router(resource_router("/knowledge-links", KnowledgeLinkRepository()))
