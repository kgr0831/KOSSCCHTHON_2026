"""Owner-scoped GitHub sources and URL-only LinkedIn source registration.

GitHub credentials stay server-side in ``ExternalAccount``.  A repository is
only copied into ``Material`` after the user explicitly selects it; creating a
material never starts an AI analysis run.
"""
import base64
import hashlib
import json
import secrets
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit

import httpx
from cryptography.fernet import InvalidToken
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import Field, field_validator
from sqlalchemy import select, update

from .auth import Actor, Input, check_origin, digest
from .common import DB, data, lock_user, owner, required
from .config import get_settings
from .models import AuthSession, ExternalAccount, Material, User, now
from .supabase_auth import cookie_session, flow_cipher

router = APIRouter(prefix="/api/v1")

GITHUB_API_ORIGIN = "https://api.github.com"
GITHUB_AUTHORIZE_ORIGIN = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_ORIGIN = "https://github.com/login/oauth/access_token"
GITHUB_COOKIE = "dudri_github_oauth"
GITHUB_COOKIE_PATH = "/api/v1/auth/github"
GITHUB_COOKIE_TTL_SECONDS = 600
GITHUB_REPOSITORY_PAGE_SIZE = 100
GITHUB_REPOSITORY_PAGE_LIMIT = 5
GITHUB_API_VERSION = "2022-11-28"


def github_configuration():
    settings = get_settings()
    if not settings.github_client_id or not settings.github_client_secret:
        raise HTTPException(503, "GitHub connection is not configured.")
    # Use the same application credential encryption primitive as the existing
    # OAuth flow.  Calling it here also fails safely when its key is absent.
    flow_cipher()
    return settings


def account_data(row: ExternalAccount) -> dict:
    """Serialize only connection metadata; never expose credential or subject."""
    return data(row, exclude=("user_id", "provider_user_id", "encrypted_credential", "revoked"))


def github_headers(token: str | None = None) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "dudri-source-connector",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    return headers


def github_api_request(method: str, path: str, *, token: str) -> Any:
    """Call GitHub without ever reflecting response bodies or credentials."""
    try:
        response = httpx.request(
            method,
            GITHUB_API_ORIGIN + path,
            headers=github_headers(token),
            timeout=20,
            follow_redirects=False,
        )
    except httpx.HTTPError:
        raise HTTPException(503, "GitHub could not be reached. Please try again.") from None
    if response.status_code in (401, 403):
        raise HTTPException(409, "GitHub permission changed. Reconnect the account and try again.")
    if response.status_code >= 400:
        raise HTTPException(503, "GitHub could not complete the request. Please try again.")
    try:
        return response.json()
    except ValueError:
        raise HTTPException(503, "GitHub returned an invalid response. Please try again.") from None


def github_exchange_code(code: str, verifier: str, settings) -> str:
    try:
        response = httpx.request(
            "POST",
            GITHUB_TOKEN_ORIGIN,
            headers={"Accept": "application/json", "User-Agent": "dudri-source-connector"},
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
                "code_verifier": verifier,
                "redirect_uri": settings.app_origin + "/github/callback",
            },
            timeout=20,
            follow_redirects=False,
        )
    except httpx.HTTPError:
        raise HTTPException(503, "GitHub could not be reached. Please try again.") from None
    if response.status_code >= 400:
        raise HTTPException(401, "GitHub authorization could not be verified. Please connect again.")
    try:
        payload = response.json()
        token = payload["access_token"]
        if not isinstance(token, str) or not token or len(token) > 4096:
            raise ValueError
        return token
    except (KeyError, TypeError, ValueError):
        raise HTTPException(401, "GitHub authorization could not be verified. Please connect again.") from None


def github_identity(token: str) -> tuple[str, str]:
    payload = github_api_request("GET", "/user", token=token)
    try:
        provider_user_id = str(int(payload["id"]))
        login = payload["login"]
        if not isinstance(login, str) or not login.strip() or len(login) > 200:
            raise ValueError
        return provider_user_id, login.strip()
    except (KeyError, TypeError, ValueError):
        raise HTTPException(503, "GitHub returned an invalid account response. Please try again.") from None


def credential_for(account: ExternalAccount) -> str:
    try:
        token = flow_cipher().decrypt(account.encrypted_credential.encode()).decode()
        if not token or len(token) > 4096:
            raise ValueError
        return token
    except (InvalidToken, UnicodeDecodeError, ValueError, TypeError):
        raise HTTPException(409, "GitHub permission is no longer available. Reconnect the account.") from None


