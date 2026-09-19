from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import select

from .ai import get_ai
from .auth import Actor, Input
from .common import DB, Page, required
from .models import Affiliation, CareerEvent, Preference, Project, Tag, University, User, UserTag
from .profiles import public_user

router = APIRouter(prefix="/api/v1")


class SearchFilters(Input):
    university_ids: list[str] = Field(default_factory=list, max_length=20)
    department: str = Field(default="", max_length=150)
    enrollment_status: Literal["student", "graduate", "leave", "other"] | None = None
    company: str = Field(default="", max_length=200)
    role: str = Field(default="", max_length=200)
    role_tag_ids: list[str] = Field(default_factory=list, max_length=30)
    skill_tag_ids: list[str] = Field(default_factory=list, max_length=30)
    interest_tag_ids: list[str] = Field(default_factory=list, max_length=30)
    project_available: bool | None = None
    coffee_chat_available: bool | None = None
    learning_stage: str = Field(default="", max_length=50)
    activity_goal: str = Field(default="", max_length=1000)
    collaboration_mode: Literal["online", "offline", "hybrid", "flexible"] | None = None
    hours_per_week_min: int | None = Field(default=None, ge=0, le=168)


class SearchInput(Input):
    purpose: Literal["coffee_chat", "team_building", "beginner_team_building"] = "coffee_chat"
    filters: SearchFilters = Field(default_factory=SearchFilters)
    match_direction: Literal["similar", "complementary"] = "similar"


def filtered_users(db, user, body):
    f = body.filters
    query = select(User).join(Preference).where(User.account_status == "active", User.id != user.id)
    if f.university_ids or f.department or f.enrollment_status:
        school = select(Affiliation.user_id).where(Affiliation.withdrawn.is_(False))
        if f.university_ids:
            school = school.where(Affiliation.university_id.in_(f.university_ids))
        if f.department:
            school = school.where(Affiliation.department == f.department)
        if f.enrollment_status:
            school = school.where(Affiliation.enrollment_status == f.enrollment_status)
        query = query.where(User.id.in_(school))
    if f.company or f.role:
        career = select(CareerEvent.user_id).where(CareerEvent.withdrawn.is_(False))
        if f.company:
            career = career.where(CareerEvent.organization_name == f.company)
        if f.role:
            career = career.where(CareerEvent.title == f.role)
        query = query.where(User.id.in_(career))
    for kind, ids in (("role", f.role_tag_ids), ("skill", f.skill_tag_ids), ("interest", f.interest_tag_ids)):
        for tag_id in ids:
            tag = required(db, Tag, tag_id)
            if tag.kind != kind:
                raise HTTPException(422, "태그 종류를 확인해 주세요.")
            query = query.where(User.id.in_(select(UserTag.user_id).where(UserTag.tag_id == tag_id)))
    for key in ("project_available", "coffee_chat_available", "collaboration_mode"):
        value = getattr(f, key)
        if value is not None:
            query = query.where(getattr(Preference, key) == value)
    if f.learning_stage:
        query = query.where(Preference.learning_stage == f.learning_stage)
    if f.activity_goal:
        query = query.where(Preference.activity_goal == f.activity_goal)
    if f.hours_per_week_min is not None:
        query = query.where(Preference.hours_per_week >= f.hours_per_week_min)
    return query


@router.post("/search/users")
def search_users(body: SearchInput, db: DB, user: Actor, page: Page):
    result = page.page(db, filtered_users(db, user, body), User, lambda row: {
        "user": public_user(db, row), "reason": "설정한 탐색 조건에 맞는 동문입니다. 공개한 경험과 관심사를 살펴보세요.",
        "matched_conditions": []})
    return result | {"result_kind": "filtered", "ranking_status": "pending_design"}


@router.get("/search/filters")
def filters(db: DB, user: Actor):
    return {"universities": [{"id": x.id, "name": x.name} for x in db.scalars(select(University).where(University.is_supported.is_(True)))],
            "tags": [{"id": x.id, "kind": x.kind, "name": x.name} for x in db.scalars(select(Tag))],
            "learning_stages": ["exploring", "starting", "learning", "building", "experienced"]}


class InterpretInput(Input):
    text: str = Field(min_length=1, max_length=3000)
    purpose: Literal["coffee_chat", "team_building", "beginner_team_building"] = "coffee_chat"


@router.post("/search/interpret")
def interpret(body: InterpretInput, db: DB, user: Actor, ai=Depends(get_ai)):
    choices = filters(db, user)
    result = ai.generate("검색 실행 없이 사용자 문장을 수정 가능한 필터로 해석하세요. 학교·태그 ID는 제공한 목록에서만 사용하세요.",
                         body.model_dump() | choices, SearchInput)
    valid_ids = {x["id"] for x in choices["tags"]}
    valid_universities = {x["id"] for x in choices["universities"]}
    f = result.filters
    if not set(f.university_ids) <= valid_universities or not set(
        f.skill_tag_ids + f.role_tag_ids + f.interest_tag_ids) <= valid_ids:
        raise HTTPException(502, "AI가 해석한 조건을 확인할 수 없습니다. 직접 필터를 선택해 주세요.")
    return result


@router.post("/projects/{project_id}/candidate-search")
def candidates(project_id: str, body: SearchInput, db: DB, user: Actor, page: Page):
    project = required(db, Project, project_id)
    if project.creator_id != user.id:
        raise HTTPException(403, "프로젝트 관리자만 후보를 검색할 수 있습니다.")
    return search_users(body, db, user, page)
