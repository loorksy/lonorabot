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
