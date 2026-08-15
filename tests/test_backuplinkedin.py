from __future__ import annotations

import asyncio
import datetime as dt
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import backuplinkedin as backup


def response(value: object) -> io.BytesIO:
    return io.BytesIO(json.dumps(value).encode())


def test_page_cdp_url_prefers_existing_linkedin_target(monkeypatch) -> None:
    calls = []

    def fake_urlopen(request, timeout):
        calls.append((request, timeout))
        return response(
            [
                {"type": "page", "url": "https://example.com", "webSocketDebuggerUrl": "ws://example"},
                {"type": "page", "url": "https://www.linkedin.com/feed/", "webSocketDebuggerUrl": "ws://linkedin"},
            ]
        )

    monkeypatch.setattr(backup, "urlopen", fake_urlopen)

    assert backup.page_cdp_url("http://localhost:9222") == "ws://linkedin"
    assert calls == [("http://localhost:9222/json/list", 5)]


def test_page_cdp_url_creates_target_when_linkedin_is_not_open(monkeypatch) -> None:
    calls = []

    def fake_urlopen(request, timeout):
        calls.append((request, timeout))
        if len(calls) == 1:
            return response([])
        return response({"webSocketDebuggerUrl": "ws://new-linkedin"})

    monkeypatch.setattr(backup, "urlopen", fake_urlopen)

    assert backup.page_cdp_url("http://localhost:9222/") == "ws://new-linkedin"
    request, timeout = calls[1]
    assert request.get_method() == "PUT"
    assert request.full_url.startswith("http://localhost:9222/json/new?")
    assert "linkedin.com" in request.full_url
    assert timeout == 5


def test_page_cdp_url_preserves_direct_websocket() -> None:
    assert backup.page_cdp_url("ws://localhost:9222/devtools/page/123") == "ws://localhost:9222/devtools/page/123"


def test_exact_linkedin_id_timestamp() -> None:
    created = dt.datetime(2026, 8, 14, 12, tzinfo=dt.UTC)
    snowflake = int(created.timestamp() * 1000) << 22

    assert backup.linkedin_id_datetime(f"urn:li:activity:{snowflake}") == created


def test_new_snapshot_counts_can_decrease_to_zero() -> None:
    old = {"type": "post", "id": "urn:li:activity:1", "reactionCount": 10, "commentCount": 2}
    new = {"type": "post", "id": "urn:li:activity:1", "reactionCount": 0, "commentCount": 0}

    assert backup.merge_row(old, new) == new


def test_direct_cdp_click_dispatches_trusted_mouse_events() -> None:
    class FakePage:
        def __init__(self) -> None:
            self.commands = []

        async def evaluate(self, expression, arg=...):
            return {"x": 12, "y": 34}

        async def command(self, method, **params):
            self.commands.append((method, params))

    page = FakePage()
    asyncio.run(backup.CDPElement(page, "document.body").click())

    assert [params["type"] for _, params in page.commands] == ["mousePressed", "mouseReleased"]
    assert all(params["x"] == 12 and params["y"] == 34 for _, params in page.commands)
