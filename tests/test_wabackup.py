"""Archive safety and change-journal contracts for the extensionless CLI."""

import importlib.machinery
import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

loader = importlib.machinery.SourceFileLoader("wabackup", str(Path(__file__).parents[1] / "wabackup"))
spec = importlib.util.spec_from_loader(loader.name, loader)
wa = importlib.util.module_from_spec(spec)
loader.exec_module(wa)


def msg(mid="M1", **extra):
    return {
        "ChatJID": "123@g.us",
        "ChatName": "Family",
        "MsgID": mid,
        "Timestamp": "2026-01-02T10:00:00Z",
        "Text": "hello",
        **extra,
    }


class Client:
    def __init__(self, tmp_path):
        self.store = tmp_path / "store"
        self.store.mkdir()
        with sqlite3.connect(self.store / "wacli.db") as c:
            c.execute(
                "create table messages(chat_jid,msg_id,deleted_at,revoked,deleted_for_me,media_type,direct_path TEXT DEFAULT 'defaultpath',local_path,media_unavailable_at,media_key BLOB DEFAULT X'01')"
            )
        self.messages = [msg()]
        self.events = []
        self.exports = []
        self.calls = []
        self.download_error = False
        self.downloads = []

    def call(self, *args, **kwargs):
        self.calls.append(args)
        if args == ("doctor",):
            return {"store_dir": str(self.store), "linked_jid": "self@s.whatsapp.net"}
        if args[:2] == ("messages", "changes"):
            return {"next_checkpoint": "checkpoint"}
        if args[:2] == ("media", "download"):
            self.downloads.append((args, kwargs))
            if self.download_error:
                raise RuntimeError(self.download_error if isinstance(self.download_error, str) else "expired media")
            Path(args[args.index("--output") + 1]).write_bytes(b"\xff\xd8\xffimage")
            return {}
        if args[:2] == ("messages", "show"):
            return msg("DELETED", Revoked=True, Text="original")
        raise AssertionError(args)

    def export(self, *filters):
        self.exports.append(filters)
        if "--chat" in filters:
            selector = filters[filters.index("--chat") + 1]
            return [m for m in self.messages if selector in (m["ChatJID"], m.get("ChatName"))]
        return self.messages

    def changes(self, checkpoint):
        return self.events, "next"


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("WABACKUP_CACHE_DIR", str(tmp_path / "cache"))
    return Client(tmp_path), tmp_path / "output"


def run(client, output, **options):
    defaults = {
        "conversations": [],
        "name": "",
        "since": "",
        "until": "",
        "limit": 0,
        "images": True,
        "full": False,
        "dry_run": False,
        "format": "jsonl",
    }
    wa.backup(client, output, **(defaults | options))


def rows(output):
    return wa.load(next(output.glob("*.jsonl")))


def test_legacy_fields_image_and_unknown_keys_survive(setup):
    client, output = setup
    output.mkdir()
    old = {
        "messageId": "M1",
        "conversationId": "123@g.us",
        "time": "2026-01-02T10:00:00Z",
        "text": "rich old text",
        "quoteText": "quote",
        "custom": [1],
        "mediaPath": "media/old.jpg",
    }
    (output / "old [123@g.us].jsonl").write_text(wa.packed(old) + "\n")
    (output / "media").mkdir()
    (output / "media/old.jpg").write_bytes(b"old bytes")
    client.messages = [msg(MediaType="image", MimeType="image/jpeg")]
    run(client, output)
    row = rows(output)["M1"]
    assert all(row[k] == v for k, v in old.items())
    assert (output / row["mediaPath"]).read_bytes() == b"old bytes"
    assert row["wacli"] == client.messages[0]
    assert json.loads(next((output / ".history").glob("*.jsonl")).read_text()) == old
    assert not any(c[:2] == ("media", "download") for c in client.calls)


def test_incremental_noop_does_not_rewrite_or_export(setup):
    client, output = setup
    run(client, output)
    path = next(output.glob("*.jsonl"))
    before = (path.read_bytes(), path.stat().st_mtime_ns)
    client.exports.clear()
    run(client, output)
    assert not client.exports
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


