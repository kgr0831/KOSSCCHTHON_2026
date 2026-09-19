"""Owner drafts, immutable revisions, and explicitly published personal documents."""
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import Field
from sqlalchemy import func, select, update

from .auth import Actor, Input
from .common import DB, data, lock_user, owner, required, update_revision
from .config import get_settings
from .connector_support import connector_execution_target, selected_cli_connection
from .document_references import selected_references
from .local_runtime import execution_target
from .models import (
    AISettings,
    Job,
    PersonalSite,
    Publication,
    SiteVersion,
    SiteVersionReferenceInput,
    User,
    now,
)
from .profiles import public_user
from .site_render import html_document, safe_markup, update_fields
from .styles import get_style, styles
from .subscriptions import AIPlanUser, can_generate_ai_documents

router = APIRouter(prefix="/api/v1", tags=["personal documents"])
Kind = Literal["portfolio", "profile_pr", "cv", "cover_letter"]


class Section(Input):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,50}$")
    heading: str = Field(max_length=200)
    body: str = Field(max_length=12000)
    items: list[str] = Field(default_factory=list, max_length=30)


class Document(Input):
    title: str = Field(min_length=1, max_length=200)
    headline: str = Field(max_length=500)
    summary: str = Field(max_length=12000)
    sections: list[Section] = Field(default_factory=list, max_length=20)
    accent: str = Field(default="#7060d9", pattern=r"^#[0-9a-fA-F]{6}$")
    font: Literal["sans-serif", "serif", "monospace"] = "sans-serif"
    spacing: int = Field(default=24, ge=8, le=64)


class Code(Input):
    html: str = Field(min_length=10, max_length=180000)
    css: str = Field(default="", max_length=100000)
    javascript: str = Field(default="", max_length=50000)


class Generated(Input):
    document: Document
    code: Code


class NewVersion(Input):
    style_id: str
    instruction: str = Field(default="", max_length=15000)
    consent: Literal[True]
    revision: int = Field(ge=0)
    base_version_id: str | None = None
    reference_ids: list[str] = Field(default_factory=list, max_length=5)


def own_site(db, user, site_id):
    return owner(required(db, PersonalSite, site_id), user)


def own_version(db, user, version_id):
    version = required(db, SiteVersion, version_id)
    return own_site(db, user, version.site_id), version


def version_data(version, preview=False):
    result = data(version)
    if preview and version.code:
        result["preview_html"] = html_document(version.code)
    return result


def next_version(db, site, user, **values):
    number = db.scalar(select(func.max(SiteVersion.version_number)).where(SiteVersion.site_id == site.id)) or 0
    row = SiteVersion(site_id=site.id, version_number=number + 1, facts_revision=user.facts_revision, **values)
    db.add(row)
    db.flush()
    return row


@router.get("/portfolio-styles")
def style_list(db: DB, user: Actor):
    return {"items": [{k: v for k, v in x.items() if k != "markdown"} for x in styles(db, user)]}


@router.get("/me/sites")
def list_sites(db: DB, user: Actor):
    result = []
    for site in db.scalars(select(PersonalSite).where(PersonalSite.user_id == user.id).order_by(PersonalSite.created_at)):
        versions = list(db.scalars(select(SiteVersion).where(SiteVersion.site_id == site.id).order_by(SiteVersion.version_number.desc())))
        result.append({**data(site), "versions": [data(v, exclude=("code", "gui", "public_input_snapshot")) for v in versions],
                       "public_url": f"{get_settings().site_origin}/s/{site.slug}" if site.published_version_id else None})
    return {"items": result}


@router.post("/me/sites/{kind}/versions", status_code=202)
def generate(kind: Kind, body: NewVersion, db: DB, user: AIPlanUser):
    user = lock_user(db, user.id)
    if not can_generate_ai_documents(user):
        raise HTTPException(403, "AI document generation requires a PREMIUM plan.")
    style = get_style(body.style_id, db, user)
    references = selected_references(db, user.id, kind, body.reference_ids)
    ai_settings = db.get(AISettings, user.id)
    if any(reference.image_content for reference in references):
        connection = selected_cli_connection(ai_settings)
        if not (ai_settings and ai_settings.transport in ("cli", "hybrid") and ai_settings.cli_provider == "codex"
                and connection and connection.get("status") == "connected"):
            raise HTTPException(422, "PNG/JPG 참고 자료는 이 PC의 Codex CLI 연결에서만 사용할 수 있어요.")
    site = db.scalar(select(PersonalSite).where(PersonalSite.user_id == user.id, PersonalSite.site_kind == kind))
    if not site:
        if body.revision != 0:
            raise HTTPException(409, "사이트 목록을 다시 불러와 주세요.")
        site = PersonalSite(user_id=user.id, site_kind=kind, slug=f"{kind}-{user.id}")
        db.add(site)
        db.flush()
    else:
        update_revision(db, site, body.revision, {})
    base = None
    if body.base_version_id:
        _, base = own_version(db, user, body.base_version_id)
        if base.site_id != site.id or not base.code:
            raise HTTPException(422, "이 사이트의 저장된 버전을 선택해 주세요.")
        if base.facts_revision != user.facts_revision:
            raise HTTPException(409, "프로필이 변경됐습니다. 최신 공개 정보로 새로 생성해 주세요.")
    snapshot = {"profile": public_user(db, user), "style_markdown": style["markdown"]}
    row = next_version(db, site, user, edit_mode="ai", style_id=style["id"], instruction=body.instruction,
                       base_version_id=base.id if base else None, public_input_snapshot=snapshot,
                       validation={"base_site_revision": site.revision})
    db.add_all(SiteVersionReferenceInput(version_id=row.id, reference_id=reference.id,
                                         reference_revision=reference.revision) for reference in references)
    target = connector_execution_target(ai_settings)
    # Local API/worker launches retain the existing same-PC execution target;
    # only a deployed account with a paired CLI selection targets that PC.
    db.add(Job(user_id=user.id, kind="site", target_id=row.id,
               execution_target=execution_target() if target == "server" else target))
    return {**version_data(row), "site_revision": site.revision}


