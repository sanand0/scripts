#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "typer>=0.12",
# ]
# ///

"""Export Microsoft Edge browsing history across all profiles.

Examples:
  browsing_history.py --root ~/.config/microsoft-edge-cdp --sync-only
  browsing_history.py --no-sync --since 30d > history.tsv
  browsing_history.py --format json --fields timestamp,activity_source,url | jaq '.[0]'
  browsing_history.py --describe | jaq .
"""

from __future__ import annotations

import csv
import hashlib
import heapq
import json
import shutil
import sqlite3
import sys
import tempfile
from calendar import monthrange
from collections.abc import Iterator, Sequence
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import typer

app = typer.Typer(add_completion=False, no_args_is_help=False)

CHROME_EPOCH = datetime(1601, 1, 1, tzinfo=timezone.utc)
DEFAULT_DB = Path("~/Documents/data/browsing-history.db").expanduser()
DEFAULT_FIELDS = [
    "timestamp",
    "url",
    "title",
    "activity_source",
    "visit_count",
    "typed_count",
    "number_of_hits",
    "transition",
    "transition_type",
    "visit_duration_seconds",
    "from_url",
    "search_term",
    "shortcut_text",
    "profile",
    "profile_name",
    "source",
    "visit_id",
    "url_id",
    "shortcut_id",
]
SQLITE_SIDECARS = ("-journal", "-wal", "-shm")
ACTIVITY_FILES = ("History", "Shortcuts")
TRANSITIONS = {
    0: "link",
    1: "typed",
    2: "auto_bookmark",
    3: "auto_subframe",
    4: "manual_subframe",
    5: "generated",
    6: "start_page",
    7: "form_submit",
    8: "reload",
    9: "keyword",
    10: "keyword_generated",
}
DESCRIBE = {
    "name": "browsing_history.py",
    "purpose": "Sync Microsoft Edge URL activity into SQLite and query it.",
    "outputs": ["tsv", "csv", "json"],
    "database": str(DEFAULT_DB),
    "default_fields": DEFAULT_FIELDS,
    "discovery": [
        "~/.config/microsoft-edge-cdp (preferred)",
        "~/.config/microsoft-edge and ~/.config/microsoft-edge-*",
        "~/.var/app/com.microsoft.Edge/config/microsoft-edge*",
        "~/snap/microsoft-edge/common/.config/microsoft-edge*",
        "Any repeated --root path",
    ],
    "activity_sources": {
        "history": "Canonical visits from History.visits joined to History.urls.",
        "shortcut": "Recovered omnibox URL activity from Shortcuts.omni_box_shortcuts.",
    },
    "lock_safety": "Copies SQLite databases plus journal/WAL sidecars to a temp dir before reads.",
}
DB_COLUMNS = [
    "activity_source",
    "record_id",
    "timestamp",
    "sort_visit_time",
    "url",
    "title",
    "visit_count",
    "typed_count",
    "number_of_hits",
    "transition",
    "transition_type",
    "visit_duration_seconds",
    "from_url",
    "search_term",
    "shortcut_text",
    "shortcut_contents",
    "shortcut_description",
    "shortcut_type",
    "document_type",
    "last_visit_time",
    "hidden",
    "profile",
    "profile_name",
    "source",
    "visit_id",
    "url_id",
    "shortcut_id",
]


def chrome_time(dt: datetime) -> int:
    return int((dt.astimezone(timezone.utc) - CHROME_EPOCH).total_seconds() * 1_000_000)


def from_chrome_time(value: int | None) -> str:
    if not value:
        return ""
    return (CHROME_EPOCH + timedelta(microseconds=value)).isoformat().replace("+00:00", "Z")


