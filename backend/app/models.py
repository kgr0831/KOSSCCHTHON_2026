from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def uid() -> str:
    return str(uuid4())


def now() -> datetime:
    return datetime.now(UTC)


class Entity:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class User(Entity, Base):
    __tablename__ = "users"
    login_email: Mapped[str] = mapped_column(String(254), unique=True)
    account_status: Mapped[str] = mapped_column(default="active")
    is_admin: Mapped[bool] = mapped_column(default=False)
    # Locks all fact mutations, snapshots and publication decisions for this owner.
    facts_revision: Mapped[int] = mapped_column(default=1)


class Profile(Base):
    __tablename__ = "profiles"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    display_name: Mapped[str] = mapped_column(default="")
    bio: Mapped[str] = mapped_column(Text, default="")
    avatar_url: Mapped[str | None]
    name_is_public: Mapped[bool] = mapped_column(default=True)
    bio_is_public: Mapped[bool] = mapped_column(default=True)
    avatar_is_public: Mapped[bool] = mapped_column(default=True)
    revision: Mapped[int] = mapped_column(default=1)


class University(Entity, Base):
    __tablename__ = "universities"
    name: Mapped[str] = mapped_column(unique=True)
    is_supported: Mapped[bool] = mapped_column(default=True)


class UniversityDomain(Entity, Base):
    __tablename__ = "university_domains"
    university_id: Mapped[str] = mapped_column(ForeignKey("universities.id"))
    domain: Mapped[str] = mapped_column(unique=True)


class Affiliation(Entity, Base):
    __tablename__ = "school_affiliations"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    university_id: Mapped[str] = mapped_column(ForeignKey("universities.id"))
    department: Mapped[str] = mapped_column(default="")
    enrollment_status: Mapped[str] = mapped_column(default="student")
    entry_year: Mapped[int | None]
    graduation_year: Mapped[int | None]
    is_public: Mapped[bool] = mapped_column(default=True)
    withdrawn: Mapped[bool] = mapped_column(default=False)
    revision: Mapped[int] = mapped_column(default=1)


class Verification(Entity, Base):
    __tablename__ = "email_verifications"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    school_affiliation_id: Mapped[str | None] = mapped_column(ForeignKey("school_affiliations.id"))
    university_domain_id: Mapped[str | None] = mapped_column(ForeignKey("university_domains.id"))
    verification_kind: Mapped[str]
    verified_email: Mapped[str]
    company_name: Mapped[str | None]
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuthChallenge(Entity, Base):
    __tablename__ = "auth_challenges"
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    purpose: Mapped[str]
    email: Mapped[str]
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuthSession(Entity, Base):
    __tablename__ = "auth_sessions"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    family_id: Mapped[str] = mapped_column(index=True)
    refresh_hash: Mapped[str] = mapped_column(String(64), unique=True)
    access_hash: Mapped[str] = mapped_column(String(64), unique=True)
    access_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(default=False)
    rotated: Mapped[bool] = mapped_column(default=False)


class Preference(Base):
    __tablename__ = "user_preferences"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    coffee_chat_available: Mapped[bool] = mapped_column(default=False)
    project_available: Mapped[bool] = mapped_column(default=False)
    learning_stage: Mapped[str] = mapped_column(default="exploring")
    activity_goal: Mapped[str] = mapped_column(default="")
    hours_per_week: Mapped[int | None]
    available_time_windows: Mapped[list] = mapped_column(JSON, default=list)
    collaboration_mode: Mapped[str] = mapped_column(default="flexible")
    is_public: Mapped[bool] = mapped_column(default=True)
    revision: Mapped[int] = mapped_column(default=1)


class CareerEvent(Entity, Base):
    __tablename__ = "career_events"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    event_kind: Mapped[str]
    title: Mapped[str]
    organization_name: Mapped[str] = mapped_column(default="")
    started_on: Mapped[str | None]
    ended_on: Mapped[str | None]
    description: Mapped[str] = mapped_column(Text, default="")
    is_public: Mapped[bool] = mapped_column(default=False)
    withdrawn: Mapped[bool] = mapped_column(default=False)
    revision: Mapped[int] = mapped_column(default=1)


class Tag(Entity, Base):
    __tablename__ = "tags"
    __table_args__ = (UniqueConstraint("kind", "name"),)
    kind: Mapped[str]
    name: Mapped[str]


class UserTag(Entity, Base):
    __tablename__ = "user_tags"
    __table_args__ = (UniqueConstraint("user_id", "tag_id", "usage"),)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    tag_id: Mapped[str] = mapped_column(ForeignKey("tags.id"))
    usage: Mapped[str]
    is_public: Mapped[bool] = mapped_column(default=False)


