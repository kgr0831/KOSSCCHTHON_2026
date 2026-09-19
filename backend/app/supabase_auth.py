"""Server-side Google PKCE flow; provider tokens never enter persistent browser storage."""
import base64
import hashlib
import json
import secrets
from datetime import timedelta
from urllib.parse import urlencode
from uuid import UUID

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import EmailStr, Field, TypeAdapter, ValidationError
from sqlalchemy import select

from .auth import Actor, Input, check_origin, digest
from .common import DB, utc
from .config import get_settings
from .models import AuthSession, Preference, Profile, User, now, uid

router = APIRouter(prefix="/api/v1/auth")
COOKIE_PATH = "/api/v1/auth"


def configuration():
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_publishable_key:
        raise HTTPException(503, "Google 로그인이 아직 연결되지 않았습니다.")
    return settings


def provider_request(method, path, *, token=None, body=None):
    settings = configuration()
    headers = {"apikey": settings.supabase_publishable_key}
    if token:
        headers["Authorization"] = "Bearer " + token
    try:
        result = httpx.request(method, settings.supabase_url + "/auth/v1" + path,
                               headers=headers, json=body, timeout=20, follow_redirects=False)
        result.raise_for_status()
        return result.json() if result.content else {}
    except httpx.HTTPStatusError as exc:
        status = 401 if exc.response.status_code in (400, 401, 403, 422) else 503
    except (httpx.HTTPError, ValueError):
        status = 503
    raise HTTPException(status, "Google 로그인 연결을 확인하지 못했습니다. 다시 로그인해 주세요.") from None


def verified_identity(access):
    identity = provider_request("GET", "/user", token=access)
    try:
        if not isinstance(identity, dict):
            raise ValueError
        subject = str(UUID(identity["id"]))
        email = str(TypeAdapter(EmailStr).validate_python(identity["email"])).lower()
        if not identity.get("email_confirmed_at") or not any(
            isinstance(item, dict) and item.get("provider") == "google" for item in (identity.get("identities") or [])
        ):
            raise ValueError
    except (KeyError, TypeError, ValueError, ValidationError):
        raise HTTPException(401, "확인된 Google 계정으로 로그인해 주세요.") from None
    # Only a display name may come from editable metadata, never permissions or school proof.
    metadata = identity.get("user_metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}
    name = str(metadata.get("full_name") or metadata.get("name") or "새 동문")[:100]
    return subject, email, name


def tokens(payload):
    try:
        access, refresh = payload["access_token"], payload["refresh_token"]
        lifetime = min(3600, int(payload["expires_in"]))
        if not isinstance(access, str) or not isinstance(refresh, str) or not access or not refresh or lifetime <= 0:
            raise ValueError
        return access, refresh, lifetime
    except (KeyError, TypeError, ValueError):
        raise HTTPException(503, "로그인 세션을 확인하지 못했습니다. 다시 시도해 주세요.") from None


def issue_provider_session(db, user, response, payload, previous=None):
    access, refresh, lifetime = tokens(payload)
    # Supabase can return its current token during the provider's reuse interval.
    if previous and previous.refresh_hash == digest(refresh):
        row = previous
        row.rotated = False
        row.access_hash = digest(access)
        row.access_expires_at = now() + timedelta(seconds=lifetime)
    else:
        row = AuthSession(user_id=user.id, family_id=previous.family_id if previous else uid(),
                          auth_provider="supabase", access_hash=digest(access), refresh_hash=digest(refresh),
                          access_expires_at=now() + timedelta(seconds=lifetime),
                          expires_at=utc(previous.expires_at) if previous else now() + timedelta(days=30))
        db.add(row)
    response.set_cookie("dudri_refresh", refresh, httponly=True,
                        secure=get_settings().environment == "production", samesite="lax",
                        path=COOKIE_PATH, max_age=max(1, int((utc(row.expires_at) - now()).total_seconds())))
    response.headers["Cache-Control"] = "no-store"
    return {"access_token": access, "token_type": "bearer", "expires_in": lifetime, "user_id": user.id}


def refresh_provider_session(db, user, response, refresh, previous):
    payload = provider_request("POST", "/token?grant_type=refresh_token", body={"refresh_token": refresh})
    access, _, _ = tokens(payload)
    subject, _, _ = verified_identity(access)
    if subject != user.supabase_user_id:
        raise HTTPException(401, "로그인 계정이 변경되었습니다. 다시 로그인해 주세요.")
    return issue_provider_session(db, user, response, payload, previous)


def flow_cipher():
    key = get_settings().credential_encryption_key
    if not key:
        raise HTTPException(503, "로그인 보안 설정이 필요합니다.")
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(key.encode()).digest()))


