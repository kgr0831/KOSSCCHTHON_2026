from collections import defaultdict
from datetime import date
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import Field, model_validator
from sqlalchemy import delete, select

from .auth import Actor, Input, current_user
from .common import DB, Page, data, facts_changed, lock_user, owner, required, update_revision
from .models import (
    Affiliation,
    CareerEvent,
    Preference,
    Profile,
    ProfileAvatar,
    Project,
    ProjectMember,
    Tag,
    University,
    User,
    UserTag,
    Verification,
    now,
)

router = APIRouter(prefix="/api/v1")


def affiliations_for(db, user_id, public=False):
    query = select(Affiliation, University.name).join(University).where(
        Affiliation.user_id == user_id, Affiliation.withdrawn.is_(False))
    if public:
        query = query.where(Affiliation.is_public.is_(True))
    return [data(affiliation) | {"university_name": university_name, "status_source": "user_input"}
            for affiliation, university_name in db.execute(query)]


def tags_for(db, user_id, public=False):
    query = select(UserTag, Tag.name, Tag.kind).join(Tag).where(UserTag.user_id == user_id)
    if public:
        query = query.where(UserTag.is_public.is_(True))
    return [data(user_tag) | {"name": name, "kind": kind}
            for user_tag, name, kind in db.execute(query)]


def public_users(db, users):
    """Serialize several public profiles without issuing queries per person."""
    user_ids = [user.id for user in users]
    if not user_ids:
        return []

    profiles = {profile.user_id: profile for profile in db.scalars(
        select(Profile).where(Profile.user_id.in_(user_ids)))}
    affiliations = defaultdict(list)
    for affiliation, university_name in db.execute(select(Affiliation, University.name).join(University).where(
            Affiliation.user_id.in_(user_ids), Affiliation.withdrawn.is_(False), Affiliation.is_public.is_(True))):
        affiliations[affiliation.user_id].append(data(affiliation) | {
            "university_name": university_name, "status_source": "user_input"})

    tags = defaultdict(list)
    for user_tag, name, kind in db.execute(select(UserTag, Tag.name, Tag.kind).join(Tag).where(
            UserTag.user_id.in_(user_ids), UserTag.is_public.is_(True))):
        tags[user_tag.user_id].append(data(user_tag) | {"name": name, "kind": kind})

    careers = defaultdict(list)
    for career in db.scalars(select(CareerEvent).where(CareerEvent.user_id.in_(user_ids),
            CareerEvent.is_public.is_(True), CareerEvent.withdrawn.is_(False))):
        careers[career.user_id].append(data(career, exclude=("user_id",)))

    memberships = defaultdict(list)
    for member, project in db.execute(select(ProjectMember, Project).join(Project).where(
            ProjectMember.user_id.in_(user_ids), ProjectMember.is_public.is_(True),
            Project.visibility == "public")):
        memberships[member.user_id].append(data(member) | {
            "project_title": project.title, "summary": project.summary})

    preferences = {preference.user_id: preference for preference in db.scalars(
        select(Preference).where(Preference.user_id.in_(user_ids), Preference.is_public.is_(True)))}
    verifications = defaultdict(list)
    for verification in db.scalars(select(Verification).where(Verification.user_id.in_(user_ids),
            (Verification.expires_at.is_(None)) | (Verification.expires_at > now()))):
        verifications[verification.user_id].append(verification)

    result = []
    for user in users:
        profile = profiles.get(user.id)
        if not profile:
            raise HTTPException(404, "프로필을 찾을 수 없습니다.")
        visible_affiliations = affiliations[user.id]
        public_profile = {
            "id": user.id,
            "display_name": profile.display_name if profile.name_is_public else "동문",
            "school_affiliations": visible_affiliations,
            "tags": tags[user.id],
            "career_events": careers[user.id],
            "project_members": memberships[user.id],
        }
        if profile.bio_is_public:
            public_profile["bio"] = profile.bio
        if profile.avatar_is_public:
            public_profile["avatar_url"] = profile.avatar_url
        if preference := preferences.get(user.id):
            public_profile["preferences"] = data(preference, exclude=("user_id", "revision"))
        visible_ids = {affiliation["id"] for affiliation in visible_affiliations}
        public_profile["verifications"] = [{
            "kind": verification.verification_kind,
            "verified_at": data(verification)["verified_at"],
            "meaning": "이메일 접근 확인",
        } for verification in verifications[user.id]
            if verification.verification_kind != "school" or verification.school_affiliation_id in visible_ids]
        result.append(public_profile)
    return result


