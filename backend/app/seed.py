"""Idempotent, explicitly fictional local data. Never overwrite edited records."""
from datetime import timedelta
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select

from .config import get_settings
from .db import session_factory
from .models import (
    Affiliation,
    Booking,
    CareerEvent,
    CoffeeRequest,
    CoffeeSlot,
    Notification,
    Preference,
    Profile,
    Project,
    ProjectMember,
    RecruitmentPost,
    RoleOpening,
    Tag,
    University,
    UniversityDomain,
    User,
    UserTag,
    now,
)


def demo_id(name: str) -> str:
    return str(uuid5(NAMESPACE_URL, "dudri-local-demo/" + name))


PEOPLE = [
    ("김민준", "국민대학교", "소프트웨어학부", "프론트엔드", "첫 프로젝트를 완성하고 싶은 학생입니다.", "React", "starting"),
    ("김서준", "국민대학교", "소프트웨어학부", "백엔드", "백엔드 서비스 개발 경험과 배운 점을 나눕니다.", "Python", "experienced"),
    ("정유나", "국민대학교", "디자인학부", "디자인", "사용자의 이야기를 듣고 화면으로 옮기는 디자이너입니다.", "Figma", "building"),
    ("박지우", "숭실대학교", "컴퓨터학부", "프론트엔드", "접근성 좋은 웹 서비스를 함께 만들고 싶어요.", "TypeScript", "building"),
    ("이하윤", "순천향대학교", "컴퓨터소프트웨어공학과", "기획", "학생에게 유용한 서비스를 기획하고 있습니다.", "Figma", "learning"),
    ("최도윤", "국민대학교", "인공지능학부", "AI", "작은 데이터로 문제를 해결하는 실험을 좋아합니다.", "Python", "building"),
    ("한소연", "숭실대학교", "소프트웨어학부", "백엔드", "데이터와 API 설계에 관심 있는 동문입니다.", "Kotlin", "experienced"),
    ("윤수빈", "순천향대학교", "정보보호학과", "보안", "개인정보를 지키는 서비스 설계에 관심이 있어요.", "Python", "learning"),
]
DEMO_USERS = [demo_id(f"user/{i}") for i in range(len(PEOPLE))]


