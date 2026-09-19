from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field

from .ai import AIProvider, cli_command, get_ai, model_ids, read_api_key
from .auth import Actor, Input
from .common import DB, data, lock_user, required, update_revision
from .config import get_settings
from .local_runtime import cli_allowed, device_id
from .models import AISettings, User
from .subscriptions import AIPlanUser, can_generate_ai_documents

router = APIRouter(prefix="/api/v1")


@router.get("/me/ai-settings")
def settings(db: DB, user: Actor):
    row = db.get(AISettings, user.id)
    result = data(row) if row else {"transport": "api", "easy_model": "", "hard_model": "", "revision": 0,
                                  "cli_provider": "codex", "cli_model": "", "cli_connections": []}
    result["cli_connections"] = [{**item, "current_pc": cli_allowed() and item["device_id"] == device_id()}
                                 for item in result["cli_connections"]]
    if get_settings().environment == "production":
        result["transport"] = "api"
    return result


@router.get("/ai/providers")
def providers(user: Actor):
    from fastapi import HTTPException
    available, error = [], None
    try:
        available = [x for x in model_ids() if "claude" in x.lower() or ("gemini" in x.lower() and "flash" in x.lower())]
    except HTTPException as exc:
        error = exc.detail
    return {"api": {"configured": bool(read_api_key()), "models": available, "error": error},
            "cli": {"allowed": cli_allowed(), "codex_installed": cli_allowed() and bool(cli_command("codex")),
                    "claude_installed": cli_allowed() and bool(cli_command("claude")), "gemini_installed": cli_allowed() and bool(cli_command("gemini")),
                    "connection": "separate_local_login"},
            "routing": {"easy": "Gemini Flash · 미제공 시 Claude Haiku", "hard": "Claude Sonnet"},
            "consent_text": "생성에 필요한 프로필·선택 자료·작성 내용이 선택한 AI 제공자로 전송됩니다. 결과는 승인 전까지 확정 프로필에 반영하지 않습니다."}


class ProviderEdit(Input):
    transport: Literal["api", "cli", "hybrid"]
    easy_model: str = Field(default="", max_length=150)
    hard_model: str = Field(default="", max_length=150)
    cli_provider: Literal["codex", "claude"] | None = None
    cli_model: str | None = Field(default=None, max_length=150)
    revision: int = Field(ge=0)


@router.put("/me/ai-settings")
def edit_settings(body: ProviderEdit, db: DB, user: Actor):
    from fastapi import HTTPException

    from .ai import choose_model
    if not cli_allowed() and body.transport != "api":
        raise HTTPException(403, "배포 서버에서는 API 연결을 사용해 주세요. 구독 CLI는 로컬 실행 전용입니다.")
    lock_user(db, user.id)
    if body.transport == "api":
        if body.easy_model:
            choose_model("easy", body.easy_model)
        if body.hard_model:
            choose_model("hard", body.hard_model)
    row = db.get(AISettings, user.id)
    changes = body.model_dump(exclude={"revision", "cli_provider", "cli_model"})
    if cli_allowed():
        family = body.cli_provider or (row.cli_provider if row else "codex")
        model = body.cli_model if body.cli_model is not None else (row.cli_model if row else "")
        connection = next((x for x in (row.cli_connections if row else [])
                           if x["provider"] == family and x["device_id"] == device_id()), None)
        if body.transport != "api" and (not connection or connection["status"] != "connected"):
            raise HTTPException(409, "먼저 이 PC의 CLI 연결을 확인해 주세요.")
        if model and (not connection or model not in connection["models"]):
            raise HTTPException(422, "연결을 확인한 CLI의 모델 목록에서 선택해 주세요.")
        changes.update(cli_provider=family, cli_model=model)
    if not row:
        if body.revision != 0:
            raise HTTPException(409, "설정을 다시 불러와 주세요.")
        row = AISettings(user_id=user.id, **changes)
        db.add(row)
        db.flush()
    else:
        update_revision(db, row, body.revision, changes)
    return settings(db, user)


@router.post("/me/ai-cli-connections/{family}/check")
def check_cli(family: Literal["codex", "claude"], db: DB, user: Actor):
    if not cli_allowed():
        raise HTTPException(403, "CLI 연결 확인은 PC에서 BAT로 실행한 두드리에서만 가능합니다.")
    from .cli_metadata import probe_cli

    connection = probe_cli(family)
    lock_user(db, user.id)
    row = db.get(AISettings, user.id)
    if not row:
        row = AISettings(user_id=user.id)
        db.add(row)
        db.flush()
    # Only the explicit metadata projection can reach DB. Never accept paths or credentials from HTTP.
    remaining = [x for x in row.cli_connections if (x["device_id"], x["provider"]) != (connection["device_id"], family)]
    row.cli_connections = [*remaining, connection]
    row.revision += 1
    db.flush()
    return settings(db, user)


class DraftInput(Input):
    purpose: str = Field(min_length=1, max_length=200)
    recipient_id: str | None = None
    text: str = Field(default="", max_length=12000)


class CoffeeDraft(Input):
    questions: str = Field(min_length=1, max_length=5000)
    introduction: str = Field(max_length=3000)


@router.post("/coffee-chat-drafts")
def coffee_draft(body: DraftInput, db: DB, user: Actor, ai: AIProvider = Depends(get_ai)):
    from .profiles import public_user
    counterpart = public_user(db, required(db, User, body.recipient_id)) if body.recipient_id else None
    return ai.generate("커피챗 요청을 위한 구체적인 질문 3개와 간단한 소개 초안을 한국어로 작성하세요. 전송하지 않고 사용자가 수정할 초안입니다.",
                       {"purpose": body.purpose, "me": public_user(db, user), "recipient": counterpart, "notes": body.text}, CoffeeDraft)


class WritingInput(Input):
    kind: Literal["profile", "experience", "recruitment", "career"]
    text: str = Field(min_length=1, max_length=15000)


class WritingDraft(Input):
    title: str = Field(max_length=200)
    text: str = Field(max_length=15000)
    questions: list[str] = Field(default_factory=list, max_length=8)


@router.post("/ai/writing-drafts")
def writing(body: WritingInput, db: DB, user: AIPlanUser, ai: AIProvider = Depends(get_ai)):
    from .profiles import public_user
    user = lock_user(db, user.id)
    if not can_generate_ai_documents(user):
        raise HTTPException(403, "AI document generation requires a PREMIUM plan.")
    return ai.generate("입력된 실제 경험을 바탕으로 읽기 쉬운 한국어 초안을 작성하세요. 새 사실을 만들지 말고 부족한 정보는 questions로 물어보세요.",
                       {"kind": body.kind, "notes": body.text, "profile": public_user(db, user)}, WritingDraft)
