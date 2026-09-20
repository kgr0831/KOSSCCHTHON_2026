"""Authenticated WebSocket invalidations backed by the shared database."""
import asyncio
import hashlib
import secrets
from collections import deque
from dataclasses import dataclass
from datetime import timedelta

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

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
_DISPATCH_INTERVAL_SECONDS = 1
_MAX_EVENTS_PER_POLL = 100
_MAX_DELIVERED_EVENT_IDS = 500
_MAX_TICKETS_PER_MINUTE = 10
_MAX_PENDING_MESSAGES = 100


@dataclass
class _Subscriber:
    user_id: str
    session_id: str
    messages: asyncio.Queue[dict]


def _dispatch_batch(engine, session_ids: set[str]):
    """Read shared invalidations once, off the API event loop."""
    with Session(engine) as db:
        events = list(db.execute(select(RealtimeEvent.id, RealtimeEvent.target_user_id, RealtimeEvent.kind).where(
            RealtimeEvent.created_at >= now() - _EVENT_REPLAY_WINDOW
        ).order_by(RealtimeEvent.created_at.desc(), RealtimeEvent.id.desc()).limit(_MAX_EVENTS_PER_POLL)))
        active_sessions = set()
        if session_ids:
            active_sessions = set(db.scalars(select(AuthSession.id).join(User).where(
                AuthSession.id.in_(session_ids),
                User.account_status == "active",
                AuthSession.revoked.is_(False),
                AuthSession.rotated.is_(False),
                AuthSession.access_expires_at > now(),
                AuthSession.expires_at > now(),
            )))
    return events, active_sessions


class RealtimeHub:
    """One database poller per API process, regardless of connected clients."""

    def __init__(self):
        self._subscribers: dict[str, _Subscriber] = {}
        self._task: asyncio.Task | None = None
        self._seen: set[str] = set()
        self._seen_order: deque[str] = deque()

    async def subscribe(self, user_id: str, session_id: str, engine):
        subscriber_id = secrets.token_urlsafe(16)
        messages: asyncio.Queue[dict] = asyncio.Queue(maxsize=_MAX_PENDING_MESSAGES)
        self._subscribers[subscriber_id] = _Subscriber(user_id, session_id, messages)
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(engine), name="dudri-realtime-dispatcher")
        return subscriber_id, messages

    async def unsubscribe(self, subscriber_id: str):
        self._subscribers.pop(subscriber_id, None)
        if not self._subscribers and self._task and not self._task.done():
            self._task.cancel()
            self._task = None

    async def close(self):
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        self._subscribers.clear()

    def _remember(self, event_id: str) -> bool:
        if event_id in self._seen:
            return False
        if len(self._seen_order) >= _MAX_DELIVERED_EVENT_IDS:
            self._seen.discard(self._seen_order.popleft())
        self._seen.add(event_id)
        self._seen_order.append(event_id)
        return True

    @staticmethod
    def _send(subscriber: _Subscriber, message: dict):
        try:
            subscriber.messages.put_nowait(message)
        except asyncio.QueueFull:
            # These are cache invalidations. A later one is redundant while a
            # client already has pending work, so do not grow memory unbounded.
            pass

    async def _dispatch(self, events, active_sessions: set[str]):
        subscribers = tuple(self._subscribers.values())
        for subscriber in subscribers:
            if subscriber.session_id not in active_sessions:
                self._send(subscriber, {"type": "close"})
        for event_id, target_user_id, kind in events:
            if not self._remember(event_id):
                continue
            message = {"type": "event", "id": event_id, "kind": kind}
            for subscriber in subscribers:
                if subscriber.session_id in active_sessions and (target_user_id is None or target_user_id == subscriber.user_id):
                    self._send(subscriber, message)

    async def _run(self, engine):
        try:
            while self._subscribers:
                session_ids = {subscriber.session_id for subscriber in self._subscribers.values()}
                try:
                    events, active_sessions = await asyncio.to_thread(_dispatch_batch, engine, session_ids)
                    await self._dispatch(events, active_sessions)
                    delay = _DISPATCH_INTERVAL_SECONDS
                except Exception:
                    # A transient database outage must not terminate every
                    # socket. Their next normal API read still reports it.
                    delay = 3
                await asyncio.sleep(delay)
        except asyncio.CancelledError:
            raise


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
    hub: RealtimeHub = websocket.app.state.realtime_hub
    subscriber_id, messages = await hub.subscribe(user_id, session_id, db.get_bind())
    await websocket.send_json({"type": "ready"})
    try:
        while expiry > now():
            remaining = max(0, (expiry - now()).total_seconds())
            incoming = asyncio.create_task(websocket.receive_text())
            outgoing = asyncio.create_task(messages.get())
            try:
                done, pending = await asyncio.wait((incoming, outgoing), timeout=remaining,
                                                   return_when=asyncio.FIRST_COMPLETED)
                for task in pending:
                    task.cancel()
                if pending:
                    await asyncio.gather(*pending, return_exceptions=True)
                if not done:
                    return
                if outgoing in done:
                    message = outgoing.result()
                    if message["type"] == "close":
                        await websocket.close(code=1008)
                        return
                    await websocket.send_json(message)
                if incoming in done and incoming.result() == "ping":
                    await websocket.send_json({"type": "pong"})
            finally:
                for task in (incoming, outgoing):
                    if not task.done():
                        task.cancel()
    except WebSocketDisconnect:
        return
    finally:
        await hub.unsubscribe(subscriber_id)
        db.rollback()
        # A short lived connection is intentional: the client obtains a fresh
        # credential, which also bounds a ticket after logout/revocation.
        if websocket.client_state.name != "DISCONNECTED":
            try:
                await websocket.close(code=1000)
            except RuntimeError:
                pass
