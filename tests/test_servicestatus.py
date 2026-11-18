"""Parsing contracts for servicestatus: job discovery, error picking, transient vs actionable, persistence."""

import datetime as dt
import importlib.machinery
import importlib.util
import sys
from pathlib import Path

loader = importlib.machinery.SourceFileLoader("servicestatus", str(Path(__file__).parents[1] / "servicestatus"))
spec = importlib.util.spec_from_loader(loader.name, loader)
ss = sys.modules[loader.name] = importlib.util.module_from_spec(spec)
loader.exec_module(ss)

T0 = dt.datetime(2026, 11, 18, 1, 30, tzinfo=dt.timezone(dt.timedelta(hours=8)))


def records(*lines, result="done", exit_status=None):
    """Journal records for one invocation: process lines, then systemd's end-of-run messages."""
    out = [(T0 + dt.timedelta(seconds=i), {"MESSAGE": line}) for i, line in enumerate(lines)]
    end = T0 + dt.timedelta(seconds=len(lines))
    if result == "failed":
        out.append((end, {"MESSAGE": f"x.service: Main process exited, code=exited, status={exit_status or 1}/FAILURE",
                          "USER_INVOCATION_ID": "i", "EXIT_STATUS": str(exit_status or 1)}))
        out.append((end, {"MESSAGE": "x.service: Failed with result 'exit-code'.", "USER_INVOCATION_ID": "i"}))
    out.append((end, {"MESSAGE": "Finished x.", "USER_INVOCATION_ID": "i", "JOB_RESULT": result}))
    return out


def by_job(runs):
    return {r.job: (r.level, r.message) for r in runs}


def test_wrapper_jobs_are_discovered_without_configuration():
    runs = ss.parse_invocation("daily-activities", "daily-activities", records(
        "2026-11-18T01:30:00+08:00 daily-activities: start brand-new-job: uv run new.py",
        "progress 1/2",
        "2026-11-18T01:30:01+08:00 daily-activities: ok brand-new-job (1s)",
        "2026-11-18T01:30:01+08:00 daily-activities: start backupgoogle: uv run backupgoogle.py",
        "chat: scanning 21 recently active spaces",
        "╭──── Traceback (most recent call last) ────╮",
        "│ /home/x.py:12 in main                     │",
        "╰───────────────────────────────────────────╯",
        "JSONDecodeError: Unterminated string starting at: line 1 column 80 (char 79)",
        "2026-11-18T01:30:02+08:00 daily-activities: failed backupgoogle exit=1 (57s)",
        "2026-11-18T01:30:02+08:00 daily-activities: skip hetznerbackup: metered or unknown connection",
        "2026-11-18T01:30:03+08:00 daily-activities: completed with 1 failed job(s)",
        result="failed",
    ))
    assert by_job(runs) == {
        "brand-new-job": ("ok", ""),
        "backupgoogle": ("fail", "JSONDecodeError: Unterminated string starting at: line 1 column 80 (char 79)"
                                 " (after: chat: scanning 21 recently active spaces)"),
        "hetznerbackup": ("warn", "skipped: metered or unknown connection"),
    }


def test_network_errors_are_transient_and_name_the_cause():
    runs = ss.parse_invocation("daily-activities", "daily-activities", records(
        "2026-11-01T03:47:00+08:00 daily-activities: start backupgoogle: x",
        "error[auth]: Authentication failed: Failed to get token: Connection failure: Hyper error: client error "
        "(Connect): dns error: failed to lookup address information",
        "Traceback (most recent call last):",
        '  File "/home/x.py", line 1, in <module>',
        "subprocess.CalledProcessError: Command 'gws' returned non-zero exit status 2.",
        "2026-11-01T03:47:01+08:00 daily-activities: failed backupgoogle exit=1 (1s)",
        "2026-11-01T03:47:01+08:00 daily-activities: start summarize: x",
        "ERROR 2026-11-02 Call.md: Error code: 429 - {'error':",
        "{'message': 'You have no credits remaining.'}}",
        "2026-11-01T03:47:02+08:00 daily-activities: failed summarize exit=1 (1s)",
        result="failed",
    ))
    level, message = by_job(runs)["backupgoogle"]
    assert level == "warn" and message.startswith("dns error · error[auth]: Authentication failed")
    assert by_job(runs)["summarize"] == (
        "fail", "ERROR 2026-11-02 Call.md: Error code: 429 - {'error': {'message': 'You have no credits remaining.'}}")


