import base64
import importlib.util
import datetime as dt
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

SCRIPT = Path(__file__).resolve().parents[1] / "backupgoogle.py"
spec = importlib.util.spec_from_file_location("backupgoogle", SCRIPT)
backupgoogle = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(backupgoogle)


def encoded(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def test_normalize_mail_preserves_thread_id_and_strips_quoted_reply():
    message = {
        "id": "m1",
        "threadId": "t1",
        "internalDate": "1788000000000",
        "sizeEstimate": 123,
        "snippet": "Hello",
        "payload": {
            "headers": [
                {"name": "From", "value": "Alice <alice@example.com>"},
                {"name": "To", "value": "Anand <anand@example.com>"},
                {"name": "Subject", "value": "Re: Test"},
            ],
            "mimeType": "text/plain",
            "body": {"data": encoded("Hello\n\nOn Tue, Sep 1, 2026 at 10:00 AM Anand wrote:\n> old text")},
        },
    }

    row = backupgoogle.normalize_mail(message, "anand@example.com")

    assert row["id"] == "m1"
    assert row["thread_id"] == "t1"
    assert row["body"] == "Hello"


def test_normalize_calendar_preserves_recurrence_status_and_rsvp():
    event = {
        "id": "event_20260901T100000Z",
        "recurringEventId": "event",
        "originalStartTime": {"dateTime": "2026-09-01T18:00:00+08:00"},
        "status": "confirmed",
        "summary": "Review",
        "start": {"dateTime": "2026-09-01T18:00:00+08:00"},
        "end": {"dateTime": "2026-09-01T18:30:00+08:00"},
        "attendees": [
            {"email": "anand@example.com", "responseStatus": "accepted"},
            {"email": "alice@example.com", "responseStatus": "declined"},
        ],
        "organizer": {"email": "anand@example.com"},
    }

    row = backupgoogle.normalize_calendar(event, "anand@example.com")

    assert row["recurring_event_id"] == "event"
    assert row["original_start_time"] == "2026-09-01T18:00:00+08:00"
    assert row["status"] == "confirmed"
    assert row["attendee_status"] == {
        "anand@example.com": "accepted",
        "alice@example.com": "declined",
    }


def test_normalize_chat_preserves_native_relationship_ids():
    users = {}
    message = {
        "name": "spaces/AAA/messages/BBB.BBB",
        "createTime": "2026-09-01T10:00:00Z",
        "text": "Hello",
        "sender": {"name": "users/123", "displayName": "Alice"},
        "thread": {"name": "spaces/AAA/threads/BBB"},
    }
    space = {"name": "spaces/AAA", "displayName": "Project Room"}

    row = backupgoogle.normalize_chat(message, space, users)

    assert row["sender_id"] == "users/123"
    assert row["space_id"] == "spaces/AAA"
    assert row["thread_id"] == "spaces/AAA/threads/BBB"
    assert row["sender_name"] == "Alice"


@pytest.mark.parametrize("source", ["mail", "calendar", "chat", "chat-spaces"])
def test_monthly_migration_preserves_rows_and_is_idempotent(tmp_path, source):
    key = "name" if source == "chat-spaces" else "id"
    time = "lastActiveTime" if source == "chat-spaces" else "time"
    rows = [
        {key: "one", time: "2026-09-30T23:59:59-07:00", "body": "unchanged"},
        {key: "two", time: "2026-10-01", "metadata": {"thread": "native-id"}},
    ]
    legacy = tmp_path / f"{source}.jsonl"
    backupgoogle.write_jsonl(legacy, rows)
    backupgoogle.migrate_account(tmp_path)
    assert not legacy.exists()
    assert backupgoogle.load_jsonl(tmp_path / f"{source}-2026-09.jsonl") == rows[:1]
    assert backupgoogle.load_jsonl(tmp_path / f"{source}-2026-10.jsonl") == rows[1:]
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in tmp_path.iterdir()}
    backupgoogle.migrate_account(tmp_path)
    backupgoogle.update_monthly(tmp_path, source, rows)
    assert before == {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in tmp_path.iterdir()}


@pytest.mark.parametrize("source,key,time", [("calendar", "id", "time"), ("chat-spaces", "name", "lastActiveTime")])
def test_monthly_update_moves_native_id_without_duplicates(tmp_path, source, key, time):
    old = {key: "one", time: "2026-09-30"}
    new = {key: "one", time: "2026-10-01", "title": "rescheduled"}
    backupgoogle.update_monthly(tmp_path, source, [old])
    backupgoogle.update_monthly(tmp_path, source, [new])
    assert backupgoogle.load_jsonl(tmp_path / f"{source}-2026-09.jsonl") == []
    assert backupgoogle.load_jsonl(tmp_path / f"{source}-2026-10.jsonl") == [new]


