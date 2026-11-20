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
Interrupted Work activity without a message ID uses a labelled local prompt-based ID.
Full scans retain a hidden saved prefix only when the entire saved suffix is observed.
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
from collections import defaultdict
from contextlib import AsyncExitStack, asynccontextmanager
import datetime as dt
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import tempfile
from urllib.parse import urlsplit
from urllib.request import urlopen
from uuid import UUID

import typer
import websockets

from archive.backupwhatsapp import CDPPage, cdp_http_base
from chatgpt_streams import ROOT, captured_turns, replay_branch
import sanand_observability as obs

app = typer.Typer(add_completion=False, help=__doc__)
SCRAPERS = Path(__file__).resolve().parent.parent / "tools" / "aiscrapers"
RAW_DIR = Path.home() / "Documents/data/anand-chrome-tools/chatgpt-raw"
CONVERTER = Path(__file__).resolve().parent.parent / "chatgpt-to-markdown/chatgpt-to-markdown.js"
SOURCES = ("chatgptscraper.js", "chatgpt-sidebar-scraper.js")
UUID_PATTERN = r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}"
LOCAL_ACTIVITY_PATTERN = rf"local-activity:({UUID_PATTERN}):(0|[1-9][0-9]*)"


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
    if first["id"].startswith("local-activity:"):
        return None  # A locally derived position is not an immutable message ID.
    old = next((m for m in previous if m["id"] == first["id"]), None)
    if old and all(first.get(k) == old.get(k) for k in ("id", "role", "content", "parts")):
        return first["id"]
    return None


def merge_tail(previous: list[dict], messages: list[dict], anchor: str) -> list[dict]:
    if unchanged_anchor(messages, previous) != anchor:
        raise IncompleteChat("Incremental anchor changed; prior backup retained")
    index = next(i for i,m in enumerate(previous) if m["id"] == anchor)
    return previous[:index] + messages


def full_scan_prefix(previous: list[dict], messages: list[dict]) -> int:
    """Reuse a hidden prefix only when the entire saved suffix is still visible."""
    anchor = unchanged_anchor(messages, previous)
    if not anchor:
        return 0
    index = next(i for i, row in enumerate(previous) if row['id'] == anchor)
    suffix = [row['id'] for row in previous[index:]]
    return index if [row['id'] for row in messages[:len(suffix)]] == suffix else 0


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


def markdown_version(path: Path) -> tuple[float | None, bool]:
    """Read the source version from converter metadata, including older exports."""
    with path.open("rb") as stream:
        header = stream.read(8192).decode("utf-8-sig", errors="replace")
    header = header.replace("\r\n", "\n")
    if header.startswith("---\n"):
        header = header.split("\n---", 1)[0]
        match = re.search(r"^date: (.+)$", header, re.M)
        if match:
            try:
                date = dt.datetime.fromisoformat(match[1].strip('"'))
                if date.tzinfo:
                    return date.timestamp(), 'capture: "stream-replay"' in header.splitlines()
            except ValueError:
                pass
    else:
        # Legacy exports show local time rounded to minutes. Protect the whole minute.
        header = re.split(r"\n#+ (?:User|Assistant|ChatGPT)\s*\r?\n", header, maxsplit=1)[0]
        match = re.search(r"^- Updated: (.+)$", header, re.M)
        if match:
            try:
                return dt.datetime.strptime(match[1], "%b %d, %Y, %I:%M %p").timestamp() + 60, False
            except ValueError:
                pass
    return None, False


def markdown_blocks(version: tuple[float | None, bool], source_time: float, *, native: bool) -> bool:
    updated, replay = version
    if updated is None:
        return True
    if native and replay and abs(updated - source_time) <= .001:
        return False
    return updated >= source_time - .001


