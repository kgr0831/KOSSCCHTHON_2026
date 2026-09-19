import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.auth import get_mailer, issue_session
from app.db import Base, get_db, make_engine
from app.main import create_app
from app.models import Preference, Profile, University, UniversityDomain, User


class CaptureMailer:
    def __init__(self):
        self.deliveries = []

    def send(self, email, purpose, token):
        self.deliveries.append((email, purpose, token))


@pytest.fixture
def world(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    app = create_app()
    mailer = CaptureMailer()

    def db_override():
        with factory() as db:
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise

    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[get_mailer] = lambda: mailer
    with factory.begin() as db:
        university = University(name="테스트 대학교")
        db.add(university)
        db.flush()
        db.add(UniversityDomain(university_id=university.id, domain="university.example"))
        users = []
        for index in range(3):
            user = User(login_email=f"person{index}@university.example")
            db.add(user)
            db.flush()
            db.add_all([Profile(user_id=user.id, display_name=f"동문 {index}"),
                        Preference(user_id=user.id, coffee_chat_available=True, project_available=True)])
            users.append(user.id)
    client = TestClient(app)

    def auth(index):
        from fastapi import Response
        with factory.begin() as db:
            body = issue_session(db, users[index], Response())
        return {"Authorization": f"Bearer {body['access_token']}"}

    yield {"client": client, "factory": factory, "users": users, "auth": auth,
           "mailer": mailer, "university": university.id}
    client.close()
    engine.dispose()
