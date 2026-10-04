#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["typer>=0.12", "websockets>=15"]
# ///
"""Back up LinkedIn data that the standard export misses via CDP.

Examples:
  backuplinkedin.py posts --username sanand0 --limit 5
  backuplinkedin.py posts --username sanand0 --limit 100 --format jsonl | moor
  backuplinkedin.py posts --username sanand0 --limit 0 --max-scrolls 1000
  backuplinkedin.py posts --username sanand0 --no-comments --dry-run
  backuplinkedin.py --describe | jaq .
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

import typer
import websockets

import sanand_observability as obs

app = typer.Typer(add_completion=False, help=__doc__)

CDP_URL = "http://localhost:9222"
OUT_PATH = Path.home() / "Documents/data/linkedin-posts.jsonl"
POST_SELECTORS = ('[data-urn][role="article"], .feed-shared-update-v2[data-urn]', '[componentkey^="update-card-focus"][role="listitem"]')
POST_SELECTOR = ", ".join(POST_SELECTORS)
COMMENT_SELECTOR = 'article.comments-comment-entity[data-id], [componentkey^="CommentComponentReference_urn:li:comment:"]'
POST_ID_JS = r"""el => el?.getAttribute('data-urn') ||
  (el?.querySelector('a[href*="/analytics/post-summary/"], a[href*="/feed/update/urn:li:activity:"]')?.href.match(/urn:li:activity:\d+/) || [])[0] || ''"""
POST_UGC_JS = r"""post => {
  const button = post.querySelector('button[aria-label^="Reaction button state:"]');
  let fiber = button && button[Object.keys(button).find(k => k.startsWith('__reactFiber'))];
  const ids = new Set(), seen = new WeakSet();
  let visited = 0;
  const scan = (value, depth=0) => {
    if (typeof value === 'string') {
      const m = value.match(/^reactionState-(urn:li:ugcPost:\d+)$/);
      if (m) ids.add(m[1]);
    } else if (value && typeof value === 'object' && depth < 14 && visited++ < 5000 && !seen.has(value)) {
      seen.add(value);
      for (const [key, child] of Object.entries(value))
        if (!['children', '_owner', 'return', 'stateNode'].includes(key)) scan(child, depth+1);
    }
  };
  for (let i=0; fiber && i<30; i++, fiber=fiber.return) {
    scan(fiber.memoizedProps); scan(fiber.pendingProps);
    if (fiber.stateNode === post) break;
  }
  return ids.size === 1 ? [...ids][0] : '';
}"""


def selector_expression(root: str, selector: str) -> str:
    """Return a DOM expression supporting Playwright's simple :has-text form."""
    return rf"""((root, selector) => {{
      const rows = [];
      for (const part of selector.split(/,\s*/)) {{
        const text = part.match(/:has-text\(\"([^\"]*)\"\)/)?.[1];
        const css = part.replace(/:has-text\(\"[^\"]*\"\)/g, "");
        for (const item of root.querySelectorAll(css))
          if (!text || (item.innerText || item.textContent || "").includes(text)) rows.push(item);
      }}
      return [...new Set(rows)];
    }})({root}, {compact_json(selector)})"""


class _UnsupportedLocator:
    async def aria_snapshot(self, timeout: int = 0) -> str:
        raise NotImplementedError("ARIA snapshots are unavailable through direct CDP")


class CDPPage:
    """Small page-target CDP client that does not attach every browser tab."""

    def __init__(self, socket: Any, url: str, browser_version: str) -> None:
        self.socket = socket
        self.url = url
        self.browser_version = browser_version
        self.command_id = 0
        self.focus_emulated = False

    async def command(self, method: str, **params: Any) -> dict[str, Any]:
        self.command_id += 1
        command_id = self.command_id
        await self.socket.send(compact_json({"id": command_id, "method": method, "params": params}))
        async with asyncio.timeout(30):
            while True:
                response = json.loads(await self.socket.recv())
                if response.get("id") != command_id:
                    continue
                if response.get("error"):
                    raise RuntimeError(f"CDP {method}: {response['error'].get('message', response['error'])}")
                return response.get("result") or {}

    async def evaluate(self, expression: str, arg: Any = ...) -> Any:
        source = f"({expression})()" if arg is ... else f"({expression})({compact_json(arg)})"
        result = await self.command("Runtime.evaluate", expression=source, awaitPromise=True, returnByValue=True, userGesture=True)
        if details := result.get("exceptionDetails"):
            raise RuntimeError((details.get("exception") or {}).get("description") or details.get("text"))
        return (result.get("result") or {}).get("value")

    async def goto(self, url: str, **_: Any) -> None:
        await self.command("Page.navigate", url=url)
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            state = await self.evaluate("() => ({ ready: document.readyState, url: location.href })")
            self.url = state["url"]
            if state["ready"] in {"interactive", "complete"}:
                return
            await asyncio.sleep(0.1)
        raise TimeoutError(f"navigation did not settle within 45s: {url}")

    async def wait_for_selector(self, selector: str, timeout: int) -> None:
        deadline = time.monotonic() + timeout / 1000
        while time.monotonic() < deadline:
            if await self.evaluate("selector => Boolean(document.querySelector(selector))", selector):
                return
            await asyncio.sleep(0.1)
        raise TimeoutError(f"selector not found after {timeout}ms: {selector}")

    async def query_selector_all(self, selector: str) -> list[CDPElement]:
        return await CDPElement(self, "document").query_selector_all(selector)

    async def wait_for_timeout(self, timeout: int) -> None:
        await asyncio.sleep(timeout / 1000)

    async def title(self) -> str:
        return await self.evaluate("() => document.title")

    async def version(self) -> str:
        return self.browser_version

    def locator(self, selector: str) -> _UnsupportedLocator:
        return _UnsupportedLocator()

    def on(self, event: str, callback: Any) -> None:
        return None

    async def close(self) -> None:
        try:
            if self.focus_emulated:
                await self.command("Emulation.setFocusEmulationEnabled", enabled=False)
                self.focus_emulated = False
        finally:
            await self.socket.close()


class CDPElement:
    def __init__(self, page: CDPPage, expression: str) -> None:
        self.page = page
        self.expression = expression

    async def evaluate(self, expression: str, arg: Any = ...) -> Any:
        suffix = "" if arg is ... else f",{compact_json(arg)}"
        return await self.page.evaluate(f"() => ({expression})({self.expression}{suffix})")

    async def query_selector_all(self, selector: str) -> list[CDPElement]:
        expression = selector_expression(self.expression, selector)
        identities = await self.page.evaluate(f"""() => ({expression}).map(el => {{
          const attr = ['data-urn', 'data-id', 'componentkey', 'id'].find(a => el.getAttribute(a));
          return attr ? [attr, el.getAttribute(attr)] : null;
        }})""")
        # Pin keyed elements: indexes change when cards/replies are inserted or recycled.
        return [CDPElement(self.page, f"({expression}).find(el => el.getAttribute({compact_json(key[0])}) === {compact_json(key[1])})" if key else f"({expression})[{index}]") for index, key in enumerate(identities)]

    async def get_attribute(self, name: str) -> str | None:
        return await self.evaluate("(el, name) => el.getAttribute(name)", name)

    async def click(self, **_: Any) -> None:
        # Mouse dispatch can succeed without delivering events to a hidden SDUI tab.
        # These controls only expand/read content; DOM clicks work without activation.
        await self.evaluate("el => el.click()")

    async def scroll_into_view_if_needed(self, **_: Any) -> None:
        await self.evaluate("el => el.scrollIntoView({ block: 'center', inline: 'nearest' })")


