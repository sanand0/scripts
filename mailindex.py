#!/usr/bin/env -S uv run --script
"""Build a compact, resumable SQLite FTS index for ~/Documents/Mail/*.mbox."""

# Source: https://chatgpt.com/c/6a633fff-824c-83ec-b378-b620e4d1a4f2

from __future__ import annotations

import argparse
import hashlib
import html
import json
import mmap
import re
import sqlite3
import sys
import time
from collections.abc import Iterator
from datetime import UTC
from email import policy
from email.header import decode_header, make_header
from email.parser import BytesHeaderParser, BytesParser
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

VERSION = "1.3.0"
SCHEMA_VERSION = 103
TOKENIZER = "unicode61 remove_diacritics 2"
MAIL_DIR = Path.home() / "Documents" / "Mail"
DEFAULT_DATABASE = "mail-index.sqlite"
MAX_MESSAGE_BYTES = 100 * 1024 * 1024
MAX_TEXT_CHARS = 10 * 1024 * 1024


class HTMLText(HTMLParser):
    """Extract visible text from an HTML email body."""

    BLOCK_TAGS = {"br", "p", "div", "li", "tr", "h1", "h2", "h3"}
    HIDDEN_TAGS = {"script", "style", "svg", "template"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.HIDDEN_TAGS:
            self.hidden += 1
        elif not self.hidden and tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.HIDDEN_TAGS and self.hidden:
            self.hidden -= 1
        elif not self.hidden and tag in self.BLOCK_TAGS - {"br", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(data)


def fail(message: str, hint: str | None = None) -> None:
    payload = {"ok": False, "error": message}
    if hint:
        payload["hint"] = hint
    print(json.dumps(payload, ensure_ascii=False), file=sys.stderr)
    raise SystemExit(2)


def log(event: str, **fields: Any) -> None:
    details = " ".join(
        f"{key}={json.dumps(value, ensure_ascii=False)}"
        for key, value in fields.items()
    )
    print(f"[{event}] {details}".rstrip(), file=sys.stderr, flush=True)


def mail_file(name: str, suffix: str) -> Path:
    """Return a simple filename rooted in MAIL_DIR, never beside the script."""
    path = Path(name)
    if path.is_absolute() or len(path.parts) != 1 or path.suffix.lower() != suffix:
        fail(f"Expected a {suffix} filename in {MAIL_DIR}, got {name!r}")
    return MAIL_DIR / path


def connect(path: Path, readonly: bool = False) -> sqlite3.Connection:
    if readonly:
        if not path.exists():
            fail(f"Index does not exist: {path}")
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    else:
        connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 30000")
    if not readonly:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        connection.execute("PRAGMA temp_store = MEMORY")
        connection.execute("PRAGMA cache_size = -200000")
    return connection


def schema_version(connection: sqlite3.Connection) -> int:
    return connection.execute("PRAGMA user_version").fetchone()[0]


def require_schema(connection: sqlite3.Connection) -> None:
    existing = schema_version(connection)
    if existing != SCHEMA_VERSION:
        fail(
            f"Incompatible index schema {existing or 'unknown'}",
            "Choose a v1.3 database filename or delete that index and rebuild.",
        )


def initialize(connection: sqlite3.Connection) -> None:
    existing = schema_version(connection)
    has_tables = connection.execute(
        "SELECT EXISTS(SELECT 1 FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%')"
    ).fetchone()[0]
    if has_tables and existing != SCHEMA_VERSION:
        fail(
            f"Incompatible index schema {existing or 'unknown'}",
            "Choose a new --database filename or delete that index and rebuild.",
        )
    try:
        connection.executescript(
            f"""
            CREATE TABLE IF NOT EXISTS sources (
                id INTEGER PRIMARY KEY,
                path TEXT NOT NULL UNIQUE,
                size INTEGER NOT NULL,
                fingerprint TEXT NOT NULL,
                next_offset INTEGER NOT NULL DEFAULT 0,
                message_count INTEGER NOT NULL DEFAULT 0,
                partial_bodies INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'pending'
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY,
                source_id INTEGER NOT NULL REFERENCES sources(id),
                byte_offset INTEGER NOT NULL,
                byte_length INTEGER NOT NULL,
                date_utc TEXT,
                sender TEXT NOT NULL DEFAULT '',
                recipients TEXT NOT NULL DEFAULT '',
                subject TEXT NOT NULL DEFAULT '',
                labels TEXT NOT NULL DEFAULT '',
                message_id TEXT NOT NULL DEFAULT '',
                in_reply_to TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS messages_date_idx ON messages(date_utc);
            CREATE VIRTUAL TABLE IF NOT EXISTS search USING fts5(
                subject, sender, recipients, labels, body,
                content='', detail=column, tokenize='{TOKENIZER}'
            );
            PRAGMA user_version = {SCHEMA_VERSION};
            """
        )
    except sqlite3.OperationalError as error:
        fail(f"SQLite FTS5 is unavailable: {error}")
    connection.commit()


def fingerprint(path: Path, size: int | None = None) -> str:
    """Fingerprint a file prefix using its size and boundary MiBs."""
    actual_size = path.stat().st_size
    size = actual_size if size is None else size
    if not 0 <= size <= actual_size:
        raise ValueError(f"Cannot fingerprint {size} bytes of a {actual_size}-byte file")
    digest = hashlib.sha256(str(size).encode())
    with path.open("rb") as handle:
        digest.update(handle.read(min(size, 1 << 20)))
        if size > 1 << 20:
            handle.seek(size - (1 << 20))
            digest.update(handle.read(1 << 20))
    return digest.hexdigest()


def discover(pattern: str) -> list[Path]:
    if "/" in pattern or "\\" in pattern or ".." in pattern:
        fail("--pattern must be a filename glob such as '*.mbox'")
    files = sorted(
        (path for path in MAIL_DIR.glob(pattern) if path.is_file()),
        key=lambda path: path.name.casefold(),
    )
    if not files:
        fail(f"No files match {pattern!r} in {MAIL_DIR}")
    return files


def records(path: Path, start: int) -> Iterator[tuple[int, int, int, bytes]]:
    """Yield content offset, byte length, next separator offset, and RFC-822 bytes."""
    if path.stat().st_size == 0:
        return
    with path.open("rb") as handle, mmap.mmap(
        handle.fileno(), 0, access=mmap.ACCESS_READ
    ) as mm:
        if start:
            if start >= len(mm):
                return
            if mm[start : start + 5] != b"From ":
                raise ValueError(f"Checkpoint {start} is not an mbox separator")
            separator = start
        elif mm[:5] == b"From ":
            separator = 0
        else:
            marker = mm.find(b"\nFrom ")
            if marker < 0:
                raise ValueError("No mbox 'From ' separator found")
            separator = marker + 1

        while separator < len(mm):
            line_end = mm.find(b"\n", separator)
            if line_end < 0:
                raise ValueError(f"Incomplete mbox separator at byte {separator}")
            byte_offset = line_end + 1
            marker = mm.find(b"\nFrom ", byte_offset)
            next_offset = len(mm) if marker < 0 else marker + 1
            raw = mm[byte_offset:next_offset]
            yield byte_offset, len(raw), next_offset, raw
            separator = next_offset


def decode_header_value(value: Any) -> str:
    if value is None:
        return ""
    try:
        text = value if isinstance(value, str) else str(value)
        return str(make_header(decode_header(text))).replace("\x00", "")
    except Exception:  # A malformed header should not abort the archive.
        try:
            return str(value).replace("\x00", "")
        except Exception:
            return ""


def header(message: Any, name: str) -> str:
    if message is None:
        return ""
    try:
        values = message.get_all(name, [])
    except Exception:
        try:
            value = message.get(name)
        except Exception:
            return ""
        values = [] if value is None else [value]
    return ", ".join(filter(None, map(decode_header_value, values)))


def utc_date(raw: str) -> str | None:
    try:
        value = parsedate_to_datetime(raw)
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat()
    except (TypeError, ValueError, OverflowError):
        return None


def part_text(part: Any) -> str:
    payload = part.get_payload(decode=True)
    if payload is None:
        value = part.get_payload()
        return value if isinstance(value, str) else ""
    try:
        return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")


def body_text(message: Any) -> tuple[str, bool]:
    plain: list[str] = []
    rich: list[str] = []
    for part in message.walk() if message.is_multipart() else [message]:
        if part.is_multipart() or part.get_content_maintype() != "text":
            continue
        if part.get_content_disposition() == "attachment" or part.get_filename():
            continue
        if part.get_content_type() == "text/plain":
            plain.append(part_text(part))
        elif part.get_content_type() == "text/html":
            rich.append(part_text(part))

    if plain:
        value = "\n".join(plain)
    else:
        parser = HTMLText()
        try:
            parser.feed("\n".join(rich))
            value = "".join(parser.parts)
        except Exception:
            value = re.sub(r"(?s)<[^>]+>", " ", html.unescape("\n".join(rich)))
    value = re.sub(r"\s+", " ", value.replace("\x00", " ")).strip()
    return value[:MAX_TEXT_CHARS], len(value) > MAX_TEXT_CHARS


def headers_only(raw: bytes) -> bytes:
    ends = [
        position + len(marker)
        for marker in (b"\r\n\r\n", b"\n\n")
        if (position := raw.find(marker)) >= 0
    ]
    return raw[: min(min(ends) if ends else len(raw), 2 << 20)]


def fields(message: Any, body: str) -> dict[str, Any]:
    return {
        "date_utc": utc_date(header(message, "date")),
        "sender": header(message, "from"),
        "recipients": " | ".join(
            filter(None, (header(message, "to"), header(message, "cc"), header(message, "bcc")))
        ),
        "subject": header(message, "subject"),
        "labels": header(message, "x-gmail-labels"),
        "message_id": header(message, "message-id"),
        "in_reply_to": header(message, "in-reply-to"),
        "body": body,
    }


def parse(raw: bytes) -> tuple[dict[str, Any], bool]:
    """Return searchable fields and whether the body may be incomplete."""
    try:
        if len(raw) > MAX_MESSAGE_BYTES:
            message = BytesHeaderParser(policy=policy.default).parsebytes(headers_only(raw))
            return fields(message, ""), True
        message = BytesParser(policy=policy.default).parsebytes(raw)
        body, truncated = body_text(message)
        return fields(message, body), truncated
    except Exception as error:
        log("message_parse_error", error=f"{type(error).__name__}: {error}")
        try:
            message = BytesHeaderParser(policy=policy.compat32).parsebytes(headers_only(raw))
        except Exception:
            message = None
        return fields(message, ""), True


def plan(connection: sqlite3.Connection | None, path: Path) -> dict[str, Any]:
    size = path.stat().st_size
    row = None if connection is None else connection.execute(
        "SELECT * FROM sources WHERE path = ?", (path.name,)
    ).fetchone()
    if row is None:
        action, next_offset = "add", 0
    elif size < row["size"] or fingerprint(path, row["size"]) != row["fingerprint"]:
        action, next_offset = "changed", row["next_offset"]
    elif size > row["size"]:
        action, next_offset = "append", row["next_offset"]
    elif row["status"] == "complete" and row["next_offset"] == size:
        action, next_offset = "skip", size
    else:
        action, next_offset = "resume", row["next_offset"]
    return {
        "path": path.name,
        "size": size,
        "fingerprint": fingerprint(path),
        "action": action,
        "next_offset": next_offset,
    }


def index_file(
    connection: sqlite3.Connection,
    path: Path,
    item: dict[str, Any],
    batch_size: int,
    remaining: int | None,
) -> dict[str, Any]:
    if item["action"] == "changed":
        fail(
            f"Previously indexed mbox changed: {path.name}",
            "Choose a new database filename or delete the index and rebuild.",
        )
    if item["action"] == "skip":
        return {"path": path.name, "action": "skipped", "indexed": 0}

    if item["action"] == "add":
        cursor = connection.execute(
            "INSERT INTO sources(path, size, fingerprint, status) VALUES (?, ?, ?, 'indexing')",
            (path.name, item["size"], item["fingerprint"]),
        )
        source_id = cursor.lastrowid
    else:
        source_id = connection.execute(
            "SELECT id FROM sources WHERE path = ?", (path.name,)
        ).fetchone()[0]
        connection.execute(
            "UPDATE sources SET size=?, fingerprint=?, status='indexing' WHERE id=?",
            (item["size"], item["fingerprint"], source_id),
        )
    connection.commit()

    next_id = connection.execute("SELECT coalesce(max(id), 0) + 1 FROM messages").fetchone()[0]
    offset = item["next_offset"]
    indexed = partial_bodies = 0
    batch: list[tuple[int, int, int, bytes]] = []
    last_log = time.monotonic()
    log("source_start", path=path.name, size=item["size"], offset=offset, action=item["action"])

    def commit(items: list[tuple[int, int, int, bytes]]) -> None:
        nonlocal next_id, offset, indexed, partial_bodies, last_log
        message_rows = []
        search_rows = []
        partial = 0
        for byte_offset, byte_length, next_offset, raw in items:
            data, incomplete = parse(raw)
            message_rows.append(
                (
                    next_id,
                    source_id,
                    byte_offset,
                    byte_length,
                    data["date_utc"],
                    data["sender"],
                    data["recipients"],
                    data["subject"],
                    data["labels"],
                    data["message_id"],
                    data["in_reply_to"],
                )
            )
            search_rows.append(
                (next_id, data["subject"], data["sender"], data["recipients"], data["labels"], data["body"])
            )
            next_id += 1
            offset = next_offset
            partial += incomplete

        try:
            connection.execute("BEGIN")
            connection.executemany(
                "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                message_rows,
            )
            connection.executemany(
                "INSERT INTO search(rowid, subject, sender, recipients, labels, body) VALUES (?, ?, ?, ?, ?, ?)",
                search_rows,
            )
            connection.execute(
                """UPDATE sources
                   SET next_offset=?, message_count=message_count+?, partial_bodies=partial_bodies+?
                   WHERE id=?""",
                (offset, len(items), partial, source_id),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise

        indexed += len(items)
        partial_bodies += partial
        if time.monotonic() - last_log >= 5:
            log(
                "checkpoint",
                path=path.name,
                indexed=indexed,
                percent=round(offset * 100 / max(1, item["size"]), 2),
                partial_bodies=partial_bodies,
            )
            last_log = time.monotonic()

    try:
        for record in records(path, offset):
            batch.append(record)
            reached_limit = remaining is not None and indexed + len(batch) >= remaining
            if len(batch) >= batch_size or reached_limit:
                commit(batch)
                batch.clear()
                if reached_limit:
                    break
        if batch:
            commit(batch)
    except Exception as error:
        connection.execute("UPDATE sources SET status='error' WHERE id=?", (source_id,))
        connection.commit()
        fail(f"Failed in {path.name} near byte {offset}: {type(error).__name__}: {error}")

    complete = offset >= item["size"]
    connection.execute(
        "UPDATE sources SET status=? WHERE id=?",
        ("complete" if complete else "partial", source_id),
    )
    connection.commit()
    log(
        "source_done",
        path=path.name,
        indexed=indexed,
        complete=complete,
        partial_bodies=partial_bodies,
    )
    return {
        "path": path.name,
        "action": "completed" if complete else "partial",
        "indexed": indexed,
        "partial_bodies": partial_bodies,
        "next_offset": offset,
    }


def status(connection: sqlite3.Connection, database: Path) -> dict[str, Any]:
    return {
        "ok": True,
        "version": VERSION,
        "mail_directory": str(MAIL_DIR),
        "database": str(database),
        "database_bytes": database.stat().st_size,
        "messages": connection.execute("SELECT count(*) FROM messages").fetchone()[0],
        "sources": [
            dict(row)
            for row in connection.execute(
                """SELECT path, size, next_offset, message_count, partial_bodies, status
                   FROM sources ORDER BY path"""
            )
        ],
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--database", "-d", default=DEFAULT_DATABASE, help="SQLite filename in ~/Documents/Mail")
    result.add_argument("--pattern", default="*.mbox", help="Mbox filename glob in ~/Documents/Mail")
    result.add_argument("--batch-size", type=int, default=500, help="Messages committed per transaction")
    result.add_argument("--max-messages", type=int, help="Stop cleanly after N newly indexed messages")
    result.add_argument("--vacuum", action="store_true", help="Compact the completed index after building")
    result.add_argument("--dry-run", action="store_true", help="Show planned actions without writing")
    result.add_argument("--status", action="store_true", help="Report checkpoints without building")
    return result


def main() -> None:
    args = parser().parse_args()
    if args.batch_size < 1 or args.max_messages is not None and args.max_messages < 1:
        fail("--batch-size and --max-messages must be positive")
    if not MAIL_DIR.is_dir():
        fail(f"Mail directory does not exist: {MAIL_DIR}")

    database = mail_file(args.database, ".sqlite")
    if args.status:
        connection = connect(database, readonly=True)
        try:
            require_schema(connection)
            print(json.dumps(status(connection, database), ensure_ascii=False, indent=2))
        finally:
            connection.close()
        return

    files = discover(args.pattern)
    if args.dry_run:
        connection = connect(database, readonly=True) if database.exists() else None
        try:
            if connection:
                require_schema(connection)
            print(
                json.dumps(
                    {
                        "ok": True,
                        "version": VERSION,
                        "mail_directory": str(MAIL_DIR),
                        "database": str(database),
                        "sources": [plan(connection, path) for path in files],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        finally:
            if connection:
                connection.close()
        return

    connection = connect(database)
    started = time.monotonic()
    try:
        initialize(connection)
        plans = [plan(connection, path) for path in files]
        changed = [item["path"] for item in plans if item["action"] == "changed"]
        if changed:
            fail(f"Previously indexed mbox files changed: {changed}")

        results = []
        remaining = args.max_messages
        for path, item in zip(files, plans, strict=True):
            if remaining is not None and remaining <= 0:
                break
            result = index_file(connection, path, item, args.batch_size, remaining)
            results.append(result)
            if remaining is not None:
                remaining -= result["indexed"]

        connection.execute("PRAGMA optimize")
        connection.commit()
        if args.vacuum:
            log("vacuum_start", database=database.name)
            connection.execute("INSERT INTO search(search) VALUES('optimize')")
            connection.commit()
            connection.execute("VACUUM")
            log("vacuum_done", database=database.name)
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        payload = status(connection, database)
        payload.update(seconds=round(time.monotonic() - started, 2), run=results)
    finally:
        connection.close()
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