def cookie_session(request, db):
    row = db.scalar(select(AuthSession).where(
        AuthSession.refresh_hash == digest(request.cookies.get("dudri_refresh", "")),
        AuthSession.revoked.is_(False), AuthSession.rotated.is_(False), AuthSession.expires_at > now()))
    return row


def start_flow(request, response, db, user=None):
    check_origin(request)
    settings = configuration()
    verifier = secrets.token_urlsafe(48)
    pending = {"verifier": verifier, "origin": settings.app_origin}
    if user:
        row = cookie_session(request, db)
        if not row or row.user_id != user.id or user.supabase_user_id:
            raise HTTPException(409, "기존 계정으로 다시 로그인한 뒤 Google 계정을 연결해 주세요.")
        pending.update(user_id=user.id, family_id=row.family_id)
    encrypted = flow_cipher().encrypt(json.dumps(pending).encode()).decode()
    response.set_cookie("dudri_oauth", encrypted, httponly=True, secure=settings.environment == "production",
                        samesite="lax", path=COOKIE_PATH, max_age=600)
    response.headers["Cache-Control"] = "no-store"
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    query = urlencode({"provider": "google", "redirect_to": settings.app_origin + "/auth/callback",
                       "code_challenge": challenge, "code_challenge_method": "s256", "prompt": "select_account"})
    return {"url": settings.supabase_url + "/auth/v1/authorize?" + query}


@router.get("/providers")
def providers():
    settings = get_settings()
    return {"google": bool(settings.supabase_url and settings.supabase_publishable_key),
            "school_signup": settings.environment != "production"}


@router.post("/google")
def google_start(request: Request, response: Response, db: DB):
    return start_flow(request, response, db)


@router.post("/google/link")
def google_link(request: Request, response: Response, db: DB, user: Actor):
    return start_flow(request, response, db, user)


class CodeInput(Input):
    code: str = Field(min_length=10, max_length=2048)


@router.post("/google/callback")
def google_callback(body: CodeInput, request: Request, response: Response, db: DB):
    check_origin(request)
    try:
        pending = json.loads(flow_cipher().decrypt(request.cookies.get("dudri_oauth", "").encode(), ttl=600))
        verifier = pending["verifier"]
        if pending["origin"] != get_settings().app_origin or not isinstance(verifier, str):
            raise ValueError
    except (InvalidToken, ValueError, KeyError, TypeError):
        raise HTTPException(401, "로그인을 시작한 브라우저에서 다시 시도해 주세요.") from None
    linked = None
    if pending.get("user_id"):
        row = cookie_session(request, db)
        if not row or row.user_id != pending["user_id"] or row.family_id != pending["family_id"]:
            raise HTTPException(401, "계정 연결 중 로그인 상태가 변경되었습니다.")
        linked = db.get(User, row.user_id)
        if not linked or linked.account_status != "active" or linked.supabase_user_id:
            raise HTTPException(409, "이미 연결되었거나 사용할 수 없는 계정입니다.")
    payload = provider_request("POST", "/token?grant_type=pkce",
                               body={"auth_code": body.code, "code_verifier": verifier})
    access, _, _ = tokens(payload)
    subject, email, name = verified_identity(access)
    user = db.scalar(select(User).where(User.supabase_user_id == subject))
    if linked:
        if user and user.id != linked.id:
            raise HTTPException(409, "이 Google 계정은 다른 두드리 계정에 연결되어 있습니다.")
        user = linked
        user.supabase_user_id = subject
    elif not user:
        if db.scalar(select(User.id).where(User.login_email == email)):
            raise HTTPException(409, "기존 이메일로 먼저 로그인한 뒤 프로필에서 Google 계정을 연결해 주세요.")
        user = User(login_email=email, supabase_user_id=subject)
        db.add(user)
        db.flush()
        db.add_all([Profile(user_id=user.id, display_name=name), Preference(user_id=user.id)])
    if user.account_status != "active":
        raise HTTPException(401, "사용할 수 없는 계정입니다.")
    response.delete_cookie("dudri_oauth", path=COOKIE_PATH)
    return issue_provider_session(db, user, response, payload)
