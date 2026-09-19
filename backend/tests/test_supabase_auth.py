from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from sqlalchemy import func, select

from app.auth import digest
from app.config import Settings
from app.models import AuthSession, User, Verification

ORIGIN = {"Origin": "http://localhost:3000"}
SUBJECT = "75f5f2d6-b34f-4988-9dad-215aa8cf62d4"


@pytest.fixture
def google(monkeypatch):
    settings = Settings(_env_file=None, environment="test", app_origin="http://localhost:3000",
                        supabase_url="https://auth.example", supabase_publishable_key="fixture-publishable",
                        credential_encryption_key="fixture-encryption-key")
    monkeypatch.setattr("app.auth.get_settings", lambda: settings)
    monkeypatch.setattr("app.supabase_auth.get_settings", lambda: settings)
    state = {"email": "google@example.com", "subject": SUBJECT, "confirmed": True, "calls": [], "refresh": 0}

    def request(method, url, **kwargs):
        state["calls"].append((method, url, kwargs))
        assert kwargs["headers"]["apikey"] == "fixture-publishable"
        assert kwargs["follow_redirects"] is False
        if url.endswith("/user"):
            body = {"id": state["subject"], "email": state["email"],
                    "email_confirmed_at": "2026-01-01T00:00:00Z" if state["confirmed"] else None,
                    "identities": [{"provider": "google"}],
                    "user_metadata": {"full_name": "Google Fixture", "is_admin": True, "school_verified": True}}
        elif "/token?" in url:
            if "refresh_token" in url:
                state["refresh"] += 1
            index = 0 if state.get("reuse") else state["refresh"]
            body = {"access_token": f"fixture-access-{index}", "refresh_token": f"fixture-refresh-{index}", "expires_in": 3600}
        else:
            assert url.endswith("/logout?scope=local")
            body = {}
        return httpx.Response(200, json=body, request=httpx.Request(method, url))

    monkeypatch.setattr("app.supabase_auth.httpx.request", request)
    return state


def finish(client):
    return client.post("/api/v1/auth/google/callback", headers=ORIGIN, json={"code": "fixture-code-one-use"})


def test_google_pkce_verified_subject_refresh_and_logout(world, google):
    client = world["client"]
    assert client.post("/api/v1/auth/google").status_code == 403
    assert finish(client).status_code == 401
    assert not google["calls"]
    start = client.post("/api/v1/auth/google", headers=ORIGIN)
    query = parse_qs(urlsplit(start.json()["url"]).query)
    assert query["provider"] == ["google"] and query["code_challenge_method"] == ["s256"]
    assert query["redirect_to"] == ["http://localhost:3000/auth/callback"]
    assert "code_verifier" not in start.text
    assert "HttpOnly" in start.headers["set-cookie"] and "SameSite=lax" in start.headers["set-cookie"]
    result = finish(client)
    assert result.status_code == 200 and result.headers["cache-control"] == "no-store"
    access = {"Authorization": "Bearer " + result.json()["access_token"]}
    identity = client.get("/api/v1/me", headers=access).json()
    assert identity["google_connected"] and identity["id"] == result.json()["user_id"]
    assert identity["school_affiliations"] == []
    with world["factory"]() as db:
        user = db.get(User, identity["id"])
        assert user.supabase_user_id == SUBJECT and not user.is_admin
        session = db.scalar(select(AuthSession).where(AuthSession.user_id == user.id))
        assert session.auth_provider == "supabase" and session.refresh_hash == digest("fixture-refresh-0")
    refreshed = client.post("/api/v1/auth/refresh", headers=ORIGIN)
    assert refreshed.status_code == 200
    assert refreshed.json()["user_id"] == identity["id"]
    assert client.get("/api/v1/me", headers=access).status_code == 401
    latest = {"Authorization": "Bearer " + refreshed.json()["access_token"]}
    assert client.post("/api/v1/auth/logout", headers=ORIGIN | latest).status_code == 204
    assert client.get("/api/v1/me", headers=latest).status_code == 401
    assert any(url.endswith("/logout?scope=local") for _, url, _ in google["calls"])


def test_provider_reuse_interval_can_return_same_session(world, google):
    client = world["client"]
    client.post("/api/v1/auth/google", headers=ORIGIN)
    result = finish(client)
    google["reuse"] = True
    assert client.post("/api/v1/auth/refresh", headers=ORIGIN).status_code == 200
    headers = {"Authorization": "Bearer " + result.json()["access_token"]}
    assert client.get("/api/v1/me", headers=headers).status_code == 200
    assert client.post("/api/v1/auth/refresh", headers=ORIGIN).status_code == 200


