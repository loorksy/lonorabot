from typing import Literal

from pydantic import Field

from .domain import Contract

# The owner's unified search categories (WP-C). «الملفات» are artifacts, «المعرفة»
# is agent memory and semantic notes labelled by agent, «المهارات» the installed skills.
SearchCategory = Literal["chats", "messages", "tasks", "files", "knowledge", "skills"]
SEARCH_CATEGORIES: tuple[SearchCategory, ...] = (
    "chats",
    "messages",
    "tasks",
    "files",
    "knowledge",
    "skills",
)


class SearchQuery(Contract):
    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=30, ge=1, le=100)
