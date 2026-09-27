from __future__ import annotations

import asyncio
import datetime as dt
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import backupwhatsapp as backup


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
        async def evaluate(self, expression, arg=...):
            if expression == backup.SCROLL_HISTORY_JS:
                assert arg["fallbackTime"] == "2026-09-05T01:24:00+00:00"
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
