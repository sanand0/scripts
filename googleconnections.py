#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["playwright>=1.52", "typer>=0.12"]
# ///
"""List apps connected to the current Google Account via a CDP browser.

Examples:
  googleconnections.py
  googleconnections.py --format csv | xclip -selection clipboard
  googleconnections.py --limit 5 --format jsonl | moor
  googleconnections.py --describe | jaq .
"""

from __future__ import annotations

import asyncio
import csv
import datetime as dt
import json
import re
import sys
from dataclasses import dataclass
from io import StringIO
from typing import Any
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import typer
from playwright.async_api import Browser, Page, TimeoutError as PlaywrightTimeoutError, async_playwright

app = typer.Typer(add_completion=False, help=__doc__)

CDP_URL = "http://localhost:9222"
CONNECTIONS_URL = "https://myaccount.google.com/connections"
COLUMNS = ["url", "app", "time", "permissions", "id"]
MONTH_FORMATS = [
    "%B %d, %Y, %I:%M %p",
    "%B %d, %Y",
    "%Y %B %d, %I:%M %p",
    "%Y %B %d",
]
STOP_PERMISSION_LINES = {
    "If you remove access",
    "If you stop using Sign in with Google",
    "Remove all access",
    "Stop using Sign in with Google",
    "See something suspicious? Report this app",
    "PrivacyTermsHelpAbout",
}
ICON_LINES = {"account_circle", "pentagon"}


@dataclass(frozen=True)
class Connection:
    app: str
    id: str
    overview_url: str


