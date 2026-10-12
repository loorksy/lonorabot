import logging
from typing import Any, cast

from lonora_security.secrets import redact


class RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message: Any = record.msg
        if isinstance(message, dict):
            record.msg = redact(cast(dict[str, Any], message))
        return True
