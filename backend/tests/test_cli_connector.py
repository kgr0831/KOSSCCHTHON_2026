from sqlalchemy import select

from app.models import AISettings, CLIConnector, Job, SiteVersion


def connection(device_id):
    return {"provider": "codex", "device_id": device_id, "device_name": "fixture-pc",
            "executable_path": "C:/fixture/codex.js", "account_email": "fixture@example.com", "status": "connected",
            "models": ["fixture-model"], "default_model": "fixture-model", "checked_at": "2026-09-20T00:00:00+00:00"}


def generated():
    return {"document": {"title": "Portfolio", "headline": "My work", "summary": "Real facts",
            "sections": [{"id": "work", "heading": "Work", "body": "Built it", "items": ["One"]}]},
            "code": {"html": '<h1 data-field="title">Portfolio</h1><h2 data-field="headline">My work</h2><p data-field="summary">Real facts</p><main><section data-section="work"><h2 data-field="heading">Work</h2><p data-field="body">Built it</p><ul data-field="items"><li>One</li></ul></section></main>',
                     "css": "", "javascript": ""}}


def pair(world, monkeypatch):
    client, headers = world["client"], world["auth"](0)
    pairing = client.post("/api/v1/me/ai-cli-connectors/pairings", headers=headers, json={})
    assert pairing.status_code == 201
    device = "a" * 32
    activated = client.post("/api/v1/ai-cli-connectors/activate", headers={"X-Dudri-Pairing-Code": pairing.json()["pairing_code"]},
                            json={"device_id": device, "device_name": "fixture-pc", "connections": [connection(device)]})
    assert activated.status_code == 200, activated.text
    monkeypatch.setattr("app.ai_routes.cli_allowed", lambda: False)
    return headers, device, pairing.json()["pairing_code"], activated.json()["connector_token"], activated.json()["connector"]["id"]


def test_pairing_keeps_raw_codes_and_connector_tokens_out_of_database(world, monkeypatch):
    headers, device, pairing_code, token, connector_id = pair(world, monkeypatch)
    with world["factory"]() as db:
        row = db.get(CLIConnector, connector_id)
        assert row.device_id == device and row.token_hash != token and row.pairing_hash is None
        assert pairing_code not in str(row.token_hash) and token not in str(row.token_hash)
        settings = db.get(AISettings, world["users"][0])
        assert settings.cli_connections == [connection(device)]
    listed = world["client"].get("/api/v1/me/ai-cli-connectors", headers=headers)
    assert listed.status_code == 200 and listed.json()["items"][0]["online"]
    reused = world["client"].post("/api/v1/ai-cli-connectors/activate", headers={"X-Dudri-Pairing-Code": pairing_code},
                                  json={"device_id": device, "device_name": "fixture-pc", "connections": [connection(device)]})
    assert reused.status_code == 401
    assert world["client"].delete(f"/api/v1/me/ai-cli-connectors/{connector_id}", headers=headers).status_code == 204
    assert world["client"].post("/api/v1/ai-cli-connectors/jobs/claim", headers={"X-Dudri-Connector": token}).status_code == 401


def test_paired_pc_claims_only_its_document_job_and_saves_result(world, monkeypatch):
    headers, device, _, token, _ = pair(world, monkeypatch)
    settings = world["client"].get("/api/v1/me/ai-settings", headers=headers).json()
    saved = world["client"].put("/api/v1/me/ai-settings", headers=headers, json={
        "transport": "cli", "easy_model": "", "hard_model": "", "cli_provider": "codex",
        "cli_model": "fixture-model", "cli_device_id": device, "revision": settings["revision"],
    })
    assert saved.status_code == 200, saved.text
    created = world["client"].post("/api/v1/me/sites/portfolio/versions", headers=headers,
                                   json={"style_id": "linear", "consent": True, "revision": 0})
    assert created.status_code == 202, created.text
    with world["factory"]() as db:
        job = db.scalar(select(Job).where(Job.target_id == created.json()["id"]))
        assert job.execution_target == f"pc:{device}"
    claim = world["client"].post("/api/v1/ai-cli-connectors/jobs/claim", headers={"X-Dudri-Connector": token})
    assert claim.status_code == 200, claim.text
    job = claim.json()["job"]
    assert job and job["cli"]["connection"]["account_email"] == "fixture@example.com"
    done = world["client"].post(f'/api/v1/ai-cli-connectors/jobs/{job["job_id"]}/complete', headers={"X-Dudri-Connector": token},
                                 json={"lease_token": job["lease_token"], **generated(), "model": "fixture-model"})
    assert done.status_code == 200 and done.json()["status"] == "preview_ready"
    with world["factory"]() as db:
        assert db.get(SiteVersion, created.json()["id"]).status == "preview_ready"
        assert db.get(Job, job["job_id"]).status == "completed"
