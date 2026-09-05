#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["pyyaml>=6", "typer>=0.12"]
# ///
"""Build and query a deterministic, source-preserving local context index.

This is a candidate-discovery tool. Deep-read returned locators before making claims.

Examples:
  context.py rebuild
  context.py search 'Subject: project update' --source mail | jaq .
  context.py entity 'Alice Example' | moor
  context.py style 'how I explain verification' | jaq '.[].locator'
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import sqlite3
import time
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import unquote

import typer
import yaml

app = typer.Typer(add_completion=False, help=__doc__)
DEFAULT_DB = Path("~/Documents/data/context/context.sqlite").expanduser()
DEFAULT_LOG = Path("~/Documents/data/context/query-log.jsonl").expanduser()
DATE_FILE = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:[ -]|$)")
WORD = re.compile(r"[^\W_]+(?:[._+@/-][^\W_]+)*", re.UNICODE)
# Keep action routing explicit: recognize concrete requests without treating bare "action" or "what happened" as action queries.
ACTION_INTENT = re.compile(
    r"\b(pending|open loops?|follow[- ]?up|commit|action items?|next steps?|meeting prep|prepare(?: me)? for (?:the )?meeting|briefing|last meeting)\b",
    re.IGNORECASE,
)
RECENT_INTENT = re.compile(r"\b(recent|latest|newest|last|today|yesterday|current)\b", re.IGNORECASE)
WHY_ORDER = ["subject", "sender", "entity", "about-link", "action", "recent", "broad", "historical"]
QUERY_STOP = set(
    """the a an and or of to in on for with from by as at is are was were be been being this that