@router.get("/me/site-versions/{version_id}")
def get_version(version_id: str, db: DB, user: Actor):
    site, version = own_version(db, user, version_id)
    return {**version_data(version, True), "site_revision": site.revision,
            "facts_current": version.facts_revision == user.facts_revision}


class Edit(Input):
    revision: int = Field(ge=1)
    mode: Literal["gui", "code", "restore"]
    document: Document | None = None
    code: Code | None = None


@router.post("/me/site-versions/{version_id}/revisions", status_code=201)
def revise(version_id: str, body: Edit, db: DB, user: Actor):
    user = lock_user(db, user.id)
    site, base = own_version(db, user, version_id)
    if not base.code or base.facts_revision != user.facts_revision:
        raise HTTPException(409, "현재 공개 프로필로 새로 생성한 뒤 편집해 주세요.")
    update_revision(db, site, body.revision, {})
    code, gui = base.code, base.gui
    if body.mode == "gui":
        if not body.document:
            raise HTTPException(422, "편집할 문서를 입력해 주세요.")
        gui = body.document.model_dump()
        code = update_fields(code, gui, base.gui)
    if body.mode == "code":
        if not body.code:
            raise HTTPException(422, "HTML/CSS/JS를 입력해 주세요.")
        code = body.code.model_dump()
        # GUI only changes explicitly marked regions; arbitrary code is retained.
        from .site_render import read_fields
        gui = read_fields(code, gui)
    code = {**code, "html": safe_markup(code["html"])}
    from .site_render import validate_code
    error = validate_code(code)
    row = next_version(db, site, user, edit_mode=body.mode, status="invalid" if error else "preview_ready",
                       style_id=base.style_id, instruction=base.instruction, base_version_id=base.id,
                       public_input_snapshot=base.public_input_snapshot, code=code, gui=gui,
                       error=error, validation={"base_site_revision": site.revision})
    return {**version_data(row, True), "site_revision": site.revision}


class Revision(Input):
    revision: int = Field(ge=1)


@router.post("/me/site-versions/{version_id}/publish")
def publish(version_id: str, body: Revision, db: DB, user: Actor):
    user = lock_user(db, user.id)
    site, version = own_version(db, user, version_id)
    if version.status != "preview_ready" or version.facts_revision != user.facts_revision:
        raise HTTPException(409, "현재 공개 정보로 생성한 정상 미리보기만 게시할 수 있어요.")
    from .site_render import validate_code
    if validate_code(version.code):
        raise HTTPException(409, "저장된 코드의 검증을 완료하지 못했어요. 수정한 새 버전을 확인해 주세요.")
    update_revision(db, site, body.revision, {"published_version_id": version.id})
    db.execute(update(Publication).where(Publication.site_id == site.id, Publication.revoked_at.is_(None)).values(revoked_at=now()))
    db.add(Publication(site_id=site.id, version_id=version.id))
    return {**data(site), "public_url": f"{get_settings().site_origin}/s/{site.slug}"}


@router.post("/me/sites/{site_id}/revoke")
def revoke(site_id: str, body: Revision, db: DB, user: Actor):
    lock_user(db, user.id)
    site = own_site(db, user, site_id)
    update_revision(db, site, body.revision, {"published_version_id": None})
    db.execute(update(Publication).where(Publication.site_id == site.id, Publication.revoked_at.is_(None)).values(revoked_at=now()))
    return data(site)


@router.get("/users/{user_id}/sites")
def published_sites(user_id: str, db: DB, user: Actor):
    person = required(db, User, user_id)
    if person.account_status != "active":
        raise HTTPException(404, "프로필을 찾을 수 없습니다.")
    result = []
    for site in db.scalars(select(PersonalSite).where(PersonalSite.user_id == user_id, PersonalSite.published_version_id.is_not(None))):
        version = db.get(SiteVersion, site.published_version_id)
        if version and version.facts_revision == person.facts_revision and version.status == "preview_ready":
            result.append({"kind": site.site_kind, "url": f"{get_settings().site_origin}/s/{site.slug}"})
    return {"items": result}
