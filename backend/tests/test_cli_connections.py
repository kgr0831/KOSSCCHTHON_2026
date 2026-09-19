import json
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.ai import AIProvider
from app.cli_metadata import probe_cli
from app.config import Settings
from app.local_runtime import device_id
from app.models import AISettings, Job
from app.worker import process_one


@pytest.fixture
def connection():
    return {"provider": "codex", "device_id": device_id(), "device_name": "fixture-pc",
            "executable_path": "C:/fixture/codex.js", "account_email": "fixture@example.com", "status": "connected",
            "models": ["fixture-model"], "default_model": "fixture-model", "checked_at": "2026-09-20T00:00:00Z"}


def test_cli_metadata_is_owned_and_executable_credentials_cannot_be_supplied(world, monkeypatch, connection):
    monkeypatch.setattr("app.cli_metadata.probe_cli", lambda _: connection)
    client, auth = world["client"], world["auth"]
    a, b = auth(0), auth(1)
    response = client.post("/api/v1/me/ai-cli-connections/codex/check", headers=a)
    assert response.status_code == 200
    body = response.json()
    assert body["cli_connections"] == [{**connection, "current_pc": True}]
    assert client.get("/api/v1/me/ai-settings", headers=b).json()["cli_connections"] == []
    with world["factory"]() as db:
        assert db.get(AISettings, world["users"][0]).cli_connections == [connection]
    settings = {"transport": "cli", "cli_provider": "codex", "cli_model": "fixture-model", "revision": body["revision"]}
    for extra in ({"cli_connections": [connection]}, {"executable_path": "C:/evil.exe"}, {"api_key": "fixture-secret"}):
        rejected = client.put("/api/v1/me/ai-settings", headers=a, json={**settings, **extra})
        assert rejected.status_code == 422 and "fixture-secret" not in rejected.text
    assert client.put("/api/v1/me/ai-settings", headers=a, json=settings).status_code == 200


def test_second_pc_must_check_its_own_login_and_cloud_preserves_metadata(world, monkeypatch, connection):
    with world["factory"].begin() as db:
        db.add(AISettings(user_id=world["users"][0], cli_provider="claude", cli_model="sonnet", cli_connections=[connection]))
    client, auth = world["client"], world["auth"](0)
    monkeypatch.setattr("app.ai_routes.device_id", lambda: "another-pc")
    body = client.get("/api/v1/me/ai-settings", headers=auth).json()
    assert not body["cli_connections"][0]["current_pc"]
    edit = {"transport": "cli", "cli_provider": "codex", "revision": body["revision"]}
    assert client.put("/api/v1/me/ai-settings", headers=auth, json=edit).status_code == 409
    monkeypatch.setattr("app.ai_routes.cli_allowed", lambda: False)
    monkeypatch.setattr("app.cli_metadata.probe_cli", lambda _: pytest.fail("Cloud must never launch a CLI"))
    assert client.post("/api/v1/me/ai-cli-connections/codex/check", headers=auth).status_code == 403
    assert client.put("/api/v1/me/ai-settings", headers=auth, json=edit).status_code == 403
    response = client.put("/api/v1/me/ai-settings", headers=auth, json={**edit, "transport": "api", "cli_model": "malicious"})
    assert response.status_code == 200
    assert response.json()["cli_provider"] == "claude" and response.json()["cli_model"] == "sonnet"
    assert response.json()["cli_connections"][0]["account_email"] == connection["account_email"]


def test_official_status_projects_only_metadata(monkeypatch, tmp_path):
    monkeypatch.setattr("app.cli_metadata.get_settings", lambda: Settings(_env_file=None, project_root=tmp_path))
    monkeypatch.setattr("app.cli_metadata.cli_command", lambda _: ["node", "C:/fixture/codex.js"])
    monkeypatch.setattr("app.cli_metadata.codex_status", lambda *_: (
        {"type": "chatgpt", "email": "fixture@example.com", "accessToken": "fixture-secret", "planType": "pro"},
        [{"model": "fixture-model", "isDefault": True, "token": "fixture-secret"}]))
    result = probe_cli("codex")
    assert result["status"] == "connected" and result["default_model"] == "fixture-model"
    assert "fixture-secret" not in json.dumps(result) and "accessToken" not in result
    monkeypatch.setattr("app.cli_metadata.codex_status", lambda *_: ({"type": "apiKey"}, []))
    assert probe_cli("codex")["status"] == "needs_login"


