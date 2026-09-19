from datetime import timedelta

from app.models import now


def test_private_availability_is_saved_and_enforced_immediately(world):
    client, users = world["client"], world["users"]
    sender, recipient = world["auth"](0), world["auth"](1)
    profile = f"/api/v1/users/{users[1]}"
    assert client.get(profile, headers=sender).json()["can_request_coffee_chat"] is True
    saved = client.patch("/api/v1/me/preferences", headers=recipient,
                         json={"revision": 1, "coffee_chat_available": False, "is_public": False})
    assert saved.status_code == 200
    assert saved.json()["revision"] == 2
    assert client.get("/api/v1/me", headers=recipient).json()["preferences"]["coffee_chat_available"] is False
    public = client.get(profile, headers=sender).json()
    assert public["can_request_coffee_chat"] is False and "preferences" not in public
    start = now() + timedelta(days=3)
    body = {"recipient_id": users[1], "purpose": "Fixture", "questions": "Fixture question",
            "proposed_slots": [{"starts_at": start.isoformat(), "ends_at": (start + timedelta(minutes=30)).isoformat()}]}
    assert client.post("/api/v1/coffee-chats", headers=sender | {"Idempotency-Key": "closed"}, json=body).status_code == 409
    assert client.patch("/api/v1/me/preferences", headers=recipient,
                        json={"revision": 2, "coffee_chat_available": True}).status_code == 200
    public = client.get(profile, headers=sender).json()
    assert public["can_request_coffee_chat"] is True and "preferences" not in public
    assert client.get(profile, headers=recipient).json()["can_request_coffee_chat"] is False
    assert client.post("/api/v1/coffee-chats", headers=sender | {"Idempotency-Key": "open"}, json=body).status_code == 201
