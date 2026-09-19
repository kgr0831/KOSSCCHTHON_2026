"""Read official CLI status, projecting only non-secret connection metadata."""
import json
import os
import queue
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

from .ai import cli_command, cli_environment
from .config import get_settings
from .local_runtime import cli_allowed, device_id

PROVIDERS = ("codex", "claude")


def codex_config():
    values = {"approval_policy": '"never"', "web_search": '"disabled"', "project_doc_max_bytes": "0",
              "model_provider": '"openai"', "forced_login_method": '"chatgpt"',
              "history.persistence": '"none"', "analytics.enabled": "false", "mcp_servers": "{}"}
    for feature in ("shell_tool", "unified_exec", "shell_snapshot", "apps", "plugins", "hooks",
                    "multi_agent", "multi_agent_v2", "computer_use", "browser_use", "browser_use_external",
                    "code_mode", "code_mode_host", "view_image", "image_generation", "memories", "skill_search"):
        values[f"features.{feature}"] = "false"
    values["features.skip_host_skill_discovery"] = "true"
    return [argument for key, value in values.items() for argument in ("-c", f"{key}={value}")]


def start_cli(command, family, folder):
    return subprocess.Popen([sys.executable, str(Path(__file__).with_name("cli_runner.py")), *command],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            text=True, encoding="utf-8", errors="replace", cwd=folder,
                            env=cli_environment(family),
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)


def codex_status(command, folder):
    """No threads, login tokens, credential files or raw protocol logs are requested."""
    process = start_cli([*command, "app-server", "--listen", "stdio://", *codex_config()], "codex", folder)
    messages = queue.Queue(maxsize=128)
    stop = threading.Event()

    def read():
        try:
            for line in process.stdout:
                if stop.is_set():
                    break
                messages.put_nowait(json.loads(line))
        except (ValueError, OSError, queue.Full):
            pass
        finally:
            try:
                messages.put_nowait(None)
            except queue.Full:
                pass

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    deadline = time.monotonic() + 25

    def send(value):
        process.stdin.write(json.dumps(value) + "\n")
        process.stdin.flush()

    def request(identifier, method, params):
        send({"id": identifier, "method": method, "params": params})
        while True:
            message = messages.get(timeout=max(0.01, deadline - time.monotonic()))
            if message is None:
                raise ValueError("CLI disconnected")
            if message.get("id") == identifier:
                if "error" in message:
                    raise ValueError("CLI request failed")
                return message["result"]

    try:
        request(1, "initialize", {"clientInfo": {"name": "dudri_local", "version": "1.0.0"}})
        send({"method": "initialized"})
        account = request(2, "account/read", {"refreshToken": False}).get("account") or {}
        models = request(3, "model/list", {"limit": 100, "includeHidden": False}).get("data", [])
        return account, models
    finally:
        stop.set()
        process.stdin.close()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        reader.join(timeout=2)
        process.stdout.close()


def probe_cli(family):
    if family not in PROVIDERS or not cli_allowed():
        raise ValueError("CLI is available only on the local PC")
    command = cli_command(family)
    result = {"provider": family, "device_id": device_id(), "device_name": socket.gethostname()[:100],
              "executable_path": command[-1] if command else "", "account_email": "", "status": "not_installed",
              "models": [], "default_model": "", "checked_at": datetime.now(UTC).isoformat()}
    if not command:
        return result
    root = get_settings().project_root / ".runtime/cli"
    root.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix="status-", dir=root) as folder:
            if family == "codex":
                account, catalog = codex_status(command, folder)
                result["status"] = "connected" if account.get("type") == "chatgpt" else "needs_login"
                email = account.get("email")
                for row in catalog:
                    model = row.get("model")
                    if isinstance(model, str) and re.fullmatch(r"[a-zA-Z0-9._:-]{1,150}", model):
                        result["models"].append(model)
                        if row.get("isDefault"):
                            result["default_model"] = model
                if not result["default_model"] and result["models"]:
                    result["default_model"] = result["models"][0]
            else:
                process = start_cli([*command, "auth", "status", "--json"], family, folder)
                try:
                    output, _ = process.communicate(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate()
                    raise ValueError("CLI status timed out") from None
                account = json.loads(output)
                result["status"] = "connected" if account.get("loggedIn") and account.get("authMethod") == "claude.ai" else "needs_login"
                email = account.get("email")
                result["models"], result["default_model"] = ["sonnet", "opus", "haiku"], "sonnet"
            if isinstance(email, str) and len(email) <= 254 and re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
                result["account_email"] = email.lower()
            if result["status"] == "connected" and not result["account_email"]:
                result["status"] = "needs_login"
    except (OSError, ValueError, KeyError, TypeError, queue.Empty, subprocess.SubprocessError):
        result.update(status="error", account_email="", models=[], default_model="")
    return result
