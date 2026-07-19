#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["httpx>=0.28", "typer>=0.12", "twitter-cli>=0.8"]
# ///
"""Back up Twitter/X sources into weekly JSON and Markdown files.

Examples:
  backuptwitter.py
  backuptwitter.py --week 2026-06-28 --limit 500
  backuptwitter.py --source list-genai --dry-run --format json | jaq .
  backuptwitter.py --describe | jaq .
"""

from __future__ import annotations

import asyncio
import html
import json
import os
import re
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import httpx
import typer

app = typer.Typer(add_completion=False, help=__doc__)

SOURCES: dict[str, dict[str, Any]] = {
    "list-genai": {
        "kind": "list",
        "id": "1778746851312783449",
        "dest": "~/Documents/twitter/list-genai",
    },
    **{
        f"@{handle}": {"kind": "user", "handle": handle, "dest": f"~/Documents/twitter/@{handle}"}
        for handle in [
            "petergostev",
            "emollick",
            "karpathy",
            "simonw",
            "sama",
            "DarioAmodei",
            "demishassabis",
            "charliemarsh",
            "ch402",
            "thdxr",
        ]
    },
}
TWITTER_CWD = Path("~/Documents/twitter")
URL_RE = re.compile(r"https?://t\.co/[A-Za-z0-9]+")


@dataclass(frozen=True)
class Week:
    label: date

    @property
    def start(self) -> datetime:
        return datetime.combine(self.label - timedelta(days=7), datetime.min.time(), UTC)

    @property
    def end(self) -> datetime:
        return datetime.combine(self.label, datetime.min.time(), UTC)