def eprint(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\u202f", " ").replace("\xa0", " ")).strip()


def describe() -> dict[str, Any]:
    return {
        "name": "googleconnections.py",
        "cdp": CDP_URL,
        "source": CONNECTIONS_URL,
        "columns": COLUMNS,
        "formats": ["tsv", "csv", "jsonl"],
        "default_format": "tsv",
        "sort": ["url", "app", "id"],
        "examples": [
            "googleconnections.py",
            "googleconnections.py --format csv | xclip -selection clipboard",
            "googleconnections.py --limit 5 --format jsonl | moor",
        ],
    }


async def google_page(browser: Browser) -> Page:
    if browser.contexts:
        return await browser.contexts[0].new_page()
    raise RuntimeError("No CDP browser context found. Start Chrome/Edge with remote debugging on port 9222.")


async def goto(page: Page, url: str, settle_ms: int) -> str:
    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_timeout(settle_ms)
    text = await page.locator("body").inner_text(timeout=15000)
    if "Sign in" in await page.title() or "accounts.google.com" in page.url:
        raise RuntimeError("Google Account is not authenticated in the CDP browser. Log in manually, then rerun.")
    if "404. That" in text:
        raise RuntimeError(f"page not found: {url}")
    return text


def connection_id(url: str) -> str:
    match = re.search(r"/connections/overview/([^/?#]+)", url)
    if not match:
        raise ValueError(f"not a connection overview URL: {url}")
    return match.group(1)


async def list_connections(page: Page, settle_ms: int) -> tuple[list[Connection], int | None, str]:
    text = await goto(page, CONNECTIONS_URL, settle_ms)
    await page.wait_for_selector('a[href*="connections/overview/"]', timeout=15000)
    browser_tz = await page.evaluate("Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'")
    total_match = re.search(r"\b(\d+)\s+total apps\b", text)
    total = int(total_match.group(1)) if total_match else None
    links = await page.eval_on_selector_all(
        'a[href*="connections/overview/"]',
        """els => els.map(a => ({ text: a.innerText, href: a.href }))""",
    )
    by_id: dict[str, Connection] = {}
    for link in links:
        href = str(link.get("href") or "")
        name = clean_text(str(link.get("text") or ""))
        if not name:
            continue
        ident = connection_id(href)
        by_id.setdefault(ident, Connection(name, ident, href))
    return list(by_id.values()), total, browser_tz


def line_after(lines: list[str], label: str) -> str:
    for index, line in enumerate(lines):
        if line == label and index + 1 < len(lines):
            return lines[index + 1]
    return ""


def first_line_after(lines: list[str], labels: list[str]) -> str:
    for label in labels:
        if value := line_after(lines, label):
            return value
    return ""


def normalize_url(value: str) -> str:
    text = clean_text(value).strip("/")
    if not text:
        return ""
    if re.match(r"^[a-z][a-z0-9+.-]*://", text):
        return text
    if "." in text and " " not in text:
        return f"https://{text}"
    return text


def parse_access_time(value: str, tz_name: str, now: dt.datetime) -> dt.datetime | None:
    text = clean_text(value)
    if not text:
        return None
    lower = text.lower()
    tz = ZoneInfo(tz_name)
    if match := re.fullmatch(r"yesterday,?\s+(\d{1,2}:\d{2}\s*[AP]M)", text, flags=re.I):
        parsed_time = dt.datetime.strptime(match.group(1).upper().replace(" ", ""), "%I:%M%p").time()
        return dt.datetime.combine(now.date() - dt.timedelta(days=1), parsed_time, tz)
    if match := re.fullmatch(r"today,?\s+(\d{1,2}:\d{2}\s*[AP]M)", text, flags=re.I):
        parsed_time = dt.datetime.strptime(match.group(1).upper().replace(" ", ""), "%I:%M%p").time()
        return dt.datetime.combine(now.date(), parsed_time, tz)
    if match := re.fullmatch(r"(\d+)\s+(minute|hour|day)s?\s+ago", lower):
        amount = int(match.group(1))
        unit = match.group(2)
        delta = {"minute": dt.timedelta(minutes=amount), "hour": dt.timedelta(hours=amount), "day": dt.timedelta(days=amount)}[unit]
        return (now - delta).replace(second=0, microsecond=0)
    candidates = [text]
    if not re.search(r"\b\d{4}\b", text):
        candidates.append(f"{now.year} {text}")
    for candidate in candidates:
        for fmt in MONTH_FORMATS:
            try:
                parsed = dt.datetime.strptime(candidate, fmt)
            except ValueError:
                continue
            return parsed.replace(tzinfo=tz)
    return None


def format_time(value: dt.datetime | None) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%S%z") if value else ""


def detail_permissions(lines: list[str], app_name: str, detail_url: str) -> list[str]:
    permissions: list[str] = []
    if "/siwg/" in detail_url or any("You use Sign in with Google" in line for line in lines):
        permissions.append("See your profile info")
    if "/gal/" in detail_url:
        permissions.extend(line for line in lines if line.startswith("Google can access "))
    start = next((index for index, line in enumerate(lines) if line.endswith(" can:")), -1)
    if start >= 0:
        for line in lines[start + 1 :]:
            if line in STOP_PERMISSION_LINES:
                break
            if line and line not in ICON_LINES and not line.startswith("If "):
                permissions.append(line)
    return dedupe(permissions)


def dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


async def detail_links(page: Page) -> list[str]:
    links = await page.eval_on_selector_all(
        'a[href*="connections/details/"]',
        """els => els.map(a => a.href).filter(Boolean)""",
    )
    return dedupe([str(link) for link in links])


async def page_links(page: Page) -> list[dict[str, str]]:
    return await page.eval_on_selector_all(
        "a[href]",
        """els => els.map(a => ({ text: a.innerText || "", href: a.href || "" }))""",
    )


def urls_from_links(links: list[dict[str, str]]) -> list[str]:
    urls: list[str] = []
    for link in links:
        text = clean_text(link.get("text") or "")
        href = link.get("href") or ""
        if text == "Visit app on Google Play":
            urls.append(href)
        if "report_suspicious_web_app" in href:
            ctx = parse_qs(urlparse(href).query).get("ctx", [""])[0]
            if ctx:
                urls.append(ctx)
    return [normalize_url(url) for url in urls if normalize_url(url)]


async def scrape_connection(
    browser: Browser,
    connection: Connection,
    tz_name: str,
    now: dt.datetime,
    settle_ms: int,
) -> dict[str, str]:
    page = await google_page(browser)
    try:
        overview = await goto(page, connection.overview_url, settle_ms)
        try:
            await page.wait_for_selector('a[href*="connections/details/"]', timeout=5000)
        except PlaywrightTimeoutError:
            pass
        links = await detail_links(page)
        if not links:
            overview_lines = [clean_text(line) for line in overview.splitlines() if clean_text(line)]
            return {"url": "", "app": connection.app, "time": "", "permissions": ";".join(detail_permissions(overview_lines, connection.app, "")), "id": connection.id}
        urls: list[str] = []
        times: list[dt.datetime] = []
        permissions: list[str] = []
        for link in links:
            text = await goto(page, link, settle_ms)
            lines = [clean_text(line) for line in text.splitlines() if clean_text(line)]
            if url := normalize_url(first_line_after(lines, ["Access given to:", "Web address:"])):
                urls.append(url)
            urls.extend(urls_from_links(await page_links(page)))
            if parsed := parse_access_time(first_line_after(lines, ["Access given on:", "Linked on:"]), tz_name, now):
                times.append(parsed)
            permissions.extend(detail_permissions(lines, connection.app, link))
        return {
            "url": sorted(dedupe(urls))[0] if urls else "",
            "app": connection.app,
            "time": format_time(min(times) if times else None),
            "permissions": ";".join(dedupe(permissions)),
            "id": connection.id,
        }
    finally:
        await page.close()


async def scrape_all(cdp_url: str, limit: int, parallel: int, settle_ms: int) -> tuple[list[dict[str, str]], dict[str, Any]]:
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(cdp_url)
        page = await google_page(browser)
        try:
            connections, expected_total, tz_name = await list_connections(page, settle_ms)
        finally:
            await page.close()
        if limit:
            connections = connections[:limit]
        eprint(f"found {len(connections)} app links" + (f" ({expected_total} total apps on page)" if expected_total is not None else ""))
        now = dt.datetime.now(ZoneInfo(tz_name))
        semaphore = asyncio.Semaphore(parallel)
        done = 0

        async def worker(connection: Connection) -> dict[str, str]:
            nonlocal done
            async with semaphore:
                row = await scrape_connection(browser, connection, tz_name, now, settle_ms)
                if not row["url"] and not row["time"] and not row["permissions"]:
                    eprint(f"retrying empty row: {connection.app}")
                    row = await scrape_connection(browser, connection, tz_name, now, settle_ms * 2)
                done += 1
                eprint(f"{done}/{len(connections)} {connection.app}")
                return row

        rows = await asyncio.gather(*(worker(connection) for connection in connections))
        await browser.close()
    rows = sorted(rows, key=lambda row: (row["url"], row["app"], row["id"]))
    stats = {
        "rows": len(rows),
        "expected_total": expected_total,
        "browser_time_zone": tz_name,
        "missing_url": sum(1 for row in rows if not row["url"]),
        "missing_time": sum(1 for row in rows if not row["time"]),
        "missing_permissions": sum(1 for row in rows if not row["permissions"]),
    }
    return rows, stats


def emit_rows(rows: list[dict[str, str]], format: str) -> None:
    if format == "jsonl":
        for row in rows:
            print(compact_json(row))
        return
    dialect = "excel-tab" if format == "tsv" else "excel"
    out = StringIO()
    writer = csv.DictWriter(out, fieldnames=COLUMNS, dialect=dialect, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    print(out.getvalue(), end="")


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    describe_schema: bool = typer.Option(False, "--describe", help="Print machine-readable CLI metadata and exit."),
    format: str = typer.Option("tsv", "--format", help="Output format: tsv, csv, or jsonl."),
    limit: int = typer.Option(0, "--limit", "-n", min=0, help="Maximum apps to scrape. 0 means all."),
    parallel: int = typer.Option(4, "--parallel", min=1, max=8, help="Number of app detail tabs to load in parallel."),
    cdp_url: str = typer.Option(CDP_URL, "--cdp-url", help="Chrome DevTools Protocol URL."),
    settle_ms: int = typer.Option(1200, "--settle-ms", help="Delay after each navigation, in milliseconds."),
    stats: bool = typer.Option(False, "--stats", help="Print scrape summary JSON to stderr after rows."),
) -> None:
    if describe_schema:
        print(compact_json(describe()))
        raise typer.Exit()
    if ctx.invoked_subcommand is not None:
        return
    if format not in {"tsv", "csv", "jsonl"}:
        raise typer.BadParameter("--format must be tsv, csv, or jsonl")
    try:
        rows, summary = asyncio.run(scrape_all(cdp_url, limit, parallel, settle_ms))
    except Exception as exc:
        typer.echo(f"googleconnections.py: {exc}", err=True)
        raise typer.Exit(1) from exc
    emit_rows(rows, format)
    if stats:
        eprint(compact_json(summary))
    if summary["expected_total"] is not None and not limit and summary["rows"] != summary["expected_total"]:
        eprint(f"warning: scraped {summary['rows']} rows but Google summary says {summary['expected_total']} total apps")


if __name__ == "__main__":
    app()