def test_google_never_merges_by_email_and_rejects_unverified_identity(world, google):
    client = world["client"]
    google["email"] = "person0@university.example"
    client.post("/api/v1/auth/google", headers=ORIGIN)
    assert finish(client).status_code == 409
    with world["factory"]() as db:
        assert db.get(User, world["users"][0]).supabase_user_id is None
        assert db.scalar(select(func.count()).select_from(User)) == 3
    google["email"], google["confirmed"] = "unverified@example.com", False
    assert finish(client).status_code == 401


def test_existing_owner_explicit_link_preserves_id_and_needs_same_login(world, google):
    client = world["client"]
    client.post("/api/v1/auth/login-links", json={"email": "person0@university.example"})
    token = world["mailer"].deliveries[-1][2]
    local = client.post("/api/v1/auth/login-links/confirm", json={"token": token}).json()
    headers = ORIGIN | {"Authorization": "Bearer " + local["access_token"]}
    assert client.post("/api/v1/auth/google/link", headers=headers).status_code == 200
    cookie = client.cookies.get("dudri_refresh")
    client.cookies.delete("dudri_refresh")
    assert finish(client).status_code == 401
    assert not google["calls"]
    client.cookies.set("dudri_refresh", cookie, path="/api/v1/auth")
    linked = finish(client)
    assert linked.status_code == 200 and linked.json()["user_id"] == world["users"][0]
    with world["factory"]() as db:
        assert db.get(User, world["users"][0]).login_email == "person0@university.example"
        assert db.scalar(select(func.count()).select_from(User)) == 3
    # An old magic-link credential cannot bypass the linked Google identity.
    client.post("/api/v1/auth/login-links", json={"email": "person0@university.example"})
    token = world["mailer"].deliveries[-1][2]
    assert client.post("/api/v1/auth/login-links/confirm", json={"token": token}).status_code == 401


def test_school_confirmation_is_bound_to_requesting_user_and_never_changes_login(world):
    client, owner, other = world["client"], world["auth"](0), world["auth"](1)
    body = {"email": "separate@university.example", "university_id": world["university"], "enrollment_status": "graduate"}
    assert client.post("/api/v1/me/school-email-verifications", json=body).status_code == 401
    assert client.post("/api/v1/me/school-email-verifications", headers=owner, json=body).status_code == 202
    email, purpose, token = world["mailer"].deliveries[-1]
    assert purpose == "school_attach" and email == body["email"]
    path = "/api/v1/me/school-email-verifications/confirm"
    assert client.post(path, headers=other, json={"token": token}).status_code == 403
    result = client.post(path, headers=owner, json={"token": token})
    assert result.status_code == 200 and "access_token" not in result.json()
    assert client.post(path, headers=owner, json={"token": token}).status_code == 401
    identity = client.get("/api/v1/me", headers=owner).json()
    assert identity["login_email"] == "person0@university.example"
    assert identity["school_affiliations"][0]["enrollment_status"] == "graduate"
    with world["factory"]() as db:
        assert db.scalar(select(func.count()).select_from(User)) == 3
        assert db.scalar(select(Verification)).user_id == world["users"][0]


def test_company_confirmation_also_requires_requesting_account(world):
    client, owner, other = world["client"], world["auth"](0), world["auth"](1)
    client.post("/api/v1/auth/company-email-verifications", headers=owner,
                json={"email": "work@company.example", "company_name": "Fixture"})
    token = world["mailer"].deliveries[-1][2]
    path = "/api/v1/auth/company-email-verifications/confirm"
    assert client.post(path, json={"token": token}).status_code == 401
    assert client.post(path, headers=other, json={"token": token}).status_code == 403
    assert client.post(path, headers=owner, json={"token": token}).status_code == 200


def test_refresh_rejects_an_unexpected_provider_subject(world, google):
    client = world["client"]
    client.post("/api/v1/auth/google", headers=ORIGIN)
    assert finish(client).status_code == 200
    google["subject"] = "91415712-2c50-49a7-8d3d-c0bf5012fa55"
    assert client.post("/api/v1/auth/refresh", headers=ORIGIN).status_code == 401
    with world["factory"]() as db:
        assert db.scalar(select(func.count()).select_from(AuthSession)) == 1


def test_pkce_cookie_tampering_and_provider_errors_never_echo_secrets(world, google, monkeypatch):
    client = world["client"]
    client.post("/api/v1/auth/google", headers=ORIGIN)
    client.cookies.set("dudri_oauth", "fixture-tampered-cookie", path="/api/v1/auth")
    assert finish(client).status_code == 401
    assert not google["calls"]
    client.cookies.clear()
    client.post("/api/v1/auth/google", headers=ORIGIN)
    monkeypatch.setattr("app.supabase_auth.httpx.request", lambda method, url, **kwargs:
                        httpx.Response(400, text="fixture-secret-provider-body", request=httpx.Request(method, url)))
    result = finish(client)
    assert result.status_code == 401 and "fixture-secret" not in result.text
