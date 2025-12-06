from app.logging_utils import now_iso, make_request_id, log_json

import time

from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field, validator
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import text
from typing import Optional

import hmac
import hashlib
import json
from datetime import datetime

from app.config import settings
from app.models import get_engine, init_db
from app.storage import list_messages, compute_stats
from app.metrics import (
    inc_http_request,
    inc_webhook_result,
    observe_latency_ms,
    http_requests_total,
    webhook_requests_total,
    request_latency_ms_buckets,
    request_latency_ms_count,
    latency_buckets,
)
from fastapi import Query


class WebhookMessage(BaseModel):
    message_id: str = Field(..., min_length=1)
    from_: str = Field(..., alias="from")
    to: str
    ts: str
    text: str | None = Field(default=None, max_length=4096)

    @validator("from_")
    def validate_from(cls, v: str) -> str:
        if not (v.startswith("+") and v[1:].isdigit()):
            raise ValueError("from must be E.164-like")
        return v

    @validator("to")
    def validate_to(cls, v: str) -> str:
        if not (v.startswith("+") and v[1:].isdigit()):
            raise ValueError("to must be E.164-like")
        return v

    @validator("ts")
    def validate_ts(cls, v: str) -> str:
        # basic ISO-8601 UTC with Z check
        try:
            if not v.endswith("Z"):
                raise ValueError
            datetime.fromisoformat(v.replace("Z", "+00:00"))
        except Exception:
            raise ValueError("ts must be ISO-8601 UTC with Z")
        return v

    class Config:
        allow_population_by_field_name = True


app = FastAPI()

@app.middleware("http")
async def logging_and_metrics_middleware(request: Request, call_next):
    request_id = make_request_id()
    start = time.time()

    # run handler
    response = await call_next(request)

    latency_ms = (time.time() - start) * 1000.0
    path = request.url.path
    status_code = response.status_code

    # metrics
    inc_http_request(path, status_code)
    observe_latency_ms(latency_ms)

    # JSON log
    log_data = {
        "ts": now_iso(),
        "level": "INFO",
        "request_id": request_id,
        "method": request.method,
        "path": path,
        "status": status_code,
        "latency_ms": round(latency_ms, 2),
    }
    log_json(log_data)

    return response



engine = None
SessionLocal = None

def is_ready() -> bool:
    # WEBHOOK_SECRET must be set and non-empty
    if not settings.WEBHOOK_SECRET:
        return False
    if engine is None:
        return False
    try:
        with engine.connect() as conn:
            # simple check that messages table exists / is usable
            conn.execute(text("SELECT 1 FROM messages LIMIT 1"))
        return True
    except Exception:
        return False
    

@app.get("/health/ready")
def health_ready():
    if not is_ready():
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "not_ready"},
        )
    return {"status": "ready"}


@app.on_event("startup")
def on_startup():
    global engine, SessionLocal
    if not settings.DATABASE_URL:
        return
    engine = get_engine(settings.DATABASE_URL)
    from app.models import Base  # ensure models are imported
    init_db(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@app.get("/health/live")
def health_live():
    return {"status": "live"}

def verify_signature(raw_body: bytes, header_sig: str | None) -> bool:
    if not settings.WEBHOOK_SECRET:
        return False
    if not header_sig:
        return False
    secret = settings.WEBHOOK_SECRET.encode("utf-8")
    computed = hmac.new(secret, raw_body, hashlib.sha256).hexdigest()
    # use hmac.compare_digest for timing-safe compare
    return hmac.compare_digest(computed, header_sig)


@app.post("/webhook")
async def webhook(request: Request):
    # Read raw body for HMAC
    raw_body = await request.body()
    header_sig = request.headers.get("X-Signature")

    if not verify_signature(raw_body, header_sig):
        inc_webhook_result("invalid_signature")
        raise HTTPException(status_code=401, detail="invalid signature")


    # Parse JSON and validate with Pydantic
    try:
        payload_dict = json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError:
        # FastAPI will normally handle this, but we keep it explicit
        raise HTTPException(status_code=422, detail="Invalid JSON body")

    msg_model = WebhookMessage(**payload_dict)

    # Insert into DB with idempotency
    db: Session = SessionLocal()
    try:
        from app.models import Message
        # Check if message_id already exists
        existing = db.get(Message, msg_model.message_id)
        if existing:
            inc_webhook_result("duplicate")
            # idempotent: return ok, no new row
            return {"status": "ok"}

        now_iso = datetime.utcnow().isoformat() + "Z"
        db_msg = Message(
            message_id=msg_model.message_id,
            from_msisdn=msg_model.from_,
            to_msisdn=msg_model.to,
            ts=msg_model.ts,
            text=msg_model.text,
            created_at=now_iso,
        )
        db.add(db_msg)
        db.commit()
        inc_webhook_result("created")
        return {"status": "ok"}
    finally:
        db.close()


@app.get("/messages")
def get_messages(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    from_: Optional[str] = Query(None, alias="from"),
    since: Optional[str] = None,
    q: Optional[str] = None,
):
    db: Session = SessionLocal()
    try:
        rows, total = list_messages(
            db=db,
            limit=limit,
            offset=offset,
            from_msisdn=from_,
            since=since,
            q=q,
        )
        data = [
            {
                "message_id": m.message_id,
                "from": m.from_msisdn,
                "to": m.to_msisdn,
                "ts": m.ts,
                "text": m.text,
            }
            for m in rows
        ]
        return {
            "data": data,
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    finally:
        db.close()

@app.get("/stats")
def get_stats():
    db: Session = SessionLocal()
    try:
        return compute_stats(db)
    finally:
        db.close()

@app.get("/metrics", response_class=PlainTextResponse)
def metrics():
    lines = []

    # http_requests_total
    for (path, status), count in http_requests_total.items():
        lines.append(f'http_requests_total{{path="{path}",status="{status}"}} {count}')

    # webhook_requests_total
    for result, count in webhook_requests_total.items():
        lines.append(f'webhook_requests_total{{result="{result}"}} {count}')

    # latency buckets
    cumulative = 0
    for b in sorted(latency_buckets):
        cumulative += request_latency_ms_buckets.get(b, 0)
        lines.append(f'request_latency_ms_bucket{{le="{b}"}} {cumulative}')
    lines.append(f'request_latency_ms_bucket{{le="+Inf"}} {request_latency_ms_count}')
    lines.append(f"request_latency_ms_count {request_latency_ms_count}")

    return "\n".join(lines) + "\n"


