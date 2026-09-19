"""One terminal: configured database, API, worker, isolated sites and Next.js."""
import argparse
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from sqlalchemy.engine import make_url  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.windows_job import WindowsJob  # noqa: E402 - standalone script resolves the repository first


def instance_key(ports):
    # A non-secret identifier for this workspace and exact port set. Never used
    # as authentication or permission to stop an existing process.
    dotenv = ROOT / ".env"
    modified = dotenv.stat().st_mtime_ns if dotenv.is_file() else 0
    database = make_url(get_settings().database_url).set(password=None)
    value = f"{os.path.normcase(str(ROOT))}|{','.join(map(str, ports))}|{database}|{modified}"
    return hashlib.sha256(value.encode()).hexdigest()


def frontend_environment(env):
    # Next only needs its API proxy target. Keep server credentials out of its process.
    return {key: value for key, value in env.items()
            if key == "DUDRI_SITE_ORIGIN" or
            (not key.upper().startswith(("DUDRI_", "SUPABASE_")) and key.upper() not in ("DATABASE_URL", "KOSS_AI_API_KEY"))}


def port_in_use(port):
    with socket.socket() as probe:
        probe.settimeout(1)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def read_local_json(port, path):
    # Ignore system proxy settings for loopback health checks.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(f"http://127.0.0.1:{port}{path}", timeout=2) as response:
        if response.status != 200:
            return {}
        return json.loads(response.read(4096))


def running_instance(ports, expected):
    try:
        frontend = read_local_json(ports[0], "/api/v1/dev/instance")
        backend = read_local_json(ports[1], "/api/v1/dev/instance")
        sites = read_local_json(ports[2], "/")
        if (frontend == backend and backend.get("service") == "dudri-local"
                and backend.get("instance") == expected and backend.get("supervisor")
                and sites.get("service") == "dudri-sites" and sites.get("status") == "ok"):
            return backend
    except (OSError, ValueError, AttributeError, urllib.error.URLError):
        pass
    return None


