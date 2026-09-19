from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from sqlalchemy import select

from app.models import (
    Attendance,
    Booking,
    CoffeeSlot,
    Notification,
    Project,
    ProjectMember,
    ProjectRequest,
    RecruitmentPost,
    RoleOpening,
    User,
    now,
)


def coffee_request(world):
    start = now() + timedelta(days=3)
    body = {"recipient_id": world["users"][1], "purpose": "커리어 탐색", "questions": "첫 프로젝트 경험이 궁금해요",
            "proposed_slots": [{"starts_at": start.isoformat(), "ends_at": (start + timedelta(minutes=30)).isoformat()}]}
    response = world["client"].post("/api/v1/coffee-chats", headers=world["auth"](0) | {"Idempotency-Key": "request-1"}, json=body)
    assert response.status_code == 201
    return response.json(), body


def booking(world):
    chat, _ = coffee_request(world)
    c, b = world["client"], world["auth"](1)
    assert c.post(f"/api/v1/coffee-chats/{chat['id']}/decision", headers=b,
                   json={"decision": "accepted", "revision": 1}).status_code == 200
    body = {"slot_id": chat["proposed_slots"][0]["id"], "meeting_mode": "online", "meeting_location": "서비스 화상 통화"}
    result = c.post(f"/api/v1/coffee-chats/{chat['id']}/booking", headers=b | {"Idempotency-Key": "book-1"}, json=body)
    assert result.status_code == 201
    return result.json(), chat, body


def test_coffee_only_recipient_can_decide_and_booking_requires_acceptance(world):
    chat, body = coffee_request(world)
    c, a, b = world["client"], world["auth"](0), world["auth"](1)
    path = f"/api/v1/coffee-chats/{chat['id']}"
    assert c.post(path + "/decision", headers=a, json={"decision": "accepted", "revision": 1}).status_code == 403
    assert c.get(path, headers=world["auth"](2)).status_code == 403
    payload = {"slot_id": chat["proposed_slots"][0]["id"], "meeting_mode": "online", "meeting_location": "온라인"}
    assert c.post(path + "/booking", headers=b | {"Idempotency-Key": "early"}, json=payload).status_code == 409
    retry = c.post("/api/v1/coffee-chats", headers=a | {"Idempotency-Key": "request-1"}, json=body)
    assert retry.status_code == 201 and retry.json()["id"] == chat["id"]
    assert c.post("/api/v1/coffee-chats", headers=a | {"Idempotency-Key": "request-1"},
                   json=body | {"questions": "다른 질문"}).status_code == 409


def test_booking_unique_under_different_idempotency_keys(world):
    chat, _ = coffee_request(world)
    c, b = world["client"], world["auth"](1)
    path = f"/api/v1/coffee-chats/{chat['id']}"
    c.post(path + "/decision", headers=b, json={"decision": "accepted", "revision": 1})
    payload = {"slot_id": chat["proposed_slots"][0]["id"], "meeting_mode": "online", "meeting_location": "온라인"}
    def submit(key):
        return c.post(path + "/booking", headers=b | {"Idempotency-Key": key}, json=payload).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(submit, ["mobile", "desktop"])) == [201, 409]
    with world["factory"]() as db:
        assert len(list(db.scalars(select(Booking)))) == 1


def test_booking_changes_require_other_participant_and_keep_history(world):
    row, chat, payload = booking(world)
    c, a, b = world["client"], world["auth"](0), world["auth"](1)
    path = f"/api/v1/bookings/{row['id']}"
    change = c.post(path + "/changes", headers=a, json={"change_kind": "cancel", "revision": 1})
    assert change.status_code == 201
    assert c.get(path, headers=b).json()["status"] == "confirmed"
    decision = path + f"/changes/{change.json()['id']}/decision"
    assert c.post(decision, headers=a, json={"decision": "accepted"}).status_code == 403
    assert c.post(decision, headers=b, json={"decision": "accepted"}).status_code == 200
    detail = c.get(path, headers=a).json()
    assert detail["status"] == "cancelled"
    assert detail["changes"][0]["status"] == "accepted"
    retry = c.post(f"/api/v1/coffee-chats/{chat['id']}/booking", headers=b | {"Idempotency-Key": "book-1"}, json=payload)
    assert retry.status_code == 201 and retry.json()["id"] == row["id"]


