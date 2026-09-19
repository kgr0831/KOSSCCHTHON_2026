from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from sqlalchemy import func, select

from app.config import Settings
from app.models import AnalysisRun, ExternalAccount, Material

ORIGIN = {"Origin": "http://localhost:3000"}
GITHUB_CONNECT = "/api/v1/me/external-accounts/github/connect"
GITHUB_CALLBACK = "/api/v1/auth/github/callback"


@pytest.fixture
def github(monkeypatch):
    settings = Settings(
        _env_file=None,
        environment="test",
        app_origin="http://localhost:3000",
        credential_encryption_key="fixture-encryption-key",
        github_client_id="fixture-client-id",
        github_client_secret="fixture-client-secret",
    )
    for module in ("app.auth", "app.external_accounts", "app.supabase_auth"):
        monkeypatch.setattr(f"{module}.get_settings", lambda: settings)
    state = {"calls": []}
    repositories = {
        101: {
            "id": 101,
            "name": "private-project",
            "full_name": "fixture/private-project",
            "private": True,
            "html_url": "https://github.com/fixture/private-project",
            "description": "Private fixture project",
            "language": "Python",
            "updated_at": "2026-09-20T00:00:00Z",
        },
        202: {
            "id": 202,
            "name": "public-project",
            "full_name": "fixture/public-project",
            "private": False,
            "html_url": "https://github.com/fixture/public-project",
            "description": "Public fixture project",
            "language": "TypeScript",
            "updated_at": "2026-09-19T00:00:00Z",
        },
    }

    def request(method, url, **kwargs):
        state["calls"].append((method, url, kwargs))
        if url == "https://github.com/login/oauth/access_token":
            assert kwargs["headers"]["Accept"] == "application/json"
            assert kwargs["follow_redirects"] is False
            assert kwargs["data"]["code_verifier"]
            return httpx.Response(200, json={"access_token": "not-a-real-github-token"},
                                  request=httpx.Request(method, url))
        assert kwargs["headers"]["Authorization"].startswith("Bearer ")
        assert kwargs["follow_redirects"] is False
        if url == "https://api.github.com/user":
            payload = {"id": 12345, "login": "fixture-login"}
        elif "/user/repos?" in url:
            payload = list(repositories.values()) if "page=1" in url else []
        elif url.startswith("https://api.github.com/repositories/"):
            payload = repositories[int(url.rsplit("/", 1)[1])]
        else:
            raise AssertionError(f"Unexpected GitHub URL: {url}")
        return httpx.Response(200, json=payload, request=httpx.Request(method, url))

    monkeypatch.setattr("app.external_accounts.httpx.request", request)
    return state


def signed_in(client, world, index=0):
    client.post("/api/v1/auth/login-links", json={"email": f"person{index}@university.example"})
    token = world["mailer"].deliveries[-1][2]
    result = client.post("/api/v1/auth/login-links/confirm", json={"token": token})
    assert result.status_code == 200
    return {"Authorization": "Bearer " + result.json()["access_token"]}