def test_cli_account_switch_refuses_generation(monkeypatch, connection):
    monkeypatch.setattr("app.ai.cli_command", lambda _: ["fixture-codex"])
    monkeypatch.setattr("app.cli_metadata.probe_cli", lambda _: {**connection, "account_email": "other@example.com"})
    monkeypatch.setattr("app.ai.subprocess.Popen", lambda *_a, **_k: pytest.fail("No generation after an account switch"))
    with pytest.raises(HTTPException) as exc:
        AIProvider("cli", cli_connection=connection)._cli("fixture", {}, "hard")
    assert exc.value.status_code == 409


def test_codex_uses_stdin_disables_tools_and_does_not_inherit_server_secrets(monkeypatch, tmp_path, connection):
    from app.ai import cli_environment
    settings = Settings(_env_file=None, project_root=tmp_path)
    monkeypatch.setattr("app.ai.get_settings", lambda: settings)
    monkeypatch.setattr("app.ai.cli_command", lambda _: ["node", "C:/fixture/codex.js"])
    monkeypatch.setattr("app.cli_metadata.probe_cli", lambda _: connection)
    for name in ("DUDRI_DATABASE_URL", "DUDRI_MAIL_API_KEY", "OPENAI_API_KEY", "CODEX_API_KEY"):
        monkeypatch.setenv(name, "fixture-secret")
    assert "fixture-secret" not in json.dumps(cli_environment("codex"))
    captured = {}

    class Process:
        returncode = 0

        def __init__(self, args, **kwargs):
            captured.update(args=args, **kwargs)

        def communicate(self, prompt, timeout):
            captured["prompt"] = prompt
            return '{"connected":true}', ""

    monkeypatch.setattr("app.ai.subprocess.Popen", Process)
    provider = AIProvider("cli", cli_connection=connection)
    assert provider._cli("fixture prompt & $(never-execute)", {}, "hard") == '{"connected":true}'
    assert "$(never-execute)" not in " ".join(captured["args"]) and "$(never-execute)" in captured["prompt"]
    assert not captured.get("shell")
    for argument in ("--ephemeral", "--ignore-user-config", "read-only", "features.shell_tool=false", "features.apps=false", "features.plugins=false", "features.hooks=false"):
        assert argument in captured["args"]
    assert not list(Path(tmp_path).rglob("request-*"))


def test_codex_reference_images_use_ephemeral_request_files(monkeypatch, tmp_path, connection):
    settings = Settings(_env_file=None, project_root=tmp_path)
    monkeypatch.setattr("app.ai.get_settings", lambda: settings)
    monkeypatch.setattr("app.ai.cli_command", lambda _: ["node", "C:/fixture/codex.js"])
    monkeypatch.setattr("app.cli_metadata.probe_cli", lambda _: connection)
    captured = {}

    class Process:
        returncode = 0

        def __init__(self, args, **kwargs):
            captured.update(args=args, **kwargs)

        def communicate(self, prompt, timeout):
            captured["prompt"] = prompt
            return '{"connected":true}', ""

    monkeypatch.setattr("app.ai.subprocess.Popen", Process)
    result = AIProvider("cli", cli_connection=connection)._cli("fixture", {}, "hard", [{
        "name": "private.png", "content_type": "image/png", "content": b"\x89PNG\r\n\x1a\nfixture",
    }])
    image_path = Path(captured["args"][captured["args"].index("--image") + 1])
    assert result == '{"connected":true}' and image_path.suffix == ".png"
    assert not image_path.exists() and not list(Path(tmp_path).rglob("request-*"))
    assert "private.png" not in captured["prompt"]


def test_worker_never_claims_other_pc_or_cloud_jobs(world, monkeypatch):
    monkeypatch.setattr("app.worker.get_settings", lambda: Settings(_env_file=None, database_url="postgresql://localhost/fixture"))
    monkeypatch.setattr("app.worker.execution_target", lambda: "pc:mine")
    with world["factory"].begin() as db:
        db.add_all([Job(user_id=world["users"][0], kind="site", target_id=target, execution_target=target)
                    for target in ("pc:other", "server")])
    assert not process_one(world["factory"])
    monkeypatch.setattr("app.worker.execution_target", lambda: "server")
    with world["factory"].begin() as db:
        cloud = db.query(Job).filter_by(execution_target="server").one()
        cloud.status = "completed"
    assert not process_one(world["factory"])