def test_foreign_slot_cannot_be_booked(world):
    chat, _ = coffee_request(world)
    with world["factory"].begin() as db:
        slot = CoffeeSlot(request_id=chat["id"], starts_at=now(), ends_at=now() + timedelta(minutes=10))
        db.add(slot)
        db.flush()
        slot_id = slot.id
    c, b = world["client"], world["auth"](1)
    path = f"/api/v1/coffee-chats/{chat['id']}"
    c.post(path + "/decision", headers=b, json={"decision": "accepted", "revision": 1})
    assert c.post(path + "/booking", headers=b | {"Idempotency-Key": "expired-slot"}, json={
        "slot_id": slot_id, "meeting_mode": "online", "meeting_location": "온라인"}).status_code == 409


def test_later_attendance_claim_does_not_create_checkin_or_auto_resolve_dispute(world):
    row, _, _ = booking(world)
    c, a, b = world["client"], world["auth"](0), world["auth"](1)
    path = f"/api/v1/bookings/{row['id']}"
    assert c.put(path + "/attendance-claim", headers=a, json={"attendance_claim": "attended"}).status_code == 409
    with world["factory"].begin() as db:
        record = db.get(Booking, row["id"])
        record.starts_at, record.ends_at = now() - timedelta(hours=2), now() - timedelta(hours=1)
    assert c.post(path + "/disputes", headers=a, json={"reason": "출석 사실을 확인해 주세요"}).status_code == 201
    for headers in (a, b):
        answer = c.put(path + "/attendance-claim", headers=headers, json={"attendance_claim": "attended"})
        assert answer.status_code == 200 and answer.json()["checked_in_at"] is None
    assert c.get(path, headers=a).json()["status"] == "confirmed"
    assert c.get("/api/v1/me/trust-events", headers=a).json()["items"] == []
    with world["factory"]() as db:
        assert len(list(db.scalars(select(Attendance)))) == 2


def project_and_post(world, capacity=1):
    c, a = world["client"], world["auth"](0)
    project = c.post("/api/v1/projects", headers=a, json={"title": "함께 만드는 첫 앱", "role": "기획",
                                                               "visibility": "public"})
    assert project.status_code == 201
    project = project.json()
    post = c.post(f"/api/v1/projects/{project['id']}/recruitment-posts", headers=a,
                  json={"description": "함께 배울 동료를 찾아요", "role_openings": [{"role": "개발", "capacity": capacity}]})
    assert post.status_code == 201
    return project, post.json()


def test_explicit_recruitment_publish_and_acceptance_create_member(world):
    project, post = project_and_post(world)
    c, a, b = world["client"], world["auth"](0), world["auth"](1)
    assert c.get("/api/v1/recruitment-posts", headers=b).json()["items"] == []
    assert c.post(f"/api/v1/recruitment-posts/{post['id']}/publish", headers=b, json={"revision": 1}).status_code == 403
    assert c.post(f"/api/v1/recruitment-posts/{post['id']}/publish", headers=a, json={"revision": 1}).status_code == 200
    application = c.post(f"/api/v1/recruitment-posts/{post['id']}/applications", headers=b | {"Idempotency-Key": "apply"},
                         json={"opening_id": post["role_openings"][0]["id"], "message": "경험은 없지만 배우고 싶어요"})
    assert application.status_code == 201
    path = f"/api/v1/project-requests/{application.json()['id']}/decision"
    assert c.post(path, headers=b, json={"decision": "accepted", "revision": 1}).status_code == 403
    assert c.post(path, headers=a, json={"decision": "accepted", "revision": 1}).status_code == 200
    assert c.post(path, headers=a, json={"decision": "accepted", "revision": 1}).status_code == 409
    with world["factory"]() as db:
        assert len(list(db.scalars(select(ProjectMember).where(ProjectMember.project_id == project["id"])))) == 2


def test_concurrent_applicants_cannot_exceed_capacity(world):
    project, post = project_and_post(world)
    c, a = world["client"], world["auth"](0)
    c.post(f"/api/v1/recruitment-posts/{post['id']}/publish", headers=a, json={"revision": 1})
    requests = []
    for index in (1, 2):
        result = c.post(f"/api/v1/recruitment-posts/{post['id']}/applications",
            headers=world["auth"](index) | {"Idempotency-Key": f"apply-{index}"},
            json={"opening_id": post["role_openings"][0]["id"], "message": "참여합니다"})
        assert result.status_code == 201
        requests.append(result.json()["id"])
    def accept(request_id):
        return c.post(f"/api/v1/project-requests/{request_id}/decision", headers=a,
                       json={"decision": "accepted", "revision": 1}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(accept, requests)) == [200, 409]
    with world["factory"]() as db:
        assert db.get(RoleOpening, post["role_openings"][0]["id"]).filled == 1