def eprint(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def parse_week(value: str | None) -> Week:
    if value:
        label = date.fromisoformat(value)
    else:
        today = datetime.now(UTC).date()
        label = today - timedelta(days=(today.weekday() + 1) % 7)
    if label.weekday() != 6:
        raise typer.BadParameter(f"--week must be a Sunday, got {label}")
    return Week(label)


def weeks_ending(value: str | None, count: int) -> list[Week]:
    if count < 1:
        raise typer.BadParameter("--weeks must be at least 1")
    end = parse_week(value).label
    return [Week(end - timedelta(days=7 * index)) for index in range(count)]


def now_utc() -> datetime:
    return datetime.now(UTC)


def parse_dt(tweet: dict[str, Any]) -> datetime:
    value = tweet.get("createdAtISO") or tweet.get("createdAt")
    if not value:
        raise ValueError(f"tweet {tweet.get('id', '<missing id>')} has no createdAt/createdAtISO")
    if isinstance(value, str) and value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        parsed = parsedate_to_datetime(value)
    return parsed.astimezone(UTC)


def clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", html.unescape(text or "")).strip()


def author(tweet: dict[str, Any]) -> str:
    data = tweet.get("author") or {}
    return f"@{data.get('screenName') or data.get('username') or '?'}"


def iso(tweet: dict[str, Any]) -> str:
    return tweet.get("createdAtISO") or tweet.get("createdAt") or ""


def tweet_url(tweet: dict[str, Any]) -> str:
    return f"https://x.com/{author(tweet)[1:]}/status/{tweet.get('id')}"


def metrics(tweet: dict[str, Any]) -> str:
    data = tweet.get("metrics") or {}
    parts = []
    for key, label in [("likes", "❤️"), ("retweets", "🔁"), ("replies", "💬"), ("views", "👁️")]:
        if data.get(key) is not None:
            parts.append(f"{label}{data[key]}")
    return " ".join(parts)


def extras(tweet: dict[str, Any]) -> list[str]:
    parts = []
    links = tweet.get("urls") or []
    if links:
        urls = links if isinstance(links[0], str) else [item.get("expandedUrl") or item.get("url") for item in links]
        parts.append("Links: " + ", ".join(url for url in urls if url))
    media = tweet.get("media") or []
    if media:
        parts.append("Media: " + ", ".join(item.get("url") for item in media if item.get("url")))
    return parts


def markdown_line(ref: str, tweet: dict[str, Any], indent: str = "", rel: str = "") -> str:
    rel = f" {rel}" if rel else ""
    meta = f" {metrics(tweet)}" if metrics(tweet) else ""
    lines = [f"{indent}- [{ref}{rel}] {author(tweet)}: {clean(tweet.get('text'))} [{iso(tweet)}]{meta}"]
    lines.append(f"{indent}  URL: {tweet_url(tweet)}")
    lines += [f"{indent}  {item}" for item in extras(tweet)]
    if quote := tweet.get("quotedTweet"):
        lines.append(f"{indent}  - [{ref}.q1 quote] {author(quote)}: {clean(quote.get('text'))} [{iso(quote)}]")
        lines.append(f"{indent}    URL: {tweet_url(quote)}")
    return "\n".join(lines)


def markdown(tweets: list[dict[str, Any]]) -> str:
    tweets = sorted(tweets, key=parse_dt)
    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for tweet in tweets:
        same_author = current and author(tweet) == author(current[-1])
        near = current and (parse_dt(tweet) - parse_dt(current[-1])).total_seconds() <= 30 * 60
        if same_author and near:
            current.append(tweet)
        else:
            if current:
                groups.append(current)
            current = [tweet]
    if current:
        groups.append(current)

    chunks = []
    for index, group in enumerate(groups, 1):
        if len(group) == 1:
            chunks.append(markdown_line(str(index), group[0]))
            continue
        lines = [f"- [{index} thread?] Possible thread by {author(group[0])} [{iso(group[0])}-{iso(group[-1])}]"]
        lines += [markdown_line(f"{index}.{subindex}", tweet, "  ") for subindex, tweet in enumerate(group, 1)]
        chunks.append("\n".join(lines))
    return "\n\n".join(chunks) + ("\n" if chunks else "No tweets.\n")


async def expand_one(client: httpx.AsyncClient, sem: asyncio.Semaphore, url: str) -> tuple[str, str]:
    async with sem:
        try:
            response = await client.head(url)
            return url, response.headers.get("location", url)
        except Exception as exc:
            eprint(f"warning: could not resolve {url}: {exc}")
            return url, url


async def resolve_tco(text: str) -> str:
    urls = list(dict.fromkeys(match.group(0) for match in URL_RE.finditer(text)))
    if not urls:
        return text
    sem = asyncio.Semaphore(8)
    async with httpx.AsyncClient(follow_redirects=False, timeout=10) as client:
        pairs = await asyncio.gather(*(expand_one(client, sem, url) for url in urls))
    for old, new in pairs:
        text = text.replace(old, new)
    return text


@contextmanager
def working_dir(path: Path):
    old = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old)


def fetch(source: dict[str, Any], limit: int, cwd: Path) -> dict[str, Any]:
    """Fetch through twitter-cli's Python API.

    twitter-cli hard-caps timeline fetches at 500 even when config asks for more.
    Raising the in-memory cap keeps pagination in the package while avoiding edits
    to the installed tool.
    """
    eprint(f"fetching {limit} tweets in {cwd} via twitter-cli Python API")
    with working_dir(cwd):
        from twitter_cli.auth import get_cookies
        import twitter_cli.client as client_module
        from twitter_cli.client import TwitterClient
        from twitter_cli.config import load_config
        from twitter_cli.serialization import tweets_to_data

        client_module._ABSOLUTE_MAX_COUNT = max(client_module._ABSOLUTE_MAX_COUNT, limit)
        config = load_config()
        cookies = get_cookies()
        client = TwitterClient(cookies["auth_token"], cookies["ct0"], config.get("rateLimit"), cookie_string=cookies.get("cookie_string"))
        if source["kind"] == "list":
            tweets = client.fetch_list_timeline(source["id"], limit)
        elif source["kind"] == "user":
            profile = client.fetch_user(source["handle"])
            tweets = client.fetch_user_tweets(profile.id, limit)
        else:
            raise ValueError(f"unknown source kind: {source['kind']}")
    return {"ok": True, "schema_version": "1", "data": tweets_to_data(tweets)}


