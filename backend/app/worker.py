"""Durable, leased local AI work. A terminated worker can be restarted safely."""
import time
from datetime import timedelta
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import or_, select, update

from .ai import provider_for
from .common import lock_user
from .config import get_settings
from .db import session_factory
from .document_references import version_reference_inputs
from .job_lease import locked_lease
from .local_runtime import execution_target
from .models import Job, PersonalSite, SiteVersion, now
from .site_prompts import site_prompt
from .site_render import safe_markup, update_fields, validate_code
from .sites import Generated
from .subscriptions import can_generate_ai_documents


def process_one(factory=None):
    factory = factory or session_factory()
    token = str(uuid4())
    with factory.begin() as db:
        eligible = or_(Job.status == "queued", (Job.status == "running") & (Job.lease_until < now()))
        targets = [execution_target()]
        if get_settings().database_url.startswith("sqlite:"):
            targets.append("server")  # Pre-migration local SQLite jobs.
        eligible = eligible & Job.execution_target.in_(targets)
        job = db.scalar(select(Job).where(eligible, Job.available_at <= now()).order_by(Job.created_at).limit(1))
        if not job:
            return False
        claimed = db.execute(update(Job).where(Job.id == job.id, eligible).values(status="running", lease_token=token,
                          attempts=Job.attempts + 1, lease_until=now() + timedelta(seconds=get_settings().ai_timeout_seconds + 90))
                          .execution_options(synchronize_session=False))
        if claimed.rowcount != 1:
            return True
        job_id, target_id, user_id, kind = job.id, job.target_id, job.user_id, job.kind
    try:
        if kind == "analysis":
            from .materials import perform_analysis
            perform_analysis(factory, job_id, token)
            return True
        if kind == "style":
            from .design_upload import perform_style
            perform_style(factory, job_id, token)
            return True
        if kind != "site":
            raise HTTPException(422, "지원하지 않는 작업입니다.")
        with factory.begin() as db:
            if not locked_lease(db, job_id, token):
                return True
            user = lock_user(db, user_id)
            version = db.get(SiteVersion, target_id)
            site = db.get(PersonalSite, version.site_id)
            if not can_generate_ai_documents(user):
                raise HTTPException(403, "AI document generation requires a PREMIUM plan.")
            if version.facts_revision != user.facts_revision or user.account_status != "active":
                raise HTTPException(409, "프로필이 변경되어 생성을 중단했어요. 최신 정보로 다시 생성해 주세요.")
            version.status = "running"
            ai = provider_for(db, user_id)
            reference_materials, reference_images = version_reference_inputs(db, version.id, user.id, site.site_kind)
            if reference_images and not ai.supports_image_inputs("hard"):
                raise HTTPException(422, "PNG/JPG 참고 자료는 이 PC의 Codex CLI 연결에서만 사용할 수 있어요.")
            base = db.get(SiteVersion, version.base_version_id) if version.base_version_id else None
            inputs = {**version.public_input_snapshot, "kind": site.site_kind, "request": version.instruction,
                      "previous_code": base.code if base else None, "reference_materials": reference_materials,
                      "reference_images": [{"name": item["name"], "content_type": item["content_type"]}
                                           for item in reference_images]}
        result = ai.generate(site_prompt(inputs["kind"]), inputs, Generated, complexity="hard",
                             image_attachments=reference_images)
        gui = result.document.model_dump()
        code = update_fields(result.code.model_dump(), gui, preserve_layout=True)
        code["html"] = safe_markup(code["html"])
        error = validate_code(code)
        with factory.begin() as db:
            job = locked_lease(db, job_id, token)
            if not job:
                return True
            user = lock_user(db, user_id)
            version = db.get(SiteVersion, target_id)
            site = db.get(PersonalSite, version.site_id)
            if not can_generate_ai_documents(user):
                raise HTTPException(403, "AI document generation requires a PREMIUM plan.")
            # A reference may be withdrawn while the external CLI/API is
            # running.  Never persist a result created from a revoked input.
            version_reference_inputs(db, version.id, user.id, site.site_kind)
            stale = version.facts_revision != user.facts_revision or user.account_status != "active"
            conflict = version.validation.get("base_site_revision") != site.revision
            version.code, version.gui = code, gui
            version.status = "stale" if stale else "conflicted" if conflict else "invalid" if error else "preview_ready"
            version.error = "프로필이 변경됐습니다. 새로 생성해 주세요." if stale else "생성 중 다른 버전이 저장됐습니다. 결과를 확인한 뒤 복구로 새 버전을 만드세요." if conflict else error
            version.validation = {**version.validation, "model": ai.last_model, "transport": ai.transport}
            job.status, job.lease_until = "completed", None
    except Exception as exc:
        # Never persist provider bodies, prompts, CLI output, or secrets.
        message = str(exc.detail) if isinstance(exc, HTTPException) else "생성 작업을 마치지 못했습니다. 저장된 입력으로 다시 시도해 주세요."
        with factory.begin() as db:
            job = locked_lease(db, job_id, token)
            if job:
                job.status, job.error, job.lease_until = "failed", message, None
                if kind == "site":
                    version = db.get(SiteVersion, target_id)
                    version.status, version.error = "failed", message
                elif kind == "analysis":
                    from .models import AnalysisRun
                    run = db.get(AnalysisRun, target_id)
                    run.status, run.error = "failed", message
                elif kind == "style":
                    from .models import Material
                    row = db.get(Material, target_id)
                    row.metadata_json = {**row.metadata_json, "status": "failed", "error": message}
    return True


def main():
    print("[worker] Ready. Pending work is stored in the configured database.", flush=True)
    while True:
        try:
            if not process_one():
                time.sleep(1)
        except KeyboardInterrupt:
            return
        except Exception:
            print("[worker] Database unavailable; retrying.", flush=True)
            time.sleep(3)


if __name__ == "__main__":
    main()