def test_member_state_hides_recruitment_and_full_posts_stop_accepting_applications(world):
    project, post = project_and_post(world)
    client, creator, applicant, other = world["client"], world["auth"](0), world["auth"](1), world["auth"](2)
    opening_id = post["role_openings"][0]["id"]
    assert client.post(f"/api/v1/recruitment-posts/{post['id']}/publish", headers=creator,
                       json={"revision": post["revision"]}).status_code == 200

    application = client.post(f"/api/v1/recruitment-posts/{post['id']}/applications",
                              headers=applicant | {"Idempotency-Key": "member-state"},
                              json={"opening_id": opening_id, "message": "참여하고 싶어요"})
    assert application.status_code == 201
    pending = client.get(f"/api/v1/projects/{project['id']}", headers=applicant).json()
    assert pending["viewer_is_member"] is False
    assert pending["viewer_request_status"] == "pending"

    decision = client.post(f"/api/v1/project-requests/{application.json()['id']}/decision", headers=creator,
                           json={"decision": "accepted", "revision": 1})
    assert decision.status_code == 200
    participating = client.get(f"/api/v1/projects/{project['id']}", headers=applicant).json()
    assert participating["viewer_is_member"] is True
    assert participating["viewer_request_status"] == "accepted"

    assert client.post(f"/api/v1/recruitment-posts/{post['id']}/applications",
                       headers=applicant | {"Idempotency-Key": "member-retry"},
                       json={"opening_id": opening_id, "message": "다시 신청할게요"}).status_code == 409
    assert client.post(f"/api/v1/recruitment-posts/{post['id']}/applications",
                       headers=other | {"Idempotency-Key": "full-retry"},
                       json={"opening_id": opening_id, "message": "아직 자리가 있나요"}).status_code == 409
    assert client.get("/api/v1/recruitment-posts", headers=applicant).json()["items"] == []
    assert client.get("/api/v1/recruitment-posts", headers=other).json()["items"] == []
    assert client.get("/api/v1/projects", headers=applicant).json()["items"] == []
    with world["factory"]() as db:
        assert db.get(RoleOpening, opening_id).filled == 1
        assert db.get(RecruitmentPost, post["id"]).status == "closed"


def test_only_creator_can_soft_delete_project_and_pending_requests_are_cancelled(world):
    project, post = project_and_post(world, capacity=2)
    client, creator, member, applicant = world["client"], world["auth"](0), world["auth"](1), world["auth"](2)
    opening_id = post["role_openings"][0]["id"]
    assert client.post(f"/api/v1/recruitment-posts/{post['id']}/publish", headers=creator,
                       json={"revision": post["revision"]}).status_code == 200
    accepted = client.post(f"/api/v1/recruitment-posts/{post['id']}/applications",
                           headers=member | {"Idempotency-Key": "member-apply"},
                           json={"opening_id": opening_id, "message": "팀원이 될게요"})
    assert accepted.status_code == 201
    assert client.post(f"/api/v1/project-requests/{accepted.json()['id']}/decision", headers=creator,
                       json={"decision": "accepted", "revision": 1}).status_code == 200
    pending = client.post(f"/api/v1/recruitment-posts/{post['id']}/applications",
                          headers=applicant | {"Idempotency-Key": "delete-pending"},
                          json={"opening_id": opening_id, "message": "저도 참여할래요"})
    assert pending.status_code == 201
    with world["factory"]() as db:
        member_facts_before = db.get(User, world["users"][1]).facts_revision

    assert client.delete(f"/api/v1/projects/{project['id']}?revision={project['revision']}", headers=member).status_code == 403
    assert client.delete(f"/api/v1/projects/{project['id']}?revision={project['revision']}", headers=creator).status_code == 204
    assert client.get(f"/api/v1/projects/{project['id']}", headers=member).status_code == 404
    assert client.get(f"/api/v1/recruitment-posts/{post['id']}", headers=applicant).status_code == 404
    assert client.get("/api/v1/recruitment-posts", headers=applicant).json()["items"] == []

    request_rows = client.get("/api/v1/me/project-requests", headers=applicant).json()["items"]
    cancelled = next(row for row in request_rows if row["id"] == pending.json()["id"])
    assert cancelled["status"] == "cancelled"
    assert cancelled["project_is_active"] is False
    with world["factory"]() as db:
        assert db.get(Project, project["id"]).visibility == "withdrawn"
        assert db.get(RecruitmentPost, post["id"]).status == "closed"
        assert db.get(ProjectRequest, pending.json()["id"]).status == "cancelled"
        assert len(list(db.scalars(select(ProjectMember).where(ProjectMember.project_id == project["id"])))) == 2
        assert db.get(User, world["users"][1]).facts_revision > member_facts_before
        member_notifications = list(db.scalars(select(Notification).where(Notification.user_id == world["users"][1])))
        assert all(row.href != f"/projects/{project['id']}" for row in member_notifications)
