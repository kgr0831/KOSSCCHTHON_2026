"""Non-secret identity for this PC checkout; never a remote execution address."""
import hashlib
import socket
from urllib.parse import urlsplit

from .config import get_settings


def cli_allowed():
    settings = get_settings()
    return settings.environment != "production" and urlsplit(settings.app_origin).hostname in ("localhost", "127.0.0.1", "::1")


def device_id():
    identity = socket.gethostname() + "\n" + str(get_settings().project_root.resolve()).casefold()
    return hashlib.sha256(identity.encode()).hexdigest()[:32]


def execution_target():
    return "pc:" + device_id() if cli_allowed() else "server"
