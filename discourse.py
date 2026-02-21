#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "httpx>=0.27.0",
#     "python-dateutil>=2.9.0",
#     "lxml>=5.3.0",
#     "typer>=0.12.3",
#     "tenacity>=8.5.0",
#     "python-dotenv>=1.0.1",
#     "markdownify>=0.13.1",
# ]
# ///

"""
Usage:

discourse.py --host https://discourse.onlinedegree.iitm.ac.in --category-id 34 --since $(date -d '7 days ago' +%F)

Prints Markdown summaries of all posts in category 34 created/edited since 7 days ago.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Generator, Iterable, List, Tuple
from urllib.parse import urljoin
import os
import time
import typer

from httpx import Client, Timeout, HTTPStatusError
from dateutil import parser as dt_parser
from lxml import html
from markdownify import markdownify as md
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from dotenv import load_dotenv

app = typer.Typer(add_completion=False)


def parse_dt(value: str) -> datetime:
    parsed = dt_parser.isoparse(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def http_client(host: str) -> Client:
    api_key = os.environ["DISCOURSE_API_KEY"]
    api_user = os.environ["DISCOURSE_API_USERNAME"]
    headers = {"Api-Key": api_key, "Api-Username": api_user, "Accept": "application/json"}
    return Client(base_url=host, headers=headers, timeout=Timeout(15.0), follow_redirects=True)


@retry(
    stop=stop_after_attempt(6),
    wait=wait_exponential(multiplier=1, min=0.5, max=8),
    retry=retry_if_exception_type(HTTPStatusError),
)
def get_json(client: Client, url: str) -> dict:
    resp = client.get(url)
    if resp.status_code == 429:
        retry_after = resp.headers.get("Retry-After")
        if retry_after:
            try:
                wait_seconds = float(retry_after)
            except ValueError:
                wait_seconds = 0
            if wait_seconds > 0:
                time.sleep(wait_seconds)
        resp.raise_for_status()
    resp.raise_for_status()
    return resp.json()


def fetch_topic_pages(client: Client, category_id: int) -> Iterable[dict]:
    url = f"/c/{category_id}.json"
    while url:
        data = get_json(client, url)
        topics = data.get("topic_list", {}).get("topics", [])
        for topic in topics:
            yield topic
        more = data.get("topic_list", {}).get("more_topics_url")
        url = more if more else None


def simplify_html(host: str, cooked: str) -> Tuple[str, List[Tuple[str, str]]]:
    if not cooked:
        return "", []
    tree = html.fromstring(cooked)
    images: List[Tuple[str, str]] = []
    for img in tree.xpath("//img"):
        alt = (img.get("alt") or "").strip() or "image"
        src = img.get("src") or ""
        images.append((alt, urljoin(host + "/", src)))
    markdown = md(
        cooked,
        heading_style="ATX",
        bullets="-",
        escape_asterisks=False,
        escape_underscores=False,
        strip=["script", "style"],
    )
    compact = " ".join(markdown.split())
    return compact, images


def format_reactions(reactions: List[dict]) -> str:
    parts = []
    for entry in reactions:
        count = entry.get("count", 0)
        if not count:
            continue
        name = entry.get("reaction") or entry.get("name") or f"id{entry.get('id')}"
        parts.append(f"{name}={count}")
    return ", ".join(parts)


def format_post_line(label: str, post: dict, content: str, images: List[Tuple[str, str]]) -> str:
    created = iso(parse_dt(post["created_at"]))
    author = post.get("username") or post.get("name") or "unknown"
    parts = [
        f"{label} {created} @{author} #{post.get('post_number')}: {content}",
    ]
    if images:
        rendered = []
        for alt, src in images:
            rendered.append(f"{alt}->{src}")
        parts.append("images: " + "; ".join(rendered))
    reactions = format_reactions(post.get("actions_summary", []))
    if reactions:
        parts.append(f"reactions: {reactions}")
    return " | ".join(parts)


def format_topic_block(host: str, topic: dict, op_post: dict, posts: List[dict]) -> str:
    slug = topic.get("slug") or str(topic["id"])
    topic_url = f"{host}/t/{slug}/{topic['id']}"
    header = f"## {topic['title']} ({topic['id']})"
    lines = [header, "", f"link: {topic_url}"]
    op_content, op_images = simplify_html(host, op_post.get("cooked", ""))
    lines.append(f"- {format_post_line('OP', op_post, op_content, op_images)}")
    for post in posts:
        content, images = simplify_html(host, post.get("cooked", ""))
        lines.append(f"- {format_post_line('P', post, content, images)}")
    lines.append("")
    return "\n".join(lines)


def collect_topic_posts(
    client: Client, topic: dict, since: datetime | None
) -> Tuple[dict, List[dict]]:
    detail = get_json(client, f"/t/{topic['id']}.json")
    posts = detail.get("post_stream", {}).get("posts", [])
    if not posts:
        return {}, []
    op_post = posts[0]
    tail = posts[1:]
    if since is None:
        return op_post, tail
    recent = [p for p in tail if parse_dt(p["created_at"]) >= since]
    return op_post, recent


def stream_markdown(host: str, category_id: int, since: datetime) -> Generator[str, None, None]:
    with http_client(host) as client:
        old_hits = 0
        for topic in fetch_topic_pages(client, category_id):
            last_posted = topic.get("last_posted_at")
            if not last_posted:
                continue
            if parse_dt(last_posted) < since:
                old_hits += 1
                if old_hits >= 60:
                    break
                continue
            old_hits = 0
            op_post, posts = collect_topic_posts(client, topic, since)
            if not posts:
                continue
            yield format_topic_block(host, topic, op_post, posts) + "\n"


@app.command()
def main(
    host: str = typer.Option(..., help="e.g. https://discourse.onlinedegree.iitm.ac.in"),
    category_id: int = typer.Option(None, help="e.g. 34"),
    topic_id: int = typer.Option(None, help="e.g. 12345"),
    since: str = typer.Option(..., help="ISO8601 timestamp (UTC), e.g. 2025-01-31"),
) -> None:
    load_dotenv()
    if not category_id and not topic_id:
        raise typer.BadParameter("Provide --category-id or --topic-id")
    if category_id and topic_id:
        raise typer.BadParameter("Choose only one of --category-id or --topic-id")
    clean_host = host.rstrip("/")
    since_dt = parse_dt(since)
    emitted = False
    if topic_id:
        with http_client(clean_host) as client:
            topic = get_json(client, f"/t/{topic_id}.json")
            op_post, posts = collect_topic_posts(client, topic, None)
            if posts:
                print(format_topic_block(clean_host, topic, op_post, posts))
                emitted = True
    else:
        for block in stream_markdown(clean_host, category_id, since_dt):
            print(block, end="")
            emitted = True
    if not emitted:
        print(f"No posts after {iso(since_dt)}.")


if __name__ == "__main__":
    app()