def test_old_backfill_and_edit_follow_sequence_not_time(setup):
    client, output = setup
    run(client, output)
    client.events = [{"chat_jid": "123@g.us", "operation": "upsert"}]
    client.messages = [
        msg(Text="edited", Edited=True),
        msg("OLD", Timestamp="2020-01-01T00:00:00Z"),
    ]
    run(client, output)
    result = rows(output)
    assert set(result) == {"M1", "OLD"}
    assert result["M1"]["wacli"]["Text"] == "edited"
    assert (output / ".history").is_dir()


def test_deleted_payload_retained(setup):
    client, output = setup
    with sqlite3.connect(client.store / "wacli.db") as c:
        c.execute(
            "insert into messages(chat_jid,msg_id,deleted_at,revoked,deleted_for_me) values('123@g.us','DELETED',1,1,0)"
        )
    run(client, output)
    assert rows(output)["DELETED"]["wacli"]["Revoked"] is True
    assert rows(output)["DELETED"]["text"] == "original"


def test_image_failure_saves_text_queues_retry_then_recovers(setup, capsys):
    client, output = setup
    client.messages = [msg(MediaType="image", MimeType="image/jpeg")]
    client.download_error = True
    run(client, output)
    assert rows(output)["M1"]["text"] == "hello"
    media = json.loads((wa.cache_dir(output) / "media.json").read_text())
    assert media["items"]["123@g.us/M1"]["attempts"] == 1
    assert "waiting" in capsys.readouterr().err
    client.download_error = False
    # Unknown transient failures respect backoff until a cache/reference changes.
    item = media["items"]["123@g.us/M1"]
    item["next"] = 0
    (wa.cache_dir(output) / "media.json").write_text(wa.packed(media))
    run(client, output)
    assert (output / rows(output)["M1"]["mediaPath"]).read_bytes().startswith(b"\xff\xd8\xff")
    assert json.loads((wa.cache_dir(output) / "media.json").read_text())["items"] == {}


def test_filtered_run_cannot_advance_global_checkpoint(setup):
    client, output = setup
    run(client, output, conversations=["Family"])
    assert not wa.state_file(output).exists()


def test_dry_run_writes_nothing(setup):
    client, output = setup
    run(client, output, dry_run=True)
    assert not output.exists()


def test_corruption_fails_before_source_read_or_write(setup):
    client, output = setup
    output.mkdir()
    path = output / "bad.jsonl"
    path.write_text("not json\n")
    with pytest.raises(ValueError):
        run(client, output)
    assert not client.calls
    assert path.read_text() == "not json\n"


def test_cross_chat_filename_rejected(setup):
    client, output = setup
    output.mkdir()
    (output / "wrong [456@g.us].jsonl").write_text(wa.packed({"messageId": "M", "conversationId": "123@g.us"}))
    with pytest.raises(ValueError, match="Mixed chat"):
        run(client, output)
    assert not client.calls


def test_source_account_change_rejected(setup):
    client, output = setup
    run(client, output)
    state = json.loads(wa.state_file(output).read_text())
    state["source"]["linked_jid"] = "other"
    wa.state_file(output).write_text(wa.packed(state))
    with pytest.raises(ValueError, match="another"):
        run(client, output)


def test_legacy_duplicate_chat_files_preserved(setup):
    client, output = setup
    output.mkdir()
    for name, mid in [("A", "A"), ("B", "B")]:
        (output / f"{name} [123@g.us].jsonl").write_text(
            wa.packed(
                {
                    "messageId": mid,
                    "conversationId": "123@g.us",
                    "time": "2026-01-01T00:00:00Z",
                }
            )
        )
    before = (output / "B [123@g.us].jsonl").read_bytes()
    run(client, output)
    assert set(wa.load(output / "A [123@g.us].jsonl")) == {"A", "B", "M1"}
    assert (output / "B [123@g.us].jsonl").read_bytes() == before


def test_image_path_escape_rejected(setup):
    client, output = setup
    with pytest.raises(ValueError, match="escapes"):
        wa.image(client, output, {"mediaPath": "../outside.jpg", "wacli": msg()})


def test_pages_all_read_and_repeated_cursor_fails(monkeypatch):
    client = wa.Wacli("", None)
    pages = iter(
        [
            {"messages": [msg()], "page": {"has_more": True, "next_cursor": "C"}},
            {"messages": [msg("M2")], "page": {"has_more": False}},
        ]
    )
    monkeypatch.setattr(client, "call", lambda *a: next(pages))
    assert len(client.export()) == 2
    monkeypatch.setattr(
        client,
        "call",
        lambda *a: {"messages": [], "page": {"has_more": True, "next_cursor": "C"}},
    )
    with pytest.raises(ValueError, match="repeated"):
        client.export()


