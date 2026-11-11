from typing import Any


class LonoraError(Exception):
    def __init__(
        self,
        code: str,
        status: int = 400,
        *,
        diagnostic_message: str | None = None,
        diagnostic_type: str | None = None,
    ):
        super().__init__(code)
        self.code = code
        self.status = status
        self.diagnostic_message = diagnostic_message
        self.diagnostic_type = diagnostic_type


class ToolRefusal(LonoraError):
    """A refusal a tool writes for the model to act on.

    ``details`` are fields of the tool error contract (``class``, ``retryable``, ``hint``,
    ``candidates``, ``next_actions`` and facts the hint refers to). They are authored
    text and the account's own data, never exception text.
    """

    def __init__(self, code: str, status: int = 400, *, details: dict[str, Any] | None = None):
        super().__init__(code, status)
        self.details: dict[str, Any] = dict(details or {})
