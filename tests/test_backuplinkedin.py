from __future__ import annotations

import asyncio
import datetime as dt
import io
import json
import runpy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import backuplinkedin as backup

SDUI_FIXTURE = r'''
<div id="post" componentkey="update-card-focus-post-token" role="listitem">
  <header>
    <button aria-label="Open control menu for post by Test Author"></button>
    <a href="https://www.linkedin.com/in/test-author/?miniProfileUrn=urn%3Ali%3Afs_miniProfile%3Atest"><p><span aria-hidden="true">Test Author</span> • 1st</p></a>
    <p>Researcher and writer</p><p>2h • edited</p>
    <span aria-label="Test Author Verified Profile Premium"></span>
  </header>
  <div data-testid="expandable-text-box">First line<br>Second <a href="https://www.linkedin.com/safety/go/?url=https%3A%2F%2Fexample.org%2Fsafe%3Fa%3D1">safe link</a><button>more</button></div>
  <button aria-label="Reaction button state: no reaction"></button>
  <span id="reaction-count">12 reactions</span><span aria-labelledby="reaction-count"></span>
  <button aria-label="Comment">7</button><button aria-label="Repost">3</button>
  <a href="/analytics/post-summary/urn:li:activity:7510870387140857856/?trk=metrics">View analytics</a>
  <ul><li><svg id="praise-consumption-icon"></svg></li></ul>
  <img alt="View Test Author’s profile" src="https://media.licdn.com/profile-displayphoto/1">
  <img alt="View image" src="https://media.licdn.com/post/thumb-160" srcset="https://media.licdn.com/post/thumb-160 1x, https://media.licdn.com/post/full-1200 2x">
  <div componentkey="CommentComponentReference_urn:li:comment:(activity:7510870387140857856,7510958357751615490)">
    <header>
      <button aria-label="View more options for Commenter"></button>
      <a href="https://www.linkedin.com/in/commenter/?miniProfileUrn=urn%3Ali%3Afs_miniProfile%3Acommenter"><p><span aria-hidden="true">Commenter</span> • 2nd</p><p>Commenter headline</p></a>
      <p>1d • edited</p><span aria-label="Commenter Verified Premium"></span>
    </header>
    <div data-testid="expandable-text-box">Comment<br>body <button>more</button></div>
    <button>4</button><span aria-label="Reacted to by the author"></span>
    <div componentkey="CommentComponentReference_urn:li:comment:(activity:7510870387140857856,7510960000000000000)">
      <header><button aria-label="View more options for Reply"></button><a href="https://www.linkedin.com/in/replier/"><p><span aria-hidden="true">Replier</span> • 3rd</p><p>Reply headline</p></a><p>3h</p></header>
      <div data-testid="expandable-text-box">Reply body</div><button>2</button>
    </div>
  </div>
</div>
'''


def extract_fixture(html: str, script: str) -> list[dict[str, object]]:
    async def run() -> list[dict[str, object]]:
        from playwright.async_api import async_playwright

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            page = await browser.new_page(base_url="https://www.linkedin.com")
            await page.set_content(html)
            element = await page.query_selector("#post")
            assert element is not None
            result = await element.evaluate(script, {"scrapedAt": "2026-10-04T00:00:00+00:00"})
            await browser.close()
            return result

    return asyncio.run(run())


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