class ExternalAccount(Entity, Base):
    __tablename__ = "external_accounts"
    __table_args__ = (UniqueConstraint("user_id", "provider"),)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    provider: Mapped[str]
    provider_user_id: Mapped[str]
    login: Mapped[str]
    encrypted_credential: Mapped[str] = mapped_column(Text)
    revoked: Mapped[bool] = mapped_column(default=False)


class Material(Entity, Base):
    __tablename__ = "source_materials"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    external_account_id: Mapped[str | None] = mapped_column(ForeignKey("external_accounts.id"))
    material_kind: Mapped[str]
    display_name: Mapped[str]
    canonical_url: Mapped[str | None]
    is_private: Mapped[bool] = mapped_column(default=True)
    access_status: Mapped[str] = mapped_column(default="available")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    text_content: Mapped[str | None] = mapped_column(Text)
    object_key: Mapped[str | None]
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revision: Mapped[int] = mapped_column(default=1)


class AnalysisRun(Entity, Base):
    __tablename__ = "analysis_runs"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    purpose: Mapped[str]
    status: Mapped[str] = mapped_column(default="queued")
    consented_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    error: Mapped[str | None]


class AnalysisInput(Base):
    __tablename__ = "analysis_inputs"
    run_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.id"), primary_key=True)
    material_id: Mapped[str] = mapped_column(ForeignKey("source_materials.id"), primary_key=True)
    material_revision: Mapped[int]


class Suggestion(Entity, Base):
    __tablename__ = "ai_suggestions"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.id"), index=True)
    target_kind: Mapped[str]
    target_id: Mapped[str | None]
    target_revision: Mapped[int | None]
    field_key: Mapped[str]
    proposed_value: Mapped[dict] = mapped_column(JSON)
    accepted_value: Mapped[dict | None] = mapped_column(JSON)
    evidence: Mapped[list] = mapped_column(JSON)
    decision: Mapped[str] = mapped_column(default="pending")
    revision: Mapped[int] = mapped_column(default=1)


class Project(Entity, Base):
    __tablename__ = "projects"
    creator_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str]
    summary: Mapped[str] = mapped_column(Text, default="")
    project_status: Mapped[str] = mapped_column(default="planning")
    goal: Mapped[str] = mapped_column(default="")
    visibility: Mapped[str] = mapped_column(default="private")
    revision: Mapped[int] = mapped_column(default=1)


class ProjectSource(Base):
    __tablename__ = "project_sources"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    material_id: Mapped[str] = mapped_column(ForeignKey("source_materials.id"), primary_key=True)


class ProjectMember(Entity, Base):
    __tablename__ = "project_members"
    __table_args__ = (UniqueConstraint("project_id", "user_id"),)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str]
    contribution: Mapped[str] = mapped_column(Text, default="")
    started_on: Mapped[str | None]
    ended_on: Mapped[str | None]
    is_public: Mapped[bool] = mapped_column(default=False)


class RecruitmentPost(Entity, Base):
    __tablename__ = "recruitment_posts"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    status: Mapped[str] = mapped_column(default="draft")
    description: Mapped[str] = mapped_column(Text)
    hours_per_week: Mapped[int | None]
    collaboration_mode: Mapped[str] = mapped_column(default="flexible")
    duration: Mapped[str] = mapped_column(default="")
    revision: Mapped[int] = mapped_column(default=1)


class RoleOpening(Entity, Base):
    __tablename__ = "role_openings"
    post_id: Mapped[str] = mapped_column(ForeignKey("recruitment_posts.id"), index=True)
    role: Mapped[str]
    capacity: Mapped[int] = mapped_column(Integer)
    filled: Mapped[int] = mapped_column(default=0)
    skills: Mapped[list] = mapped_column(JSON, default=list)
    experience: Mapped[str] = mapped_column(default="")


class ProjectRequest(Entity, Base):
    __tablename__ = "project_requests"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    opening_id: Mapped[str] = mapped_column(ForeignKey("role_openings.id"))
    candidate_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    initiator_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    recipient_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    request_kind: Mapped[str]
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(default="pending")
    revision: Mapped[int] = mapped_column(default=1)


class CoffeeRequest(Entity, Base):
    __tablename__ = "coffee_requests"
    requester_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    recipient_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    purpose: Mapped[str]
    introduction: Mapped[str] = mapped_column(Text, default="")
    questions: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(default="pending")
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revision: Mapped[int] = mapped_column(default=1)


