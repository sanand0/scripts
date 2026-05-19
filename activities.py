#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["typer>=0.12"]
# ///
"""Generate daily activity TSV reports.

Examples:
  activities.py --date 2026-05-14 --dry-run
  activities.py --days 3 --limit-per-source 25
  activities.py --sources calendar,email,commit --dry-run | moor
  activities.py --describe | jaq .
"""

from __future__ import annotations

import csv
import datetime as dt
import html
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse
from typing import Any, Callable

import typer

app = typer.Typer(add_completion=False, no_args_is_help=False, help=__doc__)

ROOT = Path(__file__).resolve().parent
CODE_ROOT = Path("~/code").expanduser()
OUT_ROOT = Path("~/Documents/activities").expanduser()
BROWSER_DB = Path("~/Documents/data/browsing-history.db").expanduser()
CODEX_SESSIONS = Path("~/.codex/sessions").expanduser()
NOISE_SPACE_RE = re.compile(r"\s+")
HTML_TAG_RE = re.compile(r"<[^>]+>")
COMMIT_TIMESTAMP_RE = re.compile(r"^(?:[A-Z][a-z]{2} \d{1,2}, \d{4}, \d{1,2}:\d{2} [AP]M|\d{4}-\d{2}-\d{2})")
SUBJECT_PREFIX_RE = re.compile(r"^((re|fw|fwd):\s*)+", re.I)
SELF_EMAILS = {"s.anand@gramener.com", "root.node@gmail.com"}
DEFAULT_SOURCES = "calendar,email,commit,github-commit,browser,code-prompt,shell"
BOILERPLATE_MARKERS = (
    "________________________________________________________________________________",
    "microsoft teams meeting",
    "join this meeting",
    "join with google meet",
    "google meet",
    "meeting link",
    "zoom details",
    "join zoom meeting",
    "meet.google.com",
    "teams.microsoft.com",
    "zoom.us/",
    "meetings are open",
)
NOISY_PROMPT_PREFIXES = (
    "the following is the codex agent history whose request action you are assessing",
)
GENERIC_AI_TITLES = {"chatgpt", "claude", "codex"}
FISH_HISTORY_BURST_MINUTES = 15
SHELL_COMMAND_MAX_CHARS = 220
SHELL_NOISE_RE = re.compile(
    r"^(?:"
    r"cd\b|z\b|l\b|ls\b|ll\b|la\b|pwd\b|clear\b|history\b|exit\b|jobs\b|fg\b|bg\b|"
    r"which\b|type\b|command -v\b|abbr\b|alias\b|set -[glUx]\b|"
    r"moor\b|less\b|more\b|head\b|tail\b|cat\b"
    r")"
)
SHELL_SENSITIVE_RE = re.compile(
    r"(\b(secrets?|passwords?|passwd|tokens?|api[_-]?keys?|oauth|authorization|bearer|client[_-]?secret)\b|(?:^|[\s/])\.env\b)",
    re.I,
)
SHELL_SIGNAL_RE = re.compile(
    r"^(?:"
    r"code\b|codex\b|claude\b|llm\b|agent\b|"
    r"git (?:commit|push|pull|merge|rebase|tag|switch|checkout|status|diff|show)\b|"
    r"gh\b|gws\b|bq\b|gcloud\b|curl\b|w3m\b|lynx\b|"
    r"uv(?:x| run)?\b|npm\b|npx\b|just\b|make\b|pytest\b|ruff\b|dprint\b|"
    r".*\.py\b|"
    r"duckdb\b|sqlite3\b|qsv\b|csvq\b|jaq\b|yq\b|jq\b|ug\b|rg\b|rga\b|fd\b|sg\b|"
    r"ffmpeg\b|melt\b|magick\b|pandoc\b|pdfcpu\b|qpdf\b|pdftoppm\b|pdfplumber\b|yt-dlp\b|"
    r"rclone\b|rsync\b|scp\b|ssh\b|7zz\b|tar\b|zip\b|unzip\b"
    r")"
)
LEISURE_DOMAINS = {
    "netflix.com",
    "primevideo.com",
    "wikipedia.org",
    "en.wikipedia.org",
    "twitter.com",
    "x.com",
}
LEISURE_QUERY_RE = re.compile(
    r"\b(actor|actress|movie|film|netflix|prime video|diplomat|keri russell|sriram raghavan|poornima|honey i blew|star wars)\b",
    re.I,
)
CODE_PROMPT_CACHE: tuple[dt.datetime, dt.datetime, list[Activity]] | None = None
EMAIL_CACHE: tuple[dt.datetime, dt.datetime, list[Activity]] | None = None
SHELL_CACHE: tuple[dt.datetime, dt.datetime, list[Activity]] | None = None
REPORT_NAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.tsv$")
GWS_NOISE_PREFIXES = ("Using keyring backend:",)


