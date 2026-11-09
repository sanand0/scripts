#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "click>=8.2",
#   "lxml>=6",
#   "markdownify>=1.2",
#   "playwright>=1.54",
# ]
# ///
"""Fetch a LinkedIn profile with the session from an existing CDP browser."""

from __future__ import annotations

import asyncio
import copy
import gzip
import hashlib
import json
import os
import re
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import NamedTuple
from urllib.parse import parse_qsl, quote, unquote, urlparse, urlunsplit

import click
from lxml import etree, html
from lxml.html import HtmlElement
from markdownify import markdownify
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import async_playwright

DEFAULT_CACHE_DIR = Path("~/.cache/sanand-scripts/linkedin-cli").expanduser()
DESCRIPTION = {
    "command": "profile",
    "description": "Render one LinkedIn profile in a logged-in CDP browser.",
    "arguments": {
        "profile": "<vanity> or https://www.linkedin.com/in/<vanity>/"
    },
    "options": {
        "--cdp": "CDP endpoint; default http://localhost:9222",
        "--cache-dir": f"Cache root; default {DEFAULT_CACHE_DIR}",
        "--cache-days": "Maximum cache age in days; default 30",
        "--refresh": "Ignore cached records and replace them",
        "--format": ["markdown", "json"],
        "--output": "Write output to a file instead of stdout",
        "--wait": "Seconds allowed for LinkedIn to hydrate each page; default 3",
    },
    "network_requests": {
        "default": "3 browser page navigations",
        "offline": 0,
        "pages": ["profile", "experience", "education"],
    },
    "output_formats": ["markdown", "json"],
}


class ProfileResult(NamedTuple):
    profile_url: str
    fetched_at: str
    request_count: int
    markdown: str
    sections: dict[str, str]


def log(message: str) -> None:
    click.echo(message, err=True)


def cache_url(url: str) -> str:
    parsed = urlparse(url)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ""))


def cache_path(cache_dir: Path, url: str) -> Path:
    """Map any URL to a readable, deterministic cache path."""
    url = cache_url(url)
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"cannot cache invalid URL: {url}")
    segments = [
        quote(unquote(segment), safe="-._~")
        for segment in parsed.path.split("/")
        if segment
    ]
    directory = cache_dir / "urls" / parsed.netloc.lower() / Path(*segments)
    filename = "index"
    if parsed.query:
        readable = "_".join(
            f"{key}-{value}"
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        )
        readable = re.sub(r"[^A-Za-z0-9._~-]+", "-", readable).strip("-")[:80]
        digest = hashlib.sha256(parsed.query.encode()).hexdigest()[:12]
        filename += f"__q_{readable or 'query'}__{digest}"
    return directory / f"{filename}.json.gz"


def write_cache(cache_dir: Path, record: dict[str, object]) -> Path:
    """Atomically save one compressed raw-response/DOM record."""
    record = {**record, "url": cache_url(str(record["url"]))}
    path = cache_path(cache_dir, str(record["url"]))
    cache_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(cache_dir, 0o700)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
        temp_path = Path(temporary.name)
    try:
        with gzip.open(temp_path, "wt", encoding="utf-8") as file:
            json.dump(record, file, ensure_ascii=False)
        os.chmod(temp_path, 0o600)
        temp_path.replace(path)
    finally:
        temp_path.unlink(missing_ok=True)
    return path


def read_cache(
    cache_dir: Path,
    url: str,
    cache_days: float,
    *,
    refresh: bool = False,
    now: datetime | None = None,
) -> dict[str, object] | None:
    """Return a fresh matching record, treating invalid records as misses."""
    if refresh or cache_days <= 0:
        return None
    url = cache_url(url)
    try:
        with gzip.open(cache_path(cache_dir, url), "rt", encoding="utf-8") as file:
            record = json.load(file)
        fetched_at = datetime.fromisoformat(record["fetched_at"])
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=UTC)
        if (now or datetime.now(UTC)) - fetched_at > timedelta(days=cache_days):
            return None
        if cache_url(str(record["url"])) != url or not isinstance(
            record.get("dom"), str
        ):
            return None
        return record
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return None


def visible_text(element: HtmlElement) -> str:
    return "\n".join(
        line.strip() for line in element.text_content().splitlines() if line.strip()
    )


def parse_document(source: str) -> HtmlElement:
    document = html.fromstring(source)
    if not document.xpath("//main"):
        raise ValueError(
            "LinkedIn profile content was not found (session may be logged out)"
        )
    return document