def open_browser(url):
    opened = webbrowser.open(url)
    print("[local] Browser launch requested." if opened else f"[local] Open {url} in your browser.", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--reuse-only", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--import-sqlite", action="store_true", help="Copy saved SQLite data into an empty PostgreSQL DB before starting")
    parser.add_argument("--port", type=int, default=3000)
    parser.add_argument("--api-port", type=int, default=8000)
    parser.add_argument("--site-port", type=int, default=8001)
    args = parser.parse_args()
    ports = [args.port, args.api_port, args.site_port]
    if len(set(ports)) != 3 or any(port < 1024 or port > 65535 for port in ports):
        raise SystemExit("Use three distinct ports between 1024 and 65535.")
    identity = instance_key(ports)
    occupied = [port for port in ports if port_in_use(port)]
    if occupied:
        if args.import_sqlite:
            raise SystemExit("Stop the existing app before importing SQLite data.")
        existing = running_instance(ports, identity)
        if existing:
            url = f"http://localhost:{args.port}"
            print(f"[local] ALREADY RUNNING {url} | Original supervisor {existing['supervisor']}", flush=True)
            print("[local] Reusing the existing services. Close the original server terminal to stop them.", flush=True)
            if not args.no_browser:
                open_browser(url)
            return
        raise SystemExit(f"Port(s) {', '.join(map(str, occupied))} are in use by another app, a server still starting, or an earlier DB configuration.\n"
                         "No existing process was stopped. Close its terminal, or run:\n"
                         "start-local.bat --port 3002 --api-port 8002 --site-port 8003")
    if args.reuse_only:
        raise SystemExit("[local] This workspace is already installing or running. Wait for its original terminal, or close it before starting another port set. No runtime or dependencies were changed.")
    # A repeated launch returns above without taking ownership of any processes.
    job = WindowsJob()
    assert os.name != "nt" or job.handle
    print(f"[local] SUPERVISOR {os.getpid()}", flush=True)
    node = shutil.which("node")
    if not node:
        raise SystemExit("Node.js 22 or newer is required.")
    env = dict(os.environ)
    env.update(PYTHONUNBUFFERED="1", DUDRI_ENVIRONMENT="development", DUDRI_LOCAL_DEMO_ENABLED="true",
               DUDRI_APP_ORIGIN=f"http://localhost:{args.port}", DUDRI_SITE_ORIGIN=f"http://127.0.0.1:{args.site_port}",
               API_ORIGIN=f"http://127.0.0.1:{args.api_port}")
    env.update(DUDRI_LOCAL_INSTANCE=identity, DUDRI_LOCAL_SUPERVISOR=str(os.getpid()))
    # Settings reads the root .env directly; do not shadow it with a SQLite env default.
    database_kind = "PostgreSQL" if get_settings().database_url.startswith("postgresql") else "SQLite"
    front_env = frontend_environment(env)
    print(f"[local] Preparing {database_kind} and fictional demo accounts...", flush=True)
    subprocess.run([sys.executable, "-m", "app.prepare_database", *(["--import-sqlite"] if args.import_sqlite else [])],
                   cwd=ROOT / "backend", env=env, check=True)
    next_entry = ROOT / "frontend/node_modules/next/dist/bin/next"
    lock_hash = hashlib.sha256((ROOT / "frontend/package-lock.json").read_bytes()).hexdigest()
    install_stamp = ROOT / "frontend/node_modules/.dudri-lock"
    if not next_entry.is_file() or not install_stamp.is_file() or install_stamp.read_text() != lock_hash:
        print("[local] Installing frontend packages...", flush=True)
        subprocess.run(["cmd.exe", "/d", "/c", "npm.cmd", "ci", "--include=dev", "--include=optional"] if os.name == "nt" else ["npm", "ci", "--include=dev", "--include=optional"],
                       cwd=ROOT / "frontend", env=front_env, check=True)
        install_stamp.write_text(lock_hash)
    if os.name == "nt":
        check = [node, "-e", "try { require('@next/swc-win32-x64-msvc'); } catch { process.exit(1); }"]
        if subprocess.run(check, cwd=ROOT / "frontend", env=front_env, check=False).returncode:
            powershell = str(Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe")
            subprocess.run([powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "scripts/ensure-vc-runtime.ps1")], check=True)
            if subprocess.run(check, cwd=ROOT / "frontend", env=front_env, check=False).returncode:
                raise SystemExit("[setup] Next.js native runtime could not load. Restart Windows if requested and retry.")
    subprocess.run([node, str(ROOT / "frontend/scripts/ensure-browser.mjs")], cwd=ROOT / "frontend", env=front_env, check=True)
    children = []
    try:
        for module, port in [("app.main:app", args.api_port), ("app.site_server:app", args.site_port)]:
            children.append(subprocess.Popen([sys.executable, "-m", "uvicorn", module, "--host", "127.0.0.1", "--port", str(port),
                                               "--no-access-log"], cwd=ROOT / "backend", env=env))
        children.append(subprocess.Popen([sys.executable, "-m", "app.worker"], cwd=ROOT / "backend", env=env))
        children.append(subprocess.Popen([node, str(next_entry), "dev", "--hostname", "127.0.0.1", "--port", str(args.port)],
                                         cwd=ROOT / "frontend", env=front_env))
        deadline = time.monotonic() + 180
        waiting = {f"http://127.0.0.1:{p}/" for p in ports}
        waiting.update(f"http://127.0.0.1:{p}/api/v1/health" for p in ports[:2])
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        while waiting:
            if any(p.poll() is not None for p in children):
                raise RuntimeError("A service exited before it was ready.")
            for url in list(waiting):
                try:
                    with opener.open(url, timeout=2) as response:
                        if response.status == 200 and (not url.endswith("/health") or
                                json.loads(response.read(4096)).get("database") == "ok"):
                            waiting.remove(url)
                except (OSError, ValueError, AttributeError, urllib.error.URLError):
                    pass
            if time.monotonic() > deadline:
                raise RuntimeError("Services did not become ready within 180 seconds.")
            time.sleep(0.25)
        url = f"http://localhost:{args.port}"
        print(f"[local] READY {url} | API {args.api_port} | Sites {args.site_port} | {database_kind}", flush=True)
        from app.ai import read_api_key
        print("[local] AI API key configured. Check AI connection settings in the app to verify provider access."
              if read_api_key() else "[local] AI setup needed: add DUDRI_AI_API_KEY to the root .env, or install and log in to a supported CLI on this PC.", flush=True)
        if not args.no_browser:
            open_browser(url)
        print("[local] Close this terminal or press Ctrl+C to stop all owned services.", flush=True)
        print("[local] Press C for Claude subscription login, G for isolated Gemini login.", flush=True)
        while True:
            if any(p.poll() is not None for p in children):
                raise RuntimeError("A service stopped. Stopping its companion services.")
            if os.name == "nt":
                import msvcrt
                if msvcrt.kbhit():
                    key = msvcrt.getwch().lower()
                    if key in ("c", "g"):
                        subprocess.run([sys.executable, "-m", "app.cli_login", "claude" if key == "c" else "gemini"],
                                       cwd=ROOT / "backend", env=env, check=False)
            time.sleep(0.3)
    except KeyboardInterrupt:
        print("\n[local] Stopping. Saved profiles and the database are preserved.", flush=True)
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=4)
            except subprocess.TimeoutExpired:
                child.kill()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # No configuration values or credentials are included in error output.
        print("[local] Startup failed. Check ports, installed tools, and the service messages above.", flush=True)
        raise SystemExit(1) from None