def test_single_command_service_uses_end_status_and_systemd_exit():
    skipped = ss.parse_invocation("sync", "sync.sh", records(
        "🟠 2026-11-18T12:03:46+08:00 SKIP reason=metered-network (override: X=1)",
        "🟠 2026-11-18T12:03:46+08:00 END status=skipped mode=apply",
    ))
    assert by_job(skipped) == {"sync.sh": ("warn", "skipped: metered-network")}
    silent = ss.parse_invocation("sync", "sync.sh", records("🟢 2026-11-01T06:00:29+05:30 START mode=apply",
                                                            result="failed", exit_status=3))
    assert by_job(silent) == {"sync.sh": ("fail", "code=exited, status=3/FAILURE · last log: START mode=apply")}
    sigterm = ss.parse_invocation("vlc", "vlc.sh", records("Terminated", result="failed", exit_status=143))
    assert by_job(sigterm) == {"vlc.sh": ("ok", "")}


def test_unfinished_invocation_reports_only_finished_jobs():
    recs = records("2026-11-18T01:30:00+08:00 w: start a: x", "2026-11-18T01:30:01+08:00 w: ok a (1s)",
                   "2026-11-18T01:30:01+08:00 w: start b: x")[:-1]  # no systemd end message yet
    assert by_job(ss.parse_invocation("w", "w", recs)) == {"a": ("ok", "")}


def test_same_failure_on_n_days_is_persistent_and_recovery_clears_it():
    def run(day, level="fail", message="JSONDecodeError: char 79"):
        return ss.Run("daily-activities", "backupgoogle", T0 + dt.timedelta(days=day), level, message)

    since = T0 + dt.timedelta(days=4)
    (row,) = ss.summarize([run(2), run(3), run(4)], since, persist_days=3)
    assert row["persistent"] and row["level"] == "fail"
    (row,) = ss.summarize([run(3), run(4, message="JSONDecodeError: char 80")], since, persist_days=3)
    assert not row["persistent"]  # digits are normalized, so this is the same failure on 2 days
    (row,) = ss.summarize([run(1), run(2), run(3, "ok", ""), run(4)], since, persist_days=3)
    assert not row["persistent"]


def test_lines_without_unit_metadata_are_reattached_by_syslog_identifier(monkeypatch):
    """journald can drop a stream's unit fields (e.g. across suspend); `-u` then misses the error lines."""
    t = lambda s: T0 + dt.timedelta(seconds=s)  # noqa: E731
    sd = {"USER_UNIT": "sync.service", "USER_INVOCATION_ID": "i"}
    by_unit = [(t(0), {**sd, "MESSAGE": "Starting sync..."}),
               (t(9), {**sd, "MESSAGE": "sync.service: Main process exited, code=exited, status=30/n/a", "EXIT_STATUS": "30"}),
               (t(9), {**sd, "MESSAGE": "sync.service: Failed with result 'exit-code'."})]
    orphans = [(t(5), {"SYSLOG_IDENTIFIER": "sync.sh", "MESSAGE": "🔴 2026-11-16T12:20:05+08:00 DETAIL rsync error: timeout (code 30)"}),
               (t(99), {"SYSLOG_IDENTIFIER": "sync.sh", "MESSAGE": "ERROR from another run"})]
    monkeypatch.setattr(ss, "journal", lambda args: iter(orphans if any(a.startswith("-t") for a in args) else by_unit))
    (run,) = ss.journal_runs({"sync.service": ("sync.sh", "sync.sh")}, T0, T0 + dt.timedelta(days=1))
    assert (run.level, run.message) == ("warn", "DETAIL rsync error: timeout (code 30)")


def test_all_lists_every_run_in_window():
    runs = [ss.Run("s", "j", T0 + dt.timedelta(days=d), level) for d, level in [(0, "ok"), (1, "warn"), (2, "ok")]]
    assert [r["level"] for r in ss.every_run(runs, T0 + dt.timedelta(hours=1))] == ["warn", "ok"]
    (row,) = ss.summarize(runs, T0, persist_days=3)
    assert (row["level"], row["failed"], row["runs"]) == ("ok", 1, 3)  # a recovered failure is still counted