def seed(db):
    schools = {}
    for name, domain in [("국민대학교", "kookmin.ac.kr"), ("숭실대학교", "soongsil.ac.kr"), ("순천향대학교", "sch.ac.kr")]:
        school = db.scalar(select(University).where(University.name == name))
        if not school:
            school = University(id=demo_id(name), name=name)
            db.add(school)
            db.flush()
        schools[name] = school.id
        if not db.scalar(select(UniversityDomain).where(UniversityDomain.domain == domain)):
            db.add(UniversityDomain(id=demo_id(domain), university_id=school.id, domain=domain))
    tags = {}
    for kind, names in [("skill", ["React", "TypeScript", "Python", "Kotlin", "Figma"]), ("role", ["프론트엔드", "백엔드", "디자인", "기획", "AI", "보안"]), ("interest", ["커피챗", "게임", "교육", "캠퍼스"])]:
        for name in names:
            tag = db.scalar(select(Tag).where(Tag.kind == kind, Tag.name == name))
            if not tag:
                tag = Tag(id=demo_id(f"tag/{kind}/{name}"), kind=kind, name=name)
                db.add(tag)
                db.flush()
            tags[kind, name] = tag.id
    for i, (name, school, department, role, bio, skill, stage) in enumerate(PEOPLE):
        user_id = DEMO_USERS[i]
        if db.get(User, user_id):
            continue
        db.add(User(id=user_id, login_email=f"demo{i + 1}@dudri.example"))
        db.flush()
        db.add_all([
            Profile(user_id=user_id, display_name=name, bio=bio),
            Preference(user_id=user_id, coffee_chat_available=True, project_available=True,
                       learning_stage=stage, activity_goal="함께 프로젝트 완성하기", hours_per_week=6 + i,
                       collaboration_mode="online", is_public=True),
            Affiliation(id=demo_id(f"school/{i}"), user_id=user_id, university_id=schools[school],
                        department=department, enrollment_status="student" if i % 3 == 0 else "graduate",
                        entry_year=2022 - i, is_public=True),
            CareerEvent(id=demo_id(f"career/{i}"), user_id=user_id, event_kind="project",
                        title=f"{role} 프로젝트", organization_name="두드리 데모 스터디",
                        started_on="2026-03-01", ended_on="2026-06-30",
                        description=f"{skill}를 사용해 캠퍼스 정보를 공유하는 작은 서비스를 만들었습니다. (가상 경험)",
                        is_public=True),
            UserTag(user_id=user_id, tag_id=tags["skill", skill], usage="experienced", is_public=True),
            UserTag(user_id=user_id, tag_id=tags["role", role], usage="desired", is_public=True),
            UserTag(user_id=user_id, tag_id=tags["interest", "캠퍼스"], usage="interested", is_public=True),
        ])
    db.flush()
    for i, title in enumerate(["캠퍼스 커피챗 서비스", "함께 읽는 독서 기록", "처음 만드는 우리 학교 지도"]):
        project_id = demo_id(f"project/{i}")
        if db.get(Project, project_id):
            continue
        creator = DEMO_USERS[i + 1]
        db.add(Project(id=project_id, creator_id=creator, title=title,
                       summary="작은 아이디어를 함께 완성할 동료를 찾습니다. 로컬 데모용 가상 프로젝트입니다.",
                       goal="동료와 첫 버전 완성", visibility="public", project_status="building"))
        db.flush()
        db.add(ProjectMember(project_id=project_id, user_id=creator, role="기획", is_public=True))
        post_id = demo_id(f"post/{i}")
        db.add(RecruitmentPost(id=post_id, project_id=project_id, description="매주 한 번 진행 상황을 공유하고 작은 기능부터 함께 만듭니다.",
                              status="published", hours_per_week=5, collaboration_mode="online", duration="6주"))
        db.flush()
        db.add(RoleOpening(id=demo_id(f"opening/{i}"), post_id=post_id, role="프론트엔드", capacity=2,
                           skills=["React"], experience="처음이어도 괜찮아요"))
    for i in range(3):
        chat_id = demo_id(f"chat/{i}")
        if db.get(CoffeeRequest, chat_id):
            continue
        start = (now() + timedelta(days=i + 1)).replace(hour=10, minute=0, second=0, microsecond=0)
        db.add(CoffeeRequest(id=chat_id, requester_id=DEMO_USERS[i + 1], recipient_id=DEMO_USERS[0],
                            purpose=["첫 프로젝트 이야기", "디자인과 개발 협업", "커리어 방향 나누기"][i],
                            introduction="로컬에서 확인할 수 있는 가상 동문의 요청입니다.",
                            questions="처음 프로젝트를 시작할 때 어떤 점을 가장 고민하셨나요?",
                            status="accepted" if i == 0 else "pending"))
        db.flush()
        db.add(CoffeeSlot(id=demo_id(f"slot/{i}"), request_id=chat_id, starts_at=start, ends_at=start + timedelta(minutes=40)))
        if i == 0:
            db.add(Booking(id=demo_id("booking/0"), request_id=chat_id, starts_at=start,
                           ends_at=start + timedelta(minutes=40), meeting_mode="online", meeting_location="온라인 · 로컬 데모 약속"))
        db.add(Notification(user_id=DEMO_USERS[0], kind="coffee_request", title="동문에게 커피챗 요청이 왔어요",
                            href=f"/coffee/{chat_id}", deduplication_key=f"demo-coffee-{i}"))
    db.flush()


if __name__ == "__main__":
    if get_settings().environment == "production":
        raise SystemExit("Local demo seed is disabled in production.")
    with session_factory().begin() as db:
        seed(db)
    print("Local database ready. Fictional demo accounts: 8. Existing records preserved.")
