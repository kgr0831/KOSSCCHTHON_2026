"""Private source text and reviewable AI suggestions; nothing is auto-approved."""
import json
import subprocess
import sys
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import Field
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from .ai import provider_for
from .auth import Actor, Input
from .common import DB, data, facts_changed, lock_user, owner, required, update_revision
from .models import AnalysisInput, AnalysisRun, CareerEvent, Job, Material, Profile, Suggestion

router = APIRouter(prefix="/api/v1")


class TextSource(Input):
    display_name: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=100000)


@router.get("/me/source-materials")
def sources(db: DB, user: Actor):
    return {"items": [data(x, exclude=("text_content", "object_key")) for x in db.scalars(
        select(Material).where(Material.user_id == user.id, Material.material_kind != "design_md").order_by(Material.created_at.desc()))]}


@router.post("/me/source-materials", status_code=201)
def add_text(body: TextSource, db: DB, user: Actor):
    row = Material(user_id=user.id, material_kind="text", display_name=body.display_name, text_content=body.text)
    db.add(row)
    db.flush()
    return data(row, exclude=("text_content", "object_key"))


@router.post("/me/source-materials/upload", status_code=201)
async def upload(file: UploadFile, db: DB, user: Actor):
    raw = await file.read(10 * 1024 * 1024 + 1)
    await file.close()
    if len(raw) > 10 * 1024 * 1024:
        raise HTTPException(413, "로컬 업로드는 파일당 10MB까지 지원해요.")
    name = (file.filename or "자료").replace("\\", "/").split("/")[-1][:200]
    try:
        if name.lower().endswith(".pdf"):
            text = await run_in_threadpool(extract_pdf, raw)
        elif name.lower().endswith((".txt", ".md")):
            text = raw.decode("utf-8-sig")
        else:
            raise HTTPException(422, "텍스트 PDF, TXT, MD 파일을 지원해요.")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(422, "텍스트를 읽을 수 없어요. 암호 없는 텍스트 PDF 또는 UTF-8 파일을 선택해 주세요.") from None
    if not text.strip() or len(text) > 100000:
        raise HTTPException(422, "1~100,000자의 텍스트 자료를 선택해 주세요. 스캔 PDF는 텍스트로 붙여넣어 주세요.")
    return add_text(TextSource(display_name=name, text=text), db, user)


def extract_pdf(raw):
    result = subprocess.run([sys.executable, str(Path(__file__).with_name("pdf_extract.py"))],
                            input=raw, capture_output=True, timeout=20)
    if result.returncode:
        raise ValueError("PDF extraction failed")
    return json.loads(result.stdout.decode("utf-8"))["text"]


@router.get("/me/source-materials/{material_id}")
def source(material_id: str, db: DB, user: Actor):
    return data(owner(required(db, Material, material_id), user), exclude=("object_key",))


@router.delete("/me/source-materials/{material_id}", status_code=204)
def withdraw(material_id: str, db: DB, user: Actor):
    lock_user(db, user.id)
    row = owner(required(db, Material, material_id), user)
    row.access_status, row.text_content, row.revision = "withdrawn", None, row.revision + 1


class Analyze(Input):
    material_ids: list[str] = Field(min_length=1, max_length=10)
    consent: Literal[True]


@router.post("/me/analysis-runs", status_code=202)
def analyze(body: Analyze, db: DB, user: Actor):
    lock_user(db, user.id)
    materials = [owner(required(db, Material, x), user) for x in set(body.material_ids)]
    if any(x.access_status != "available" or not x.text_content or x.material_kind == "design_md" for x in materials):
        raise HTTPException(409, "사용 가능한 자료를 다시 선택해 주세요.")
    run = AnalysisRun(user_id=user.id, purpose="profile")
    db.add(run)
    db.flush()
    db.add_all([AnalysisInput(run_id=run.id, material_id=x.id, material_revision=x.revision) for x in materials])
    db.add(Job(user_id=user.id, kind="analysis", target_id=run.id))
    return data(run)


@router.get("/me/analysis-runs")
def runs(db: DB, user: Actor):
    return {"items": [data(x) for x in db.scalars(select(AnalysisRun).where(AnalysisRun.user_id == user.id).order_by(AnalysisRun.created_at.desc()))]}