def test_partial_export_failure_leaves_archive_and_checkpoint(setup):
    client, output = setup
    run(client, output)
    before = {p: p.read_bytes() for p in output.rglob("*") if p.is_file()}

    before[wa.state_file(output)] = wa.state_file(output).read_bytes()

    def fail(*args):
        raise RuntimeError("cursor invalidated")

    client.export = fail
    with pytest.raises(RuntimeError, match="invalidated"):
        run(client, output, full=True)
    assert all(p.read_bytes() == b for p, b in before.items())


def test_no_images_is_incremental_and_enabling_images_uses_archived_queue(setup):
    client, output = setup
    run(client, output, images=False)
    client.exports.clear()
    run(client, output, images=False)
    assert not client.exports
    run(client, output, images=True)
    assert not client.exports


def test_help_and_describe():
    runner = CliRunner()
    assert runner.invoke(wa.app, ["--help"]).exit_code == 0
    result = runner.invoke(wa.app, ["--describe"])
    assert result.exit_code == 0
    assert json.loads(result.output)["primary_key"] == ["conversationId", "messageId"]


def test_unicode_line_separators_roundtrip(setup):
    client, output = setup
    client.messages = [msg(Text="a\u2028b\u2029c\u0085d")]
    run(client, output)
    run(client, output)
    assert rows(output)["M1"]["text"] == "a\u2028b\u2029c\u0085d"


def test_reply_and_forwarding_fields_from_real_cli_keys():
    row = wa.merge({}, msg(quoted_msg_id="PARENT", quoted_sender_jid="sender@lid", IsForwarded=True))
    assert row["quoteMessageId"] == "PARENT"
    assert row["isForwarded"] is True
    assert row["wacli"]["quoted_sender_jid"] == "sender@lid"


def test_expired_checkpoint_preserves_archive_and_full_recovers(setup):
    client, output = setup
    run(client, output)
    before = {p: p.read_bytes() for p in output.rglob("*") if p.is_file()}

    before[wa.state_file(output)] = wa.state_file(output).read_bytes()

    def expired(token):
        raise RuntimeError("checkpoint expired")

    client.changes = expired
    with pytest.raises(RuntimeError, match="--full"):
        run(client, output)
    assert all(p.read_bytes() == b for p, b in before.items())
    # A chat-specific export neither consumes nor advances the expired global checkpoint.
    run(client, output, conversations=["Family"])
    assert wa.state_file(output).read_bytes() == before[wa.state_file(output)]
    run(client, output, full=True)


def media_state(output):
    return json.loads((wa.cache_dir(output) / "media.json").read_text())


def test_expired_cdn_focus_retries_immediately_on_phone_without_flags(setup, capsys):
    client, output = setup
    client.messages = [msg(MediaType="image", MimeType="image/jpeg")]
    client.download_error = "download failed with status code 410"
    run(client, output)
    first = media_state(output)
    assert first["focus"] == ["123@g.us/M1"]
    instructions = capsys.readouterr().err
    assert "Open WhatsApp on your phone" in instructions
    assert "Family" in instructions and "2026-01-02" in instructions
    assert "No extra flags" in instructions
    assert first["items"]["123@g.us/M1"]["next"] > wa.time.time()
    client.download_error = False
    client.exports.clear()
    run(client, output)
    assert not client.exports
    args, kwargs = client.downloads[-1]
    assert "--retry-on-phone" in args and kwargs["readonly"] is False
    assert media_state(output)["items"] == {}
    assert rows(output)["M1"]["mediaPath"]


def test_transient_retry_delays_double_and_no_phone_request(setup, monkeypatch):
    client, output = setup
    clock = [1_800_000_000.0]
    monkeypatch.setattr(wa.time, "time", lambda: clock[0])
    client.messages = [msg(MediaType="image")]
    client.download_error = "temporary network timeout"
    for delay in (1, 2, 4, 8, 16, 30, 30):
        run(client, output)
        entry = media_state(output)["items"]["123@g.us/M1"]
        assert entry["next"] == clock[0] + delay * 86400
        count = len(client.downloads)
        run(client, output)
        assert len(client.downloads) == count
        clock[0] = entry["next"]
    assert all("--retry-on-phone" not in args for args, _ in client.downloads)


