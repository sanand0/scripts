from __future__ import annotations

import asyncio
import base64
import datetime as dt
import json
import shutil
import subprocess
from contextlib import nullcontext
from unittest.mock import AsyncMock, MagicMock
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import backupwhatsapp as backup


@pytest.mark.parametrize(("flags", "enabled"), [
    ([], True),
    (["--no-images"], False),
    (["--images"], True),
])
def test_image_download_cli_defaults(monkeypatch, tmp_path: Path, flags: list[str], enabled: bool) -> None:
    received = []

    async def fake_run_backup(*args):
        received.append(args[-1])

    monkeypatch.setattr(backup, "run_backup", fake_run_backup)
    scraper = tmp_path / 'scraper.js'
    scraper.write_text('')
    result = CliRunner().invoke(backup.app, [*flags, '--scraper', str(scraper)])
    assert result.exit_code == 0, result.output
    assert received == [enabled]


def test_image_export_is_relative_and_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "TDS [123@g.us].jsonl"
    jpeg = b"\xff\xd8\xff" + b"example-image"
    data = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()
    relative = backup.save_image(path, "123@g.us", "ABC123", data)
    assert relative == "media/123@g.us/ABC123.jpg"
    assert (tmp_path / relative).read_bytes() == jpeg
    assert backup.save_image(path, "123@g.us", "ABC123", data) == relative
    assert len([p for p in (tmp_path / "media").rglob("*") if p.is_file()]) == 1


@pytest.mark.parametrize("data", [
    "data:image/jpeg;base64," + base64.b64encode(b"not-an-image").decode(),
    "data:text/html;base64," + base64.b64encode(b"hello").decode(),
    "data:image/jpeg;base64,not:base64",
])
def test_image_export_rejects_bad_content(tmp_path: Path, data: str) -> None:
    with pytest.raises((ValueError, base64.binascii.Error)):
        backup.save_image(tmp_path / "Chat.jsonl", "123@g.us", "ABC123", data)
    assert not (tmp_path / "media").exists()


def test_load_jsonl_reports_corrupt_file_without_changing_it(tmp_path: Path) -> None:
    path = tmp_path / "Chat [123@g.us].jsonl"
    content = '\n{"messageId":"valid","conversationId":"123@g.us"}\nOther.jsonl:{"messageId":"wrong-chat"}\n'
    path.write_text(content)
    with pytest.raises(ValueError) as error:
        backup.load_jsonl(path)
    assert f"{path}:3:" in str(error.value)
    assert "no lines were skipped" in str(error.value)
    assert "wrong-chat" not in str(error.value)
    assert path.read_text() == content


def test_load_jsonl_missing_and_blank_lines(tmp_path: Path) -> None:
    path = tmp_path / "Chat.jsonl"
    assert backup.load_jsonl(path) == []
    path.write_text('\n{"messageId":"valid","conversationId":"123@g.us"}\n\n')
    assert backup.load_jsonl(path) == [{"messageId": "valid", "conversationId": "123@g.us"}]


