import base64
import hashlib
import json
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, Query
from sqlalchemy import inspect, select, update
from sqlalchemy.orm import Session

from .db import get_db
from .models import IdempotencyRecord, Notification, PersonalSite, Publication, User, now

# Commit (or fail) before sending a successful response. Otherwise an immediate
# request after login/save can race the yield dependency's request-scope cleanup.
DB = Annotated[Session, Depends(get_db, scope="function")]


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def data(row, *, exclude=()) -> dict:
    return {
        field.key: (utc(value).isoformat() if isinstance(value, datetime) else value)
        for field in inspect(type(row)).columns
        if field.key not in exclude
        for value in [getattr(row, field.key)]
    }


def required(db: Session, model, row_id: str):
    row = db.get(model, row_id)
    if row is None:
        raise HTTPException(404, "요청한 항목을 찾을 수 없습니다.")
    return row


def owner(row, user: User, key="user_id"):
    if getattr(row, key) != user.id:
        raise HTTPException(403, "이 항목에 접근할 수 없습니다.")
    return row


def update_revision(db: Session, row, revision: int, changes: dict):
    model = type(row)
    pk = inspect(model).primary_key[0]
    result = db.execute(update(model).where(pk == getattr(row, pk.key), model.revision == revision)
                        .values(**changes, revision=revision + 1).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        raise HTTPException(409, "다른 화면에서 변경되었습니다. 최신 내용을 다시 확인해 주세요.")
    db.refresh(row)
    return row


def lock_user(db: Session, user_id: str):
    db.execute(update(User).where(User.id == user_id).values(facts_revision=User.facts_revision))
    row = required(db, User, user_id)
    db.refresh(row)
    return row


def facts_changed(db: Session, user_id: str):
    db.execute(update(User).where(User.id == user_id).values(facts_revision=User.facts_revision + 1))
    sites = list(db.scalars(select(PersonalSite).where(PersonalSite.user_id == user_id)))
    for site in sites:
        if site.published_version_id:
            db.execute(update(Publication).where(Publication.site_id == site.id,
                                                Publication.revoked_at.is_(None)).values(revoked_at=now()))
        site.published_version_id = None
        site.revision += 1


class Pagination:
    def __init__(self, limit: Annotated[int, Query(ge=1, le=100)] = 20, cursor: str | None = None):
        self.limit = limit
        self.after = None
        if cursor:
            try:
                timestamp, row_id = json.loads(base64.urlsafe_b64decode(cursor))
                self.after = (datetime.fromisoformat(timestamp), row_id)
            except (ValueError, TypeError, KeyError):
                raise HTTPException(422, "잘못된 페이지 커서입니다.")

    def page(self, db: Session, statement, model, serialize=data):
        if self.after:
            timestamp, row_id = self.after
            statement = statement.where((model.created_at < timestamp) |
                                        ((model.created_at == timestamp) & (model.id < row_id)))
        rows = list(db.scalars(statement.order_by(model.created_at.desc(), model.id.desc()).limit(self.limit + 1)))
        following = None
        if len(rows) > self.limit:
            last = rows[self.limit - 1]
            following = base64.urlsafe_b64encode(json.dumps([utc(last.created_at).isoformat(), last.id]).encode()).decode()
        return {"items": [serialize(row) for row in rows[:self.limit]], "next_cursor": following}


Page = Annotated[Pagination, Depends()]


def notify(db: Session, user_id: str, kind: str, title: str, href: str):
    db.add(Notification(user_id=user_id, kind=kind, title=title, href=href))


def idempotent_lookup(db: Session, user_id: str, operation: str, key: str | None, payload: dict):
    if not key or len(key) > 128:
        raise HTTPException(422, "1~128자의 Idempotency-Key가 필요합니다.")
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
    row = db.scalar(select(IdempotencyRecord).where(IdempotencyRecord.user_id == user_id,
                    IdempotencyRecord.operation == operation, IdempotencyRecord.key == key))
    if row and row.request_hash != digest:
        raise HTTPException(409, "같은 멱등키로 다른 내용을 전송할 수 없습니다.")
    return row, digest


def remember(db: Session, user_id: str, operation: str, key: str, digest: str, body: dict, status=201):
    db.add(IdempotencyRecord(user_id=user_id, operation=operation, key=key,
                            request_hash=digest, response_body=body, response_status=status))
