"""Authenticated pairing and job hand-off for a user's own local CLI PC."""
import base64
import hashlib
import secrets
from datetime import timedelta
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import Field
from sqlalchemy import func, or_, select, update

from .auth import Actor, Input
from .common import DB, emit_realtime, lock_user, utc
from .connector_support import connector_execution_target, selected_cli_connection
from .document_references import version_reference_inputs
from .job_lease import locked_lease
from .models import AISettings, CLIConnector, Job, PersonalSite, SiteVersion, now
from .site_render import safe_markup, update_fields, validate_code
from .sites import Code, Document
from .subscriptions import can_generate_ai_documents

router = APIRouter(prefix="/api/v1", tags=["local CLI connector"])
_PAIRING_LIFETIME = timedelta(minutes=10)
_CONNECTOR_LIFETIME = timedelta(days=30)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def connector_data(row: CLIConnector) -> dict:
    online = bool(row.status == "active" and row.last_seen_at and utc(row.last_seen_at) >= now() - timedelta(seconds=45))
    return {"id": row.id, "device_id": row.device_id, "device_name": row.device_name,
            "status": row.status, "online": online, "last_seen_at": row.last_seen_at.isoformat() if row.last_seen_at else None,
            "expires_at": row.token_expires_at.isoformat() if row.token_expires_at else None}


class PairingRequest(Input):
    pass


class ConnectionInput(Input):
    provider: Literal["codex", "claude"]
    device_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    device_name: str = Field(min_length=1, max_length=100)
    executable_path: str = Field(max_length=1000)
    account_email: str = Field(max_length=254)
    status: Literal["connected", "needs_login", "not_installed", "error"]
    models: list[str] = Field(default_factory=list, max_length=100)
    default_model: str = Field(default="", max_length=150)
    checked_at: str = Field(min_length=1, max_length=80)


class ActivationInput(Input):
    device_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    device_name: str = Field(min_length=1, max_length=100)
    connections: list[ConnectionInput] = Field(min_length=1, max_length=2)


def current_connector(
    db: DB,
    x_dudri_connector: Annotated[str | None, Header()] = None,
) -> CLIConnector:
    if not x_dudri_connector or not (40 <= len(x_dudri_connector) <= 200):
        raise HTTPException(401, "PC 커넥터 인증이 필요합니다. 웹에서 새 연결 코드를 만든 뒤 다시 실행해 주세요.")
    row = db.scalar(select(CLIConnector).where(
        CLIConnector.token_hash == _digest(x_dudri_connector), CLIConnector.status == "active",
        CLIConnector.revoked_at.is_(None), CLIConnector.token_expires_at > now()))
    if not row:
        raise HTTPException(401, "PC 커넥터 연결이 만료됐거나 해제됐습니다. 웹에서 다시 연결해 주세요.")
    row.last_seen_at = now()
    return row


ConnectorActor = Annotated[CLIConnector, Depends(current_connector)]


def _selected_settings(db, connector: CLIConnector):
    settings = db.get(AISettings, connector.user_id)
    connection = selected_cli_connection(settings)
    if (not settings or connector_execution_target(settings) != f"pc:{connector.device_id}"
            or not connection or connection.get("status") != "connected"):
        raise HTTPException(409, "이 PC의 CLI 연결 설정이 바뀌었습니다. 웹에서 다시 선택하고 저장해 주세요.")
    return settings, connection


def _fail_site_job(db, job: Job, message: str):
    job.status, job.error, job.lease_until = "failed", message, None
    version = db.get(SiteVersion, job.target_id)
    if version:
        version.status, version.error = "failed", message


@router.get("/me/ai-cli-connectors")
def connectors(db: DB, user: Actor):
    rows = db.scalars(select(CLIConnector).where(CLIConnector.user_id == user.id,
        CLIConnector.revoked_at.is_(None)).order_by(CLIConnector.created_at.desc()))
    return {"items": [connector_data(row) for row in rows]}


@router.post("/me/ai-cli-connectors/pairings", status_code=201)
def create_pairing(body: PairingRequest, db: DB, user: Actor):
    recent = db.scalar(select(func.count()).select_from(CLIConnector).where(
        CLIConnector.user_id == user.id, CLIConnector.created_at > now() - timedelta(hours=1))) or 0
    if recent >= 5:
        raise HTTPException(429, "PC 연결 코드 발급이 많습니다. 한 시간 뒤 다시 시도해 주세요.")
    code = secrets.token_urlsafe(32)
    expires_at = now() + _PAIRING_LIFETIME
    db.add(CLIConnector(user_id=user.id, pairing_hash=_digest(code), pairing_expires_at=expires_at))
    return {"pairing_code": code, "expires_at": expires_at.isoformat()}


