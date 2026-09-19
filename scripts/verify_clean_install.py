"""Exercise the BAT in a fresh copy with only Windows system tools on PATH."""
import ctypes
import json
import os
import queue
import shutil
import socket
import subprocess
import threading
import time
import urllib.request
import zipfile
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def main():
    if os.name != "nt":
        raise SystemExit("Windows only")
    target = ROOT / ".runtime" / ("clean-pc-" + uuid4().hex[:8])
    files = subprocess.check_output(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT).decode().split("\0")
    for name in files:
        if not name or name == ".env" or name == "token.txt" or (name.startswith(".env.") and name != ".env.example"):
            continue
        source = ROOT / name
        if source.is_file():
            destination = target / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
    ports = [3012, 8012, 8013]
    for port in ports:
        with socket.socket() as probe:
            probe.settimeout(1)
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                raise SystemExit("Test ports are occupied; no existing process was stopped.")
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith(("DUDRI_", "SUPABASE_", "UV_", "PYTHON", "NODE", "NPM_"))
           and key.upper() not in ("DATABASE_URL", "KOSS_AI_API_KEY", "PLAYWRIGHT_BROWSERS_PATH")}
    system = Path(os.environ["SystemRoot"])
    env["PATH"] = str(system / "System32") + ";" + str(system)
    # Reproduce an interrupted Node unzip: node.exe exists, npm and the completion
    # marker do not. A launcher that checks only node.exe must fail this fixture.
    node_archive = ROOT / ".runtime/tools/node-v22.23.2-win-x64.zip"
    if node_archive.is_file():
        tools = target / ".runtime/tools"
        tools.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(node_archive, tools / node_archive.name)
        with zipfile.ZipFile(node_archive) as archive:
            node_member = "node-v22.23.2-win-x64/node.exe"
            with archive.open(node_member) as source:
                executable = tools / node_member
                executable.parent.mkdir(parents=True, exist_ok=True)
                with executable.open("wb") as destination:
                    shutil.copyfileobj(source, destination)
    command = [str(system / "System32/cmd.exe"), "/d", "/c", str(target / "start-local.bat"), "--no-browser",
               "--port", str(ports[0]), "--api-port", str(ports[1]), "--site-port", str(ports[2])]
    process = subprocess.Popen(command, cwd=target, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    lines = queue.Queue()

    def read():
        for line in process.stdout:
            lines.put(line)

    threading.Thread(target=read, daemon=True).start()
    supervisor = None
    try:
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline:
            try:
                line = lines.get(timeout=1)
            except queue.Empty:
                if process.poll() is not None:
                    raise RuntimeError("Fresh install exited before readiness")
                continue
            # Fresh fixture contains no secrets. Show only our fixed progress messages.
            if line.startswith(("[setup]", "[local]", "[database]")):
                print(line.strip(), flush=True)
            if line.startswith("[local] SUPERVISOR "):
                supervisor = int(line.split()[-1])
            if "Startup stopped with error" in line:
                raise RuntimeError("Fresh install failed; BAT correctly remained open")
            if line.startswith("[local] READY "):
                break
        else:
            raise RuntimeError("Fresh install timed out")
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for port in ports[:2]:
            with opener.open(f"http://127.0.0.1:{port}/api/v1/health") as response:
                assert json.load(response)["database"] == "ok"
        with opener.open(f"http://127.0.0.1:{ports[0]}/api/v1/dev/accounts") as response:
            assert len(json.load(response)["items"]) == 8
        if node_archive.is_file():
            assert (target / ".runtime/tools/node-v22.23.2-win-x64/node_modules/npm/bin/npm-cli.js").is_file()
            assert (target / ".runtime/tools/node-v22.23.2-win-x64/.dudri-install-complete").is_file()
        manifest = target / "backend/pyproject.toml"
        original = manifest.read_bytes()
        try:
            # Any attempt to sync the live environment would now fail parsing.
            manifest.write_text("invalid fixture: must never be read during reuse\n", encoding="utf-8")
            duplicate = subprocess.run(command, cwd=target, env=env, input="\n", capture_output=True, text=True,
                                       encoding="utf-8", errors="replace", timeout=30, check=False)
            other_ports = command[:-6] + ["--port", "3013", "--api-port", "8014", "--site-port", "8015"]
            refused = subprocess.run(other_ports, cwd=target, env=env, input="\n", capture_output=True, text=True,
                                     encoding="utf-8", errors="replace", timeout=30, check=False)
            assert refused.returncode != 0 and "No runtime or dependencies were changed" in refused.stdout + refused.stderr
            assert "Preparing managed Python" not in refused.stdout
        finally:
            manifest.write_bytes(original)
        assert duplicate.returncode == 0 and "ALREADY RUNNING" in duplicate.stdout
        assert "SUPERVISOR " not in duplicate.stdout
        assert "Preparing managed Python" not in duplicate.stdout
        print("PASS: isolated startup, interrupted Node extraction recovery, API/DB health, duplicate reuse and live-environment protection.", flush=True)
    finally:
        if supervisor:
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.OpenProcess.restype = ctypes.c_void_p
            kernel.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint]
            kernel.CloseHandle.argtypes = [ctypes.c_void_p]
            handle = kernel.OpenProcess(1, False, supervisor)
            if handle:
                kernel.TerminateProcess(handle, 1)
                kernel.CloseHandle(handle)
        if process.poll() is None:
            try:
                process.communicate("\n", timeout=15)
            except subprocess.TimeoutExpired:
                process.terminate()
        print(f"[check] Isolated install retained at {target}", flush=True)


if __name__ == "__main__":
    main()
