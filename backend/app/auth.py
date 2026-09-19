import hashlib
import secrets
import smtplib
from datetime import timedelta
from email.message import EmailMessage
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import func, select, update

from .common import DB, data, required, utc
from .config import get_settings
from .models import (
    Affiliation,
    AuthChallenge,
    AuthSession,
    Preference,
    Profile,
    University,
    UniversityDomain,
    User,
    Verification,
    now,
    uid,
)

router = APIRouter(prefix="/api/v1")


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Mailer:
    def send(self, email: str, purpose: str, token: str):
        settings = get_settings()
        if not settings.smtp_host or not settings.smtp_sender:
            raise HTTPException(503, "이메일 발송 서비스가 아직 설정되지 않았습니다.")
        message = EmailMessage()
        message["From"] = settings.smtp_sender
        message["To"] = email
        message["Subject"] = "두드리 이메일 확인"
        # Fragment keeps the credential out of proxy/access logs and Referer headers.
        message.set_content(f"두드리에서 요청한 이메일 확인입니다.\n\n"
                            f"{settings.app_origin}/auth/confirm#purpose={purpose}&token={token}\n\n"
                            "15분 안에 한 번만 사용할 수 있습니다. 본인이 요청하지 않았다면 무시해 주세요.")
        try:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
                if settings.smtp_starttls:
                    smtp.starttls()
                if settings.smtp_username:
                    smtp.login(settings.smtp_username, settings.smtp_password)
                smtp.send_message(message)
        except (OSError, smtplib.SMTPException):
            raise HTTPException(503, "인증 메일을 보내지 못했습니다. 잠시 후 다시 시도해 주세요.")


def get_mailer():
    return Mailer()


def challenge(db, email, purpose, payload, mailer, user_id=None):
    recent = db.scalar(select(func.count()).select_from(AuthChallenge).where(
        AuthChallenge.email == email, AuthChallenge.created_at > now() - timedelta(minutes=15)))
    if recent >= 5:
        raise HTTPException(429, "인증 요청이 많습니다. 잠시 후 다시 시도해 주세요.")
    token = secrets.token_urlsafe(32)
    db.add(AuthChallenge(token_hash=digest(token), purpose=purpose, email=email, user_id=user_id,
                         payload=payload, expires_at=now() + timedelta(minutes=15)))
    db.flush()
    mailer.send(email, purpose, token)
    return {"status": "accepted", "message": "인증 메일 발송을 요청했습니다. 이메일을 확인해 주세요."}


def consume(db, token, purpose):
    row = db.scalar(select(AuthChallenge).where(AuthChallenge.token_hash == digest(token),
                    AuthChallenge.purpose == purpose))
    if not row or row.consumed_at or utc(row.expires_at) <= now():
        raise HTTPException(401, "인증 링크가 만료되었거나 이미 사용되었습니다.")
    result = db.execute(update(AuthChallenge).where(AuthChallenge.id == row.id,
                        AuthChallenge.consumed_at.is_(None), AuthChallenge.expires_at > now())
                        .values(consumed_at=now()).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        raise HTTPException(401, "인증 링크가 만료되었거나 이미 사용되었습니다.")
    return row


def issue_session(db, user_id, response, family_id=None):
    settings = get_settings()
    access, refresh = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
    db.add(AuthSession(user_id=user_id, family_id=family_id or uid(), access_hash=digest(access),
                       refresh_hash=digest(refresh), access_expires_at=now() + timedelta(minutes=15),
                       expires_at=now() + timedelta(days=30)))
    response.set_cookie("dudri_refresh", refresh, httponly=True, secure=settings.environment == "production",
                        samesite="strict", path="/api/v1/auth", max_age=30 * 86400)
    return {"access_token": access, "token_type": "bearer", "expires_in": 900}


def current_user(db: DB, authorization: Annotated[str | None, Header()] = None) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "로그인이 필요합니다.")
    row = db.scalar(select(AuthSession).where(AuthSession.access_hash == digest(authorization[7:]),
                    AuthSession.revoked.is_(False), AuthSession.rotated.is_(False),
                    AuthSession.access_expires_at > now(), AuthSession.expires_at > now()))
    user = db.get(User, row.user_id) if row else None
    if not user or user.account_status != "active":
        raise HTTPException(401, "로그인이 만료되었습니다.")
    return user


