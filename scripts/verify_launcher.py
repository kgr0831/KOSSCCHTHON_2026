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
    # Running the actual BAT twice must reopen the same stack without creating
    # another supervisor or showing its error/pause branch.
    duplicate = subprocess.run(["cmd.exe", "/d", "/c", str(root / "start-local.bat"), "--no-browser"],
                               cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15)
    assert duplicate.returncode == 0, "Repeated BAT launch failed."
    assert "[local] ALREADY RUNNING " in duplicate.stdout
    assert "[local] SUPERVISOR " not in duplicate.stdout
    assert all(listening(port) for port in ports), "Repeated launch stopped the original services."
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
    with socket.socket() as unrelated:
        unrelated.bind(("127.0.0.1", ports[0]))
        unrelated.listen()
        conflict = subprocess.run([sys.executable, str(root / "scripts/run_local.py"), "--no-browser"],
                                  cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10)
        assert conflict.returncode != 0 and "ALREADY RUNNING" not in conflict.stdout
        assert "[local] SUPERVISOR " not in conflict.stdout
        assert listening(ports[0]), "An unrelated port owner was stopped."
    print("PASS: repeated BAT reused the original stack; termination closed all services; unrelated port owner preserved.")
finally:
    if process.poll() is None:
        process.terminate()