@router.delete("/me/ai-cli-connectors/{connector_id}", status_code=204)
def revoke_connector(connector_id: str, db: DB, user: Actor):
    row = db.get(CLIConnector, connector_id)
    if not row or row.user_id != user.id:
        raise HTTPException(404, "PC 커넥터를 찾을 수 없습니다.")
    row.status, row.revoked_at, row.token_hash, row.pairing_hash = "revoked", now(), None, None
    settings = db.get(AISettings, user.id)
    if settings and settings.cli_device_id == row.device_id:
        settings.transport, settings.cli_device_id, settings.revision = "api", "", settings.revision + 1
    emit_realtime(db, "ai_connector_changed", user_ids=[user.id])


@router.post("/ai-cli-connectors/activate")
def activate_connector(
    body: ActivationInput,
    db: DB,
    x_dudri_pairing_code: Annotated[str | None, Header()] = None,
):
    if not x_dudri_pairing_code or not (40 <= len(x_dudri_pairing_code) <= 200):
        raise HTTPException(401, "PC 연결 코드가 필요합니다.")
    pending = db.scalar(select(CLIConnector).where(CLIConnector.pairing_hash == _digest(x_dudri_pairing_code)))
    if (not pending or pending.status != "pending" or not pending.pairing_expires_at
            or utc(pending.pairing_expires_at) <= now()):
        raise HTTPException(401, "PC 연결 코드가 만료됐거나 이미 사용됐습니다. 웹에서 새 코드를 만들어 주세요.")
    if any(item.device_id != body.device_id or item.device_name != body.device_name for item in body.connections):
        raise HTTPException(422, "현재 PC에서 확인한 CLI 정보만 연결할 수 있습니다.")
    if not any(item.status == "connected" and item.account_email and item.models for item in body.connections):
        raise HTTPException(409, "Codex 또는 Claude CLI에 로그인한 뒤 다시 연결해 주세요.")
    existing = db.scalar(select(CLIConnector).where(CLIConnector.user_id == pending.user_id,
        CLIConnector.device_id == body.device_id, CLIConnector.revoked_at.is_(None)))
    connector = existing or pending
    if existing:
        db.delete(pending)
    token = secrets.token_urlsafe(48)
    connector.device_id, connector.device_name = body.device_id, body.device_name
    connector.token_hash, connector.token_expires_at = _digest(token), now() + _CONNECTOR_LIFETIME
    connector.pairing_hash, connector.pairing_expires_at = None, None
    connector.status, connector.last_seen_at, connector.revoked_at = "active", now(), None

    settings = db.get(AISettings, connector.user_id)
    if not settings:
        settings = AISettings(user_id=connector.user_id)
        db.add(settings)
        db.flush()
    supplied = [item.model_dump() for item in body.connections]
    settings.cli_connections = [item for item in settings.cli_connections if item.get("device_id") != body.device_id] + supplied
    settings.revision += 1
    db.flush()
    emit_realtime(db, "ai_connector_changed", user_ids=[connector.user_id])
    return {"connector": connector_data(connector), "connector_token": token}


@router.post("/ai-cli-connectors/jobs/claim")
def claim_job(db: DB, connector: ConnectorActor):
    settings, connection = _selected_settings(db, connector)
    user = lock_user(db, connector.user_id)
    if not can_generate_ai_documents(user):
        raise HTTPException(403, "AI 문서 생성에는 프리미엄 플랜이 필요합니다.")
    target = f"pc:{connector.device_id}"
    eligible = or_(Job.status == "queued", (Job.status == "running") & (Job.lease_until < now()))
    job = db.scalar(select(Job).where(Job.user_id == connector.user_id, Job.kind == "site",
        Job.execution_target == target, eligible, Job.available_at <= now()).order_by(Job.created_at).limit(1))
    if not job:
        return {"job": None}
    lease_token = str(uuid4())
    claimed = db.execute(update(Job).where(Job.id == job.id, Job.execution_target == target, eligible).values(
        status="running", lease_token=lease_token, attempts=Job.attempts + 1,
        lease_until=now() + timedelta(seconds=270)).execution_options(synchronize_session=False))
    if claimed.rowcount != 1:
        return {"job": None}
    db.refresh(job)
    version = db.get(SiteVersion, job.target_id)
    site = db.get(PersonalSite, version.site_id) if version else None
    if not version or not site or version.facts_revision != user.facts_revision:
        _fail_site_job(db, job, "프로필이 변경되어 생성을 중단했어요. 최신 공개 정보로 다시 생성해 주세요.")
        return {"job": None}
    try:
        reference_materials, reference_images = version_reference_inputs(db, version.id, user.id, site.site_kind)
    except HTTPException as exc:
        _fail_site_job(db, job, str(exc.detail))
        return {"job": None}
    if reference_images and settings.cli_provider != "codex":
        _fail_site_job(db, job, "PNG/JPG 참고 자료는 Codex CLI 연결을 선택한 뒤 다시 생성해 주세요.")
        return {"job": None}
    version.status, version.error = "running", None
    base = db.get(SiteVersion, version.base_version_id) if version.base_version_id else None
    payload = {
        "job_id": job.id,
        "lease_token": lease_token,
        "site_kind": site.site_kind,
        "instruction": version.instruction,
        "snapshot": version.public_input_snapshot,
        "previous_code": base.code if base else None,
        "reference_materials": reference_materials,
        "reference_images": [{"name": item["name"], "content_type": item["content_type"],
                              "content": base64.b64encode(item["content"]).decode("ascii")}
                             for item in reference_images],
        "cli": {"provider": settings.cli_provider, "model": settings.cli_model, "connection": connection},
    }
    return {"job": payload}