def add_months(dt: datetime, months: int) -> datetime:
    month = dt.month - 1 + months
    year = dt.year + month // 12
    month = month % 12 + 1
    day = min(dt.day, monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def parse_time(value: str | None, end: bool = False) -> int | None:
    if not value:
        return None
    text = value.strip().lower()
    relative = text[:-4].strip() if text.endswith(" ago") else text
    now = datetime.now(timezone.utc)
    if relative.endswith("d") and relative[:-1].isdigit():
        dt = now - timedelta(days=int(relative[:-1]))
        return chrome_time(dt)
    if relative.endswith("h") and relative[:-1].isdigit():
        dt = now - timedelta(hours=int(relative[:-1]))
        return chrome_time(dt)
    if relative.endswith("m") and relative[:-1].isdigit():
        dt = add_months(now, -int(relative[:-1]))
        return chrome_time(dt)
    parts = relative.split()
    if len(parts) == 2 and parts[0].isdigit() and parts[1] in {"month", "months"}:
        dt = add_months(now, -int(parts[0]))
        return chrome_time(dt)
    if len(text) == 10:
        dt = datetime.fromisoformat(text).replace(tzinfo=timezone.utc)
        if end:
            dt += timedelta(days=1)
        return chrome_time(dt)
    dt = datetime.fromisoformat(text.replace("z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return chrome_time(dt)


def default_roots() -> list[Path]:
    home = Path.home()
    patterns = [
        ".config/microsoft-edge-cdp",
        ".config/microsoft-edge",
        ".config/microsoft-edge-*",
        ".var/app/com.microsoft.Edge/config/microsoft-edge*",
        "snap/microsoft-edge/common/.config/microsoft-edge*",
    ]
    roots: list[Path] = []
    seen: set[Path] = set()
    for pattern in patterns:
        for root in sorted(home.glob(pattern)):
            resolved = root.resolve()
            if resolved not in seen:
                seen.add(resolved)
                roots.append(root)
    return roots


def find_activity_files(roots: Sequence[Path]) -> list[Path]:
    paths: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        expanded = root.expanduser()
        if expanded.name in ACTIVITY_FILES:
            matches = [expanded]
        else:
            profile_dirs = [expanded, *[path for path in sorted(expanded.iterdir()) if path.is_dir()]] if expanded.is_dir() else []
            matches = [profile / name for profile in profile_dirs for name in ACTIVITY_FILES if (profile / name).is_file()]
            if not matches:
                matches = [path for name in ACTIVITY_FILES for path in sorted(expanded.rglob(name))]
        for path in matches:
            resolved = path.resolve()
            if resolved in seen or not path.is_file():
                continue
            seen.add(resolved)
            paths.append(path)
    return paths


def copy_sqlite(path: Path, target: Path) -> Path:
    copy = target / path.name
    shutil.copy2(path, copy)
    for suffix in SQLITE_SIDECARS:
        sidecar = path.with_name(path.name + suffix)
        if sidecar.exists():
            shutil.copy2(sidecar, target / (path.name + suffix))
    return copy


def table_exists(con: sqlite3.Connection, name: str) -> bool:
    row = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
    return row is not None


def columns(con: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in con.execute(f"PRAGMA table_info({table})")}


@lru_cache(maxsize=None)
def profile_name(profile_path: Path) -> str:
    prefs = profile_path / "Preferences"
    if not prefs.exists():
        return ""
    try:
        data = json.loads(prefs.read_text())
    except (OSError, json.JSONDecodeError):
        return ""
    account_info = data.get("account_info") or [{}]
    return str(data.get("profile", {}).get("name") or account_info[0].get("full_name") or "")


def transition_type(value: int | None) -> str:
    if value is None:
        return ""
    label = TRANSITIONS.get(value & 0xFF, f"unknown_{value & 0xFF}")
    flags = []
    if value & 0x01000000:
        flags.append("forward_back")
    if value & 0x02000000:
        flags.append("from_address_bar")
    if value & 0x40000000:
        flags.append("client_redirect")
    if value & 0x80000000:
        flags.append("server_redirect")
    return "+".join([label, *flags])


def history_query(con: sqlite3.Connection, since: int | None, until: int | None, search: str | None) -> tuple[str, list[Any]]:
    visit_cols = columns(con, "visits")
    url_cols = columns(con, "urls")
    select = [
        "v.id AS visit_id",
        "u.id AS url_id",
        "v.visit_time",
        "u.url",
        "u.title",
        "u.visit_count",
        "u.typed_count",
        "v.transition",
    ]
    select.append("v.visit_duration" if "visit_duration" in visit_cols else "0 AS visit_duration")
    select.append("fu.url AS from_url" if "from_visit" in visit_cols else "'' AS from_url")
    select.append("u.last_visit_time" if "last_visit_time" in url_cols else "0 AS last_visit_time")
    select.append("u.hidden" if "hidden" in url_cols else "0 AS hidden")
    select.append("kst.term AS search_term" if table_exists(con, "keyword_search_terms") else "'' AS search_term")

    joins = ["JOIN urls u ON u.id = v.url"]
    if "from_visit" in visit_cols:
        joins.append("LEFT JOIN visits fv ON fv.id = v.from_visit LEFT JOIN urls fu ON fu.id = fv.url")
    if table_exists(con, "keyword_search_terms"):
        joins.append("LEFT JOIN keyword_search_terms kst ON kst.url_id = u.id")

    where = []
    params: list[Any] = []
    if since is not None:
        where.append("v.visit_time >= ?")
        params.append(since)
    if until is not None:
        where.append("v.visit_time < ?")
        params.append(until)
    if search:
        where.append("(u.url LIKE ? OR u.title LIKE ?)")
        needle = f"%{search}%"
        params.extend([needle, needle])

    query = f"SELECT {', '.join(select)} FROM visits v {' '.join(joins)}"
    if where:
        query += " WHERE " + " AND ".join(where)
    query += " ORDER BY v.visit_time DESC, v.id DESC"
    return query, params


def base_row(db_path: Path, timestamp: int | None, activity_source: str) -> dict[str, Any]:
    return {
        "timestamp": from_chrome_time(timestamp),
        "_sort_visit_time": timestamp or 0,
        "activity_source": activity_source,
        "profile": db_path.parent.name,
        "profile_name": profile_name(db_path.parent),
        "source": str(db_path.resolve()),
        "visit_id": "",
        "url_id": "",
        "shortcut_id": "",
        "shortcut_text": "",
        "shortcut_contents": "",
        "shortcut_description": "",
        "shortcut_type": "",
        "document_type": "",
        "number_of_hits": "",
    }


def iter_history_rows(history_path: Path, since: int | None, until: int | None, search: str | None) -> Iterator[dict[str, Any]]:
    with tempfile.TemporaryDirectory(prefix="edge-history-") as tmp:
        copy = copy_sqlite(history_path, Path(tmp))
        uri = f"file:{copy}?mode=ro"
        con = sqlite3.connect(uri, uri=True)
        try:
            con.row_factory = sqlite3.Row
            con.execute("PRAGMA query_only = ON")
            con.execute("PRAGMA temp_store = MEMORY")
            if not table_exists(con, "visits") or not table_exists(con, "urls"):
                return
            query, params = history_query(con, since, until, search)
            for row in con.execute(query, params):
                duration = int(row["visit_duration"] or 0) / 1_000_000
                yield base_row(history_path, row["visit_time"], "history") | {
                    "url": row["url"] or "",
                    "title": row["title"] or "",
                    "visit_count": row["visit_count"] or 0,
                    "typed_count": row["typed_count"] or 0,
                    "transition": row["transition"] or 0,
                    "transition_type": transition_type(row["transition"]),
                    "visit_duration_seconds": duration,
                    "from_url": row["from_url"] or "",
                    "search_term": row["search_term"] or "",
                    "last_visit_time": from_chrome_time(row["last_visit_time"]),
                    "hidden": row["hidden"] or 0,
                    "visit_id": row["visit_id"],
                    "url_id": row["url_id"],
                }
        finally:
            con.close()


def shortcut_query(since: int | None, until: int | None, search: str | None) -> tuple[str, list[Any]]:
    where = ["url IS NOT NULL", "url != ''", "last_access_time > 0"]
    params: list[Any] = []
    if since is not None:
        where.append("last_access_time >= ?")
        params.append(since)
    if until is not None:
        where.append("last_access_time < ?")
        params.append(until)
    if search:
        where.append(
            "(url LIKE ? OR text LIKE ? OR fill_into_edit LIKE ? OR contents LIKE ? OR description LIKE ?)"
        )
        needle = f"%{search}%"
        params.extend([needle] * 5)
    query = f"""
        SELECT id, text, fill_into_edit, url, document_type, contents, description,
               transition, type, keyword, last_access_time, number_of_hits
        FROM omni_box_shortcuts
        WHERE {" AND ".join(where)}
        ORDER BY last_access_time DESC, id DESC
    """
    return query, params


def iter_shortcut_rows(shortcuts_path: Path, since: int | None, until: int | None, search: str | None) -> Iterator[dict[str, Any]]:
    with tempfile.TemporaryDirectory(prefix="edge-shortcuts-") as tmp:
        copy = copy_sqlite(shortcuts_path, Path(tmp))
        uri = f"file:{copy}?mode=ro"
        con = sqlite3.connect(uri, uri=True)
        try:
            con.row_factory = sqlite3.Row
            con.execute("PRAGMA query_only = ON")
            con.execute("PRAGMA temp_store = MEMORY")
            if not table_exists(con, "omni_box_shortcuts"):
                return
            query, params = shortcut_query(since, until, search)
            for row in con.execute(query, params):
                title = row["description"] or row["contents"] or row["text"] or ""
                yield base_row(shortcuts_path, row["last_access_time"], "shortcut") | {
                    "url": row["url"] or "",
                    "title": title,
                    "visit_count": "",
                    "typed_count": "",
                    "transition": row["transition"] or 0,
                    "transition_type": transition_type(row["transition"]),
                    "visit_duration_seconds": "",
                    "from_url": "",
                    "search_term": row["text"] or "",
                    "last_visit_time": from_chrome_time(row["last_access_time"]),
                    "hidden": "",
                    "shortcut_id": row["id"] or "",
                    "shortcut_text": row["text"] or "",
                    "shortcut_contents": row["contents"] or "",
                    "shortcut_description": row["description"] or "",
                    "shortcut_type": row["type"] if row["type"] is not None else "",
                    "document_type": row["document_type"] if row["document_type"] is not None else "",
                    "number_of_hits": row["number_of_hits"] or 0,
                }
        finally:
            con.close()


def iter_activity_rows(path: Path, since: int | None, until: int | None, search: str | None) -> Iterator[dict[str, Any]]:
    if path.name == "History":
        yield from iter_history_rows(path, since, until, search)
    elif path.name == "Shortcuts":
        yield from iter_shortcut_rows(path, since, until, search)


def parse_fields(values: Sequence[str]) -> list[str]:
    fields = [part for value in values for part in value.replace(",", " ").split()]
    return fields or DEFAULT_FIELDS


def write_rows(rows: Iterator[dict[str, Any]], fields: Sequence[str], fmt: str) -> None:
    if fmt == "json":
        first = True
        print("[")
        for row in rows:
            item = {field: row.get(field, "") for field in fields}
            print(("" if first else ",") + json.dumps(item, ensure_ascii=False))
            first = False
        print("]")
        return

    dialect = "excel-tab" if fmt == "tsv" else "excel"
    writer = csv.DictWriter(sys.stdout, fieldnames=list(fields), dialect=dialect, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)


def record_id(row: dict[str, Any]) -> str:
    timestamp = int(row.get("_sort_visit_time") or row.get("sort_visit_time") or 0)
    identity = [row.get("profile", ""), timestamp, row.get("url", "")]
    if row["activity_source"] == "shortcut":
        identity.append(row.get("shortcut_text", ""))
    return hashlib.sha256(json.dumps(identity, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def create_activity_table(con: sqlite3.Connection) -> None:
    con.execute(
        """
        CREATE TABLE activity (
            activity_source TEXT NOT NULL,
            record_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            sort_visit_time INTEGER NOT NULL,
            url TEXT NOT NULL,
            title TEXT,
            visit_count INTEGER,
            typed_count INTEGER,
            number_of_hits INTEGER,
            transition INTEGER,
            transition_type TEXT,
            visit_duration_seconds REAL,
            from_url TEXT,
            search_term TEXT,
            shortcut_text TEXT,
            shortcut_contents TEXT,
            shortcut_description TEXT,
            shortcut_type INTEGER,
            document_type INTEGER,
            last_visit_time TEXT,
            hidden INTEGER,
            profile TEXT NOT NULL,
            profile_name TEXT,
            source TEXT NOT NULL,
            visit_id TEXT,
            url_id TEXT,
            shortcut_id TEXT,
            first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (activity_source, record_id)
        )
        """
    )


def primary_key(con: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in sorted(con.execute(f"PRAGMA table_info({table})"), key=lambda row: row[5]) if row[5]]


def migrate_activity_table(con: sqlite3.Connection) -> None:
    """Replace source-local IDs with stable logical IDs without losing archived rows."""
    con.execute("ALTER TABLE activity RENAME TO activity_legacy")
    create_activity_table(con)
    columns_with_timestamps = [*DB_COLUMNS, "first_seen_at", "updated_at"]
    placeholders = ", ".join(":" + column for column in columns_with_timestamps)
    updates = ", ".join(
        f"{column} = excluded.{column}"
        for column in DB_COLUMNS
        if column not in {"activity_source", "record_id"}
    )
    sql = f"""
        INSERT INTO activity ({", ".join(columns_with_timestamps)})
        VALUES ({placeholders})
        ON CONFLICT(activity_source, record_id) DO UPDATE SET
            {updates},
            first_seen_at = MIN(activity.first_seen_at, excluded.first_seen_at),
            updated_at = MAX(activity.updated_at, excluded.updated_at)
    """
    con.row_factory = sqlite3.Row
    rows = con.execute("SELECT * FROM activity_legacy ORDER BY source LIKE '%/microsoft-edge-cdp/%'")
    for old_row in rows:
        data = dict(old_row)
        data["record_id"] = record_id(data)
        data["source"] = str(Path(data["source"]).expanduser().resolve())
        con.execute(sql, data)
    con.execute("DROP TABLE activity_legacy")


def ensure_db(con: sqlite3.Connection) -> None:
    con.execute("PRAGMA journal_mode = DELETE")
    con.execute("PRAGMA synchronous = NORMAL")
    if not table_exists(con, "activity"):
        create_activity_table(con)
    elif primary_key(con, "activity") != ["activity_source", "record_id"]:
        migrate_activity_table(con)
    con.execute("CREATE INDEX IF NOT EXISTS idx_activity_time ON activity(sort_visit_time DESC)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_activity_url ON activity(url)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_activity_source ON activity(activity_source)")


def normalize_db_row(row: dict[str, Any]) -> dict[str, Any]:
    data = {column: row.get(column, "") for column in DB_COLUMNS}
    data["record_id"] = record_id(row)
    data["sort_visit_time"] = int(row.get("_sort_visit_time") or 0)
    data["timestamp"] = row.get("timestamp") or from_chrome_time(data["sort_visit_time"])
    return data


def sync_database(db: Path, activity_files: Sequence[Path]) -> int:
    db.parent.mkdir(parents=True, exist_ok=True)
    placeholders = ", ".join(":" + column for column in DB_COLUMNS)
    updates = ", ".join(f"{column} = excluded.{column}" for column in DB_COLUMNS if column != "record_id")
    sql = f"""
        INSERT INTO activity ({", ".join(DB_COLUMNS)})
        VALUES ({placeholders})
        ON CONFLICT(activity_source, record_id) DO UPDATE SET
            {updates},
            updated_at = CURRENT_TIMESTAMP
    """
    count = 0
    seen: set[tuple[str, str]] = set()
    with sqlite3.connect(db) as con:
        ensure_db(con)
        with con:
            for row in merged_rows(activity_files, None, None, None):
                data = normalize_db_row(row)
                if not data["record_id"]:
                    continue
                key = (str(data["activity_source"]), str(data["record_id"]))
                if key in seen:
                    continue
                seen.add(key)
                con.execute(sql, data)
                count += 1
    return count


def query_database(
    db: Path,
    since: int | None,
    until: int | None,
    search: str | None,
    limit: int | None,
) -> Iterator[dict[str, Any]]:
    where = []
    params: list[Any] = []
    if since is not None:
        where.append("sort_visit_time >= ?")
        params.append(since)
    if until is not None:
        where.append("sort_visit_time < ?")
        params.append(until)
    if search:
        where.append(
            "(url LIKE ? OR title LIKE ? OR search_term LIKE ? OR shortcut_text LIKE ? OR shortcut_description LIKE ?)"
        )
        needle = f"%{search}%"
        params.extend([needle] * 5)
    sql = "SELECT * FROM activity"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY sort_visit_time DESC, activity_source, record_id"
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)

    with sqlite3.connect(db) as con:
        con.row_factory = sqlite3.Row
        for row in con.execute(sql, params):
            yield dict(row)


def merged_rows(
    activity_files: Sequence[Path],
    since: int | None,
    until: int | None,
    search: str | None,
) -> Iterator[dict[str, Any]]:
    heap: list[tuple[int, int, dict[str, Any], Iterator[dict[str, Any]]]] = []
    for index, path in enumerate(activity_files):
        rows = iter_activity_rows(path, since, until, search)
        try:
            row = next(rows)
        except StopIteration:
            continue
        heapq.heappush(heap, (-int(row["_sort_visit_time"]), index, row, rows))

    while heap:
        _, index, row, rows = heapq.heappop(heap)
        yield row
        try:
            next_row = next(rows)
        except StopIteration:
            continue
        heapq.heappush(heap, (-int(next_row["_sort_visit_time"]), index, next_row, rows))


@app.command(context_settings={"allow_extra_args": False, "ignore_unknown_options": False})
def main(
    root: list[Path] = typer.Option(
        [],
        "--root",
        help="Edge user-data root or a direct History/Shortcuts file. Repeat for multiple roots.",
    ),
    format: str = typer.Option("tsv", "--format", "-f", help="Output format: tsv, csv, json."),
    db: Path = typer.Option(DEFAULT_DB, "--db", help="SQLite database to update and query."),
    no_sync: bool = typer.Option(False, "--no-sync", help="Query --db without reading Edge files first."),
    sync_only: bool = typer.Option(False, "--sync-only", help="Update --db and exit without printing rows."),
    fields: list[str] = typer.Option(
        DEFAULT_FIELDS,
        "--fields",
        help="Fields to export; repeat or separate with commas/spaces.",
    ),
    since: str | None = typer.Option(None, "--since", help="Start time: ISO date/time, 7d, 12h, or 6m."),
    until: str | None = typer.Option(None, "--until", help="End time: ISO date/time, 7d, 12h, or 6m."),
    search: str | None = typer.Option(None, "--search", help="Case-insensitive substring in URL or title."),
    limit: int | None = typer.Option(None, "--limit", "-n", min=1, help="Stop after this many visits."),
    list_profiles: bool = typer.Option(False, "--list-profiles", help="List discovered Edge profile activity files and exit."),
    describe: bool = typer.Option(False, "--describe", help="Print machine-readable CLI metadata and exit."),
) -> None:
    """Sync Edge URL activity into SQLite, then query the database."""
    if describe:
        print(json.dumps(DESCRIBE, indent=2))
        return
    if format not in {"tsv", "csv", "json"}:
        raise typer.BadParameter("--format must be tsv, csv, or json")

    roots = root or default_roots()
    activity_files = [] if no_sync else find_activity_files(roots)
    if list_profiles:
        profiles = sorted({path.parent for path in activity_files})
        for profile in profiles:
            available = ",".join(name for name in ACTIVITY_FILES if (profile / name).exists())
            print(f"{profile.name}\t{profile_name(profile)}\t{available}\t{profile}")
        return
    if not no_sync and not activity_files:
        checked = ", ".join(str(path.expanduser()) for path in roots) or "default Edge roots"
        raise typer.BadParameter(f"No Edge activity files found under {checked}. Pass --root.")
    if not no_sync:
        count = sync_database(db.expanduser(), activity_files)
        print(f"synced {count} source rows into {db.expanduser()}", file=sys.stderr)
        if sync_only:
            return
    if not db.expanduser().exists():
        raise typer.BadParameter(f"Database does not exist: {db.expanduser()}. Run without --no-sync first.")

    start = parse_time(since)
    end = parse_time(until, end=True)
    selected_fields = parse_fields(fields)
    write_rows(query_database(db.expanduser(), start, end, search, limit), selected_fields, format)


if __name__ == "__main__":
    app()
