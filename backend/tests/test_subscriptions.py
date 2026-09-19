from sqlalchemy import select

from app.models import Job, Preference, Profile, SiteVersion, User
from app.worker import process_one


def select_plan(world, index: int, plan: str):
    response = world["client"].put("/api/v1/me/subscription", headers=world["auth"](index), json={"plan": plan})
    assert response.status_code == 200, response.text
    assert response.json() == {"plan": plan}


def document_request(kind="portfolio", revision=0):
    return {"style_id": "linear", "consent": True, "revision": revision}


def test_plan_defaults_to_free_and_selection_is_private(world):
    with world["factory"].begin() as db:
        free = User(login_email="free@university.example")
        db.add(free)
        db.flush()
        db.add_all([Profile(user_id=free.id, display_name="Free"), Preference(user_id=free.id)])
        assert free.subscription_plan == "free"

    assert world["client"].get("/api/v1/me/subscription", headers=world["auth"](0)).json() == {"plan": "premium"}
    select_plan(world, 0, "premium")
    assert world["client"].get("/api/v1/me", headers=world["auth"](0)).json()["subscription_plan"] == "premium"
    assert world["client"].get("/api/v1/me/subscription", headers=world["auth"](1)).json() == {"plan": "premium"}
    assert world["client"].put("/api/v1/me/subscription", headers=world["auth"](0), json={"plan": "gold"}).status_code == 422


def test_free_cannot_start_ai_document_or_profile_generation(world):
    select_plan(world, 0, "free")
    headers, client = world["auth"](0), world["client"]
    for kind in ("portfolio", "profile_pr", "cv", "cover_letter"):
        result = client.post(f"/api/v1/me/sites/{kind}/versions", headers=headers, json=document_request(kind))
        assert result.status_code == 403, result.text
    assert client.post("/api/v1/ai/writing-drafts", headers=headers,
                       json={"kind": "profile", "text": "A real experience"}).status_code == 403
    assert client.post("/api/v1/me/analysis-runs", headers=headers,
                       json={"material_ids": ["not-used"], "consent": True}).status_code == 403
    assert client.post("/api/v1/portfolio-styles/upload", headers=headers, data={"consent": "true"},
                       files={"file": ("style.md", b"# style", "text/markdown")}).status_code == 403


def test_premium_can_queue_document_generation(world):
    client, headers = world["client"], world["auth"](0)
    assert client.post("/api/v1/me/sites/portfolio/versions", headers=headers, json=document_request()).status_code == 202
    select_plan(world, 0, "premium")
    assert client.post("/api/v1/me/sites/cv/versions", headers=headers, json=document_request()).status_code == 202


def test_worker_fails_queued_document_when_plan_changes_to_free(world):
    client, headers = world["client"], world["auth"](0)
    created = client.post("/api/v1/me/sites/portfolio/versions", headers=headers, json=document_request())
    assert created.status_code == 202
    select_plan(world, 0, "free")
    assert process_one(world["factory"])
    with world["factory"]() as db:
        version = db.get(SiteVersion, created.json()["id"])
        job = db.scalar(select(Job).where(Job.target_id == version.id))
        assert version.status == "failed"
        assert job.status == "failed"