class CompleteInput(Input):
    lease_token: str = Field(min_length=36, max_length=80)
    document: Document
    code: Code
    model: str = Field(min_length=1, max_length=150)


class FailInput(Input):
    lease_token: str = Field(min_length=36, max_length=80)
    reason: Literal["cli_unavailable", "connection_changed", "timeout", "generation_failed"] = "generation_failed"


@router.post("/ai-cli-connectors/jobs/{job_id}/complete")
def complete_job(job_id: str, body: CompleteInput, db: DB, connector: ConnectorActor):
    job = locked_lease(db, job_id, body.lease_token)
    if not job or job.user_id != connector.user_id or job.execution_target != f"pc:{connector.device_id}" or job.kind != "site":
        raise HTTPException(409, "이 작업의 PC 실행 권한이 없거나 임대가 만료됐습니다.")
    try:
        settings, _ = _selected_settings(db, connector)
    except HTTPException:
        _fail_site_job(db, job, "PC CLI 연결 설정이 변경되어 생성 결과를 저장하지 않았습니다. 다시 생성해 주세요.")
        return {"status": "discarded"}
    user = lock_user(db, connector.user_id)
    version = db.get(SiteVersion, job.target_id)
    site = db.get(PersonalSite, version.site_id) if version else None
    if not site or not can_generate_ai_documents(user) or version.facts_revision != user.facts_revision:
        _fail_site_job(db, job, "프로필 또는 플랜이 변경되어 생성 결과를 저장하지 않았습니다. 다시 생성해 주세요.")
        return {"status": "discarded"}
    try:
        version_reference_inputs(db, version.id, user.id, site.site_kind)
    except HTTPException:
        _fail_site_job(db, job, "참고 자료가 변경되어 생성 결과를 저장하지 않았습니다. 다시 생성해 주세요.")
        return {"status": "discarded"}
    gui = body.document.model_dump()
    code = update_fields(body.code.model_dump(), gui, preserve_layout=True)
    code["html"] = safe_markup(code["html"])
    error = validate_code(code)
    conflict = version.validation.get("base_site_revision") != site.revision
    version.code, version.gui = code, gui
    version.status = "conflicted" if conflict else "invalid" if error else "preview_ready"
    version.error = "생성 중 다른 버전이 저장됐습니다. 결과를 확인한 뒤 복구로 새 버전을 만드세요." if conflict else error
    version.validation = {**version.validation, "model": body.model, "transport": "cli"}
    job.status, job.error, job.lease_until = "completed", None, None
    emit_realtime(db, "site_changed", user_ids=[connector.user_id])
    return {"status": version.status}


@router.post("/ai-cli-connectors/jobs/{job_id}/fail")
def fail_job(job_id: str, body: FailInput, db: DB, connector: ConnectorActor):
    job = locked_lease(db, job_id, body.lease_token)
    if not job or job.user_id != connector.user_id or job.execution_target != f"pc:{connector.device_id}" or job.kind != "site":
        raise HTTPException(409, "이 작업의 PC 실행 권한이 없거나 임대가 만료됐습니다.")
    messages = {
        "cli_unavailable": "이 PC에서 선택한 CLI를 찾을 수 없습니다. 연결을 다시 확인해 주세요.",
        "connection_changed": "이 PC의 CLI 로그인 계정 또는 연결 정보가 바뀌었습니다. 연결을 다시 확인해 주세요.",
        "timeout": "PC CLI 응답 시간이 초과됐습니다. 저장된 입력으로 다시 시도해 주세요.",
        "generation_failed": "PC CLI 생성 작업을 마치지 못했습니다. 연결과 사용량을 확인한 뒤 다시 시도해 주세요.",
    }
    _fail_site_job(db, job, messages[body.reason])
    emit_realtime(db, "site_changed", user_ids=[connector.user_id])
    return {"status": "failed"}
