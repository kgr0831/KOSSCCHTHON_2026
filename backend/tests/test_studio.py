from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.ai import AIProvider, choose_model
from app.common import facts_changed, lock_user
from app.db import get_db
from app.models import Job, Material, Profile, SiteVersion, User
from app.models import now as utc_now
from app.site_render import read_fields, update_fields
from app.site_server import app as public_app
from app.sites import Generated
from app.worker import process_one


def fake_result():
    return Generated.model_validate({"document": {"title": "Portfolio", "headline": "My work", "summary": "Real facts",
        "sections": [{"id": "work", "heading": "Work", "body": "Made a project", "items": ["One"]}]},
        "code": {"html": '<h1 data-field="title">Portfolio</h1><h2 data-field="headline">My work</h2><p data-field="summary">Real facts</p><main><section data-section="work"><h2 data-field="heading">Work</h2><p data-field="body">Made a project</p><ul data-field="items"><li>One</li></ul></section></main><aside id="free-code">Keep this</aside>',
                 "css": "#free-code{color:red}", "javascript": "document.body.dataset.ready = 'yes';"}})


def submit(world, kind="portfolio", revision=0):
    response = world["client"].post(f"/api/v1/me/sites/{kind}/versions", headers=world["auth"](0),
                                   json={"style_id": "linear", "consent": True, "revision": revision})
    assert response.status_code == 202, response.text
    return response.json()


def test_durable_site_owner_publish_revoke_and_private_facts(world, monkeypatch):
    monkeypatch.setattr(AIProvider, "generate", lambda *a, **k: fake_result())
    with world["factory"].begin() as db:
        profile = db.get(Profile, world["users"][0])
        profile.bio, profile.bio_is_public = "PRIVATE FACT MUST NOT LEAK", False
    created = submit(world)
    assert "PRIVATE FACT" not in str(created["public_input_snapshot"])
    assert world["client"].get(f'/api/v1/me/site-versions/{created["id"]}', headers=world["auth"](1)).status_code == 403
    # New DB session simulates a request ending before a separate worker runs.
    assert process_one(world["factory"])
    version = world["client"].get(f'/api/v1/me/site-versions/{created["id"]}', headers=world["auth"](0)).json()
    assert version["status"] == "preview_ready" and "Keep this" in version["preview_html"]
    with world["factory"]() as db:
        assert db.get(SiteVersion, created["id"]).code["html"]
    result = world["client"].post(f'/api/v1/me/site-versions/{created["id"]}/publish', headers=world["auth"](0), json={"revision": 1})
    assert result.status_code == 200, result.text
    public_app.dependency_overrides[get_db] = world["client"].app.dependency_overrides[get_db]
    try:
        client = TestClient(public_app)
        response = client.get(f'/s/{result.json()["slug"]}')
        assert response.status_code == 200
        assert "frame-src 'self'" in response.headers["content-security-policy"]
        assert 'sandbox="allow-scripts"' in response.text
        with world["factory"].begin() as db:
            lock_user(db, world["users"][0])
            facts_changed(db, world["users"][0])
        assert client.get(f'/s/{result.json()["slug"]}').status_code == 404
        assert world["client"].post(f'/api/v1/me/site-versions/{created["id"]}/publish', headers=world["auth"](0), json={"revision": 3}).status_code == 409
    finally:
        public_app.dependency_overrides.clear()


def test_expired_lease_recovery_and_conflicting_generation(world, monkeypatch):
    monkeypatch.setattr(AIProvider, "generate", lambda *a, **k: fake_result())
    first = submit(world)
    with world["factory"].begin() as db:
        job = db.scalar(select(Job).where(Job.target_id == first["id"]))
        job.status, job.lease_token, job.lease_until = "running", "dead-worker", utc_now() - timedelta(seconds=10)
    second = submit(world, revision=1)
    assert process_one(world["factory"])
    with world["factory"]() as db:
        assert db.get(SiteVersion, first["id"]).status == "conflicted"
    assert process_one(world["factory"])
    with world["factory"]() as db:
        assert db.get(SiteVersion, second["id"]).status == "preview_ready"
    assert not process_one(world["factory"])


def test_all_document_kinds_persist_without_publication(world, monkeypatch):
    monkeypatch.setattr(AIProvider, "generate", lambda *a, **k: fake_result())
    for kind in ("portfolio", "profile_pr", "cv", "cover_letter"):
        submit(world, kind)
        assert process_one(world["factory"])
    result = world["client"].get("/api/v1/me/sites", headers=world["auth"](0)).json()["items"]
    assert {x["site_kind"] for x in result} == {"portfolio", "profile_pr", "cv", "cover_letter"}
    assert all(x["versions"][0]["status"] == "preview_ready" and not x["published_version_id"] for x in result)


