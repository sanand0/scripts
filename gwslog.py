#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["typer>=0.12"]
# ///
"""Show recent Google Drive changes through the `gws` CLI.

Examples:

  gwslog.py --since 7d --type doc
  gwslog.py --path Innovation --user s.anand@gramener.com --since 30d --format jsonl
  gwslog.py --since 1d --columns "iso user title path link" | xclip -selection clipboard
  GOOGLE_WORKSPACE_CLI_CONFIG_DIR=~/.config/gws-root.node@gmail.com gwslog.py since
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Iterator

import typer

GOOGLE_APPS = "application/vnd.google-apps."
FOLDER_MIME = f"{GOOGLE_APPS}folder"
DEFAULT_COLUMNS = "date,user,name,type,size,link,path"
VALID_COLUMNS = (
    "date",
    "iso",
    "human",
    "user",
    "name",
    "title",
    "type",
    "mime",
    "ext",
    "size",
    "bytes",
    "link",
    "path",
    "id",
    "parent_id",
    "drive",
    "version",
    "created",
    "modified_by_me",
    "owner",
)
OUTPUT_FORMATS = ("text", "json", "tsv", "jsonl", "md")
COLOR_MODES = ("auto", "always", "never")
FIELDS = (
    "nextPageToken,incompleteSearch,files("
    "id,name,mimeType,parents,driveId,createdTime,modifiedTime,modifiedByMeTime,"
    "lastModifyingUser(displayName,emailAddress),owners(displayName,emailAddress),"
    "version,size,quotaBytesUsed,headRevisionId,md5Checksum,sha256Checksum,"
    "originalFilename,fileExtension,webViewLink,trashed)"
)
FOLDER_FIELDS = (
    "nextPageToken,incompleteSearch,files("
    "id,name,mimeType,parents,driveId,createdTime,modifiedTime,modifiedByMeTime,"
    "lastModifyingUser(displayName,emailAddress),owners(displayName,emailAddress),"
    "version,quotaBytesUsed,webViewLink,trashed)"
)
DRIVE_FIELDS = "nextPageToken,drives(id,name)"
TYPE_MIMES = {
    "doc": {f"{GOOGLE_APPS}document", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
    "sheet": {f"{GOOGLE_APPS}spreadsheet", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    "slide": {f"{GOOGLE_APPS}presentation", "application/vnd.openxmlformats-officedocument.presentationml.presentation"},
    "pdf": {"application/pdf"},
    "folder": {FOLDER_MIME},
}

app = typer.Typer(add_completion=False, no_args_is_help=False, help=__doc__)


def fail(message: str) -> None:
    raise typer.BadParameter(message)


def eprint(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def compact_json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def parse_columns(columns: str) -> list[str]:
    selected = [part.strip() for part in re.split(r"[\s,]+", columns) if part.strip()]
    bad = sorted(set(selected) - set(VALID_COLUMNS))
    if bad:
        fail(f"unknown --columns token(s): {', '.join(bad)}. Valid: {', '.join(VALID_COLUMNS)}")
    return selected


def parse_time(value: str | None, *, end: bool = False) -> str | None:
    if not value:
        return None
    now = dt.datetime.now(dt.UTC)
    text = value.strip()
    if match := re.fullmatch(r"(\d+)\s*d(?:ays?)?", text, re.I):
        return (now - dt.timedelta(days=int(match.group(1)))).isoformat(timespec="seconds").replace("+00:00", "Z")
    if match := re.fullmatch(r"(\d+)\s*months?\s*ago", text, re.I):
        return (now - dt.timedelta(days=30 * int(match.group(1)))).isoformat(timespec="seconds").replace("+00:00", "Z")
    if match := re.fullmatch(r"(\d+)\s*hours?\s*ago", text, re.I):
        return (now - dt.timedelta(hours=int(match.group(1)))).isoformat(timespec="seconds").replace("+00:00", "Z")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        suffix = "23:59:59Z" if end else "00:00:00Z"
        return f"{text}T{suffix}"
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        fail(f"invalid date/time: {value!r}. Use ISO, 7d, '2 months ago', or $(date -d '7 days ago' +%F).")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.UTC)
    return parsed.astimezone(dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_dt(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(dt.UTC)


def human_time(value: str) -> str:
    parsed = parse_dt(value)
    return "" if parsed is None else parsed.astimezone().strftime("%Y-%m-%d %H:%M")


def relative_time(value: str) -> str:
    parsed = parse_dt(value)
    if parsed is None:
        return ""
    seconds = int((dt.datetime.now(dt.UTC) - parsed).total_seconds())
    future = seconds < 0
    seconds = abs(seconds)
    units = ((86400, "d"), (3600, "h"), (60, "m"))
    for size, label in units:
        if seconds >= size:
            text = f"{seconds // size}{label}"
            return f"in {text}" if future else f"{text} ago"
    return "now" if seconds < 5 else (f"in {seconds}s" if future else f"{seconds}s ago")


def human_size(value: Any) -> str:
    try:
        size = int(value or 0)
    except (TypeError, ValueError):
        return ""
    if size <= 0:
        return ""
    amount = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if amount < 1024 or unit == "TB":
            return f"{amount:.1f}{unit}" if unit != "B" and amount < 10 else f"{amount:.0f}{unit}"
        amount /= 1024
    return str(size)


def safe_account(account: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.@+-]+", "_", account or "unknown")


def cache_root(account: str) -> Path:
    return Path("~/.config/sanand-scripts/gwslog").expanduser() / safe_account(account)


def config_key(config_dir: str | None) -> str:
    source = config_dir or os.environ.get("GOOGLE_WORKSPACE_CLI_CONFIG_DIR") or "default"
    return hashlib.sha256(str(Path(source).expanduser()).encode()).hexdigest()


def account_cache_path(config_dir: str | None) -> Path:
    return Path("~/.config/sanand-scripts/gwslog/accounts").expanduser() / f"{config_key(config_dir)}.json"


def run_gws(args: list[str], *, config_dir: str | None = None, dry_run: bool = False) -> str:
    cmd = ["gws", *args]
    if dry_run:
        eprint("would run: " + " ".join(cmd))
        return "{}"
    env = os.environ.copy()
    if config_dir:
        env["GOOGLE_WORKSPACE_CLI_CONFIG_DIR"] = config_dir
    result = subprocess.run(cmd, env=env, check=True, stdout=subprocess.PIPE, text=True)
    return result.stdout


def gws_json(args: list[str], *, config_dir: str | None = None, dry_run: bool = False) -> Any:
    return json.loads(run_gws(args, config_dir=config_dir, dry_run=dry_run))


def account_email(
    config_dir: str | None,
    *,
    max_age: int,
    refresh: bool,
    no_cache: bool,
    dry_run: bool = False,
) -> str:
    if dry_run:
        return os.environ.get("GWSLOG_ACCOUNT", "dry-run@example.com")
    path = account_cache_path(config_dir)
    if not no_cache and is_fresh(path, max_age, refresh=refresh):
        cached = load_json(path, {})
        if cached.get("email"):
            return cached["email"]
    data = gws_json(["drive", "about", "get", "--params", '{"fields":"user(emailAddress)"}'], config_dir=config_dir)
    email = data["user"]["emailAddress"]
    if not no_cache:
        write_json(path, {"email": email, "fetched_at": dt.datetime.now(dt.UTC).isoformat(), "config_key": config_key(config_dir)})
    return email


def color_enabled(mode: str, fmt: str) -> bool:
    if mode not in COLOR_MODES:
        fail(f"--color must be one of: {', '.join(COLOR_MODES)}")
    if fmt != "text":
        return False
    if mode == "always":
        return True
    if mode == "never":
        return False
    return sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def is_fresh(path: Path, max_age: int, *, refresh: bool) -> bool:
    return path.exists() and not refresh and dt.datetime.now().timestamp() - path.stat().st_mtime <= max_age


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def load_json(path: Path, default: Any) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def page_objects(text: str, key: str) -> Iterator[dict[str, Any]]:
    for line in text.splitlines() or [text]:
        line = line.strip()
        if not line:
            continue
        data = json.loads(line)
        if data.get("incompleteSearch"):
            eprint("warning: Drive returned incompleteSearch=true; narrow the query with --shared-drive.")
        for item in data.get(key, []):
            yield item


def fetch_pages(
    args: list[str],
    *,
    key: str,
    config_dir: str | None,
    dry_run: bool,
) -> list[dict[str, Any]]:
    out = run_gws(args, config_dir=config_dir, dry_run=dry_run)
    return [] if dry_run else list(page_objects(out, key))


def load_drives(root: Path, config_dir: str | None, max_age: int, refresh: bool, no_cache: bool, dry_run: bool) -> list[dict[str, Any]]:
    path = root / "drives.json"
    if not no_cache and is_fresh(path, max_age, refresh=refresh):
        return load_json(path, [])
    eprint("refreshing drives...")
    drives = fetch_pages(
        ["drive", "drives", "list", "--params", compact_json({"pageSize": 100, "fields": DRIVE_FIELDS}), "--page-all"],
        key="drives",
        config_dir=config_dir,
        dry_run=dry_run,
    )
    if not no_cache and not dry_run:
        write_json(path, drives)
    eprint(f"refreshing drives... {len(drives)} entries")
    return drives


def load_folders(root: Path, config_dir: str | None, max_age: int, refresh: bool, no_cache: bool, dry_run: bool) -> dict[str, dict[str, Any]]:
    path = root / "folders.json"
    if not no_cache and is_fresh(path, max_age, refresh=refresh):
        return load_json(path, {})
    eprint("refreshing folders...")
    params = {
        "pageSize": 1000,
        "q": f"mimeType='{FOLDER_MIME}' and trashed=false",
        "supportsAllDrives": True,
        "includeItemsFromAllDrives": True,
        "fields": FOLDER_FIELDS,
    }
    folders = {
        item["id"]: {
            "id": item["id"],
            "name": item.get("name", ""),
            "parents": item.get("parents", []),
            "driveId": item.get("driveId", ""),
            "webViewLink": item.get("webViewLink", ""),
        }
        for item in fetch_pages(
            ["drive", "files", "list", "--params", compact_json(params), "--page-all", "--page-limit", "1000"],
            key="files",
            config_dir=config_dir,
            dry_run=dry_run,
        )
    }
    if not no_cache and not dry_run:
        write_json(path, folders)
    eprint(f"refreshing folders... {len(folders)} entries")
    return folders


def folder_path(folder_id: str, folders: dict[str, dict[str, Any]], memo: dict[str, str] | None = None) -> str:
    memo = memo if memo is not None else {}
    if not folder_id:
        return ""
    if folder_id in memo:
        return memo[folder_id]
    folder = folders.get(folder_id)
    if not folder:
        return f"/[{folder_id}]"
    parent = (folder.get("parents") or [""])[0]
    base = folder_path(parent, folders, memo).rstrip("/")
    memo[folder_id] = f"{base}/{folder.get('name') or folder_id}"
    return memo[folder_id]


def item_path(item: dict[str, Any], folders: dict[str, dict[str, Any]]) -> str:
    parent = (item.get("parents") or [""])[0]
    base = folder_path(parent, folders).rstrip("/")
    return f"{base}/{item.get('name', '')}" if base else f"/{item.get('name', '')}"


def descendants(folder_id: str, folders: dict[str, dict[str, Any]]) -> set[str]:
    children: dict[str, list[str]] = defaultdict(list)
    for fid, data in folders.items():
        for parent in data.get("parents") or []:
            children[parent].append(fid)
    seen = {folder_id}
    stack = [folder_id]
    while stack:
        current = stack.pop()
        for child in children.get(current, []):
            if child not in seen:
                seen.add(child)
                stack.append(child)
    return seen


def resolve_folder(value: str, folders: dict[str, dict[str, Any]]) -> set[str]:
    if value in folders:
        return descendants(value, folders)
    needle = value.casefold()
    matches = [
        folder_id
        for folder_id, folder in folders.items()
        if needle in folder.get("name", "").casefold() or needle in folder_path(folder_id, folders).casefold()
    ]
    if not matches:
        fail(f"--folder did not match a cached folder id, name, or path fragment: {value}")
    ids: set[str] = set()
    for folder_id in matches:
        ids.update(descendants(folder_id, folders))
    return ids


def resolve_drive(value: str, drives: list[dict[str, Any]]) -> dict[str, Any]:
    if not value:
        return {}
    needle = value.casefold()
    matches = [drive for drive in drives if drive.get("id") == value or needle in drive.get("name", "").casefold()]
    if not matches:
        fail(f"--shared-drive did not match a cached shared drive id/name: {value}")
    if len(matches) > 1:
        fail(f"--shared-drive is ambiguous: {', '.join(drive.get('name', drive.get('id', '')) for drive in matches)}")
    return matches[0]


def query_for(since: str | None, until: str | None, include_trashed: bool, type_filter: str, name: str) -> str:
    parts = [] if include_trashed else ["trashed=false"]
    if since:
        parts.append(f"modifiedTime >= '{since}'")
    if until:
        parts.append(f"modifiedTime <= '{until}'")
    if name:
        escaped_name = name.replace("'", "\\'")
        parts.append(f"name contains '{escaped_name}'")
    if type_filter in TYPE_MIMES:
        mimes = sorted(TYPE_MIMES[type_filter])
        parts.append("(" + " or ".join(f"mimeType='{mime}'" for mime in mimes) + ")")
    if type_filter == "video":
        parts.append("mimeType contains 'video/'")
    if type_filter == "image":
        parts.append("mimeType contains 'image/'")
    if type_filter.startswith("mime:"):
        parts.append(f"mimeType='{type_filter.removeprefix('mime:')}'")
    return " and ".join(parts) if parts else ""


def file_ext(item: dict[str, Any]) -> str:
    if item.get("fileExtension"):
        return str(item["fileExtension"]).lower()
    name = item.get("name", "")
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def short_type(item: dict[str, Any]) -> str:
    mime = item.get("mimeType", "")
    ext = file_ext(item)
    lookup = {
        f"{GOOGLE_APPS}document": "doc",
        f"{GOOGLE_APPS}spreadsheet": "sheet",
        f"{GOOGLE_APPS}presentation": "slide",
        FOLDER_MIME: "folder",
        "application/pdf": "pdf",
    }
    if mime in lookup:
        return lookup[mime]
    if mime.startswith("image/"):
        return "image"
    if mime.startswith("video/"):
        return "video"
    if mime.startswith("audio/"):
        return "audio"
    return ext or mime.rsplit("/", 1)[-1]


def owner(item: dict[str, Any]) -> str:
    return ",".join(user.get("emailAddress") or user.get("displayName", "") for user in item.get("owners", []))


def to_row(item: dict[str, Any], folders: dict[str, dict[str, Any]], drives: dict[str, str]) -> dict[str, Any]:
    parent_id = (item.get("parents") or [""])[0]
    modified = item.get("modifiedTime", "")
    byte_size = item.get("size") or item.get("quotaBytesUsed") or ""
    return {
        "date": relative_time(modified),
        "iso": modified,
        "human": human_time(modified),
        "user": (item.get("lastModifyingUser") or {}).get("emailAddress")
        or (item.get("lastModifyingUser") or {}).get("displayName", ""),
        "name": item.get("name", ""),
        "title": item.get("name", ""),
        "type": short_type(item),
        "mime": item.get("mimeType", ""),
        "ext": file_ext(item),
        "size": human_size(byte_size),
        "bytes": byte_size,
        "link": item.get("webViewLink", ""),
        "path": item_path(item, folders),
        "id": item.get("id", ""),
        "parent_id": parent_id,
        "drive": drives.get(item.get("driveId", ""), item.get("driveId", "")),
        "version": item.get("version", ""),
        "created": item.get("createdTime", ""),
        "modified_by_me": item.get("modifiedByMeTime", ""),
        "owner": owner(item),
    }


def matches_local_filters(
    item: dict[str, Any],
    row: dict[str, Any],
    *,
    folder_ids: set[str],
    type_filter: str,
    path_filter: str,
    user_filter: str,
    owner_filter: str,
    shared_drive: str,
    my_drive: bool,
    mine_only: bool,
) -> bool:
    if folder_ids and not (set(item.get("parents") or []) & folder_ids):
        return False
    if type_filter.startswith("ext:") and file_ext(item) != type_filter.removeprefix("ext:").lower():
        return False
    if path_filter and path_filter.casefold() not in row["path"].casefold():
        return False
    if user_filter and user_filter.casefold() not in row["user"].casefold():
        return False
    if owner_filter and owner_filter.casefold() not in row["owner"].casefold():
        return False
    if shared_drive and not item.get("driveId"):
        return False
    if my_drive and item.get("driveId"):
        return False
    if mine_only and not item.get("modifiedByMeTime"):
        return False
    return True


def cache_key(params: dict[str, Any], local_filters: dict[str, Any]) -> str:
    return hashlib.sha256(compact_json({"params": params, "filters": local_filters}).encode()).hexdigest()


def cached_files(path: Path, key: str, max_age: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    newest_at: dt.datetime | None = None
    newest: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            if record.get("cache_key") == key:
                fetched_at = parse_dt(record.get("fetched_at"))
                if fetched_at and (newest_at is None or fetched_at >= newest_at):
                    newest_at = fetched_at
                    newest = record.get("files", [])
    if newest_at is None:
        return []
    age = (dt.datetime.now(dt.UTC) - newest_at).total_seconds()
    return newest if age <= max_age else []


def fetch_files(
    root: Path,
    params: dict[str, Any],
    key: str,
    *,
    config_dir: str | None,
    max_age: int,
    refresh: bool,
    no_cache: bool,
    dry_run: bool,
    max_rows: int,
) -> Iterable[dict[str, Any]]:
    path = root / "files.jsonl"
    if not no_cache and not refresh:
        cached = cached_files(path, key, max_age)
        if cached:
            eprint(f"using cached files... {len(cached)} entries")
            yield from cached[:max_rows]
            return
    args = ["drive", "files", "list", "--params", compact_json(params), "--page-all", "--page-limit", str(max_rows)]
    if dry_run:
        run_gws(args, config_dir=config_dir, dry_run=True)
        return
    eprint("refreshing files...")
    files = fetch_pages(args, key="files", config_dir=config_dir, dry_run=False)[:max_rows]
    if not no_cache:
        root.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(compact_json({"cache_key": key, "fetched_at": dt.datetime.now(dt.UTC).isoformat(), "params": params, "files": files}) + "\n")
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) > 200:
            path.write_text("\n".join(lines[-200:]) + "\n", encoding="utf-8")
    eprint(f"refreshing files... {len(files)} entries")
    yield from files


def render_row(row: dict[str, Any], columns: list[str], fmt: str) -> str:
    if fmt in {"json", "jsonl"}:
        return compact_json({col: row.get(col, "") for col in columns})
    if fmt == "md":
        return "| " + " | ".join(str(row.get(col, "")).replace("|", "\\|") for col in columns) + " |"
    return "\t".join(str(row.get(col, "")) for col in columns)


def print_rows(rows: Iterable[dict[str, Any]], columns: list[str], fmt: str, color_mode: str = "auto") -> None:
    colors = ["\033[36m", "\033[35m", "\033[32m", "\033[37m", "\033[34m", "\033[33m"]
    color = color_enabled(color_mode, fmt)
    if fmt == "json":
        print("[")
    elif fmt == "md":
        print(render_row(dict(zip(columns, columns)), columns, "md"))
        print("| " + " | ".join("---" for _ in columns) + " |")
    first = True
    for row in rows:
        line = render_row(row, columns, "tsv" if fmt == "text" else fmt)
        if fmt == "json":
            print(("" if first else ",") + line)
        elif color:
            values = line.split("\t")
            print("\t".join(f"{colors[i % len(colors)]}{value}\033[0m" for i, value in enumerate(values)), flush=True)
        else:
            print(line, flush=True)
        first = False
    if fmt == "json":
        print("]")


def schema() -> dict[str, Any]:
    return {
        "name": "gwslog.py",
        "description": __doc__.splitlines()[0],
        "commands": ["log(default)", "tree", "show", "refresh", "since"],
        "valid_columns": VALID_COLUMNS,
        "output_formats": OUTPUT_FORMATS,
        "color_modes": COLOR_MODES,
        "default_columns": DEFAULT_COLUMNS,
        "default_format": "text",
        "output_schema": {column: "string" for column in VALID_COLUMNS},
        "cache": {
            "root": "~/.config/sanand-scripts/gwslog/<account>/",
            "files": ["folders.json", "files.jsonl", "changes.token", "drives.json"],
        },
    }


def common_context(config_dir: str | None, max_age: int, refresh: bool, no_cache: bool, dry_run: bool) -> tuple[Path, dict[str, dict[str, Any]], list[dict[str, Any]], str]:
    account = account_email(config_dir, max_age=max_age, refresh=refresh, no_cache=no_cache, dry_run=dry_run)
    root = cache_root(account)
    folders = load_folders(root, config_dir, max_age, refresh, no_cache, dry_run)
    drives = load_drives(root, config_dir, max_age, refresh, no_cache, dry_run)
    return root, folders, drives, account


@app.callback(invoke_without_command=True)
def log(
    ctx: typer.Context,
    columns: str = typer.Option(DEFAULT_COLUMNS, "--columns", help=f"Columns, comma/space separated. Valid: {', '.join(VALID_COLUMNS)}."),
    since: str = typer.Option("", "--since", help="Show files modified on/after this time. Accepts ISO, 7d, '2 months ago', or $(date -d '7 days ago' +%F)."),
    until: str = typer.Option("", "--until", help="Show files modified on/before this time. Accepts ISO, 7d, or $(date -d '1 day ago' +%F)."),
    folder: str = typer.Option("", "--folder", help="Folder id, folder name substring, or path fragment such as /Innovation/Drafts. Matches descendants."),
    type_: str = typer.Option("", "--type", help="Filter type: doc, sheet, slide, pdf, video, image, folder, ext:opus, or mime:application/vnd.google-apps.spreadsheet."),
    name: str = typer.Option("", "--name", help="Plain substring filter on the file name."),
    path: str = typer.Option("", "--path", help="Plain substring filter on the cached resolved path."),
    user: str = typer.Option("", "--user", help="Plain substring filter on lastModifyingUser email/display name."),
    owner_filter: str = typer.Option("", "--owner", help="Plain substring filter on owner email/display name."),
    shared_drive: str = typer.Option("", "--shared-drive", help="Shared drive name substring or id. Uses corpora=drive when resolved."),
    my_drive: bool = typer.Option(False, "--my-drive", help="Only show files in My Drive."),
    mine_only: bool = typer.Option(False, "--mine-only", help="Only show files this account modified."),
    exclude_trashed: bool = typer.Option(True, "--exclude-trashed/--include-trashed", help="Exclude trashed files by default; use --include-trashed to include them."),
    limit: int = typer.Option(100, "-n", "--limit", "--n", min=1, help="Maximum rows to print."),
    format_: str = typer.Option("text", "--format", help="Output format: text, json, tsv, jsonl, md. Default: text."),
    color: str = typer.Option("auto", "--color", help="Color for text output: auto, always, never. Default: auto."),
    describe: bool = typer.Option(False, "--describe", help="Print command metadata/options/output schema as JSON and exit."),
    max_age: int = typer.Option(3600, "--max-age", min=0, help="Cache freshness in seconds. Default: 3600."),
    no_cache: bool = typer.Option(False, "--no-cache", help="Bypass all caches."),
    refresh: bool = typer.Option(False, "--refresh", help="Force cache rebuild for this query."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print what would be fetched/refreshed without calling the API."),
    config_dir: str = typer.Option("", "--config-dir", help="Override GOOGLE_WORKSPACE_CLI_CONFIG_DIR for gws auth/config."),
) -> None:
    """Show the most recently modified Drive files."""
    if ctx.invoked_subcommand:
        return
    if describe:
        print(json.dumps(schema(), ensure_ascii=False, indent=2, sort_keys=True))
        return
    fmt = format_
    if fmt not in OUTPUT_FORMATS:
        fail(f"--format must be one of: {', '.join(OUTPUT_FORMATS)}")
    if color not in COLOR_MODES:
        fail(f"--color must be one of: {', '.join(COLOR_MODES)}")
    selected = parse_columns(columns)
    config = config_dir or None
    root, folders, drive_list, _account = common_context(config, max_age, refresh, no_cache, dry_run)
    drive = resolve_drive(shared_drive, drive_list) if shared_drive else {}
    folder_ids = resolve_folder(folder, folders) if folder else set()
    drive_names = {drive.get("id", ""): drive.get("name", "") for drive in drive_list}
    parsed_since = parse_time(since)
    parsed_until = parse_time(until, end=True)
    type_filter = type_.strip().lower()
    if type_filter and type_filter not in TYPE_MIMES and type_filter not in {"video", "image"} and not type_filter.startswith(("ext:", "mime:")):
        fail("unknown --type. Use doc, sheet, slide, pdf, video, image, folder, ext:..., or mime:...")
    params: dict[str, Any] = {
        "pageSize": min(max(limit, 100), 1000),
        "orderBy": "modifiedTime desc",
        "q": query_for(parsed_since, parsed_until, not exclude_trashed, type_filter, name),
        "supportsAllDrives": True,
        "includeItemsFromAllDrives": True,
        "fields": FIELDS,
    }
    if drive:
        params.update({"corpora": "drive", "driveId": drive["id"]})
    elif my_drive:
        params["corpora"] = "user"
    local_filters = {
        "folder": sorted(folder_ids),
        "type": type_filter,
        "path": path,
        "user": user,
        "owner": owner_filter,
        "shared_drive": shared_drive,
        "my_drive": my_drive,
        "mine_only": mine_only,
    }
    key = cache_key(params, local_filters)
    files = fetch_files(root, params, key, config_dir=config, max_age=max_age, refresh=refresh, no_cache=no_cache, dry_run=dry_run, max_rows=max(limit * 3, limit))

    def rows() -> Iterator[dict[str, Any]]:
        emitted = 0
        for item in files:
            row = to_row(item, folders, drive_names)
            if not matches_local_filters(
                item,
                row,
                folder_ids=folder_ids,
                type_filter=type_filter,
                path_filter=path,
                user_filter=user,
                owner_filter=owner_filter,
                shared_drive=shared_drive,
                my_drive=my_drive,
                mine_only=mine_only,
            ):
                continue
            yield row
            emitted += 1
            if emitted >= limit:
                return

    print_rows(rows(), selected, fmt, color)


@app.command()
def tree(
    folder: str = typer.Option("", "--folder", help="Optional cached folder id/name/path fragment to print from."),
    format_: str = typer.Option("text", "--format", help="text or json."),
    max_age: int = typer.Option(3600, "--max-age", min=0, help="Cache freshness in seconds."),
    no_cache: bool = typer.Option(False, "--no-cache", help="Bypass caches."),
    refresh: bool = typer.Option(False, "--refresh", help="Force folder/drive cache refresh."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print what would be fetched/refreshed without calling the API."),
    config_dir: str = typer.Option("", "--config-dir", help="Override GOOGLE_WORKSPACE_CLI_CONFIG_DIR for gws auth/config."),
) -> None:
    """Print the cached folder tree as indented text or JSON."""
    _root, folders, _drives, _account = common_context(config_dir or None, max_age, refresh, no_cache, dry_run)
    roots = resolve_folder(folder, folders) if folder else {fid for fid, data in folders.items() if not data.get("parents")}
    if format_ == "json":
        print(json.dumps({fid: {**folders[fid], "path": folder_path(fid, folders)} for fid in sorted(roots)}, ensure_ascii=False, indent=2, sort_keys=True))
        return
    if format_ != "text":
        fail("--format for tree must be text or json")
    children: dict[str, list[str]] = defaultdict(list)
    for fid, data in folders.items():
        for parent in data.get("parents") or [""]:
            children[parent].append(fid)

    def walk(fid: str, depth: int) -> None:
        data = folders[fid]
        print(f"{'  ' * depth}{data.get('name', fid)}\t{fid}")
        for child in sorted(children.get(fid, []), key=lambda x: folders[x].get("name", "").casefold()):
            walk(child, depth + 1)

    for fid in sorted(roots, key=lambda x: folder_path(x, folders).casefold()):
        walk(fid, 0)


@app.command()
def show(
    file_id: str = typer.Argument(..., help="Drive file id."),
    format_: str = typer.Option("text", "--format", help="text or json. Default: text."),
    max_age: int = typer.Option(3600, "--max-age", min=0, help="Cache freshness in seconds."),
    no_cache: bool = typer.Option(False, "--no-cache", help="Bypass caches."),
    refresh: bool = typer.Option(False, "--refresh", help="Force folder/drive cache refresh."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print what would be fetched/refreshed without calling the API."),
    config_dir: str = typer.Option("", "--config-dir", help="Override GOOGLE_WORKSPACE_CLI_CONFIG_DIR for gws auth/config."),
) -> None:
    """Print full metadata for one file, with parents resolved to a path."""
    root, folders, drive_list, _account = common_context(config_dir or None, max_age, refresh, no_cache, dry_run)
    del root
    params = {"fileId": file_id, "supportsAllDrives": True, "fields": FIELDS.removeprefix("nextPageToken,incompleteSearch,files(").removesuffix(")")}
    item = {} if dry_run else gws_json(["drive", "files", "get", "--params", compact_json(params)], config_dir=config_dir or None)
    drive_names = {drive.get("id", ""): drive.get("name", "") for drive in drive_list}
    enriched = {**item, "path": item_path(item, folders) if item else "", "drive": drive_names.get(item.get("driveId", ""), item.get("driveId", "")) if item else ""}
    if format_ == "json":
        print(json.dumps(enriched, ensure_ascii=False, indent=2, sort_keys=True))
    elif format_ == "text":
        for key, value in enriched.items():
            print(f"{key}\t{compact_json(value) if isinstance(value, (dict, list)) else value}")
    else:
        fail("--format for show must be json or text")


@app.command()
def refresh(
    max_age: int = typer.Option(0, "--max-age", min=0, help="Ignored; present for CLI symmetry."),
    no_cache: bool = typer.Option(False, "--no-cache", help="Bypass caches after fetching."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print what would be fetched/refreshed without calling the API."),
    config_dir: str = typer.Option("", "--config-dir", help="Override GOOGLE_WORKSPACE_CLI_CONFIG_DIR for gws auth/config."),
) -> None:
    """Refresh folder, shared-drive, and recent-file caches without printing the log."""
    root, folders, drives, _account = common_context(config_dir or None, max_age, True, no_cache, dry_run)
    params = {"pageSize": 1000, "orderBy": "modifiedTime desc", "q": "trashed=false", "supportsAllDrives": True, "includeItemsFromAllDrives": True, "fields": FIELDS}
    key = cache_key(params, {})
    list(fetch_files(root, params, key, config_dir=config_dir or None, max_age=0, refresh=True, no_cache=no_cache, dry_run=dry_run, max_rows=1000))
    eprint(f"cache ready: {len(folders)} folders, {len(drives)} shared drives")


@app.command()
def since(
    limit: int = typer.Option(100, "-n", "--limit", "--n", min=1, help="Maximum changes to fetch."),
    format_: str = typer.Option("text", "--format", help="Output format: text, json, tsv, jsonl, md. Default: text."),
    color: str = typer.Option("auto", "--color", help="Color for text output: auto, always, never. Default: auto."),
    max_age: int = typer.Option(3600, "--max-age", min=0, help="Cache freshness in seconds."),
    no_cache: bool = typer.Option(False, "--no-cache", help="Bypass folder/drive caches."),
    refresh: bool = typer.Option(False, "--refresh", help="Force folder/drive cache refresh."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print what would be fetched/refreshed without calling the API."),
    config_dir: str = typer.Option("", "--config-dir", help="Override GOOGLE_WORKSPACE_CLI_CONFIG_DIR for gws auth/config."),
) -> None:
    """Show and advance the incremental Drive changes feed."""
    fmt = format_
    if fmt not in OUTPUT_FORMATS:
        fail(f"--format must be one of: {', '.join(OUTPUT_FORMATS)}")
    if color not in COLOR_MODES:
        fail(f"--color must be one of: {', '.join(COLOR_MODES)}")
    root, folders, drives, _account = common_context(config_dir or None, max_age, refresh, no_cache, dry_run)
    token_path = root / "changes.token"
    if token_path.exists():
        token = token_path.read_text(encoding="utf-8").strip()
    else:
        data = gws_json(["drive", "changes", "getStartPageToken", "--params", '{"supportsAllDrives":true}'], config_dir=config_dir or None, dry_run=dry_run)
        token = data.get("startPageToken", "")
        if not dry_run:
            token_path.parent.mkdir(parents=True, exist_ok=True)
            token_path.write_text(token, encoding="utf-8")
        eprint("initialized changes.token; run again to read incremental changes")
        return
    params = {
        "pageToken": token,
        "pageSize": min(max(limit, 100), 1000),
        "supportsAllDrives": True,
        "includeItemsFromAllDrives": True,
        "includeRemoved": True,
        "fields": "nextPageToken,newStartPageToken,changes(time,removed,fileId,file(id,name,mimeType,parents,driveId,createdTime,modifiedTime,modifiedByMeTime,lastModifyingUser(displayName,emailAddress),owners(displayName,emailAddress),version,size,quotaBytesUsed,webViewLink,trashed))",
    }
    out = run_gws(["drive", "changes", "list", "--params", compact_json(params), "--page-all", "--page-limit", str(limit)], config_dir=config_dir or None, dry_run=dry_run)
    drive_names = {drive.get("id", ""): drive.get("name", "") for drive in drives}
    rows: list[dict[str, Any]] = []
    new_token = ""
    if not dry_run:
        for line in out.splitlines() or [out]:
            data = json.loads(line)
            new_token = data.get("newStartPageToken") or new_token
            for change in data.get("changes", []):
                item = change.get("file") or {"id": change.get("fileId", "")}
                row = to_row(item, folders, drive_names)
                row.update({"change_time": change.get("time", ""), "removed": change.get("removed", False), "id": change.get("fileId") or row["id"]})
                rows.append(row)
        if new_token:
            token_path.write_text(new_token, encoding="utf-8")
    print_rows(rows[:limit], ["change_time", "user", "name", "type", "path", "link", "id"], fmt, color)


if __name__ == "__main__":
    app()
