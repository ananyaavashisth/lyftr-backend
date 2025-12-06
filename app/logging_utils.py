import json
import uuid
from datetime import datetime
from typing import Any, Dict

def now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"

def make_request_id() -> str:
    return str(uuid.uuid4())

def log_json(data: Dict[str, Any]) -> None:
    print(json.dumps(data, default=str))
