#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["typer>=0.12"]
# ///
"""Back up Google Chat, Calendar, and Gmail through the `gws` CLI.

Examples:
  backupgoogle.py --days 3
  backupgoogle.py --since 2026-05-11 --until 2026-05-15 --sources chat,mail
  backupgoogle.py --days 7 --format jsonl | jaq .
  GOOGLE_WORKSPACE_CLI_CONFIG_DIR=~/.config/gws-root.node@gmail.com backupgoogle.py --days 3
"""

from __future__ import annotations

import base64
import datetime as dt
import html
import json
import os
import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import typer

app = typer.Typer(add_completion=False, help=__doc__)

OUT_ROOT = Path("~/Documents/data").expanduser()
SOURCES = {"chat", "calendar", "mail"}
SPACE_CACHE_HOURS = 6
GWS_NOISE_PREFIXES = ("Using keyring backend:",)
REPLY_MARKERS = re.compile(
    r"\n\s*(?:On [\s\S]{0,1000}?wrote:\s*|From:\s.+\nSent:\s.+\n|-----Original Message-----|_{20,}|-{20,})",
    re.I | re.S,
)
NOISE_RE = re.compile(r"[ \t\r\f\v]+")


class TextHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"br", "p", "div", "tr", "li"}:
            self.parts.append("\n")
        if tag == "img":
            alt = dict(attrs).get("alt")
            if alt:
                self.parts.append(f" [image: {alt}] ")

    def text(self) -> str:
        return clean_text(" ".join(self.parts))


