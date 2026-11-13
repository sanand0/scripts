"""Exercise the scheduled WhatsApp command and failure reporting without live jobs."""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = (ROOT / "daily-activities").read_text()
FUNCTIONS = WRAPPER[WRAPPER.index("log() {") : WRAPPER.index("find_ssh_agent() {")]
WHATSAPP_JOB = next(line for line in WRAPPER.splitlines() if line.strip().startswith('run_job "wabackup" '))
FOOTER = WRAPPER[WRAPPER.index('if [[ "$failures" -gt 0 ]]') :]


@pytest.mark.parametrize("exit_code", [0, 7])
def test_scheduled_backup_and_failure_reporting(tmp_path, exit_code):
    uv = tmp_path / "uv"
    uv.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$JOB_LOG"\nexit "$JOB_EXIT"\n')
    uv.chmod(0o755)
    log = tmp_path / "jobs.log"
    result = subprocess.run(
        ["bash", "-s"],
        input=FUNCTIONS + "\nfailures=0\n" + WHATSAPP_JOB + "\n" + FOOTER,
        env=os.environ | {"UV": str(uv), "JOB_LOG": str(log), "JOB_EXIT": str(exit_code)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert log.read_text().splitlines() == ["run --script /home/sanand/code/scripts/wabackup"]
    assert result.returncode == bool(exit_code)
    assert ("failed wabackup exit=7" if exit_code else "ok wabackup") in result.stderr


def test_whatsapp_precedes_context_rebuild():
    assert WRAPPER.index(WHATSAPP_JOB) < WRAPPER.index('run_job "context-rebuild"')