def test_gui_preserves_free_code_and_css_and_reorders_sections():
    generated = fake_result()
    doc = generated.document.model_dump()
    generated.code.html = '<header data-section="hero"><h1>Preserve hero</h1></header>' + generated.code.html
    code = update_fields(generated.code.model_dump(), doc)
    code["css"] += "\n.custom-added-later{color:green}"
    code["html"] = code["html"].replace("My work", "Edited in code")
    parsed = read_fields(code, doc)
    assert parsed["headline"] == "Edited in code"
    parsed["title"] = "New title"
    parsed["sections"].insert(0, {"id": "intro", "heading": "Intro", "body": "First", "items": []})
    updated = update_fields(code, parsed)
    assert "custom-added-later" in updated["css"] and "free-code" in updated["html"]
    assert updated["html"].index('data-section="intro"') < updated["html"].index('data-section="work"')
    assert updated["javascript"] == code["javascript"]
    assert '<header data-section="hero">' in updated["html"]
    assert 'Preserve hero' in updated["html"]


def test_invalid_code_saved_but_not_publishable_and_revision_cas(world, monkeypatch):
    monkeypatch.setattr(AIProvider, "generate", lambda *a, **k: fake_result())
    created = submit(world)
    process_one(world["factory"])
    path = f'/api/v1/me/site-versions/{created["id"]}/revisions'
    body = {"revision": 1, "mode": "code", "code": {**fake_result().code.model_dump(), "javascript": "const broken = ;"}}
    changed = world["client"].post(path, headers=world["auth"](0), json=body)
    assert changed.status_code == 201 and changed.json()["status"] == "invalid"
    assert world["client"].post(path, headers=world["auth"](0), json=body).status_code == 409
    assert world["client"].post(f'/api/v1/me/site-versions/{changed.json()["id"]}/publish', headers=world["auth"](0), json={"revision": 2}).status_code == 409


def test_analysis_requires_consent_and_withdrawal_prevents_apply(world, monkeypatch):
    from app.materials import AnalysisResult
    headers = world["auth"](0)
    material = world["client"].post("/api/v1/me/source-materials", headers=headers,
                                    json={"display_name": "CV", "text": "I built a campus app."}).json()
    body = {"material_ids": [material["id"]]}
    assert world["client"].post("/api/v1/me/analysis-runs", headers=headers, json=body).status_code == 422
    result = AnalysisResult.model_validate({"suggestions": [{"kind": "bio", "title": "About", "text": "Campus app developer",
        "material_id": material["id"], "quote": "I built a campus app."}]})
    monkeypatch.setattr(AIProvider, "generate", lambda *a, **k: result)
    assert world["client"].post("/api/v1/me/analysis-runs", headers=headers, json={**body, "consent": True}).status_code == 202
    process_one(world["factory"])
    proposal = world["client"].get("/api/v1/me/suggestions", headers=headers).json()["items"][0]
    with world["factory"]() as db:
        assert db.get(Profile, world["users"][0]).bio != "Campus app developer"
    world["client"].delete(f'/api/v1/me/source-materials/{material["id"]}', headers=headers)
    with world["factory"]() as db:
        assert db.get(Material, material["id"]).text_content is None
    assert world["client"].post(f'/api/v1/me/suggestions/{proposal["id"]}/decision', headers=headers,
                               json={"decision": "accepted", "revision": 1, "text": "Campus app developer"}).status_code == 409


def test_model_routing_uses_authorized_haiku_fallback(monkeypatch):
    monkeypatch.setattr("app.ai.model_ids", lambda: ["claude-haiku-4-5", "claude-sonnet-5", "claude-opus-5"])
    assert "haiku" in choose_model("easy") and "sonnet" in choose_model("hard")
    monkeypatch.setattr("app.ai.model_ids", lambda: ["claude-haiku-4-5", "gemini-2.5-flash"])
    assert "gemini" in choose_model("easy")


def test_seed_idempotent_preserves_user_changes(world):
    from app.seed import DEMO_USERS, seed
    with world["factory"].begin() as db:
        seed(db)
    with world["factory"].begin() as db:
        db.get(Profile, DEMO_USERS[0]).bio = "User edited this"
    with world["factory"].begin() as db:
        seed(db)
    with world["factory"]() as db:
        assert db.get(Profile, DEMO_USERS[0]).bio == "User edited this"
        assert len(list(db.scalars(select(User).where(User.id.in_(DEMO_USERS))))) == 8
