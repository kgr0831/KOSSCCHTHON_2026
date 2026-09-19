"""Authenticated WebSocket invalidations backed by the shared database."""
import asyncio
import hashlib
import secrets
from datetime import timedelta

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy import delete, func, or_, select, update

from .auth import SessionActor
from .common import DB, utc
from .config import get_settings
from .models import AuthSession, RealtimeEvent, RealtimeTicket, User, now

router = APIRouter(prefix="/api/v1", tags=["realtime"])
_PROTOCOL = "dudri"
_TICKET_LIFETIME = timedelta(minutes=2)
# Events are inserted inside the mutation's database transaction.  Query a
# small overlap rather than trusting UUID/timestamp ordering: another worker
# can commit an earlier insert after a later one is already observed.
_EVENT_REPLAY_WINDOW = timedelta(minutes=10)
_POLL_INTERVAL_SECONDS = 0.5
_MAX_EVENTS_PER_POLL = 100
_MAX_DELIVERED_EVENT_IDS = 500
_MAX_TICKETS_PER_MINUTE = 10


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


@router.post("/realtime/tickets")
def create_ticket(db: DB, actor: SessionActor):
    """Issue a short-lived one-time credential for a browser WebSocket."""
    user, session = actor
    db.execute(delete(RealtimeTicket).where(RealtimeTicket.expires_at <= now()))
    issued_recently = db.scalar(select(func.count()).select_from(RealtimeTicket).where(
        RealtimeTicket.user_id == user.id, RealtimeTicket.created_at > now() - timedelta(minutes=1)))
    if issued_recently >= _MAX_TICKETS_PER_MINUTE:
        raise HTTPException(429, "실시간 연결을 너무 자주 다시 시도하고 있습니다. 잠시 후 다시 시도해 주세요.")
    # The browser only needs one not-yet-used ticket per access session.  This
    # also prevents abandoned reconnect attempts accumulating until expiry.
    db.execute(delete(RealtimeTicket).where(RealtimeTicket.session_id == session.id,
                                            RealtimeTicket.consumed_at.is_(None)))
    token = secrets.token_urlsafe(32)
    expiry = now() + _TICKET_LIFETIME
    db.add(RealtimeTicket(user_id=user.id, session_id=session.id, token_hash=_digest(token), expires_at=expiry))
    db.flush()
    return {"token": token, "expires_at": expiry.isoformat(), "protocol": _PROTOCOL}


def _ticket_from_protocols(websocket: WebSocket) -> str | None:
    offered = [value.strip() for value in websocket.headers.get("sec-websocket-protocol", "").split(",") if value.strip()]
    if not offered or offered[0] != _PROTOCOL or len(offered) != 2:
        return None
    token = offered[1]
    return token if 20 <= len(token) <= 200 else None


async def _reject(websocket: WebSocket):
    await websocket.close(code=1008)


@router.websocket("/realtime")
async def realtime_socket(websocket: WebSocket, db: DB):
    # WebSocket browser APIs cannot send Authorization headers.  The ticket is
    # supplied as a subprotocol so it is absent from the request URL/log line.
    if websocket.headers.get("origin") != get_settings().app_origin:
        await _reject(websocket)
        return
    token = _ticket_from_protocols(websocket)
    if not token:
        await _reject(websocket)
        return
    ticket = db.scalar(select(RealtimeTicket).where(RealtimeTicket.token_hash == _digest(token)))
    if not ticket or ticket.consumed_at or utc(ticket.expires_at) <= now():
        await _reject(websocket)
        return
    session = db.get(AuthSession, ticket.session_id)
    user = db.get(User, ticket.user_id)
    if (not user or user.account_status != "active" or not session or session.user_id != user.id
            or session.revoked or session.rotated or utc(session.access_expires_at) <= now()
            or utc(session.expires_at) <= now()):
        await _reject(websocket)
        return
    consumed = db.execute(update(RealtimeTicket).where(RealtimeTicket.id == ticket.id,
                          RealtimeTicket.consumed_at.is_(None), RealtimeTicket.expires_at > now())
                          .values(consumed_at=now()).execution_options(synchronize_session=False))
    if consumed.rowcount != 1:
        await _reject(websocket)
        return
    # Commit before accepting: concurrent reconnects cannot reuse this ticket.
    user_id, session_id, expiry = user.id, session.id, utc(ticket.expires_at)
    db.commit()
    await websocket.accept(subprotocol=_PROTOCOL)
    delivered_event_ids: set[str] = set()
    await websocket.send_json({"type": "ready"})
    try:
        while expiry > now():
            poll_started = asyncio.get_running_loop().time()
            # End each read transaction so SQLite and PostgreSQL connections
            # see events committed by a different API worker.
            db.rollback()
            person = db.get(User, user_id)
            active_session = db.get(AuthSession, session_id)
            if (not person or person.account_status != "active" or not active_session
                    or active_session.user_id != user_id or active_session.revoked or active_session.rotated
                    or utc(active_session.access_expires_at) <= now() or utc(active_session.expires_at) <= now()):
                db.rollback()
                await websocket.close(code=1008)
                return
            events = list(db.scalars(select(RealtimeEvent).where(
                or_(RealtimeEvent.target_user_id == user_id, RealtimeEvent.target_user_id.is_(None)),
                RealtimeEvent.created_at >= now() - _EVENT_REPLAY_WINDOW)
                .order_by(RealtimeEvent.created_at.desc(), RealtimeEvent.id.desc()).limit(_MAX_EVENTS_PER_POLL)))
            # Do not retain a database connection while network IO waits. The
            # synchronous API pool is deliberately small on the free tier.
            event_messages = [{"type": "event", "id": event.id, "kind": event.kind} for event in events]
            if len(delivered_event_ids) >= _MAX_DELIVERED_EVENT_IDS:
                delivered_event_ids.intersection_update(event["id"] for event in event_messages)
            db.rollback()
            for event in event_messages:
                if event["id"] in delivered_event_ids:
                    continue
                await websocket.send_json(event)
                delivered_event_ids.add(event["id"])
            try:
                remaining = max(0, _POLL_INTERVAL_SECONDS - (asyncio.get_running_loop().time() - poll_started))
                message = await asyncio.wait_for(websocket.receive_text(), timeout=remaining)
                if message == "ping":
                    await websocket.send_json({"type": "pong"})
            except TimeoutError:
                pass
            finally:
                # A buffered flood of client text frames must not turn into an
                # unbounded database poll loop.  One socket observes at most
                # one poll interval regardless of how quickly it sends ping.
                remaining = _POLL_INTERVAL_SECONDS - (asyncio.get_running_loop().time() - poll_started)
                if remaining > 0:
                    await asyncio.sleep(remaining)
    except WebSocketDisconnect:
        return
    finally:
        db.rollback()
        # A short lived connection is intentional: the client obtains a fresh
        # credential, which also bounds a ticket after logout/revocation.
        if websocket.client_state.name != "DISCONNECTED":
            try:
                await websocket.close(code=1000)
            except RuntimeError:
                pass