def test_only_two_focus_images_ignore_cooldown(setup):
    client, output = setup
    client.messages = [msg(f"M{i}", MediaType="image") for i in range(5)]
    client.download_error = "download failed with status code 403"
    run(client, output)
    focus = media_state(output)["focus"]
    assert len(focus) == 2
    client.downloads.clear()
    run(client, output)
    assert len(client.downloads) == 2
    assert all("--retry-on-phone" in args for args, _ in client.downloads)
    assert media_state(output)["focus"] == focus


def test_confirmed_not_on_phone_skipped_permanently(setup):
    client, output = setup
    client.messages = [msg(MediaType="image")]
    client.download_error = "download failed with status code 403"
    run(client, output)
    client.download_error = "media recovery not_on_phone for 123@g.us/M1: "
    run(client, output)
    assert media_state(output)["items"]["123@g.us/M1"]["status"] == "unavailable"
    client.downloads.clear()
    run(client, output)
    assert not client.downloads


def test_database_unavailable_skips_without_network(setup):
    client, output = setup
    client.messages = [msg(MediaType="image")]
    with sqlite3.connect(client.store / "wacli.db") as db:
        db.execute(
            "insert into messages(chat_jid,msg_id,media_type,media_unavailable_at) values('123@g.us','M1','image',123)"
        )
    run(client, output)
    assert not client.downloads
    assert media_state(output)["items"]["123@g.us/M1"]["status"] == "unavailable"


def test_changed_media_reference_reopens_unavailable_without_full_export(setup):
    client, output = setup
    client.messages = [msg(MediaType="image")]
    with sqlite3.connect(client.store / "wacli.db") as db:
        db.execute(
            "insert into messages(chat_jid,msg_id,media_type,media_unavailable_at,direct_path) values('123@g.us','M1','image',123,'old')"
        )
    run(client, output)
    with sqlite3.connect(client.store / "wacli.db") as db:
        db.execute("update messages set media_unavailable_at=NULL,direct_path='new'")
    client.exports.clear()
    run(client, output)
    assert not client.exports
    assert media_state(output)["items"] == {}
    assert rows(output)["M1"]["mediaPath"]


def test_new_cached_copy_bypasses_transient_backoff(setup):
    client, output = setup
    client.messages = [msg(MediaType="image")]
    with sqlite3.connect(client.store / "wacli.db") as db:
        db.execute("insert into messages(chat_jid,msg_id,media_type) values('123@g.us','M1','image')")
    client.download_error = "temporary network error"
    run(client, output)
    cached = client.store / "cached.jpg"
    cached.write_bytes(b"cached")
    with sqlite3.connect(client.store / "wacli.db") as db:
        db.execute("update messages set local_path=?", (str(cached),))
    client.download_error = False
    run(client, output)
    assert media_state(output)["items"] == {}


def test_image_attempt_budget_preserves_remaining_queue(setup):
    client, output = setup
    client.messages = [msg(f"M{i}", MediaType="image") for i in range(30)]
    client.download_error = "temporary network error"
    run(client, output)
    assert len(client.downloads) == 20
    assert len(media_state(output)["items"]) == 30


def test_missing_download_information_is_not_probed_on_phone(setup, capsys):
    client, output = setup
    client.messages = [msg(MediaType="image")]
    with sqlite3.connect(client.store / "wacli.db") as db:
        db.execute("insert into messages(chat_jid,msg_id,media_type,media_key) values('123@g.us','M1','image',NULL)")
    run(client, output)
    run(client, output)
    assert not client.downloads
    assert media_state(output)["items"]["123@g.us/M1"]["kind"] == "metadata"
    text = capsys.readouterr().err
    assert "Message yourself" in text
    assert "forward" in text


