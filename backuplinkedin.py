#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["playwright>=1.52", "typer>=0.12"]
# ///
"""Back up LinkedIn data that the standard export misses via CDP.

Examples:
  backup_linkedin.py posts --username sanand0 --limit 5
  backup_linkedin.py posts --username sanand0 --limit 100 --format jsonl | moor
  backup_linkedin.py posts --username sanand0 --limit 0 --max-scrolls 1000
  backup_linkedin.py posts --username sanand0 --no-comments --dry-run
  backup_linkedin.py --describe | jaq .
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import typer
from playwright.async_api import Browser, ElementHandle, Page, async_playwright

import sanand_observability as obs

app = typer.Typer(add_completion=False, help=__doc__)

CDP_URL = "http://localhost:9222"
OUT_PATH = Path("/home/sanand/Documents/data/linkedin-posts.jsonl")
POST_SELECTOR = '[data-urn][role="article"], .feed-shared-update-v2[data-urn]'


def eprint(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def parse_count(value: str) -> int | None:
    text = re.sub(r"\s+", " ", value or "").strip().lower().replace(",", "")
    match = re.search(r"(\d+(?:\.\d+)?)\s*([kmb])?", text)
    if not match:
        return None
    scale = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}.get(match.group(2) or "", 1)
    return int(float(match.group(1)) * scale)


def parse_relative_time(value: str, scraped_at: dt.datetime) -> tuple[str, str]:
    text = re.sub(r"\s+", " ", value or "").strip().lower()
    text = text.replace("• edited", "").replace("edited •", "").strip(" •")
    if not text:
        return "", "missing"
    if match := re.search(r"\b(\d+)\s*(min|m|hour|hr|h|day|d|week|w|month|mo|year|yr|y)s?\b", text):
        amount = int(match.group(1))
        unit = match.group(2)
        days = {"week": 7, "w": 7, "month": 30, "mo": 30, "year": 365, "yr": 365, "y": 365}
        if unit in {"min", "m"}:
            delta = dt.timedelta(minutes=amount)
        elif unit in {"hour", "hr", "h"}:
            delta = dt.timedelta(hours=amount)
        elif unit in {"day", "d"}:
            delta = dt.timedelta(days=amount)
        else:
            delta = dt.timedelta(days=amount * days[unit])
        return (scraped_at - delta).isoformat(), "relative"
    if "yesterday" in text:
        return (scraped_at - dt.timedelta(days=1)).isoformat(), "relative"
    return "", "unparsed"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{time.time_ns()}.tmp")
    tmp.write_text("".join(compact_json(row) + "\n" for row in rows))
    tmp.replace(path)


def row_key(row: dict[str, Any]) -> str:
    return f"{row.get('type', 'row')}:{row.get('id') or row.get('url') or compact_json(row)[:160]}"


def richness(value: Any) -> int:
    if value in (None, "", [], {}, False):
        return 0
    if isinstance(value, str):
        return len(value)
    if isinstance(value, (list, dict)):
        return len(value)
    return 1


def merge_row(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    merged = dict(old)
    for key, value in new.items():
        if key == "scrapedAt" or richness(value) >= richness(merged.get(key)):
            merged[key] = value
    return merged


def sort_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (str(row.get("postedAt") or row.get("commentedAt") or ""), str(row.get("type") or ""), str(row.get("id") or ""))


def update_jsonl(path: Path, rows: list[dict[str, Any]]) -> int:
    existing = {row_key(row): row for row in load_jsonl(path)}
    changed = 0
    for row in rows:
        key = row_key(row)
        merged = merge_row(existing.get(key, {}), row)
        if existing.get(key) != merged:
            changed += 1
        existing[key] = merged
    write_jsonl(path, sorted(existing.values(), key=sort_key, reverse=True))
    return changed


def add_time_fields(row: dict[str, Any], scraped_at: dt.datetime) -> dict[str, Any]:
    if row["type"] == "post":
        when, confidence = parse_relative_time(row.get("postedText", ""), scraped_at)
        row["postedAt"] = when
        row["postedAtConfidence"] = confidence
    else:
        when, confidence = parse_relative_time(row.get("commentedText", ""), scraped_at)
        row["commentedAt"] = when
        row["commentedAtConfidence"] = confidence
    row["scrapedAt"] = scraped_at.isoformat()
    return row


def describe() -> dict[str, Any]:
    return {
        "name": "backup_linkedin.py",
        "cdp": CDP_URL,
        "commands": ["posts"],
        "output": str(OUT_PATH),
        "primary_key": "type:id",
        "examples": [
            "backup_linkedin.py posts --username sanand0",
            "backup_linkedin.py posts --username sanand0 --limit 100 --format jsonl",
            "backup_linkedin.py posts --username sanand0 --limit 0 --max-scrolls 1000",
            "backup_linkedin.py posts --username sanand0 --no-comments --dry-run",
        ],
    }


async def linkedin_page(browser: Browser) -> Page:
    for context in browser.contexts:
        for page in context.pages:
            if "linkedin.com" in page.url:
                await page.bring_to_front()
                return page
    if browser.contexts:
        return await browser.contexts[0].new_page()
    raise RuntimeError("No CDP browser context found. Start Chrome/Edge with remote debugging on port 9222.")


async def navigate_posts(page: Page, username: str) -> None:
    await page.goto(f"https://www.linkedin.com/in/{username}/recent-activity/all/", wait_until="domcontentloaded", timeout=45000)
    await page.wait_for_timeout(3500)
    if "login" in page.url or "Sign in" in await page.title():
        raise RuntimeError("LinkedIn is not authenticated in the CDP browser. Log in manually, then rerun.")
    await page.wait_for_selector(POST_SELECTOR, timeout=20000)


async def click_all(handles: list[ElementHandle], label: str, settle_ms: int) -> int:
    clicked = 0
    for handle in handles:
        try:
            await handle.evaluate("(el) => el.scrollIntoView({ block: 'center', inline: 'nearest' })")
            await handle.click(timeout=800, force=True, no_wait_after=True)
            clicked += 1
            await asyncio.sleep(settle_ms / 1000)
        except Exception as exc:
            try:
                await handle.evaluate(
                    """(el) => {
                      el.scrollIntoView({ block: "center", inline: "nearest" });
                      for (const type of ["pointerdown", "mousedown", "pointerup", "mouseup", "click"]) {
                        el.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: window }));
                      }
                    }"""
                )
                clicked += 1
                await asyncio.sleep(settle_ms / 1000)
            except Exception as fallback_exc:
                eprint(f"warning: could not click {label}: {exc}; fallback: {fallback_exc}")
    return clicked


async def expand_text(post: ElementHandle, settle_ms: int) -> None:
    handles = await post.query_selector_all(
        'button[aria-label^="see more"], button[aria-label*="visually reveals content"], '
        'button.see-more, button:has-text("… more"), button:has-text("... more"), '
        '.feed-shared-inline-show-more-text__see-more-less-toggle'
    )
    await click_all(handles[:12], "see-more", settle_ms)


async def open_comments(post: ElementHandle, settle_ms: int) -> None:
    buttons = await post.query_selector_all('button[aria-label="Comment"], button.comment-button, [aria-label*="comments on"]')
    await click_all(buttons[:2], "comments", settle_ms)


async def load_all_comments(post: ElementHandle, max_rounds: int, settle_ms: int) -> dict[str, int]:
    stats = {"loadMoreClicks": 0, "replyClicks": 0, "staleRounds": 0}
    previous = -1
    for _ in range(max_rounds):
        await expand_text(post, settle_ms)
        comments = await post.query_selector_all('article.comments-comment-entity[data-id]')
        load_buttons = await post.query_selector_all(
            'button:has-text("Load more comments"), button:has-text("Show more comments"), '
            'button:has-text("See previous comments"), button:has-text("Load previous comments"), '
            '[role="button"]:has-text("Load more comments"), [role="button"]:has-text("Show more comments"), '
            '[role="button"]:has-text("See previous comments"), [role="button"]:has-text("Load previous comments")'
        )
        reply_buttons = await post.query_selector_all(
            'button:has-text("See previous replies"), button:has-text("Load more replies"), button:has-text("Show replies"), '
            '[role="button"]:has-text("See previous replies"), [role="button"]:has-text("Load more replies"), [role="button"]:has-text("Show replies")'
        )
        stats["loadMoreClicks"] += await click_all(load_buttons[:3], "load-more-comments", settle_ms)
        stats["replyClicks"] += await click_all(reply_buttons[:5], "load-more-replies", settle_ms)
        count = len(comments)
        remaining_buttons = len(load_buttons) + len(reply_buttons)
        if count == previous:
            stats["staleRounds"] += 1
        else:
            stats["staleRounds"] = 0
        if not remaining_buttons and stats["staleRounds"] >= 2:
            break
        if remaining_buttons and stats["staleRounds"] >= 3:
            eprint("warning: comment loader buttons remain visible but no new comment rows appeared; moving on")
            break
        previous = count
    return stats


EXTRACT_JS = r"""
(post, { scrapedAt }) => {
  const text = (el) => (el?.innerText || el?.textContent || "").replace(/\s+\n/g, "\n").replace(/[ \t]+/g, " ").trim();
  const cleanUrl = (url) => {
    try {
      const value = new URL(url, location.href);
      value.hash = "";
      return value.href;
    } catch {
      return url || "";
    }
  };
  const number = (value) => {
    const match = String(value || "").replace(/,/g, "").match(/(\d+(?:\.\d+)?)\s*([kmb])?/i);
    if (!match) return null;
    const scale = { k: 1e3, m: 1e6, b: 1e9 }[(match[2] || "").toLowerCase()] || 1;
    return Math.round(Number(match[1]) * scale);
  };
  const miniProfileUrn = (link) => {
    if (!link?.href) return "";
    try {
      return new URL(link.href, location.href).searchParams.get("miniProfileUrn") || "";
    } catch {
      return "";
    }
  };
  const badgesFrom = (value) => {
    const badges = [];
    if (/\bverified\b/i.test(value || "")) badges.push("verified");
    if (/\bpremium\b/i.test(value || "")) badges.push("premium");
    return [...new Set(badges)];
  };
  const degreeFrom = (value) => {
    const match = String(value || "").match(/\b(1st|2nd|3rd\+?)\b/i);
    return match ? match[1] : "";
  };
  const first = (root, selectors) => selectors.map((s) => root.querySelector(s)).find(Boolean) || null;
  const all = (root, selectors) => [...new Set(selectors.flatMap((s) => [...root.querySelectorAll(s)]))];
  const ariaText = (root) => all(root, ['[aria-label]']).map((el) => el.getAttribute("aria-label") || "").join(" ");
  const visibleText = (root, selectors) => text(first(root, selectors.map((s) => `${s} [aria-hidden="true"]`)) || first(root, selectors));
  const urn = post.getAttribute("data-urn") || "";
  const lines = text(post).split("\n").map((line) => line.trim()).filter(Boolean);
  const profile = first(post, ['a[href*="/in/"]']);
  const authorName = visibleText(post, ['.update-components-actor__name', '.feed-shared-actor__name', 'span.update-components-actor__title']) || lines[1] || "";
  const headline = visibleText(post, ['.update-components-actor__description', '.feed-shared-actor__description']);
  const commentary = text(first(post, ['.update-components-update-v2__commentary', '.feed-shared-update-v2__description-wrapper', '.feed-shared-inline-show-more-text']));
  const ageEl = first(post, ['.update-components-actor__sub-description span[aria-hidden="true"]', '.feed-shared-actor__sub-description span[aria-hidden="true"]']);
  const ageText = text(ageEl) || (lines.find((line) => /^\d+\s*(m|min|h|hr|d|w|mo|y|yr)\b/i.test(line)) || "");
  const socialText = text(first(post, ['.social-details-social-counts', '.feed-shared-social-counts']));
  const reactionText = text(first(post, ['.social-details-social-counts__reactions-count', '[aria-label*="reactions"], [aria-label*="others"]']));
  const commentText = (socialText.match(/[\d,.]+\s+comments?/i) || [""])[0];
  const repostText = (socialText.match(/[\d,.]+\s+reposts?/i) || [""])[0];
  const impressionText = (text(post).match(/[\d,.]+\s+impressions?/i) || [""])[0];
  const analytics = first(post, ['a.analytics-entry-point[href]', 'a[href*="/analytics/post-summary/"]']);
  const actor = first(post, ['.update-components-actor', '.feed-shared-actor']);
  const actorText = `${text(actor)} ${ariaText(actor || post)} ${lines.slice(0, 8).join(" ")}`;
  const reactionTypesVisible = [...new Set(all(post, [
    '.social-details-social-counts img[alt]',
    '.feed-shared-social-counts img[alt]',
    '.social-detail-social-counts__count-icon[alt]',
    '.reactions-icon[alt]',
  ]).map((img) => (img.alt || "").trim().toLowerCase()).filter((alt) => alt && !/profile|photo|graphic/i.test(alt)))];
  const links = all(post, ['.update-components-update-v2__commentary a[href]', '.feed-shared-update-v2__description-wrapper a[href]', '.update-components-article a[href]'])
    .map((a) => cleanUrl(a.href))
    .filter((href) => href && !href.includes('/feed/update/') && !href.startsWith('javascript:'));
  const mediaMap = new Map();
  const addMedia = (item) => {
    if (!item.url || item.url.startsWith("data:")) return;
    mediaMap.set(`${item.kind}:${item.url}`, item);
  };
  all(post, ['img[src]']).forEach((img) => {
    if (img.closest('.update-components-actor, .feed-shared-actor, .comments-comment-meta__container')) return;
    if (/profile photo/i.test(img.alt || "")) return;
    const url = cleanUrl(img.src);
    if (/static\.licdn\.com\/aero-v1\/sc\//.test(url) || /profile-displayphoto/.test(url)) return;
    addMedia({ kind: "image", url, alt: img.alt || "" });
  });
  all(post, ['video[src]']).forEach((video) => addMedia({ kind: "video", url: cleanUrl(video.src), poster: cleanUrl(video.poster || "") }));
  all(post, ['iframe[src], object[data], embed[src]']).forEach((el) => addMedia({ kind: "document", url: cleanUrl(el.src || el.data || "") }));
  const media = [...mediaMap.values()];
  const rows = [{
    type: "post",
    id: urn,
    postId: (urn.match(/activity:(\d+)/) || [])[1] || "",
    url: urn ? `https://www.linkedin.com/feed/update/${urn}/` : cleanUrl(location.href),
    authorName,
    authorProfile: profile ? cleanUrl(profile.href).split("?")[0] : "",
    authorMiniProfileUrn: miniProfileUrn(profile),
    authorDescription: headline,
    authorBadges: lines.filter((line) => /verified|premium|you/i.test(line)).slice(0, 6),
    premiumVerifiedBadges: badgesFrom(actorText),
    postedText: ageText,
    edited: /edited/i.test(text(first(post, ['.update-components-actor__sub-description', '.feed-shared-actor__sub-description']))),
    visibility: (lines.find((line) => /visible to/i.test(line)) || ""),
    content: commentary,
    links: [...new Set(links)],
    linkCount: new Set(links).size,
    media,
    mediaCount: media.length,
    analyticsUrl: analytics ? cleanUrl(analytics.href).split("?")[0] : "",
    reactionCount: number(reactionText),
    reactionTypesVisible,
    commentCount: number(commentText),
    repostCount: number(repostText),
    impressionCount: number(impressionText),
    socialText,
    rawText: text(post).slice(0, 20000),
    scrapedAt,
  }];
  const commentArticles = all(post, ['article.comments-comment-entity[data-id]']);
  for (const article of commentArticles) {
    const id = article.getAttribute("data-id") || "";
    const meta = first(article, ['.comments-comment-meta__container']);
    const name = text(first(article, ['.comments-comment-meta__description-title']));
    const profileLink = first(article, ['a.comments-comment-meta__description-container[href*="/in/"], a[href*="/in/"]']);
    const description = text(first(article, ['.comments-comment-meta__description-subtitle']));
    const relation = text(first(article, ['.comments-comment-meta__data']));
    const timeText = text(first(article, ['time.comments-comment-meta__data', 'time', '.comments-comment-meta__info']));
    const content = text(first(article, ['.comments-comment-item__main-content', '.comments-comment-entity__content']));
    const social = text(first(article, ['.comments-comment-social-bar--cr', '.comment-social-activity']));
    const reactionButton = first(article, ['button[aria-label*="Reaction"], .comments-comment-social-bar__reactions-count--cr']);
    const replyButton = first(article, ['button[aria-label^="Reply to"]']);
    const parentArticle = article.parentElement?.closest('article.comments-comment-entity[data-id]');
    const metaText = `${text(meta)} ${ariaText(meta || article)}`;
    const commentReactionTypes = [...new Set(all(article, [
      '.comments-comment-social-bar--cr img[alt]',
      '.comment-social-activity img[alt]',
      '.reactions-icon[alt]',
    ]).map((img) => (img.alt || "").trim().toLowerCase()).filter((alt) => alt && !/profile|photo|graphic/i.test(alt)))];
    rows.push({
      type: "comment",
      id,
      commentId: (id.match(/,(\d+)\)/) || [])[1] || "",
      parentId: urn,
      parentCommentId: parentArticle ? parentArticle.getAttribute("data-id") : "",
      commenterName: name,
      commenterProfile: profileLink ? cleanUrl(profileLink.href).split("?")[0] : "",
      commenterMiniProfileUrn: miniProfileUrn(profileLink),
      commenterDescription: description,
      commenterType: relation,
      commenterDegree: degreeFrom(relation || metaText),
      commenterBadges: metaText.split("\n").filter((line) => /verified|premium/i.test(line)),
      premiumVerifiedBadges: badgesFrom(metaText),
      commentedText: timeText,
      edited: /edited/i.test(text(meta) + " " + text(article)),
      content,
      reactionCount: number(text(reactionButton) || reactionButton?.getAttribute("aria-label")),
      reactionText: reactionButton?.getAttribute("aria-label") || "",
      reactionTypesVisible: commentReactionTypes,
      replyCount: number(text(replyButton) || ""),
      impressionCount: number((text(article).match(/[\d,.]+\s+impressions?/i) || [""])[0]),
      socialText: social,
      rawText: text(article).slice(0, 10000),
      scrapedAt,
    });
  }
  return rows;
}
"""


async def extract_post(post: ElementHandle, scraped_at: dt.datetime) -> list[dict[str, Any]]:
    rows = await post.evaluate(EXTRACT_JS, {"scrapedAt": scraped_at.isoformat()})
    return [add_time_fields(row, scraped_at) for row in rows if row.get("id")]


async def scroll_page(page: Page, settle_ms: int) -> dict[str, Any]:
    data = await page.evaluate(
        """() => {
          const main = document.querySelector("main");
          const scroller = main && main.scrollHeight > main.clientHeight + 100 ? main : document.scrollingElement;
          const before = { top: scroller.scrollTop, height: scroller.scrollHeight, client: scroller.clientHeight };
          scroller.scrollTop += Math.max(600, scroller.clientHeight * 0.85);
          window.dispatchEvent(new Event("scroll"));
          return before;
        }"""
    )
    await page.wait_for_timeout(settle_ms)
    return data


async def scrape_posts(
    cdp_url: str,
    username: str,
    limit: int,
    out_path: Path,
    include_comments: bool,
    max_scrolls: int,
    max_comment_rounds: int,
    settle_ms: int,
    dry_run: bool,
    format: str,
) -> None:
    cache_dir = Path("~/.cache/sanand-scripts/backuplinkedin").expanduser()
    trace = obs.new_run(
        "backuplinkedin",
        cache_dir=cache_dir,
        args=obs.sanitize_args(
            {
                "username": username,
                "limit": limit,
                "out": out_path,
                "comments": include_comments,
                "cdp_url": cdp_url,
                "max_scrolls": max_scrolls,
                "max_comment_rounds": max_comment_rounds,
                "settle_ms": settle_ms,
                "dry_run": dry_run,
                "format": format,
            }
        ),
    )
    rows: list[dict[str, Any]] = []
    processed: set[str] = set()
    changed = 0
    page: Page | None = None
    try:
        async with async_playwright() as p:
            with trace.span("cdp_connection", {"cdp_url": cdp_url}):
                browser = await p.chromium.connect_over_cdp(cdp_url)
                trace.event("runtime", await obs.browser_versions(browser))
            with trace.span("page_discovery"):
                page = await linkedin_page(browser)
                obs.attach_page_observers(page, trace)
                trace.event("page", {"url": page.url, "title": await page.title()})
            with trace.span("page_navigation", {"username_hash": obs.short_hash(username)}):
                await navigate_posts(page, username)
            with trace.span("dom_validation"):
                post_containers = len(await page.query_selector_all(POST_SELECTOR))
                trace.event("selector_counts", {"selector_used": POST_SELECTOR, "post_containers": post_containers})
            stale = 0
            for _ in range(max_scrolls):
                with trace.span("scanning"):
                    handles = await page.query_selector_all(POST_SELECTOR)
                if not handles:
                    eprint("warning: no post containers found on current viewport")
                before = len(processed)
                for post in handles:
                    urn = await post.get_attribute("data-urn")
                    if not urn or urn in processed:
                        continue
                    processed.add(urn)
                    with trace.span("opening_expanding", {"post_hash": obs.short_hash(urn)}):
                        await post.scroll_into_view_if_needed(timeout=5000)
                        await page.wait_for_timeout(settle_ms)
                        await expand_text(post, settle_ms)
                        comment_stats: dict[str, int] = {}
                        if include_comments:
                            await open_comments(post, settle_ms)
                            comment_stats = await load_all_comments(post, max_comment_rounds, settle_ms)
                    scraped_at = now_utc()
                    try:
                        with trace.span("extraction", {"post_hash": obs.short_hash(urn)}):
                            extracted = await extract_post(post, scraped_at)
                    except Exception as exc:
                        trace.exception(exc, post_hash=obs.short_hash(urn))
                        eprint(f"warning: failed to extract {urn}: {exc}")
                        continue
                    for row in extracted:
                        if row["type"] == "post":
                            row["commentScrapeStats"] = comment_stats
                    with trace.span("validation"):
                        trace.event("row_counts", {"post_hash": obs.short_hash(urn), "rows": len(extracted), "missing_rates": obs.missing_rates(extracted, ["id", "content", "postedText"])})
                    rows.extend(extracted)
                    if not dry_run:
                        before_rows = len(load_jsonl(out_path))
                        with trace.span("writing", {"path": str(out_path), "before_rows": before_rows}):
                            delta = update_jsonl(out_path, extracted)
                        changed += delta
                        trace.event("output_stats", {"path": str(out_path), "before_rows": before_rows, "after_rows": len(load_jsonl(out_path)), "rows_changed": delta})
                    event = {"event": "scraped", "post": urn, "rows": len(extracted), "posts_seen": len(processed)}
                    print(compact_json(event) if format == "jsonl" else f"scraped: {urn}: rows={len(extracted)} seen={len(processed)}", flush=True)
                    if limit and len(processed) >= limit:
                        break
                if limit and len(processed) >= limit:
                    break
                stale = stale + 1 if len(processed) == before else 0
                with trace.span("scrolling", {"stale": stale}):
                    scroll = await scroll_page(page, settle_ms * 2)
                    trace.event("scroll_stats", scroll)
                if stale >= 6 or scroll["top"] + scroll["client"] >= scroll["height"] - 8:
                    show_more = await page.query_selector_all('button:has-text("Show more results"), button:has-text("Show more posts")')
                    clicks = await click_all(show_more[:2], "show-more-results", settle_ms * 2)
                    trace.event("click_stats", {"show_more_buttons": len(show_more), "show_more_clicks": clicks})
                    if not clicks:
                        break
            dom = await obs.capture_dom_outline(page)
            await browser.close()
        post_rows = sum(1 for row in rows if row.get("type") == "post")
        previous = obs.latest_summary(cache_dir).get("selector_used")
        summary_stats = {
            "status": "ok",
            "dry_run": dry_run,
            "path": str(out_path),
            "posts": len(processed),
            "rows": len(rows),
            "post_rows": post_rows,
            "rows_changed": changed,
            "selector_used": POST_SELECTOR,
            "previous_selector": previous,
            "limit": limit,
            "post_containers": post_containers if "post_containers" in locals() else 0,
            "missing_rates": obs.missing_rates([row for row in rows if row.get("type") == "post"], ["id", "content", "postedText"]),
        }
        anomalies = obs.classify_linkedin_anomalies(summary_stats)
        if anomalies:
            trace.write_zip("anomaly", {**summary_stats, "anomalies": anomalies}, dom)
        elif not obs.monthly_baseline_exists(cache_dir, trace.stamp):
            trace.write_zip("baseline", summary_stats, dom)
        trace.finish({**summary_stats, "anomalies": anomalies})
    except Exception as exc:
        trace.exception(exc)
        if page is not None:
            try:
                trace.write_zip("anomaly", {"status": "failed"}, await obs.capture_dom_outline(page))
            except Exception as zip_exc:
                trace.exception(zip_exc, during="failure_zip")
        trace.finish({"status": "failed", "error_type": type(exc).__name__, "error_message": str(exc)})
        raise
    if dry_run:
        eprint(f"dry-run: scraped {len(rows)} rows for {len(processed)} posts; not writing {out_path}")
        return
    summary = {"event": "updated", "path": str(out_path), "posts": len(processed), "rows": len(rows), "rows_changed": changed}
    print(compact_json(summary) if format == "jsonl" else f"updated: posts={len(processed)} rows={len(rows)} changed={changed} -> {out_path}", flush=True)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    describe_schema: bool = typer.Option(False, "--describe", help="Print machine-readable CLI metadata and exit."),
) -> None:
    if describe_schema:
        print(compact_json(describe()))
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit(0)


@app.command(help="Back up recent LinkedIn posts and comments from a profile activity page.")
def posts(
    username: str = typer.Option(..., "--username", help="LinkedIn public identifier, e.g. sanand0."),
    limit: int = typer.Option(100, "--limit", "-n", min=0, help="Maximum posts to scrape. Use 0 for no explicit limit."),
    out: Path = typer.Option(OUT_PATH, "--out", help="JSONL file to update in place."),
    comments: bool = typer.Option(True, "--comments/--no-comments", help="Expand and scrape comments for each post."),
    cdp_url: str = typer.Option(CDP_URL, "--cdp-url", help="Chrome DevTools Protocol URL."),
    max_scrolls: int = typer.Option(240, "--max-scrolls", help="Maximum profile activity scroll rounds."),
    max_comment_rounds: int = typer.Option(30, "--max-comment-rounds", help="Maximum load-more rounds per post."),
    settle_ms: int = typer.Option(800, "--settle-ms", help="Delay after clicks and scrolls, in milliseconds."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Scrape and report without writing the JSONL file."),
    format: str = typer.Option("text", "--format", help="text or jsonl progress output."),
) -> None:
    if format not in {"text", "jsonl"}:
        raise typer.BadParameter("--format must be text or jsonl")
    try:
        asyncio.run(scrape_posts(cdp_url, username, limit, out.expanduser(), comments, max_scrolls, max_comment_rounds, settle_ms, dry_run, format))
    except Exception as exc:
        typer.echo(f"backup_linkedin.py: {exc}", err=True)
        raise typer.Exit(1) from exc


if __name__ == "__main__":
    app()