def _find_section(document: HtmlElement, label: str) -> HtmlElement | None:
    sections = []
    for section in document.xpath("//main//section"):
        text = visible_text(section)
        has_label = any(
            visible_text(element) == label for element in section.xpath(".//*")
        )
        if has_label and not text.startswith("More profiles for you"):
            sections.append(section)
    return (
        min(sections, key=lambda section: len(visible_text(section)))
        if sections
        else None
    )


def extract_detail_section(source: str, label: str) -> HtmlElement | None:
    section = _find_section(parse_document(source), label)
    return copy.deepcopy(section) if section is not None else None


def _drop_noise(element: HtmlElement) -> None:
    for node in element.xpath(".//button | .//svg | .//img"):
        node.drop_tree()
    for link in element.xpath(".//a"):
        if visible_text(link) in {"Connect", "Follow", "Message"}:
            link.drop_tree()
    for nested_link in element.xpath(".//a//a"):
        nested_link.drop_tag()


def _markdown(element: HtmlElement) -> str:
    _drop_noise(element)
    result = markdownify(
        etree.tostring(element, encoding="unicode"),
        heading_style="ATX",
        strip=["picture"],
    )
    result = re.sub(r"[ \t]+\n", "\n", result)
    result = re.sub(
        r"(?m)^[·•]\s+(?![123](?:st|nd|rd)\b|\[?Contact info)", "- ", result
    )
    result = re.sub(r"\)\[", ")\n\n[", result)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


def _profile_markdown(source: str) -> dict[str, str]:
    document = parse_document(source)
    title = "".join(document.xpath("//title[1]/text()")).removesuffix(" | LinkedIn")
    if not title:
        raise ValueError("LinkedIn profile name was not found")
    top = _find_section(document, title)
    if top is None:
        raise ValueError("LinkedIn top card was not found")
    top = copy.deepcopy(top)
    top_markdown = _markdown(top)
    top_markdown = re.sub(
        rf"^\[## {re.escape(title)}\]\([^)]+\)", f"# {title}", top_markdown
    )
    top_markdown = re.sub(rf"(?m)^## {re.escape(title)}$", f"# {title}", top_markdown)
    top_markdown = re.sub(r"\n\n·\n", "\n", top_markdown)
    top_markdown = re.sub(r"(?m)^·\s+(?=\[Contact info\])", "", top_markdown)
    top_markdown = re.sub(r"(?m)^(?:·|-)\s*\n+(?=\[Contact info\])", "", top_markdown)
    degrees = re.findall(r"(?m)^· (?:1st|2nd|3rd\+?)$", top_markdown)
    if len(degrees) > 1:
        for degree in degrees[:-1]:
            top_markdown = top_markdown.replace(f"\n\n{degree}", "", 1)
    sections = {"profile": top_markdown}
    about = _find_section(document, "About")
    if about is not None:
        about_markdown = _markdown(copy.deepcopy(about))
        sections["about"] = re.sub(r"^About\b", "## About", about_markdown)
    return sections


def render_profile(
    pages: dict[str, str], profile_url: str, request_count: int
) -> ProfileResult:
    sections = _profile_markdown(pages["profile"])
    for key, label in (("experience", "Experience"), ("education", "Education")):
        section = extract_detail_section(pages[key], label)
        if section is None:
            continue
        body = _markdown(section)
        body = re.sub(rf"^{label}\b", f"## {label}", body)
        sections[key] = body
    markdown = "\n\n".join(sections.values()).strip() + "\n"
    return ProfileResult(
        profile_url=profile_url,
        fetched_at=datetime.now(UTC).isoformat(),
        request_count=request_count,
        markdown=markdown,
        sections=sections,
    )


def normalize_profile_url(value: str) -> str:
    value = value.strip()
    if "://" not in value:
        if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?", value):
            raise click.BadParameter(
                "vanity must contain only letters, numbers, and hyphens"
            )
        return f"https://www.linkedin.com/in/{value}/"
    parsed = urlparse(value)
    parts = [part for part in parsed.path.split("/") if part]
    if (
        parsed.scheme != "https"
        or parsed.hostname not in {"linkedin.com", "www.linkedin.com"}
        or len(parts) < 2
        or parts[0] != "in"
    ):
        raise click.BadParameter("expected https://www.linkedin.com/in/<vanity>/")
    return f"https://www.linkedin.com/in/{parts[1]}/"


