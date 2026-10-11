from pydantic import BaseModel, Field


class AgentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    instructions: str = Field(default="", max_length=8000)


class ThreadCreate(BaseModel):
    title: str = Field(default="Conversation", min_length=1, max_length=160)


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=20000)


class MemoryUpdate(BaseModel):
    content: str = Field(max_length=30000)


class RoutineCreate(BaseModel):
    prompt: str = Field(min_length=1, max_length=8000)
    interval_seconds: int = Field(ge=60, le=31_536_000)
