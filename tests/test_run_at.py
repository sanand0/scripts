from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LOADER = importlib.machinery.SourceFileLoader("run_at", str(ROOT / "run-at"))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
assert SPEC and SPEC.loader
run_at = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = run_at
SPEC.loader.exec_module(run_at)


def completed(*, returncode: int = 0, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


@pytest.fixture
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    config = tmp_path / "config/systemd/user"
    state = tmp_path / "state/run-at"
    monkeypatch.setattr(run_at, "CONFIG_DIR", config)
    monkeypatch.setattr(run_at, "STATE_DIR", state)
    monkeypatch.setattr(run_at, "JOBS_DIR", state / "jobs")
    monkeypatch.setattr(run_at, "systemctl", lambda *args, **kwargs: completed())
    monkeypatch.setattr(run_at, "parse_when", lambda _: "2026-08-15 14:00:00")
    return tmp_path


def test_job_id_is_deterministic_and_command_sensitive() -> None:
    first = run_at.job_id("2026-08-15 14:00:00", ["python", "a.py"])
    assert first == run_at.job_id("2026-08-15 14:00:00", ["python", "a.py"])
    assert first != run_at.job_id("2026-08-15 14:00:00", ["python", "b.py"])
    assert first.startswith("python-")


def test_dry_run_preserves_bash_c_shell_expression(isolated: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run_at.schedule(
        "2026-08-15 14:00",
        ["bash", "-c", "echo 'hello' > /tmp/hello.txt"],
        None,
        True,
    )
    output = capsys.readouterr().out

    assert '"command": [\n    "bash",\n    "-c",' in output
    assert "OnCalendar=2026-08-15 14:00:00" in output
    assert "Persistent=true" in output
    assert "AccuracySec=1s" in output


def test_schedule_writes_units_and_runner(isolated: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(run_at, "systemctl", lambda *args, **kwargs: calls.append(args) or completed())
    monkeypatch.setenv("PATH", "/test/bin:/usr/bin")

    run_at.schedule("later", ["echo", "hello world"], "greeting", False)

    job = run_at.job_id("2026-08-15 14:00:00", ["echo", "hello world"])
    p = run_at.paths(job)
    meta = json.loads(p["meta"].read_text())
    runner = p["runner"].read_text()

    assert meta["command"] == ["echo", "hello world"]
    assert meta["name"] == "greeting"
    assert meta["cwd"] == str(Path.cwd())
    assert "echo 'hello world'" in runner
    assert "flock -n 9 || exit 0" in runner
    assert f"[[ -e {p['done']} ]] && exit 0" in runner
    assert f"ExecStart={p['runner']}" in p["service"].read_text()
    assert f"Unit=run-at-{job}.service" in p["timer"].read_text()
    assert ("daemon-reload",) in calls
    assert ("enable", "--now", f"run-at-{job}.timer") in calls


def test_runner_executes_success_only_once(isolated: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output = isolated / "payload.txt"
    monkeypatch.chdir(isolated)
    run_at.schedule("later", ["bash", "-c", f"echo ok >> {output}"], None, False)
    job = run_at.job_id("2026-08-15 14:00:00", ["bash", "-c", f"echo ok >> {output}"])
    runner = run_at.paths(job)["runner"]

    assert subprocess.run([runner], check=False).returncode == 0
    assert subprocess.run([runner], check=False).returncode == 0

    assert output.read_text() == "ok\n"
    assert run_at.paths(job)["done"].exists()


def test_runner_failure_is_not_marked_done(isolated: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(isolated)
    run_at.schedule("later", ["bash", "-c", "exit 7"], None, False)
    job = run_at.job_id("2026-08-15 14:00:00", ["bash", "-c", "exit 7"])

    result = subprocess.run([run_at.paths(job)["runner"]], check=False)

    assert result.returncode == 7
    assert not run_at.paths(job)["done"].exists()


def test_rescheduling_done_job_is_noop(isolated: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(run_at, "systemctl", lambda *args, **kwargs: calls.append(args) or completed())
    command = ["echo", "hello"]
    run_at.schedule("later", command, None, False)
    job = run_at.job_id("2026-08-15 14:00:00", command)
    run_at.paths(job)["done"].touch()
    calls.clear()

    run_at.schedule("later", command, None, False)

    assert calls == []


def test_cancel_keeps_done_but_clear_removes_it(isolated: Path) -> None:
    command = ["echo", "hello"]
    run_at.schedule("later", command, None, False)
    job = run_at.job_id("2026-08-15 14:00:00", command)
    p = run_at.paths(job)
    p["done"].touch()

    run_at.cancel(job)
    assert p["done"].exists()
    assert not p["meta"].exists()

    run_at.clear(job)
    assert not any(path.exists() for path in p.values())


def test_clear_done_removes_only_completed_jobs(isolated: Path) -> None:
    done_command = ["echo", "done"]
    pending_command = ["echo", "pending"]
    run_at.schedule("later", done_command, None, False)
    run_at.schedule("later", pending_command, None, False)
    done_job = run_at.job_id("2026-08-15 14:00:00", done_command)
    pending_job = run_at.job_id("2026-08-15 14:00:00", pending_command)
    run_at.paths(done_job)["done"].touch()

    run_at.clear_done()

    assert not any(path.exists() for path in run_at.paths(done_job).values())
    assert run_at.paths(pending_job)["meta"].exists()