def test_migration_retries_after_write_failure(tmp_path, monkeypatch):
    rows = [{"id": "one", "time": "2026-09-01"}, {"id": "two", "time": "2026-10-01"}]
    legacy = tmp_path / "mail.jsonl"
    backupgoogle.write_jsonl(legacy, rows)
    write = backupgoogle.write_jsonl

    def interrupted(path, values):
        if path.name == "mail-2026-10.jsonl":
            raise OSError("interrupted")
        write(path, values)

    monkeypatch.setattr(backupgoogle, "write_jsonl", interrupted)
    with pytest.raises(OSError, match="interrupted"):
        backupgoogle.migrate_account(tmp_path)
    assert backupgoogle.load_jsonl(legacy) == rows
    monkeypatch.setattr(backupgoogle, "write_jsonl", write)
    backupgoogle.migrate_account(tmp_path)
    assert not legacy.exists()
    assert [row for path in sorted(tmp_path.glob("mail-*.jsonl")) for row in backupgoogle.load_jsonl(path)] == rows


def test_interrupted_month_move_retains_archived_copy(tmp_path, monkeypatch):
    old = {"id": "one", "time": "2026-09-30"}
    new = {"id": "one", "time": "2026-10-01"}
    backupgoogle.update_monthly(tmp_path, "calendar", [old])
    write = backupgoogle.write_jsonl

    def interrupted(path, values):
        if path.name == "calendar-2026-10.jsonl":
            raise OSError("interrupted")
        write(path, values)

    monkeypatch.setattr(backupgoogle, "write_jsonl", interrupted)
    with pytest.raises(OSError, match="interrupted"):
        backupgoogle.update_monthly(tmp_path, "calendar", [new])
    assert backupgoogle.load_jsonl(tmp_path / "calendar-2026-09.jsonl") == [old]
    monkeypatch.setattr(backupgoogle, "write_jsonl", write)
    backupgoogle.update_monthly(tmp_path, "calendar", [new])
    assert backupgoogle.load_jsonl(tmp_path / "calendar-2026-09.jsonl") == []
    assert backupgoogle.load_jsonl(tmp_path / "calendar-2026-10.jsonl") == [new]


def test_user_mapping_migration_and_monthly_snapshot(tmp_path):
    legacy = tmp_path / "chat-users.jsonl"
    backupgoogle.write_jsonl(legacy, [{"id": "users/1", "name": "Alice"}])
    timestamp = dt.datetime(2026, 9, 30, tzinfo=dt.UTC).timestamp()
    os.utime(legacy, (timestamp, timestamp))
    backupgoogle.migrate_account(tmp_path)
    assert (tmp_path / "chat-users-2026-09.jsonl").exists()
    assert backupgoogle.load_chat_users(tmp_path) == {"users/1": "Alice"}
    backupgoogle.write_chat_users(tmp_path, {"users/1": "Alice Updated", "users/2": "Bob"})
    assert backupgoogle.user_path(tmp_path).exists()
    assert backupgoogle.load_chat_users(tmp_path) == {"users/1": "Alice Updated", "users/2": "Bob"}


def test_space_cache_keeps_all_months_and_uses_temporary_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    account_dir = tmp_path / "archive/me@example.com"
    calls = []
    spaces = [
        {"name": "spaces/old", "lastActiveTime": "2026-09-15T00:00:00Z"},
        {"name": "spaces/new", "lastActiveTime": "2026-10-15T00:00:00Z"},
    ]

    def list_spaces(*args, **kwargs):
        calls.append(1)
        return spaces

    monkeypatch.setattr(backupgoogle, "gws_items", list_spaces)
    recent = backupgoogle.collect_spaces(account_dir, backupgoogle.parse_time("2026-10-01"), config_dir="", refresh=False)
    assert [row["name"] for row in recent] == ["spaces/new"]
    all_spaces = backupgoogle.collect_spaces(account_dir, backupgoogle.parse_time("2026-09-01"), config_dir="", refresh=False)
    assert len(all_spaces) == 2
    assert calls == [1]
    assert backupgoogle.space_path(account_dir).is_relative_to(tmp_path / "home/.cache/sanand-scripts/backupgoogle")
    assert len(list(account_dir.glob("chat-spaces-*.jsonl"))) == 2


def test_cli_uses_iitm_config_and_writes_monthly_files(tmp_path, monkeypatch):
    account = "anand@study.iitm.ac.in"
    config = str(tmp_path / "gws-iitm")

    def identity(config_dir):
        assert config_dir == config
        return account

    def collect(*args, **kwargs):
        assert kwargs["config_dir"] == config
        return [{"id": "one", "time": "2026-09-30"}, {"id": "two", "time": "2026-10-01"}]

    monkeypatch.setattr(backupgoogle, "account_email", identity)
    for source in ("mail", "calendar", "chat"):
        monkeypatch.setattr(backupgoogle, f"collect_{source}", collect)
    result = CliRunner().invoke(backupgoogle.app, ["--config-dir", config, "--out-root", str(tmp_path), "--since", "2026-09-30", "--until", "2026-10-02", "--format", "jsonl"])
    assert result.exit_code == 0, result.output
    for source in ("mail", "calendar", "chat"):
        assert (tmp_path / account / f"{source}-2026-09.jsonl").exists()
        assert (tmp_path / account / f"{source}-2026-10.jsonl").exists()
        assert not (tmp_path / account / f"{source}.jsonl").exists()
