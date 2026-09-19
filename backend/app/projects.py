from typing import Annotated, Literal

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import Field
from sqlalchemy import select, update

from .auth import Actor, Input
from .coffee import Decision
from .common import (
    DB,
    Page,
    data,
    facts_changed,
    idempotent_lookup,
    lock_user,
    notify,
    remember,
    required,
    update_revision,
)
from .models import (
    Material,
    Notification,
    Project,
    ProjectMember,
    ProjectRequest,
    ProjectSource,
    RecruitmentPost,
    RoleOpening,
    User,
)
from .rewards import consume_opportunity

router = APIRouter(prefix="/api/v1")


def get_project(db, project_id, user, manage=False):
    row = required(db, Project, project_id)
    if row.visibility == "withdrawn":
        raise HTTPException(404, "철회된 프로젝트입니다.")
    if manage and row.creator_id != user.id:
        raise HTTPException(403, "프로젝트 관리자 권한이 필요합니다.")
    if not manage and row.visibility != "public" and row.creator_id != user.id:
        member = db.scalar(select(ProjectMember).where(ProjectMember.project_id == row.id,
                                                      ProjectMember.user_id == user.id))
        if not member:
            raise HTTPException(403, "비공개 프로젝트입니다.")
    return row


def project_data(db, row, viewer=None):
    result = data(row)
    result["member_count"] = len(list(db.scalars(select(ProjectMember.id).where(ProjectMember.project_id == row.id))))
    if viewer:
        member = db.scalar(select(ProjectMember.id).where(ProjectMember.project_id == row.id,
                                                           ProjectMember.user_id == viewer.id))
        pending = db.scalar(select(ProjectRequest).where(ProjectRequest.project_id == row.id,
                                                          ProjectRequest.candidate_id == viewer.id,
                                                          ProjectRequest.status == "pending")
                            .order_by(ProjectRequest.created_at.desc()))
        latest = pending or db.scalar(select(ProjectRequest).where(ProjectRequest.project_id == row.id,
                                                                    ProjectRequest.candidate_id == viewer.id)
                                      .order_by(ProjectRequest.created_at.desc()))
        result["viewer_is_member"] = member is not None
        result["viewer_request_status"] = latest.status if latest else None
        result["viewer_request_kind"] = latest.request_kind if latest else None
    return result


def request_data(db, row):
    project = db.get(Project, row.project_id)
    return data(row) | {"project_is_active": project is not None and project.visibility != "withdrawn"}


def cancel_pending_requests(db, project_id, opening_id=None, exclude_id=None):
    query = select(ProjectRequest).where(ProjectRequest.project_id == project_id,
                                         ProjectRequest.status == "pending")
    if opening_id:
        query = query.where(ProjectRequest.opening_id == opening_id)
    if exclude_id:
        query = query.where(ProjectRequest.id != exclude_id)
    rows = list(db.scalars(query))
    for row in rows:
        update_revision(db, row, row.revision, {"status": "cancelled"})
    return rows


def notify_cancelled_requests(db, rows, actor_id, title, href="/projects/requests"):
    recipients = {row.candidate_id for row in rows}
    for user_id in sorted(recipients - {actor_id}):
        notify(db, user_id, "project_request_cancelled", title, href)


class ProjectInput(Input):
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(default="", max_length=10000)
    project_status: Literal["planning", "building", "completed", "paused"] = "planning"
    goal: str = Field(default="", max_length=1000)
    visibility: Literal["private", "public"] = "private"
    role: str = Field(min_length=1, max_length=100)
    contribution: str = Field(default="", max_length=5000)


class ProjectEdit(Input):
    revision: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(default="", max_length=10000)
    project_status: Literal["planning", "building", "completed", "paused"] = "planning"
    goal: str = Field(default="", max_length=1000)
    visibility: Literal["private", "public"] = "private"