@router.get("/me/suggestions")
def suggestions(db: DB, user: Actor):
    return {"items": [data(x) for x in db.scalars(select(Suggestion).where(Suggestion.user_id == user.id).order_by(Suggestion.created_at.desc()))]}


class Proposed(Input):
    kind: Literal["bio", "experience"]
    title: str = Field(max_length=200)
    text: str = Field(min_length=1, max_length=5000)
    material_id: str
    quote: str = Field(min_length=1, max_length=700)


class AnalysisResult(Input):
    suggestions: list[Proposed] = Field(max_length=15)


def checked_inputs(db, run):
    result = []
    for link in db.scalars(select(AnalysisInput).where(AnalysisInput.run_id == run.id)):
        material = db.get(Material, link.material_id)
        if not material or material.user_id != run.user_id or material.access_status != "available" or material.revision != link.material_revision:
            raise HTTPException(409, "자료 사용이 철회되거나 변경돼 분석 결과를 사용할 수 없어요.")
        result.append({"material_id": material.id, "text": material.text_content})
    return result


def perform_analysis(factory, job_id, token):
    with factory.begin() as db:
        job = db.get(Job, job_id)
        run = db.get(AnalysisRun, job.target_id)
        user = lock_user(db, run.user_id)
        if user.account_status != "active":
            raise HTTPException(403, "계정이 비활성 상태입니다.")
        inputs = checked_inputs(db, run)
        run.status = "running"
        profile_revision = db.get(Profile, run.user_id).revision
        ai = provider_for(db, run.user_id)
    result = ai.generate("자료에서 자기소개와 활동 경험 제안만 추출하세요. 확정 사실로 저장되지 않습니다. quote는 해당 material_id의 원문에서 그대로 인용해야 합니다. 날짜·기관·자격을 추측하지 마세요.",
                         {"materials": inputs}, AnalysisResult, complexity="easy")
    with factory.begin() as db:
        job = db.get(Job, job_id)
        if job.lease_token != token or job.status != "running":
            return
        run = db.get(AnalysisRun, job.target_id)
        lock_user(db, run.user_id)
        inputs = {x["material_id"]: x["text"] for x in checked_inputs(db, run)}
        for suggestion in result.suggestions:
            if suggestion.material_id not in inputs or suggestion.quote not in inputs[suggestion.material_id]:
                continue
            db.add(Suggestion(user_id=run.user_id, run_id=run.id, target_kind=suggestion.kind,
                              target_id=run.user_id if suggestion.kind == "bio" else None,
                              target_revision=profile_revision if suggestion.kind == "bio" else None,
                              field_key="bio" if suggestion.kind == "bio" else "description",
                              proposed_value={"title": suggestion.title, "text": suggestion.text},
                              evidence=[{"material_id": suggestion.material_id, "quote": suggestion.quote}]))
        run.status, job.status, job.lease_until = "completed", "completed", None


class Decide(Input):
    decision: Literal["accepted", "rejected"]
    revision: int = Field(ge=1)
    title: str = Field(default="", max_length=200)
    text: str = Field(default="", max_length=5000)
    is_public: bool = False


@router.post("/me/suggestions/{suggestion_id}/decision")
def decide(suggestion_id: str, body: Decide, db: DB, user: Actor):
    lock_user(db, user.id)
    row = owner(required(db, Suggestion, suggestion_id), user)
    db.refresh(row)
    if row.decision != "pending":
        raise HTTPException(409, "이미 검토한 제안입니다.")
    if body.decision == "accepted":
        if not body.text.strip():
            raise HTTPException(422, "승인할 내용을 입력해 주세요.")
        checked_inputs(db, required(db, AnalysisRun, row.run_id))
        if row.target_kind == "bio":
            profile = required(db, Profile, user.id)
            update_revision(db, profile, row.target_revision, {"bio": body.text, "bio_is_public": body.is_public})
        else:
            if not body.title.strip():
                raise HTTPException(422, "경험 제목을 입력해 주세요.")
            event = CareerEvent(user_id=user.id, event_kind="activity", title=body.title,
                                description=body.text, is_public=body.is_public)
            db.add(event)
            db.flush()
            row.target_id = event.id
        facts_changed(db, user.id)
    update_revision(db, row, body.revision, {"decision": body.decision, "accepted_value":
                    {"title": body.title, "text": body.text, "is_public": body.is_public} if body.decision == "accepted" else None})
    return data(row)
