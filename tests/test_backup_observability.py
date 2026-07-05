from __future__ import annotations

import json
from pathlib import Path
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sanand_observability as obs


def test_artifact_names_are_flat_and_monthly() -> None:
    run = obs.new_run("backupwhatsapp", cache_dir=Path("/tmp/cache"), now="2026-07-03T04:05:06Z")

    assert run.events_path.name == "2026-07-runs.jsonl"
    assert run.latest_path.name == "latest.json"
    assert run.zip_path("baseline").name.startswith("2026-07-03T04-05-06Z-")
    assert run.zip_path("baseline").name.endswith("-baseline.zip")
    assert run.zip_path("anomaly").parent == Path("/tmp/cache")


def test_redaction_removes_tokens_queries_headers_and_private_text() -> None:
    redacted = obs.redact(
        {
            "url": "https://web.whatsapp.com/send?phone=123&text=secret",
            "headers": {"authorization": "Bearer abc", "cookie": "sid=123"},
            "messageText": "hello private chat",
            "contactName": "A Person",
            "postedText": 0.0,
            "safeCount": 3,
        }
    )

    assert redacted["url"] == "https://web.whatsapp.com/send"
    assert redacted["headers"] == "[redacted]"
    assert redacted["messageText"]["redacted"] is True
    assert redacted["contactName"]["redacted"] is True
    assert redacted["postedText"] == 0.0
    assert redacted["safeCount"] == 3
    assert "secret" not in json.dumps(redacted)
    assert "A Person" not in json.dumps(redacted)


def test_anomaly_classification_for_linkedin_and_whatsapp() -> None:
    linkedin = obs.classify_linkedin_anomalies(
        {
            "post_containers": 5,
            "post_rows": 0,
            "previous_selector": ".old",
            "selector_used": ".new",
            "missing_rates": {"content": 0.9},
        }
    )
    whatsapp = obs.classify_whatsapp_anomalies(
        {
            "selected_chats": 1,
            "opened_chats": 1,
            "messages_seen": 0,
            "local_rows": 20,
            "expected_conversation_id": "123@c.us",
            "opened_conversation_id": "456@c.us",
            "history_scroller_found": False,
        }
    )

    assert "linkedin_containers_without_rows" in linkedin
    assert "linkedin_selector_candidate_changed" in linkedin
    assert "whatsapp_zero_messages_with_existing_history" in whatsapp
    assert "whatsapp_opened_different_conversation" in whatsapp
    assert "whatsapp_no_history_scroller" in whatsapp


def test_linkedin_limit_suppresses_expected_sampling_anomaly() -> None:
    anomalies = obs.classify_linkedin_anomalies({"post_containers": 5, "post_rows": 1, "limit": 1})

    assert "linkedin_fewer_rows_than_containers" not in anomalies


def test_latest_json_is_atomic_summary(tmp_path: Path) -> None:
    run = obs.new_run("backuplinkedin", cache_dir=tmp_path, now="2026-07-03T04:05:06Z")

    run.finish({"status": "ok", "rows": 2})
    run.finish({"status": "failed", "rows": 0})

    latest = json.loads((tmp_path / "latest.json").read_text())
    assert latest["status"] == "failed"
    assert latest["rows"] == 0
    assert latest["run_id"] == run.run_id
    assert not list(tmp_path.glob(".latest.json.*.tmp"))


def test_zip_manifest_and_events_are_redacted(tmp_path: Path) -> None:
    run = obs.new_run("backupwhatsapp", cache_dir=tmp_path, now="2026-07-03T04:05:06Z")
    run.event("console_error", {"message": "private message body", "token": "abc"})
    archive = run.write_zip("anomaly", {"url": "https://example.com/?token=abc"}, {"outline": [{"text": "private"}]})

    with zipfile.ZipFile(archive) as handle:
        names = set(handle.namelist())
        manifest = json.loads(handle.read("manifest.json"))
        events = handle.read("events.jsonl").decode()
        dom = handle.read("dom-outline.json").decode()

    assert {"manifest.json", "events.jsonl", "dom-outline.json"} <= names
    assert manifest["kind"] == "anomaly"
    assert "abc" not in events
    assert "private" not in dom