@router.post("/projects", status_code=201)
def create_project(body: ProjectInput, db: DB, user: Actor):
    lock_user(db, user.id)
    row = Project(creator_id=user.id, **body.model_dump(exclude={"role", "contribution"}))
    db.add(row)
    db.flush()
    db.add(ProjectMember(project_id=row.id, user_id=user.id, role=body.role, contribution=body.contribution,
                         is_public=body.visibility == "public"))
    facts_changed(db, user.id)
    return project_data(db, row, user)


@router.get("/projects")
def projects(db: DB, user: Actor, page: Page, mine: bool = False, q: str = Query(default="", max_length=200)):
    member_ids = select(ProjectMember.project_id).where(ProjectMember.user_id == user.id)
    query = select(Project).where(Project.visibility != "withdrawn")
    query = query.where(Project.creator_id == user.id) if mine else query.where(
        Project.visibility == "public", ~Project.id.in_(member_ids))
    if q:
        query = query.where(Project.title.icontains(q, autoescape=True))
    return page.page(db, query, Project, lambda x: project_data(db, x, user))


@router.get("/projects/{project_id}")
def project_detail(project_id: str, db: DB, user: Actor):
    return project_data(db, get_project(db, project_id, user), user)


def invalidate_members(db, project_id):
    for user_id in sorted(db.scalars(select(ProjectMember.user_id).where(ProjectMember.project_id == project_id))):
        lock_user(db, user_id)
        facts_changed(db, user_id)


@router.patch("/projects/{project_id}")
def edit_project(project_id: str, body: ProjectEdit, db: DB, user: Actor):
    row = get_project(db, project_id, user, True)
    invalidate_members(db, project_id)
    update_revision(db, row, body.revision, body.model_dump(exclude={"revision"}))
    if row.visibility != "public":
        db.execute(update(RecruitmentPost).where(RecruitmentPost.project_id == row.id,
                   RecruitmentPost.status == "published").values(status="draft", revision=RecruitmentPost.revision + 1))
    return project_data(db, row, user)


@router.delete("/projects/{project_id}", status_code=204)
def remove_project(project_id: str, db: DB, user: Actor, revision: int = Query(ge=1)):
    row = get_project(db, project_id, user, True)
    member_ids = list(db.scalars(select(ProjectMember.user_id).where(ProjectMember.project_id == row.id)))
    invalidate_members(db, project_id)
    update_revision(db, row, revision, {"visibility": "withdrawn"})
    db.execute(update(RecruitmentPost).where(RecruitmentPost.project_id == row.id)
               .values(status="closed", revision=RecruitmentPost.revision + 1))
    cancelled = cancel_pending_requests(db, row.id)
    # Existing decision alerts must not lead to a withdrawn project. Request
    # alerts remain useful because the dashboard shows their cancellation.
    db.execute(update(Notification).where(Notification.href == f"/projects/{row.id}").values(href="/projects"))
    affected_users = set(member_ids)
    for request in cancelled:
        affected_users.update((request.candidate_id, request.initiator_id, request.recipient_id))
    for user_id in sorted(affected_users - {user.id}):
        notify(db, user_id, "project_closed", "프로젝트가 삭제되어 관련 참여 요청이 취소되었어요", "/projects")


@router.get("/projects/{project_id}/members")
def members(project_id: str, db: DB, user: Actor):
    get_project(db, project_id, user)
    result = []
    for member in db.scalars(select(ProjectMember).where(ProjectMember.project_id == project_id)):
        if member.user_id == user.id or member.is_public:
            result.append(data(member))
        else:
            result.append({"id": member.id, "is_public": False})
    return {"items": result, "next_cursor": None}


class MemberEdit(Input):
    role: str = Field(min_length=1, max_length=100)
    contribution: str = Field(default="", max_length=5000)
    started_on: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    ended_on: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    is_public: bool = False


