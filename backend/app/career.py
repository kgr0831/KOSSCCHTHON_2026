import hashlib
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import Field
from sqlalchemy import select

from .ai import AIProvider, get_ai
from .auth import Actor, Input
from .common import DB, data
from .models import CareerPlan, User
from .profiles import public_user, public_users

router = APIRouter(prefix="/api/v1")


@router.get("/recommendations")
def recommendations(db: DB, user: Actor):
    people = list(db.scalars(select(User).where(User.id != user.id, User.account_status == "active")))
    # Deliberately arbitrary: no inferred compatibility, trust, or fabricated scores.
    people.sort(key=lambda x: hashlib.sha256(f"{date.today()}:{user.id}:{x.id}".encode()).digest())
    return {"mode": "temporary", "label": "임시 추천 · 적합도 순위가 아닌 임의 순서예요",
            "items": public_users(db, people[:6])}


class Step(Input):
    title: str = Field(max_length=200)
    description: str = Field(max_length=2000)
    actions: list[str] = Field(min_length=1, max_length=8)


class Roadmap(Input):
    headline: str = Field(max_length=300)
    insight: str = Field(max_length=4000)
    steps: list[Step] = Field(min_length=1, max_length=6)


class Goal(Input):
    goal: str = Field(min_length=1, max_length=3000)
    consent: Literal[True]


@router.get("/me/career-plans")
def plans(db: DB, user: Actor):
    return {"items": [data(x) for x in db.scalars(select(CareerPlan).where(CareerPlan.user_id == user.id).order_by(CareerPlan.created_at.desc()))]}


@router.post("/me/career-plans", status_code=201)
def plan(body: Goal, db: DB, user: Actor, ai: AIProvider = Depends(get_ai)):
    result = ai.generate("공개된 현재 경험과 목표를 바탕으로 현실적인 단계별 커리어 계획을 한국어로 제안하세요. 미래 계획이며 이미 성취한 사실처럼 쓰지 마세요. 각 단계에 이번 주 실천할 행동을 포함하세요.",
                         {"profile": public_user(db, user), "goal": body.goal}, Roadmap, complexity="hard")
    row = CareerPlan(user_id=user.id, goal=body.goal, content=result.model_dump(), facts_revision=user.facts_revision)
    db.add(row)
    db.flush()
    return data(row)
