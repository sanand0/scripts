#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["typer>=0.12", "websockets>=15"]
# ///
"""Incrementally back up ChatGPT's rendered history in a private background Edge tab.

Loads ../tools/aiscrapers/*.js on every page; no scraping logic or APIs in Python.
Sidebar discovery is partial: archived/project/older chats may never appear.
Use --conversation URL to add known omissions. See README.md for export reconciliation.
Full scans check both rendered history boundaries, not all branches. Incremental
updates trust the saved prefix before an unchanged message anchor; --rescan checks it.
Chat-local extraction failures and active generation stay pending while the batch
continues, including isolated load timeouts. Two consecutive load failures stop
further requests; authentication, rate limiting, CDP and write errors stop immediately.
DOM timestamps are retained when available; missing timestamps are never invented.
Publishes Title.md in ~/Documents/chatgpt using chatgpt-to-markdown filename rules.
Canonical JSONL/Markdown stay in ~/Documents/data/chatgpt; prior shared files are
archived there before replacement. Later exports may overwrite shared Markdown;
unchanged captures leave those exports alone. Do not run both writers concurrently.

Examples:
  backupchatgpt.py --limit 20 --format jsonl > /tmp/chatgpt-run.jsonl
  backupchatgpt.py --rescan --limit 5 --name research | moor
  backupchatgpt.py --conversation https://chatgpt.com/c/UUID --dry-run
  backupchatgpt.py --describe | jaq .
"""
from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack, asynccontextmanager
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import tempfile
from urllib.parse import urlsplit
from urllib.request import urlopen
from uuid import UUID

import typer
import websockets

from backupwhatsapp import CDPPage, cdp_http_base
import sanand_observability as obs

app = typer.Typer(add_completion=False, help=__doc__)
SCRAPERS = Path(__file__).resolve().parent.parent / "tools" / "aiscrapers"
SOURCES = ("chatgptscraper.js", "chatgpt-sidebar-scraper.js")


class IncompleteChat(ValueError):
    """A chat-local extraction failure; preserve it and continue the batch."""


class ChatLoadFailure(IncompleteChat):
    """A transient conversation load error; repeated failures stop requests."""


class ChatLoadTimeout(ChatLoadFailure):
    """Ambiguous missing content after the bounded load wait."""


# Read-only: never invoke generation controls. The agent UI uses aria-label=Stop
# without the historical stop-button test ID. Ignore hidden stale controls.
GENERATION_ACTIVE = """!![...document.querySelectorAll('[data-is-streaming="true"], [data-testid="stop-button"], button[aria-label="Stop"], button[aria-label="Stop streaming"], button[aria-label="Stop generating"]')].some(n => !n.closest('[hidden], [aria-hidden="true"]') && n.getClientRects().length)"""


def encoded(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value) -> str:
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def duration(seconds: float) -> str:
    minutes, seconds = divmod(max(0, round(seconds)), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}"


def size(n: int) -> str:
    return f"{n}B" if n < 1000 else f"{n / 1000:.0f}KB" if n < 1_000_000 else f"{n / 1_000_000:.1f}MB"


def message_stats(rows: list[dict]) -> dict:
    return dict(messages=len(rows), prompts=sum(r["role"] == "user" for r in rows), replies=sum(r["role"] == "assistant" for r in rows))


def unchanged_anchor(messages: list[dict], previous: list[dict]) -> str | None:
    """Only the oldest captured message can anchor the prefix: later matches could hide an edit."""
    if not messages:
        return None
    first = messages[0]
    old = next((m for m in previous if m["id"] == first["id"]), None)
    if old and all(first.get(k) == old.get(k) for k in ("id", "role", "content", "parts")):
        return first["id"]
    return None


def merge_tail(previous: list[dict], messages: list[dict], anchor: str) -> list[dict]:
    if unchanged_anchor(messages, previous) != anchor:
        raise IncompleteChat("Incremental anchor changed; prior backup retained")
    index = next(i for i,m in enumerate(previous) if m["id"] == anchor)
    return previous[:index] + messages


def result_line(summary: dict) -> str:
    return (f'ID={summary["conversationId"]}\t({summary["position"]}/{summary["total"]})'
            f'\tmessages={summary["messages"]}\tprompts={summary["prompts"]}'
            f'\tcaptured={summary.get("captured_messages", summary["messages"]):03}\treused={summary.get("reused_messages", 0):03}'
            f'\telapsed={duration(summary["duration_ms"] / 1000)}\tmarkdown={size(summary["markdown_bytes"])}'
            f'\tcanonical={"dry-run" if summary.get("dry_run") else "updated" if summary["changed"] else "unchanged"}\tshared={summary["shared_status"]}')


def page_event(page, name: str, data: dict) -> None:
    if trace := getattr(page, "backup_trace", None):
        trace.event(name, {**getattr(page, "backup_context", {}), **data})


