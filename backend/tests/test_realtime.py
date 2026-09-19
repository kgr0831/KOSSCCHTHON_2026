from datetime import timedelta

from sqlalchemy import select, update

from app.common import emit_realtime
from app.models import AuthSession, RealtimeEvent, RealtimeTicket, now


def ticket(world, index=0):
    response = world["client"].post("/api/v1/realtime/tickets", headers=world["auth"](index))
    assert response.status_code == 200
    return response.json()["token"]


def test_realtime_ticket_requires_authenticated_user(world):
    assert world["client"].post("/api/v1/realtime/tickets").status_code == 401


def test_realtime_socket_consumes_ticket_and_scopes_events(world):
    c = world["client"]
    token = ticket(world)
    with c.websocket_connect("/api/v1/realtime", subprotocols=["dudri", token],
                             headers={"origin": "http://localhost:3000"}) as socket:
        assert socket.receive_json() == {"type": "ready"}
        with world["factory"].begin() as db:
            emit_realtime(db, "another-user", user_ids=[world["users"][1]])
            emit_realtime(db, "my-notification", user_ids=[world["users"][0]])
        event = socket.receive_json()
        assert event["type"] == "event" and event["kind"] == "my-notification"
    with world["factory"]() as db:
        assert db.scalar(select(RealtimeTicket).where(RealtimeTicket.token_hash.is_not(None))).consumed_at is not None


def test_realtime_ticket_cannot_be_reused(world):
    c, token = world["client"], ticket(world)
    with c.websocket_connect("/api/v1/realtime", subprotocols=["dudri", token],
                             headers={"origin": "http://localhost:3000"}) as socket:
        assert socket.receive_json()["type"] == "ready"
    # The second attempt is rejected before accepting the socket.
    try:
        with c.websocket_connect("/api/v1/realtime", subprotocols=["dudri", token],
                                 headers={"origin": "http://localhost:3000"}):
            raise AssertionError("consumed ticket unexpectedly connected")
    except Exception as error:
        assert "1008" in str(error) or error.__class__.__name__ in {"WebSocketDisconnect", "WebSocketDenialResponse"}


def test_realtime_socket_closes_when_its_issuing_session_is_revoked(world):
    c, token = world["client"], ticket(world)
    with c.websocket_connect("/api/v1/realtime", subprotocols=["dudri", token],
                             headers={"origin": "http://localhost:3000"}) as socket:
        assert socket.receive_json()["type"] == "ready"
        with world["factory"].begin() as db:
            row = db.scalar(select(RealtimeTicket).where(RealtimeTicket.token_hash.is_not(None)))
            db.execute(update(AuthSession).where(AuthSession.id == row.session_id).values(revoked=True))
        socket.send_text("ping")
        message = socket.receive()
        if message["type"] == "websocket.send":
            # The pre-revocation poll can still answer this one ping.  Its
            # next fixed-cadence poll must observe the revoked session.
            assert message["text"] == '{"type":"pong"}'
            message = socket.receive()
        assert message["type"] == "websocket.close"
        assert message["code"] == 1008


def test_realtime_socket_handles_late_commit_with_an_older_timestamp(world):
    c, user_id = world["client"], world["users"][0]
    with c.websocket_connect("/api/v1/realtime", subprotocols=["dudri", ticket(world)],
                             headers={"origin": "http://localhost:3000"}) as socket:
        assert socket.receive_json()["type"] == "ready"
        with world["factory"].begin() as db:
            emit_realtime(db, "newer-event", user_ids=[user_id])
        assert socket.receive_json()["kind"] == "newer-event"
        # Simulate another worker committing an earlier insert only after the
        # socket has already observed the newer one.
        with world["factory"].begin() as db:
            db.add(RealtimeEvent(target_user_id=user_id, kind="late-commit",
                                 created_at=now() - timedelta(seconds=5)))
        assert socket.receive_json()["kind"] == "late-commit"
