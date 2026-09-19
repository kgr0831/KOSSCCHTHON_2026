from bs4 import BeautifulSoup
from sqlalchemy import select
from test_studio import fake_result

from app.ai import AIProvider
from app.models import Job
from app.site_render import update_fields
from app.worker import process_one


def test_layout_preserves_separate_parents_and_free_nodes():
    doc = fake_result().document.model_dump()
    doc["sections"].append({"id": "about", "heading": "About", "body": "About me", "items": []})
    markup = '<header><h1 data-field="title">Title</h1></header><main><div id="grid"><section data-section="work"><h2 data-field="heading">Work</h2></section><span id="decoration">Keep</span></div><aside id="about-container"><section data-section="about"><h2 data-field="heading">About</h2></section></aside></main>'
    code = {"html": markup, "css": ".grid{display:grid}", "javascript": ""}
    for preserve in (True, False):
        updated = update_fields(code, {**doc, "sections": list(reversed(doc["sections"]))}, doc, preserve_layout=preserve)
        soup = BeautifulSoup(updated["html"], "html.parser")
        assert soup.select_one('[data-section="work"]').parent["id"] == "grid"
        assert soup.select_one('[data-section="about"]').parent["id"] == "about-container"
        assert soup.select_one('#decoration').parent["id"] == "grid"
        if preserve:
            assert updated["css"] == code["css"]


def test_design_upload_is_private_persistent_and_retryable(world, monkeypatch):
    client, headers = world["client"], world["auth"](0)
    body = {"file": ("../../custom.md", b"# A custom portfolio\nUse teal cards and generous spacing", "text/markdown")}
    assert client.post("/api/v1/portfolio-styles/upload", headers=headers, files=body).status_code == 422
    response = client.post("/api/v1/portfolio-styles/upload", headers=headers, files=body, data={"consent": "true"})
    assert response.status_code == 202
    style = response.json()
    assert style["source_file"] == "custom.md" and style["id"].startswith("uploaded-")
    assert client.get(f'/api/v1/portfolio-styles/{style["id"]}', headers=world["auth"](1)).status_code == 404
    assert not client.get("/api/v1/me/source-materials", headers=headers).json()["items"]
    analyze = client.post("/api/v1/me/analysis-runs", headers=headers, json={"material_ids": [style["id"].removeprefix("uploaded-")], "consent": True})
    assert analyze.status_code == 409
    def fail(*a, **k):
        raise RuntimeError("Provider failed")
    monkeypatch.setattr(AIProvider, "generate", fail)
    assert process_one(world["factory"])
    assert client.get(f'/api/v1/portfolio-styles/{style["id"]}', headers=headers).json()["status"] == "failed"
    with world["factory"].begin() as db:
        db.scalar(select(Job).where(Job.kind == "style")).execution_target = "pc:previous-installation"
    retry = client.post(f'/api/v1/portfolio-styles/{style["id"]}/preview', headers=headers, json={"consent": True})
    assert retry.status_code == 202
    with world["factory"]() as db:
        from app.local_runtime import execution_target
        assert db.scalar(select(Job).where(Job.kind == "style")).execution_target == execution_target()
    monkeypatch.setattr(AIProvider, "generate", lambda *a, **k: fake_result().code)
    monkeypatch.setattr("app.design_upload.reference_images", lambda code: {"reference_image": "data:image/png;base64,fixture", "mobile_reference_image": "data:image/png;base64,fixture-mobile"})
    assert process_one(world["factory"])
    loaded = client.get(f'/api/v1/portfolio-styles/{style["id"]}', headers=headers).json()
    assert loaded["status"] == "ready" and loaded["reference_image"]
    with world["factory"]() as db:
        jobs = list(db.scalars(select(Job).where(Job.kind == "style")))
        assert len(jobs) == 1 and jobs[0].attempts == 2
    created = client.post("/api/v1/me/sites/portfolio/versions", headers=headers, json={"style_id": style["id"], "consent": True, "revision": 0})
    assert created.status_code == 202
    assert "Use teal cards" in created.json()["public_input_snapshot"]["style_markdown"]


def test_nested_project_cards_survive_parent_copy_updates():
    document = fake_result().document.model_dump()
    document["sections"] = [
        {"id": "collection", "heading": "Selected projects", "body": "Updated intro", "items": []},
        {"id": "work", "heading": "Campus app", "body": "My contribution", "items": []},
    ]
    markup = '<h1>Portfolio</h1><section data-section="collection"><h2 data-field="heading">Projects</h2><div data-field="body">Old intro<div class="project-grid"><article data-section="work"><h3 data-field="heading">Old title</h3><p data-field="body">Old body</p></article></div></div></section>'
    for preserve in (True, False):
        result = update_fields({"html": markup, "css": "", "javascript": ""}, document, preserve_layout=preserve)
        soup = BeautifulSoup(result["html"], "html.parser")
        assert soup.select_one('.project-grid > [data-section="work"]')
        assert soup.select_one('[data-section="work"] h3').text == "Campus app"
        assert "Updated intro" in soup.text and "My contribution" in soup.text


def test_upload_limits_and_kind_specific_prompts(world, monkeypatch):
    headers, client = world["auth"](0), world["client"]
    for filename, raw in (("bad.html", b"test"), ("large.md", b"x" * 65537), ("empty.md", b""), ("wrong.md", b"\xff\xfe")):
        assert client.post("/api/v1/portfolio-styles/upload", headers=headers, files={"file": (filename, raw)}, data={"consent": "true"}).status_code == 422
    calls = []
    def generate(prompt, inputs, schema, **kwargs):
        calls.append((prompt, inputs["kind"]))
        return fake_result()
    monkeypatch.setattr(AIProvider, "generate", lambda self, *a, **k: generate(*a, **k))
    for kind in ("portfolio", "cv"):
        assert client.post(f"/api/v1/me/sites/{kind}/versions", headers=headers, json={"style_id": "linear", "consent": True, "revision": 0}).status_code == 202
        assert process_one(world["factory"])
    assert "case study" in calls[0][0] and "A4" in calls[1][0]
    assert calls[0][0] != calls[1][0]