def tweet_rows(root: Any) -> list[dict[str, Any]]:
    rows = root.get("data", root) if isinstance(root, dict) else root
    if not isinstance(rows, list):
        raise ValueError("twitter-cli JSON must be a list or an object with a data list")
    return rows


def tweet_key(tweet: dict[str, Any]) -> str:
    return str(tweet.get("id") or tweet_url(tweet))


def richness(value: Any) -> int:
    if value in (None, "", [], {}, False):
        return 0
    if isinstance(value, str):
        return len(value)
    if isinstance(value, (list, dict)):
        return len(value)
    return 1


def merge_tweets(existing: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int, int]:
    rows = {tweet_key(tweet): tweet for tweet in existing}
    added = changed = 0
    for tweet in incoming:
        key = tweet_key(tweet)
        if key not in rows:
            rows[key] = tweet
            added += 1
            continue
        merged = dict(rows[key])
        for name, value in tweet.items():
            if name == "metrics" or richness(value) >= richness(merged.get(name)):
                merged[name] = value
        if merged != rows[key]:
            changed += 1
        rows[key] = merged
    return sorted(rows.values(), key=parse_dt), added, changed


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text())


def week_tweets(rows: list[dict[str, Any]], week: Week) -> list[dict[str, Any]]:
    return sorted([tweet for tweet in rows if week.start <= parse_dt(tweet) < week.end], key=parse_dt)


def tweet_bounds(tweets: list[dict[str, Any]]) -> dict[str, str | None]:
    if not tweets:
        return {"oldest_tweet_at": None, "newest_tweet_at": None}
    return {
        "oldest_tweet_at": parse_dt(tweets[0]).isoformat().replace("+00:00", "Z"),
        "newest_tweet_at": parse_dt(tweets[-1]).isoformat().replace("+00:00", "Z"),
    }


def fetched_bounds(rows: list[dict[str, Any]]) -> dict[str, str | None]:
    return {
        "fetched_oldest_at": parse_dt(rows[-1]).isoformat().replace("+00:00", "Z") if rows else None,
        "fetched_newest_at": parse_dt(rows[0]).isoformat().replace("+00:00", "Z") if rows else None,
    }


def complete_from_fetch(rows: list[dict[str, Any]], week: Week, limit: int) -> bool:
    return bool(rows) and (len(rows) < limit or parse_dt(rows[-1]) <= week.start)


def existing_data_complete(existing: dict[str, Any] | None, week: Week) -> bool:
    if not existing:
        return False
    backup = existing.get("backup") or {}
    if backup.get("fetched_oldest_at"):
        return parse_dt({"createdAtISO": backup["fetched_oldest_at"]}) <= week.start
    if backup.get("fetched") is not None and backup.get("limit") is not None and int(backup["fetched"]) < int(backup["limit"]):
        return True
    if not tweet_rows(existing):
        return True
    # Legacy files predate explicit completion metadata. Treat them as complete
    # for resume speed; --refresh can rebuild them with stricter metadata.
    return backup.get("complete", True) is True