@dataclass(frozen=True)
class Activity:
    when: dt.datetime
    type: str
    activity: str
    source: str
    source_id: str


@dataclass(frozen=True)
class Context:
    day: dt.date
    start: dt.datetime
    end: dt.datetime
    limit_per_source: int
    browser_synced: bool


Collector = Callable[[Context], list[Activity]]


def eprint(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def useful_stderr(text: str) -> str:
    lines = [line for line in text.splitlines() if not line.startswith(GWS_NOISE_PREFIXES)]
    return "\n".join(lines)


def local_now() -> dt.datetime:
    return dt.datetime.now().astimezone()


def day_bounds(day: dt.date) -> tuple[dt.datetime, dt.datetime]:
    tz = local_now().tzinfo
    if tz is None:
        raise typer.BadParameter("System local timezone is unavailable.")
    start = dt.datetime.combine(day, dt.time.min, tzinfo=tz)
    return start, start + dt.timedelta(days=1)


def parse_day(value: str | None) -> dt.date:
    return local_now().date() if not value else dt.date.fromisoformat(value)


def yesterday() -> dt.date:
    return local_now().date() - dt.timedelta(days=1)


def existing_report_days(output_dir: Path) -> list[dt.date]:
    root = output_dir.expanduser()
    if not root.exists():
        return []
    return sorted(dt.date.fromisoformat(path.stem) for path in root.iterdir() if REPORT_NAME_RE.match(path.name))


def default_day_range(output_dir: Path) -> tuple[dt.date, dt.date] | None:
    last_day = yesterday()
    days = existing_report_days(output_dir)
    if not days:
        return last_day - dt.timedelta(days=6), last_day
    first_day = max(days) + dt.timedelta(days=1)
    if first_day > last_day:
        return None
    return first_day, last_day


def requested_day_range(date: str | None, days: int | None, output_dir: Path) -> tuple[dt.date, dt.date] | None:
    if date is None and days is None:
        return default_day_range(output_dir)
    last_day = parse_day(date) if date else yesterday()
    count = days or 1
    return last_day - dt.timedelta(days=count - 1), last_day


def clean_text(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = HTML_TAG_RE.sub(" ", text)
    return NOISE_SPACE_RE.sub(" ", text).strip()


def trim(value: Any, max_chars: int = 220) -> str:
    text = clean_text(value)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "..."


def trim_middle(value: Any, max_chars: int = 220) -> str:
    text = clean_text(value)
    if len(text) <= max_chars:
        return text
    head_chars = int(max_chars * 0.58)
    tail_chars = max_chars - head_chars - 5
    return text[:head_chars].rstrip() + " ... " + text[-tail_chars:].lstrip()


def join_parts(parts: list[str]) -> str:
    return "; ".join(part for part in parts if part)


def first_sentence(text: Any, max_chars: int = 260) -> str:
    cleaned = clean_text(text)
    for marker in ("\n\n", ". ", "? ", "! "):
        index = cleaned.find(marker)
        if 30 <= index <= max_chars:
            return cleaned[: index + (1 if marker.strip() in {".", "?", "!"} else 0)].strip()
    return trim(cleaned, max_chars)


def strip_subject_prefixes(subject: Any) -> str:
    return SUBJECT_PREFIX_RE.sub("", clean_text(subject)).strip()


def strip_calendar_boilerplate(value: Any) -> str:
    text = clean_text(value)
    lower = text.lower()
    cut = len(text)
    for marker in BOILERPLATE_MARKERS:
        index = lower.find(marker)
        if index >= 0:
            cut = min(cut, index)
    return trim(text[:cut], 140)


def short_email_list(value: str, max_people: int = 3) -> str:
    people = []
    for item in value.split(","):
        cleaned = clean_text(item).strip('" ')
        if not cleaned:
            continue
        if "<" in cleaned:
            cleaned = cleaned.split("<", 1)[0].strip('" ')
        people.append(cleaned)
    if not people:
        return ""
    suffix = "" if len(people) <= max_people else f" +{len(people) - max_people}"
    return ", ".join(people[:max_people]) + suffix


def path_summary(paths: list[str], max_paths: int = 3) -> str:
    cleaned = [path for path in paths if path and not path.endswith("/")]
    if not cleaned:
        return ""
    names = [Path(path).name or path for path in cleaned[:max_paths]]
    suffix = "" if len(cleaned) <= max_paths else f" +{len(cleaned) - max_paths} files"
    return ", ".join(names) + suffix


def looks_machine_prompt(text: str) -> bool:
    lowered = text.casefold()
    return lowered.startswith(NOISY_PROMPT_PREFIXES) or ("toolu_" in lowered and "/tasks/" in lowered)


def prompt_goal(text: str) -> str:
    cleaned = clean_text(text)
    lowered = cleaned.casefold()
    if match := re.search(r"the current ([^.;]+?) works but gets ([^.;]+?) wrong", cleaned, re.I):
        return trim(f"Fix {match.group(2)} in {match.group(1)}", 220)
    if match := re.match(r"modify\s+(\S+)\s+to\s+(.+)", cleaned, re.I):
        return trim(f"Update {match.group(1)} to {match.group(2)}", 220)
    if match := re.match(r"read\s+(\S+)\s+(.+)", cleaned, re.I):
        return trim(f"Assess {match.group(1)}: {match.group(2)}", 220)
    if lowered.startswith("our aim is to build an app where"):
        return "Build multi-document Q&A app for uploaded business materials"
    if lowered.startswith("we will be adding"):
        goal = cleaned.split("adding", 1)[1].strip()
        goal = re.split(r"\bFirst,\s+", goal, maxsplit=1, flags=re.I)[0].strip()
        return trim("Add " + goal, 180)
    if lowered.startswith("you are reviewing"):
        return trim("Review " + cleaned.split("reviewing", 1)[1].strip(), 220)
    if match := re.match(r"using\s+(\S+),?\s+(.+)", cleaned, re.I):
        return trim(f"Use {match.group(1)} to {match.group(2)}", 220)
    return first_sentence(cleaned, 300)


def time_label(value: dt.datetime) -> str:
    local = value.astimezone()
    hour = local.hour % 12 or 12
    ampm = "am" if local.hour < 12 else "pm"
    return f"{hour}:{local.minute:02d} {ampm}"


def date_comment(day: dt.date) -> str:
    start, _end = day_bounds(day)
    return f"{start:%a}, {start.day} {start:%b %Y %z}"


def parse_iso(value: str) -> dt.datetime:
    text = value.replace("Z", "+00:00")
    parsed = dt.datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=local_now().tzinfo)
    return parsed.astimezone()


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def command_json(args: list[str]) -> Any:
    if args[0] == "gws":
        result = subprocess.run(args, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if stderr := useful_stderr(result.stderr):
            eprint(stderr)
        if result.returncode:
            raise subprocess.CalledProcessError(result.returncode, args, result.stdout, result.stderr)
    else:
        result = subprocess.run(args, check=True, stdout=subprocess.PIPE, text=True)
    text = result.stdout.strip()
    try:
        return json.loads(text or "{}")
    except json.JSONDecodeError:
        pass
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def page_items(data: Any, key: str) -> list[dict[str, Any]]:
    pages = data if isinstance(data, list) else [data]
    items: list[dict[str, Any]] = []
    for page in pages:
        items.extend(page.get(key, []))
    return items


def gws_items(path: list[str], params: dict[str, Any], key: str, *, page_all: bool = True) -> list[dict[str, Any]]:
    args = ["gws", *path, "--params", compact_json(params), "--format", "json"]
    if page_all:
        args.extend(["--page-all", "--page-limit", "20"])
    return page_items(command_json(args), key)


def headers(message: dict[str, Any]) -> dict[str, str]:
    raw = (message.get("payload") or {}).get("headers") or []
    return {item.get("name", "").lower(): item.get("value", "") for item in raw}


def calendar_time(value: dict[str, Any]) -> dt.datetime:
    if value.get("dateTime"):
        return parse_iso(value["dateTime"])
    return parse_iso(value["date"] + "T00:00:00")


def describe_people(attendees: list[dict[str, Any]], organizer: str) -> str:
    people = []
    for item in attendees:
        email_addr = clean_text(item.get("email")).lower()
        label = clean_text(item.get("displayName")) or email_addr
        if email_addr and email_addr not in SELF_EMAILS:
            people.append(label)
    if not people and organizer and organizer.lower() not in SELF_EMAILS:
        people.append(organizer)
    if not people:
        return ""
    suffix = "" if len(people) <= 2 else f" +{len(people) - 2}"
    return "with " + ", ".join(people[:2]) + suffix


def collect_calendar(ctx: Context) -> list[Activity]:
    params = {
        "calendarId": "primary",
        "timeMin": ctx.start.isoformat(),
        "timeMax": ctx.end.isoformat(),
        "singleEvents": True,
        "orderBy": "startTime",
        "maxResults": 2500,
        "fields": "items(id,status,summary,start,end,attendees(email,displayName,responseStatus),organizer(email),location,description,eventType),nextPageToken",
    }
    activities = []
    for item in gws_items(["calendar", "events", "list"], params, "items"):
        if item.get("status") == "cancelled":
            continue
        when = calendar_time(item.get("start") or {})
        if not (ctx.start <= when < ctx.end):
            continue
        end = calendar_time(item.get("end") or item.get("start") or {})
        minutes = max(0, int((end - when).total_seconds() // 60))
        organizer = clean_text((item.get("organizer") or {}).get("email"))
        parts = [
            trim(item.get("summary"), 90),
            describe_people(item.get("attendees") or [], organizer),
            f"{minutes}m" if minutes else "",
            strip_calendar_boilerplate(item.get("location")),
            strip_calendar_boilerplate(item.get("description")),
        ]
        activities.append(Activity(when, "calendar", join_parts(parts), "calendar", item.get("id", "")))
    return activities[: ctx.limit_per_source]


def preload_email(start: dt.datetime, end: dt.datetime) -> None:
    global EMAIL_CACHE
    if EMAIL_CACHE and EMAIL_CACHE[0] <= start and EMAIL_CACHE[1] >= end:
        return
    # Gmail date search is account-timezone based and can miss local-day edges.
    # Search a wider date window, then filter exactly on internalDate.
    after = (start - dt.timedelta(days=1)).strftime("%Y/%-m/%-d")
    before = (end + dt.timedelta(days=1)).strftime("%Y/%-m/%-d")
    listed = gws_items(
        ["gmail", "users", "messages", "list"],
        {
            "userId": "me",
            "q": f"in:sent after:{after} before:{before}",
            "maxResults": 2500,
            "fields": "messages(id,threadId),nextPageToken,resultSizeEstimate",
        },
        "messages",
    )
    eprint(f"preloading sent email metadata for {len(listed)} messages...")
    activities = []
    for row in listed:
        message_id = row.get("id")
        if not message_id:
            continue
        msg = command_json(
            [
                "gws",
                "gmail",
                "users",
                "messages",
                "get",
                "--params",
                compact_json(
                    {
                        "userId": "me",
                        "id": message_id,
                        "format": "metadata",
                        "metadataHeaders": ["To", "Cc", "Bcc", "Subject", "Date"],
                        "fields": "id,threadId,internalDate,snippet,payload(headers)",
                    }
                ),
                "--format",
                "json",
            ]
        )
        when = dt.datetime.fromtimestamp(int(msg["internalDate"]) / 1000, dt.UTC).astimezone()
        if not (start <= when < end):
            continue
        hdr = headers(msg)
        recipients = short_email_list(", ".join(filter(None, [hdr.get("to"), hdr.get("cc"), hdr.get("bcc")])))
        parts = [f"to {recipients}" if recipients else "", trim(strip_subject_prefixes(hdr.get("subject")), 120), trim(msg.get("snippet"), 180)]
        activities.append(Activity(when, "email", join_parts(parts), "email", message_id))
    activities.sort(key=lambda item: item.when, reverse=True)
    EMAIL_CACHE = (start, end, activities)


def collect_email(ctx: Context) -> list[Activity]:
    if EMAIL_CACHE is None or EMAIL_CACHE[0] > ctx.start or EMAIL_CACHE[1] < ctx.end:
        preload_email(ctx.start, ctx.end)
    activities = [row for row in (EMAIL_CACHE[2] if EMAIL_CACHE else []) if ctx.start <= row.when < ctx.end]
    return activities[: ctx.limit_per_source]


def child_repos() -> list[Path]:
    return [path for path in CODE_ROOT.iterdir() if path.is_dir() and (path / ".git").exists()]


def collect_commits(ctx: Context) -> list[Activity]:
    activities = []
    for repo in child_repos():
        result = subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "log",
                "--all",
                f"--since={ctx.start.isoformat()}",
                f"--until={ctx.end.isoformat()}",
                "--format=%x1e%cI%x00%H%x00%s",
                "--name-only",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
        for record in result.stdout.split("\x1e"):
            lines = [line for line in record.splitlines() if line.strip()]
            if not lines:
                continue
            parts = lines[0].split("\0")
            if len(parts) != 3:
                continue
            when, sha, subject = parts
            if COMMIT_TIMESTAMP_RE.search(subject):
                files = path_summary(lines[1:])
                subject = f"updated {files}" if files else subject
            activities.append(
                Activity(parse_iso(when), "commit", f"~/{repo.relative_to(Path.home())}: {trim(subject, 180)}", "commit", sha)
            )
    activities.sort(key=lambda item: item.when, reverse=True)
    return activities[: ctx.limit_per_source]


def collect_github_commits(ctx: Context) -> list[Activity]:
    start_day = ctx.start.astimezone(dt.UTC).date().isoformat()
    end_day = (ctx.end.astimezone(dt.UTC) - dt.timedelta(seconds=1)).date().isoformat()
    result = command_json(
        [
            "gh",
            "search",
            "commits",
            "--author",
            "@me",
            "--committer-date",
            f"{start_day}..{end_day}",
            "--sort",
            "committer-date",
            "--order",
            "desc",
            "--limit",
            str(min(ctx.limit_per_source * 3, 30)),
            "--json",
            "sha,repository,commit",
        ]
    )
    activities = []
    for item in result:
        commit = item.get("commit") or {}
        when = parse_iso((commit.get("committer") or {}).get("date") or (commit.get("author") or {}).get("date"))
        if not (ctx.start <= when < ctx.end):
            continue
        repo = (item.get("repository") or {}).get("fullName") or (item.get("repository") or {}).get("name") or "GitHub"
        subject = str(commit.get("message") or "").splitlines()[0]
        if COMMIT_TIMESTAMP_RE.search(subject):
            subject = "timestamped update"
        sha = item.get("sha") or ""
        activities.append(Activity(when, "commit", f"{repo}: {trim(subject, 180)}", "github-commit", sha))
        if len(activities) >= ctx.limit_per_source:
            break
    return activities


def browser_description(row: dict[str, Any]) -> tuple[str, str]:
    raw_url = row.get("url", "")
    title = clean_text(row.get("title"))
    parsed = urlparse(raw_url)
    host = parsed.netloc.replace("www.", "")
    params = parse_qs(parsed.query)
    if host.endswith("google.com") and parsed.path.startswith("/search") and params.get("q"):
        query = unquote(params["q"][0]).strip()
        if LEISURE_QUERY_RE.search(query):
            return f"leisure: search {query}", f"leisure-search:{query.casefold()}"
        return f"search: {query}", f"search:{query.casefold()}"
    if host.endswith("google.com") and parsed.path == "/url":
        target = (params.get("url") or params.get("q") or [""])[0]
        if target:
            target_host = urlparse(target).netloc.replace("www.", "") or host
            label = target_host if title.startswith("http") else title or target_host
            return f"read: {trim(label, 150)} [{target_host}]", f"{target_host}:{label.casefold()}"
    if host in {"127.0.0.1:7952", "localhost:7952"}:
        return "local app: preview server (7952)", "local:7952"
    if host in {"localhost:8000", "127.0.0.1:8000"}:
        return "local app: agentserve (8000)", "local:8000"
    if host.startswith("localhost") or host.startswith("127.0.0.1"):
        return f"local app: {host}", f"local:{host}"
    title_key = title.casefold()
    if host in LEISURE_DOMAINS:
        return f"leisure: {trim(title or host, 150)} [{host}]", f"leisure:{host}:{parsed.path}:{title_key}"
    if host in {"claude.ai", "chatgpt.com"} and title_key in GENERIC_AI_TITLES:
        return f"ai-chat: {title} session [{host}]", f"ai-chat:{host}:{parsed.path}"
    if title and title != raw_url:
        return f"read: {trim(title, 150)} [{host}]", f"{host}:{parsed.path}:{title.casefold()}"
    path = trim(parsed.path, 80)
    return f"visit: {host}{path}", f"{host}:{parsed.path}"


def collect_browser(ctx: Context) -> list[Activity]:
    data = command_json(
        [
            str(ROOT / "browsing_history.py"),
            "--no-sync",
            "--since",
            ctx.start.isoformat(),
            "--until",
            ctx.end.isoformat(),
            "--limit",
            str(ctx.limit_per_source),
            "--fields",
            "timestamp,title,url,activity_source",
            "--format",
            "json",
        ]
    )
    activities = []
    seen: dict[str, dt.datetime] = {}
    for row in data:
        when = parse_iso(row.get("timestamp", ""))
        desc, key = browser_description(row)
        previous = seen.get(key) or seen.get(desc.casefold())
        if previous and abs((when - previous).total_seconds()) <= 180:
            continue
        seen[key] = when
        seen[desc.casefold()] = when
        activities.append(Activity(when, "browser", desc, "browser", key))
    return activities


def iter_codex_files(start: dt.datetime, end: dt.datetime) -> list[Path]:
    files = []
    day = start.date()
    last_day = (end - dt.timedelta(microseconds=1)).date()
    while day <= last_day:
        folder = CODEX_SESSIONS / f"{day:%Y}" / f"{day:%m}" / f"{day:%d}"
        if folder.exists():
            files.extend(sorted(folder.glob("*.jsonl")))
        day += dt.timedelta(days=1)
    return files


def codex_activity(path: Path, start: dt.datetime, end: dt.datetime) -> Activity | None:
    session_id = path.stem
    cwd = ""
    prompt = ""
    prompt_when: dt.datetime | None = None
    start_when: dt.datetime | None = None
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            event_when = parse_iso(event["timestamp"]) if event.get("timestamp") else None
            if event_when and start_when is None:
                start_when = event_when
            payload = event.get("payload") or {}
            if event.get("type") == "session_meta":
                session_id = payload.get("id") or session_id
                cwd = payload.get("cwd") or cwd
            elif event.get("type") == "turn_context":
                cwd = payload.get("cwd") or cwd
            elif event.get("type") == "event_msg" and payload.get("type") == "user_message" and not prompt:
                message = payload.get("message")
                if isinstance(message, str):
                    prompt = clean_text(message)
                    prompt_when = event_when or start_when
    when = prompt_when or start_when
    if not prompt or when is None or not (start <= when < end) or looks_machine_prompt(prompt):
        return None
    cwd_display = cwd.replace(str(Path.home()), "~") if cwd else ""
    project = Path(cwd).name if cwd else "codex"
    desc = join_parts([project, prompt_goal(prompt), cwd_display])
    return Activity(when, "code-prompt", desc, "codex-prompt", session_id)


def preload_code_prompts(start: dt.datetime, end: dt.datetime) -> None:
    global CODE_PROMPT_CACHE
    if CODE_PROMPT_CACHE and CODE_PROMPT_CACHE[0] <= start and CODE_PROMPT_CACHE[1] >= end:
        return
    activities = []
    files = iter_codex_files(start, end)
    eprint(f"preloading code prompts from {len(files)} Codex session files...")
    for path in files:
        activity = codex_activity(path, start, end)
        if activity is not None:
            activities.append(activity)
    activities.extend(agentlog_prompt_activities(start, end))
    activities.sort(key=lambda item: item.when, reverse=True)
    CODE_PROMPT_CACHE = (start, end, activities)


def import_agentlog() -> Any:
    spec = importlib.util.spec_from_file_location("agentlog", ROOT / "agentlog.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not import agentlog.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def agentlog_prompt_activities(start: dt.datetime, end: dt.datetime) -> list[Activity]:
    agentlog = import_agentlog()
    activities = []
    for name, backend in agentlog.BACKENDS.items():
        if name == "codex":
            continue
        try:
            summaries, _stats = backend.list_sessions(
                root=backend.default_root,
                strict=False,
                cwd_filter="",
                since=start.isoformat(),
                until=end.isoformat(),
                limit=0,
                max_chars=1200,
                include_empty=False,
                width=100,
                allow_warmup=False,
                allow_local_commands=False,
                search_re=None,
            )
        except Exception as exc:
            eprint(f"warning: skipped {name} prompts: {exc}")
            continue
        for summary in summaries:
            when_text = summary.start_ts or summary.end_ts
            if not when_text:
                continue
            when = parse_iso(when_text)
            if not (start <= when < end):
                continue
            prompt = clean_text(summary.first_prompt)
            if looks_machine_prompt(prompt):
                continue
            cwd = summary.cwd.replace(str(Path.home()), "~")
            project = Path(summary.cwd).name if summary.cwd else name
            desc = join_parts([project, prompt_goal(prompt), cwd])
            activities.append(Activity(when, "code-prompt", desc, f"{name}-prompt", summary.session_id))
    return activities


def collect_code_prompts(ctx: Context) -> list[Activity]:
    if CODE_PROMPT_CACHE is None or CODE_PROMPT_CACHE[0] > ctx.start or CODE_PROMPT_CACHE[1] < ctx.end:
        preload_code_prompts(ctx.start, ctx.end)
    activities = [row for row in (CODE_PROMPT_CACHE[2] if CODE_PROMPT_CACHE else []) if ctx.start <= row.when < ctx.end]
    activities.sort(key=lambda item: item.when, reverse=True)
    return activities[: ctx.limit_per_source]


def clean_shell_command(command: str) -> str:
    text = command.replace("\x00", " ")
    text = re.sub(r"\s*(?:\n|&&|\|\|)\s*", "; ", text)
    text = re.sub(r"\s*;\s*", "; ", text)
    return NOISE_SPACE_RE.sub(" ", text).strip(" ;")


def is_signal_shell_command(command: str) -> bool:
    lowered = command.casefold()
    if lowered.startswith("#"):
        return False
    if SHELL_SENSITIVE_RE.search(command):
        return False
    if "history" in lowered and not re.search(r"\b(?:git|agentlog|activities)\b", lowered):
        return False
    if SHELL_NOISE_RE.match(lowered):
        return False
    return bool(SHELL_SIGNAL_RE.search(lowered) or "|" in command or ">" in command)


def shell_command_score(command: str) -> int:
    lowered = command.casefold()
    score = 0
    scoring = [
        (r"\bgit (commit|push|merge|rebase|tag)\b", 7),
        (r"\b(transcribe_calls|backupmeet|backupwhatsapp|mcpserver|activities|browsing_history)\.py\b", 6),
        (r"\b(gws|bq|gcloud|gh|rclone|ffmpeg|melt|pandoc|yt-dlp)\b", 5),
        (r"\b(uv run|uvx|npm run|npx|just|pytest|ruff|dprint)\b", 4),
        (r"\b(duckdb|sqlite3|qsv|csvq|jaq|yq|jq|ug|rg|rga|fd|sg)\b", 3),
        (r"\b(code|codex|claude|llm)\b", 2),
    ]
    for pattern, points in scoring:
        if re.search(pattern, lowered):
            score += points
    if "|" in command or ">" in command:
        score += 1
    if re.match(r"^(git status|git diff|git show)\b", lowered):
        score -= 2
    if len(command) > 260:
        score += 1
    return score


def preload_shell_commands(start: dt.datetime, end: dt.datetime) -> None:
    global SHELL_CACHE
    if SHELL_CACHE and SHELL_CACHE[0] <= start and SHELL_CACHE[1] >= end:
        return
    result = subprocess.run(
        ["fish", "-lc", 'history --show-time="%s " --null --max 50000'],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        eprint(f"warning: skipped fish history: {result.stderr.decode(errors='replace').strip()}")
        SHELL_CACHE = (start, end, [])
        return
    eprint("preloading fish shell history...")
    rows = []
    for record in result.stdout.split(b"\0"):
        if not record.strip():
            continue
        head, _, body = record.partition(b" ")
        try:
            when = dt.datetime.fromtimestamp(int(head), start.tzinfo).astimezone()
        except ValueError:
            continue
        if not (start <= when < end):
            continue
        command = clean_shell_command(body.decode(errors="replace"))
        if not command or not is_signal_shell_command(command):
            continue
        rows.append(Activity(when, "shell", command, "fish-history", f"fish:{int(when.timestamp())}:{command[:80]}"))
    rows.sort(key=lambda item: item.when)
    SHELL_CACHE = (start, end, rows)


def collect_shell(ctx: Context) -> list[Activity]:
    if SHELL_CACHE is None or SHELL_CACHE[0] > ctx.start or SHELL_CACHE[1] < ctx.end:
        preload_shell_commands(ctx.start, ctx.end)
    commands = [row for row in (SHELL_CACHE[2] if SHELL_CACHE else []) if ctx.start <= row.when < ctx.end]
    bursts: list[list[Activity]] = []
    for command in commands:
        if not bursts or (command.when - bursts[-1][-1].when).total_seconds() > FISH_HISTORY_BURST_MINUTES * 60:
            bursts.append([command])
        else:
            bursts[-1].append(command)
    activities = []
    for burst in bursts:
        commands_by_text = {row.activity: row for row in burst}
        ordered_commands = list(commands_by_text)
        samples = sorted(sorted(ordered_commands, key=shell_command_score, reverse=True)[:3], key=ordered_commands.index)
        more = len(ordered_commands) - len(samples)
        suffix = "" if more <= 0 else f"; +{more} more"
        activity = trim_middle("CLI: " + "; ".join(samples) + suffix, SHELL_COMMAND_MAX_CHARS)
        activities.append(Activity(burst[0].when, "shell", activity, "fish-history", f"fish-burst:{int(burst[0].when.timestamp())}"))
    return activities[: ctx.limit_per_source]


COLLECTORS: dict[str, Collector] = {
    "calendar": collect_calendar,
    "email": collect_email,
    "commit": collect_commits,
    "github-commit": collect_github_commits,
    "browser": collect_browser,
    "code-prompt": collect_code_prompts,
    "shell": collect_shell,
}


def parse_sources(value: str) -> list[str]:
    sources = [part.strip() for part in value.replace(" ", ",").split(",") if part.strip()]
    bad = sorted(set(sources) - set(COLLECTORS))
    if bad:
        raise typer.BadParameter(f"unknown source(s): {', '.join(bad)}. Valid: {', '.join(COLLECTORS)}")
    return sources


def sync_browser_history() -> None:
    subprocess.run([str(ROOT / "browsing_history.py"), "--sync-only"], check=True)


def dedupe(activities: list[Activity]) -> list[Activity]:
    seen: set[str] = set()
    rows = []
    for item in sorted(activities, key=lambda row: (row.when, row.type, row.activity)):
        key = item.source_id or f"{item.when.isoformat()}:{item.type}:{item.activity}"
        if key in seen:
            continue
        seen.add(key)
        rows.append(item)
    return compress_bursts(rows)


def compress_bursts(rows: list[Activity]) -> list[Activity]:
    compressed: list[Activity] = []
    counts: list[int] = []
    for item in rows:
        if compressed:
            previous = compressed[-1]
            same = previous.type == item.type and previous.activity == item.activity
            close = (item.when - previous.when).total_seconds() <= 20 * 60
            if same and close:
                counts[-1] += 1
                continue
        compressed.append(item)
        counts.append(1)
    output = []
    for item, count in zip(compressed, counts):
        if count > 1:
            output.append(replace(item, activity=f"{item.activity} ({count}x in burst)"))
        else:
            output.append(item)
    return output


def rows_for_day(ctx: Context, sources: list[str]) -> list[Activity]:
    activities: list[Activity] = []
    local_commit_shas: set[str] = set()
    for source in sources:
        eprint(f"{ctx.day}: collecting {source}...")
        rows = COLLECTORS[source](ctx)
        if source == "commit":
            local_commit_shas.update(row.source_id for row in rows)
        if source == "github-commit":
            rows = [row for row in rows if row.source_id not in local_commit_shas]
        activities.extend(rows)
    return annotate_contextual_rows(dedupe(activities))


def annotate_contextual_rows(rows: list[Activity]) -> list[Activity]:
    output: list[Activity] = []
    last_named: Activity | None = None
    for row in rows:
        title = row.activity.split(";", 1)[0].strip()
        if row.type == "calendar" and title.casefold() == "spillover" and last_named is not None:
            output.append(replace(row, activity=f"Spillover from {last_named.activity.split(';', 1)[0]};" + row.activity.split(";", 1)[1]))
            continue
        output.append(row)
        if row.type in {"calendar", "code-prompt", "commit"} and title.casefold() not in {"lunch", "dinner", "travel", "call home", "spillover"}:
            last_named = row
    return output


def write_report(path: Path, day: dt.date, rows: list[Activity], generated_at: dt.datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", dir=path.parent, delete=False) as handle:
        handle.write(f"# DATE={date_comment(day)}\n")
        handle.write(f"# GENERATED_AT={generated_at.isoformat(timespec='seconds')}\n")
        writer = csv.writer(handle, dialect="excel-tab", lineterminator="\n")
        writer.writerow(["Time", "Type", "Activity"])
        for row in rows:
            writer.writerow([time_label(row.when), row.type, row.activity])
        temp = Path(handle.name)
    temp.replace(path)


def print_report(day: dt.date, rows: list[Activity], generated_at: dt.datetime) -> None:
    print(f"# DATE={date_comment(day)}")
    print(f"# GENERATED_AT={generated_at.isoformat(timespec='seconds')}")
    writer = csv.writer(sys.stdout, dialect="excel-tab", lineterminator="\n")
    writer.writerow(["Time", "Type", "Activity"])
    for row in rows:
        writer.writerow([time_label(row.when), row.type, row.activity])


def describe() -> dict[str, Any]:
    return {
        "name": "activities.py",
        "purpose": "Generate ~/Documents/activities/YYYY-MM-DD.tsv daily activity reports.",
        "comments": ["DATE", "GENERATED_AT"],
        "columns": ["Time", "Type", "Activity"],
        "sources": sorted(COLLECTORS),
        "default_sources": DEFAULT_SOURCES.split(","),
        "default_date_range": "Pending days after the latest YYYY-MM-DD.tsv in output_dir through yesterday; if none exist, the last 7 days ending yesterday.",
        "extension_point": "Add a collect_<source>(Context) function and register it in COLLECTORS.",
    }


@app.callback(invoke_without_command=True)
def main(
    date: str | None = typer.Option(None, "--date", help="Last local day to generate, YYYY-MM-DD. Default with --days: yesterday."),
    days: int | None = typer.Option(None, "--days", min=1, help="Generate this many days ending at --date. Default: pending days through yesterday."),
    sources: str = typer.Option(DEFAULT_SOURCES, "--sources", help="Comma/space separated sources."),
    output_dir: Path = typer.Option(OUT_ROOT, "--output-dir", help="Directory for YYYY-MM-DD.tsv reports."),
    limit_per_source: int = typer.Option(500, "--limit-per-source", min=1, help="Maximum rows from each source per day."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print the first report to stdout instead of writing files."),
    no_browser_sync: bool = typer.Option(False, "--no-browser-sync", help="Do not refresh browsing-history.db before browser queries."),
    show_describe: bool = typer.Option(False, "--describe", help="Print machine-readable CLI metadata and exit."),
) -> None:
    if show_describe:
        print(json.dumps(describe(), indent=2))
        return

    selected_sources = parse_sources(sources)
    day_range = requested_day_range(date, days, output_dir)
    if day_range is None:
        eprint(f"nothing to do: reports are current through {yesterday().isoformat()}")
        return
    if "browser" in selected_sources and not no_browser_sync:
        eprint("syncing browser history...")
        sync_browser_history()
    generated_at = local_now()
    first_day, last_day = day_range
    first_start, _first_end = day_bounds(first_day)
    _last_start, last_end = day_bounds(last_day)
    if "email" in selected_sources:
        preload_email(first_start, last_end)
    if "code-prompt" in selected_sources:
        preload_code_prompts(first_start, last_end)
    if "shell" in selected_sources:
        preload_shell_commands(first_start, last_end)
    total_days = (last_day - first_day).days + 1
    for offset in range(total_days - 1, -1, -1):
        day = last_day - dt.timedelta(days=offset)
        start, end = day_bounds(day)
        rows = rows_for_day(Context(day, start, end, limit_per_source, "browser" in selected_sources), selected_sources)
        if dry_run:
            print_report(day, rows, generated_at)
            return
        path = output_dir.expanduser() / f"{day.isoformat()}.tsv"
        write_report(path, day, rows, generated_at)
        eprint(f"wrote {path} ({len(rows)} rows)")


if __name__ == "__main__":
    app()
