from datetime import timedelta

from sqlalchemy import select

from app.models import Booking, CoffeeRequest, MonthlyOpportunity, PointTransaction, now


def rewards(world, index):
    response = world["client"].get("/api/v1/me/rewards", headers=world["auth"](index))
    assert response.status_code == 200, response.text
    return response.json()


def set_plan(world, index, plan):
    response = world["client"].put("/api/v1/me/subscription", headers=world["auth"](index), json={"plan": plan})
    assert response.status_code == 200, response.text


def coffee_body(world, minute=0):
    starts_at = now() + timedelta(days=3, minutes=minute)
    return {
        "recipient_id": world["users"][1],
        "purpose": "Career conversation",
        "questions": "What helped you learn this role?",
        "proposed_slots": [{"starts_at": starts_at.isoformat(), "ends_at": (starts_at + timedelta(minutes=30)).isoformat()}],
    }


def test_free_opportunities_are_shared_for_coffee_and_idempotent_retries(world):
    client, headers = world["client"], world["auth"](0)
    set_plan(world, 0, "free")
    assert rewards(world, 0)["opportunities"] == {
        "period": rewards(world, 0)["opportunities"]["period"], "limit": 5, "bonus": 0, "used": 0,
        "remaining": 5, "resets_at": rewards(world, 0)["opportunities"]["resets_at"],
    }
    assert client.post("/api/v1/coffee-chats", headers=headers, json=coffee_body(world)).status_code == 422
    assert rewards(world, 0)["opportunities"]["used"] == 0
    first_body = coffee_body(world, 1)
    first = client.post("/api/v1/coffee-chats", headers=headers | {"Idempotency-Key": "coffee-1"}, json=first_body)
    assert first.status_code == 201
    assert client.post("/api/v1/coffee-chats", headers=headers | {"Idempotency-Key": "coffee-1"}, json=first_body).status_code == 201
    for number in range(2, 6):
        response = client.post("/api/v1/coffee-chats", headers=headers | {"Idempotency-Key": f"coffee-{number}"},
                               json=coffee_body(world, number))
        assert response.status_code == 201, response.text
    opportunity = rewards(world, 0)["opportunities"]
    assert opportunity["limit"] == 5 and opportunity["used"] == 5 and opportunity["remaining"] == 0
    assert client.post("/api/v1/coffee-chats", headers=headers | {"Idempotency-Key": "coffee-6"},
                       json=coffee_body(world, 6)).status_code == 429


def project_and_draft(world):
    client, headers = world["client"], world["auth"](0)
    project = client.post("/api/v1/projects", headers=headers,
                          json={"title": "Quota fixture", "role": "Planner", "visibility": "public"})
    assert project.status_code == 201
    post = client.post(f"/api/v1/projects/{project.json()['id']}/recruitment-posts", headers=headers,
                       json={"description": "Join the project", "role_openings": [{"role": "Developer", "capacity": 2}]})
    assert post.status_code == 201
    return project.json(), post.json()


def test_publish_and_participation_application_consume_the_same_monthly_allowance(world):
    client = world["client"]
    set_plan(world, 0, "free")
    set_plan(world, 1, "free")
    project, post = project_and_draft(world)
    creator = world["auth"](0)
    # Creating a draft is free; publishing its public opportunity costs one.
    assert rewards(world, 0)["opportunities"]["used"] == 0
    published = client.post(f"/api/v1/recruitment-posts/{post['id']}/publish", headers=creator,
                            json={"revision": post["revision"]})
    assert published.status_code == 200, published.text
    assert rewards(world, 0)["opportunities"]["used"] == 1
    assert client.post(f"/api/v1/recruitment-posts/{post['id']}/publish", headers=creator,
                       json={"revision": published.json()["revision"]}).status_code == 409
    assert rewards(world, 0)["opportunities"]["used"] == 1

    applicant = world["auth"](1)
    body = {"opening_id": post["role_openings"][0]["id"], "message": "I would like to participate."}
    applied = client.post(f"/api/v1/recruitment-posts/{post['id']}/applications",
                          headers=applicant | {"Idempotency-Key": "apply-once"}, json=body)
    assert applied.status_code == 201, applied.text
    assert client.post(f"/api/v1/recruitment-posts/{post['id']}/applications",
                       headers=applicant | {"Idempotency-Key": "apply-once"}, json=body).status_code == 201
    opportunity = rewards(world, 1)["opportunities"]
    assert opportunity["used"] == 1 and opportunity["remaining"] == 4
    assert client.get(f"/api/v1/projects/{project['id']}", headers=applicant).json()["viewer_request_status"] == "pending"


def completed_booking(world):
    with world["factory"].begin() as db:
        chat = CoffeeRequest(requester_id=world["users"][0], recipient_id=world["users"][1],
                             purpose="Completed fixture", questions="Question", status="accepted")
        db.add(chat)
        db.flush()
        row = Booking(request_id=chat.id, starts_at=now() - timedelta(hours=2), ends_at=now() - timedelta(hours=1),
                      meeting_mode="online", meeting_location="Video call")
        db.add(row)
        db.flush()
        return row.id


def test_completed_coffee_chat_awards_points_to_both_and_mentor_bonus_once(world):
    booking_id = completed_booking(world)
    client = world["client"]
    path = f"/api/v1/bookings/{booking_id}/attendance-claim"
    assert client.put(path, headers=world["auth"](0), json={"attendance_claim": "attended"}).status_code == 200
    assert client.put(path, headers=world["auth"](1), json={"attendance_claim": "attended"}).status_code == 200
    assert client.put(path, headers=world["auth"](1), json={"attendance_claim": "attended"}).status_code == 200
    requester, mentor = rewards(world, 0), rewards(world, 1)
    assert requester["points"] == mentor["points"] == 1
    assert requester["opportunities"]["bonus"] == 0
    assert mentor["opportunities"]["bonus"] == 1
    assert mentor["opportunities"]["remaining"] == 21
    with world["factory"]() as db:
        assert len(list(db.scalars(select(PointTransaction).where(PointTransaction.booking_id == booking_id)))) == 2
        assert db.get(Booking, booking_id).completion_rewarded_at is not None


def test_new_month_starts_a_fresh_opportunity_balance_and_keeps_points(world, monkeypatch):
    import app.rewards as reward_module

    monkeypatch.setattr(reward_module, "period_key", lambda at=None: "2026-09")
    set_plan(world, 0, "free")
    client = world["client"]
    response = client.post("/api/v1/coffee-chats", headers=world["auth"](0) | {"Idempotency-Key": "september"},
                           json=coffee_body(world))
    assert response.status_code == 201
    assert rewards(world, 0)["opportunities"]["used"] == 1
    monkeypatch.setattr(reward_module, "period_key", lambda at=None: "2026-10")
    current = rewards(world, 0)["opportunities"]
    assert current["period"] == "2026-10" and current["used"] == current["bonus"] == 0 and current["remaining"] == 5
    with world["factory"]() as db:
        rows = list(db.scalars(select(MonthlyOpportunity).where(MonthlyOpportunity.user_id == world["users"][0])))
        assert {row.period_key for row in rows} == {"2026-09", "2026-10"}