@router.patch("/projects/{project_id}/members/me")
def edit_member(project_id: str, body: MemberEdit, db: DB, user: Actor):
    lock_user(db, user.id)
    get_project(db, project_id, user)
    member = db.scalar(select(ProjectMember).where(ProjectMember.project_id == project_id,
                                                  ProjectMember.user_id == user.id))
    if not member:
        raise HTTPException(403, "본인이 참여한 내용만 수정할 수 있습니다.")
    for key, value in body.model_dump().items():
        setattr(member, key, value)
    facts_changed(db, user.id)
    return data(member)


class SourceLink(Input):
    material_id: str


@router.post("/projects/{project_id}/sources", status_code=201)
def link_source(project_id: str, body: SourceLink, db: DB, user: Actor):
    get_project(db, project_id, user, True)
    material = required(db, Material, body.material_id)
    if material.user_id != user.id or material.access_status != "available":
        raise HTTPException(403, "직접 제공한 유효한 자료만 연결할 수 있습니다.")
    row = ProjectSource(project_id=project_id, material_id=material.id)
    db.add(row)
    db.flush()
    return data(row)


@router.delete("/projects/{project_id}/sources/{material_id}", status_code=204)
def unlink_source(project_id: str, material_id: str, db: DB, user: Actor):
    get_project(db, project_id, user, True)
    row = db.get(ProjectSource, (project_id, material_id))
    if not row:
        raise HTTPException(404, "연결된 자료가 없습니다.")
    db.delete(row)


class OpeningInput(Input):
    role: str = Field(min_length=1, max_length=100)
    capacity: int = Field(ge=1, le=100)
    skills: list[str] = Field(default_factory=list, max_length=30)
    experience: str = Field(default="", max_length=1000)


class PostInput(Input):
    description: str = Field(min_length=1, max_length=10000)
    hours_per_week: int | None = Field(default=None, ge=1, le=168)
    collaboration_mode: Literal["online", "offline", "hybrid", "flexible"] = "flexible"
    duration: str = Field(default="", max_length=200)
    role_openings: list[OpeningInput] = Field(min_length=1, max_length=20)


def post_data(db, post):
    project = required(db, Project, post.project_id)
    return data(post) | {"project_title": project.title, "creator_id": project.creator_id,
                        "role_openings": [data(x) for x in db.scalars(select(RoleOpening).where(RoleOpening.post_id == post.id))]}


@router.post("/projects/{project_id}/recruitment-posts", status_code=201)
def create_post(project_id: str, body: PostInput, db: DB, user: Actor):
    get_project(db, project_id, user, True)
    post = RecruitmentPost(project_id=project_id, **body.model_dump(exclude={"role_openings"}))
    db.add(post)
    db.flush()
    db.add_all([RoleOpening(post_id=post.id, **x.model_dump()) for x in body.role_openings])
    db.flush()
    return post_data(db, post)


@router.get("/recruitment-posts")
def posts(db: DB, user: Actor, page: Page, mine: bool = False):
    query = select(RecruitmentPost).join(Project).where(Project.visibility != "withdrawn")
    if mine:
        query = query.where(Project.creator_id == user.id)
    else:
        member_projects = select(ProjectMember.project_id).where(ProjectMember.user_id == user.id)
        has_opening = select(RoleOpening.id).where(RoleOpening.post_id == RecruitmentPost.id,
                                                   RoleOpening.filled < RoleOpening.capacity).exists()
        query = query.where(RecruitmentPost.status == "published", Project.visibility == "public",
                            ~Project.id.in_(member_projects), has_opening)
    return page.page(db, query, RecruitmentPost, lambda x: post_data(db, x))


@router.get("/recruitment-posts/{post_id}")
def post_detail(post_id: str, db: DB, user: Actor):
    post = required(db, RecruitmentPost, post_id)
    project = get_project(db, post.project_id, user)
    if post.status != "published" and project.creator_id != user.id:
        raise HTTPException(403, "게시되지 않은 공고입니다.")
    return post_data(db, post)


