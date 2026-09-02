import base64
import importlib.util
from pathlib import Path

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
