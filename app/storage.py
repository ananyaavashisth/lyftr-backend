from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from app.models import Message

def list_messages(
    db: Session,
    limit: int = 50,
    offset: int = 0,
    from_msisdn: Optional[str] = None,
    since: Optional[str] = None,
    q: Optional[str] = None,
) -> Tuple[List[Message], int]:
    stmt = select(Message)

    if from_msisdn:
        stmt = stmt.where(Message.from_msisdn == from_msisdn)
    if since:
        stmt = stmt.where(Message.ts >= since)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(func.lower(Message.text).like(like))

    # total before pagination
    count_stmt = stmt.with_only_columns(func.count()).order_by(None)
    total = db.execute(count_stmt).scalar_one()

    # ordering + pagination
    stmt = stmt.order_by(Message.ts.asc(), Message.message_id.asc())
    stmt = stmt.limit(limit).offset(offset)

    rows = db.execute(stmt).scalars().all()
    return rows, total

from sqlalchemy import text

def compute_stats(db: Session) -> dict:
    # total_messages
    total_messages = db.execute(
        select(func.count()).select_from(Message)
    ).scalar_one()

    # senders_count (distinct from_msisdn)
    senders_count = db.execute(
        select(func.count(func.distinct(Message.from_msisdn)))
    ).scalar_one()

    # messages_per_sender: top 10 by count desc
    mps_rows = db.execute(
        select(Message.from_msisdn, func.count().label("count"))
        .group_by(Message.from_msisdn)
        .order_by(func.count().desc())
        .limit(10)
    ).all()
    messages_per_sender = [
        {"from": row[0], "count": row[1]} for row in mps_rows
    ]

    # first_message_ts and last_message_ts
    first_ts = db.execute(
        select(func.min(Message.ts))
    ).scalar_one()
    last_ts = db.execute(
        select(func.max(Message.ts))
    ).scalar_one()

    return {
        "total_messages": total_messages,
        "senders_count": senders_count,
        "messages_per_sender": messages_per_sender,
        "first_message_ts": first_ts,
        "last_message_ts": last_ts,
    }

