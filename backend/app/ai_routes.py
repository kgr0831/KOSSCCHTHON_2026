from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import Field

from .ai import AIProvider, cli_command, get_ai, model_ids, read_api_key
from .auth import Actor, Input
from .common import DB, data, lock_user, required, update_revision
from .models import AISettings, User

router = APIRouter(prefix="/api/v1")


@router.get("/me/ai-settings")
def settings(db: DB, user: Actor):
    row = db.get(AISettings, user.id)
    return data(row) if row else {"transport": "api", "easy_model": "", "hard_model": "", "revision": 0}


@router.get("/ai/providers")
def providers(user: Actor):
    from fastapi import HTTPException
    available, error = [], None
    try:
        available = [x for x in model_ids() if "claude" in x.lower() or ("gemini" in x.lower() and "flash" in x.lower())]
    except HTTPException as exc:
        error = exc.detail
    return {"api": {"configured": bool(read_api_key()), "models": available, "error": error},
            "cli": {"claude_installed": bool(cli_command("claude")), "gemini_installed": bool(cli_command("gemini")),
                    "connection": "separate_local_login"},
            "routing": {"easy": "Gemini Flash · 미제공 시 Claude Haiku", "hard": "Claude Sonnet"},
            "consent_text": "생성에 필요한 프로필·선택 자료·작성 내용이 선택한 AI 제공자로 전송됩니다. 결과는 승인 전까지 확정 프로필에 반영하지 않습니다."}


class ProviderEdit(Input):
    transport: Literal["api", "cli", "hybrid"]
    easy_model: str = Field(default="", max_length=150)
    hard_model: str = Field(default="", max_length=150)
    revision: int = Field(ge=0)


@router.put("/me/ai-settings")
def edit_settings(body: ProviderEdit, db: DB, user: Actor):
    from fastapi import HTTPException

    from .ai import choose_model
    lock_user(db, user.id)
    if body.transport == "api":
        if body.easy_model:
            choose_model("easy", body.easy_model)
        if body.hard_model:
            choose_model("hard", body.hard_model)
    row = db.get(AISettings, user.id)
    if not row:
        if body.revision != 0:
            raise HTTPException(409, "설정을 다시 불러와 주세요.")
        row = AISettings(user_id=user.id, **body.model_dump(exclude={"revision"}))
        db.add(row)
        db.flush()
    else:
        update_revision(db, row, body.revision, body.model_dump(exclude={"revision"}))
    return data(row)


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
def writing(body: WritingInput, db: DB, user: Actor, ai: AIProvider = Depends(get_ai)):
    from .profiles import public_user
    return ai.generate("입력된 실제 경험을 바탕으로 읽기 쉬운 한국어 초안을 작성하세요. 새 사실을 만들지 말고 부족한 정보는 questions로 물어보세요.",
                       {"kind": body.kind, "notes": body.text, "profile": public_user(db, user)}, WritingDraft)
