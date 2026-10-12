import json
import logging

from lonora_security.secrets import redact

from .context import request_id, run_id


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname,
            "logger": record.name,
            "message": redact(record.getMessage()),
            "request_id": request_id.get(),
            "run_id": run_id.get(),
        }
        return json.dumps(payload, ensure_ascii=False)