def eprint(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def useful_stderr(text: str) -> str:
    lines = [line for line in text.splitlines() if not line.startswith(GWS_NOISE_PREFIXES)]
    return "\n".join(lines)


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def clean_text(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = NOISE_RE.sub(" ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()


def parse_time(value: str) -> dt.datetime:
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        value += "T00:00:00"
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.datetime.now().astimezone().tzinfo)
    return parsed.astimezone(dt.UTC)


def time_range(since: str, until: str, days: int) -> tuple[dt.datetime, dt.datetime]:
    end = parse_time(until) if until else dt.datetime.now(dt.UTC)
    start = parse_time(since) if since else end - dt.timedelta(days=days)
    if start >= end:
        raise typer.BadParameter("--since must be before --until")
    return start, end


def safe_account(email: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.@+-]+", "_", email or "unknown")


def run_gws(args: list[str], *, config_dir: str = "") -> str:
    env = os.environ.copy()
    if config_dir:
        env["GOOGLE_WORKSPACE_CLI_CONFIG_DIR"] = config_dir
    result = subprocess.run(
        ["gws", *args],
        env=env,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if stderr := useful_stderr(result.stderr):
        eprint(stderr)
    if result.returncode:
        raise subprocess.CalledProcessError(result.returncode, ["gws", *args], result.stdout, result.stderr)
    return result.stdout


def gws_json(args: list[str], *, config_dir: str = "") -> Any:
    text = run_gws([*args, "--format", "json"], config_dir=config_dir).strip()
    try:
        return json.loads(text or "{}")
    except json.JSONDecodeError:
        return [json.loads(line) for line in text.splitlines() if line.strip()]


def gws_items(path: list[str], params: dict[str, Any], key: str, *, config_dir: str = "", page_limit: int = 50) -> list[dict[str, Any]]:
    data = gws_json([*path, "--params", compact_json(params), "--page-all", "--page-limit", str(page_limit)], config_dir=config_dir)
    pages = data if isinstance(data, list) else [data]
    items: list[dict[str, Any]] = []
    for page in pages:
        items.extend(page.get(key) or [])
    return items


def account_email(config_dir: str) -> str:
    data = gws_json(["drive", "about", "get", "--params", '{"fields":"user(emailAddress)"}'], config_dir=config_dir)
    return data["user"]["emailAddress"]


def headers(message: dict[str, Any]) -> dict[str, str]:
    raw = (message.get("payload") or {}).get("headers") or []
    return {item.get("name", "").lower(): item.get("value", "") for item in raw}


def decode_data(value: str) -> str:
    if not value:
        return ""
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded).decode("utf-8", "replace")


def walk_parts(part: dict[str, Any]) -> list[dict[str, Any]]:
    children = part.get("parts") or []
    return [part, *[child for item in children for child in walk_parts(item)]]


def html_to_text(value: str) -> str:
    parser = TextHTMLParser()
    parser.feed(value)
    return parser.text()


def email_body(message: dict[str, Any]) -> str:
    plain: list[str] = []
    rendered: list[str] = []
    for part in walk_parts(message.get("payload") or {}):
        data = ((part.get("body") or {}).get("data")) or ""
        if not data:
            continue
        mime = part.get("mimeType", "")
        if mime == "text/plain":
            plain.append(decode_data(data))
        elif mime == "text/html":
            rendered.append(html_to_text(decode_data(data)))
    body = clean_text("\n".join(plain or rendered))
    body = REPLY_MARKERS.split(body, maxsplit=1)[0]
    kept = []
    lines = body.splitlines()
    for pos, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(">"):
            continue
        if stripped.lower().startswith("on ") and "wrote:" in "\n".join(lines[pos : pos + 8]).lower():
            break
        kept.append(line)
    body = "\n".join(kept)
    return clean_text(body)


def attachments(message: dict[str, Any]) -> list[dict[str, Any]]:
    files = []
    for part in walk_parts(message.get("payload") or {}):
        if not part.get("filename"):
            continue
        body = part.get("body") or {}
        files.append(
            {
                "filename": part.get("filename"),
                "mime_type": part.get("mimeType"),
                "size": body.get("size"),
                "part_id": part.get("partId"),
                "attachment_id": body.get("attachmentId"),
            }
        )
    return files


def add_present(row: dict[str, Any], **items: Any) -> dict[str, Any]:
    for key, value in items.items():
        if value not in ("", None, [], {}, 0):
            row[key] = value
    return row


def normalize_mail(message: dict[str, Any], account: str) -> dict[str, Any]:
    hdr = headers(message)
    when = dt.datetime.fromtimestamp(int(message["internalDate"]) / 1000, dt.UTC).isoformat()
    row = {
        "time": when,
        "from": hdr.get("from", ""),
        "subject": hdr.get("subject", ""),
        "snippet": clean_text(message.get("snippet")),
        "body": email_body(message),
        "to": hdr.get("to", ""),
        "size": message.get("sizeEstimate"),
        "id": message.get("id"),
    }
    return add_present(row, cc=hdr.get("cc", ""), bcc=hdr.get("bcc", ""), attachments=attachments(message))


def collect_mail(start: dt.datetime, end: dt.datetime, account: str, *, config_dir: str) -> list[dict[str, Any]]:
    after = (start - dt.timedelta(days=1)).strftime("%Y/%-m/%-d")
    before = (end + dt.timedelta(days=1)).strftime("%Y/%-m/%-d")
    ids = gws_items(
        ["gmail", "users", "messages", "list"],
        {"userId": "me", "q": f"after:{after} before:{before}", "maxResults": 500, "fields": "messages(id,threadId),nextPageToken"},
        "messages",
        config_dir=config_dir,
    )
    rows = []
    for pos, row in enumerate(ids, 1):
        msg_id = row.get("id")
        if not msg_id:
            continue
        if pos % 50 == 0:
            eprint(f"mail: fetched {pos}/{len(ids)}")
        msg = gws_json(["gmail", "users", "messages", "get", "--params", compact_json({"userId": "me", "id": msg_id, "format": "full"})], config_dir=config_dir)
        when = dt.datetime.fromtimestamp(int(msg["internalDate"]) / 1000, dt.UTC)
        if start <= when < end:
            rows.append(normalize_mail(msg, account))
    return rows


def event_time(value: dict[str, Any]) -> str:
    if value.get("dateTime"):
        return value["dateTime"]
    return value.get("date", "")


def normalize_calendar(event: dict[str, Any], account: str) -> dict[str, Any]:
    attendees = event.get("attendees") or []
    row = {
        "time": event_time(event.get("start") or {}),
        "title": event.get("summary", ""),
        "attendees": [item.get("email") for item in attendees if item.get("email")],
        "body": clean_text(event.get("description")),
        "end_time": event_time(event.get("end") or {}),
        "id": event.get("id"),
    }
    return add_present(
        row,
        location=clean_text(event.get("location")),
        organizer=(event.get("organizer") or {}).get("email", ""),
        hangout_link=event.get("hangoutLink", ""),
    )


def collect_calendar(start: dt.datetime, end: dt.datetime, account: str, *, config_dir: str) -> list[dict[str, Any]]:
    rows = gws_items(
        ["calendar", "events", "list"],
        {
            "calendarId": "primary",
            "timeMin": start.isoformat().replace("+00:00", "Z"),
            "timeMax": end.isoformat().replace("+00:00", "Z"),
            "singleEvents": True,
            "orderBy": "startTime",
            "maxResults": 2500,
        },
        "items",
        config_dir=config_dir,
    )
    return [normalize_calendar(row, account) for row in rows]


def space_path(account_dir: Path) -> Path:
    return account_dir / "chat-spaces.jsonl"


def user_path(account_dir: Path) -> Path:
    return account_dir / "chat-users.jsonl"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(compact_json(row) + "\n" for row in rows)
    path.write_text(text)


def sort_time(row: dict[str, Any], key: str) -> float:
    value = row.get(key) or row.get("time") or row.get("lastActiveTime") or ""
    try:
        return parse_time(str(value)).timestamp()
    except ValueError:
        return 0


def update_jsonl(path: Path, rows: list[dict[str, Any]], *, sort_key: str = "time") -> int:
    existing = {row["id"]: row for row in load_jsonl(path) if row.get("id")}
    for row in rows:
        existing[row["id"]] = row
    write_jsonl(path, sorted(existing.values(), key=lambda row: sort_time(row, sort_key), reverse=True))
    return len(rows)


def normalize_space(space: dict[str, Any]) -> dict[str, Any]:
    return add_present(
        {
            "lastActiveTime": space.get("lastActiveTime") or space.get("createTime", ""),
            "displayName": space.get("displayName", ""),
            "name": space.get("name"),
        },
        space_type=space.get("spaceType") or space.get("type", ""),
        space_uri=space.get("spaceUri", ""),
    )


def collect_spaces(account_dir: Path, start: dt.datetime, *, config_dir: str, refresh: bool) -> list[dict[str, Any]]:
    path = space_path(account_dir)
    if not refresh and path.exists() and path.stat().st_mtime > (dt.datetime.now().timestamp() - SPACE_CACHE_HOURS * 3600):
        spaces = load_jsonl(path)
    else:
        spaces = [normalize_space(space) for space in gws_items(["chat", "spaces", "list"], {"pageSize": 1000}, "spaces", config_dir=config_dir)]
        write_jsonl(path, sorted(spaces, key=lambda row: sort_time(row, "lastActiveTime"), reverse=True))
    return [space for space in spaces if parse_time(space.get("lastActiveTime") or space.get("createTime") or "1970-01-01T00:00:00Z") >= start]


def normalize_reactions(reactions: list[dict[str, Any]]) -> list[str]:
    labels = []
    for item in reactions or []:
        emoji = item.get("emoji") or {}
        label = emoji.get("unicode") or emoji.get("customEmoji", {}).get("uid") or ""
        if label:
            labels.append(f"{label}:{item.get('reactionCount', 0)}")
    return labels


def load_chat_users(account_dir: Path) -> dict[str, str]:
    return {row["id"]: row.get("name", row["id"]) for row in load_jsonl(user_path(account_dir)) if row.get("id")}


def write_chat_users(account_dir: Path, users: dict[str, str]) -> None:
    rows = [{"id": user_id, "name": name} for user_id, name in sorted(users.items(), key=lambda item: item[1].lower())]
    write_jsonl(user_path(account_dir), rows)


def sender_name(sender: dict[str, Any], users: dict[str, str]) -> str:
    user_id = sender.get("name", "")
    name = clean_text(sender.get("displayName")) or users.get(user_id) or user_id
    if user_id and user_id not in users:
        users[user_id] = name
    return name


def normalize_chat(message: dict[str, Any], space: dict[str, Any], users: dict[str, str]) -> dict[str, Any]:
    cards = message.get("cardsV2") or []
    attachments_meta = []
    for item in message.get("attachment") or []:
        data_ref = item.get("attachmentDataRef") or {}
        attachments_meta.append(
            {
                "name": item.get("name"),
                "filename": item.get("contentName"),
                "mime_type": item.get("contentType"),
                "resource_name": data_ref.get("resourceName"),
            }
        )
    sender = message.get("sender") or {}
    row = {
        "time": message.get("createTime", ""),
        "sender_name": sender_name(sender, users),
        "body": clean_text(message.get("text") or message.get("argumentText")),
        "space_name": space.get("displayName", ""),
        "id": message.get("name"),
    }
    return add_present(
        row,
        reactions=normalize_reactions(message.get("emojiReactionSummaries") or []),
        attachments=attachments_meta,
        cards=len(cards),
    )


def collect_chat(start: dt.datetime, end: dt.datetime, account: str, account_dir: Path, *, config_dir: str, refresh_spaces: bool) -> list[dict[str, Any]]:
    rows = []
    users = load_chat_users(account_dir)
    spaces = collect_spaces(account_dir, start, config_dir=config_dir, refresh=refresh_spaces)
    eprint(f"chat: scanning {len(spaces)} recently active spaces")
    filter_expr = f'create_time > "{start.isoformat().replace("+00:00", "Z")}" AND create_time < "{end.isoformat().replace("+00:00", "Z")}"'
    for pos, space in enumerate(spaces, 1):
        if pos % 25 == 0:
            eprint(f"chat: scanned {pos}/{len(spaces)} spaces")
        try:
            messages = gws_items(
                ["chat", "spaces", "messages", "list"],
                {"parent": space["name"], "pageSize": 1000, "orderBy": "create_time DESC", "filter": filter_expr},
                "messages",
                config_dir=config_dir,
            )
        except subprocess.CalledProcessError as exc:
            eprint(f"chat: skipped {space.get('name')} ({exc})")
            continue
        rows.extend(normalize_chat(msg, space, users) for msg in messages)
    write_chat_users(account_dir, users)
    return rows


def describe() -> dict[str, Any]:
    return {
        "name": "backupgoogle.py",
        "outputs": {
            "chat": "~/Documents/data/{email}/chat.jsonl",
            "calendar": "~/Documents/data/{email}/calendar.jsonl",
            "mail": "~/Documents/data/{email}/mail.jsonl",
            "chat_spaces": "~/Documents/data/{email}/chat-spaces.jsonl",
            "chat_users": "~/Documents/data/{email}/chat-users.jsonl",
        },
        "common_fields": ["time", "id"],
        "filters": ["--days", "--since", "--until", "--sources"],
        "examples": ["backupgoogle.py --days 3", "backupgoogle.py --since 2026-05-11 --sources chat,mail"],
    }


@app.command()
def main(
    days: int = typer.Option(3, "--days", "-d", min=1, help="Back up this many days ending now, unless --since is set."),
    since: str = typer.Option("", "--since", help="Inclusive start date/time. Accepts YYYY-MM-DD or ISO datetime."),
    until: str = typer.Option("", "--until", help="Exclusive end date/time. Defaults to now."),
    sources: str = typer.Option("chat,calendar,mail", "--sources", help="Comma-separated: chat,calendar,mail."),
    config_dir: str = typer.Option("", "--config-dir", help="Override GOOGLE_WORKSPACE_CLI_CONFIG_DIR for gws."),
    out_root: Path = typer.Option(OUT_ROOT, "--out-root", help="Backup root directory."),
    refresh_spaces: bool = typer.Option(False, "--refresh-spaces", help="Refresh chat space cache."),
    format: str = typer.Option("text", "--format", help="text or jsonl summary."),
    describe_schema: bool = typer.Option(False, "--describe", help="Print machine-readable CLI/schema description and exit."),
) -> None:
    if describe_schema:
        print(compact_json(describe()))
        return
    selected = {item.strip() for item in sources.split(",") if item.strip()}
    if unknown := selected - SOURCES:
        raise typer.BadParameter(f"unknown source(s): {', '.join(sorted(unknown))}")
    if format not in {"text", "jsonl"}:
        raise typer.BadParameter("--format must be text or jsonl")

    start, end = time_range(since, until, days)
    account = account_email(config_dir)
    account_dir = out_root.expanduser() / safe_account(account)
    eprint(f"account: {account}")
    eprint(f"range: {start.isoformat()} to {end.isoformat()}")

    summaries = []
    collectors = {
        "calendar": lambda: collect_calendar(start, end, account, config_dir=config_dir),
        "mail": lambda: collect_mail(start, end, account, config_dir=config_dir),
        "chat": lambda: collect_chat(start, end, account, account_dir, config_dir=config_dir, refresh_spaces=refresh_spaces),
    }
    for source in ["calendar", "mail", "chat"]:
        if source not in selected:
            continue
        eprint(f"{source}: collecting")
        rows = collectors[source]()
        count = update_jsonl(account_dir / f"{source}.jsonl", rows)
        summary = {"source": source, "account": account, "rows_updated": count, "path": str(account_dir / f"{source}.jsonl")}
        summaries.append(summary)
        print(compact_json(summary) if format == "jsonl" else f"{source}: updated {count} rows -> {summary['path']}")


if __name__ == "__main__":
    app()