def public_user(db, user):
    return public_users(db, [user])[0]


@router.get("/me")
def me(db: DB, user: Actor):
    profile_and_preferences = db.execute(select(Profile, Preference).join(
        Preference, Preference.user_id == Profile.user_id).where(Profile.user_id == user.id)).one_or_none()
    if not profile_and_preferences:
        raise HTTPException(404, "프로필을 찾을 수 없습니다.")
    profile, preferences = profile_and_preferences
    return {"id": user.id, "login_email": user.login_email, "account_status": user.account_status,
            "subscription_plan": user.subscription_plan,
            "google_connected": bool(user.supabase_user_id),
            "profile": data(profile),
            "school_affiliations": affiliations_for(db, user.id),
            "preferences": data(preferences), "tags": tags_for(db, user.id)}


class ProfilePatch(Input):
    revision: int = Field(ge=1)
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    bio: str | None = Field(default=None, max_length=5000)
    name_is_public: bool | None = None
    bio_is_public: bool | None = None
    avatar_is_public: bool | None = None


@router.patch("/me")
def edit_me(body: ProfilePatch, db: DB, user: Actor):
    lock_user(db, user.id)
    changes = body.model_dump(exclude_unset=True, exclude={"revision"}, mode="json")
    if any(value is None for key, value in changes.items() if key != "avatar_url"):
        raise HTTPException(422, "필수 프로필 값은 null로 바꿀 수 없습니다.")
    profile = update_revision(db, required(db, Profile, user.id), body.revision, changes)
    facts_changed(db, user.id)
    return data(profile)


MAX_AVATAR_BYTES = 2 * 1024 * 1024
# Multipart boundaries and the field name add a small amount of framing around
# the file bytes.  This cap is enforced before Starlette parses/spools the
# multipart body in main.py.
MAX_AVATAR_REQUEST_BYTES = MAX_AVATAR_BYTES + 128 * 1024


def image_content_type(raw: bytes) -> str | None:
    """Recognize only non-scriptable raster image formats from their bytes."""
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if raw.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if raw.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if raw.startswith(b"RIFF") and raw[8:12] == b"WEBP":
        return "image/webp"
    return None


@router.post("/me/avatar")
async def upload_avatar(file: UploadFile, db: DB, user: Actor):
    """Persist a small profile avatar in PostgreSQL, not an ephemeral disk."""
    raw = await file.read(MAX_AVATAR_BYTES + 1)
    await file.close()
    content_type = image_content_type(raw)
    if not raw or len(raw) > MAX_AVATAR_BYTES or not content_type:
        raise HTTPException(422, "PNG, JPEG, GIF 또는 WebP 이미지(최대 2MB)를 선택해 주세요.")
    lock_user(db, user.id)
    avatar = db.get(ProfileAvatar, user.id)
    if avatar:
        avatar.content_type, avatar.content, avatar.byte_size = content_type, raw, len(raw)
        avatar.revision += 1
        avatar.updated_at = now()
    else:
        avatar = ProfileAvatar(user_id=user.id, content_type=content_type, content=raw, byte_size=len(raw))
        db.add(avatar)
        db.flush()
    profile = required(db, Profile, user.id)
    profile = update_revision(db, profile, profile.revision,
                              {"avatar_url": f"/api/v1/users/{user.id}/avatar?v={avatar.revision}"})
    facts_changed(db, user.id)
    return data(profile)


@router.delete("/me/avatar", status_code=204)
def remove_avatar(db: DB, user: Actor, revision: int = Query(ge=1)):
    lock_user(db, user.id)
    avatar = db.get(ProfileAvatar, user.id)
    if avatar:
        db.delete(avatar)
    update_revision(db, required(db, Profile, user.id), revision, {"avatar_url": None})
    facts_changed(db, user.id)