class CoffeeSlot(Entity, Base):
    __tablename__ = "coffee_proposed_slots"
    request_id: Mapped[str] = mapped_column(ForeignKey("coffee_requests.id"), index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Booking(Entity, Base):
    __tablename__ = "coffee_bookings"
    request_id: Mapped[str] = mapped_column(ForeignKey("coffee_requests.id"), unique=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    meeting_mode: Mapped[str]
    meeting_location: Mapped[str]
    status: Mapped[str] = mapped_column(default="confirmed")
    revision: Mapped[int] = mapped_column(default=1)


class BookingChange(Entity, Base):
    __tablename__ = "booking_changes"
    booking_id: Mapped[str] = mapped_column(ForeignKey("coffee_bookings.id"), index=True)
    proposer_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    change_kind: Mapped[str]
    proposed_value: Mapped[dict] = mapped_column(JSON)
    base_revision: Mapped[int]
    status: Mapped[str] = mapped_column(default="pending")
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Attendance(Entity, Base):
    __tablename__ = "attendance_records"
    __table_args__ = (UniqueConstraint("booking_id", "user_id"),)
    booking_id: Mapped[str] = mapped_column(ForeignKey("coffee_bookings.id"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    checkin_method: Mapped[str | None]
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attendance_claim: Mapped[str | None]
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Dispute(Entity, Base):
    __tablename__ = "disputes"
    booking_id: Mapped[str] = mapped_column(ForeignKey("coffee_bookings.id"), index=True)
    reporter_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(default="open")
    resolution: Mapped[str | None] = mapped_column(Text)


class TrustEvent(Entity, Base):
    __tablename__ = "trust_events"
    __table_args__ = (UniqueConstraint("booking_id", "user_id", "event_kind"),)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    booking_id: Mapped[str] = mapped_column(ForeignKey("coffee_bookings.id"))
    event_kind: Mapped[str]
    evidence: Mapped[dict] = mapped_column(JSON)


class Notification(Entity, Base):
    __tablename__ = "notifications"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str]
    title: Mapped[str]
    href: Mapped[str]
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deduplication_key: Mapped[str | None] = mapped_column(unique=True)


class PersonalSite(Entity, Base):
    __tablename__ = "personal_sites"
    __table_args__ = (UniqueConstraint("user_id", "site_kind"),)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    site_kind: Mapped[str]
    slug: Mapped[str] = mapped_column(unique=True)
    revision: Mapped[int] = mapped_column(default=1)
    published_version_id: Mapped[str | None] = mapped_column(ForeignKey("site_versions.id", use_alter=True, name="fk_personal_sites_published_version"))


class SiteVersion(Entity, Base):
    __tablename__ = "site_versions"
    __table_args__ = (UniqueConstraint("site_id", "version_number"),)
    site_id: Mapped[str] = mapped_column(ForeignKey("personal_sites.id"), index=True)
    version_number: Mapped[int]
    base_version_id: Mapped[str | None] = mapped_column(ForeignKey("site_versions.id"))
    edit_mode: Mapped[str]
    status: Mapped[str] = mapped_column(default="queued")
    style_id: Mapped[str]
    instruction: Mapped[str] = mapped_column(Text, default="")
    public_input_snapshot: Mapped[dict] = mapped_column(JSON)
    facts_revision: Mapped[int]
    code: Mapped[dict] = mapped_column(JSON, default=dict)
    gui: Mapped[dict] = mapped_column(JSON, default=dict)
    validation: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None]


class Publication(Entity, Base):
    __tablename__ = "site_publications"
    site_id: Mapped[str] = mapped_column(ForeignKey("personal_sites.id"), index=True)
    version_id: Mapped[str] = mapped_column(ForeignKey("site_versions.id"))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Job(Entity, Base):
    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("kind", "target_id"),)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str]
    target_id: Mapped[str]
    status: Mapped[str] = mapped_column(default="queued", index=True)
    attempts: Mapped[int] = mapped_column(default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_token: Mapped[str | None]
    error: Mapped[str | None]


class IdempotencyRecord(Entity, Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (UniqueConstraint("user_id", "operation", "key"),)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    operation: Mapped[str]
    key: Mapped[str]
    request_hash: Mapped[str]
    response_body: Mapped[dict] = mapped_column(JSON)
    response_status: Mapped[int]


class AISettings(Base):
    __tablename__ = "user_ai_settings"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    transport: Mapped[str] = mapped_column(default="api")
    easy_model: Mapped[str] = mapped_column(default="")
    hard_model: Mapped[str] = mapped_column(default="")
    revision: Mapped[int] = mapped_column(default=1)


class CareerPlan(Entity, Base):
    __tablename__ = "career_plans"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    goal: Mapped[str]
    content: Mapped[dict] = mapped_column(JSON)
    facts_revision: Mapped[int]
    revision: Mapped[int] = mapped_column(default=1)
