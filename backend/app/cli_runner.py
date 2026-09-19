"""Private helper: closing/killing this process also stops its CLI descendants."""
import subprocess
import sys

from windows_job import WindowsJob

if __name__ == "__main__":
    job = WindowsJob()
    # Argument vectors only. No shell, prompt interpolation, files, or logging.
    child = subprocess.Popen(sys.argv[1:], stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr)
    raise SystemExit(child.wait())