def test_files_for_id_treats_brackets_literally(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(backup, "OUT_DIR", tmp_path)
    first = tmp_path / "Old title [123@g.us].jsonl"
    second = tmp_path / "New title [123@g.us].jsonl"
    other = tmp_path / "Other [1234@g.us].jsonl"
    for path in (first, second, other):
        path.write_text("")

    assert backup.files_for_id("123@g.us") == [second, first]


def test_already_checked_requires_exact_list_evidence() -> None:
    previous = {
        "chat": {
            "lastActiveText": "09:00",
            "lastActiveDay": "2026-08-15",
            "listTime": "2026-08-15T03:30:00+00:00",
        }
    }
    changed = {"lastActiveText": "18:00", "lastActiveDay": "2026-08-15"}

    assert not backup.already_checked(previous, "chat", changed, dt.datetime(2026, 8, 15, 12, 30, tzinfo=dt.UTC))


def test_same_day_later_activity_is_not_known_unchanged(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(backup, "OUT_DIR", tmp_path)
    path = backup.filename_for("Chat", "123@g.us")
    path.write_text('{"messageId":"old","conversationId":"123@g.us","time":"2026-08-15T03:30:00+00:00"}\n')
    chat = {
        "title": "Chat",
        "conversationId": "123@g.us",
        "lastActiveText": "18:00",
        "lastActiveTime": "2026-08-15T12:30:00+00:00",
        "lastActiveDay": "2026-08-15",
        "browserTimeZone": "Asia/Calcutta",
        "unreadCount": 0,
    }

    assert not backup.known_no_new_content(chat, {})


def test_merge_matches_live_scraper_for_numeric_and_corrected_values() -> None:
    assert backup.merged_value("mediaWidth", 320, 640) == (640, True)
    assert backup.merged_value("mediaWidth", 640, 320) == (640, False)
    assert backup.merged_value("time", "2026-08-14T10:00:00.000Z", "2026-08-15T10:00:00.000Z") == (
        "2026-08-15T10:00:00.000Z",
        True,
    )
    assert backup.merged_value("mediaDuration", "0:12", "0:13") == ("0:13", True)
    assert backup.merged_value("isOutgoing", True, False) == (True, False)
    assert backup.merged_value("conversationTitle", "A much longer old name", "New") == ("New", True)


def test_open_chat_fails_closed_when_identity_does_not_change() -> None:
    class FakePage:
        async def evaluate(self, expression, arg=...):
            if expression == backup.CHAT_LIST_JS:
                return {"chats": [{"title": "Chat", "conversationId": "expected@g.us"}]}
            if expression == backup.CLICK_CHAT_JS:
                return True
            return ""

        async def wait_for_selector(self, selector, timeout):
            return None

        async def wait_for_timeout(self, timeout):
            return None

    opened, _ = asyncio.run(backup.open_chat(FakePage(), "Chat", "expected@g.us", 0))

    assert not opened


def test_open_chat_reuses_already_open_exact_conversation(monkeypatch) -> None:
    page = MagicMock()
    page.wait_for_timeout = AsyncMock()
    monkeypatch.setattr(backup, 'current_chat_id', AsyncMock(return_value='expected@g.us'))
    monkeypatch.setattr(backup, 'list_chats', AsyncMock(side_effect=AssertionError('chat list must not be scanned')))
    assert asyncio.run(backup.open_chat(page, 'Chat', 'expected@g.us', 0)) == (True, 'already-open')
    page.wait_for_timeout.assert_awaited_once_with(1200)


def test_chat_list_scans_overlap_virtualized_rows() -> None:
    assert 0 < backup.CHAT_LIST_SCROLL_PAGE_FACTOR <= 1


def test_chat_scan_does_not_stop_on_repeated_virtualized_rows(monkeypatch) -> None:
    class FakePage:
        index = 0

        async def wait_for_selector(self, selector, timeout):
            return None

        async def eval_on_selector(self, selector, expression):
            self.index = 0 if "= 0" in expression else self.index + 1

        async def wait_for_timeout(self, timeout):
            return None

    async def fake_list_chats(page):
        title = "Target" if page.index == 12 else "Cached row"
        return {"scrollTop": page.index, "clientHeight": 1, "scrollHeight": 100, "chats": [{"title": title, "conversationId": title}]}

    monkeypatch.setattr(backup, "list_chats", fake_list_chats)

    chats = asyncio.run(backup.iter_chats(FakePage(), 15))

    assert [chat["title"] for chat in chats] == ["Cached row", "Target"]


def test_scrape_open_chat_passes_chat_list_time_as_dom_fallback(monkeypatch) -> None:
    class FakePage:
        async def evaluate(self, expression, arg=..., **kwargs):
            if expression == backup.SCROLL_HISTORY_JS:
                assert arg["fallbackTime"] == "2026-09-05T01:24:00+00:00"
                assert arg["images"] is True
                return {"messages": []}
            if "parser_dom_count" in expression:
                return {"parser_dom_count": 0, "history_scroller_found": False}
            return "123@g.us"

    async def no_inject(page, scraper):
        return None

    monkeypatch.setattr(backup, "inject_scraper", no_inject)
    fallback_time = dt.datetime(2026, 9, 5, 1, 24, tzinfo=dt.UTC)

    asyncio.run(backup.scrape_open_chat(FakePage(), None, fallback_time, 0, 0, 0))


def test_richer_replacement_preserves_previous_value_in_history(tmp_path: Path) -> None:
    path = tmp_path / "Chat [123@g.us].jsonl"
    path.write_text('{"messageId":"m1","conversationId":"123@g.us","text":"old"}\n')

    backup.update_conversation(path, "Chat", "123@g.us", [{"messageId": "m1", "text": "new expanded"}], None, None, 0)

    assert json.loads(path.read_text())["text"] == "new expanded"
    audit = [json.loads(line) for line in backup.history_path(path).read_text().splitlines()]
    text_change = next(row for row in audit if "text" in row["fields"])
    assert set(text_change["fields"]["text"].values()) == {"old", "new expanded"}


def test_update_normalizes_legacy_full_jid_user_ids(tmp_path: Path) -> None:
    path = tmp_path / "Chat [123@g.us].jsonl"
    path.write_text('{"messageId":"m1","conversationId":"123@g.us","userId":"123@g.us"}\n')

    changed = backup.update_conversation(path, "Chat", "123@g.us", [], None, None, 0)

    assert changed == 1
    assert json.loads(path.read_text())["userId"] == "123"


@pytest.mark.parametrize('row', [[], None, {}, {'messageId': ''}, {'messageId': 'm'},
    {'messageId': 'm', 'conversationId': 'other@g.us'}])
def test_invalid_records_cannot_replace_backup(tmp_path: Path, row) -> None:
    path = tmp_path / 'Chat [123@g.us].jsonl'
    original = '{"messageId":"old","conversationId":"123@g.us"}\n'
    path.write_text(original)
    with pytest.raises(ValueError, match='Invalid backup'):
        backup.write_jsonl(path, [{'messageId': 'valid', 'conversationId': '123@g.us'}, row])
    assert path.read_text() == original
    assert list(tmp_path.iterdir()) == [path]


def test_valid_write_and_read(tmp_path: Path) -> None:
    path = tmp_path / 'Chat [123@g.us].jsonl'
    rows = [{'messageId': 'm', 'conversationId': '123@g.us', 'text': 'hello'}]
    backup.write_jsonl(path, rows)
    assert backup.load_jsonl(path) == rows


def test_preflight_reports_all_bad_files_before_connecting(tmp_path: Path, monkeypatch) -> None:
    from unittest.mock import MagicMock

    monkeypatch.setattr(backup, 'OUT_DIR', tmp_path)
    monkeypatch.setattr(backup.obs, 'new_run', lambda *args, **kwargs: MagicMock())
    async def unexpected_connection(*args):
        pytest.fail('preflight must finish before CDP connects')
    monkeypatch.setattr(backup, 'connect_whatsapp_page', unexpected_connection)
    bad = tmp_path / 'Bad [123@g.us].jsonl'
    wrong = tmp_path / 'Wrong [456@g.us].jsonl'
    bad.write_text('search-output\n')
    wrong.write_text('{"messageId":"m","conversationId":"123@g.us"}\n')
    # Diagnostic/recovery artifacts are deliberately outside the top-level backup set.
    (tmp_path / '.recovery').mkdir()
    (tmp_path / '.recovery/bad.jsonl').write_text('preserved evidence')
    with pytest.raises(ValueError) as error:
        asyncio.run(backup.run_backup('http://unused', set(), '', None, None, None, None,
                                      0, 1, 1, 1, 0, True, 'jsonl'))
    assert f'{bad}:1:' in str(error.value)
    assert f'{wrong}:1:' in str(error.value)
    assert bad.read_text() == 'search-output\n'


def test_update_rejects_wrong_identity_without_history_writes(tmp_path: Path) -> None:
    path = tmp_path / 'Chat [123@g.us].jsonl'
    original = '{"messageId":"m","conversationId":"other@g.us"}\n'
    path.write_text(original)
    with pytest.raises(ValueError):
        backup.update_conversation(path, 'Chat', '123@g.us', [], None, None, 0)
    assert path.read_text() == original
    assert not backup.history_path(path).exists()


@pytest.mark.parametrize('message', [{'text': 'missing ID'}, {'messageId': 'm', 'conversationId': 'other@g.us'}])
def test_update_rejects_bad_incoming_records_before_writing(tmp_path: Path, message) -> None:
    path = tmp_path / 'Chat [123@g.us].jsonl'
    original = '{"messageId":"m","conversationId":"123@g.us","text":"old"}\n'
    path.write_text(original)
    with pytest.raises(ValueError):
        backup.update_conversation(path, 'Chat', '123@g.us', [message], None, None, 0)
    assert path.read_text() == original
    assert not backup.history_path(path).exists()


@pytest.mark.parametrize('row', [None, [], {}, {'messageId': 1, 'conversationId': '123@g.us'},
                               {'messageId': 'm', 'conversationId': 'other@g.us'}])
def test_load_rejects_invalid_records_with_line_number(tmp_path: Path, row) -> None:
    path = tmp_path / 'Chat [123@g.us].jsonl'
    path.write_text('\n' + json.dumps(row) + '\n')
    with pytest.raises(ValueError) as error:
        backup.load_jsonl(path)
    assert f'{path}:2:' in str(error.value)


def test_merge_rejects_cross_chat_records_without_deleting_sources(tmp_path: Path) -> None:
    target = tmp_path / 'Target [123@g.us].jsonl'
    source = tmp_path / 'Source [456@g.us].jsonl'
    target.write_text('{"messageId":"a","conversationId":"123@g.us"}\n')
    source.write_text('{"messageId":"b","conversationId":"456@g.us"}\n')
    before = {p: p.read_bytes() for p in (target, source)}
    with pytest.raises(ValueError):
        backup.merge_jsonl_files(target, [source])
    assert {p: p.read_bytes() for p in (target, source)} == before
    assert not backup.history_path(target).exists()


@pytest.mark.parametrize("earlier_button", [False, True])
def test_history_scroll_captures_virtualized_messages_between_endpoints(earlier_button: bool) -> None:
    """A jump to the top renders endpoints but skips the messages in between."""
    harness = r'''
const scrape = SCROLL_SOURCE;
const scroller = {
  position: 2000, scrollHeight: 3000, clientHeight: 1000,
  get scrollTop() { return this.position; },
  set scrollTop(value) { this.position = Math.max(0, Math.min(value, this.scrollHeight - this.clientHeight)); },
  dispatchEvent() {},
};
const main = { querySelectorAll: () => [] };
globalThis.document = {
  querySelector: (selector) => selector === 'div#main' ? main : EARLIER_BUTTON && selector.includes('Load earlier') ? { click() { if(scroller.scrollTop > 4) throw new Error('loaded earlier without traversing current messages'); } } : null,
  querySelectorAll: (selector) => selector === 'div#main div' ? [scroller] : [],
};
globalThis.setTimeout = (done) => { done(); };
globalThis.whatsappscraper = { whatsappMessages: () =>
  Array.from({length: 30}, (_, i) => ({
    messageId: String(i), text: `message ${i}`,
    time: new Date(Date.UTC(2026, 9, 20, 0, i)).toISOString(),
  })).filter((_, i) => i * 100 >= scroller.scrollTop && i * 100 < scroller.scrollTop + 1000)
};
const result = await scrape({cutoff: '2026-10-20T00:00:00.000Z', maxRounds: 20, settleMs: 0, images: false});
console.log(JSON.stringify(result));
'''.replace('SCROLL_SOURCE', backup.SCROLL_HISTORY_JS).replace('EARLIER_BUTTON', json.dumps(earlier_button))
    result = subprocess.run(['node', '--input-type=module'], input=harness, text=True, capture_output=True, check=True)
    data = json.loads(result.stdout)
    assert data['reason'] == 'cutoff-reached'
    assert {row['messageId'] for row in data['messages']} == {str(i) for i in range(30)}


def _install_run_backup_mocks(monkeypatch, out_dir: Path, cache_dir: Path, *, incremental: bool, reason: str):
    conversation_id = "120363430988346355@g.us"
    title = "TDS"
    monkeypatch.setattr(backup, "OUT_DIR", out_dir)
    monkeypatch.setattr(backup, "CACHE_DIR", cache_dir)
    out_dir.mkdir(parents=True)
    cache_dir.mkdir(parents=True)

    path = backup.filename_for(title, conversation_id)
    old = {
        "messageId": "old-message",
        "conversationId": conversation_id,
        "time": "2026-10-26T10:00:00+00:00",
        "mediaPath": "media/120363430988346355@g.us/old.jpg",
    }
    original_jsonl = json.dumps(old, separators=(",", ":")) + "\n"
    path.write_text(original_jsonl)
    history_path = backup.history_path(path)
    history_path.parent.mkdir(parents=True)
    original_history = '{"archivedAt":"2026-10-01T00:00:00+00:00","reason":"prior"}\n'
    history_path.write_text(original_history)
    media_path = path.parent / old["mediaPath"]
    media_path.parent.mkdir(parents=True)
    media_path.write_bytes(b"keep existing media")
    original_media = {p.relative_to(path.parent): p.read_bytes() for p in (path.parent / "media").rglob("*") if p.is_file()}

    checked_path = backup.state_path()
    original_checked = '{"unrelated":{"sentinel":"keep"}}\n'
    checked_path.write_text(original_checked)

    chat = {
        "title": title,
        "conversationId": conversation_id,
        "lastActiveText": "10:10",
        "lastActiveTime": "2026-10-27T10:10:00+00:00",
        "lastActiveDay": "2026-10-27",
        "browserTimeZone": "UTC",
        "unreadCount": 0,
    }
    page = MagicMock()
    page.title = AsyncMock(return_value="WhatsApp")
    page.evaluate = AsyncMock(return_value={"chat_list": 1, "main_data_id": 1, "main_present": True, "pane_present": True})
    page.close = AsyncMock()
    trace = MagicMock()
    trace.span.return_value = nullcontext()
    trace.stamp = "2026-10-27T10-20-00Z-test"

    async def fake_connect(_cdp_url):
        return page

    async def fake_iter_chats(_page, _max_scan, _stop_at=None, _checked_state=None):
        return [chat]

    async def fake_open_chat(_page, _title, _conversation_id, _max_scan):
        return True, "visible"

    image = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xffmock-image").decode()

    async def fake_scrape(_page, _cutoff, _fallback_time, _max_messages, _max_rounds, _settle_ms, **_kwargs):
        return ([{
            "messageId": "new-message",
            "conversationId": conversation_id,
            "time": "2026-10-27T10:05:00+00:00",
            "text": "new message",
            "_imageData": image,
        }], {
            "reason": reason,
            "rounds": 200 if reason == "max-rounds" else 3,
            "conversation_id": conversation_id,
            "history_scroller_found": True,
        })

    monkeypatch.setattr(backup.obs, "new_run", MagicMock(return_value=trace))
    monkeypatch.setattr(backup.obs, "attach_page_observers", MagicMock())
    monkeypatch.setattr(backup.obs, "capture_dom_outline", AsyncMock(return_value={"outline": []}))
    monkeypatch.setattr(backup.obs, "classify_whatsapp_anomalies", MagicMock(return_value=[]))
    monkeypatch.setattr(backup.obs, "monthly_baseline_exists", MagicMock(return_value=True))
    monkeypatch.setattr(backup, "connect_whatsapp_page", fake_connect)
    monkeypatch.setattr(backup, "iter_chats", fake_iter_chats)
    monkeypatch.setattr(backup, "open_chat", fake_open_chat)
    monkeypatch.setattr(backup, "scrape_open_chat", fake_scrape)
    monkeypatch.setattr(backup, "inject_scraper", AsyncMock())
    monkeypatch.setattr(backup, "incremental_stop_time", lambda: None)

    return {
        "title": title,
        "conversation_id": conversation_id,
        "path": path,
        "original_jsonl": original_jsonl,
        "history_path": history_path,
        "original_history": original_history,
        "media_path": path.parent / "media",
        "original_media": original_media,
        "checked_path": checked_path,
        "original_checked": original_checked,
        "trace": trace,
        "page": page,
        "incremental": incremental,
    }


async def _run_test_backup(incremental: bool) -> None:
    since = None if incremental else dt.datetime(2026, 10, 26, 10, 0, tzinfo=dt.UTC)
    await backup.run_backup(
        "http://localhost:9222",
        set() if incremental else {"TDS"},
        "",
        since,
        None,
        None,
        None,
        0,
        0,
        1,
        200,
        0,
        False,
        "text",
        True,
    )


@pytest.mark.parametrize('open_title,open_id,found', [('TDS', 'expected', True), ('TDS', '', False), ('Other chat', 'expected', False)])
def test_explicit_request_can_use_matching_open_chat_when_sidebar_misses_it(tmp_path: Path, monkeypatch, open_title: str, open_id: str, found: bool) -> None:
    paths = _install_run_backup_mocks(monkeypatch, tmp_path / 'out', tmp_path / 'cache', incremental=False, reason='cutoff-reached')
    monkeypatch.setattr(backup, 'iter_chats', AsyncMock(return_value=[]))
    monkeypatch.setattr(backup, 'current_chat_id', AsyncMock(return_value=paths['conversation_id'] if open_id else ''))
    async def evaluate(expression, *args, **kwargs):
        if 'chat_list:' in expression:
            return {'chat_list': 0, 'main_data_id': 1, 'main_present': True, 'pane_present': True}
        return open_title
    paths['page'].evaluate = AsyncMock(side_effect=evaluate)
    if found:
        asyncio.run(_run_test_backup(False))
        assert {r['messageId'] for r in backup.load_jsonl(paths['path'])} == {'old-message', 'new-message'}
    else:
        with pytest.raises(RuntimeError, match='not found'):
            asyncio.run(_run_test_backup(False))
        assert paths['path'].read_text() == paths['original_jsonl']


@pytest.mark.parametrize("incremental", [True, False], ids=["incremental", "explicit-range"])
@pytest.mark.parametrize("reason", ["max-rounds", "history-unavailable"])
def test_incomplete_history_fails_before_any_per_chat_write(tmp_path: Path, monkeypatch, incremental: bool, reason: str) -> None:
    paths = _install_run_backup_mocks(monkeypatch, tmp_path / "out", tmp_path / "cache", incremental=incremental, reason=reason)

    with pytest.raises(RuntimeError, match="History scan incomplete"):
        asyncio.run(_run_test_backup(incremental))

    assert paths["path"].read_text() == paths["original_jsonl"]
    assert paths["history_path"].read_text() == paths["original_history"]
    assert {p.relative_to(paths["path"].parent): p.read_bytes() for p in paths["media_path"].rglob("*") if p.is_file()} == paths["original_media"]
    assert paths["checked_path"].read_text() == paths["original_checked"]
    paths["trace"].finish.assert_called_once()
    assert paths["trace"].finish.call_args.args[0]["status"] == "failed"


def test_stalled_load_earlier_does_not_claim_history_complete() -> None:
    harness = r'''
const scrape = SCROLL_SOURCE;
const scroller = {scrollTop: 0, scrollHeight: 1500, clientHeight: 1000, dispatchEvent() {}};
const main = {querySelectorAll: () => []};
const earlier = {click() {}};
globalThis.document = {
  querySelector: selector => selector === 'div#main' ? main : selector.includes('Load earlier') ? earlier : null,
  querySelectorAll: selector => selector === 'div#main div' ? [scroller] : [],
};
globalThis.setTimeout = done => done();
globalThis.whatsappscraper = {whatsappMessages: () => [{messageId: 'new', text: 'new', time: '2026-10-29T00:00:00.000Z'}]};
const result = await scrape({cutoff: '2026-10-26T00:00:00.000Z', maxRounds: 20, settleMs: 0, images: false});
console.log(JSON.stringify(result));
'''.replace('SCROLL_SOURCE', backup.SCROLL_HISTORY_JS)
    result = subprocess.run(['node', '--input-type=module'], input=harness, text=True, capture_output=True, check=True)
    assert json.loads(result.stdout)['reason'] == 'history-unavailable'


@pytest.mark.parametrize("incremental", [True, False], ids=["incremental", "explicit-range"])
def test_cutoff_reached_still_persists_messages_and_media(tmp_path: Path, monkeypatch, incremental: bool) -> None:
    paths = _install_run_backup_mocks(monkeypatch, tmp_path / "out", tmp_path / "cache", incremental=incremental, reason="cutoff-reached")

    asyncio.run(_run_test_backup(incremental))

    rows = backup.load_jsonl(paths["path"])
    assert {row["messageId"] for row in rows} == {"old-message", "new-message"}
    new_row = next(row for row in rows if row["messageId"] == "new-message")
    image_path = paths["path"].parent / new_row["mediaPath"]
    assert image_path.is_file()
    checked = json.loads(paths["checked_path"].read_text())
    if incremental:
        assert backup.chat_key(paths["title"], paths["conversation_id"]) in checked
    else:
        assert checked == {"unrelated": {"sentinel": "keep"}}


def test_explicit_message_date_overrides_stale_date_chip() -> None:
    if not shutil.which("node"):
        pytest.skip("Node.js is required for this JavaScript regression check")
    start = backup.SCROLL_HISTORY_JS.index("  const rowsFromDateChips = () => {")
    end = backup.SCROLL_HISTORY_JS.index("  const mediaFiles = [];", start)
    timestamp_parser = backup.SCROLL_HISTORY_JS[start:end]
    node_test = f"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
const timestampParser = {json.dumps(timestamp_parser)};
const dataId = {{ getAttribute: () => 'm1' }};
const row = {{
  matches: (selector) => selector === '[role="row"]',
  querySelector: (selector) => selector === '[data-id]' ? dataId
    : selector === '[data-pre-plain-text]' ? {{ getAttribute: () => '[2:30 pm, 27/10/2026]' }}
    : null,
  querySelectorAll: () => [],
  closest: () => null,
}};
const staleDateChip = {{
  matches: () => false,
  closest: () => null,
  querySelector: () => null,
  innerText: '20/10/2026',
}};
const context = {{
  fallbackTime: '',
  document: {{ querySelector: () => ({{ querySelectorAll: () => [staleDateChip, row] }}) }},
  parseClock: (value) => {{
    const match = String(value || '').match(/^(\\d{{1,2}}):(\\d{{2}})\\s*([ap]m)$/i);
    if (!match) return null;
    let hours = Number(match[1]) % 12;
    if (match[3].toLowerCase() === 'pm') hours += 12;
    return {{ hours, minutes: Number(match[2]) }};
  }},
  parseDateLabel: (value) => {{
    const match = String(value || '').match(/^(\\d{{1,2}})\\/(\\d{{1,2}})\\/(\\d{{4}})$/);
    return match ? new Date(Number(match[3]), Number(match[2]) - 1, Number(match[1])) : null;
  }},
  visibleTimeForRow: () => '2:30 pm',
  messageIdFromDataId: (value) => value,
  fallbackText: () => ({{}}),
  additionalFields: () => ({{}}),
}};
const result = vm.runInNewContext(`${{timestampParser}}\\nrowsFromDateChips()`, context);
assert.equal(result.rows.m1.time, new Date(2026, 9, 27, 14, 30).toISOString());
"""
    result = subprocess.run(["node", "-e", node_test], text=True, capture_output=True, timeout=5)
    assert result.returncode == 0, result.stderr
