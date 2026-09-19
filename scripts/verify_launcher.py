"""Windows integration check: kill only our reported supervisor, check all ports."""
import ctypes
import os
import queue
import socket
import subprocess
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path

root = Path(__file__).resolve().parents[1]
if os.name != "nt":
    raise SystemExit("This check targets the Windows BAT lifecycle.")


def listening(port):
    with socket.socket() as probe:
        return probe.connect_ex(("127.0.0.1", port)) == 0


ports = [3000, 8000, 8001]
if any(listening(port) for port in ports):
    raise SystemExit("Close the running local terminal before this lifecycle check.")
process = subprocess.Popen([sys.executable, str(root / "scripts/run_local.py"), "--no-browser"],
                           cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           text=True, encoding="utf-8", errors="replace")
lines = queue.Queue()


def read_lines():
    for line in process.stdout:
        lines.put(line)


threading.Thread(target=read_lines, daemon=True).start()
supervisor = None
ready = False
try:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            line = lines.get(timeout=0.5)
        except queue.Empty:
            continue
        if line.startswith("[local] SUPERVISOR "):
            supervisor = int(line.split()[-1])
        if line.startswith("[local] READY "):
            ready = True
            break
    if not ready or not supervisor or not all(listening(port) for port in ports):
        raise RuntimeError("Launcher readiness check failed.")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes, kernel.OpenProcess.restype = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE
    kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    # PID originates from the supervisor spawned immediately above, never from
    # a process-name search or an arbitrary existing port owner.
    handle = kernel.OpenProcess(0x0001, False, supervisor)
    if not handle:
        raise RuntimeError("Could not open our supervisor.")
    try:
        if not kernel.TerminateProcess(handle, 0):
            raise RuntimeError("Could not terminate our supervisor.")
    finally:
        kernel.CloseHandle(handle)
    deadline = time.monotonic() + 10
    while any(listening(port) for port in ports) and time.monotonic() < deadline:
        time.sleep(0.2)
    assert not any(listening(port) for port in ports), "An owned server survived supervisor termination."
    process.wait(timeout=5)
    print("PASS: API + frontend + site server ready; forced supervisor termination closed all three ports.")
finally:
    if process.poll() is None:
        process.terminate()