def connect_github(client, headers):
    started = client.post(GITHUB_CONNECT, headers=ORIGIN | headers)
    assert started.status_code == 200
    query = parse_qs(urlsplit(started.json()["url"]).query)
    assert query["scope"] == ["read:user repo"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["redirect_uri"] == ["http://localhost:3000/github/callback"]
    assert "client_secret" not in started.text
    assert "HttpOnly" in started.headers["set-cookie"]
    return client.post(GITHUB_CALLBACK, headers=ORIGIN,
                       json={"code": "fixture-authorization-code", "state": query["state"][0]})


def test_github_connection_binds_state_to_refresh_family_and_hides_credential(world, github):
    client = world["client"]
    owner = signed_in(client, world)
    started = client.post(GITHUB_CONNECT, headers=ORIGIN | owner)
    assert started.status_code == 200
    query = parse_qs(urlsplit(started.json()["url"]).query)
    assert "not-a-real-github-token" not in started.text

    # Replacing the refresh cookie with another account's session prevents the
    # callback before a provider token exchange can occur.
    signed_in(client, world, 1)
    rejected = client.post(GITHUB_CALLBACK, headers=ORIGIN,
                           json={"code": "fixture-authorization-code", "state": query["state"][0]})
    assert rejected.status_code == 401
    assert not github["calls"]

    # Restarting with the active owner session succeeds and stores only an
    # encrypted credential in the database.
    owner = signed_in(client, world)
    connected = connect_github(client, owner)
    assert connected.status_code == 200
    assert connected.json()["provider"] == "github"
    assert "encrypted_credential" not in connected.json()
    assert "not-a-real-github-token" not in connected.text
    with world["factory"]() as db:
        account = db.scalar(select(ExternalAccount).where(ExternalAccount.user_id == world["users"][0]))
        assert account.encrypted_credential != "not-a-real-github-token"
        assert account.login == "fixture-login"


def test_github_callback_rejects_tampered_state_before_provider_exchange(world, github):
    client = world["client"]
    owner = signed_in(client, world)
    started = client.post(GITHUB_CONNECT, headers=ORIGIN | owner)
    query = parse_qs(urlsplit(started.json()["url"]).query)
    client.cookies.set("dudri_github_oauth", "fixture-tampered-cookie", path="/api/v1/auth/github")
    response = client.post(GITHUB_CALLBACK, headers=ORIGIN,
                           json={"code": "fixture-authorization-code", "state": query["state"][0]})
    assert response.status_code == 401
    assert not github["calls"]


def test_github_lists_and_syncs_only_selected_repositories_without_analysis(world, github):
    client = world["client"]
    owner = signed_in(client, world)
    assert connect_github(client, owner).status_code == 200
    github["calls"].clear()

    listed = client.get("/api/v1/me/external-accounts/github/repositories", headers=owner)
    assert listed.status_code == 200
    assert {item["repository_id"] for item in listed.json()["items"]} == {101, 202}
    assert {item["private"] for item in listed.json()["items"]} == {True, False}
    with world["factory"]() as db:
        assert db.scalar(select(func.count()).select_from(Material)) == 0

    synced = client.post("/api/v1/me/external-accounts/github/sync", headers=owner,
                         json={"repository_ids": [101]})
    assert synced.status_code == 200
    material_id = synced.json()["items"][0]["id"]
    assert synced.json()["items"][0]["canonical_url"] == "https://github.com/fixture/private-project"
    with world["factory"]() as db:
        material = db.get(Material, material_id)
        assert material.material_kind == "github_repository"
        assert material.is_private and material.metadata_json["repository_id"] == 101
        assert "GitHub repository metadata" in material.text_content
        assert db.scalar(select(func.count()).select_from(AnalysisRun)) == 0

    # Repeating the same explicit choice is an idempotent source upsert.
    repeated = client.post("/api/v1/me/external-accounts/github/sync", headers=owner,
                           json={"repository_ids": [101]})
    assert repeated.status_code == 200
    assert repeated.json()["items"][0]["id"] == material_id
    assert client.post("/api/v1/me/external-accounts/github/sync", headers=owner,
                       json={"repository_ids": [101, 101]}).status_code == 422


def test_external_account_listing_and_deletion_are_owner_scoped(world, github):
    client = world["client"]
    owner = signed_in(client, world)
    connection = connect_github(client, owner)
    account_id = connection.json()["id"]
    material_id = client.post("/api/v1/me/external-accounts/github/sync", headers=owner,
                              json={"repository_ids": [101]}).json()["items"][0]["id"]
    assert client.get("/api/v1/me/external-accounts", headers=owner).json()["items"][0]["id"] == account_id
    other = world["auth"](1)
    assert client.get("/api/v1/me/external-accounts", headers=other).json()["items"] == []
    assert client.delete(f"/api/v1/me/external-accounts/{account_id}", headers=other).status_code == 403
    assert client.delete(f"/api/v1/me/external-accounts/{account_id}", headers=owner).status_code == 204
    assert client.get("/api/v1/me/external-accounts", headers=owner).json()["items"] == []
    with world["factory"]() as db:
        assert db.get(Material, material_id).external_account_id is None


def test_linkedin_is_a_private_url_only_source_with_no_provider_fetch(world, monkeypatch):
    monkeypatch.setattr("app.external_accounts.httpx.request", lambda *_args, **_kwargs:
                        pytest.fail("LinkedIn URL registration must not fetch a provider"))
    client, owner = world["client"], world["auth"](0)
    created = client.post("/api/v1/me/source-materials/linkedin", headers=owner,
                          json={"url": "https://linkedin.com/in/fixture-profile/?tracking=discard"})
    assert created.status_code == 201
    material_id = created.json()["id"]
    assert created.json()["canonical_url"] == "https://www.linkedin.com/in/fixture-profile"
    with world["factory"]() as db:
        material = db.get(Material, material_id)
        assert material.material_kind == "linkedin"
        assert material.is_private and material.text_content is None and material.external_account_id is None

    updated = client.post("/api/v1/me/source-materials/linkedin", headers=owner,
                          json={"url": "https://www.linkedin.com/in/fixture-profile"})
    assert updated.status_code == 200 and updated.json()["id"] == material_id
    assert client.post("/api/v1/me/source-materials/linkedin", headers=owner,
                       json={"url": "http://linkedin.com/in/not-https"}).status_code == 422
    assert client.post("/api/v1/me/source-materials/linkedin", headers=owner,
                       json={"url": "https://linkedin.example/in/not-linkedin"}).status_code == 422