def eprint(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def page_cdp_url(cdp_url: str) -> str:
    """Resolve one LinkedIn page target to avoid attaching every open browser tab."""
    if cdp_url.startswith("ws"):
        return cdp_url
    base = cdp_url.rstrip("/")
    targets = json.load(urlopen(f"{base}/json/list", timeout=5))
    target = next(
        (
            item
            for item in targets
            if item.get("type") == "page"
            and urlparse(item.get("url", "")).hostname in {"linkedin.com", "www.linkedin.com"}
            and item.get("webSocketDebuggerUrl")
        ),
        None,
    )
    if target is None:
        request = Request(
            f"{base}/json/new?{quote('https://www.linkedin.com/', safe=':/')}",
            method="PUT",
        )
        target = json.load(urlopen(request, timeout=5))
    return target["webSocketDebuggerUrl"]


async def connect_linkedin_page(cdp_url: str) -> CDPPage:
    direct_url = await asyncio.to_thread(page_cdp_url, cdp_url)
    base = cdp_url.rstrip("/")
    version = {}
    if cdp_url.startswith("http"):
        version = await asyncio.to_thread(lambda: json.load(urlopen(f"{base}/json/version", timeout=5)))
    socket = await websockets.connect(direct_url, max_size=None, open_timeout=10)
    page = CDPPage(socket, "", version.get("Browser") or "")
    try:
        page.url = await page.evaluate("() => location.href")
        # SDUI defers infinite-scroll rendering in hidden tabs. Emulation resumes it
        # without Page.bringToFront/Target.activateTarget or changing the selected tab.
        await page.command("Emulation.setFocusEmulationEnabled", enabled=True)
        page.focus_emulated = True
    except Exception:
        await page.close()
        raise
    return page


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


COUNT_RE = re.compile(
    r"^\s*(\d[\d,]*(?:\.\d+)?)(?:[ \t]*([kmb]))?(?=\s|$)", re.IGNORECASE
)


def parse_count(value: str) -> int | None:
    """Parse a leading count without treating a following name as a K/M/B suffix."""
    match = COUNT_RE.match(value or "")
    if not match:
        return None
    scale = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}.get(
        (match.group(2) or "").lower(), 1
    )
    return round(float(match.group(1).replace(",", "")) * scale)


def linkedin_id_datetime(value: str) -> dt.datetime | None:
    """Decode the exact timestamp embedded in a LinkedIn activity or comment ID."""
    match = re.search(r"(?:activity:|,|^)(\d{16,})(?:\)|$)", value or "")
    if not match:
        return None
    timestamp = dt.datetime.fromtimestamp((int(match.group(1)) >> 22) / 1000, dt.UTC)
    earliest = dt.datetime(2010, 1, 1, tzinfo=dt.UTC)
    return timestamp if earliest <= timestamp <= now_utc() + dt.timedelta(days=1) else None


def labeled_count(value: str, label: str) -> int | None:
    match = re.search(
        rf"(?:^|\n)([\d,.]+(?:\.\d+)?(?:[ \t]*[kmb])?)\s+{label}s?\b",
        value or "",
        re.IGNORECASE,
    )
    return parse_count(match.group(1)) if match else None


def normalize_counts(row: dict[str, Any]) -> dict[str, Any]:
    """Re-parse raw count text so selector quirks cannot silently inflate metrics."""
    if row.get("type") == "post":
        social = str(row.get("socialText") or "")
        if social:
            reaction = parse_count(social)
            if reaction is not None:
                row["reactionCount"] = reaction
            row["commentCount"] = labeled_count(social, "comment") or 0
            row["repostCount"] = labeled_count(social, "repost") or 0
    else:
        reaction = parse_count(str(row.get("reactionText") or ""))
        if reaction is not None:
            row["reactionCount"] = reaction
    return row


def parse_relative_time(value: str, scraped_at: dt.datetime) -> tuple[str, str]:
    text = re.sub(r"\s+", " ", value or "").strip().lower()
    text = text.replace("• edited", "").replace("edited •", "").strip(" •")
    if not text:
        return "", "missing"
    if match := re.search(r"\b(\d+)\s*(min|m|hour|hr|h|day|d|week|w|month|mo|year|yr|y)s?\b", text):
        amount = int(match.group(1))
        unit = match.group(2)
        days = {"week": 7, "w": 7, "month": 30, "mo": 30, "year": 365, "yr": 365, "y": 365}
        if unit in {"min", "m"}:
            delta = dt.timedelta(minutes=amount)
        elif unit in {"hour", "hr", "h"}:
            delta = dt.timedelta(hours=amount)
        elif unit in {"day", "d"}:
            delta = dt.timedelta(days=amount)
        else:
            delta = dt.timedelta(days=amount * days[unit])
        return (scraped_at - delta).isoformat(), "relative"
    if "yesterday" in text:
        return (scraped_at - dt.timedelta(days=1)).isoformat(), "relative"
    return "", "unparsed"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{time.time_ns()}.tmp")
    tmp.write_text("".join(compact_json(row) + "\n" for row in rows))
    tmp.replace(path)


def row_key(row: dict[str, Any]) -> str:
    return f"{row.get('type', 'row')}:{row.get('id') or row.get('url') or compact_json(row)[:160]}"


LATEST_FIELDS = {
    "commentCount",
    "commentScrapeStats",
    "commentedText",
    "edited",
    "impressionCount",
    "postedText",
    "rawText",
    "reactionCount",
    "reactionText",
    "replyCount",
    "repostCount",
    "scrapedAt",
    "socialText",
    "visibility",
    "reactedByAuthor",
}
TIME_FIELDS = {"postedAt", "postedAtConfidence", "commentedAt", "commentedAtConfidence"}


def richness(value: Any) -> int:
    if value in (None, "", [], {}, False):
        return 0
    if isinstance(value, str):
        return len(value)
    if isinstance(value, (list, dict)):
        return len(value)
    return 1