def atomic(path: Path, text: str | bytes) -> bool:
    data = text.encode() if isinstance(text, str) else text
    if path.exists() and path.read_bytes() == data:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with tmp.open("wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    tmp.replace(path)
    return True


def identity(value: str) -> str:
    if "://" in value:
        url = urlsplit(value)
        if url.scheme != "https" or url.netloc != "chatgpt.com":
            raise ValueError("Conversation URLs must be https://chatgpt.com/.../c/UUID")
        match = re.search(r"/c/([^/?#]+)", url.path)
        value = match[1] if match else ""
    return str(UUID(value))


def filename(title: str, cid: str) -> str:
    title = re.sub(r'[\x00-\x1f<>:"/\\|?*]', "_", title).strip(" .") or "Untitled"
    title = title.encode()[:170].decode("utf-8", errors="ignore")
    return f"{title} [{cid}].jsonl"


def file_id(path: Path) -> str:
    return identity(path.stem.rsplit(" [", 1)[-1].removesuffix("]"))


def markdown_owner(path: Path) -> str | None:
    """Read identity only from export metadata or scraper frontmatter, never message bodies."""
    if path.is_symlink():
        return None
    with path.open("rb") as stream:
        header = stream.read(8192).decode("utf-8-sig", errors="replace")
    header = re.split(r"\n#+ (?:User|Assistant|ChatGPT)\s*\r?\n", header, maxsplit=1)[0]
    match = re.search(r'^(?:- Link: |source: ")(https://chatgpt\.com/[^\s"]+)', header, re.M)
    if not match:
        return None
    try:
        return identity(match[1])
    except ValueError:
        return None


def markdown_index(directory: Path) -> dict[Path, str | None]:
    return {path: markdown_owner(path) for path in sorted(directory.glob("*.md"))}


def publish_markdown(canonical: Path, cid: str, title: str, directory: Path, index: dict, previous: dict, metrics: dict | None = None) -> dict:
    """Publish converter-compatible names; retain overwritten exports and leave later exports alone."""
    data = canonical.read_bytes()
    fingerprint = hashlib.sha256(data).hexdigest()
    location = str(directory.resolve())
    matches = [p for p, owner in index.items() if owner == cid]
    if previous.get("hash") == fingerprint and previous.get("directory") == location and matches:
        return dict(previous, file=matches[0].name, changed=False, removed=[], bytes=len(data))
    # Equivalent to chatgpt-to-markdown's ASCII \w sanitization and collapsed spaces.
    base = re.sub(r"[^A-Za-z0-9_]+", " ", title).strip() or cid
    compatible = [p for p in matches if re.fullmatch(re.escape(base) + r"(?: \(\d+\))?", p.stem)]
    target = compatible[0] if compatible else directory / f"{base}.md"
    count = 0
    while True:
        # Match NTFS case-insensitive semantics even when running on ext4.
        other = next((p for p in index if p.name.casefold() == target.name.casefold()), None)
        if other is None:
            break
        if index[other] == cid:
            target = other
            break
        count += 1
        target = directory / f"{base} ({count}).md"
    if len(target.name.encode()) > 255:
        raise ValueError("Title exceeds the converter's filename limit; shorten the chat title")
    removed = []
    for path in dict.fromkeys([*matches, target]):
        if not path.exists():
            continue
        if markdown_owner(path) != cid:
            raise ValueError(f"Markdown identity changed during publication: {path}; stop the converter and retry")
        old = path.read_bytes()
        if old != data or path != target:
            revision = canonical.parent / ".revisions" / cid / f"shared-{digest([str(path), hashlib.sha256(old).hexdigest()])}"
            atomic(revision.with_suffix(".md"), old)
            atomic(revision.with_suffix(".json"), encoded(dict(source=str(path), conversationId=cid)) + "\n")
    details = f'markdown={size(len(data))}'
    if metrics:
        details = f'elapsed={duration(metrics["duration_ms"] / 1000)} prompts={metrics["prompts"]} messages={metrics["messages"]} ' + details
    print(f"Publishing local Markdown ID={cid} ({details})", file=sys.stderr, flush=True)
    changed = atomic(target, data)
    index[target] = cid
    for path in matches:
        if path != target:
            path.unlink()  # Exact prior bytes were archived above.
            index.pop(path)
            removed.append(path.name)
    return dict(hash=fingerprint, file=target.name, directory=location, changed=changed or bool(removed), removed=removed, bytes=len(data))


def records(messages: list[dict], cid: str, metadata: dict | None = None) -> list[dict]:
    result = []
    for message in messages:
        payload = {k: v for k,v in message.items() if k not in {"contentHash", "conversationId"}}
        if metadata is not None:
            payload["conversation"] = metadata
        result.append(dict(payload, conversationId=cid, contentHash=digest(payload)))
    return result


def validate(rows: list[dict], previous: list[dict]) -> None:
    if not rows:
        raise IncompleteChat("Empty extraction; previous backup retained")
    ids = [r["id"] for r in rows]
    if len(ids) != len(set(ids)):
        raise IncompleteChat("Duplicate message IDs")
    for row in rows:
        try:
            UUID(row["id"])
        except ValueError as exc:
            raise IncompleteChat("Unstable/positional message ID; full immutable UUID required") from exc
        if row["role"] not in {"user", "assistant"} or not row["content"].strip():
            raise IncompleteChat("Invalid message role/content")
    previous_ids = {r["id"] for r in previous}
    if previous_ids - set(ids):
        raise IncompleteChat("Extraction missing previously saved IDs (incomplete history or changed branch); backup retained")
    if [i for i in ids if i in previous_ids] != [r["id"] for r in previous]:
        raise IncompleteChat("Previously saved messages reordered; backup retained")
    if rows[0]["role"] != "user" or rows[-1]["role"] != "assistant" or any(a["role"] == b["role"] == "user" for a,b in zip(rows, rows[1:])):
        raise IncompleteChat(f'Suspiciously incomplete roles/history: prompts={message_stats(rows)["prompts"]} replies={message_stats(rows)["replies"]} first={rows[0]["role"]} last={rows[-1]["role"]}; prior backup retained')


def read_rows(path: Path, cid: str) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line_no, line in enumerate(path.read_text().splitlines(), 1):
        try:
            row = json.loads(line)
            if row["conversationId"] != cid or records([row], cid)[0] != row:
                raise ValueError("conversation identity/content hash mismatch")
            rows.append(row)
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError(f"{path}:{line_no}: invalid backup: {exc}") from exc
    validate(rows, [])
    return rows


def save(path: Path, rows: list[dict], markdown: str, title: str | None = None) -> bool:
    """Archive the prior canonical snapshot before replacing it; replay repairs interrupted MD writes."""
    text = "".join(encoded(r) + "\n" for r in rows)
    target = path.with_name(filename(title, file_id(path))) if title is not None else path
    if target != path and target.exists():
        raise ValueError(f"Rename target already exists: {target}; reconcile duplicate backups first")
    old_markdown = path.with_suffix(".md").read_text() if path.with_suffix(".md").exists() else None
    if path.exists() and (path.read_text() != text or old_markdown != markdown):
        revision = path.parent / ".revisions" / rows[0]["conversationId"] / digest([path.read_text(), old_markdown])
        atomic(revision.with_suffix(".jsonl"), path.read_text())
        if path.with_suffix(".md").exists():
            atomic(revision.with_suffix(".md"), path.with_suffix(".md").read_text())
    changed = atomic(path, text)
    changed = atomic(path.with_suffix(".md"), markdown) or changed
    if target != path:
        path.with_suffix(".md").replace(target.with_suffix(".md"))
        path.replace(target)  # Canonical file moves last; interruption can replay the pair.
        return True
    return changed


async def inject(page: CDPPage) -> None:
    # Read at execution time, never cache/vendor/translate the sibling sources.
    for name in SOURCES:
        source = (SCRAPERS / name).read_text()
        page_event(page, "scraper_source", dict(source_file=name, sha256=hashlib.sha256(source.encode()).hexdigest()))
        await page.evaluate("() => {" + source + ";return true;}")


@asynccontextmanager
async def owned_page(cdp_url: str):
    def version():
        with urlopen(cdp_http_base(cdp_url) + "/json/version", timeout=5) as response:
            return json.load(response)
    try:
        info = await asyncio.to_thread(version)
    except OSError as exc:
        raise RuntimeError(f"CDP unavailable at {cdp_url}; start authenticated Edge with port 9222") from exc
    if "Edg/" not in info.get("Browser", ""):
        raise RuntimeError("Expected an existing Microsoft Edge CDP session")
    async with websockets.connect(info["webSocketDebuggerUrl"], max_size=None) as socket:
        browser = CDPPage(socket, "", info["Browser"])
        target = (await browser.command("Target.createTarget", url="about:blank", background=True))["targetId"]
        page = None
        try:
            # Attach only our target. No activation, focus emulation, or ownership of user tabs.
            def target_socket():
                with urlopen(cdp_http_base(cdp_url) + "/json/list", timeout=5) as response:
                    return next(t["webSocketDebuggerUrl"] for t in json.load(response) if t["id"] == target)
            async with websockets.connect(await asyncio.to_thread(target_socket), max_size=None, open_timeout=10) as page_socket:
                page = CDPPage(page_socket, "", info["Browser"])
                yield page
                page.backup_keep_open = getattr(page, "backup_keep_open", False) or await page.evaluate(f"() => ({GENERATION_ACTIVE})")
        except BaseException:
            retain_page(page, target)
            raise
        else:
            if getattr(page, "backup_keep_open", False):
                retain_page(page, target)
            else:
                await browser.command("Target.closeTarget", targetId=target)


def retain_page(page, target):
    if page is not None:
        page_event(page, "inspection_tab_retained", dict(target_id=target, url=page.url))
        if trace := getattr(page, "backup_trace", None):
            trace.counters.update(inspection_target_id=target, inspection_url=page.url)
            trace.counters.setdefault("inspection_tabs", []).append(dict(target_id=target, url=page.url))
    print(f"Inspection tab kept open target={target} url={obs.clean_url(page.url) if page is not None else 'about:blank'}; close it manually after inspecting", file=sys.stderr, flush=True)


async def navigate(page: CDPPage, url: str, conversation: bool = False) -> None:
    started = time.monotonic()
    page_event(page, "navigation_start", dict(url=url))
    await asyncio.sleep(max(0, 10 - (time.monotonic() - getattr(page, "last_navigation", 0))))
    page.last_navigation = time.monotonic()
    result = await page.command("Page.navigate", url=url)
    if result.get("errorText"):
        raise RuntimeError(f"Navigation failed: {result['errorText']}")
    previous = None
    injected = False
    for attempt in range(60):
        await asyncio.sleep(1)
        status = await page.evaluate('''() => ({busy: GENERATION_ACTIVE, url:location.href, login:!!document.querySelector('[data-testid="login-button"],a[href="/auth/login"]'),
          history:!!document.querySelector('nav[aria-label="Chat history"] a[href*="/c/"]'),
          assistant:!!document.querySelector('[data-message-author-role="assistant"],[data-markdown-text-style="assistant-message"]'),
          users:document.querySelectorAll('[data-message-author-role="user"],[data-user-message-bubble="true"]').length,
          assistants:document.querySelectorAll('[data-message-author-role="assistant"],[data-markdown-text-style="assistant-message"]').length,
          images:document.querySelectorAll("main img").length, message_units:document.querySelectorAll("main [data-chatgpt-search-message-ids], main [data-message-id]").length,
          readyState:document.readyState, challenge:!!document.querySelector('#challenge-running,#challenge-stage,iframe[src*="challenges.cloudflare.com"]'),
          rate_limited:/Too many requests|Rate limit|Try again later/i.test([...document.querySelectorAll('[role="alert"]')].map(n=>n.innerText).join(" ")),
          load_error:/Could not load (?:this )?(?:ChatGPT )?conversation|Unable to load conversation|Something went wrong while loading/i.test(document.querySelector('main [role="alert"]')?.innerText || (document.querySelector('[data-user-message-bubble],[data-message-author-role]') ? '' : document.querySelector('main')?.innerText||'')),
          error:/Conversation not found|You do not have access/i.test(document.querySelector('main [role="alert"]')?.innerText || (document.querySelector('[data-user-message-bubble],[data-message-author-role]') ? '' : document.querySelector('main')?.innerText||''))})'''.replace('GENERATION_ACTIVE', GENERATION_ACTIVE))
        if conversation and "/c/" in urlsplit(status["url"]).path and status.get("readyState") in {"interactive", "complete"} and not any(status.get(k) for k in ("login", "busy", "challenge", "rate_limited", "load_error", "error")):
            if identity(status["url"]) != identity(url):
                raise RuntimeError("Opened a different conversation")
            if not injected:
                await inject(page)
                injected = True
            # Readiness follows the scraper's contract, including image-only replies.
            counts = await page.evaluate("""() => {const messages=chatgptscraper.extractMessages(document);
              return {users:messages.filter(m=>m.role==='user').length,assistants:messages.filter(m=>m.role==='assistant').length};}""")
            status.update(counts, assistant=bool(counts["assistants"]))
        if status != previous or attempt % 10 == 0 or attempt == 59:
            page_event(page, "navigation_state", dict(status, poll=attempt + 1, duration_ms=round((time.monotonic() - started) * 1000)))
        if attempt and attempt % 10 == 0:
            print(f'  loading elapsed={duration(time.monotonic()-started)} users={status.get("users", 0)} assistants={status.get("assistants", 0)} challenge={str(status.get("challenge", False)).lower()}', file=sys.stderr, flush=True)
        previous = status
        page.url = status["url"]
        if status["login"] or "/auth/" in status["url"]:
            raise RuntimeError("ChatGPT authentication unavailable; sign in to Edge manually")
        if status.get("challenge"):
            raise RuntimeError("ChatGPT browser challenge; stop requests and inspect the tab")
        if status.get("rate_limited"):
            raise RuntimeError("ChatGPT rate limited; stop requests and retry later")
        if status.get("busy"):
            raise IncompleteChat("Generation still running; deferred without touching controls")
        if status.get("load_error"):
            error = ChatLoadFailure if conversation else RuntimeError
            raise error("ChatGPT could not load this conversation; prior backup retained")
        if status["error"]:
            raise IncompleteChat("Conversation missing/inaccessible; prior backup retained")
        if (status["assistant"] if conversation else status["history"]):
            if conversation and identity(status["url"]) != identity(url):
                raise RuntimeError("Opened a different conversation")
            await asyncio.sleep(3)  # React can hydrate user text before assistant content.
            if not injected:
                await inject(page)
            page_event(page, "navigation_ready", dict(duration_ms=round((time.monotonic() - started) * 1000)))
            return
    page_event(page, "navigation_failed", dict(status, duration_ms=round((time.monotonic() - started) * 1000)))
    error = ChatLoadTimeout if conversation else RuntimeError
    raise error(f'ChatGPT load timeout after 60s: users={status.get("users", 0)} assistants={status.get("assistants", 0)} challenge={status.get("challenge", False)}; inspect navigation_state events')


# Only navigation/scroll orchestration lives here. All message and link extraction stays in tools.
SCROLL = r'''({sidebar, reset, direction, edge}) => {
  const scope = document.querySelector(sidebar ? 'nav[aria-label="Chat history"]' : 'main');
  if (!scope) throw Error('Missing scroll scope');
  const anchor = scope.querySelector(sidebar ? 'a[href*="/c/"]' : '[data-user-message-bubble],[data-message-author-role],[data-markdown-text-style="assistant-message"]');
  const candidates = [];
  // Follow the message's ancestors so nested code editors cannot become the history scroller.
  for (let e=anchor?.parentElement||scope;e;e=e.parentElement) candidates.push(e);
  const elements = candidates.filter(e => e.clientHeight>0 && /auto|scroll/.test(getComputedStyle(e).overflowY));
  const scroller = elements.sort((a,b)=>(b.scrollHeight-b.clientHeight)-(a.scrollHeight-a.clientHeight))[0] || document.scrollingElement;
  if (reset) window.__backupScroller = scroller;
  const e = window.__backupScroller;
  if (!e?.isConnected) throw Error('Scroll container disappeared');
  const before = e.scrollTop;
  if (edge === 'bottom') e.scrollTop = e.scrollHeight;
  if (direction) e.scrollTop += direction * Math.max(1,e.clientHeight*0.65);
  return {top:e.scrollTop,height:e.scrollHeight,viewport:e.clientHeight,before,
    container:{tag:e.tagName,id:e.id},
    boundary:direction<0 ? e.scrollTop<=1 : e.scrollTop+e.clientHeight>=e.scrollHeight-2};
}'''


async def sweep(page, sidebar: bool, direction: int, max_steps: int, checkpoint=None, anchor_previous=None) -> dict:
    started = time.monotonic()
    page_event(page, "scroll_start", dict(sidebar=sidebar, direction=direction, max_steps=max_steps))
    last = None
    stable = 0
    expanded_total = 0
    visible_before = set() if sidebar else getattr(page, "backup_visible", set())
    for step in range(max_steps):
        snapshot = await page.evaluate('''async sidebar => {
          const collapsed = () => sidebar ? [] : [...document.querySelectorAll('[data-user-message-bubble="true"] button[aria-expanded="false"], [data-message-author-role="user"] button[aria-expanded="false"]')]
            .filter(b=>/^Show more$/i.test(b.innerText.trim()) && !b.closest('[hidden], [aria-hidden="true"]') && b.getClientRects().length);
          let expanded = 0;
          // Only unfold prompt text in our owned tab. Never activate assistant,
          // generation, reasoning, edit, or submit controls.
          if (!sidebar && !GENERATION_ACTIVE) {
            for (const button of collapsed()) {button.click(); expanded++;}
            if (expanded) await new Promise(resolve=>setTimeout(resolve,250));
          }
          return {expanded_prompts:expanded,collapsed_prompts:collapsed().length,captured: sidebar
          ? chatgptSidebarScraper.captureChats(document,window.__backupState)
          : chatgptscraper.captureMessages(document,window.__backupState),
          visible: sidebar ? [] : chatgptscraper.extractMessages(document).map(m=>m.id),
          blocked: location.pathname.includes("/auth/") || !!document.querySelector('[data-testid="login-button"],a[href="/auth/login"],#challenge-running,#challenge-stage,iframe[src*="challenges.cloudflare.com"]') || /Too many requests|Rate limit|Try again later/i.test([...document.querySelectorAll('[role="alert"]')].map(n=>n.innerText).join(" ")),
          busy: GENERATION_ACTIVE};}'''.replace('GENERATION_ACTIVE', GENERATION_ACTIVE), sidebar)
        if snapshot.get("blocked"):
            raise RuntimeError("ChatGPT authentication/challenge/rate limit during scan; stop requests and retry later")
        if not sidebar and snapshot["busy"]:
            raise IncompleteChat("Generation still running; deferred without touching controls")
        expanded_total += snapshot.get("expanded_prompts", 0)
        if snapshot.get("expanded_prompts"):
            page_event(page, "prompt_expansion", dict(expanded=snapshot["expanded_prompts"], remaining=snapshot.get("collapsed_prompts", 0)))
            print(f'  expanded_prompts={snapshot["expanded_prompts"]:03}', file=sys.stderr, flush=True)
        if snapshot.get("collapsed_prompts"):
            raise IncompleteChat("Long prompt remains collapsed; incomplete capture deferred")
        captured = snapshot["captured"]
        if checkpoint:
            checkpoint(captured)
        visible = set(snapshot["visible"])
        unstable = [mid for mid in visible if not re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", mid)]
        if unstable:
            page_event(page, "capture_anomaly", dict(step=step, reason="unstable_ids", unstable_ids=unstable[:10]))
            raise IncompleteChat("Unstable/positional message IDs in rendered history; scan incomplete")
        if len(visible) != len(snapshot["visible"]):
            page_event(page, "capture_anomaly", dict(step=step, reason="duplicate_ids", visible_count=len(snapshot["visible"]), unique_count=len(visible)))
            raise IncompleteChat("Duplicate visible message IDs")
        if visible_before and visible and not visible_before.intersection(visible):
            page_event(page, "capture_anomaly", dict(step=step, reason="non_overlapping_windows", previous_ids=sorted(visible_before)[:5], visible_ids=snapshot["visible"][:5]))
            raise IncompleteChat("Non-overlapping virtualized windows; history gap possible")
        visible_before = visible or visible_before
        if not sidebar:
            page.backup_visible = visible_before
        geometry = await page.evaluate(SCROLL, dict(sidebar=sidebar, reset=step == 0, direction=0))
        signature = digest([captured, geometry])
        stable = stable + 1 if signature == last else 0
        last = signature
        boundary = geometry["top"] <= 1 if direction < 0 else geometry["top"] + geometry["viewport"] >= geometry["height"] - 2
        anchor = unchanged_anchor(captured, anchor_previous) if anchor_previous and not snapshot["busy"] else None
        if step % 20 == 0 or stable == 3 or (stable >= 3 and not snapshot["busy"]):
            page_event(page, "scroll_checkpoint", dict(sidebar=sidebar, direction=direction, step=step, captured=len(captured), visible=len(visible), stable=stable, boundary=boundary, busy=snapshot["busy"], geometry=geometry, duration_ms=round((time.monotonic() - started) * 1000)))
        if step % 20 == 0:
            print(f'  direction={"up" if direction < 0 else "dn"} step={step:03}/{max_steps:03} captured={len(captured):03} elapsed={duration(time.monotonic() - started)}', file=sys.stderr, flush=True)
        if anchor:
            if stable >= 3:
                result = dict(steps=step + 1, boundary=boundary, count=len(captured), expanded_prompts=expanded_total, duration_ms=round((time.monotonic()-started)*1000), anchor_id=anchor)
                page_event(page, "scroll_anchor", result)
                return result
            await asyncio.sleep(1)  # Confirm the anchor after hydration without scrolling past it.
            continue
        if stable >= 3 and not snapshot["busy"]:
            if boundary:
                result = dict(steps=step + 1, boundary=True, count=len(captured), expanded_prompts=expanded_total, duration_ms=round((time.monotonic() - started) * 1000))
                page_event(page, "scroll_finish", dict(result, sidebar=sidebar, direction=direction))
                return result
            raise IncompleteChat("Scrolling plateau away from boundary; scan incomplete")
        await page.evaluate(SCROLL, dict(sidebar=sidebar, reset=False, direction=direction))
        await asyncio.sleep(0.7 if not boundary else 1)
    raise IncompleteChat(f"Scroll budget exhausted after {max_steps} steps; scan incomplete")


def select(catalog, conversations, name, rescan, limit, today):
    wanted = {identity(c) for c in conversations}
    candidates = [(cid, c) for cid, c in catalog.items() if (not wanted or cid in wanted) and name.casefold() in c["title"].casefold()]
    if not wanted and not rescan:
        candidates = [(cid, c) for cid, c in candidates if (c.get("pending") or c.get("checked", "") < today or c.get("changed")) and (not c.get("pending") or time.time() - c.get("attempted", 0) >= 900)]
    return sorted(candidates, key=lambda pair: (not pair[1].get("changed", False), pair[1].get("rank", 1_000_000) if pair[1].get("changed") else 1_000_000, pair[1].get("checked", "")))[:limit]


def selection_counts(catalog, conversations, name, rescan, limit, today):
    matching = select(catalog, conversations, name, True, len(catalog), today)
    due = sum(bool(conversations or rescan or c.get("pending") or c.get("checked", "") < today or c.get("changed")) for _, c in matching)
    eligible = len(select(catalog, conversations, name, rescan, len(catalog), today))
    return dict(known=len(catalog), selected=min(limit, eligible), due=due,
                deferred_limit=max(0, eligible-limit), cooldown=due-eligible,
                not_due=len(matching)-due, filtered=len(catalog)-len(matching))


def discovery_due(discovery: dict, rescan: bool = False) -> bool:
    return rescan or time.time() - discovery.get("attempted", 0) >= 900


async def run(cdp_url, out_dir, conversations, name, rescan, limit, dry_run, output_format, scroll_steps, markdown_dir=None):
    cache = Path.home() / ".cache/sanand-scripts/backupchatgpt"
    # Keep the namespace when the same archive is mounted under another home alias.
    marker = out_dir / ".backupchatgpt-state"
    state_key = marker.read_text().strip() if marker.exists() else digest(str(out_dir.resolve()))[:16]
    if not re.fullmatch(r"[a-f0-9]{16}", state_key):
        raise ValueError(f"Invalid cache namespace in {marker}")
    state_path = cache / state_key / "catalog.json"
    catalog = json.loads(state_path.read_text()) if state_path.exists() else {}
    discovery_path = state_path.with_name("discovery.json")
    discovery = json.loads(discovery_path.read_text()) if discovery_path.exists() else {}
    trace = obs.new_run("backupchatgpt", cache_dir=cache, args=obs.sanitize_args(dict(conversation=conversations, name=name, limit=limit, rescan=rescan, dry_run=dry_run, cdp_url=cdp_url, out_dir=out_dir, scroll_steps=scroll_steps, markdown_dir=markdown_dir)))
    trace.counters.update(script_file=str(Path(__file__).resolve()), script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    trace.event("script_source", trace.counters)
    def persist():
        if not dry_run:
            atomic(state_path, encoded(catalog) + "\n")
    def discovered(chats):
        for rank, chat in enumerate(chats):
            cid = identity(chat["url"])
            old = catalog.get(cid, {})
            catalog[cid] = dict(old, **chat, rank=rank, seen=trace.run_id,
                                changed=old.get("changed", False) or old.get("title") != chat["title"] or rank < old.get("rank", rank))
        persist()
    today = dt.datetime.now(dt.UTC).date().isoformat()
    active_id = None
    context = dict(stage="preflight")
    completed = 0
    failed = 0
    attempted = 0
    consecutive_load_failures = 0
    failures = []
    selected = []
    chat_started = time.monotonic()
    candidate = []
    def capture_candidate(messages):
        nonlocal candidate
        candidate = messages
    def publish(path, cid, title, rows, started=None):
        if markdown_dir is not None and not dry_run:
            metrics = dict(message_stats(rows), duration_ms=round((time.monotonic() - started) * 1000) if started is not None else 0)
            result = publish_markdown(path.with_suffix(".md"), cid, title, markdown_dir, markdown_files, catalog[cid].get("markdown", {}), metrics)
            catalog[cid]["markdown"] = {k: result[k] for k in ("hash", "file", "directory")}
            trace.event("markdown_publication", dict(conversationId=cid, changed=result["changed"], archived_names=len(result["removed"]), markdown_bytes=result["bytes"], **metrics))
            persist()
            return result
    def incomplete(exc):
        if active_id and catalog[active_id].get("pending"):
            catalog[active_id]["error"] = str(exc) or type(exc).__name__
            catalog[active_id]["error_context"] = dict(context, run_id=trace.run_id, observed_messages=len(candidate))
            if candidate and not dry_run:
                partial = out_dir / ".incomplete" / active_id / digest(candidate)
                atomic(partial.with_suffix(".jsonl"), "".join(encoded(r) + "\n" for r in records(candidate, active_id)))
                atomic(partial.with_suffix(".json"), encoded(dict(status="incomplete", reason=str(exc) or type(exc).__name__, run_id=trace.run_id, **context, **message_stats(candidate))) + "\n")
        persist()
    paths = {}
    try:
        markdown_files = markdown_index(markdown_dir) if markdown_dir is not None else {}
        if not dry_run:
            for directory in dict.fromkeys([out_dir, *([markdown_dir] if markdown_dir is not None else [])]):
                directory.mkdir(parents=True, exist_ok=True)
                with tempfile.TemporaryFile(dir=directory):
                    pass
            atomic(marker, state_key + "\n")
        for path in out_dir.glob("*.jsonl"):
            cid = file_id(path)
            if cid in paths:
                raise ValueError(f"Duplicate canonical backups for {cid}; reconcile before running")
            paths[cid] = path
            rows = read_rows(path, cid)
            catalog.setdefault(cid, dict(title=cid, url=f"https://chatgpt.com/c/{cid}"))
            if path.with_suffix(".md").exists():
                publish(path, cid, rows[0].get("conversation", {}).get("title", catalog[cid]["title"]), rows)
        for cid, chat in catalog.items():
            if cid not in paths or not paths[cid].with_suffix(".md").exists():
                chat.update(checked="", changed=True)
        if not conversations and not discovery_due(discovery, rescan) and not select(catalog, [], name, False, limit, today):
            waiting = [cid for cid,c in catalog.items() if c.get("pending")]
            counts = selection_counts(catalog, [], name, False, limit, today)
            trace.finish(dict(status="no-eligible-conversations", discovery_partial=True, pending=waiting, **counts))
            print(encoded(dict(type="run", status="no-eligible-conversations", skipped=len(catalog), pending=waiting, **counts, discovery_error=discovery.get("error"))) if output_format == "jsonl" else f"Run status=no-eligible-conversations known={len(catalog)} due={counts['due']} cooldown={counts['cooldown']} pending={len(waiting)} elapsed={duration(time.monotonic()-trace.started)} logs={trace.events_path}", flush=True)
            return
        async with AsyncExitStack() as pages:
            page = await pages.enter_async_context(owned_page(cdp_url))
            page.backup_trace = trace
            page.backup_context = context
            trace.event("browser", dict(browser_version=getattr(page, "browser_version", "")))
            print("Using automation-owned background tab", file=sys.stderr, flush=True)
            discovery_error = discovery.get("error")
            discovery_source = "cached"
            if not conversations and discovery_due(discovery, rescan):
                discovery_source = "live"
                discovery = dict(attempted=time.time(), attempted_day=today, scan_id=trace.run_id, error="interrupted-discovery", exhaustive=False)
                if not dry_run:
                    atomic(discovery_path, encoded(discovery) + "\n")
                context["stage"] = "discovery"
                await navigate(page, "https://chatgpt.com/")
                await page.evaluate("() => {window.__backupState=chatgptSidebarScraper.createScraperState();}")
                discovery_error = None
                try:
                    await sweep(page, True, -1, scroll_steps, discovered)
                    await sweep(page, True, 1, scroll_steps, discovered)
                    if await page.evaluate('() => /Unable to load history/i.test(document.querySelector(\'nav[aria-label="Chat history"]\')?.innerText||"")'):
                        discovery_error = "sidebar-history-load-error"
                except IncompleteChat as exc:
                    discovery_error = str(exc)
                if not dry_run:
                    atomic(discovery_path, encoded(dict(discovery, error=discovery_error)) + "\n")
            missing = sum(c.get("seen") != discovery.get("scan_id") for c in catalog.values()) if discovery.get("scan_id") else None
            for chat in catalog.values():
                chat["sidebar_status"] = ("observed" if chat.get("seen") == discovery["scan_id"] else "not-observed") if discovery.get("scan_id") else "not-checked"
            trace.event("discovery", dict(known=len(catalog), not_observed=missing, partial=True, source=discovery_source, error=discovery_error))
            print(f"Partial sidebar discovery source={discovery_source}: {len(catalog)} known; unobserved={missing if missing is not None else 'not checked'}; {discovery_error or 'no exhaustive coverage claim'}", file=sys.stderr, flush=True)
            for value in conversations:
                cid = identity(value)
                catalog.setdefault(cid, dict(title=cid, url=value if "://" in value else f"https://chatgpt.com/c/{cid}"))
            persist()
            selected = select(catalog, conversations, name, rescan, limit, today)
            counts = selection_counts(catalog, conversations, name, rescan, limit, today)
            trace.event("selection", dict(counts, skipped=len(catalog)-len(selected)))
            print(f"Selected conversations={len(selected)} " + " ".join(f"{k}={counts[k]}" for k in ("known", "due", "deferred_limit", "cooldown", "not_due", "filtered")), file=sys.stderr, flush=True)
            for position, (cid, chat) in enumerate(selected, 1):
                active_id, candidate = None, []
                context.update(stage="opening-tab", position=position)
                if getattr(page, "url", "") and not getattr(page, "backup_keep_open", False) and await page.evaluate(f"() => ({GENERATION_ACTIVE})"):
                    page.backup_keep_open = True
                if getattr(page, "backup_keep_open", False):
                    last_navigation = getattr(page, "last_navigation", 0)
                    await pages.aclose()
                    page = await pages.enter_async_context(owned_page(cdp_url))
                    page.last_navigation = last_navigation
                    page.backup_trace, page.backup_context = trace, context
                try:
                    active_id = cid
                    candidate = []
                    chat_started = time.monotonic()
                    previous = read_rows(paths[cid], cid) if cid in paths else []
                    incremental = bool(previous) and not rescan and chat.get("prompt_expansion_checked", False)
                    context.update(conversationId=cid, position=position, total=len(selected), stage="opening")
                    trace.event("conversation_start", dict(context, expected_url=chat["url"], previous_messages=len(previous), incremental=incremental))
                    print(f"Scanning ID={cid} ({position}/{len(selected)}) mode={'incremental' if incremental else 'full'} run_elapsed={duration(time.monotonic() - trace.started)}", file=sys.stderr, flush=True)
                    if previous and not rescan and not chat.get("prompt_expansion_checked"):
                        print("  Full scan verifies prompt expansion before prefix reuse", file=sys.stderr, flush=True)
                    chat.update(attempted=time.time(), pending=True, error="interrupted-before-validation")
                    persist()
                    attempted = position
                    await navigate(page, chat["url"], True)
                    consecutive_load_failures = 0
                    await page.evaluate("() => {window.__backupState=chatgptscraper.createScraperState(document);}")
                    page.backup_visible = set()
                    if incremental:
                        context["stage"] = "scroll-down"
                        await page.evaluate(SCROLL, dict(sidebar=False, reset=True, direction=0, edge="bottom"))
                        await asyncio.sleep(1)
                        down = await sweep(page, False, 1, scroll_steps, capture_candidate)
                        if not down["count"]:
                            raise IncompleteChat("Empty tail at bottom; prior backup retained")
                        context["stage"] = "scroll-up"
                        up = await sweep(page, False, -1, scroll_steps, capture_candidate, anchor_previous=previous)
                    else:
                        context["stage"] = "scroll-up"
                        up = await sweep(page, False, -1, scroll_steps, capture_candidate)
                        context["stage"] = "scroll-down"
                        down = await sweep(page, False, 1, scroll_steps, capture_candidate)
                    context["stage"] = "validation"
                    result = await page.evaluate("""() => {const messages=__backupState.messages;
                      const positions=new Map(messages.map((m,i)=>[m.id,i]));
                      return {messages,metadata:__backupState.metadata,orderValid:[...__backupState.successorsById].every(([id,next])=>[...next].every(n=>positions.get(id)<positions.get(n)))};}""")
                    if not result["orderValid"]:
                        raise IncompleteChat("Conflicting observed message ordering")
                    title = result["metadata"]["title"]
                    if title == "ChatGPT Conversation":
                        title = chat["title"]
                    path = paths.get(cid, out_dir / filename(title, cid))
                    anchor = up.get("anchor_id")
                    reused = 0
                    expected_prefix = previous
                    if anchor:
                        reused = next(i for i,m in enumerate(previous) if m["id"] == anchor)
                        result["messages"] = merge_tail(previous, result["messages"], anchor)
                        expected_prefix = previous[:reused+1]
                        trace.event("prefix_reused", dict(context, anchor_id=anchor, reused_messages=reused, captured_messages=up["count"], prefix_assumption=True))
                        print(f"  anchor={anchor} reused={reused:03} captured={up['count']:03}", file=sys.stderr, flush=True)
                    timestamps = {r["id"]: r["timestamp"] for r in previous if "timestamp" in r}
                    for message in result["messages"]:
                        if message["id"] in timestamps:
                            message.setdefault("timestamp", timestamps[message["id"]])
                    metadata = dict(result["metadata"], title=title, date=(previous[0].get("conversation", {}).get("date") if previous else None) or chat.get("date", result["metadata"]["date"]))
                    if identity(metadata["source"]) != cid:
                        raise IncompleteChat("Scraper metadata belongs to a different conversation")
                    rows = records(result["messages"], cid, metadata)
                    missing_ids = {r["id"] for r in previous}-{r["id"] for r in rows}
                    validation = dict(context, **message_stats(rows), previous_messages=len(previous), missing_previous_ids=len(missing_ids), missing_id_sample=sorted(missing_ids)[:5], order_valid=result["orderValid"], content_hash=digest(rows), previous_content_hash=digest(previous))
                    trace.event("validation_start", validation)
                    validate(rows, expected_prefix)
                    trace.event("validation", validation)
                    markdown = await page.evaluate("({rows,metadata}) => chatgptscraper.messagesToMarkdown(rows,metadata)", dict(rows=rows, metadata=metadata))
                    if await page.evaluate(f"() => ({GENERATION_ACTIVE})"):
                        raise IncompleteChat("Generation started during extraction; deferred without publishing")
                    context["stage"] = "writing"
                    trace.event("write_start", dict(context, markdown_bytes=len(markdown.encode())))
                    changed = False if dry_run else save(path, rows, markdown, title)
                    context["stage"] = "publication"
                    publication = publish(out_dir / filename(title, cid), cid, title, rows, chat_started)
                    coverage = "matched-prefix+rendered-tail" if anchor else "rendered-boundaries"
                    chat.update(title=title, url=metadata["source"], checked=today, changed=False, pending=False, error=None, date=metadata["date"], coverage=coverage, prompt_expansion_checked=True, messages=len(rows), contentHash=digest(rows))
                    chat.pop("error_context", None)
                    persist()  # Commit each chat, so interruption resumes from remaining/oldest chats.
                    completed += 1
                    summary = dict(conversationId=cid, position=position, total=len(selected), status="validated", coverage=coverage, expanded_prompts=up.get("expanded_prompts", 0)+down.get("expanded_prompts", 0), reused_messages=reused, captured_messages=up["count"] if anchor else len(rows), **message_stats(rows), changed=changed, shared_status="disabled" if markdown_dir is None else "dry-run" if dry_run else "updated" if publication["changed"] else "unchanged", dry_run=dry_run, duration_ms=round((time.monotonic()-chat_started)*1000), markdown_bytes=len(markdown.encode()), jsonl_bytes=sum(len((encoded(r)+"\n").encode()) for r in rows), timestamps=sum("timestamp" in r for r in rows), up=up, down=down)
                    trace.event("conversation", summary)
                    print(encoded(summary) if output_format == "jsonl" else result_line(summary), flush=True)
                except IncompleteChat as exc:
                    failed += 1
                    consecutive_load_failures = consecutive_load_failures + 1 if isinstance(exc, ChatLoadFailure) else 0
                    incomplete(exc)
                    page.backup_keep_open = True
                    remaining = len(selected)-position
                    failure = dict(context, completed=completed, failed=failed, consecutive_load_failures=consecutive_load_failures, pending_count=len(selected)-completed, unattempted=remaining, observed_messages=len(candidate), error=str(exc), duration_ms=round((time.monotonic()-chat_started)*1000))
                    failures.append(failure)
                    trace.event("conversation_incomplete", failure)
                    action = "stopping after repeated load failures" if consecutive_load_failures >= 2 else "continuing" if remaining else "batch finished with pending chats"
                    print(f"Incomplete ID={cid} ({position}/{len(selected)}) stage={context['stage']} reason={exc} completed={completed} failed={failed} unattempted={remaining}; {action}", file=sys.stderr, flush=True)
                    if output_format == "jsonl":
                        print(encoded(dict(type="conversation", status="incomplete", **failure)), flush=True)
                    if consecutive_load_failures >= 2:
                        raise RuntimeError(f"Stopping after {consecutive_load_failures} consecutive conversation load failures; retry later. Latest: {exc}") from exc
            context["stage"] = "closing-tab"
        flagged = [cid for cid,c in catalog.items() if c.get("pending")]
        due_remaining = selection_counts(catalog, [], "", False, len(catalog), today)["due"]
        trace.finish(dict(status="incomplete" if failed else "partial", conversations=completed, completed=completed, failures=failures, failed=failed, unattempted=0, due_remaining=due_remaining, pending_count=len(selected)-completed, flagged_pending_count=len(flagged), selected=len(selected), discovery_partial=True, discovery_error=discovery_error))
        if output_format == "jsonl":
            print(encoded(dict(type="run", status="incomplete" if failed else "partial", failures=failures, failed=failed, unattempted=0, due_remaining=due_remaining, sidebar_exhaustive=False, discovery_error=discovery_error, selected=len(selected), completed=completed, pending_count=len(selected)-completed, flagged_pending_count=len(flagged), duration_ms=round((time.monotonic()-trace.started)*1000), skipped=len(catalog)-len(selected), pending=flagged)), flush=True)
        else:
            print(f"Run status={'incomplete' if failed else 'partial'} completed={completed}/{len(selected)} failed={failed} unattempted=0 due_remaining={due_remaining} pending={len(selected)-completed} flagged_pending={len(flagged)} elapsed={duration(time.monotonic()-trace.started)} logs={trace.events_path}", flush=True)
    except BaseException as exc:
        incomplete(exc)
        failure = dict(context, completed=completed, failed=failed, failures=failures, consecutive_load_failures=consecutive_load_failures, due_remaining=selection_counts(catalog, [], "", False, len(catalog), today)["due"], selected=len(selected), pending_count=len(selected)-completed, flagged_pending_count=sum(bool(c.get("pending")) for c in catalog.values()), unattempted=len(selected)-attempted, observed_messages=len(candidate), conversation_duration_ms=round((time.monotonic()-chat_started)*1000))
        trace.exception(exc, **failure)
        trace.finish(dict(status="failed", error_type=type(exc).__name__, error_message=str(exc), **failure))
        print(f'Incomplete ID={active_id or "none"} ({context.get("position", 0)}/{len(selected)}) stage={context["stage"]} completed={completed} failed={failed} pending={failure["pending_count"]} unattempted={failure["unattempted"]} flagged_pending={failure["flagged_pending_count"]} due_remaining={failure["due_remaining"]} elapsed={duration(time.monotonic()-chat_started)} logs={trace.events_path}', file=sys.stderr, flush=True)
        if output_format == "jsonl":
            print(encoded(dict(type="run", status="incomplete", error=str(exc) or type(exc).__name__, pending=[cid for cid,c in catalog.items() if c.get("pending")], **failure)), flush=True)
        raise

    return failed


@app.command(help=__doc__)
def main(
    conversation: list[str] = typer.Option([], "--conversation", help="Repeatable conversation URL or UUID; bypass daily schedule."),
    name: str = typer.Option("", help="Case-insensitive title substring."),
    rescan: bool = typer.Option(False, help="Full history scan without the anchor shortcut; refresh sidebar, bounded by --limit."),
    limit: int = typer.Option(20, "--limit", "-n", min=1),
    dry_run: bool = typer.Option(False, help="Extract/validate without writing backups or discovery state; logs still written."),
    cdp_url: str = typer.Option("http://localhost:9222"),
    out_dir: Path = typer.Option(Path.home() / "Documents/data/chatgpt"),
    markdown_dir: Path = typer.Option(Path.home() / "Documents/chatgpt", help="Shared Markdown folder, using chatgpt-to-markdown filenames; keep separate from --out-dir."),
    format: str = typer.Option("text", help="text (TSV) or jsonl."),
    scroll_steps: int = typer.Option(300, min=5, help="Maximum steps per scroll direction; exhaustion is incomplete."),
    describe: bool = typer.Option(False, "--describe"),
):
    if describe:
        from typer.main import get_command
        print(encoded(dict(command="backupchatgpt", parameters=[dict(name=p.name, flags=p.opts+p.secondary_opts, type=p.type.name, multiple=p.multiple, default=str(p.default) if isinstance(p.default, Path) else p.default, help=p.help) for p in get_command(app).params], output="Conversation summaries plus final run record; canonical JSONL preserves scraper messages plus conversation metadata, conversationId and contentHash", coverage="Partial sidebar, current rendered branch only; no timestamp API", sources=[str(SCRAPERS / n) for n in SOURCES])))
        return
    if format not in {"text", "jsonl"}:
        raise typer.BadParameter("--format must be text or jsonl")
    os.umask(0o077)
    for value in conversation:
        identity(value)
    # A single process owns state/output, including custom output directories.
    lock_dir = Path.home() / ".cache/sanand-scripts/backupchatgpt"
    lock_dir.mkdir(parents=True, exist_ok=True)
    with (lock_dir / "run.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if markdown_dir.expanduser().resolve() == out_dir.expanduser().resolve():
                raise ValueError("--markdown-dir must be separate from the canonical --out-dir")
            failed = asyncio.run(run(cdp_url, out_dir.expanduser(), conversation, name, rescan, limit, dry_run, format, scroll_steps, markdown_dir.expanduser()))
        except (OSError, ValueError, RuntimeError, TimeoutError) as exc:
            print(f"backupchatgpt: {exc}", file=sys.stderr, flush=True)
            raise typer.Exit(1) from exc
        if failed:
            raise typer.Exit(1)


if __name__ == "__main__":
    app()