Actor = Annotated[User, Depends(current_user)]


def admin_user(user: Actor):
    if not user.is_admin:
        raise HTTPException(403, "운영자 권한이 필요합니다.")
    return user


Admin = Annotated[User, Depends(admin_user)]


def check_origin(request):
    if request.headers.get("origin") != get_settings().app_origin:
        raise HTTPException(403, "허용되지 않은 요청 출처입니다.")


class SchoolSignup(Input):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    university_id: str
    enrollment_status: Literal["student", "graduate", "leave", "other"]
    department: str = Field(default="", max_length=150)
    entry_year: int | None = Field(default=None, ge=1900, le=2200)


class EmailInput(Input):
    email: EmailStr


class CompanyInput(EmailInput):
    company_name: str = Field(min_length=1, max_length=150)


class TokenInput(Input):
    token: str = Field(min_length=20, max_length=200)


@router.get("/universities")
def universities(db: DB):
    return {"items": [data(x) for x in db.scalars(select(University).where(University.is_supported.is_(True)))],
            "next_cursor": None}


@router.get("/universities/{university_id}/domains")
def university_domains(university_id: str, db: DB):
    required(db, University, university_id)
    return {"items": [data(x) for x in db.scalars(select(UniversityDomain).where(
        UniversityDomain.university_id == university_id))], "next_cursor": None}


@router.post("/auth/school-email-verifications", status_code=202)
def school_start(body: SchoolSignup, db: DB, mailer=Depends(get_mailer)):
    university = required(db, University, body.university_id)
    domain = db.scalar(select(UniversityDomain).where(UniversityDomain.university_id == university.id,
                       UniversityDomain.domain == str(body.email).split("@")[1].lower()))
    if not university.is_supported or not domain:
        raise HTTPException(422, "선택한 학교의 허용 이메일 도메인과 일치하지 않습니다.")
    payload = body.model_dump(mode="json") | {"domain_id": domain.id}
    return challenge(db, str(body.email).lower(), "school", payload, mailer)


def confirm_school(token, db, response):
    row = consume(db, token, "school")
    user = db.scalar(select(User).where(User.login_email == row.email))
    if not user:
        user = User(login_email=row.email)
        db.add(user)
        db.flush()
        db.add_all([Profile(user_id=user.id, display_name=row.payload["name"]), Preference(user_id=user.id)])
    affiliation = db.scalar(select(Affiliation).where(Affiliation.user_id == user.id,
        Affiliation.university_id == row.payload["university_id"], Affiliation.withdrawn.is_(False)))
    if not affiliation:
        affiliation = Affiliation(user_id=user.id, **{key: row.payload[key] for key in
            ("university_id", "enrollment_status", "department", "entry_year")})
        db.add(affiliation)
        db.flush()
    db.add(Verification(user_id=user.id, school_affiliation_id=affiliation.id,
                        university_domain_id=row.payload["domain_id"], verification_kind="school",
                        verified_email=row.email))
    return issue_session(db, user.id, response)


@router.post("/auth/school-email-verifications/confirm")
def school_confirm(body: TokenInput, db: DB, response: Response):
    return confirm_school(body.token, db, response)


@router.get("/auth/school-email-verifications/confirm")
def school_confirm_legacy(token: str, db: DB, response: Response):
    return confirm_school(token, db, response)


@router.post("/auth/login-links", status_code=202)
def login_start(body: EmailInput, db: DB, mailer=Depends(get_mailer)):
    email = str(body.email).lower()
    user = db.scalar(select(User).where(User.login_email == email, User.account_status == "active"))
    # Deliver the same neutral message for unregistered addresses, avoiding account enumeration.
    return challenge(db, email, "login", {}, mailer, user.id if user else None)


