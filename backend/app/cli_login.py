"""Interactive login stays inside the official CLI; no session-file copying."""
import subprocess
import sys

from .ai import cli_command, cli_environment
from .config import get_settings

if __name__ == "__main__":
    family = sys.argv[1] if len(sys.argv) == 2 else ""
    if family not in ("codex", "claude", "gemini"):
        raise SystemExit("Choose codex, claude or gemini.")
    command = cli_command(family)
    if not command:
        raise SystemExit(f"Install the official {family} CLI first.")
    env = cli_environment(family)
    cwd = get_settings().project_root / ".runtime/cli-login"
    cwd.mkdir(parents=True, exist_ok=True)
    if family == "codex":
        command += ["login"]
    elif family == "claude":
        command += ["auth", "login"]
    else:
        command += ["--extensions", "none", "--allowed-mcp-server-names", "__dudri_no_servers__", "--ignore-env"]
        print("Log in with Google in Gemini CLI. Enter /quit when finished to return to Dudri.", flush=True)
    raise SystemExit(subprocess.call(command, cwd=cwd, env=env))