def merge_row(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """Keep rich identity data, but let newer snapshot values decrease or reach zero."""
    merged = dict(old)
    for key, value in new.items():
        if key in TIME_FIELDS:
            continue
        if key in LATEST_FIELDS:
            if value is not None:
                merged[key] = value
        elif richness(value) >= richness(merged.get(key)):
            merged[key] = value
    for prefix in ("postedAt", "commentedAt"):
        confidence = f"{prefix}Confidence"
        if (
            new.get(prefix)
            and (new.get(confidence) == "id" or merged.get(confidence) != "id")
        ):
            merged[prefix] = new[prefix]
            merged[confidence] = new.get(confidence)
    return merged


def sort_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (str(row.get("postedAt") or row.get("commentedAt") or ""), str(row.get("type") or ""), str(row.get("id") or ""))


def update_jsonl(path: Path, rows: list[dict[str, Any]]) -> int:
    existing = {row_key(row): row for row in load_jsonl(path)}
    changed = 0
    for row in rows:
        key = row_key(row)
        merged = merge_row(existing.get(key, {}), row)
        if existing.get(key) != merged:
            changed += 1
        existing[key] = merged
    write_jsonl(path, sorted(existing.values(), key=sort_key, reverse=True))
    return changed


def add_time_fields(row: dict[str, Any], scraped_at: dt.datetime) -> dict[str, Any]:
    if row["type"] == "post":
        exact = linkedin_id_datetime(str(row.get("postId") or row.get("id") or ""))
        when, confidence = (
            (exact.isoformat(), "id")
            if exact
            else parse_relative_time(row.get("postedText", ""), scraped_at)
        )
        row["postedAt"] = when
        row["postedAtConfidence"] = confidence
    else:
        exact = linkedin_id_datetime(str(row.get("commentId") or row.get("id") or ""))
        when, confidence = (
            (exact.isoformat(), "id")
            if exact
            else parse_relative_time(row.get("commentedText", ""), scraped_at)
        )
        row["commentedAt"] = when
        row["commentedAtConfidence"] = confidence
    row["scrapedAt"] = scraped_at.isoformat()
    return row


def describe() -> dict[str, Any]:
    return {
        "name": "backuplinkedin.py",
        "cdp": CDP_URL,
        "commands": ["posts"],
        "output": str(OUT_PATH),
        "primary_key": "type:id",
        "examples": [
            "backuplinkedin.py posts --username sanand0",
            "backuplinkedin.py posts --username sanand0 --limit 100 --format jsonl",
            "backuplinkedin.py posts --username sanand0 --limit 0 --max-scrolls 1000",
            "backuplinkedin.py posts --username sanand0 --no-comments --dry-run",
        ],
    }


async def navigate_posts(page: CDPPage, username: str) -> None:
    await page.goto(f"https://www.linkedin.com/in/{username}/recent-activity/all/", wait_until="domcontentloaded", timeout=45000)
    await page.wait_for_timeout(3500)
    if "login" in page.url or "Sign in" in await page.title():
        raise RuntimeError("LinkedIn is not authenticated in the CDP browser. Log in manually, then rerun.")
    await page.wait_for_selector(POST_SELECTOR, timeout=20000)


async def resolve_post_urn(post: CDPElement, settle_ms: int, known_ugc_parents: dict[str, str] | None = None) -> str:
    """Read a permalink for reposts whose SDUI cards expose no analytics/activity link."""
    if urn := await post.evaluate(POST_ID_JS):
        return urn
    ugc = await post.evaluate(POST_UGC_JS)
    if ugc and (known_ugc_parents or {}).get(ugc):
        return known_ugc_parents[ugc]
    # Popovers opened offscreen do not expose their menu items in the SDUI DOM.
    await post.scroll_into_view_if_needed()
    await post.page.wait_for_timeout(settle_ms)
    url = await post.evaluate(r"""async el => {
      const menu = el.querySelector('button[aria-label^="Open control menu"]');
      if (!menu) return '';
      if (menu.getAttribute('aria-expanded') !== 'true') menu.click();
      let label;
      for (let i=0; i<40 && !label; i++) {
        label = [...document.querySelectorAll('p')].find(el => el.innerText === 'Copy link to post');
        if (!label) await new Promise(r => setTimeout(r,50));
      }
      if (!label) return '';
      // Capture the site's permalink without reading or modifying the user's clipboard.
      const clipboard = navigator.clipboard;
      const prior = Object.getOwnPropertyDescriptor(clipboard, 'writeText');
      let copied = '';
      Object.defineProperty(clipboard, 'writeText', {configurable:true, value:async value => {copied=value;}});
      try {
        label.click();
        for (let i=0; i<400 && !copied; i++) await new Promise(r => setTimeout(r,50));
        return copied;
      } finally {
        if (prior) Object.defineProperty(clipboard, 'writeText', prior);
        else delete clipboard.writeText;
      }
    }""")
    if urlparse(url).hostname == "lnkd.in":
        def redirect_url() -> str:
            with urlopen(Request(url, method="HEAD"), timeout=10) as response:
                return response.geturl()
        url = await asyncio.to_thread(redirect_url)
    if urlparse(url).hostname not in {"linkedin.com", "www.linkedin.com"}:
        return ""
    match = re.search(r"urn:li:activity:(\d+)", url)
    return match[0] if match else ""


async def click_all(handles: list[CDPElement], label: str, settle_ms: int) -> int:
    clicked = 0
    for handle in handles:
        if not await handle.evaluate("el => Boolean(el)"):
            continue
        try:
            await handle.evaluate("(el) => el.scrollIntoView({ block: 'center', inline: 'nearest', behavior: 'instant' })")
            # Deliver queued scroll events before opening a popover; SDUI closes it on scroll.
            await asyncio.sleep(0.1)
            await handle.click(timeout=800, force=True, no_wait_after=True)
            clicked += 1
            await asyncio.sleep(settle_ms / 1000)
        except Exception as exc:
            eprint(f"warning: could not click {label}: {exc}")
    return clicked


async def expand_text(post: CDPElement, settle_ms: int) -> None:
    handles = await post.query_selector_all(
        'button[aria-label^="see more"], button[aria-label*="visually reveals content"], '
        'button.see-more, button:has-text("… more"), button:has-text("... more"), '
        'button[data-testid="expandable-text-button"]:has-text("more"), '
        '.feed-shared-inline-show-more-text__see-more-less-toggle'
    )
    await click_all(handles[:12], "see-more", settle_ms)


async def open_comments(post: CDPElement, settle_ms: int) -> None:
    if await post.query_selector_all('[componentkey^="commentsSectionContainer"]'):
        return
    buttons = await post.query_selector_all('button[aria-label="Comment"], button.comment-button, [aria-label*="comments on"]')
    await click_all(buttons[:1], "comments", settle_ms)


async def load_all_comments(post: CDPElement, max_rounds: int, settle_ms: int) -> dict[str, Any]:
    stats: dict[str, Any] = {"loadMoreClicks": 0, "replyClicks": 0, "staleRounds": 0, "replyParents": {}}
    expected = await post.evaluate("el => el.querySelector('button[aria-label=\"Comment\"]')?.innerText || ''")
    expected_count = parse_count(expected) or 0
    stats["expectedComments"] = expected_count
    # LinkedIn describes "Most recent" as showing all comments; relevance can filter them.
    sort_attempted = False
    previous = -1
    for _ in range(max_rounds):
        if not sort_attempted:
            sorters = await post.query_selector_all('button:has-text("Most relevant"), [role="button"]:has-text("Most relevant")')
            if sorters:
                sort_attempted = True
                await click_all(sorters[:1], "comment-sort", settle_ms)
                options = await post.page.query_selector_all('[role="menuitem"]:has-text("Most recent")')
                stats["sortClicks"] = await click_all(options[:1], "most-recent-comments", settle_ms * 2)
        await expand_text(post, settle_ms)
        comments = await post.query_selector_all(COMMENT_SELECTOR)
        load_buttons = await post.query_selector_all(
            'button:has-text("Load more comments"), button:has-text("Show more comments"), '
            'button:has-text("See previous comments"), button:has-text("Load previous comments"), '
            '[role="button"]:has-text("Load more comments"), [role="button"]:has-text("Show more comments"), '
            '[role="button"]:has-text("See previous comments"), [role="button"]:has-text("Load previous comments"), '
            '[componentkey*="-replaceableLoadMoreComments"] [role="button"]'
        )
        reply_buttons = await post.query_selector_all(
            'button:has-text("See previous replies"), button:has-text("Load more replies"), button:has-text("Show replies"), '
            '[role="button"]:has-text("See previous replies"), [role="button"]:has-text("Load more replies"), [role="button"]:has-text("Show replies"), '
            'button:has-text("See more replies"), [role="button"]:has-text("See more replies"), '
            '[componentkey*="-replaceableLoadMoreReplies"] [role="button"]'
        )
        stats["loadMoreClicks"] += await click_all(load_buttons[:3], "load-more-comments", settle_ms)
        if not load_buttons:
            for button in reply_buttons[:5]:
                # SDUI replies are siblings, not descendants of the parent comment.
                # The explicit reply loader follows its parent; record newly expanded IDs.
                parent = await button.evaluate(r"""el => {
                  if (!el) return '';
                  const selector = '[componentkey^="CommentComponentReference_urn:li:comment:"]';
                  const card = el.closest('[componentkey^="update-card-focus"]');
                  const article = el.closest(selector) || [...(card?.querySelectorAll(selector) || [])]
                    .filter(c => c.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING).at(-1);
                  return article?.getAttribute('componentkey').replace('CommentComponentReference_', '') || '';
                }""")
                before_ids = {await c.get_attribute("componentkey") for c in await post.query_selector_all(COMMENT_SELECTOR)}
                stats["replyClicks"] += await click_all([button], "load-more-replies", settle_ms)
                if parent:
                    parent = stats["replyParents"].get(parent, parent)
                    # Allow async reply hydration; do not assign unrelated load-more comments.
                    for _ in range(5):
                        await asyncio.sleep(settle_ms / 1000)
                        for comment in await post.query_selector_all(COMMENT_SELECTOR):
                            key = await comment.get_attribute("componentkey")
                            if key and key not in before_ids:
                                stats["replyParents"][key.removeprefix("CommentComponentReference_")] = parent
        count = len(comments)
        remaining_buttons = len(load_buttons) + len(reply_buttons)
        if count == previous:
            stats["staleRounds"] += 1
        else:
            stats["staleRounds"] = 0
        if not remaining_buttons and stats["staleRounds"] >= (10 if count < expected_count else 5):
            break
        if remaining_buttons and stats["staleRounds"] >= 3:
            eprint("warning: comment loader buttons remain visible but no new comment rows appeared; moving on")
            break
        previous = count
        await asyncio.sleep(settle_ms / 1000)
    stats["commentsLoaded"] = len(await post.query_selector_all(COMMENT_SELECTOR))
    stats["remainingLoaders"] = await post.evaluate(r"""el => [...el.querySelectorAll('button, [role="button"]')]
      .filter(b => /^(Load|Show|See).*?(comments|replies)$/i.test(b.innerText.trim())).length""")
    return stats


EXTRACT_JS = r"""
(post, { scrapedAt }) => {
  const text = (el) => (el?.innerText || el?.textContent || "").replace(/\s+\n/g, "\n").replace(/[ \t]+/g, " ").trim();
  const cleanUrl = (url) => {
    try {
      const value = new URL(url, location.href);
      value.hash = "";
      return value.href;
    } catch {
      return url || "";
    }
  };
  const number = (value) => {
    const match = String(value || "").match(/^\s*(\d[\d,]*(?:\.\d+)?)(?:[ \t]*([kmb]))?(?=\s|$)/i);
    if (!match) return null;
    const scale = { k: 1e3, m: 1e6, b: 1e9 }[(match[2] || "").toLowerCase()] || 1;
    return Math.round(Number(match[1].replace(/,/g, "")) * scale);
  };
  const miniProfileUrn = (link) => {
    if (!link?.href) return "";
    try {
      return new URL(link.href, location.href).searchParams.get("miniProfileUrn") || "";
    } catch {
      return "";
    }
  };
  const badgesFrom = (value) => {
    const badges = [];
    if (/\bverified\b/i.test(value || "")) badges.push("verified");
    if (/\bpremium\b/i.test(value || "")) badges.push("premium");
    return [...new Set(badges)];
  };
  const degreeFrom = (value) => {
    const match = String(value || "").match(/\b(1st|2nd|3rd\+?)\b/i);
    return match ? match[1] : "";
  };
  const first = (root, selectors) => selectors.map((s) => root.querySelector(s)).find(Boolean) || null;
  const all = (root, selectors) => [...new Set(selectors.flatMap((s) => [...root.querySelectorAll(s)]))];
  const ariaText = (root) => all(root, ['[aria-label]']).map((el) => el.getAttribute("aria-label") || "").join(" ");
  const visibleText = (root, selectors) => text(first(root, selectors.map((s) => `${s} [aria-hidden="true"]`)) || first(root, selectors));
  const urn = post.getAttribute("data-urn") || "";
  const lines = text(post).split("\n").map((line) => line.trim()).filter(Boolean);
  const profile = first(post, ['a[href*="/in/"]']);
  const authorName = visibleText(post, ['.update-components-actor__name', '.feed-shared-actor__name', 'span.update-components-actor__title']) || lines[1] || "";
  const headline = visibleText(post, ['.update-components-actor__description', '.feed-shared-actor__description']);
  const commentary = text(first(post, ['.update-components-update-v2__commentary', '.feed-shared-update-v2__description-wrapper', '.feed-shared-inline-show-more-text']));
  const ageEl = first(post, ['.update-components-actor__sub-description span[aria-hidden="true"]', '.feed-shared-actor__sub-description span[aria-hidden="true"]']);
  const ageText = text(ageEl) || (lines.find((line) => /^\d+\s*(m|min|h|hr|d|w|mo|y|yr)\b/i.test(line)) || "");
  const socialText = text(first(post, ['.social-details-social-counts', '.feed-shared-social-counts']));
  const reactionText = text(first(post, ['.social-details-social-counts__reactions-count', '[aria-label*="reactions"], [aria-label*="others"]']));
  const commentText = (socialText.match(/[\d,.]+\s*[kmb]?\s+comments?/i) || [""])[0];
  const repostText = (socialText.match(/[\d,.]+\s*[kmb]?\s+reposts?/i) || [""])[0];
  const impressionText = (text(post).match(/[\d,.]+\s*[kmb]?\s+impressions?/i) || [""])[0];
  const hasSocialCounts = Boolean(first(post, ['.social-details-social-counts', '.feed-shared-social-counts']));
  const reactionCount = number(socialText.split("\n")[0]) ?? number(reactionText);
  const analytics = first(post, ['a.analytics-entry-point[href]', 'a[href*="/analytics/post-summary/"]']);
  const actor = first(post, ['.update-components-actor', '.feed-shared-actor']);
  const actorText = `${text(actor)} ${ariaText(actor || post)}`;
  const reactionTypesVisible = [...new Set(all(post, [
    '.social-details-social-counts img[alt]',
    '.feed-shared-social-counts img[alt]',
    '.social-detail-social-counts__count-icon[alt]',
    '.reactions-icon[alt]',
  ]).map((img) => (img.alt || "").trim().toLowerCase()).filter((alt) => alt && !/profile|photo|graphic/i.test(alt)))];
  const links = all(post, ['.update-components-update-v2__commentary a[href]', '.feed-shared-update-v2__description-wrapper a[href]', '.update-components-article a[href]'])
    .map((a) => cleanUrl(a.href))
    .filter((href) => href && !href.includes('/feed/update/') && !href.startsWith('javascript:'));
  const mediaMap = new Map();
  const addMedia = (item) => {
    if (!item.url || item.url.startsWith("data:")) return;
    mediaMap.set(`${item.kind}:${item.url}`, item);
  };
  all(post, ['img[src]']).forEach((img) => {
    if (img.closest('.update-components-actor, .feed-shared-actor, .comments-comment-meta__container')) return;
    if (/profile photo/i.test(img.alt || "")) return;
    const url = cleanUrl(img.src);
    if (/static\.licdn\.com\/aero-v1\/sc\//.test(url) || /profile-displayphoto/.test(url)) return;
    addMedia({ kind: "image", url, alt: img.alt || "" });
  });
  all(post, ['video[src]']).forEach((video) => addMedia({ kind: "video", url: cleanUrl(video.src), poster: cleanUrl(video.poster || "") }));
  all(post, ['iframe[src], object[data], embed[src]']).forEach((el) => addMedia({ kind: "document", url: cleanUrl(el.src || el.data || "") }));
  const media = [...mediaMap.values()];
  const rows = [{
    type: "post",
    id: urn,
    postId: (urn.match(/activity:(\d+)/) || [])[1] || "",
    url: urn ? `https://www.linkedin.com/feed/update/${urn}/` : cleanUrl(location.href),
    authorName,
    authorProfile: profile ? cleanUrl(profile.href).split("?")[0] : "",
    authorMiniProfileUrn: miniProfileUrn(profile),
    authorDescription: headline,
    authorBadges: text(actor).split("\n").filter((line) => /verified|premium|you/i.test(line)).slice(0, 6),
    premiumVerifiedBadges: badgesFrom(actorText),
    postedText: ageText,
    edited: /edited/i.test(text(first(post, ['.update-components-actor__sub-description', '.feed-shared-actor__sub-description']))),
    visibility: (lines.find((line) => /visible to/i.test(line)) || ""),
    content: commentary,
    links: [...new Set(links)],
    linkCount: new Set(links).size,
    media,
    mediaCount: media.length,
    analyticsUrl: analytics ? cleanUrl(analytics.href).split("?")[0] : "",
    reactionCount: reactionCount ?? (hasSocialCounts ? 0 : null),
    reactionTypesVisible,
    commentCount: number(commentText) ?? (hasSocialCounts ? 0 : null),
    repostCount: number(repostText) ?? (hasSocialCounts ? 0 : null),
    impressionCount: number(impressionText),
    socialText,
    rawText: text(post).slice(0, 20000),
    scrapedAt,
  }];
  const commentArticles = all(post, ['article.comments-comment-entity[data-id]']);
  for (const article of commentArticles) {
    const id = article.getAttribute("data-id") || "";
    const meta = first(article, ['.comments-comment-meta__container']);
    const name = text(first(article, ['.comments-comment-meta__description-title']));
    const profileLink = first(article, ['a.comments-comment-meta__description-container[href*="/in/"], a[href*="/in/"]']);
    const description = text(first(article, ['.comments-comment-meta__description-subtitle']));
    const relation = text(first(article, ['.comments-comment-meta__data']));
    const timeText = text(first(article, ['time.comments-comment-meta__data', 'time', '.comments-comment-meta__info']));
    const content = text(first(article, ['.comments-comment-item__main-content', '.comments-comment-entity__content']));
    const social = text(first(article, ['.comments-comment-social-bar--cr', '.comment-social-activity']));
    const reactionButton = first(article, ['button[aria-label*="Reaction"], .comments-comment-social-bar__reactions-count--cr']);
    const replyButton = first(article, ['button[aria-label^="Reply to"]']);
    const parentArticle = article.parentElement?.closest('article.comments-comment-entity[data-id]');
    const metaText = `${text(meta)} ${ariaText(meta || article)}`;
    const commentReactionTypes = [...new Set(all(article, [
      '.comments-comment-social-bar--cr img[alt]',
      '.comment-social-activity img[alt]',
      '.reactions-icon[alt]',
    ]).map((img) => (img.alt || "").trim().toLowerCase()).filter((alt) => alt && !/profile|photo|graphic/i.test(alt)))];
    rows.push({
      type: "comment",
      id,
      commentId: (id.match(/,(\d+)\)/) || [])[1] || "",
      parentId: urn,
      parentCommentId: parentArticle ? parentArticle.getAttribute("data-id") : "",
      commenterName: name,
      commenterProfile: profileLink ? cleanUrl(profileLink.href).split("?")[0] : "",
      commenterMiniProfileUrn: miniProfileUrn(profileLink),
      commenterDescription: description,
      commenterType: relation,
      commenterDegree: degreeFrom(relation || metaText),
      commenterBadges: metaText.split("\n").filter((line) => /verified|premium/i.test(line)),
      premiumVerifiedBadges: badgesFrom(metaText),
      commentedText: timeText,
      edited: /edited/i.test(text(meta) + " " + text(article)),
      content,
      reactionCount: number(text(reactionButton) || reactionButton?.getAttribute("aria-label")),
      reactionText: reactionButton?.getAttribute("aria-label") || "",
      reactionTypesVisible: commentReactionTypes,
      replyCount: number(text(replyButton) || ""),
      impressionCount: number((text(article).match(/[\d,.]+\s*[kmb]?\s+impressions?/i) || [""])[0]),
      socialText: social,
      rawText: text(article).slice(0, 10000),
      scrapedAt,
    });
  }
  return rows;
}
"""


SDUI_EXTRACT_JS = r"""
(post, { scrapedAt, postUrn }) => {
  const commentSelector = '[componentkey^="CommentComponentReference_urn:li:comment:"]';
  const text = el => (el?.innerText || el?.textContent || '').replace(/\s+\n/g, '\n').replace(/[ \t]+/g, ' ').trim();
  const own = (root, selector) => [...root.querySelectorAll(selector)].filter(el => el.closest(commentSelector) === root.closest(commentSelector));
  const number = value => {
    const m = String(value || '').match(/^\s*(\d[\d,]*(?:\.\d+)?)(?:[ \t]*([kmb]))?(?=\s|$)/i);
    return m ? Math.round(Number(m[1].replace(/,/g, '')) * ({k:1e3,m:1e6,b:1e9}[m[2]?.toLowerCase()] || 1)) : null;
  };
  const badges = value => ['premium', 'verified'].filter(b => new RegExp(`\\b${b}\\b`, 'i').test(value));
  const types = root => [...new Set(own(root, 'li svg[id*="-consumption-"]').map(el => {
    const token = el.id.split('-consumption-')[0];
    return ({empathy:'love', entertainment:'funny', praise:'celebrate', appreciation:'support', interest:'insightful'})[token] || token;
  }))];
  const content = root => {
    const el = own(root, '[data-testid="expandable-text-box"]')[0];
    if (!el) return '';
    const copy = el.cloneNode(true);
    copy.querySelectorAll('button').forEach(b => b.remove());
    // textContent drops BR newlines; innerText on a detached clone drops layout too.
    copy.querySelectorAll('br').forEach(br => br.replaceWith('\n'));
    return text(copy);
  };
  const identity = (root, comment = false) => {
    const menu = own(root, comment ? 'button[aria-label^="View more options"]' : 'button[aria-label^="Open control menu"]')[0];
    let header = menu?.parentElement;
    const profileSelector = 'a[href*="/in/"], a[href*="/company/"]';
    let link = own(header || root, profileSelector).find(a => a.querySelector('p'));
    if (!link && !comment) {
      link = own(root, profileSelector).find(a => a.querySelector('p') && !a.closest('[data-sdui-anchor-id^="feed-header-"]'));
      header = link?.parentElement;
      while (header && header !== root && !header.querySelector('[aria-label^="Visibility:"]')) header = header.parentElement;
    }
    const paras = [...(link?.querySelectorAll('p') || [])];
    const other = [...(header?.querySelectorAll('p') || [])].filter(p => !link?.contains(p) && !p.closest('button, [role="button"]'));
    const badgeText = `${text(paras[0])} ${[...(header?.querySelectorAll('[aria-label]') || [])].map(el => el.getAttribute('aria-label')).join(' ')}`;
    return {
      name: text(paras[0]?.querySelector('[aria-hidden="true"]') || paras[0]).replace(/\s*•.*$/s, '').trim(),
      profile: link?.href.split('?')[0] || '',
      miniProfileUrn: link ? new URL(link.href, location.href).searchParams.get('miniProfileUrn') || '' : '',
      description: text(comment ? paras.slice(1).find(p => text(p) !== 'Author') : other[0]),
      relation: paras.some(p => text(p) === 'Author') ? 'Author' : '',
      time: text(other.at(-1)).replace(/\s*•\s*$/, ''),
      badges: badges(badgeText),
      degree: (text(paras[0]).match(/\b(1st|2nd|3rd\+?)/i) || [''])[0],
      edited: /\bedited\b/i.test(text(other.at(-1))),
    };
  };
  const analytics = own(post, 'a[href*="/analytics/post-summary/"]')[0];
  const permalink = own(post, 'a[href*="/feed/update/urn:li:activity:"]')[0];
  const urn = ((analytics?.href || permalink?.href || '').match(/urn:li:activity:\d+/) || [''])[0] || postUrn || '';
  if (!urn) throw new Error('SDUI post has no stable activity URN');
  const actor = identity(post);
  const count = label => {
    const button = own(post, `button[aria-label="${label}"]`)[0];
    return button ? number(text(button)) ?? 0 : null;
  };
  const reaction = own(post, '[aria-labelledby]').map(el => document.getElementById(el.getAttribute('aria-labelledby'))).find(el => /reactions?$/i.test(text(el)));
  const reactionCount = number(text(reaction)) ?? count('Reaction button state: no reaction');
  const commentCount = count('Comment'), repostCount = count('Repost');
  const socialText = `${reactionCount ?? ''} reactions\n${commentCount ?? ''} comments\n${repostCount ?? ''} reposts`;
  const links = [...new Set(own(post, '[data-testid="expandable-text-box"] a[href]').map(a => {
    const url = new URL(a.href, location.href);
    return url.pathname === '/safety/go/' ? url.searchParams.get('url') || a.href : a.href;
  }))];
  const media = own(post, 'img[src]').filter(img => !/profile-|static\.licdn\.com/.test(img.src) && !/profile/i.test(img.alt)).map(img => ({
    kind:'image', url:img.currentSrc || img.src, alt:img.alt || '',
    // SDUI img.src is often a 160px thumbnail; preserve the actual displayed source and available variants.
    sources:img.srcset ? img.srcset.split(/,\s*/).map(s => s.trim().split(/\s+/)[0]) : [],
  }));
  for (const video of own(post, 'video')) {
    const player = video.closest('[data-vjs-player]')?.player;
    const sources = (player?.currentSources?.() || [...video.querySelectorAll('source')].map(s => ({src:s.src,type:s.type})))
      .filter(s => /^https?:/.test(s.src || '')).map(s => ({url:s.src, type:s.type || ''}));
    const direct = video.currentSrc || video.src;
    const url = sources.find(s => s.type === 'video/mp4')?.url || sources[0]?.url || (/^https?:/.test(direct) ? direct : '');
    if (url) media.push({kind:'video', url, sources, poster:player?.poster?.() || video.poster || '',
      duration:Number.isFinite(player?.duration?.() ?? video.duration) ? player?.duration?.() ?? video.duration : null});
  }
  const repostHeader = own(post, '[data-sdui-anchor-id^="feed-header-"]')[0];
  const reposter = repostHeader && (repostHeader.closest('a[href*="/in/"]') || [...repostHeader.querySelectorAll('a[href*="/in/"]')].find(a => text(a)));
  const rows = [{
    type:'post', id:urn, postId:urn.split(':').at(-1), url:`https://www.linkedin.com/feed/update/${urn}/`,
    authorName:actor.name, authorProfile:actor.profile, authorMiniProfileUrn:actor.miniProfileUrn, authorDescription:actor.description,
    authorBadges:actor.badges, premiumVerifiedBadges:actor.badges, postedText:actor.time, edited:actor.edited,
    repostedBy:reposter ? text(reposter) : '', repostedByProfile:reposter?.href.split('?')[0] || '',
    visibility:own(post, '[aria-label^="Visibility:"]')[0]?.getAttribute('aria-label')?.replace('Visibility: ', '') || '',
    content:content(post), links, linkCount:links.length, media, mediaCount:media.length,
    analyticsUrl:analytics?.href.split('?')[0] || '', reactionCount, reactionTypesVisible:types(post),
    commentCount, repostCount, impressionCount:number(text(analytics)), socialText, rawText:text(post).slice(0,20000), scrapedAt,
  }];
  for (const article of post.querySelectorAll(commentSelector)) {
    const id = article.getAttribute('componentkey').replace('CommentComponentReference_', '');
    const actor = identity(article, true);
    const reactionText = own(article, 'button, [role="button"]').map(text).find(t => /^\d[\d,]*(?:\s|$)/.test(t)) || '';
    const parent = article.parentElement.closest(commentSelector);
    rows.push({
      type:'comment', id, commentId:(id.match(/,(\d+)\)/) || [,''])[1], parentId:urn,
      parentCommentId:parent?.getAttribute('componentkey').replace('CommentComponentReference_', '') || '',
      commenterName:actor.name, commenterProfile:actor.profile, commenterMiniProfileUrn:actor.miniProfileUrn, commenterDescription:actor.description,
      commenterType:actor.relation || actor.degree, commenterDegree:actor.degree, commenterBadges:actor.badges, premiumVerifiedBadges:actor.badges,
      commentedText:actor.time, edited:actor.edited, content:content(article),
      reactionCount:number(reactionText), reactionText, reactionTypesVisible:types(article),
      reactedByAuthor:own(article, '[aria-label="Reacted to by the author"]').length > 0,
      replyCount:number(text(own(article, 'p').find(p => !p.closest('button, [role="button"], a[href*="/in/"]') && /^\d[\d,]*(?:\s+\d[\d,]*)?$/.test(text(p))))),
      impressionCount:number(text(own(article, 'p').find(p => /^\d[\d,]* impressions?\b/.test(text(p))))),
      socialText:'', rawText:text(article).slice(0,10000), scrapedAt,
    });
  }
  return rows;
}
"""


async def extract_post(post: CDPElement, scraped_at: dt.datetime, urn: str = "") -> list[dict[str, Any]]:
    script = EXTRACT_JS if await post.get_attribute("data-urn") else SDUI_EXTRACT_JS
    rows = await post.evaluate(script, {"scrapedAt": scraped_at.isoformat(), "postUrn": urn})
    return [add_time_fields(normalize_counts(row), scraped_at) for row in rows if row.get("id")]


def apply_reply_parents(rows: list[dict[str, Any]], parents: dict[str, str]) -> None:
    """Restore SDUI sibling reply relationships observed through explicit loaders."""
    comments = [row for row in rows if row["type"] == "comment"]
    for row in comments:
        if row["id"] in parents:
            row["parentCommentId"] = parents[row["id"]]
    for index, parent in enumerate(comments):
        count = parent.get("replyCount") or 0
        if not count or parent["id"] not in parents.values():
            continue
        # "See previous replies" can insert older siblings before already-visible replies.
        # Require the displayed count and a freshly observed child to agree with the group.
        group = comments[index + 1:index + 1 + count]
        if len(group) == count and any(row.get("parentCommentId") == parent["id"] for row in group):
            for row in group:
                row["parentCommentId"] = parent["id"]


async def scroll_page(page: CDPPage, settle_ms: int) -> dict[str, Any]:
    data = await page.evaluate(
        """() => {
          const main = document.querySelector("main");
          const scroller = main && main.scrollHeight > main.clientHeight + 100 ? main : document.scrollingElement;
          const before = { top: scroller.scrollTop, height: scroller.scrollHeight, client: scroller.clientHeight };
          scroller.scrollTop += Math.max(600, scroller.clientHeight * 0.85);
          window.dispatchEvent(new Event("scroll"));
          return before;
        }"""
    )
    await page.wait_for_timeout(settle_ms)
    return data


async def scrape_posts(
    cdp_url: str,
    username: str,
    limit: int,
    out_path: Path,
    include_comments: bool,
    max_scrolls: int,
    max_comment_rounds: int,
    settle_ms: int,
    dry_run: bool,
    format: str,
) -> None:
    cache_dir = Path("~/.cache/sanand-scripts/backuplinkedin").expanduser()
    trace = obs.new_run(
        "backuplinkedin",
        cache_dir=cache_dir,
        args=obs.sanitize_args(
            {
                "username": username,
                "limit": limit,
                "out": out_path,
                "comments": include_comments,
                "cdp_url": cdp_url,
                "max_scrolls": max_scrolls,
                "max_comment_rounds": max_comment_rounds,
                "settle_ms": settle_ms,
                "dry_run": dry_run,
                "format": format,
            }
        ),
    )
    rows: list[dict[str, Any]] = []
    processed: set[str] = set()
    changed = 0
    incomplete_comments = 0
    page: CDPPage | None = None
    try:
        # Reject corrupt local input before changing the browser or any backup.
        existing_rows = load_jsonl(out_path)
        ugc_parents: dict[str, set[str]] = {}
        for row in existing_rows:
            if row.get("type") == "comment" and (match := re.search(r"\(ugcPost:(\d+),", row.get("id", ""))):
                ugc_parents.setdefault(f"urn:li:ugcPost:{match[1]}", set()).add(row["parentId"])
        known_ugc_parents = {ugc: next(iter(parents)) for ugc, parents in ugc_parents.items() if len(parents) == 1}
        with trace.span("cdp_connection", {"cdp_url": cdp_url}):
            page = await connect_linkedin_page(cdp_url)
            trace.event("runtime", await obs.browser_versions(page))
        with trace.span("page_session"):
            with trace.span("page_discovery"):
                obs.attach_page_observers(page, trace)
                trace.event("page", {"url": page.url, "title": await page.title()})
            with trace.span("page_navigation", {"username_hash": obs.short_hash(username)}):
                await navigate_posts(page, username)
            with trace.span("dom_validation"):
                post_containers = len(await page.query_selector_all(POST_SELECTOR))
                selector_counts = {selector: len(await page.query_selector_all(selector)) for selector in POST_SELECTORS}
                selector_used = next(selector for selector, count in selector_counts.items() if count)
                trace.event("selector_counts", {"selector_used": selector_used, "post_containers": post_containers, "candidates": selector_counts})
            stale = 0
            for _ in range(max_scrolls):
                with trace.span("scanning"):
                    handles = await page.query_selector_all(POST_SELECTOR)
                if not handles:
                    eprint("warning: no post containers found on current viewport")
                before = len(processed)
                for post in handles:
                    urn = await resolve_post_urn(post, settle_ms, known_ugc_parents)
                    if not urn:
                        raise RuntimeError("Post container has no stable activity URN; refusing to write an unidentified post")
                    if urn in processed:
                        continue
                    with trace.span("opening_expanding", {"post_hash": obs.short_hash(urn)}):
                        await post.scroll_into_view_if_needed(timeout=5000)
                        await page.wait_for_timeout(settle_ms)
                        await expand_text(post, settle_ms)
                        comment_stats: dict[str, Any] = {}
                        if include_comments:
                            await open_comments(post, settle_ms)
                            comment_stats = await load_all_comments(post, max_comment_rounds, settle_ms)
                            if comment_stats["commentsLoaded"] < comment_stats["expectedComments"] or comment_stats["remainingLoaders"]:
                                incomplete_comments += 1
                                eprint(f"warning: incomplete comments for {urn}: loaded={comment_stats['commentsLoaded']} expected={comment_stats['expectedComments']} remaining_loaders={comment_stats['remainingLoaders']}")
                    scraped_at = now_utc()
                    try:
                        with trace.span("extraction", {"post_hash": obs.short_hash(urn)}):
                            extracted = await extract_post(post, scraped_at, urn)
                    except Exception as exc:
                        trace.exception(exc, post_hash=obs.short_hash(urn))
                        raise
                    if not extracted or extracted[0].get("id") != urn:
                        raise RuntimeError("Post identity changed during extraction; refusing to write mismatched rows")
                    processed.add(urn)
                    apply_reply_parents(extracted, comment_stats.get("replyParents", {}))
                    for row in extracted:
                        if row["type"] == "post" and include_comments:
                            row["commentScrapeStats"] = comment_stats
                    with trace.span("validation"):
                        trace.event("row_counts", {"post_hash": obs.short_hash(urn), "rows": len(extracted), "missing_rates": obs.missing_rates(extracted, ["id", "content", "postedText"])})
                    rows.extend(extracted)
                    if not dry_run:
                        before_rows = len(load_jsonl(out_path))
                        with trace.span("writing", {"path": str(out_path), "before_rows": before_rows}):
                            delta = update_jsonl(out_path, extracted)
                        changed += delta
                        trace.event("output_stats", {"path": str(out_path), "before_rows": before_rows, "after_rows": len(load_jsonl(out_path)), "rows_changed": delta})
                    event = {"event": "scraped", "post": urn, "rows": len(extracted), "posts_seen": len(processed)}
                    print(compact_json(event) if format == "jsonl" else f"scraped: {urn}: rows={len(extracted)} seen={len(processed)}", flush=True)
                    if limit and len(processed) >= limit:
                        break
                if limit and len(processed) >= limit:
                    break
                stale = stale + 1 if len(processed) == before else 0
                with trace.span("scrolling", {"stale": stale}):
                    scroll = await scroll_page(page, settle_ms * 2)
                    trace.event("scroll_stats", scroll)
                if stale >= 6 or scroll["top"] + scroll["client"] >= scroll["height"] - 8:
                    show_more = await page.query_selector_all('button:has-text("Show more results"), button:has-text("Show more posts")')
                    clicks = await click_all(show_more[:2], "show-more-results", settle_ms * 2)
                    trace.event("click_stats", {"show_more_buttons": len(show_more), "show_more_clicks": clicks})
                    # Infinite-scroll hydration can append cards without a button.
                    # Give it the same quiet window instead of stopping on the first bottom hit.
                    if not clicks and stale >= 6:
                        break
            dom = await obs.capture_dom_outline(page)
        post_rows = sum(1 for row in rows if row.get("type") == "post")
        previous = obs.latest_summary(cache_dir).get("selector_used")
        summary_stats = {
            "status": "ok",
            "dry_run": dry_run,
            "path": str(out_path),
            "posts": len(processed),
            "rows": len(rows),
            "post_rows": post_rows,
            "incomplete_comments": incomplete_comments,
            "rows_changed": changed,
            "selector_used": selector_used,
            "selector_counts": selector_counts,
            "previous_selector": previous,
            "limit": limit,
            "post_containers": post_containers if "post_containers" in locals() else 0,
            "missing_rates": obs.missing_rates([row for row in rows if row.get("type") == "post"], ["id", "content", "postedText"]),
        }
        anomalies = obs.classify_linkedin_anomalies(summary_stats)
        if incomplete_comments:
            anomalies.append("linkedin_incomplete_comments")
        if anomalies:
            trace.write_zip("anomaly", {**summary_stats, "anomalies": anomalies}, dom)
        elif not obs.monthly_baseline_exists(cache_dir, trace.stamp):
            trace.write_zip("baseline", summary_stats, dom)
        trace.finish({**summary_stats, "anomalies": anomalies})
    except Exception as exc:
        trace.exception(exc)
        if page is not None:
            try:
                trace.write_zip("anomaly", {"status": "failed"}, await obs.capture_dom_outline(page))
            except Exception as zip_exc:
                trace.exception(zip_exc, during="failure_zip")
        trace.finish({"status": "failed", "error_type": type(exc).__name__, "error_message": str(exc)})
        raise
    finally:
        if page is not None:
            await page.close()
    if dry_run:
        eprint(f"dry-run: scraped {len(rows)} rows for {len(processed)} posts; not writing {out_path}")
        return
    summary = {"event": "updated", "path": str(out_path), "posts": len(processed), "rows": len(rows), "rows_changed": changed}
    print(compact_json(summary) if format == "jsonl" else f"updated: posts={len(processed)} rows={len(rows)} changed={changed} -> {out_path}", flush=True)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    describe_schema: bool = typer.Option(False, "--describe", help="Print machine-readable CLI metadata and exit."),
) -> None:
    if describe_schema:
        print(compact_json(describe()))
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit(0)