def markdown_stem(title: str, cid: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", " ", title).strip() or cid


def retitle_markdown(data: bytes, title: str) -> bytes:
    """Change only the title in recognized frontmatter or the legacy export heading."""
    if data.removeprefix(b"\xef\xbb\xbf").startswith((b"---\n", b"---\r\n")):
        header = re.split(rb"\r?\n---(?:\r?\n|$)", data, maxsplit=1)[0]
        match = re.search(rb"^title: [^\r\n]*", header, re.M)
        line = f"title: {encoded(title)}".encode()
    else:
        match = re.match(rb"(?:\xef\xbb\xbf)?(# [^\r\n]*)", data)
        line = f"# {' '.join(title.splitlines())}".encode()
        if match:
            start, end = match.span(1)
            return data[:start] + line + data[end:]
    return data[:match.start()] + line + data[match.end():] if match else data


def publish_markdown(canonical: Path, cid: str, title: str, directory: Path, index: dict, previous: dict,
                     metrics: dict | None = None, *, source_time: float | None = None,
                     rename_only: bool = False, dry_run: bool = False, revision_root: Path | None = None,
                     native: bool = False) -> dict:
    """Publish by UUID, preserving the best local transcript for metadata-only renames."""
    matches = [p for p, owner in index.items() if owner == cid]
    base = markdown_stem(title, cid)
    compatible = [p for p in matches if re.fullmatch(re.escape(base) + r"(?: \(\d+\))?", p.stem)]
    if rename_only:
        versions = {p: markdown_version(p)[0] for p in matches}
        if not source_time or not title.strip() or title.strip().casefold() in {"new chat", "untitled"}:
            return dict(changed=False, held=True)
        current = [p for p, t in versions.items() if t is not None and abs(t - source_time) <= .001]
        if len(current) != 1 or any(t is None or t > source_time + .001 for t in versions.values()):
            return dict(changed=False, held=True)
        original = current[0].read_bytes()
        data = retitle_markdown(original, title)
        if data == original and len(compatible) == len(matches):
            return dict(changed=False, held=True)
    else:
        if source_time is not None and any(markdown_blocks(v, source_time, native=native) for v in map(markdown_version, matches)):
            return dict(changed=False, held=True)
        data = canonical.read_bytes()
    fingerprint = hashlib.sha256(data).hexdigest()
    location = str(directory.resolve())
    if previous.get("hash") == fingerprint and previous.get("directory") == location and matches and not rename_only:
        return dict(previous, file=matches[0].name, changed=False, removed=[], bytes=len(data))
    target = compatible[0] if compatible else directory / f"{base}.md"
    count = 0
    while True:
        # Match NTFS case-insensitive semantics even when running on ext4.
        other = next((p for p in index if p.name.casefold() == target.name.casefold()), None)
        if other is None:
            break
        if index[other] == cid:
            if target.exists():
                target = other
            break
        count += 1
        target = directory / f"{base} ({count}).md"
    if len(target.name.encode()) > 255:
        raise ValueError("Title exceeds the converter's filename limit; shorten the chat title")
    if dry_run:
        return dict(changed=True, file=target.name)
    revision_root = revision_root or (directory if source_time is not None else canonical.parent) / ".revisions"
    removed = []
    for path in dict.fromkeys([*matches, target]):
        if not path.exists():
            continue
        if markdown_owner(path) != cid:
            raise ValueError(f"Markdown identity changed during publication: {path}; stop the converter and retry")
        old = path.read_bytes()
        if old != data or path != target:
            revision = revision_root / cid / f"shared-{digest([str(path), hashlib.sha256(old).hexdigest()])}"
            atomic(revision.with_suffix(".md"), old)
            atomic(revision.with_suffix(".json"), encoded(dict(source=str(path), conversationId=cid)) + "\n")
    if metrics:
        details = f'elapsed={duration(metrics["duration_ms"] / 1000)} prompts={metrics["prompts"]} messages={metrics["messages"]} markdown={size(len(data))}'
        print(f"Publishing local Markdown ID={cid} ({details})", file=sys.stderr, flush=True)
    changed = atomic(target, data)
    index[target] = cid
    for path in matches:
        if path != target:
            path.unlink()  # Exact prior bytes were archived above.
            index.pop(path)
            removed.append(path.name)
    return dict(hash=fingerprint, file=target.name, directory=location, changed=changed or bool(removed), removed=removed, bytes=len(data))


def raw_snapshot(path: Path) -> tuple[bytes, dict, dict]:
    """Validate the identity and write pair without waiting for the extension."""
    data = path.read_bytes()
    info = json.loads(path.with_suffix(".backup.json").read_bytes())
    value = json.loads(data)
    if (not isinstance(value, dict) or not isinstance(info, dict) or
        info.get("hash") != hashlib.sha256(data).hexdigest() or
        value.get("conversation_id", value.get("id")) != path.stem or value.get("is_temporary_chat")):
        raise ValueError("Snapshot identity or sidecar hash mismatch")
    return data, value, info


def raw_messages(snapshot: dict, *, complete: bool = False) -> list[dict]:
    messages = snapshot.get("messages")
    tip = snapshot.get("current_node")
    if complete and not tip:
        raise ValueError("Snapshot has no active tip")
    if messages is None:
        nodes = snapshot.get("mapping", {})
        messages = []
        node_id = tip
        visited = set()
        while node_id in nodes and node_id not in visited:
            visited.add(node_id)
            node = nodes[node_id]
            if node.get("message") is not None:
                messages.append(node["message"])
            node_id = node.get("parent")
        if complete and node_id is not None:
            raise ValueError("Snapshot has a broken active branch")
        messages.reverse()
    elif complete and (not messages or messages[-1].get("id") != tip or
                       any(snapshot.get("page_info", {}).get(k) is not False
                           for k in ("has_previous_page", "has_next_page"))):
        raise ValueError("Snapshot has an incomplete active branch")
    return messages


def raw_has_reply(snapshot: dict, prompt_ids: set[str]) -> bool:
    seen_prompt = False
    for message in raw_messages(snapshot):
        seen_prompt = seen_prompt or message.get("id") in prompt_ids
        if (seen_prompt and message.get("status") == "finished_successfully" and
            not message.get("metadata", {}).get("is_visually_hidden_from_conversation") and
            message.get("channel") == "final" and message.get("author", {}).get("role") in {"assistant", "tool"}):
            return True
    return False


def unfinished_snapshot(messages: list[dict], tip: str | None) -> str | None:
    # Older sidecars could mark an unfilled final image as a complete branch.
    if any(m.get("author", {}).get("role") == "tool" and m.get("channel") == "final" and
           m.get("content", {}).get("content_type") == "multimodal_text" and m["content"].get("parts") == []
           for m in messages):
        return "img"
    tip_message = next((m for m in messages if m.get("id") == tip), {})
    if tip_message.get("status") == "in_progress":
        return "img" if "image_gen_estimated_duration_ms" in (tip_message.get("metadata") or {}) else "wip"
    return None


def snapshot_observations(raw_dir: Path) -> dict:
    observations = defaultdict(list)
    for path in (raw_dir / "observations").glob("*.json"):
        try:
            obs = json.loads(path.read_bytes())
            if (obs["format"] == 1 and re.fullmatch(UUID_PATTERN, obs["id"]) and
                re.fullmatch(r"[0-9a-f]{64}", obs["hash"]) and type(obs["tabId"]) is int and
                type(obs["startedAt"]) is int and type(obs["finishedAt"]) is int and
                0 < obs["startedAt"] <= obs["finishedAt"] and isinstance(obs["query"], dict) and
                isinstance(obs["path"], str) and isinstance(obs["queryKeys"], list) and
                all(isinstance(key, str) for key in obs["queryKeys"])):
                observations[obs["id"]].append(obs)
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return observations


def cursor_window(raw_dir: Path, cid: str, obs: dict, *, older: bool) -> dict | None:
    path = raw_dir / "versions" / cid / f"{obs['hash']}.json"
    try:
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != obs["hash"]:
            return None
        value = json.loads(data)
        page, messages = value["page_info"], value["messages"]
        if (value.get("conversation_id", value.get("id", cid if older else None)) == cid and
            not value.get("is_temporary_chat") and "mapping" not in value and
            isinstance(messages, list) and messages and
            all(isinstance(m.get("id"), str) and m["id"] and isinstance(m.get("content"), dict) for m in messages) and
            page["start_cursor"] == messages[0]["id"] and page["end_cursor"] == messages[-1]["id"] and
            type(page["has_previous_page"]) is bool and page["has_next_page"] is older):
            return value
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        pass
    return None


def recover_cursor_pages(raw_dir: Path, cid: str, observations: list[dict], previous: dict, source_time: float, update: float) -> tuple[dict | None, str | None]:
    """Reconstruct one observed active branch while preserving the native captures."""
    base_pattern = rf"/backend-api/conversations?/{cid}"
    bases = [obs for obs in observations if re.fullmatch(base_pattern, obs["path"])]
    dated = [obs for obs in bases if type(obs.get("updateTime")) in (int, float) and
             math.isfinite(obs["updateTime"]) and obs["updateTime"] > 0 and
             obs["updateTime"] >= source_time and obs["updateTime"] + 1 >= update]
    if not dated:
        return None, None
    newest = max(dated, key=lambda obs: (obs["updateTime"], obs["startedAt"]))
    if newest.get("coverage") in {"tree", "branch"}:
        decision = newest.get("decision")
        held = decision and decision not in {"promote", "unchanged", "reviewed"}
        return None, f"Newer snapshot preserved in version history ({decision})" if held else None
    if not isinstance(previous.get("messages"), list):
        return None, None
    if set(newest["queryKeys"]) != newest["query"].keys() or newest["query"].keys() - {"num_turns", "include_has_versions"}:
        return None, None
    head = cursor_window(raw_dir, cid, newest, older=False)
    if (not head or not head["page_info"]["has_previous_page"] or head.get("update_time") != newest["updateTime"] or
        head.get("current_node") != head["messages"][-1]["id"]):
        return None, None

    recovered = None
    for anchor in dated:
        if (anchor["updateTime"] != newest["updateTime"] or set(anchor["queryKeys"]) != anchor["query"].keys() or
            anchor["query"].keys() - {"num_turns", "include_has_versions"}):
            continue
        base = head if anchor["hash"] == newest["hash"] else cursor_window(raw_dir, cid, anchor, older=False)
        # The same window may be served again with different advisory URL metadata.
        if not base or any(base.get(k) != head.get(k) for k in ("messages", "current_node", "page_info", "update_time")):
            continue
        # A new base request in this tab may switch versions, even for the same conversation.
        visit_end = min((other["startedAt"] for other in bases if other is not anchor and
                         other["tabId"] == anchor["tabId"] and other["startedAt"] >= anchor["startedAt"]), default=math.inf)
        pages = defaultdict(list)
        for obs in observations:
            if (obs["path"] == f"{anchor['path']}/messages" and obs["tabId"] == anchor["tabId"] and
                anchor["finishedAt"] <= obs["startedAt"] <= obs["finishedAt"] < visit_end and
                set(obs["queryKeys"]) == obs["query"].keys() and
                {key: val for key, val in obs["query"].items() if key != "before"} == anchor["query"] and
                isinstance(obs["query"].get("before"), str)):
                pages[obs["query"]["before"]].append(obs)
        windows = [base]
        seen = {m["id"] for m in base["messages"]}
        finished = anchor["finishedAt"]
        while windows[-1]["page_info"]["has_previous_page"]:
            cursor = windows[-1]["page_info"]["start_cursor"]
            options = [p for p in pages[cursor] if p["startedAt"] >= finished]
            if len({p["hash"] for p in options}) != 1:
                break
            obs = min(options, key=lambda p: p["finishedAt"])
            page = cursor_window(raw_dir, cid, obs, older=True)
            if (not page or page.get("current_node") not in (None, base["current_node"]) or
                page.get("update_time") not in (None, base["update_time"])):
                break
            ids = {m["id"] for m in page["messages"]}
            if len(ids) != len(page["messages"]) or ids & seen:
                break
            seen.update(ids)
            windows.append(page)
            finished = obs["finishedAt"]
        if windows[-1]["page_info"]["has_previous_page"]:
            continue
        messages = [m for page in reversed(windows) for m in page["messages"]]
        if len(seen) != len(messages) or unfinished_snapshot(messages, base["current_node"]):
            continue
        # Preserve the accepted branch in order, including content and attachment references.
        before = previous["messages"]
        before_ids = {m["id"] for m in before}
        shared = [m for m in messages if m["id"] in before_ids]
        attachments = ("attachments", "files", "files_v2", "sync_sources")
        fields = ("id", "content", "author", "channel", "recipient", "status", *attachments)
        metadata_fields = (*attachments, "is_visually_hidden_from_conversation")
        if len(before) != len(shared) or any(
            any(old.get(k) != new.get(k) for k in fields) or
            any((old.get("metadata") or {}).get(k) != (new.get("metadata") or {}).get(k) for k in metadata_fields)
            for old, new in zip(before, shared)
        ):
            return None, "Complete pages conflict with the accepted snapshot"
        if recovered and recovered["messages"] != messages:
            return None, "Conflicting older pages for the same snapshot"
        recovered = dict(head, messages=messages, page_info=dict(has_previous_page=False, has_next_page=False))
    return recovered, None if recovered else "No complete, consistent cursor chain in the saved pages"


def render_snapshot(data: bytes, replay: bool) -> bytes:
    render = subprocess.run(
        ["node", "--input-type=module", "-e",
         "import fs from 'node:fs'; const {renderSnapshot} = await import(process.argv[1]);"
         "process.stdout.write(renderSnapshot(JSON.parse(fs.readFileSync(0, 'utf8'))));",
         CONVERTER.as_uri()],
        input=data, capture_output=True, timeout=30,
    )
    if render.returncode:
        lines = render.stderr.decode(errors="replace").splitlines()
        detail = next((line for line in lines if line.startswith(("Error:", "TypeError:", "SyntaxError:"))), "No renderer diagnostic")
        raise ValueError(f"Markdown rendering failed: {detail}")
    if replay:
        return render.stdout.replace(b'\n---\n', b'\ncapture: "stream-replay"\n---\n', 1)
    return render.stdout


def preserves_transcript(path: Path, rendered: bytes) -> bool:
    """A stream replay may extend existing Markdown only if the visible prefix agrees."""
    original = path.read_bytes().replace(b"\r\n", b"\n")
    prefix = original.partition(b"\n---\n")[2].strip()
    body = rendered.partition(b"\n---\n")[2].strip()
    return bool(original.startswith(b"---\n") and prefix and (body == prefix or body.startswith(prefix + b"\n\n# ")))


def raw_backup(raw_dir: Path, markdown_dir: Path, dry_run: bool, output_format: str, *, verbose: bool = False) -> int:
    if not raw_dir.is_dir():
        raise ValueError(f"Raw capture directory is missing: {raw_dir}")
    if raw_dir.resolve() == markdown_dir.resolve():
        raise ValueError("Raw and Markdown directories must be separate")
    if not CONVERTER.is_file():
        raise ValueError(f"Markdown converter is missing: {CONVERTER}")
    catalog_path = raw_dir / "catalog.json"
    catalog = json.loads(catalog_path.read_text()) if catalog_path.is_file() else {}
    if not isinstance(catalog, dict):
        raise ValueError("Invalid ChatGPT capture catalog")
    catalog_times = {}
    catalog_titles = {}
    for cid, entry in catalog.items():
        update = entry.get("updateTime") if isinstance(entry, dict) else entry
        if not re.fullmatch(UUID_PATTERN, cid) or type(update) not in (int, float) or not math.isfinite(update) or update <= 0:
            raise ValueError("Invalid ChatGPT capture catalog")
        catalog_times[cid] = update
        title = entry.get("title") if isinstance(entry, dict) else None
        if isinstance(title, str) and title.strip():
            catalog_titles[cid] = title
    index = markdown_index(markdown_dir)
    owned = defaultdict(list)
    for path, owner in index.items():
        owned[owner].append(path)
    paths = {p.stem: p for p in raw_dir.glob("*.json") if re.fullmatch(UUID_PATTERN, p.stem)}
    turns = captured_turns(raw_dir / "events")
    observations = snapshot_observations(raw_dir)
    label_width = len("would-update" if dry_run else "missing")
    failures = 0
    with tempfile.TemporaryDirectory(prefix="chatgpt-render-") as tmp:
        for cid in sorted(paths.keys() | catalog_times.keys() | turns.keys()):
            path = paths.get(cid)
            matches = owned[cid]
            message = dict(conversationId=cid)
            catalog_title = catalog_titles.get(cid)
            title = catalog_title or (matches[0].stem if matches else "—")
            pending_label = "part"
            update = latest_update = catalog_times.get(cid, 0)
            try:
                versions = [markdown_version(p) for p in matches]
                replay = False
                ready = False
                if path is None:
                    status = "missing"
                    value, messages, source_time, tip = {}, [], 0, ROOT
                else:
                    data, value, info = raw_snapshot(path)
                    messages = raw_messages(value)
                    tip = value.get("current_node")
                    source_time = value.get("update_time")
                    if type(source_time) in (int, float) and math.isfinite(source_time):
                        latest_update = max(latest_update, source_time)
                    snapshot_title = value.get("title")
                    if isinstance(snapshot_title, str) and snapshot_title.strip() and (not catalog_title or latest_update > update):
                        title = snapshot_title
                    unfinished = unfinished_snapshot(messages, tip)
                    if info.get("coverage") == "partial" or unfinished == "img":
                        status = "deferred"
                        pending_label = unfinished or "part"
                    elif info.get("coverage") not in {"tree", "branch"} or type(source_time) not in (int, float) or not math.isfinite(source_time) or source_time <= 0 or source_time != info.get("updateTime"):
                        raise ValueError("Snapshot has no verified coverage or server update time")
                    else:
                        status = "stale-capture" if source_time + 1 < update else ""
                        ready = not status
                    if (not unfinished and status in {"deferred", "stale-capture"} and cid in observations and
                        type(source_time) in (int, float) and math.isfinite(source_time)):
                        assembled, reason = recover_cursor_pages(raw_dir, cid, observations[cid], value, source_time, update)
                        if assembled:
                            value = assembled
                            data = encoded(value).encode()
                            source_time, tip = value["update_time"], value["current_node"]
                            latest_update = max(latest_update, source_time)
                            title = value.get("title") or title
                            message["sourceType"] = "cursor-pages"
                            status, ready = "", True
                        elif reason:
                            message["reason"] = reason
                            if status == "deferred" and value.get("page_info", {}).get("has_previous_page") is True:
                                pending_label = "pages"
                if cid in turns and status != "deferred":
                    if path is not None:
                        messages = raw_messages(value, complete=True)
                    recovered = replay_branch(turns[cid], messages, tip, source_time, update)
                    if recovered:
                        messages, stream_title, source_time = recovered
                        title = catalog_title or stream_title or (title if title != "—" else cid)
                        value = dict(conversation_id=cid, title=title, update_time=source_time, messages=messages,
                                     current_node=messages[-1]["id"], page_info=dict(has_previous_page=False, has_next_page=False))
                        data = encoded(value).encode()
                        latest_update = max(latest_update, source_time)
                        message.pop("reason", None)
                        message["sourceType"] = "stream-replay"
                        ready = replay = True
                if status == "missing" and not replay and update and any(t is not None and t >= update - .001 for t, _ in versions):
                    continue
                if ready:
                    if any(markdown_blocks(v, source_time, native=not replay) for v in versions):
                        if replay:
                            status = "up-to-date" if all(t is not None for t, _ in versions) else "replay-held"
                            if status == "up-to-date" and not any(
                                is_replay and abs(t - source_time) <= .001 for t, is_replay in versions
                            ):
                                replay = False
                                del message["sourceType"]
                        else:
                            result = publish_markdown(path, cid, value.get("title") or "", markdown_dir, index, {},
                                                      source_time=source_time, rename_only=True, dry_run=dry_run)
                            if result["changed"]:
                                status = "would-rename" if dry_run else "renamed"
                                message["file"] = result["file"]
                            else:
                                status = "up-to-date" if all(t is not None for t, _ in versions) else "unknown-markdown-version"
                                if status == "unknown-markdown-version":
                                    files = ", ".join(p.name for p, (t, _) in zip(matches, versions) if t is None)
                                    message["warning"] = f"Check the update date in {files} before replacing the Markdown."
                    else:
                        output = render_snapshot(data, replay)
                        rendered = Path(tmp) / "render.md"
                        rendered.write_bytes(output)
                        if markdown_owner(rendered) != cid:
                            raise ValueError("Rendered Markdown identity mismatch")
                        if replay and not all(preserves_transcript(p, output) for p in matches):
                            status = "replay-held"
                            message["reason"] = "Existing Markdown does not match the recovered transcript prefix"
                        elif dry_run:
                            status = "would-update" if matches else "would-create"
                        else:
                            result = publish_markdown(rendered, cid, value.get("title") or cid, markdown_dir, index, {},
                                                      source_time=source_time, native=not replay)
                            status = "up-to-date" if result.get("held") else "updated" if matches else "created"
                            if result.get("file"):
                                message["file"] = result["file"]
            except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
                failures += 1
                status = "error"
                message["error"] = str(exc)
            message["status"] = status
            severity = "error" if "error" in message else "warning" if "warning" in message else None
            if severity:
                detail = " ".join(message[severity].splitlines())
                print(f"{severity}[chatcli-backup]: {cid} {detail}", file=sys.stderr, flush=True)
            if not (severity or verbose or (dry_run and status.startswith("would-"))):
                continue
            if verbose:
                if severity:
                    icon, label = "🔴", "check"
                elif status in {"deferred", "missing", "stale-capture", "replay-held"}:
                    icon, label = "🟡", {"deferred": pending_label, "missing": "missing",
                                         "stale-capture": "stale", "replay-held": "held"}[status]
                else:
                    icon, label = "🟢", status if status.startswith("would-") else "replay" if replay else "done"
                try:
                    updated_at = dt.datetime.fromtimestamp(latest_update, dt.UTC).isoformat().replace("+00:00", "Z") if latest_update else None
                except (OverflowError, OSError, ValueError):
                    updated_at = None
                message.update(label=label, updatedAt=updated_at, title=" ".join(title.split()))
            if output_format == "jsonl":
                print(encoded(message), flush=True)
            elif verbose:
                print(f"{icon} {label:<{label_width}}\t{cid}\t{updated_at or '—'}\t{message['title']}", flush=True)
            elif not severity:
                print(f"{cid}\t{status}\t{message.get('file', '')}", flush=True)
    return failures


def records(messages: list[dict], cid: str, metadata: dict | None = None) -> list[dict]:
    result = []
    for message in messages:
        payload = {k: v for k,v in message.items() if k not in {"contentHash", "conversationId"}}
        if metadata is not None:
            payload["conversation"] = metadata
        result.append(dict(payload, conversationId=cid, contentHash=digest(payload)))
    return result


def validate(rows: list[dict], previous: list[dict], activity_previous: list[dict] | None = None) -> None:
    if not rows:
        raise IncompleteChat("Empty extraction; previous backup retained")
    ids = [r["id"] for r in rows]
    if len(ids) != len(set(ids)):
        raise IncompleteChat("Duplicate message IDs")
    earlier_users = set()
    old_by_id = {row['id']: row for row in (previous if activity_previous is None else activity_previous)}
    if {mid for mid in old_by_id if mid.startswith('local-activity:')} - set(ids):
        raise IncompleteChat("Previously saved local activity missing; prior backup retained")
    for row in rows:
        local = re.fullmatch(LOCAL_ACTIVITY_PATTERN, row["id"])
        if local:
            if row.get("idSource") != "local-activity" or row["role"] != "assistant" or local.group(1) not in earlier_users:
                raise IncompleteChat("Local activity is missing its preceding prompt or provenance")
            old = old_by_id.get(row['id'])
            if old and any(row.get(k) != old.get(k) for k in ('role', 'content', 'parts', 'idSource')):
                raise IncompleteChat("Previously saved local activity changed; prior backup retained")
        else:
            try:
                UUID(row["id"])
            except ValueError as exc:
                raise IncompleteChat("Unstable/positional message ID; full immutable UUID required") from exc
        if row["role"] not in {"user", "assistant"} or not row["content"].strip():
            raise IncompleteChat("Invalid message role/content")
        if row['role'] == 'user':
            earlier_users.add(row['id'])
    previous_ids = {r["id"] for r in previous}
    if previous_ids - set(ids):
        raise IncompleteChat("Extraction missing previously saved IDs (incomplete history or changed branch); backup retained")
    if [i for i in ids if i in previous_ids] != [r["id"] for r in previous]:
        raise IncompleteChat("Previously saved messages reordered; backup retained")


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
    # A deliberately unanswered prompt is valid, but give replies the full load
    # window to hydrate before treating a user-only page as ready.
    if (conversation and injected and status.get("users") and not status.get("assistants")
            and status.get("readyState") in {"interactive", "complete"}
            and "/c/" in urlsplit(status["url"]).path and identity(status["url"]) == identity(url)):
        page_event(page, "navigation_ready", dict(duration_ms=round((time.monotonic() - started) * 1000), prompt_only=True))
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
        unstable = [mid for mid in visible if not re.fullmatch(rf"(?:{UUID_PATTERN}|{LOCAL_ACTIVITY_PATTERN})", mid)]
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
            discovery_error = discovery.get("error")
            status = "incomplete" if discovery_error else "no-eligible-conversations"
            trace.finish(dict(status=status, discovery_partial=True, discovery_error=discovery_error, pending=waiting, **counts))
            print(encoded(dict(type="run", status=status, skipped=len(catalog), pending=waiting, **counts, discovery_error=discovery_error)) if output_format == "jsonl" else f"Run status={status} known={len(catalog)} due={counts['due']} cooldown={counts['cooldown']} pending={len(waiting)} discovery_error={discovery_error or 'none'} elapsed={duration(time.monotonic()-trace.started)} logs={trace.events_path}", flush=True)
            return bool(discovery_error)
        async with AsyncExitStack() as pages:
            page = await pages.enter_async_context(owned_page(cdp_url))
            page.backup_trace = trace
            page.backup_context = context
            trace.event("browser", dict(browser_version=getattr(page, "browser_version", "")))
            print("Using automation-owned background tab", file=sys.stderr, flush=True)
            discovery_error = None if conversations else discovery.get("error")
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
                    elif up.get("boundary") and down.get("boundary"):
                        reused = full_scan_prefix(previous, result["messages"])
                        if reused:
                            result["messages"] = previous[:reused] + result["messages"]
                            trace.event("prefix_reused", dict(context, anchor_id=result["messages"][reused]["id"], reused_messages=reused, captured_messages=len(result["messages"])-reused, prefix_assumption=True, full_scan=True))
                            print(f"  retained_saved_prefix={reused:03}", file=sys.stderr, flush=True)
                    # Some Work views hydrate the prompt while omitting a saved reply.
                    if result["messages"] and all(m["role"] == "user" for m in result["messages"]):
                        raw_path = RAW_DIR / f"{cid}.json"
                        try:
                            _, native, raw_info = raw_snapshot(raw_path)
                        except (FileNotFoundError, ValueError):
                            native, raw_info = {}, {}
                        if raw_info.get("coverage") in {"branch", "tree"}:
                            if raw_has_reply(native, {m["id"] for m in result["messages"]}):
                                raise IncompleteChat("Rendered prompt-only view omits a reply present in native capture")
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
                    validate(rows, expected_prefix, previous)
                    trace.event("validation", validation)
                    markdown = await page.evaluate("({rows,metadata}) => chatgptscraper.messagesToMarkdown(rows,metadata)", dict(rows=rows, metadata=metadata))
                    if await page.evaluate(f"() => ({GENERATION_ACTIVE})"):
                        raise IncompleteChat("Generation started during extraction; deferred without publishing")
                    context["stage"] = "writing"
                    trace.event("write_start", dict(context, markdown_bytes=len(markdown.encode())))
                    changed = False if dry_run else save(path, rows, markdown, title)
                    context["stage"] = "publication"
                    publication = publish(out_dir / filename(title, cid), cid, title, rows, chat_started)
                    coverage = "matched-prefix+rendered-tail" if anchor or reused else "rendered-boundaries"
                    chat.update(title=title, url=metadata["source"], checked=today, changed=False, pending=False, error=None, date=metadata["date"], coverage=coverage, prompt_expansion_checked=True, messages=len(rows), contentHash=digest(rows))
                    chat.pop("error_context", None)
                    persist()  # Commit each chat, so interruption resumes from remaining/oldest chats.
                    completed += 1
                    summary = dict(conversationId=cid, position=position, total=len(selected), status="validated", coverage=coverage, expanded_prompts=up.get("expanded_prompts", 0)+down.get("expanded_prompts", 0), reused_messages=reused, captured_messages=up["count"] if anchor else len(rows)-reused, **message_stats(rows), changed=changed, shared_status="disabled" if markdown_dir is None else "dry-run" if dry_run else "updated" if publication["changed"] else "unchanged", dry_run=dry_run, duration_ms=round((time.monotonic()-chat_started)*1000), markdown_bytes=len(markdown.encode()), jsonl_bytes=sum(len((encoded(r)+"\n").encode()) for r in rows), timestamps=sum("timestamp" in r for r in rows), up=up, down=down)
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
        status = "incomplete" if failed or discovery_error else "partial"
        trace.finish(dict(status=status, conversations=completed, completed=completed, failures=failures, failed=failed, unattempted=0, due_remaining=due_remaining, pending_count=len(selected)-completed, flagged_pending_count=len(flagged), selected=len(selected), discovery_partial=True, discovery_error=discovery_error))
        if output_format == "jsonl":
            print(encoded(dict(type="run", status=status, failures=failures, failed=failed, unattempted=0, due_remaining=due_remaining, sidebar_exhaustive=False, discovery_error=discovery_error, selected=len(selected), completed=completed, pending_count=len(selected)-completed, flagged_pending_count=len(flagged), duration_ms=round((time.monotonic()-trace.started)*1000), skipped=len(catalog)-len(selected), pending=flagged)), flush=True)
        else:
            print(f"Run status={status} completed={completed}/{len(selected)} failed={failed} unattempted=0 due_remaining={due_remaining} pending={len(selected)-completed} flagged_pending={len(flagged)} discovery_error={discovery_error or 'none'} elapsed={duration(time.monotonic()-trace.started)} logs={trace.events_path}", flush=True)
    except BaseException as exc:
        incomplete(exc)
        failure = dict(context, completed=completed, failed=failed, failures=failures, consecutive_load_failures=consecutive_load_failures, due_remaining=selection_counts(catalog, [], "", False, len(catalog), today)["due"], selected=len(selected), pending_count=len(selected)-completed, flagged_pending_count=sum(bool(c.get("pending")) for c in catalog.values()), unattempted=len(selected)-attempted, observed_messages=len(candidate), conversation_duration_ms=round((time.monotonic()-chat_started)*1000))
        trace.exception(exc, **failure)
        trace.finish(dict(status="failed", error_type=type(exc).__name__, error_message=str(exc), **failure))
        print(f'Incomplete ID={active_id or "none"} ({context.get("position", 0)}/{len(selected)}) stage={context["stage"]} completed={completed} failed={failed} pending={failure["pending_count"]} unattempted={failure["unattempted"]} flagged_pending={failure["flagged_pending_count"]} due_remaining={failure["due_remaining"]} elapsed={duration(time.monotonic()-chat_started)} logs={trace.events_path}', file=sys.stderr, flush=True)
        if output_format == "jsonl":
            print(encoded(dict(type="run", status="incomplete", error=str(exc) or type(exc).__name__, pending=[cid for cid,c in catalog.items() if c.get("pending")], **failure)), flush=True)
        raise

    return failed or bool(discovery_error)


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
        from inspect import signature
        from typer.main import get_command
        # Derive types from our CLI signature; Typer 0.29 no longer exposes Click's .type.
        types = {"str": "text", "list[str]": "text", "int": "integer", "bool": "boolean", "Path": "path"}
        params = signature(main).parameters
        print(encoded(dict(command="backupchatgpt", parameters=[dict(name=p.name, flags=p.opts+p.secondary_opts, type=types[params[p.name].annotation], multiple=p.multiple, default=str(p.default) if isinstance(p.default, Path) else p.default, help=p.help) for p in get_command(app).params], output="Conversation summaries plus final run record; canonical JSONL preserves scraper messages plus conversation metadata, conversationId and contentHash", coverage="Partial sidebar, current rendered branch only; no timestamp API", sources=[str(SCRAPERS / n) for n in SOURCES])))
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


raw_app = typer.Typer(add_completion=False)


@raw_app.command()
def backup_raw(
    raw_dir: Path = typer.Option(RAW_DIR, help="Local extension capture directory."),
    markdown_dir: Path = typer.Option(Path.home() / "Documents/chatgpt", help="Markdown publication directory."),
    dry_run: bool = typer.Option(False, help="Show proposed changes without publishing."),
    format: str = typer.Option("text", help="Output format: text (TSV) or jsonl."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show each chat’s status, ID, latest known update in UTC, and title."),
):
    """Update Markdown from local ChatGPT snapshots and completed generation streams.

    Examples:
      chatcli backup --dry-run
      chatcli backup --verbose --format jsonl | jaq .
      chatcli backup --markdown-dir /tmp/chatgpt-preview
    """
    if format not in {"text", "jsonl"}:
        raise typer.BadParameter("--format must be text or jsonl")
    os.umask(0o077)
    try:
        if dry_run:
            failed = raw_backup(raw_dir.expanduser(), markdown_dir.expanduser(), True, format, verbose=verbose)
        else:
            lock_dir = Path.home() / ".cache/sanand-scripts/backupchatgpt"
            lock_dir.mkdir(parents=True, exist_ok=True)
            with (lock_dir / "run.lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                failed = raw_backup(raw_dir.expanduser(), markdown_dir.expanduser(), False, format, verbose=verbose)
    except (OSError, ValueError) as exc:
        print(f"error[chatcli-backup]: {exc}", file=sys.stderr)
        raise typer.Exit(1) from exc
    if failed:
        raise typer.Exit(1)


if __name__ == "__main__":
    if sys.argv[1:2] == ["raw"]:
        raw_app(args=sys.argv[2:], prog_name="chatcli backup")
    else:
        app()