def test_sync_is_default_and_no_sync_is_available(monkeypatch, tmp_path):
    syncs = []

    class Fake:
        def __init__(self, *args):
            pass

        def call(self, *args, **kwargs):
            if args == ("doctor",):
                return {"lock_held": False}
            syncs.append(args)

    monkeypatch.setattr(wa, "Wacli", Fake)
    monkeypatch.setattr(wa, "backup", lambda *args: None)
    monkeypatch.setenv("WABACKUP_CACHE_DIR", str(tmp_path / "cache"))
    runner = CliRunner()
    result = runner.invoke(wa.app, ["--output-dir", str(tmp_path / "archive")])
    assert result.exit_code == 0, result.output
    assert syncs == [("sync", "--once", "--idle-exit", "10s")]
    syncs.clear()
    assert runner.invoke(wa.app, ["--output-dir", str(tmp_path / "archive"), "--no-sync"]).exit_code == 0
    assert syncs == []


def test_existing_store_owner_is_not_disrupted(monkeypatch, tmp_path):
    class Fake:
        def __init__(self, *args):
            pass

        def call(self, *args, **kwargs):
            assert args == ("doctor",)
            return {"lock_held": True}

    monkeypatch.setattr(wa, "Wacli", Fake)
    monkeypatch.setattr(wa, "backup", lambda *args: None)
    monkeypatch.setenv("WABACKUP_CACHE_DIR", str(tmp_path / "cache"))
    result = CliRunner().invoke(wa.app, ["--output-dir", str(tmp_path / "archive")])
    assert result.exit_code == 0, result.output
    assert "active store owner" in result.output


def test_recovery_hints_show_sender_and_searchable_caption_instead_of_ids(setup, capsys):
    import shlex

    client, output = setup
    client.messages = [
        msg(
            "INTERNAL-MESSAGE-ID",
            ChatName="Alice's Family",
            SenderName="Meera",
            MediaType="image",
            MediaCaption="Annual sports day photo",
            Text="fallback text",
        )
    ]
    client.download_error = "download failed with status code 410"
    run(client, output)
    text = capsys.readouterr().err
    assert "from Meera" in text and 'search for "Annual sports day photo"' in text
    assert "INTERNAL-MESSAGE-ID" not in text
    command = next(line.strip() for line in text.splitlines() if line.strip().startswith("wabackup --conversation"))
    assert shlex.split(command) == ["wabackup", "--conversation", "Alice's Family"]
    checklist = (wa.cache_dir(output) / "media-help.txt").read_text()
    assert "from Meera" in checklist and "Annual sports day photo" in checklist
    assert "INTERNAL-MESSAGE-ID" not in checklist


def test_captionless_hint_and_message_text_fallback():
    base = {
        "messageId": "INTERNAL",
        "conversationTitle": "Family",
        "time": "2026-01-02T10:00:00Z",
        "author": "Ravi",
        "wacli": {"MediaType": "image", "Text": "[Image]"},
    }
    assert "photo without a caption" in wa.picture_hint(base, "123@g.us")
    assert "from Ravi" in wa.picture_hint(base, "123@g.us")
    base["wacli"]["Text"] = "School trip\nphotos"
    assert 'search for "School trip photos"' in wa.picture_hint(base, "123@g.us")
    assert "INTERNAL" not in wa.picture_hint(base, "123@g.us")


def test_one_chat_retries_all_waiting_images_without_touching_other_archive_or_checkpoint(setup, capsys):
    client, output = setup
    client.messages = [msg(f"F{i}", MediaType="image") for i in range(5)] + [
        msg("OTHER", ChatJID="456@g.us", ChatName="Work", MediaType="image")
    ]
    client.download_error = "download failed with status code 403"
    run(client, output)
    before_checkpoint = wa.state_file(output).read_bytes()
    other_path = output / "Work [456@g.us].jsonl"
    before_other = other_path.read_bytes()
    other_retry = dict(media_state(output)["items"]["456@g.us/OTHER"])
    client.downloads.clear()
    client.exports.clear()
    client.download_error = False
    run(client, output, conversations=["Family"])
    assert client.exports == [("--chat", "Family")]
    assert len(client.downloads) == 5
    assert all(args[args.index("--chat") + 1] == "123@g.us" for args, _ in client.downloads)
    assert other_path.read_bytes() == before_other
    assert wa.state_file(output).read_bytes() == before_checkpoint
    assert media_state(output)["items"] == {"456@g.us/OTHER": other_retry}
    assert all(r.get("mediaPath") for r in wa.load(output / "Family [123@g.us].jsonl").values())