class PublishInput(Input):
    revision: int = Field(ge=1)


@router.post("/recruitment-posts/{post_id}/publish")
def publish_post(post_id: str, body: PublishInput, db: DB, user: Actor):
    post = required(db, RecruitmentPost, post_id)
    project = get_project(db, post.project_id, user, True)
    lock_user(db, user.id)
    db.refresh(project)
    if post.status != "draft":
        raise HTTPException(409, "Only a draft recruitment post can be published.")
    if project.visibility != "public":
        raise HTTPException(409, "프로젝트 공개 범위를 먼저 확인해 주세요.")
    if not db.scalar(select(RoleOpening.id).where(RoleOpening.post_id == post.id,
                                                   RoleOpening.filled < RoleOpening.capacity)):
        raise HTTPException(409, "모집 가능한 역할이 없습니다.")
    update_revision(db, post, body.revision, {"status": "published"})
    # If this balance check rejects, the surrounding request transaction also
    # rolls the attempted publication back.
    consume_opportunity(db, user)
    return post_data(db, post)


class PostEdit(Input):
    revision: int = Field(ge=1)
    description: str = Field(min_length=1, max_length=10000)
    hours_per_week: int | None = Field(default=None, ge=1, le=168)
    collaboration_mode: Literal["online", "offline", "hybrid", "flexible"] = "flexible"
    duration: str = Field(default="", max_length=200)
    status: Literal["draft", "closed"] = "draft"


@router.patch("/recruitment-posts/{post_id}")
def edit_post(post_id: str, body: PostEdit, db: DB, user: Actor):
    post = required(db, RecruitmentPost, post_id)
    get_project(db, post.project_id, user, True)
    update_revision(db, post, body.revision, body.model_dump(exclude={"revision"}))
    return post_data(db, post)


class Application(Input):
    opening_id: str
    message: str = Field(min_length=1, max_length=5000)


class Invitation(Application):
    candidate_id: str


def create_request(db, user, project, opening_id, candidate_id, kind, message, key):
    for user_id in sorted({project.creator_id, candidate_id}):
        lock_user(db, user_id)
    payload = {"opening_id": opening_id, "candidate_id": candidate_id, "kind": kind, "message": message}
    operation = f"project-request:{project.id}"
    existing, request_hash = idempotent_lookup(db, user.id, operation, key, payload)
    if existing:
        return existing.response_body
    opening = required(db, RoleOpening, opening_id)
    post = required(db, RecruitmentPost, opening.post_id)
    db.refresh(project)
    db.refresh(opening)
    db.refresh(post)
    if post.project_id != project.id or post.status != "published" or project.visibility != "public":
        raise HTTPException(409, "현재 모집 중인 역할이 아닙니다.")
    required(db, User, candidate_id)
    if candidate_id == project.creator_id or db.scalar(select(ProjectMember).where(
            ProjectMember.project_id == project.id, ProjectMember.user_id == candidate_id)):
        raise HTTPException(409, "이미 참여 중인 사용자입니다.")
    if opening.filled >= opening.capacity:
        raise HTTPException(409, "이 역할의 모집이 마감되었습니다.")
    if db.scalar(select(ProjectRequest).where(ProjectRequest.project_id == project.id,
            ProjectRequest.candidate_id == candidate_id, ProjectRequest.status == "pending")):
        raise HTTPException(409, "이미 응답을 기다리는 참여 요청이 있습니다.")
    if kind == "application":
        # Invitations are not a candidate-initiated participation request.
        consume_opportunity(db, user)
    recipient = project.creator_id if kind == "application" else candidate_id
    row = ProjectRequest(project_id=project.id, opening_id=opening.id, candidate_id=candidate_id,
                         initiator_id=user.id, recipient_id=recipient, request_kind=kind, message=message)
    db.add(row)
    db.flush()
    notify(db, recipient, "project_request", "프로젝트 참여 요청이 도착했어요", "/projects/requests")
    result = data(row)
    remember(db, user.id, operation, key, request_hash, result)
    return result