@app.command(help="Back up recent LinkedIn posts and comments from a profile activity page.")
def posts(
    username: str = typer.Option(..., "--username", help="LinkedIn public identifier, e.g. sanand0."),
    limit: int = typer.Option(100, "--limit", "-n", min=0, help="Maximum posts to scrape. Use 0 for no explicit limit."),
    out: Path = typer.Option(OUT_PATH, "--out", help="JSONL file to update in place."),
    comments: bool = typer.Option(True, "--comments/--no-comments", help="Expand and scrape comments for each post."),
    cdp_url: str = typer.Option(CDP_URL, "--cdp-url", help="Chrome DevTools Protocol URL."),
    max_scrolls: int = typer.Option(240, "--max-scrolls", help="Maximum profile activity scroll rounds."),
    max_comment_rounds: int = typer.Option(30, "--max-comment-rounds", help="Maximum load-more rounds per post."),
    settle_ms: int = typer.Option(800, "--settle-ms", help="Delay after clicks and scrolls, in milliseconds."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Scrape and report without writing the JSONL file."),
    format: str = typer.Option("text", "--format", help="text or jsonl progress output."),
) -> None:
    if format not in {"text", "jsonl"}:
        raise typer.BadParameter("--format must be text or jsonl")
    try:
        asyncio.run(scrape_posts(cdp_url, username, limit, out.expanduser(), comments, max_scrolls, max_comment_rounds, settle_ms, dry_run, format))
    except Exception as exc:
        typer.echo(f"backuplinkedin.py: {exc}", err=True)
        raise typer.Exit(1) from exc


if __name__ == "__main__":
    app()