these those it its i me my we our you your they their he she his her them localmcp local mcp bash use using go
through read search find look check based past conversations conversation content files file notes transcripts
transcript relevant extensively required require help suggest give share tell make create draft answer reply recent
latest current things stuff what where when who why how would should could can may might will do did done if than
then into about around against across via all any each some few more most much many one two three today tomorrow
yesterday week month year please feel free skills skill research online guardrails adapted audience situation""".split()  # noqa: SIM905
)
ACTION_STOP = {
    "what", "should", "could", "would", "about", "with", "from", "action", "item", "items", "todo", "follow",
    "open", "loop", "next", "step", "steps", "agenda", "need", "have", "there", "that", "this",
    "pending", "commit", "meeting", "prep", "prepare", "briefing", "last",
}


class SourceConfig:
    """All input locations, kept injectable so rebuild behavior is fixture-testable."""

    def __init__(self, home: Path) -> None:
        self.home = home
        self.transcripts = home / "Dropbox/notes/transcripts"
        self.about = home / "Dropbox/notes/about"
        self.data = home / "Documents/data"
        self.whatsapp = self.data / "whatsapp"
        self.chatgpt = home / "Documents/chatgpt"
        self.claude = home / "Documents/claude"
        self.mail_index = home / "Documents/Mail/mail-index.sqlite"
        self.log_path = home / "Documents/data/context/query-log.jsonl"
        self.assets = (
            home / "code/README.md",
            home / "code/talks/README.md",
            home / "code/datastories/config.json",
            home / "code/llmdemos/config.json",
            home / "code/llmevals/README.md",
            home / "code/blog/description.md",
            home / "code/til/README.md",
        )

    @classmethod
    def for_home(cls, home: Path) -> SourceConfig:
        return cls(Path(home))


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def display_path(path: Path, home: Path) -> str:
    try:
        return f"~/{path.relative_to(home)}"
    except ValueError:
        return str(path)


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}, text
    data = yaml.safe_load(text[4:end]) or {}
    if not isinstance(data, dict):
        raise TypeError("YAML frontmatter must be a mapping")
    return data, text[end + 5 :]


def listify(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    values = value if isinstance(value, list) else [value]
    return [str(item).strip() for item in values if str(item).strip()]


def timestamp_from_name(name: str) -> str:
    match = DATE_FILE.match(name)
    return match.group(1) if match else ""


def normalize_timestamp(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return text
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        for pattern in ("%b %d, %Y, %I:%M %p", "%B %d, %Y, %I:%M %p"):
            try:
                parsed = dt.datetime.strptime(text, pattern).replace(tzinfo=dt.datetime.now().astimezone().tzinfo)
                break
            except ValueError:
                continue
        else:
            return text
    if parsed.tzinfo:
        return parsed.astimezone(dt.UTC).isoformat()
    return parsed.isoformat()


def parse_date(value: str, *, now: dt.datetime | None = None) -> str:
    if not value:
        return ""
    now = now or dt.datetime.now(dt.UTC)
    if match := re.fullmatch(r"(\d+)d", value.strip(), re.IGNORECASE):
        return (now - dt.timedelta(days=int(match.group(1)))).date().isoformat()
    try:
        return dt.date.fromisoformat(value[:10]).isoformat()
    except ValueError as error:
        raise typer.BadParameter(f"Expected ISO date or Nd, got {value!r}") from error


def json_lines(path: Path) -> Iterable[tuple[int, dict[str, Any]]]:
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line_number, line in enumerate(handle, 1):
            if line.strip():
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError(f"{path}:{line_number}: expected a JSON object")
                yield line_number, value


SCHEMA = """
CREATE TABLE items (
  id INTEGER PRIMARY KEY, source TEXT NOT NULL, native_id TEXT NOT NULL DEFAULT '',
  timestamp TEXT NOT NULL DEFAULT '', title TEXT NOT NULL DEFAULT '', body TEXT NOT NULL DEFAULT '',
  summary TEXT NOT NULL DEFAULT '', locator TEXT NOT NULL, thread_id TEXT NOT NULL DEFAULT '',
  conversation_id TEXT NOT NULL DEFAULT '', account TEXT NOT NULL DEFAULT '',
  author TEXT NOT NULL DEFAULT '', role TEXT NOT NULL DEFAULT '', extra TEXT NOT NULL DEFAULT '{}'
);
CREATE VIRTUAL TABLE item_fts USING fts5(
  title, body, summary, author, content='items', content_rowid='id',
  tokenize='unicode61 remove_diacritics 2'
);
CREATE VIRTUAL TABLE item_vocab USING fts5vocab(item_fts, 'row');
CREATE TABLE actions (
  id INTEGER PRIMARY KEY, item_id INTEGER NOT NULL REFERENCES items(id),
  action_text TEXT NOT NULL, owner TEXT NOT NULL DEFAULT '', due_date TEXT NOT NULL DEFAULT '',
  fingerprint TEXT NOT NULL
);
CREATE TABLE entities (
  entity_id INTEGER PRIMARY KEY, canonical_name TEXT NOT NULL, profile_path TEXT NOT NULL
);
CREATE TABLE aliases (entity_id INTEGER NOT NULL REFERENCES entities(entity_id), alias TEXT NOT NULL);
CREATE TABLE item_entities (
  item_id INTEGER NOT NULL REFERENCES items(id), entity_id INTEGER NOT NULL REFERENCES entities(entity_id),
  role TEXT NOT NULL, UNIQUE(item_id, entity_id, role)
);
CREATE TABLE source_status (
  source TEXT PRIMARY KEY, latest_item_time TEXT NOT NULL DEFAULT '', source_mtime TEXT NOT NULL DEFAULT '',
  row_count INTEGER NOT NULL DEFAULT 0, built_at TEXT NOT NULL, warning TEXT NOT NULL DEFAULT ''
);
CREATE INDEX items_source_time_idx ON items(source, timestamp);
CREATE INDEX items_thread_idx ON items(thread_id);
CREATE INDEX items_conversation_idx ON items(conversation_id);
CREATE INDEX actions_fingerprint_idx ON actions(fingerprint);
CREATE INDEX aliases_alias_idx ON aliases(alias COLLATE NOCASE);
"""


def add_item(connection: sqlite3.Connection, **row: Any) -> int:
    fields = (
        "source", "native_id", "timestamp", "title", "body", "summary", "locator",
        "thread_id", "conversation_id", "account", "author", "role", "extra",
    )
    values = [row.get(field, "{}" if field == "extra" else "") for field in fields]
    cursor = connection.execute(
        f"INSERT INTO items({','.join(fields)}) VALUES({','.join('?' for _ in fields)})",
        values,
    )
    return int(cursor.lastrowid)


def action_parts(text: str) -> tuple[str, str, str]:
    owner = ""
    remainder = text.strip()
    if match := re.match(r"^([^:]{1,60}):\s+(.+)$", remainder):
        owner, remainder = match.groups()
    due = (re.search(r"\b\d{4}-\d{2}-\d{2}\b", remainder) or [""])[0]
    normalized = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", "", remainder.casefold())
    normalized = " ".join(re.findall(r"[\w@.+-]+", normalized))
    fingerprint = hashlib.sha256(normalized.encode()).hexdigest()[:20]
    return owner.strip(), due, fingerprint


def strong_aliases(text: str) -> set[str]:
    aliases: set[str] = set()
    metadata = re.compile(
        r"^\s*[-*]?\s*(Alias(?:es)?|E-?mail(?: address)?|Google(?: Chat)? ID|Chat ID|WhatsApp(?: ID)?|User ID):\s*(.+)$",
        re.IGNORECASE | re.MULTILINE,
    )
    for match in metadata.finditer(text):
        field, value = match.groups()
        if field.casefold().startswith("alias"):
            aliases.update(part.strip().casefold() for part in re.split(r"[,;]", value) if part.strip())
        aliases.update(item.casefold() for item in re.findall(
            r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b|\busers/\d+\b|\b\d+@(?:lid|c\.us)\b",
            value, re.IGNORECASE,
        ))
    return aliases


def identity_values(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from identity_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from identity_values(item)
    elif value not in (None, ""):
        yield str(value)


# Restrict prefix fallback to simple multi-word names so emails, IDs, and paths cannot become person matches.
HUMAN_NAME = re.compile(r"[^\W\d_]+(?:[-'’][^\W\d_]+)*(?:\s+[^\W\d_]+(?:[-'’][^\W\d_]+)*)+", re.UNICODE)


def safe_prefix_entities(alias_entities: dict[str, set[int]], value: str) -> set[int]:
    """Return all entities behind a validated strict name prefix for fail-closed callers."""
    prefix = " ".join(value.strip().split()).casefold()
    if not HUMAN_NAME.fullmatch(prefix):
        return set()
    return {
        entity_id
        for alias, ids in alias_entities.items()
        if alias != prefix and alias.casefold().startswith(prefix)
        for entity_id in ids
    }


def linked_entities(alias_entities: dict[str, set[int]], *values: Any) -> set[int]:
    matches: set[int] = set()
    for value in values:
        for text in identity_values(value):
            candidates = {text.strip().casefold()}
            candidates.update(item.casefold() for item in re.findall(
                r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b|\busers/\d+\b|\b\d+@(?:lid|c\.us)\b",
                text, re.IGNORECASE,
            ))
            if display := re.match(r"\s*([^<]+?)\s*<[^>]+>\s*$", text):
                candidates.add(display.group(1).strip().casefold())
            for candidate in candidates:
                ids = alias_entities.get(candidate, set())
                if len(ids) == 1:
                    matches.update(ids)
                elif not ids:
                    prefix_ids = safe_prefix_entities(alias_entities, candidate)
                    if len(prefix_ids) == 1:
                        matches.update(prefix_ids)
    return matches


def link_item(connection: sqlite3.Connection, item_id: int, alias_entities: dict[str, set[int]], role: str, *values: Any) -> None:
    for entity_id in linked_entities(alias_entities, *values):
        connection.execute(
            "INSERT OR IGNORE INTO item_entities(item_id,entity_id,role) VALUES(?,?,?)",
            (item_id, entity_id, role),
        )


def file_mtime(paths: Iterable[Path]) -> str:
    values = [path.stat().st_mtime for path in paths if path.exists()]
    return dt.datetime.fromtimestamp(max(values), dt.UTC).isoformat() if values else ""


def index_sources(connection: sqlite3.Connection, config: SourceConfig, built_at: str) -> None:
    source_paths: dict[str, list[Path]] = defaultdict(list)
    transcript_ids: dict[str, int] = {}
    transcript_people: dict[int, list[str]] = {}

    if config.transcripts.is_dir():
        for path in sorted(config.transcripts.glob("*.md")):
            if not DATE_FILE.match(path.name):
                continue
            metadata, body = parse_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
            summary = "\n".join(listify(metadata.get("summary")))
            keywords = listify(metadata.get("keywords"))
            people = listify(metadata.get("people"))
            native_id = path.name
            locator = display_path(path, config.home)
            item_id = add_item(
                connection, source="transcript", native_id=native_id,
                timestamp=timestamp_from_name(path.name),
                title=re.sub(r"^\d{4}-\d{2}-\d{2}[ -]*", "", path.stem), body=body,
                summary="\n".join(filter(None, [summary, "Keywords: " + ", ".join(keywords) if keywords else ""])),
                locator=locator, author=" / ".join(people),
                extra=compact_json({"people": people, "keywords": keywords}),
            )
            transcript_ids[path.name] = item_id
            transcript_people[item_id] = people
            for action in listify(metadata.get("actions")):
                owner, due, fingerprint = action_parts(action)
                connection.execute(
                    "INSERT INTO actions(item_id,action_text,owner,due_date,fingerprint) VALUES(?,?,?,?,?)",
                    (item_id, action, owner, due, fingerprint),
                )
            source_paths["transcript"].append(path)

    alias_entities: dict[str, set[int]] = defaultdict(set)
    if config.about.is_dir():
        for path in sorted(config.about.glob("*.md")):
            if path.name.startswith("week-"):
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            heading = re.search(r"^#\s+(.+?)\s*$", text, re.MULTILINE)
            canonical = (heading.group(1) if heading else path.stem).strip()
            locator = display_path(path, config.home)
            about_item = add_item(
                connection, source="about", native_id=path.name, title=canonical,
                body=text, locator=locator,
            )
            cursor = connection.execute(
                "INSERT INTO entities(canonical_name,profile_path) VALUES(?,?)", (canonical, locator)
            )
            entity_id = int(cursor.lastrowid)
            aliases = {canonical.casefold(), path.stem.casefold(), *strong_aliases(text)}
            for alias in sorted(aliases):
                connection.execute("INSERT INTO aliases(entity_id,alias) VALUES(?,?)", (entity_id, alias))
                alias_entities[alias].add(entity_id)
            connection.execute(
                "INSERT OR IGNORE INTO item_entities(item_id,entity_id,role) VALUES(?,?,?)",
                (about_item, entity_id, "profile"),
            )
            cited_names = {
                unquote(Path(match).name)
                for match in re.findall(r"(?:\.\./transcripts/|Dropbox/notes/transcripts/)([^\]\)`\n]+?\.md)", text)
            }
            for name in cited_names:
                if item_id := transcript_ids.get(name):
                    connection.execute(
                        "INSERT OR IGNORE INTO item_entities(item_id,entity_id,role) VALUES(?,?,?)",
                        (item_id, entity_id, "evidence"),
                    )
            source_paths["about"].append(path)

    for item_id, people in transcript_people.items():
        for person in people:
            for entity_id in linked_entities(alias_entities, person):
                connection.execute(
                    "INSERT OR IGNORE INTO item_entities(item_id,entity_id,role) VALUES(?,?,?)",
                    (item_id, entity_id, "mentioned"),
                )

    account_dirs = []
    if config.data.is_dir():
        account_dirs = sorted(path for path in config.data.iterdir() if path.is_dir() and "@" in path.name)
    for account_dir in account_dirs:
        account = account_dir.name
        for filename, source in (("mail.jsonl", "mail"), ("calendar.jsonl", "calendar"), ("chat.jsonl", "gchat")):
            path = account_dir / filename
            if not path.exists():
                continue
            for line_number, row in json_lines(path):
                locator = f"{display_path(path, config.home)}#L{line_number}"
                if source == "mail":
                    author = str(row.get("from", ""))
                    role = "user" if account.casefold() in author.casefold() else "other"
                    extra_keys = ("to", "cc", "bcc", "attachments", "size")
                    item_id = add_item(
                        connection, source=source, native_id=row.get("id", ""),
                        timestamp=normalize_timestamp(row.get("time")), title=row.get("subject", ""),
                        body=row.get("body", ""), summary=row.get("snippet", ""), locator=locator,
                        thread_id=row.get("thread_id") or row.get("threadId", ""), account=account,
                        author=author, role=role,
                        extra=compact_json({key: row[key] for key in extra_keys if key in row}),
                    )
                    link_item(connection, item_id, alias_entities, "sender", row.get("from"))
                    link_item(connection, item_id, alias_entities, "recipient", *(row.get(key) for key in ("to", "cc", "bcc")))
                elif source == "calendar":
                    extra_keys = (
                        "attendees", "attendee_status", "status", "end_time", "location", "hangout_link",
                        "recurring_event_id", "original_start_time",
                    )
                    item_id = add_item(
                        connection, source=source, native_id=row.get("id", ""),
                        timestamp=normalize_timestamp(row.get("time")), title=row.get("title", ""),
                        body=row.get("body", ""), locator=locator,
                        conversation_id=row.get("recurring_event_id", ""), account=account,
                        author=row.get("organizer", ""),
                        extra=compact_json({key: row[key] for key in extra_keys if key in row}),
                    )
                    link_item(connection, item_id, alias_entities, "organizer", row.get("organizer"))
                    link_item(connection, item_id, alias_entities, "attendee", row.get("attendees"))
                else:
                    extra_keys = ("sender_id", "space_id", "reactions", "attachments", "cards")
                    item_id = add_item(
                        connection, source=source, native_id=row.get("id", ""),
                        timestamp=normalize_timestamp(row.get("time")), title=row.get("space_name", ""),
                        body=row.get("body", ""), locator=locator, thread_id=row.get("thread_id", ""),
                        conversation_id=row.get("space_id", ""), account=account,
                        author=row.get("sender_name", ""),
                        extra=compact_json({key: row[key] for key in extra_keys if key in row}),
                    )
                    link_item(connection, item_id, alias_entities, "sender", row.get("sender_id"), row.get("sender_name"))
            source_paths[source].append(path)

        drive = account_dir / "drive.jsonl"
        if drive.exists():
            for line_number, row in json_lines(drive):
                extra = {key: value for key, value in row.items() if key not in {"id", "name", "modifiedTime", "webViewLink"}}
                item_id = add_item(
                    connection, source="drive", native_id=row.get("id", ""),
                    timestamp=normalize_timestamp(row.get("modifiedTime")), title=row.get("name", ""),
                    locator=row.get("webViewLink") or f"{display_path(drive, config.home)}#L{line_number}",
                    account=account, extra=compact_json(extra),
                )
            source_paths["drive"].append(drive)

    if config.whatsapp.is_dir():
        for path in sorted(config.whatsapp.glob("*.jsonl")):
            for line_number, row in json_lines(path):
                extra_keys = (
                    "userId", "authorPhone", "isOutgoing", "reactions", "linkUrl", "linkSite",
                    "linkTitle", "mediaType", "scrapedAt",
                )
                author = row.get("author") or row.get("authorPhone") or row.get("userId", "")
                item_id = add_item(
                    connection, source="whatsapp", native_id=row.get("messageId", ""),
                    timestamp=normalize_timestamp(row.get("time")),
                    title=row.get("conversationTitle", path.stem), body=row.get("text", ""),
                    locator=f"{display_path(path, config.home)}#L{line_number}",
                    conversation_id=row.get("conversationId", ""), author=author,
                    role="user" if row.get("isOutgoing") else "other",
                    extra=compact_json({key: row[key] for key in extra_keys if key in row}),
                )
                link_item(
                    connection, item_id, alias_entities, "sender",
                    row.get("userId"), row.get("authorPhone"), row.get("author"),
                )
            source_paths["whatsapp"].append(path)

    for source, directory in (("chatgpt", config.chatgpt), ("claude", config.claude)):
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.md")):
            text = path.read_text(encoding="utf-8", errors="replace")
            title_match = re.search(r"^#\s*(.*?)\s*$", text, re.MULTILINE)
            title = (title_match.group(1) if title_match else path.stem).strip() or path.stem
            created_match = re.search(r"^- Created:\s*(.+)$", text, re.MULTILINE)
            timestamp = normalize_timestamp(created_match.group(1)) if created_match else ""
            link_match = re.search(r"^- Link:\s*(\S+)", text, re.MULTILINE)
            conversation_id = (link_match.group(1).rstrip("/").rsplit("/", 1)[-1] if link_match else path.stem)
            heading = re.compile(r"^##\s+(User|Assistant|human|assistant)\s*$", re.MULTILINE)
            matches = list(heading.finditer(text))
            for turn, match in enumerate(matches, 1):
                body = text[match.end() : matches[turn].start() if turn < len(matches) else len(text)].strip()
                role = "user" if match.group(1).casefold() in {"user", "human"} else "assistant"
                line_number = text.count("\n", 0, match.start()) + 1
                add_item(
                    connection, source=source, native_id=f"{conversation_id}:{turn}",
                    timestamp=timestamp, title=title, body=body,
                    locator=f"{display_path(path, config.home)}#L{line_number}",
                    conversation_id=conversation_id, role=role,
                )
            source_paths[source].append(path)

    for path in config.assets:
        if not path.exists():
            continue
        display = display_path(path, config.home)
        if path.suffix == ".json":
            data = json.loads(path.read_text(encoding="utf-8"))
            entries = data if isinstance(data, list) else next((value for value in data.values() if isinstance(value, list)), [])
            for index, entry in enumerate(entries):
                if not isinstance(entry, dict):
                    continue
                key = str(entry.get("id") or entry.get("slug") or entry.get("title") or index)
                add_item(
                    connection, source="asset_registry", native_id=f"{display}#{key}",
                    timestamp=normalize_timestamp(entry.get("date") or entry.get("created")),
                    title=entry.get("title") or entry.get("name") or key,
                    body=compact_json(entry), summary=entry.get("summary") or entry.get("description", ""),
                    locator=f"{display}#{key}", extra=compact_json(entry),
                )
        else:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            asset_lines = [(number, line) for number, line in enumerate(lines, 1) if line.startswith("- ")]
            if path.name == "description.md":
                asset_lines = [(number, line) for number, line in enumerate(lines, 1) if ":description:" in line]
            if not asset_lines:
                asset_lines = [(1, "\n".join(lines))]
            for number, line in asset_lines:
                link = re.search(r"\[([^]]+)\]\(([^)]+)\)", line)
                title = link.group(1) if link else re.sub(r"^[^:]+:description:\s*|^-\s*", "", line)[:160]
                key = link.group(2) if link else line.split(":description:", 1)[0]
                add_item(
                    connection, source="asset_registry", native_id=f"{display}#{key}",
                    title=title, body=line, locator=f"{display}#L{number}",
                )
        source_paths["asset_registry"].append(path)

    all_sources = ("transcript", "about", "mail", "calendar", "gchat", "whatsapp", "chatgpt", "claude", "drive", "asset_registry")
    for source in all_sources:
        paths = source_paths[source]
        row = connection.execute(
            "SELECT count(*),coalesce(max(timestamp),'') FROM items WHERE source=?", (source,)
        ).fetchone()
        warning = "" if paths else "source missing or no production input found"
        connection.execute(
            "INSERT INTO source_status VALUES(?,?,?,?,?,?)",
            (source, row[1], file_mtime(paths), row[0], built_at, warning),
        )


def validate_database(connection: sqlite3.Connection) -> None:
    integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity != "ok":
        raise RuntimeError(f"SQLite integrity check failed: {integrity}")
    items = connection.execute("SELECT count(*) FROM items").fetchone()[0]
    fts = connection.execute("SELECT count(*) FROM item_fts").fetchone()[0]
    if items != fts:
        raise RuntimeError(f"FTS count mismatch: {items} items, {fts} FTS rows")
    missing = connection.execute("SELECT count(*) FROM items WHERE locator='' OR locator IS NULL").fetchone()[0]
    if missing:
        raise RuntimeError(f"{missing} indexed items have no locator")


def rebuild_database(database: Path, config: SourceConfig | None = None) -> dict[str, Any]:
    """Build a validated sibling temp DB and atomically replace the live DB."""
    config = config or SourceConfig.for_home(Path.home())
    database = Path(database).expanduser()
    temp = database.with_suffix(database.suffix + ".tmp")
    database.parent.mkdir(parents=True, exist_ok=True)
    temp.unlink(missing_ok=True)
    started = time.perf_counter()
    built_at = dt.datetime.now(dt.UTC).isoformat()
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(temp)
        connection.executescript(SCHEMA)
        index_sources(connection, config, built_at)
        connection.execute("INSERT INTO item_fts(item_fts) VALUES('rebuild')")
        connection.execute("PRAGMA optimize")
        connection.commit()
        validate_database(connection)
        counts = dict(connection.execute("SELECT source,row_count FROM source_status ORDER BY source"))
        connection.close()
        connection = None
        os.replace(temp, database)
    except BaseException:
        if connection is not None:
            connection.close()
        temp.unlink(missing_ok=True)
        raise
    return {
        "database": str(database), "counts": counts, "database_bytes": database.stat().st_size,
        "built_at": built_at, "rebuild_seconds": round(time.perf_counter() - started, 3),
    }


def connect(database: Path) -> sqlite3.Connection:
    uri = f"file:{Path(database).expanduser()}?mode=ro&immutable=1"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def intent_text(query: str) -> str:
    text = unquote(query or "")
    cuts = [
        match.start() for pattern in (
            r"\n\s*(?:#+\s*)?Guardrails\s*:", r"\n\s*<skill\b", r"\n\s*Use relevant skills\s*:",
        ) if (match := re.search(pattern, text, re.IGNORECASE)) and match.start() > 0
    ]
    return text[:min(cuts)] if cuts else text[:1800]


def query_tokens(query: str) -> list[str]:
    seen: set[str] = set()
    tokens = []
    for token in WORD.findall(intent_text(query)):
        folded = token.casefold().strip("./-")
        if len(folded) > 2 and folded not in seen and folded not in QUERY_STOP and folded not in {"subject", "from"}:
            seen.add(folded)
            tokens.append(folded)
    return tokens[:18]


def fts_expression(query: str, column: str = "", tokens: list[str] | None = None) -> str:
    prefix = f"{column}:" if column else ""
    return " OR ".join(f'{prefix}"{token.replace(chr(34), "")}"' for token in (tokens or query_tokens(query)))


def cue(query: str, name: str) -> str:
    match = re.search(rf"^\s*>?\s*{name}:\s*(.+)$", query, re.IGNORECASE | re.MULTILINE)
    return match.group(1).strip() if match else ""


def iso_day(timestamp: str) -> dt.date | None:
    try:
        return dt.date.fromisoformat(timestamp[:10])
    except (ValueError, TypeError):
        return None


def hit_from_row(row: sqlite3.Row | dict[str, Any], snippet: str, score: float, why: set[str]) -> dict[str, Any]:
    item = dict(row)
    return {
        "source": item.get("source", ""), "timestamp": item.get("timestamp", ""),
        "title": item.get("title", ""), "author": item.get("author", ""),
        "role": item.get("role", ""), "native_id": item.get("native_id", ""),
        "thread_id": item.get("thread_id", ""), "conversation_id": item.get("conversation_id", ""),
        "locator": item.get("locator", ""), "snippet": snippet,
        "score": round(score, 8), "why": [reason for reason in WHY_ORDER if reason in why],
    }


def database_alias_entities(connection: sqlite3.Connection) -> dict[str, set[int]]:
    aliases: dict[str, set[int]] = defaultdict(set)
    for row in connection.execute("SELECT alias,entity_id FROM aliases"):
        aliases[row["alias"].casefold()].add(row["entity_id"])
    return aliases


def unique_query_entities(connection: sqlite3.Connection, query: str) -> list[int]:
    alias_entities = database_alias_entities(connection)
    folded = " ".join(intent_text(query).casefold().split())
    exact_matches: list[tuple[int, int]] = []
    for alias, ids in alias_entities.items():
        normalized_alias = " ".join(alias.split())
        if len(ids) == 1 and re.search(rf"(?<!\w){re.escape(normalized_alias)}(?!\w)", folded):
            exact_matches.append((len(normalized_alias), next(iter(ids))))

    prefix_entities: dict[str, set[int]] = defaultdict(set)
    for alias, ids in alias_entities.items():
        words = [word.casefold() for word in WORD.findall(alias)]
        for end in range(2, len(words) + 1):
            prefix_entities[" ".join(words[:end])].update(ids)
    prefix_matches = [
        (len(prefix), next(iter(ids)))
        for prefix, ids in prefix_entities.items()
        if len(ids) == 1 and re.search(rf"(?<!\w){re.escape(prefix)}(?!\w)", folded)
    ]
    matches = sorted(exact_matches, reverse=True) + sorted(prefix_matches, reverse=True)
    return list(dict.fromkeys(entity_id for _, entity_id in sorted(matches, reverse=True)))


def ranked_fts(
    connection: sqlite3.Connection, query: str, *, column: str = "", sources: list[str] | None,
    since: str, until: str, limit: int,
) -> list[sqlite3.Row]:
    tokens = query_tokens(query)
    if not column and len(tokens) > 8:
        placeholders = ",".join("?" for _ in tokens)
        frequencies = dict(connection.execute(
            f"SELECT term,doc FROM item_vocab WHERE term IN ({placeholders})", tokens
        ))
        selected = set(sorted(tokens, key=lambda token: (frequencies.get(token, 0), -len(token), token))[:8])
        tokens = [token for token in tokens if token in selected]
    if not (expression := fts_expression(query, column, tokens)):
        return []
    sql = """SELECT i.*,bm25(item_fts,6,1,4,5) rank
             FROM item_fts JOIN items i ON i.id=item_fts.rowid WHERE item_fts MATCH ?"""
    params: list[Any] = [expression]
    if sources:
        local_sources = [source for source in sources if source != "historical_mail"]
        if not local_sources:
            sql += " AND 0"
        else:
            sql += f" AND i.source IN ({','.join('?' for _ in local_sources)})"
            params.extend(local_sources)
    if since:
        sql += " AND i.timestamp>=?"
        params.append(since)
    if until:
        sql += " AND i.timestamp<?"
        params.append(until)
    sql += " ORDER BY rank,i.id LIMIT ?"
    params.append(limit)
    return connection.execute(sql, params).fetchall()


def needs_historical(query: str, since: str, until: str, as_of: str) -> bool:
    years = [int(year) for year in re.findall(r"\b(19\d{2}|20\d{2})\b", query)]
    dates = [value for value in (since, until, as_of) if value]
    return any(year < 2026 for year in years) or any(value[:4].isdigit() and int(value[:4]) < 2026 for value in dates) or bool(re.search(r"\b(historical|archive|old email|years ago)\b", query, re.IGNORECASE))


def historical_hits(config: SourceConfig, query: str, since: str, until: str, limit: int) -> list[dict[str, Any]]:
    if not config.mail_index.exists() or not (expression := fts_expression(query)):
        return []
    connection = sqlite3.connect(f"file:{config.mail_index}?mode=ro&immutable=1", uri=True)
    connection.row_factory = sqlite3.Row
    sql = """SELECT m.date_utc timestamp,m.subject title,m.sender author,m.message_id native_id,
                    s.path, m.byte_offset,m.byte_length,bm25(search) rank
             FROM search JOIN messages m ON m.id=search.rowid JOIN sources s ON s.id=m.source_id
             WHERE search MATCH ?"""
    params: list[Any] = [expression]
    if since:
        sql += " AND m.date_utc>=?"
        params.append(since)
    if until:
        sql += " AND m.date_utc<?"
        params.append(until)
    sql += " ORDER BY rank,m.id LIMIT ?"
    params.append(limit)
    try:
        rows = connection.execute(sql, params).fetchall()
    except sqlite3.DatabaseError:
        rows = []
    finally:
        connection.close()
    hits = []
    for row in rows:
        source_path = Path(row["path"])
        if not source_path.is_absolute():
            source_path = config.mail_index.parent / source_path
        hits.append({
            "source": "historical_mail", "timestamp": row["timestamp"] or "", "title": row["title"] or "",
            "author": row["author"] or "", "role": "", "native_id": row["native_id"] or "",
            "thread_id": "", "conversation_id": "",
            "locator": f'{source_path}#byte={row["byte_offset"]},{row["byte_length"]}',
            "snippet": " — ".join(filter(None, [row["title"], row["author"]])),
            "score": 0.0, "why": ["broad", "historical"],
        })
    return hits


def log_query(path: Path, *, mode: str, query: str, filters: dict[str, Any], hits: list[dict[str, Any]], started: float) -> None:
    entry = {
        "timestamp": dt.datetime.now(dt.UTC).isoformat(), "mode": mode, "query": query,
        "filters": filters, "result_count": len(hits),
        "result_sources": dict(sorted((source, sum(hit["source"] == source for hit in hits)) for source in {hit["source"] for hit in hits})),
        "latency_ms": round((time.perf_counter() - started) * 1000, 3),
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(compact_json(entry) + "\n")
    except OSError as error:
        typer.echo(f"warning: could not write context query log {path}: {error}", err=True)


def search_database(
    database: Path, query: str, *, sources: list[str] | None = None, since: str = "", until: str = "",
    as_of: str = "", limit: int = 20, config: SourceConfig | None = None,
    log_path: Path | None = None, mode: str = "search",
) -> list[dict[str, Any]]:
    started = time.perf_counter()
    if limit < 1:
        raise typer.BadParameter("--limit must be positive")
    config = config or SourceConfig.for_home(Path.home())
    since, until, as_of = parse_date(since), parse_date(until), parse_date(as_of)
    if since and until and since >= until:
        raise typer.BadParameter("--since must be before --until")
    if as_of and (not until or as_of < until):
        until = (dt.date.fromisoformat(as_of) + dt.timedelta(days=1)).isoformat()
    intent = intent_text(query)
    if not fts_expression(intent):
        return []
    connection = connect(database)
    candidates: dict[int, dict[str, Any]] = {}

    def add_ranking(rows: Iterable[sqlite3.Row], reason: str, weight: float) -> None:
        for rank, row in enumerate(rows, 1):
            candidate = candidates.setdefault(row["id"], {
                "row": row, "score": 0.0, "why": set(),
                "snippet": row["summary"] or row["body"][:300] or row["title"],
            })
            candidate["score"] += weight / (40 + rank)
            candidate["why"].add(reason)

    lexical_limit = max(limit * 6, 80)
    add_ranking(
        ranked_fts(connection, intent, sources=sources, since=since, until=until, limit=lexical_limit),
        "broad", 1.0,
    )
    subject, sender = cue(query, "Subject"), cue(query, "From")
    if subject:
        add_ranking(
            ranked_fts(connection, subject, column="title", sources=sources, since=since, until=until, limit=lexical_limit),
            "subject", 1.5,
        )
    if sender:
        add_ranking(
            ranked_fts(connection, sender, column="author", sources=sources, since=since, until=until, limit=lexical_limit),
            "sender", 1.2,
        )

    query_entities = unique_query_entities(connection, intent)
    for entity_id in query_entities:
        entity_rows = connection.execute(
            """SELECT i.*,ie.role entity_role FROM item_entities ie JOIN items i ON i.id=ie.item_id
               WHERE ie.entity_id=? ORDER BY i.timestamp DESC,i.id LIMIT 100""", (entity_id,)
        ).fetchall()
        for rank, row in enumerate(entity_rows, 1):
            if sources and row["source"] not in sources:
                continue
            if since and row["timestamp"] < since or until and row["timestamp"] >= until:
                continue
            candidate = candidates.setdefault(row["id"], {"row": row, "score": 0.0, "why": set(), "snippet": row["summary"] or row["body"][:300] or row["title"]})
            candidate["score"] += 1.4 / (40 + rank)
            candidate["why"].add("entity")
            if row["entity_role"] == "evidence":
                candidate["score"] += 0.025
                candidate["why"].add("about-link")

    if ACTION_INTENT.search(intent):
        action_sql = "SELECT i.*,a.action_text FROM actions a JOIN items i ON i.id=a.item_id WHERE 1"
        action_params: list[Any] = []
        if sources:
            action_sql += f" AND i.source IN ({','.join('?' for _ in sources)})"
            action_params.extend(sources)
        if since:
            action_sql += " AND i.timestamp>=?"
            action_params.append(since)
        if until:
            action_sql += " AND i.timestamp<?"
            action_params.append(until)
        action_sql += " ORDER BY i.timestamp DESC,a.id"
        action_rows = connection.execute(action_sql, action_params).fetchall()
        action_terms = {token for token in query_tokens(intent) if token not in ACTION_STOP}
        action_items: set[int] = set()
        for rank, row in enumerate(action_rows, 1):
            haystack = f'{row["action_text"]} {row["title"]}'.casefold()
            if action_terms and not any(term in haystack for term in action_terms):
                continue
            candidate = candidates.setdefault(row["id"], {"row": row, "score": 0.0, "why": set(), "snippet": row["action_text"]})
            if row["id"] not in action_items:
                candidate["score"] += 1.2 / (40 + rank)
                candidate["snippet"] = row["action_text"]
                action_items.add(row["id"])
            candidate["why"].add("action")

    if RECENT_INTENT.search(intent) or mode == "recent":
        reference = dt.date.fromisoformat(as_of) if as_of else dt.datetime.now(dt.UTC).date()
        for candidate in candidates.values():
            if day := iso_day(candidate["row"]["timestamp"]):
                age = (reference - day).days
                if 0 <= age <= 365:
                    candidate["score"] += 0.04 * (1 - age / 366)
                    candidate["why"].add("recent")

    hits = [hit_from_row(value["row"], value["snippet"], value["score"], value["why"]) for value in candidates.values()]
    if needs_historical(intent, since, until, as_of) and (not sources or "mail" in sources or "historical_mail" in sources):
        history = historical_hits(config, intent, since, until, max(limit * 3, 30))
        for rank, hit in enumerate(history, 1):
            hit["score"] = round(1 / (60 + rank), 8)
        hits.extend(history)
    hits.sort(
        key=lambda hit: (
            -hit["score"],
            -(iso_day(hit["timestamp"]) or dt.date.min).toordinal(),
            hit["source"],
            hit["native_id"],
        )
    )
    hits = hits[:limit]
    connection.close()
    log_query(
        log_path or Path(os.environ.get("CONTEXT_QUERY_LOG", config.log_path)), mode=mode, query=query,
        filters={"sources": sources or [], "since": since, "until": until, "as_of": as_of, "limit": limit},
        hits=hits, started=started,
    )
    return hits


def direct_item_hit(row: sqlite3.Row, why: str) -> dict[str, Any]:
    return hit_from_row(row, row["body"][:500] or row["summary"] or row["title"], 1.0, {why})


def thread_results(database: Path, thread_id: str) -> list[dict[str, Any]]:
    connection = connect(database)
    rows = connection.execute("SELECT * FROM items WHERE thread_id=? ORDER BY timestamp,id", (thread_id,)).fetchall()
    connection.close()
    return [direct_item_hit(row, "broad") for row in rows]


def resolve_entities(connection: sqlite3.Connection, person: str) -> list[sqlite3.Row]:
    query = person.strip()
    exact = connection.execute(
        """SELECT e.entity_id,e.canonical_name,e.profile_path FROM entities e JOIN aliases a USING(entity_id)
           WHERE a.alias=? COLLATE NOCASE GROUP BY e.entity_id ORDER BY e.canonical_name,e.entity_id""",
        (query,),
    ).fetchall()
    if exact:
        return exact
    prefix_ids = safe_prefix_entities(database_alias_entities(connection), query)
    return [
        row for row in connection.execute(
            "SELECT entity_id,canonical_name,profile_path FROM entities ORDER BY canonical_name,entity_id"
        ) if row["entity_id"] in prefix_ids
    ]


def ambiguity_result(person: str, matches: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    return [{"ambiguity": person.strip(), "matches": [row["canonical_name"] for row in matches]}]


def entity_results(database: Path, person: str, since: str = "", limit: int = 50) -> list[dict[str, Any]]:
    connection = connect(database)
    matches = resolve_entities(connection, person)
    if len(matches) != 1:
        connection.close()
        return ambiguity_result(person, matches) if matches else []
    entity = matches[0]
    sql = """SELECT DISTINCT i.* FROM item_entities ie JOIN items i ON i.id=ie.item_id
             WHERE ie.entity_id=?"""
    params: list[Any] = [entity["entity_id"]]
    if since:
        sql += " AND i.timestamp>=?"
        params.append(parse_date(since))
    sql += " ORDER BY i.timestamp DESC,i.id LIMIT ?"
    params.append(limit)
    items = [direct_item_hit(row, "entity") for row in connection.execute(sql, params)]
    connection.close()
    return [{"entity_id": entity["entity_id"], "canonical_name": entity["canonical_name"], "profile_path": entity["profile_path"], "items": items}]


def open_loop_results(database: Path, entity: str = "", limit: int = 50) -> list[dict[str, Any]]:
    connection = connect(database)
    entity_id = None
    if entity:
        matches = resolve_entities(connection, entity)
        if len(matches) != 1:
            connection.close()
            return ambiguity_result(entity, matches) if matches else []
        entity_id = matches[0]["entity_id"]
    sql = """SELECT a.*,i.timestamp,i.title,i.locator FROM actions a JOIN items i ON i.id=a.item_id"""
    params: list[Any] = []
    if entity_id is not None:
        sql += " WHERE EXISTS (SELECT 1 FROM item_entities ie WHERE ie.item_id=i.id AND ie.entity_id=?)"
        params.append(entity_id)
    sql += " ORDER BY i.timestamp DESC,a.id LIMIT ?"
    params.append(limit * 5)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in connection.execute(sql, params):
        grouped[row["fingerprint"]].append({
            "action_text": row["action_text"], "owner": row["owner"], "due_date": row["due_date"],
            "timestamp": row["timestamp"], "title": row["title"], "locator": row["locator"],
        })
    output = []
    for fingerprint, occurrences in grouped.items():
        latest = max(item["timestamp"] for item in occurrences)
        later_evidence = []
        if entity_id is not None:
            later_evidence = [
                direct_item_hit(row, "entity")
                for row in connection.execute(
                    """SELECT DISTINCT i.* FROM item_entities ie JOIN items i ON i.id=ie.item_id
                       WHERE ie.entity_id=? AND i.timestamp>? ORDER BY i.timestamp LIMIT 10""",
                    (entity_id, latest),
                )
            ]
        output.append({
            "fingerprint": fingerprint, "action_text": occurrences[0]["action_text"],
            "occurrences": occurrences, "later_evidence": later_evidence, "completion_evidence": None,
        })
    connection.close()
    return sorted(output, key=lambda item: (-len(item["occurrences"]), item["fingerprint"]))[:limit]


def style_results(database: Path, query: str, *, limit: int = 20, config: SourceConfig | None = None, log_path: Path | None = None) -> list[dict[str, Any]]:
    config = config or SourceConfig.for_home(Path.home())
    hits = search_database(database, query, sources=["chatgpt", "claude", "mail"], limit=limit * 5, config=config, log_path=log_path, mode="style")
    return [hit for hit in hits if hit["role"] == "user"][:limit]


def assets_results(database: Path, query: str, *, limit: int = 20, config: SourceConfig | None = None, log_path: Path | None = None) -> list[dict[str, Any]]:
    return search_database(database, query, sources=["asset_registry"], limit=limit, config=config, log_path=log_path, mode="assets")


def status_database(database: Path, config: SourceConfig | None = None, *, identities: bool = False) -> dict[str, Any]:
    config = config or SourceConfig.for_home(Path.home())
    connection = connect(database)
    rows = connection.execute("SELECT * FROM source_status ORDER BY source").fetchall()
    sources = {
        row["source"]: {key: row[key] for key in row.keys() if key != "source"}  # noqa: SIM118
        for row in rows
    }
    built_at = max((row["built_at"] for row in rows), default="")
    missing = [source for source, row in sources.items() if row["warning"]]
    now = dt.datetime.now(dt.UTC).date()
    stale = []
    for source, row in sources.items():
        freshness = row["source_mtime"] if source in {"about", "asset_registry"} else row["latest_item_time"]
        if (day := iso_day(freshness)) and (now - day).days > 14:
            stale.append(source)
    result: dict[str, Any] = {
        "database": str(Path(database).expanduser()), "database_bytes": Path(database).expanduser().stat().st_size,
        "built_at": built_at, "sources": sources, "missing_sources": missing, "stale_sources": stale,
    }
    if identities:
        ambiguous = [
            dict(row) for row in connection.execute(
                """SELECT alias,count(DISTINCT entity_id) profile_count FROM aliases
                   GROUP BY alias HAVING profile_count>1 ORDER BY alias"""
            )
        ]
        duplicates = [
            dict(row) for row in connection.execute(
                """SELECT lower(canonical_name) name,count(*) profile_count FROM entities
                   GROUP BY lower(canonical_name) HAVING profile_count>1 ORDER BY name"""
            )
        ]
        result["identities"] = {"ambiguous_aliases": ambiguous, "duplicate_profile_candidates": duplicates}
    connection.close()
    return result


def describe() -> dict[str, Any]:
    common_hit = ["source", "timestamp", "title", "author", "role", "native_id", "thread_id", "conversation_id", "locator", "snippet", "score", "why"]
    return {
        "name": "context.py", "database": str(DEFAULT_DB),
        "principle": "Candidate discovery only; deep-read original locators before claims.",
        "output": {"default": "json", "search_hit_fields": common_hit},
        "commands": {
            "rebuild": {},
            "search": {"query": "string", "source": "repeatable string", "since": "date", "until": "date", "as_of": "date", "limit": "integer"},
            "entity": {"person": "string", "since": "date"},
            "recent": {"query": "string", "days": "positive integer"},
            "open-loops": {"entity": "string?"}, "thread": {"thread_id": "string"},
            "style": {"query": "string"}, "assets": {"query": "string"},
            "status": {"identities": "boolean"},
        },
    }


def emit(value: Any) -> None:
    typer.echo(json.dumps(value, ensure_ascii=False, indent=2))


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    database: Annotated[Path, typer.Option("--database", "--db", help="Context SQLite database")] = DEFAULT_DB,
    describe_flag: Annotated[bool, typer.Option("--describe", help="Print machine-readable CLI schema")] = False,
) -> None:
    ctx.ensure_object(dict)
    ctx.obj["database"] = database.expanduser()
    if describe_flag:
        emit(describe())
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


@app.command()
def rebuild(ctx: typer.Context) -> None:
    """Rebuild, validate, and atomically replace the entire index."""
    emit(rebuild_database(ctx.obj["database"]))


@app.command("search")
def search_command(
    ctx: typer.Context, query: str,
    source: Annotated[list[str] | None, typer.Option("--source")] = None,
    since: str = "", until: str = "",
    as_of: Annotated[str, typer.Option("--as-of")] = "", limit: int = 20,
) -> None:
    """Find cross-source lexical candidates with explained deterministic routing."""
    emit(search_database(ctx.obj["database"], query, sources=source or None, since=since, until=until, as_of=as_of, limit=limit))


@app.command()
def entity(ctx: typer.Context, person: str, since: str = "", limit: int = 50) -> None:
    """Show evidence explicitly connected to one unambiguous About identity."""
    emit(entity_results(ctx.obj["database"], person, since, limit))


@app.command()
def recent(ctx: typer.Context, query: str, days: int = typer.Option(..., min=1), limit: int = 20) -> None:
    """Search within the last N days and apply the deterministic recency signal."""
    now = dt.datetime.now(dt.UTC)
    emit(search_database(ctx.obj["database"], query, since=f"{days}d", as_of=now.date().isoformat(), limit=limit, mode="recent"))


@app.command("open-loops")
def open_loops(ctx: typer.Context, entity: str = "", limit: int = 50) -> None:
    """Group explicit transcript actions without inferring pending or done state."""
    emit(open_loop_results(ctx.obj["database"], entity, limit))


@app.command()
def thread(ctx: typer.Context, thread_id: str) -> None:
    """Reconstruct a Gmail or Google Chat thread using its native thread ID."""
    emit(thread_results(ctx.obj["database"], thread_id))


@app.command()
def style(ctx: typer.Context, query: str, limit: int = 20) -> None:
    """Find user-authored chat turns and sent mail; exclude assistant prose."""
    emit(style_results(ctx.obj["database"], query, limit=limit))


@app.command()
def assets(ctx: typer.Context, query: str, limit: int = 20) -> None:
    """Find entries in existing asset registries."""
    emit(assets_results(ctx.obj["database"], query, limit=limit))


@app.command()
def status(ctx: typer.Context, identities: bool = False) -> None:
    """Report index/source freshness and optional identity ambiguity diagnostics."""
    emit(status_database(ctx.obj["database"], identities=identities))


if __name__ == "__main__":
    app()
