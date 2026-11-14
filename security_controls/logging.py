import json
import logging
from datetime import datetime, timezone


class SafeJSONFormatter(logging.Formatter):
    """Only approved metadata; never serialize messages, request bodies or exceptions."""
    def format(self, record):
        allowed = {"code", "level", "actor_id", "target_id", "ip_fingerprint", "request_id", "route", "event_reference"}
        data = {key: value for key, value in getattr(record, "security_data", {}).items() if key in allowed}
        result = {"timestamp": datetime.now(timezone.utc).isoformat(), "logger": record.name,
                  "level": record.levelname, "code": "application_event", **data}
        if record.exc_info:
            result["exception_type"] = record.exc_info[0].__name__
        return json.dumps(result, ensure_ascii=True)
