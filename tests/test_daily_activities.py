"""Exercise scheduled local backups and failure reporting without live jobs."""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = (ROOT / "daily-activities").read_text()
FUNCTIONS = WRAPPER[WRAPPER.index("log() {") : WRAPPER.index("find_ssh_agent() {")]
BACKUPS = {
    "wabackup": "run --script /home/sanand/code/scripts/wabackup",
    "chatcli-backup": "run --script /home/sanand/code/scripts/chatcli backup",
}
BACKUP_JOBS = {
    name: next(line for line in WRAPPER.splitlines() if line.strip().startswith(f'run_job "{name}" '))
    for name in BACKUPS
}
FOOTER = WRAPPER[WRAPPER.index('if [[ "$failures" -gt 0 ]]') :]


@pytest.mark.parametrize("name", BACKUPS)
@pytest.mark.parametrize("exit_code", [0, 7])
def test_scheduled_backup_and_failure_reporting(tmp_path, name, exit_code):
    uv = tmp_path / "uv"
    uv.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$JOB_LOG"\nexit "$JOB_EXIT"\n')
    uv.chmod(0o755)
    log = tmp_path / "jobs.log"
    result = subprocess.run(
        ["bash", "-s"],
        input=FUNCTIONS + "\nfailures=0\n" + BACKUP_JOBS[name] + "\n" + FOOTER,
        env=os.environ | {"UV": str(uv), "JOB_LOG": str(log), "JOB_EXIT": str(exit_code)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert log.read_text().splitlines() == [BACKUPS[name]]
    assert result.returncode == bool(exit_code)
    assert (f"failed {name} exit=7" if exit_code else f"ok {name}") in result.stderr


@pytest.mark.parametrize("name", BACKUPS)
def test_backup_precedes_context_rebuild(name):
    assert WRAPPER.index(BACKUP_JOBS[name]) < WRAPPER.index('run_job "context-rebuild"')
