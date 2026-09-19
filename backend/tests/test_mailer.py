import httpx
import pytest
from fastapi import HTTPException

from app.auth import Mailer
from app.config import Settings


def test_https_verification_mail_preserves_fragment_token_and_single_recipient(monkeypatch):
    settings = Settings(_env_file=None, mail_provider="brevo", mail_api_key="fixture-mail-key",
                        smtp_sender="sender@example.invalid", app_origin="https://app.example")
    monkeypatch.setattr("app.auth.get_settings", lambda: settings)

    def send(url, **kwargs):
        assert url == "https://api.brevo.com/v3/smtp/email"
        assert kwargs["headers"] == {"api-key": "fixture-mail-key"}
        assert kwargs["follow_redirects"] is False
        body = kwargs["json"]
        assert body["to"] == [{"email": "student@university.example"}]
        assert body["sender"]["email"] == "sender@example.invalid"
        assert "https://app.example/auth/confirm#purpose=school&token=fixture-token" in body["textContent"]
        return httpx.Response(201, request=httpx.Request("POST", url), json={"messageId": "fixture"})

    monkeypatch.setattr("app.auth.httpx.post", send)
    Mailer().send("student@university.example", "school", "fixture-token")
    assert "fixture-mail-key" not in repr(settings)


@pytest.mark.parametrize("status", [401, 429, 500])
def test_https_mail_failure_does_not_expose_provider_body(monkeypatch, status):
    monkeypatch.setattr("app.auth.get_settings", lambda: Settings(_env_file=None, mail_provider="brevo",
                        mail_api_key="fixture-mail-key", smtp_sender="sender@example.invalid"))
    monkeypatch.setattr("app.auth.httpx.post", lambda url, **_: httpx.Response(status,
                        request=httpx.Request("POST", url), text="fixture-private-provider-details"))
    with pytest.raises(HTTPException) as error:
        Mailer().send("student@university.example", "school", "fixture-token")
    assert error.value.status_code == 503
    assert "fixture" not in str(error.value.detail)


def test_production_free_api_can_use_https_mail_without_smtp():
    settings = Settings(_env_file=None, environment="production", service_role="api",
                        database_url="postgresql://localhost/fixture", app_origin="https://app.example",
                        site_origin="https://sites.example", credential_encryption_key="fixture",
                        mail_provider="brevo", mail_api_key="fixture-mail-key", smtp_sender="sender@example.invalid")
    assert not settings.smtp_host