def github_account(db: DB, user: User) -> ExternalAccount:
    account = db.scalar(select(ExternalAccount).where(
        ExternalAccount.user_id == user.id,
        ExternalAccount.provider == "github",
        ExternalAccount.revoked.is_(False),
    ))
    if not account:
        raise HTTPException(409, "Connect a GitHub account first.")
    return account


def access_session(request: Request, db: DB, user: User) -> AuthSession:
    """Bind the outgoing OAuth state to the same active auth-session family."""
    authorization = request.headers.get("authorization", "")
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Sign in is required.")
    row = db.scalar(select(AuthSession).where(
        AuthSession.user_id == user.id,
        AuthSession.access_hash == digest(authorization[7:]),
        AuthSession.revoked.is_(False),
        AuthSession.rotated.is_(False),
        AuthSession.access_expires_at > now(),
        AuthSession.expires_at > now(),
    ))
    if not row:
        raise HTTPException(401, "Sign in is required.")
    return row


def repository_data(payload: Any) -> dict:
    if not isinstance(payload, dict):
        raise HTTPException(503, "GitHub returned an invalid repository response. Please try again.")
    try:
        repository_id = payload["id"]
        if isinstance(repository_id, bool):
            raise ValueError
        repository_id = int(repository_id)
        full_name = payload["full_name"]
        display_name = payload.get("name") or full_name
        private = payload["private"]
        html_url = payload["html_url"]
        if (
            repository_id <= 0
            or not isinstance(full_name, str)
            or not full_name.strip()
            or len(full_name) > 200
            or not isinstance(display_name, str)
            or not display_name.strip()
            or len(display_name) > 200
            or not isinstance(private, bool)
            or not isinstance(html_url, str)
        ):
            raise ValueError
        url = urlsplit(html_url)
        if url.scheme != "https" or url.hostname != "github.com" or url.username or url.password:
            raise ValueError
        description = payload.get("description")
        language = payload.get("language")
        updated_at = payload.get("updated_at")
        if description is not None and not isinstance(description, str):
            raise ValueError
        if language is not None and not isinstance(language, str):
            raise ValueError
        if updated_at is not None and not isinstance(updated_at, str):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise HTTPException(503, "GitHub returned an invalid repository response. Please try again.") from None
    return {
        "repository_id": repository_id,
        "full_name": full_name.strip(),
        "display_name": display_name.strip(),
        "private": private,
        "canonical_url": urlunsplit(("https", "github.com", url.path, "", "")),
        "description": (description or "").strip()[:5000],
        "language": (language or "").strip()[:200],
        "updated_at": (updated_at or "").strip()[:100],
    }


def repository_text(repository: dict) -> str:
    """Private, selected-source metadata only; source code is never fetched here."""
    lines = [
        "GitHub repository metadata selected by the user.",
        f"Repository: {repository['full_name']}",
        f"Visibility: {'private' if repository['private'] else 'public'}",
    ]
    if repository["description"]:
        lines.append(f"Description: {repository['description']}")
    if repository["language"]:
        lines.append(f"Primary language: {repository['language']}")
    if repository["updated_at"]:
        lines.append(f"Updated at: {repository['updated_at']}")
    return "\n".join(lines)


def repository_metadata(repository: dict) -> dict:
    return {
        "provider": "github",
        "repository_id": repository["repository_id"],
        "full_name": repository["full_name"],
        "description": repository["description"],
        "primary_language": repository["language"],
        "updated_at": repository["updated_at"],
        "visibility": "private" if repository["private"] else "public",
    }


def list_repositories(token: str) -> tuple[list[dict], bool]:
    repositories: list[dict] = []
    truncated = False
    for page in range(1, GITHUB_REPOSITORY_PAGE_LIMIT + 1):
        query = urlencode({
            "affiliation": "owner,collaborator,organization_member",
            "direction": "desc",
            "page": page,
            "per_page": GITHUB_REPOSITORY_PAGE_SIZE,
            "sort": "updated",
        })
        payload = github_api_request("GET", f"/user/repos?{query}", token=token)
        if not isinstance(payload, list):
            raise HTTPException(503, "GitHub returned an invalid repository list. Please try again.")
        repositories.extend(repository_data(item) for item in payload)
        if len(payload) < GITHUB_REPOSITORY_PAGE_SIZE:
            break
    else:
        truncated = True
    # GitHub can theoretically return duplicate entries through affiliation
    # views.  Keep a deterministic, one-row-per-repository response.
    unique = {item["repository_id"]: item for item in repositories}
    return sorted(unique.values(), key=lambda item: item["full_name"].lower()), truncated