def test_default_output_path_follows_home(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    namespace = runpy.run_path(str(Path(__file__).resolve().parents[1] / "backuplinkedin.py"), run_name="test_default_home")
    expected = tmp_path / "Documents/data/linkedin-posts.jsonl"
    assert namespace["OUT_PATH"] == expected
    assert namespace["describe"]()["output"] == str(expected)


def test_exact_linkedin_id_timestamp() -> None:
    created = dt.datetime(2026, 8, 14, 12, tzinfo=dt.UTC)
    snowflake = int(created.timestamp() * 1000) << 22

    assert backup.linkedin_id_datetime(f"urn:li:activity:{snowflake}") == created


def test_new_snapshot_counts_can_decrease_to_zero() -> None:
    old = {"type": "post", "id": "urn:li:activity:1", "reactionCount": 10, "commentCount": 2}
    new = {"type": "post", "id": "urn:li:activity:1", "reactionCount": 0, "commentCount": 0}

    assert backup.merge_row(old, new) == new


def test_direct_cdp_click_delivers_one_native_dom_click() -> None:
    async def run() -> int:
        from playwright.async_api import async_playwright

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            page = await browser.new_page()
            await page.set_content('<button id="clicker">Click</button><output id="count">0</output>')
            await page.evaluate(
                """() => document.querySelector('#clicker').addEventListener('click', () => {
                    const out = document.querySelector('#count'); out.textContent = String(Number(out.textContent) + 1);
                })"""
            )
            await backup.CDPElement(page, "document.querySelector('#clicker')").click()
            count = await page.locator("#count").inner_text()
            await browser.close()
            return int(count)

    assert asyncio.run(run()) == 1


def test_sdui_extracts_post_and_nested_comments_from_semantic_dom() -> None:
    rows = extract_fixture(SDUI_FIXTURE, backup.SDUI_EXTRACT_JS)

    post, comment, reply = rows
    assert post["id"] == "urn:li:activity:7510870387140857856"
    assert post["analyticsUrl"].endswith("activity:7510870387140857856/")
    assert post["authorName"] == "Test Author"
    assert post["authorProfile"] == "https://www.linkedin.com/in/test-author/"
    assert post["authorMiniProfileUrn"] == "urn:li:fs_miniProfile:test"
    assert post["authorDescription"] == "Researcher and writer"
    assert post["postedText"] == "2h • edited"
    assert post["edited"] is True
    assert post["premiumVerifiedBadges"] == ["premium", "verified"]
    assert post["content"] == "First line\nSecond safe link"
    assert post["links"] == ["https://example.org/safe?a=1"]
    assert post["reactionCount"] == 12
    assert post["commentCount"] == 7
    assert post["repostCount"] == 3
    assert post["reactionTypesVisible"] == ["celebrate"]
    assert post["mediaCount"] == 1
    assert post["media"][0]["sources"][-1].endswith("full-1200")

    assert comment["id"].startswith("urn:li:comment:(activity:7510870387140857856,")
    assert comment["commenterName"] == "Commenter"
    assert comment["commenterMiniProfileUrn"] == "urn:li:fs_miniProfile:commenter"
    assert comment["commenterDegree"] == "2nd"
    assert comment["commenterDescription"] == "Commenter headline"
    assert comment["commentedText"] == "1d • edited"
    assert comment["edited"] is True
    assert comment["content"] == "Comment\nbody"
    assert comment["reactionCount"] == 4
    assert comment["reactedByAuthor"] is True
    assert comment["parentCommentId"] == ""

    assert reply["commenterName"] == "Replier"
    assert reply["commenterDegree"] == "3rd"
    assert reply["content"] == "Reply body"
    assert reply["parentCommentId"] == comment["id"]


def test_legacy_extract_still_handles_basic_post() -> None:
    html = '''
    <div id="post" data-urn="urn:li:activity:7510870387140857856" role="article">
      <div class="feed-shared-actor"><span class="feed-shared-actor__name">Legacy Author</span><span class="feed-shared-actor__description">Legacy headline</span><span class="feed-shared-actor__sub-description"><span aria-hidden="true">3h</span></span></div>
      <div class="feed-shared-inline-show-more-text">Legacy content</div>
      <div class="feed-shared-social-counts">9 reactions\n2 comments\n1 repost</div>
      <a class="analytics-entry-point" href="/analytics/post-summary/urn:li:activity:7510870387140857856/?x=1">analytics</a>
    </div>
    '''
    rows = extract_fixture(html, backup.EXTRACT_JS)
    assert len(rows) == 1
    assert rows[0]["id"] == "urn:li:activity:7510870387140857856"
    assert rows[0]["content"] == "Legacy content"
    assert rows[0]["analyticsUrl"].endswith("activity:7510870387140857856/")


def test_sdui_selector_and_post_id_are_keyed_to_card_identity() -> None:
    async def run() -> tuple[int, list[str]]:
        from playwright.async_api import async_playwright

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            page = await browser.new_page(base_url="https://www.linkedin.com")
            await page.set_content(
                '<div componentkey="update-card-focus-a" role="listitem"><a href="/analytics/post-summary/urn:li:activity:1/">a</a></div>'
                '<div componentkey="update-card-focus-b" role="listitem"><a href="/analytics/post-summary/urn:li:activity:2/">b</a></div>'
            )
            count = await page.locator(backup.POST_SELECTOR).count()
            elements = await page.query_selector_all(backup.POST_SELECTOR)
            ids = [await element.evaluate(backup.POST_ID_JS) for element in elements]
            await browser.close()
            return count, ids

    count, ids = asyncio.run(run())
    assert count == 2
    assert ids == ["urn:li:activity:1", "urn:li:activity:2"]


def test_comment_loader_waits_for_async_hydration(monkeypatch) -> None:
    class FakePost:
        def __init__(self) -> None:
            self.loaded = False

        async def evaluate(self, expression, arg=...):
            return "2" if 'aria-label="Comment"' in expression else 0

        async def query_selector_all(self, selector):
            if selector == backup.COMMENT_SELECTOR:
                return [object(), object()] if self.loaded else []
            return []

    post = FakePost()
    sleeps = 0

    async def fake_sleep(_seconds):
        nonlocal sleeps
        sleeps += 1
        if sleeps == 1:
            post.loaded = True

    monkeypatch.setattr(backup.asyncio, "sleep", fake_sleep)
    stats = asyncio.run(backup.load_all_comments(post, max_rounds=10, settle_ms=1))
    assert stats["commentsLoaded"] == 2
    assert sleeps > 0


def test_comment_loader_maps_flat_sdui_reply_to_preceding_parent() -> None:
    html = r'''
    <div id="post" componentkey="update-card-focus-post" role="listitem">
      <a href="https://www.linkedin.com/analytics/post-summary/urn:li:activity:7510870387140857856/"><p>analytics</p></a>
      <div data-testid="expandable-text-box">Post body</div>
      <button aria-label="Comment">1</button>
      <div componentkey="CommentComponentReference_urn:li:comment:(activity:7510870387140857856,7510958357751615490)">
        <header><button aria-label="View more options for Parent"></button><a href="https://www.linkedin.com/in/parent/"><p><span aria-hidden="true">Parent</span> • 2nd</p><p>Parent headline</p></a><p>1d</p></header>
        <p>2
        2</p>
        <div data-testid="expandable-text-box">Parent body</div>
      </div>
      <div role="button" id="more-replies">See more replies</div>
    </div>
    <script>
      document.querySelector('#more-replies').addEventListener('click', function () {
        this.insertAdjacentHTML('beforebegin', '<div componentkey="CommentComponentReference_urn:li:comment:(activity:7510870387140857856,7510960000000000000)"><header><button aria-label="View more options for Reply"></button><a href="https://www.linkedin.com/in/reply/"><p><span aria-hidden="true">Reply</span> • 3rd</p><p>Author</p><p>Reply headline</p></a><p>3h</p></header><p>202 impressions</p><div data-testid="expandable-text-box">Reply body</div></div>');
        this.remove();
      });
    </script>
    '''

    async def run() -> tuple[dict[str, object], list[dict[str, object]]]:
        from playwright.async_api import async_playwright

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            page = await browser.new_page()
            await page.set_content(html)
            post = backup.CDPElement(page, "document.querySelector('#post')")
            stats = await backup.load_all_comments(post, max_rounds=5, settle_ms=1)
            rows = await post.evaluate(backup.SDUI_EXTRACT_JS, {"scrapedAt": "2026-10-04T00:00:00+00:00"})
            await browser.close()
            return stats, rows

    stats, rows = asyncio.run(run())
    parent = "urn:li:comment:(activity:7510870387140857856,7510958357751615490)"
    child = "urn:li:comment:(activity:7510870387140857856,7510960000000000000)"
    assert stats["replyClicks"] == 1
    assert stats["replyParents"] == {child: parent}
    assert [row["content"] for row in rows[1:]] == ["Parent body", "Reply body"]
    assert rows[1]["replyCount"] == 2
    assert rows[1]["impressionCount"] is None
    assert rows[2]["commenterType"] == "Author"
    assert rows[2]["commenterDescription"] == "Reply headline"
    assert rows[2]["impressionCount"] == 202


def test_page_cdp_url_requires_linkedin_page_with_websocket(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        return response(
            [
                {"type": "page", "url": "https://evil.test/linkedin.com/", "webSocketDebuggerUrl": "ws://evil"},
                {"type": "service_worker", "url": "https://www.linkedin.com/sw.js", "webSocketDebuggerUrl": "ws://worker"},
                {"type": "page", "url": "https://www.linkedin.com/feed/"},
                {"type": "page", "url": "https://www.linkedin.com/in/test/", "webSocketDebuggerUrl": "ws://linkedin"},
            ]
        )

    monkeypatch.setattr(backup, "urlopen", fake_urlopen)
    assert backup.page_cdp_url("http://localhost:9222") == "ws://linkedin"


def test_keyed_cdp_elements_survive_reordering_and_removal() -> None:
    async def run() -> list[str | None]:
        from playwright.async_api import async_playwright

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            page = await browser.new_page()
            await page.set_content('<main id="root"><div data-urn="urn:li:activity:1"></div><div data-urn="urn:li:activity:2"></div></main>')
            root = backup.CDPElement(page, "document.querySelector('#root')")
            handles = await root.query_selector_all('[data-urn]')
            await page.evaluate("""() => document.querySelector('#root').insertAdjacentHTML('afterbegin', '<div data-urn="urn:li:activity:0"></div>')""")
            first = await handles[0].get_attribute("data-urn")
            await page.evaluate("""() => document.querySelector('[data-urn="urn:li:activity:0"]').remove()""")
            second = await handles[1].get_attribute("data-urn")
            await browser.close()
            return [first, second]

    assert asyncio.run(run()) == ["urn:li:activity:1", "urn:li:activity:2"]


def test_connect_enables_focus_emulation_without_activating_tab(monkeypatch) -> None:
    class FakeSocket:
        def __init__(self) -> None:
            self.methods: list[tuple[str, dict[str, object]]] = []
            self.closed = False
            self.pending: dict[str, object] | None = None

        async def send(self, raw: str) -> None:
            message = json.loads(raw)
            self.pending = message
            self.methods.append((message["method"], message.get("params", {})))

        async def recv(self) -> str:
            assert self.pending is not None
            message = self.pending
            self.pending = None
            if message["method"] == "Runtime.evaluate":
                return json.dumps({"id": message["id"], "result": {"result": {"value": "https://www.linkedin.com/in/test/"}}})
            return json.dumps({"id": message["id"], "result": {}})

        async def close(self) -> None:
            self.closed = True

    socket = FakeSocket()

    async def fake_connect(*_args, **_kwargs):
        return socket

    monkeypatch.setattr(backup, "page_cdp_url", lambda _url: "ws://linkedin")
    monkeypatch.setattr(backup.websockets, "connect", fake_connect)
    monkeypatch.setattr(backup, "urlopen", lambda *_args, **_kwargs: response({"Browser": "Chrome/Test"}))

    async def run() -> None:
        page = await backup.connect_linkedin_page("http://localhost:9222")
        assert page.focus_emulated is True
        await page.close()

    asyncio.run(run())
    methods = [method for method, _params in socket.methods]
    assert methods == ["Runtime.evaluate", "Emulation.setFocusEmulationEnabled", "Emulation.setFocusEmulationEnabled"]
    assert socket.methods[1][1] == {"enabled": True}
    assert socket.methods[2][1] == {"enabled": False}
    assert "Page.bringToFront" not in methods
    assert "Target.activateTarget" not in methods
    assert socket.closed is True


def test_close_closes_socket_even_if_focus_reset_fails(monkeypatch) -> None:
    import pytest

    class FakeSocket:
        def __init__(self) -> None:
            self.closed = False
            self.pending: dict[str, object] | None = None

        async def send(self, raw: str) -> None:
            self.pending = json.loads(raw)

        async def recv(self) -> str:
            assert self.pending is not None
            message = self.pending
            self.pending = None
            if message["method"] == "Runtime.evaluate":
                return json.dumps({"id": message["id"], "result": {"result": {"value": "https://www.linkedin.com/"}}})
            if message["method"] == "Emulation.setFocusEmulationEnabled" and not message["params"]["enabled"]:
                return json.dumps({"id": message["id"], "error": {"message": "reset failed"}})
            return json.dumps({"id": message["id"], "result": {}})

        async def close(self) -> None:
            self.closed = True

    socket = FakeSocket()

    async def fake_connect(*_args, **_kwargs):
        return socket

    monkeypatch.setattr(backup, "page_cdp_url", lambda _url: "ws://linkedin")
    monkeypatch.setattr(backup.websockets, "connect", fake_connect)
    monkeypatch.setattr(backup, "urlopen", lambda *_args, **_kwargs: response({"Browser": "Chrome/Test"}))

    async def run() -> None:
        page = await backup.connect_linkedin_page("http://localhost:9222")
        with pytest.raises(RuntimeError, match="reset failed"):
            await page.close()

    asyncio.run(run())
    assert socket.closed is True


def test_sdui_extracts_videojs_sources_poster_and_duration() -> None:
    async def run() -> list[dict[str, object]]:
        from playwright.async_api import async_playwright

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            page = await browser.new_page()
            await page.route("**/*", lambda route: route.abort())
            await page.set_content(
                '<div id="post"><div data-vjs-player="true"><video poster="https://media.example/poster.jpg"></video></div></div>'
            )
            await page.evaluate(
                """() => document.querySelector('[data-vjs-player]').player = {
                    currentSources: () => [
                      {src: 'blob:https://www.linkedin.com/temp', type: 'video/mp4'},
                      {src: 'data:video/mp4;base64,temporary', type: 'video/mp4'},
                      {src: 'https://media.example/video.m3u8', type: 'application/x-mpegURL'},
                      {src: 'https://media.example/video.mp4', type: 'video/mp4'}
                    ], poster: () => 'https://media.example/poster-large.jpg', duration: () => 42
                }"""
            )
            post = backup.CDPElement(page, "document.querySelector('#post')")
            rows = await post.evaluate(
                backup.SDUI_EXTRACT_JS,
                {"scrapedAt": "2026-10-04T00:00:00+00:00", "postUrn": "urn:li:activity:1"},
            )
            await browser.close()
            return rows

    media = asyncio.run(run())[0]["media"]
    assert media == [
        {
            "kind": "video",
            "url": "https://media.example/video.mp4",
            "sources": [
                {"url": "https://media.example/video.m3u8", "type": "application/x-mpegURL"},
                {"url": "https://media.example/video.mp4", "type": "video/mp4"},
            ],
            "poster": "https://media.example/poster-large.jpg",
            "duration": 42,
        }
    ]


def test_sdui_extracts_repost_actor_and_supplied_urn() -> None:
    async def run() -> dict[str, object]:
        from playwright.async_api import async_playwright

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            page = await browser.new_page()
            await page.route("**/*", lambda route: route.abort())
            await page.set_content(
                '''<div id="post">
                  <div data-sdui-anchor-id="feed-header-repost"><a href="https://www.linkedin.com/in/reposter/"><span>Reposter</span></a></div>
                  <header><button aria-label="Open control menu for post"></button><a href="https://www.linkedin.com/in/author/"><p><span aria-hidden="true">Author</span></p></a><p>Author headline</p><p>1h</p><span aria-label="Visibility: Anyone"></span></header>
                  <div data-testid="expandable-text-box">Reposted content</div>
                </div>'''
            )
            post = backup.CDPElement(page, "document.querySelector('#post')")
            rows = await post.evaluate(
                backup.SDUI_EXTRACT_JS,
                {"scrapedAt": "2026-10-04T00:00:00+00:00", "postUrn": "urn:li:activity:999"},
            )
            await browser.close()
            return rows[0]

    row = asyncio.run(run())
    assert row["id"] == "urn:li:activity:999"
    assert row["repostedBy"] == "Reposter"
    assert row["repostedByProfile"] == "https://www.linkedin.com/in/reposter/"


def test_resolve_post_urn_captures_permalink_without_touching_clipboard(monkeypatch) -> None:
    class RedirectResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def geturl(self):
            return "https://www.linkedin.com/feed/update/urn:li:activity:123456/"

    requests: list[tuple[str, str, int]] = []

    def fake_urlopen(request, timeout):
        requests.append((request.get_method(), request.full_url, timeout))
        return RedirectResponse()

    monkeypatch.setattr(backup, "urlopen", fake_urlopen)

    async def run() -> tuple[str, int, bool]:
        from playwright.async_api import async_playwright

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            page = await browser.new_page()
            await page.route("**/*", lambda route: route.abort())
            await page.set_content(
                '''<div id="post"><button aria-label="Open control menu for post"></button></div>
                <script>
                  window.originalCalls = 0;
                  const original = async value => { window.originalCalls++; return value; };
                  Object.defineProperty(navigator, 'clipboard', {configurable: true, value: {writeText: original}});
                  window.originalWriteText = navigator.clipboard.writeText;
                  document.querySelector('button').onclick = () => {
                    const p = document.createElement('p'); p.textContent = 'Copy link to post';
                    p.onclick = () => navigator.clipboard.writeText('https://lnkd.in/short');
                    document.body.append(p);
                  };
                </script>'''
            )
            post = backup.CDPElement(page, "document.querySelector('#post')")
            urn = await backup.resolve_post_urn(post, settle_ms=1)
            original_calls = await page.evaluate("() => window.originalCalls")
            restored = await page.evaluate("() => navigator.clipboard.writeText === window.originalWriteText")
            await browser.close()
            return urn, original_calls, restored

    urn, original_calls, restored = asyncio.run(run())
    assert urn == "urn:li:activity:123456"
    assert original_calls == 0
    assert restored is True
    assert requests == [("HEAD", "https://lnkd.in/short", 10)]


def test_post_ugc_js_returns_unique_react_reaction_state_id() -> None:
    async def run() -> tuple[str, str]:
        from playwright.async_api import async_playwright

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            page = await browser.new_page()
            await page.route("**/*", lambda route: route.abort())
            await page.set_content('<div id="post"><button aria-label="Reaction button state: no reaction"></button></div>')
            await page.evaluate(
                """() => {
                  const button = document.querySelector('button');
                  button.__reactFiberTest = {
                    memoizedProps: {triggers: [{value: 'reactionState-urn:li:ugcPost:7415738265976221696'}]},
                    pendingProps: {}, return: null, stateNode: document.querySelector('#post')
                  };
                }"""
            )
            post = backup.CDPElement(page, "document.querySelector('#post')")
            unique = await post.evaluate(backup.POST_UGC_JS)
            await page.evaluate(
                """() => document.querySelector('button').__reactFiberTest.memoizedProps.triggers.push({value: 'reactionState-urn:li:ugcPost:9999999999999999999'})"""
            )
            ambiguous = await post.evaluate(backup.POST_UGC_JS)
            await browser.close()
            return unique, ambiguous

    assert asyncio.run(run()) == (
        "urn:li:ugcPost:7415738265976221696",
        "",
    )


def test_resolve_post_urn_uses_verified_ugc_parent_before_clipboard() -> None:
    class FakePost:
        def __init__(self) -> None:
            self.expressions: list[str] = []

        async def evaluate(self, expression, arg=...):
            self.expressions.append(expression)
            if expression == backup.POST_ID_JS:
                return ""
            if expression == backup.POST_UGC_JS:
                return "urn:li:ugcPost:7415738265976221696"
            raise AssertionError(f"clipboard fallback should not run: {expression}")

    post = FakePost()
    result = asyncio.run(
        backup.resolve_post_urn(
            post,
            settle_ms=1,
            known_ugc_parents={
                "urn:li:ugcPost:7415738265976221696": "urn:li:activity:7415939374598602752"
            },
        )
    )
    assert result == "urn:li:activity:7415939374598602752"
    assert post.expressions == [backup.POST_ID_JS, backup.POST_UGC_JS]


def test_apply_reply_parents_links_new_and_previously_visible_siblings() -> None:
    parent = "urn:li:comment:(activity:1,10)"
    new_child = "urn:li:comment:(activity:1,11)"
    visible_child = "urn:li:comment:(activity:1,12)"
    rows = [
        {"type": "comment", "id": parent, "replyCount": 2, "parentCommentId": ""},
        {"type": "comment", "id": new_child, "replyCount": None, "parentCommentId": ""},
        {"type": "comment", "id": visible_child, "replyCount": None, "parentCommentId": ""},
    ]

    backup.apply_reply_parents(rows, {new_child: parent})

    assert [row["parentCommentId"] for row in rows] == ["", parent, parent]


def test_apply_reply_parents_does_not_guess_without_observed_mapping() -> None:
    parent = "urn:li:comment:(activity:1,20)"
    rows = [
        {"type": "comment", "id": parent, "replyCount": 2, "parentCommentId": ""},
        {"type": "comment", "id": "urn:li:comment:(activity:1,21)", "replyCount": None, "parentCommentId": ""},
        {"type": "comment", "id": "urn:li:comment:(activity:1,22)", "replyCount": None, "parentCommentId": ""},
    ]

    backup.apply_reply_parents(rows, {})

    assert all(not row["parentCommentId"] for row in rows)


def test_apply_reply_parents_does_not_assign_unrelated_adjacent_comments() -> None:
    parent = "urn:li:comment:(activity:1,30)"
    mapped_child = "urn:li:comment:(activity:1,33)"
    rows = [
        {"type": "comment", "id": parent, "replyCount": 2, "parentCommentId": ""},
        {"type": "comment", "id": "urn:li:comment:(activity:1,31)", "replyCount": None, "parentCommentId": ""},
        {"type": "comment", "id": "urn:li:comment:(activity:1,32)", "replyCount": None, "parentCommentId": ""},
        {"type": "comment", "id": mapped_child, "replyCount": None, "parentCommentId": ""},
    ]

    backup.apply_reply_parents(rows, {mapped_child: parent})

    assert rows[1]["parentCommentId"] == ""
    assert rows[2]["parentCommentId"] == ""
    assert rows[3]["parentCommentId"] == parent