@router.get("/users/{user_id}/avatar")
def avatar(user_id: str, db: DB, authorization: str | None = Header(default=None)):
    person = required(db, User, user_id)
    profile = required(db, Profile, user_id)
    actor = current_user(db, authorization) if authorization else None
    if person.account_status != "active" or not profile.avatar_is_public and (not actor or actor.id != user_id):
        # A missing response avoids turning private avatar URLs into an oracle.
        raise HTTPException(404, "프로필 이미지를 찾을 수 없습니다.")
    image = db.get(ProfileAvatar, user_id)
    if not image:
        raise HTTPException(404, "프로필 이미지를 찾을 수 없습니다.")
    return Response(content=image.content, media_type=image.content_type,
                    headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/users/{user_id}")
def user_profile(user_id: str, db: DB, actor: Actor):
    user = required(db, User, user_id)
    if user.account_status != "active":
        raise HTTPException(404, "공개 프로필을 찾을 수 없습니다.")
    result = public_user(db, user)
    # Request availability is actionable even when other activity conditions are private.
    result["can_request_coffee_chat"] = actor.id != user.id and required(db, Preference, user.id).coffee_chat_available
    return result


class AffiliationInput(Input):
    university_id: str
    department: str = Field(default="", max_length=150)
    enrollment_status: Literal["student", "graduate", "leave", "other"] = "student"
    entry_year: int | None = Field(default=None, ge=1900, le=2200)
    graduation_year: int | None = Field(default=None, ge=1900, le=2200)
    is_public: bool = True

    @model_validator(mode="after")
    def dates(self):
        if self.entry_year and self.graduation_year and self.entry_year > self.graduation_year:
            raise ValueError("졸업 연도는 입학 연도보다 빨라질 수 없습니다.")
        return self


class AffiliationEdit(AffiliationInput):
    revision: int = Field(ge=1)


@router.get("/me/school-affiliations")
def my_affiliations(db: DB, user: Actor):
    return {"items": affiliations_for(db, user.id), "next_cursor": None}


@router.post("/me/school-affiliations", status_code=201)
def add_affiliation(body: AffiliationInput, db: DB, user: Actor):
    required(db, University, body.university_id)
    lock_user(db, user.id)
    row = Affiliation(user_id=user.id, **body.model_dump())
    db.add(row)
    facts_changed(db, user.id)
    db.flush()
    return data(row)


@router.patch("/me/school-affiliations/{row_id}")
def edit_affiliation(row_id: str, body: AffiliationEdit, db: DB, user: Actor):
    lock_user(db, user.id)
    row = owner(required(db, Affiliation, row_id), user)
    if row.withdrawn or row.university_id != body.university_id:
        raise HTTPException(409, "철회된 소속이나 학교를 바꿀 수 없습니다. 새 소속을 추가해 주세요.")
    update_revision(db, row, body.revision, body.model_dump(exclude={"revision"}))
    facts_changed(db, user.id)
    return data(row)


@router.delete("/me/school-affiliations/{row_id}", status_code=204)
def remove_affiliation(row_id: str, db: DB, user: Actor, revision: int = Query(ge=1)):
    lock_user(db, user.id)
    row = owner(required(db, Affiliation, row_id), user)
    update_revision(db, row, revision, {"withdrawn": True, "is_public": False})
    facts_changed(db, user.id)


class CareerInput(Input):
    event_kind: Literal["education", "activity", "project", "internship", "employment", "transition"]
    title: str = Field(min_length=1, max_length=200)
    organization_name: str = Field(default="", max_length=200)
    started_on: date | None = None
    ended_on: date | None = None
    description: str = Field(default="", max_length=10000)
    is_public: bool = False

    @model_validator(mode="after")
    def dates(self):
        if self.started_on and self.ended_on and self.started_on > self.ended_on:
            raise ValueError("종료일은 시작일 이후여야 합니다.")
        return self


class CareerEdit(CareerInput):
    revision: int = Field(ge=1)


@router.get("/me/career-events")
def careers(db: DB, user: Actor, page: Page):
    return page.page(db, select(CareerEvent).where(CareerEvent.user_id == user.id,
                                                 CareerEvent.withdrawn.is_(False)), CareerEvent)


@router.post("/me/career-events", status_code=201)
def add_career(body: CareerInput, db: DB, user: Actor):
    lock_user(db, user.id)
    row = CareerEvent(user_id=user.id, **body.model_dump(mode="json"))
    db.add(row)
    facts_changed(db, user.id)
    db.flush()
    return data(row)


@router.patch("/me/career-events/{row_id}")
def edit_career(row_id: str, body: CareerEdit, db: DB, user: Actor):
    lock_user(db, user.id)
    row = owner(required(db, CareerEvent, row_id), user)
    if row.withdrawn:
        raise HTTPException(409, "철회한 경력입니다.")
    update_revision(db, row, body.revision, body.model_dump(mode="json", exclude={"revision"}))
    facts_changed(db, user.id)
    return data(row)


@router.delete("/me/career-events/{row_id}", status_code=204)
def remove_career(row_id: str, db: DB, user: Actor, revision: int = Query(ge=1)):
    lock_user(db, user.id)
    row = owner(required(db, CareerEvent, row_id), user)
    update_revision(db, row, revision, {"withdrawn": True, "is_public": False})
    facts_changed(db, user.id)


class PreferencePatch(Input):
    revision: int = Field(ge=1)
    coffee_chat_available: bool | None = None
    project_available: bool | None = None
    learning_stage: Literal["exploring", "starting", "learning", "building", "experienced"] | None = None
    activity_goal: str | None = Field(default=None, max_length=1000)
    hours_per_week: int | None = Field(default=None, ge=0, le=168)
    available_time_windows: list[dict] | None = Field(default=None, max_length=28)
    collaboration_mode: Literal["online", "offline", "hybrid", "flexible"] | None = None
    is_public: bool | None = None


@router.get("/me/preferences")
def preferences(db: DB, user: Actor):
    return data(required(db, Preference, user.id))


@router.patch("/me/preferences")
def edit_preferences(body: PreferencePatch, db: DB, user: Actor):
    lock_user(db, user.id)
    changes = body.model_dump(exclude_unset=True, exclude={"revision"})
    if any(value is None for key, value in changes.items() if key != "hours_per_week"):
        raise HTTPException(422, "필수 활동 조건은 null로 바꿀 수 없습니다.")
    row = update_revision(db, required(db, Preference, user.id), body.revision, changes)
    facts_changed(db, user.id)
    return data(row)


@router.get("/tags")
def tags(db: DB, page: Page, kind: Literal["skill", "role", "interest"] | None = None):
    query = select(Tag)
    if kind:
        query = query.where(Tag.kind == kind)
    return page.page(db, query, Tag)


@router.get("/me/tags")
def my_tags(db: DB, user: Actor):
    return {"items": tags_for(db, user.id), "next_cursor": None, "revision": user.facts_revision}


class TagSelection(Input):
    tag_id: str
    usage: Literal["experienced", "desired", "interested"]
    is_public: bool = False


class TagReplace(Input):
    revision: int = Field(ge=1)
    items: list[TagSelection] = Field(max_length=100)


@router.put("/me/tags")
def replace_tags(body: TagReplace, db: DB, user: Actor):
    locked = lock_user(db, user.id)
    if locked.facts_revision != body.revision:
        raise HTTPException(409, "프로필이 변경되었습니다. 태그를 다시 확인해 주세요.")
    keys = [(x.tag_id, x.usage) for x in body.items]
    if len(set(keys)) != len(keys):
        raise HTTPException(422, "같은 태그를 중복 선택할 수 없습니다.")
    for item in body.items:
        required(db, Tag, item.tag_id)
    db.execute(delete(UserTag).where(UserTag.user_id == user.id))
    db.add_all([UserTag(user_id=user.id, **x.model_dump()) for x in body.items])
    facts_changed(db, user.id)
    db.flush()
    return my_tags(db, user)


def timeline_for(db, user):
    profile = public_user(db, user)
    events = [{"id": x["id"], "kind": "education", "title": x["university_name"],
               "date": str(x["entry_year"]) if x["entry_year"] else None} for x in profile["school_affiliations"]]
    events += [{"id": x["id"], "kind": x["event_kind"], "title": x["title"], "date": x["started_on"]}
               for x in profile["career_events"]]
    events += [{"id": x["id"], "kind": "project", "title": x["project_title"], "date": x["started_on"]}
               for x in profile["project_members"]]
    return sorted(events, key=lambda x: (x["date"] is None, x["date"] or "", x["id"]))


@router.get("/users/{user_id}/timeline")
def timeline(user_id: str, db: DB, actor: Actor):
    return {"items": timeline_for(db, required(db, User, user_id)), "next_cursor": None}


@router.get("/users/{user_id}/career-path-graph")
def graph(user_id: str, db: DB, actor: Actor):
    nodes = timeline_for(db, required(db, User, user_id))
    dated = [x for x in nodes if x["date"]]
    return {"nodes": nodes, "edges": [{"source": a["id"], "target": b["id"]}
                                       for a, b in zip(dated, dated[1:])],
            "meaning": "사용자가 입력·승인하고 공개한 사건을 시간순으로 연결합니다."}
