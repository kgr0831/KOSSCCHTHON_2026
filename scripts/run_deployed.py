"""Container entry point for a free API/worker host or a self-hosted full app."""
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def main():
    env = dict(os.environ)
    role = env.get("DUDRI_SERVICE_ROLE", "api")
    env["DUDRI_SERVICE_ROLE"] = role
    env.update(DUDRI_ENVIRONMENT="production", API_ORIGIN="http://127.0.0.1:8000")
    public_url = env.get("RENDER_EXTERNAL_URL", "").rstrip("/")
    if public_url:
        env.setdefault("DUDRI_APP_ORIGIN" if role == "app" else "DUDRI_SITE_ORIGIN", public_url)
    os.environ.update(env)
    from app.config import get_settings
    settings = get_settings()
    port = int(env.get("PORT", "10000"))
    if not 1024 <= port <= 65535 or port == 8000:
        raise SystemExit("[deploy] PORT must be between 1024 and 65535 and different from private API port 8000.")
    if role != "sites":
        subprocess.run([sys.executable, "-m", "app.prepare_database"], cwd=ROOT / "backend", env=env, check=True)
    children = []

    def stop(signum, frame):
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        if role == "sites":
            commands = [[sys.executable, "-m", "uvicorn", "app.site_server:app", "--host", "0.0.0.0", "--port", str(port), "--no-access-log"]]
        elif role == "api":
            commands = [[sys.executable, "-m", "uvicorn", "app.public_api:app", "--host", "0.0.0.0", "--port", str(port), "--no-access-log"],
                        [sys.executable, "-m", "app.worker"]]
        else:
            commands = [[sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000", "--no-access-log"],
                        [sys.executable, "-m", "app.worker"]]
        for command in commands:
            children.append(subprocess.Popen(command, cwd=ROOT / "backend", env=env, start_new_session=True))
        if role == "app":
            public_env = {key: value for key, value in env.items() if not key.startswith(("DUDRI_", "SUPABASE_"))
                          and key not in ("DATABASE_URL", "KOSS_AI_API_KEY")}
            public_env["DUDRI_SITE_ORIGIN"] = settings.site_origin
            children.append(subprocess.Popen(["node", str(ROOT / "frontend/scripts/next-server.mjs")],
                                             cwd=ROOT / "frontend", env=public_env, start_new_session=True))
        print(f"[deploy] {role} started; production authentication enabled.", flush=True)
        while all(child.poll() is None for child in children):
            time.sleep(0.5)
        raise RuntimeError("A companion service stopped")
    finally:
        # Each service owns a process group. Container termination also ends any
        # in-flight renderer; its durable job will be reclaimed after lease expiry.
        for child in children:
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        for child in children:
            try:
                child.wait(timeout=8)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("[deploy] Startup failed. Check PostgreSQL, HTTPS origins, SMTP host/sender and server secret settings. Configuration values are never printed.") from None
