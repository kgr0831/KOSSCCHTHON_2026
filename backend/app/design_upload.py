"""Private design documents and durable reference images rendered from real AI output."""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Form, HTTPException, UploadFile
from sqlalchemy import select

from .ai import provider_for
from .auth import Actor, Input
from .common import DB, lock_user
from .config import get_settings
from .models import Job, Material, now
from .site_render import html_document, validate_code
from .sites import Code
from .styles import REFERENCE_DOCUMENT, get_style, style_data

router = APIRouter(prefix="/api/v1/portfolio-styles", tags=["design documents"])


def create_style(db, user, markdown, filename, source_style_id=None):
    def field(name):
        match = re.search(r"^" + name + r":\s*(.*?)\s*$", markdown, re.MULTILINE)
        return match.group(1).strip('"') if match else ""
    row = Material(user_id=user.id, material_kind="design_md", display_name=(field("display_name") or filename.removesuffix(".md"))[:150],
                   text_content=markdown, metadata_json={"source_file": filename, "description": field("gui_summary")[:500] or "내가 추가한 디자인 스타일",
                                                        "status": "queued", "source_style_id": source_style_id})
    db.add(row)
    db.flush()
    db.add(Job(user_id=user.id, kind="style", target_id=row.id))
    return style_data(row)


@router.post("/upload", status_code=202)
async def upload_design(file: UploadFile, db: DB, user: Actor, consent: bool = Form(False)):
    if not consent:
        raise HTTPException(422, "디자인 MD를 AI로 전송해 예시 이미지를 만드는 데 동의해 주세요.")
    raw = await file.read(65537)
    await file.close()
    filename = (file.filename or "design.md").replace("\\", "/").split("/")[-1][:200]
    if not filename.lower().endswith(".md") or len(raw) > 65536:
        raise HTTPException(422, "64KB 이하의 UTF-8 디자인 MD 파일을 선택해 주세요.")
    try:
        markdown = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(422, "UTF-8 인코딩의 MD 파일이 필요해요.") from None
    if not markdown.strip() or "\x00" in markdown:
        raise HTTPException(422, "내용이 있는 디자인 문서를 선택해 주세요.")
    lock_user(db, user.id)
    return create_style(db, user, markdown, filename)


@router.get("/{style_id}")
def detail(style_id: str, db: DB, user: Actor):
    return get_style(style_id, db, user)


class Preview(Input):
    consent: Literal[True]


@router.post("/{style_id}/preview", status_code=202)
def preview(style_id: str, body: Preview, db: DB, user: Actor):
    lock_user(db, user.id)
    style = get_style(style_id, db, user)
    if style_id.startswith("uploaded-"):
        row = db.scalar(select(Material).where(Material.id == style_id.removeprefix("uploaded-"), Material.user_id == user.id, Material.material_kind == "design_md"))
        if row.metadata_json.get("status") not in ("queued", "running", "ready"):
            row.metadata_json = {**row.metadata_json, "status": "queued", "error": None}
            job = db.scalar(select(Job).where(Job.kind == "style", Job.target_id == row.id))
            if job:
                job.status, job.error, job.lease_token, job.lease_until, job.available_at = "queued", None, None, None, now()
            else:
                db.add(Job(user_id=user.id, kind="style", target_id=row.id))
        return style_data(row)
    if style.get("status") in ("queued", "running", "ready"):
        return style
    return create_style(db, user, style["markdown"], style["source_file"], source_style_id=style_id)


def reference_images(code):
    node = shutil.which("node")
    if not node:
        raise HTTPException(503, "예시 이미지 생성에 Node.js가 필요해요.")
    result = subprocess.run([sys.executable, str(Path(__file__).with_name("cli_runner.py")), node, str(get_settings().project_root / "frontend/scripts/render-style.mjs")],
                            input=html_document(code), encoding="utf-8", capture_output=True, timeout=45)
    if result.returncode:
        raise HTTPException(503, "예시 이미지를 만들지 못했어요. Edge 설치를 확인하고 다시 시도해 주세요.")
    return json.loads(result.stdout)


def perform_style(factory, job_id, token):
    with factory.begin() as db:
        job = db.get(Job, job_id)
        user = lock_user(db, job.user_id)
        row = db.get(Material, job.target_id)
        if row.user_id != user.id or user.account_status != "active" or row.access_status != "available":
            raise HTTPException(409, "디자인을 사용할 수 없어요.")
        row.metadata_json = {**row.metadata_json, "status": "running"}
        markdown = row.text_content
        revision = row.revision
        ai = provider_for(db, user.id)
    result = ai.generate("디자인 예시 이미지를 위한 반응형 웹 포트폴리오를 만드세요. 입력의 가상 인물만 사용하고 디자인 MD의 색상·서체·배치를 따르세요. "
                         "큰 소개 hero와 작업 카드 3개, 작은 소개 영역으로 간결하게 구성하세요. 이력서 표로 만들지 마세요. "
                         "HTML은 body 내부 마크업이며 h1을 포함하세요. CSS는 별도 문자열이고 javascript는 빈 문자열로 반환하세요. "
                         "외부 리소스·네트워크·iframe·폼·인라인 이벤트를 사용하지 마세요. 390px 모바일에서 가로 넘침을 방지하세요. "
                         "JSON 객체에 html, css, javascript 키만 담고 각 문자열 내부의 따옴표와 줄바꿈을 올바르게 이스케이프하세요. 마크다운 코드 블록 없이 반환하세요.",
                         {"style_markdown": markdown, "profile": REFERENCE_DOCUMENT}, Code, complexity="hard")
    code = result.model_dump()
    if validate_code(code):
        raise HTTPException(422, "예시 화면을 검증하지 못했어요. 다시 시도해 주세요.")
    images = reference_images(code)
    with factory.begin() as db:
        job = db.get(Job, job_id)
        if job.lease_token != token or job.status != "running":
            return
        user = lock_user(db, job.user_id)
        row = db.get(Material, job.target_id)
        if row.user_id != user.id or user.account_status != "active" or row.access_status != "available" or row.revision != revision:
            raise HTTPException(409, "디자인 사용이 철회됐어요.")
        row.metadata_json = {**row.metadata_json, **images, "status": "ready", "error": None, "model": ai.last_model}
        job.status, job.lease_until = "completed", None
