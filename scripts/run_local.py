"""One terminal: persistent SQLite, API, worker, isolated sites and Next.js."""
import argparse
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
from app.windows_job import WindowsJob  # noqa: E402 - standalone script resolves the repository first


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--port", type=int, default=3000)
    parser.add_argument("--api-port", type=int, default=8000)
    parser.add_argument("--site-port", type=int, default=8001)
    args = parser.parse_args()
    job = WindowsJob()
    assert os.name != "nt" or job.handle
    print(f"[local] SUPERVISOR {os.getpid()}", flush=True)
    ports = [args.port, args.api_port, args.site_port]
    if len(set(ports)) != 3 or any(port < 1024 or port > 65535 for port in ports):
        raise SystemExit("Use three distinct ports between 1024 and 65535.")
    for port in ports:
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                raise SystemExit(f"Port {port} is in use. Close the earlier local terminal or choose another port.")
    node = shutil.which("node")
    if not node:
        raise SystemExit("Node.js 22 or newer is required.")
    env = dict(os.environ)
    env.update(PYTHONUNBUFFERED="1", DUDRI_ENVIRONMENT="development", DUDRI_LOCAL_DEMO_ENABLED="true",
               DUDRI_APP_ORIGIN=f"http://localhost:{args.port}", DUDRI_SITE_ORIGIN=f"http://127.0.0.1:{args.site_port}",
               API_ORIGIN=f"http://127.0.0.1:{args.api_port}")
    # Absolute SQLite URL prevents cwd changes from creating a second database.
    env.setdefault("DUDRI_DATABASE_URL", f"sqlite:///{(ROOT / 'backend/.data/dudri.db').as_posix()}")
    print("[local] Preparing persistent database and fictional demo accounts...", flush=True)
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT / "backend", env=env, check=True)
    subprocess.run([sys.executable, "-m", "app.seed"], cwd=ROOT / "backend", env=env, check=True)
    next_entry = ROOT / "frontend/node_modules/next/dist/bin/next"
    if not next_entry.is_file():
        print("[local] Installing frontend packages...", flush=True)
        subprocess.run(["cmd.exe", "/d", "/c", "npm.cmd", "ci"] if os.name == "nt" else ["npm", "ci"],
                       cwd=ROOT / "frontend", env=env, check=True)
    children = []
    try:
        for module, port in [("app.main:app", args.api_port), ("app.site_server:app", args.site_port)]:
            children.append(subprocess.Popen([sys.executable, "-m", "uvicorn", module, "--host", "127.0.0.1", "--port", str(port),
                                               "--no-access-log"], cwd=ROOT / "backend", env=env))
        children.append(subprocess.Popen([sys.executable, "-m", "app.worker"], cwd=ROOT / "backend", env=env))
        children.append(subprocess.Popen([node, str(next_entry), "dev", "--hostname", "127.0.0.1", "--port", str(args.port)],
                                         cwd=ROOT / "frontend", env=env))
        deadline = time.monotonic() + 180
        waiting = {f"http://127.0.0.1:{p}/" for p in ports}
        while waiting:
            if any(p.poll() is not None for p in children):
                raise RuntimeError("A service exited before it was ready.")
            for url in list(waiting):
                try:
                    with urllib.request.urlopen(url, timeout=1) as response:
                        if response.status == 200:
                            waiting.remove(url)
                except (OSError, urllib.error.URLError):
                    pass
            if time.monotonic() > deadline:
                raise RuntimeError("Services did not become ready within 180 seconds.")
            time.sleep(0.25)
        url = f"http://localhost:{args.port}"
        print(f"[local] READY {url} | API {args.api_port} | Sites {args.site_port} | SQLite persisted", flush=True)
        if not args.no_browser:
            opened = webbrowser.open(url)
            print("[local] Browser launch requested." if opened else f"[local] Open {url} in your browser.", flush=True)
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