def confirm_login(token, db, response):
    row = consume(db, token, "login")
    user = db.get(User, row.user_id) if row.user_id else None
    if not user or user.account_status != "active":
        raise HTTPException(401, "학교 인증 후 로그인해 주세요.")
    return issue_session(db, user.id, response)


@router.post("/auth/login-links/confirm")
def login_confirm(body: TokenInput, db: DB, response: Response):
    return confirm_login(body.token, db, response)


@router.get("/auth/login-links/confirm")
def login_confirm_legacy(token: str, db: DB, response: Response):
    return confirm_login(token, db, response)


@router.post("/auth/company-email-verifications", status_code=202)
def company_start(body: CompanyInput, db: DB, user: Actor, mailer=Depends(get_mailer)):
    return challenge(db, str(body.email).lower(), "company", {"company_name": body.company_name}, mailer, user.id)


def confirm_company(token, db):
    row = consume(db, token, "company")
    db.add(Verification(user_id=row.user_id, verification_kind="company", verified_email=row.email,
                        company_name=row.payload["company_name"]))
    return {"status": "verified", "meaning": "회사 이메일 접근 확인. 직무·직급·과거 경력 인증과 다릅니다."}


@router.post("/auth/company-email-verifications/confirm")
def company_confirm(body: TokenInput, db: DB):
    return confirm_company(body.token, db)


@router.get("/auth/company-email-verifications/confirm")
def company_confirm_legacy(token: str, db: DB):
    return confirm_company(token, db)


@router.get("/me/verifications")
def verifications(db: DB, user: Actor):
    return {"items": [data(x) for x in db.scalars(select(Verification).where(Verification.user_id == user.id))],
            "next_cursor": None}


@router.post("/auth/refresh")
def refresh(request: Request, response: Response, db: DB):
    check_origin(request)
    token = request.cookies.get("dudri_refresh", "")
    row = db.scalar(select(AuthSession).where(AuthSession.refresh_hash == digest(token)))
    if row and row.rotated:
        db.execute(update(AuthSession).where(AuthSession.family_id == row.family_id).values(revoked=True))
        db.commit()  # Reuse revocation must survive the rejected request's rollback.
        raise HTTPException(401, "재사용된 세션입니다. 다시 로그인해 주세요.")
    if not row or row.revoked or utc(row.expires_at) <= now():
        raise HTTPException(401, "로그인이 필요합니다.")
    user = required(db, User, row.user_id)
    if user.account_status != "active":
        raise HTTPException(401, "사용할 수 없는 계정입니다.")
    consumed = db.execute(update(AuthSession).where(AuthSession.id == row.id,
        AuthSession.rotated.is_(False), AuthSession.revoked.is_(False)).values(rotated=True)
        .execution_options(synchronize_session=False))
    if consumed.rowcount != 1:
        raise HTTPException(401, "세션이 변경되었습니다.")
    return issue_session(db, row.user_id, response, row.family_id)


@router.post("/auth/logout", status_code=204)
def logout(request: Request, response: Response, db: DB):
    check_origin(request)
    row = db.scalar(select(AuthSession).where(AuthSession.refresh_hash == digest(
        request.cookies.get("dudri_refresh", ""))))
    if row:
        db.execute(update(AuthSession).where(AuthSession.family_id == row.family_id).values(revoked=True))
    response.delete_cookie("dudri_refresh", path="/api/v1/auth")


class UniversityInput(Input):
    name: str = Field(min_length=1, max_length=150)


class DomainInput(Input):
    domain: str = Field(pattern=r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+$")


@router.post("/admin/universities", status_code=201)
def add_university(body: UniversityInput, db: DB, user: Admin):
    row = University(name=body.name)
    db.add(row)
    db.flush()
    return data(row)


@router.post("/admin/universities/{university_id}/domains", status_code=201)
def add_domain(university_id: str, body: DomainInput, db: DB, user: Admin):
    required(db, University, university_id)
    row = UniversityDomain(university_id=university_id, domain=body.domain)
    db.add(row)
    db.flush()
    return data(row)
