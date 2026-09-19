import importlib.util
from pathlib import Path


def _launcher():
    path = Path(__file__).resolve().parents[2] / "scripts" / "run_deployed.py"
    spec = importlib.util.spec_from_file_location("dudri_deployment", path)
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    return launcher


class _Process:
    def __init__(self, statuses):
        self.statuses = iter(statuses)

    def poll(self):
        return next(self.statuses)


def test_worker_exit_is_restarted_without_ending_primary_api():
    launcher = _launcher()
    # The primary process survives the worker failure for one supervisor cycle,
    # then ends normally so this focused test cannot run indefinitely.
    primary = _Process([None, None, 0])
    failed_worker = _Process([137])
    replacement = _Process([None])
    launched = []

    result = launcher.supervise_primary_services(
        [primary], failed_worker, ["worker"],
        lambda command: launched.append(command) or replacement,
        sleep=lambda _: None,
    )

    assert launched == [["worker"]]
    assert result is replacement
