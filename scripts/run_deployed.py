"""Container entry point for a free API/worker host or a self-hosted full app."""
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def supervise_primary_services(primary, worker, worker_command, spawn, sleep=time.sleep):
    """Keep serving requests when the best-effort background worker exits.

    The free deployment deliberately runs the API and worker in one container.
    A renderer or provider subprocess can still terminate the worker (for
    example, under a platform memory limit).  That must not turn a recoverable
    background-job failure into an API and sign-in outage.
    """
    while all(process.poll() is None for process in primary):
        if worker.poll() is not None:
            print("[deploy] Worker stopped; restarting it without interrupting the API.", flush=True)
            sleep(5)
            if all(process.poll() is None for process in primary):
                worker = spawn(worker_command)
        sleep(0.5)
    return worker


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
    primary_commands = []
    worker_command = None
    primary = []
    worker = None

    def stop(signum, frame):
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        if role == "sites":
            primary_commands = [[sys.executable, "-m", "uvicorn", "app.site_server:app", "--host", "0.0.0.0", "--port", str(port), "--no-access-log"]]
        elif role == "api":
            primary_commands = [[sys.executable, "-m", "uvicorn", "app.public_api:app", "--host", "0.0.0.0", "--port", str(port), "--no-access-log"]]
            worker_command = [sys.executable, "-m", "app.worker"]
        else:
            primary_commands = [[sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000", "--no-access-log"]]
            worker_command = [sys.executable, "-m", "app.worker"]
        primary = [subprocess.Popen(command, cwd=ROOT / "backend", env=env, start_new_session=True)
                   for command in primary_commands]
        worker = (subprocess.Popen(worker_command, cwd=ROOT / "backend", env=env, start_new_session=True)
                  if worker_command else None)
        if role == "app":
            public_env = {key: value for key, value in env.items() if not key.startswith(("DUDRI_", "SUPABASE_"))
                          and key not in ("DATABASE_URL", "KOSS_AI_API_KEY")}
            public_env["DUDRI_SITE_ORIGIN"] = settings.site_origin
            primary.append(subprocess.Popen(["node", str(ROOT / "frontend/scripts/next-server.mjs")],
                                             cwd=ROOT / "frontend", env=public_env, start_new_session=True))
        print(f"[deploy] {role} started; production authentication enabled.", flush=True)
        if worker:
            worker = supervise_primary_services(
                primary, worker, worker_command,
                lambda command: subprocess.Popen(command, cwd=ROOT / "backend", env=env, start_new_session=True),
            )
        else:
            while all(process.poll() is None for process in primary):
                time.sleep(0.5)
        raise RuntimeError("A primary service stopped")
    finally:
        # Each service owns a process group. Container termination also ends any
        # in-flight renderer; its durable job will be reclaimed after lease expiry.
        for child in [*primary, *([worker] if worker else [])]:
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        for child in [*primary, *([worker] if worker else [])]:
            try:
                child.wait(timeout=8)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("[deploy] Startup failed. Check PostgreSQL, HTTPS origins, SMTP host/sender and server secret settings. Configuration values are never printed.") from None