def normalize_linkedin_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        hostname = (parsed.hostname or "").lower()
        if parsed.port or parsed.scheme != "https" or parsed.username or parsed.password:
            raise ValueError
        if hostname != "linkedin.com" and not hostname.endswith(".linkedin.com"):
            raise ValueError
        path = parsed.path.rstrip("/")
        if not path.lower().startswith(("/in/", "/pub/")) or path.count("/") < 2:
            raise ValueError
        return urlunsplit(("https", "www.linkedin.com", path, "", ""))
    except ValueError:
        raise ValueError("Use a valid HTTPS LinkedIn profile URL") from None


class GitHubCallback(Input):
    code: str = Field(min_length=1, max_length=2048)
    state: str = Field(min_length=20, max_length=200)


class GitHubSync(Input):
    repository_ids: list[int] = Field(min_length=1, max_length=20)


class LinkedInSource(Input):
    url: str = Field(min_length=20, max_length=2048)

    @field_validator("url")
    @classmethod
    def valid_linkedin_url(cls, value: str):
        return normalize_linkedin_url(value)


@router.post("/me/external-accounts/github/connect")
def github_connect(request: Request, response: Response, db: DB, user: Actor):
    check_origin(request)
    settings = github_configuration()
    session = access_session(request, db, user)
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(48)
    pending = {
        "state": state,
        "verifier": verifier,
        "user_id": user.id,
        "family_id": session.family_id,
        "origin": settings.app_origin,
    }
    encrypted = flow_cipher().encrypt(json.dumps(pending, separators=(",", ":")).encode()).decode()
    response.set_cookie(
        GITHUB_COOKIE,
        encrypted,
        httponly=True,
        secure=settings.environment == "production",
        samesite="lax",
        path=GITHUB_COOKIE_PATH,
        max_age=GITHUB_COOKIE_TTL_SECONDS,
    )
    response.headers["Cache-Control"] = "no-store"
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    query = urlencode({
        "client_id": settings.github_client_id,
        "redirect_uri": settings.app_origin + "/github/callback",
        "scope": "read:user repo",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    return {"url": GITHUB_AUTHORIZE_ORIGIN + "?" + query}


@router.post("/auth/github/callback")
def github_callback(body: GitHubCallback, request: Request, response: Response, db: DB):
    check_origin(request)
    settings = github_configuration()
    try:
        pending = json.loads(flow_cipher().decrypt(
            request.cookies.get(GITHUB_COOKIE, "").encode(), ttl=GITHUB_COOKIE_TTL_SECONDS
        ))
        expected_state = pending["state"]
        verifier = pending["verifier"]
        pending_user_id = pending["user_id"]
        pending_family_id = pending["family_id"]
        if (
            pending["origin"] != settings.app_origin
            or not all(isinstance(value, str) and value for value in
                       (expected_state, verifier, pending_user_id, pending_family_id))
            or not secrets.compare_digest(expected_state, body.state)
        ):
            raise ValueError
    except (InvalidToken, ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise HTTPException(401, "Start the GitHub connection again in this browser.") from None
    session = cookie_session(request, db)
    if not session or session.user_id != pending_user_id or session.family_id != pending_family_id:
        raise HTTPException(401, "The signed-in session changed while connecting GitHub.")
    user_id = session.user_id
    # Do not retain a database connection while the OAuth provider is contacted.
    db.rollback()
    token = github_exchange_code(body.code, verifier, settings)
    provider_user_id, login = github_identity(token)

    lock_user(db, user_id)
    user = required(db, User, user_id)
    if user.account_status != "active":
        raise HTTPException(401, "This account is not active.")
    attached_elsewhere = db.scalar(select(ExternalAccount).where(
        ExternalAccount.provider == "github",
        ExternalAccount.provider_user_id == provider_user_id,
        ExternalAccount.user_id != user.id,
        ExternalAccount.revoked.is_(False),
    ))
    if attached_elsewhere:
        raise HTTPException(409, "This GitHub account is already connected to another account.")
    encrypted_token = flow_cipher().encrypt(token.encode()).decode()
    account = db.scalar(select(ExternalAccount).where(
        ExternalAccount.user_id == user.id,
        ExternalAccount.provider == "github",
    ))
    if account:
        account.provider_user_id = provider_user_id
        account.login = login
        account.encrypted_credential = encrypted_token
        account.revoked = False
    else:
        account = ExternalAccount(
            user_id=user.id,
            provider="github",
            provider_user_id=provider_user_id,
            login=login,
            encrypted_credential=encrypted_token,
        )
        db.add(account)
        db.flush()
    response.delete_cookie(GITHUB_COOKIE, path=GITHUB_COOKIE_PATH)
    response.headers["Cache-Control"] = "no-store"
    return account_data(account)


@router.get("/me/external-accounts")
def external_accounts(db: DB, user: Actor):
    rows = db.scalars(select(ExternalAccount).where(
        ExternalAccount.user_id == user.id,
        ExternalAccount.revoked.is_(False),
    ).order_by(ExternalAccount.created_at.desc()))
    return {"items": [account_data(row) for row in rows], "next_cursor": None}


@router.delete("/me/external-accounts/{account_id}", status_code=204)
def delete_external_account(account_id: str, db: DB, user: Actor):
    lock_user(db, user.id)
    account = owner(required(db, ExternalAccount, account_id), user)
    # Keep user-selected source snapshots private, but sever their credential
    # relationship before deleting the account row.
    db.execute(update(Material).where(Material.external_account_id == account.id).values(external_account_id=None))
    db.delete(account)


@router.get("/me/external-accounts/github/repositories")
def github_repositories(db: DB, user: Actor):
    account = github_account(db, user)
    # ``account`` has everything needed to decrypt the token.  Release the
    # request transaction before making potentially slow provider calls.
    token = credential_for(account)
    db.rollback()
    repositories, truncated = list_repositories(token)
    return {"items": repositories, "next_cursor": None, "truncated": truncated}


@router.post("/me/external-accounts/github/sync")
def github_sync(body: GitHubSync, db: DB, user: Actor):
    if len(set(body.repository_ids)) != len(body.repository_ids) or any(identifier <= 0 for identifier in body.repository_ids):
        raise HTTPException(422, "Choose each GitHub repository only once.")
    account = github_account(db, user)
    account_id, token = account.id, credential_for(account)
    db.rollback()
    selected = []
    for repository_id in body.repository_ids:
        selected.append(repository_data(github_api_request("GET", f"/repositories/{repository_id}", token=token)))

    lock_user(db, user.id)
    account = required(db, ExternalAccount, account_id)
    if account.user_id != user.id or account.provider != "github" or account.revoked:
        raise HTTPException(409, "GitHub connection changed. Refresh and try again.")
    result = []
    for repository in selected:
        metadata = repository_metadata(repository)
        text = repository_text(repository)
        material = db.scalar(select(Material).where(
            Material.user_id == user.id,
            Material.material_kind == "github_repository",
            Material.canonical_url == repository["canonical_url"],
            (Material.external_account_id == account.id) | (Material.external_account_id.is_(None)),
        ).order_by(Material.created_at.desc()))
        values = {
            "external_account_id": account.id,
            "display_name": repository["display_name"],
            "is_private": repository["private"],
            "access_status": "available",
            "metadata_json": metadata,
            "text_content": text,
        }
        if material:
            if any(getattr(material, key) != value for key, value in values.items()):
                for key, value in values.items():
                    setattr(material, key, value)
                material.revision += 1
        else:
            material = Material(
                user_id=user.id,
                material_kind="github_repository",
                canonical_url=repository["canonical_url"],
                **values,
            )
            db.add(material)
            db.flush()
        result.append(data(material, exclude=("text_content", "object_key")))
    # No AnalysisRun or Job is created here.  The normal analysis endpoint
    # remains the only path that can send an explicitly selected material to AI.
    return {"items": result}


@router.post("/me/source-materials/linkedin", status_code=201)
def add_linkedin_source(body: LinkedInSource, response: Response, db: DB, user: Actor):
    """Store a private external link only.  LinkedIn OAuth/fetching is out of scope."""
    lock_user(db, user.id)
    material = db.scalar(select(Material).where(
        Material.user_id == user.id,
        Material.material_kind == "linkedin",
        Material.access_status == "available",
    ).order_by(Material.created_at.desc()))
    values = {
        "display_name": "LinkedIn profile",
        "canonical_url": body.url,
        "is_private": True,
        "access_status": "available",
        "metadata_json": {"provider": "linkedin", "url": body.url},
        "text_content": None,
        "external_account_id": None,
    }
    if material:
        if any(getattr(material, key) != value for key, value in values.items()):
            for key, value in values.items():
                setattr(material, key, value)
            material.revision += 1
        response.status_code = 200
    else:
        material = Material(user_id=user.id, material_kind="linkedin", **values)
        db.add(material)
        db.flush()
    return data(material, exclude=("text_content", "object_key"))
