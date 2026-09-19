"""Idempotent service catalog. Never create user accounts or sample content."""
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select

from .db import session_factory
from .models import Tag, University, UniversityDomain


def catalog_id(name: str) -> str:
    # Retain the original namespace so existing school and tag references stay stable.
    return str(uuid5(NAMESPACE_URL, "dudri-local-demo/" + name))


def catalog(db):
    schools = {}
    for name, domain in [("국민대학교", "kookmin.ac.kr"), ("숭실대학교", "soongsil.ac.kr"), ("순천향대학교", "sch.ac.kr")]:
        school = db.scalar(select(University).where(University.name == name))
        if not school:
            school = University(id=catalog_id(name), name=name)
            db.add(school)
            db.flush()
        schools[name] = school.id
        if not db.scalar(select(UniversityDomain).where(UniversityDomain.domain == domain)):
            db.add(UniversityDomain(id=catalog_id(domain), university_id=school.id, domain=domain))
    tags = {}
    for kind, names in [("skill", ["React", "TypeScript", "Python", "Kotlin", "Figma"]), ("role", ["프론트엔드", "백엔드", "디자인", "기획", "AI", "보안"]), ("interest", ["커피챗", "게임", "교육", "캠퍼스"])]:
        for name in names:
            tag = db.scalar(select(Tag).where(Tag.kind == kind, Tag.name == name))
            if not tag:
                tag = Tag(id=catalog_id(f"tag/{kind}/{name}"), kind=kind, name=name)
                db.add(tag)
                db.flush()
            tags[kind, name] = tag.id
    return schools, tags


if __name__ == "__main__":
    with session_factory().begin() as db:
        catalog(db)
    print("Service catalog ready. No user data created.")