def markdown_complete(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


def filtered_root(root: dict[str, Any], tweets: list[dict[str, Any]], week: Week, source_name: str, limit: int, meta: dict[str, Any]) -> dict[str, Any]:
    output = dict(root)
    output["data"] = tweets
    output["backup"] = {
        "source": source_name,
        "week_start": week.start.isoformat().replace("+00:00", "Z"),
        "week_end": week.end.isoformat().replace("+00:00", "Z"),
        "week_closed": week.end <= now_utc(),
        "tweet_count": len(tweets),
        "limit": limit,
        "updated_at": now_utc().isoformat().replace("+00:00", "Z"),
        **tweet_bounds(tweets),
        **meta,
    }
    return output


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{time.time_ns()}.tmp")
    tmp.write_text(text)
    tmp.replace(path)


def describe() -> dict[str, Any]:
    return {
        "name": "backuptwitter.py",
        "default_source": "list-genai",
        "sources": SOURCES,
        "twitter_cwd": str(TWITTER_CWD),
        "week": "Sunday date ending the backed-up UTC week [week-7d, week)",
        "outputs": ["<dest>/<week>.json", "<dest>/<week>.md"],
        "examples": [
            "backuptwitter.py",
            "backuptwitter.py --all-sources --week 2026-06-28 --weeks 3",
            "backuptwitter.py --week 2026-06-28 --limit 500",
            "backuptwitter.py --source list-genai --dry-run --format json",
        ],
    }


def source_names(source_name: str, all_sources: bool) -> list[str]:
    if all_sources:
        return list(SOURCES)
    if source_name not in SOURCES:
        raise typer.BadParameter(f"unknown --source {source_name!r}; choose one of {', '.join(SOURCES)}")
    return [source_name]


def backup_source(
    source_name: str,
    week_value: str | None,
    limit: int,
    dest: Path | None,
    twitter_cwd: Path,
    weeks: int,
    incremental_limit: int,
    refresh: bool,
    dry_run: bool,
    no_resolve: bool,
) -> list[dict[str, Any]]:
    source = SOURCES[source_name]
    out_dir = (dest or Path(source["dest"])).expanduser()
    selected_weeks = weeks_ending(week_value, weeks)
    run_at = now_utc()

    plans = []
    for week in selected_weeks:
        json_path = out_dir / f"{week.label}.json"
        md_path = out_dir / f"{week.label}.md"
        existing = load_json(json_path)
        closed = week.end <= run_at
        skip_fetch = bool(closed and not refresh and existing_data_complete(existing, week))
        skip_write = bool(skip_fetch and markdown_complete(md_path))
        plans.append({
            "week": week,
            "json_path": json_path,
            "md_path": md_path,
            "existing": existing,
            "closed": closed,
            "skip_fetch": skip_fetch,
            "skip_write": skip_write,
        })

    needs_fetch = [plan for plan in plans if not plan["skip_fetch"]]
    root: dict[str, Any] = {"ok": True, "schema_version": "1", "data": []}
    rows: list[dict[str, Any]] = []
    fetched_limit = 0
    if needs_fetch:
        all_existing_open = all(plan["existing"] and not plan["closed"] for plan in needs_fetch)
        fetch_limit = min(limit, incremental_limit) if all_existing_open else limit
        overlap_ids = {
            tweet_key(tweet)
            for plan in needs_fetch
            for tweet in tweet_rows(plan["existing"] or {"data": []})
            if not plan["closed"]
        }
        while True:
            root = fetch(source, fetch_limit, twitter_cwd.expanduser())
            rows = tweet_rows(root)
            fetched_limit = fetch_limit
            if not overlap_ids or any(tweet_key(tweet) in overlap_ids for tweet in rows) or fetch_limit >= limit or len(rows) < fetch_limit:
                break
            fetch_limit = min(limit, fetch_limit * 2)
            eprint(f"no overlap with existing open-week tweets; retrying with --limit {fetch_limit}")

    summaries = []
    for plan in plans:
        week = plan["week"]
        json_path = plan["json_path"]
        md_path = plan["md_path"]
        existing = plan["existing"]
        if plan["skip_write"]:
            existing_tweets = week_tweets(tweet_rows(existing), week)
            summaries.append({
                "source": source_name,
                "week": week.label.isoformat(),
                "week_start": week.start.isoformat().replace("+00:00", "Z"),
                "week_end": week.end.isoformat().replace("+00:00", "Z"),
                "fetched": 0,
                "kept": len(existing_tweets),
                "added": 0,
                "changed": 0,
                "complete": True,
                "skipped": True,
                "reason": "complete closed week already exists",
                "json": str(json_path),
                "markdown": str(md_path),
                "dry_run": dry_run,
            })
            continue

        existing_tweets = week_tweets(tweet_rows(existing), week) if existing else []
        incoming = [] if plan["skip_fetch"] else week_tweets(rows, week)
        tweets, added, changed = merge_tweets(existing_tweets, incoming)
        existing_backup = (existing or {}).get("backup") or {}
        complete = existing_backup.get("complete", True) if plan["skip_fetch"] else (True if not plan["closed"] else complete_from_fetch(rows, week, fetched_limit))
        data = filtered_root(root if isinstance(root, dict) else existing or {"ok": True}, tweets, week, source_name, fetched_limit, {
            "fetched": len(rows),
            "incoming": len(incoming),
            "added": added,
            "changed": changed,
            "complete": complete,
            "skipped": False,
            "rebuilt_from_existing": bool(plan["skip_fetch"]),
            "run_started_at": run_at.isoformat().replace("+00:00", "Z"),
            **fetched_bounds(rows),
        })
        md_text = markdown(tweets)
        if not no_resolve:
            md_text = asyncio.run(resolve_tco(md_text))
        if not dry_run:
            atomic_write(json_path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
            atomic_write(md_path, md_text)
        summaries.append({
            "source": source_name,
            "week": week.label.isoformat(),
            "week_start": week.start.isoformat().replace("+00:00", "Z"),
            "week_end": week.end.isoformat().replace("+00:00", "Z"),
            "fetched": len(rows),
            "kept": len(tweets),
            "added": added,
            "changed": changed,
            "complete": complete,
            "skipped": False,
            "json": str(json_path),
            "markdown": str(md_path),
            "dry_run": dry_run,
        })
    return summaries


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    source_name: str = typer.Option("list-genai", "--source", help="Source key in SOURCES."),
    all_sources: bool = typer.Option(False, "--all-sources", help="Back up every configured source, skipping complete weeks."),
    week_value: str | None = typer.Option(None, "--week", help="Sunday date ending the UTC week, e.g. 2026-06-28."),
    limit: int = typer.Option(500, "--limit", "-n", min=1, help="Recent tweets to fetch from twitter-cli."),
    dest: Path | None = typer.Option(None, "--dest", help="Override output directory."),
    twitter_cwd: Path = typer.Option(TWITTER_CWD, "--twitter-cwd", help="Working directory for uvx twitter-cli."),
    weeks: int = typer.Option(1, "--weeks", min=1, help="Number of weekly files to write ending at --week."),
    incremental_limit: int = typer.Option(100, "--incremental-limit", min=1, help="Initial fetch depth when only updating existing open weeks."),
    refresh: bool = typer.Option(False, "--refresh", help="Rebuild existing closed weeks instead of skipping them."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Fetch and filter, but do not write files."),
    output_format: str = typer.Option("text", "--format", help="text or json summary."),
    no_resolve: bool = typer.Option(False, "--no-resolve", help="Do not resolve t.co links in Markdown."),
    describe_flag: bool = typer.Option(False, "--describe", help="Print machine-readable CLI description and exit."),
) -> None:
    """Back up the selected source for a completed UTC week."""
    if ctx.invoked_subcommand:
        return
    if describe_flag:
        print(json.dumps(describe(), indent=2, ensure_ascii=False))
        return
    if output_format not in {"text", "json"}:
        raise typer.BadParameter("--format must be text or json")

    summaries = []
    failed = False
    for name in source_names(source_name, all_sources):
        try:
            summaries.extend(backup_source(name, week_value, limit, dest, twitter_cwd, weeks, incremental_limit, refresh, dry_run, no_resolve))
        except Exception as exc:
            if not all_sources:
                raise
            failed = True
            summaries.append({
                "source": name,
                "failed": True,
                "error": str(exc),
                "dry_run": dry_run,
            })
    if output_format == "json":
        print(json.dumps(summaries[0] if len(summaries) == 1 else summaries, indent=2, ensure_ascii=False))
    else:
        action = "would write" if dry_run else "wrote"
        for summary in summaries:
            if summary.get("failed"):
                eprint(f"failed {summary['source']}: {summary['error']}")
                continue
            if summary["skipped"]:
                eprint(f"skipped {summary['kept']} tweets for {summary['week_start']}..{summary['week_end']}: {summary['reason']}")
            else:
                status = "complete" if summary["complete"] else "incomplete"
                eprint(f"{action} {summary['kept']} tweets ({summary['added']} added, {summary['changed']} changed, {status}) from {summary['fetched']} fetched for {summary['week_start']}..{summary['week_end']}")
            print(summary["json"])
            print(summary["markdown"])
    if failed:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