@router.post("/recruitment-posts/{post_id}/applications", status_code=201)
def apply(post_id: str, body: Application, db: DB, user: Actor,
          idempotency_key: Annotated[str | None, Header()] = None):
    post = required(db, RecruitmentPost, post_id)
    opening = required(db, RoleOpening, body.opening_id)
    if opening.post_id != post_id:
        raise HTTPException(422, "이 공고의 모집 역할이 아닙니다.")
    project = get_project(db, post.project_id, user)
    return create_request(db, user, project, body.opening_id, user.id, "application", body.message, idempotency_key)


@router.post("/projects/{project_id}/invitations", status_code=201)
def invite(project_id: str, body: Invitation, db: DB, user: Actor,
           idempotency_key: Annotated[str | None, Header()] = None):
    project = get_project(db, project_id, user, True)
    return create_request(db, user, project, body.opening_id, body.candidate_id, "invitation", body.message, idempotency_key)


@router.get("/me/project-requests")
def requests(db: DB, user: Actor, page: Page):
    return page.page(db, select(ProjectRequest).where((ProjectRequest.initiator_id == user.id) |
                                                     (ProjectRequest.recipient_id == user.id)), ProjectRequest,
                     lambda row: request_data(db, row))


@router.post("/project-requests/{request_id}/decision")
def decide_request(request_id: str, body: Decision, db: DB, user: Actor):
    row = required(db, ProjectRequest, request_id)
    if row.recipient_id != user.id:
        raise HTTPException(403, "요청을 받은 사람만 결정할 수 있습니다.")
    project = required(db, Project, row.project_id)
    for user_id in sorted({project.creator_id, row.candidate_id}):
        lock_user(db, user_id)
    db.refresh(row)
    if row.status != "pending":
        raise HTTPException(409, "이미 처리된 참여 요청입니다.")
    if body.decision == "accepted":
        opening = required(db, RoleOpening, row.opening_id)
        post = required(db, RecruitmentPost, opening.post_id)
        db.refresh(project)
        if post.status != "published" or project.visibility != "public":
            raise HTTPException(409, "현재 모집 중이 아닙니다.")
        if db.scalar(select(ProjectMember).where(ProjectMember.project_id == project.id,
                                                 ProjectMember.user_id == row.candidate_id)):
            raise HTTPException(409, "이미 프로젝트 팀원입니다.")
        count = db.execute(update(RoleOpening).where(RoleOpening.id == opening.id,
            RoleOpening.filled < RoleOpening.capacity).values(filled=RoleOpening.filled + 1))
        if count.rowcount != 1:
            raise HTTPException(409, "모집 인원이 모두 찼습니다.")
        db.add(ProjectMember(project_id=project.id, user_id=row.candidate_id, role=opening.role))
        facts_changed(db, row.candidate_id)
        db.refresh(opening)
        if opening.filled >= opening.capacity:
            cancelled = cancel_pending_requests(db, project.id, opening_id=opening.id, exclude_id=row.id)
            notify_cancelled_requests(db, cancelled, user.id, "모집 정원이 차서 참여 요청이 취소되었어요")
        if not db.scalar(select(RoleOpening.id).where(RoleOpening.post_id == post.id,
                                                       RoleOpening.filled < RoleOpening.capacity)):
            db.execute(update(RecruitmentPost).where(RecruitmentPost.id == post.id,
                       RecruitmentPost.status == "published").values(status="closed",
                                                                        revision=RecruitmentPost.revision + 1))
    update_revision(db, row, body.revision, {"status": body.decision})
    notify(db, row.initiator_id, "project_decision", "프로젝트 요청에 답변이 도착했어요", f"/projects/{row.project_id}")
    return data(row)