async def fetch_profile(
    profile_url: str,
    cdp: str,
    wait: float,
    cache_dir: Path,
    cache_days: float,
    refresh: bool,
) -> ProfileResult:
    urls = {
        "profile": profile_url,
        "experience": f"{profile_url}details/experience/",
        "education": f"{profile_url}details/education/",
    }
    pages: dict[str, str] = {}
    missing: list[tuple[str, str]] = []
    for index, (name, url) in enumerate(urls.items(), start=1):
        record = read_cache(cache_dir, url, cache_days, refresh=refresh)
        if record is None:
            missing.append((name, url))
        else:
            log(f"CACHE {index}/3 {name}: {cache_path(cache_dir, url)}")
            pages[name] = str(record["dom"])

    if missing:
        log(f"Connecting to the logged-in browser at {cdp}")
        async with async_playwright() as playwright:
            browser = await playwright.chromium.connect_over_cdp(cdp)
            page = await browser.contexts[0].new_page()
            try:
                for name, url in missing:
                    index = list(urls).index(name) + 1
                    log(f"GET {index}/3 {name}: {url}")
                    response = await page.goto(url, wait_until="domcontentloaded")
                    if response is None or not response.ok:
                        status = response.status if response else "no response"
                        raise RuntimeError(f"LinkedIn returned {status} for {url}")
                    await page.wait_for_timeout(wait * 1_000)
                    if "/login" in page.url or not await page.locator("main").count():
                        raise RuntimeError(
                            "LinkedIn did not return an authenticated profile page: "
                            f"{page.url}"
                        )
                    dom = await page.content()
                    try:
                        response_body = await response.text()
                        response_error = None
                    except PlaywrightError as error:
                        response_body = None
                        response_error = str(error)
                    headers = await response.all_headers()
                    record: dict[str, object] = {
                        "schema_version": 1,
                        "kind": "page",
                        "url": url,
                        "final_url": page.url,
                        "fetched_at": datetime.now(UTC).isoformat(),
                        "status": response.status,
                        "content_type": headers.get("content-type"),
                        "response_body": response_body,
                        "dom": dom,
                        "title": await page.title(),
                    }
                    if response_error:
                        record["response_body_error"] = response_error
                    write_cache(cache_dir, record)
                    pages[name] = dom
            finally:
                await page.close()
    return render_profile(pages, profile_url, request_count=len(missing))


def serialize(result: ProfileResult, output_format: str) -> str:
    if output_format == "markdown":
        return result.markdown
    return (
        json.dumps(
            {
                "ok": True,
                "schema_version": "1",
                "data": {
                    "profile_url": result.profile_url,
                    "fetched_at": result.fetched_at,
                    "request_count": result.request_count,
                    "sections": result.sections,
                    "markdown": result.markdown,
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
def cli() -> None:
    """Read LinkedIn using the logged-in session in a CDP browser."""


@cli.command()
@click.argument("profile_url", required=False)
@click.option("--cdp", default="http://localhost:9222", show_default=True)
@click.option(
    "--cache-dir",
    type=click.Path(path_type=Path, file_okay=False),
    default=DEFAULT_CACHE_DIR,
    envvar="LINKEDIN_CACHE_DIR",
    show_default=True,
)
@click.option(
    "--cache-days",
    type=click.FloatRange(min=0),
    default=30.0,
    show_default=True,
    help="Maximum cache age in days; 0 always fetches.",
)
@click.option("--refresh", is_flag=True, help="Ignore and replace cached records.")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["markdown", "json"]),
    default="markdown",
    show_default=True,
)
@click.option("--output", type=click.Path(path_type=Path, dir_okay=False))
@click.option(
    "--wait",
    type=click.FloatRange(min=0),
    default=3.0,
    show_default=True,
    help="Seconds to wait for LinkedIn to hydrate each page.",
)
@click.option("--describe", is_flag=True, help="Print the machine-readable interface.")
def profile(
    profile_url: str | None,
    cdp: str,
    cache_dir: Path,
    cache_days: float,
    refresh: bool,
    output_format: str,
    output: Path | None,
    wait: float,
    describe: bool,
) -> None:
    """Fetch PROFILE_URL and print its profile, experience, and education."""
    if describe:
        click.echo(json.dumps(DESCRIPTION, indent=2))
        return
    if not profile_url:
        raise click.UsageError("Missing argument PROFILE_URL")
    url = normalize_profile_url(profile_url)
    try:
        result = asyncio.run(
            fetch_profile(
                url,
                cdp,
                wait,
                cache_dir.expanduser(),
                cache_days,
                refresh,
            )
        )
    except Exception as error:
        raise click.ClickException(str(error)) from error
    rendered = serialize(result, output_format)
    if output:
        output.write_text(rendered)
        log(f"Wrote {output}")
    else:
        click.echo(rendered, nl=False)


if __name__ == "__main__":
    cli()
