#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["playwright>=1.52", "typer>=0.12"]
# ///
"""Back up WhatsApp Web conversations through Chrome DevTools Protocol.

Examples:
  backupwhatsapp.py --limit 5
  backupwhatsapp.py --conversation "Family" --conversation "Notes" --format jsonl
  backupwhatsapp.py --since 2026-05-01 --until 2026-05-17 --limit 20 | moor
  backupwhatsapp.py --describe | jaq .
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import typer
from playwright.async_api import Browser, Page, async_playwright

import sanand_observability as obs

app = typer.Typer(add_completion=False, help=__doc__)

OUT_DIR = Path("~/Documents/data/whatsapp").expanduser()
CACHE_DIR = Path("~/.cache/sanand-scripts/backupwhatsapp").expanduser()
SCRAPER = Path("/home/sanand/code/tools/whatsappscraper/whatsappscraper.min.js")
CDP_URL = "http://localhost:9222"
CHAT_LIST_SELECTOR = "#pane-side"
MAIN_SELECTOR = "div#main"
INCREMENTAL_SORT_SAFETY = 4
INCREMENTAL_LOOKBACK_DAYS = 3
INCREMENTAL_PAST_CUTOFF_PAGES = 2
CHAT_LIST_SCROLL_PAGE_FACTOR = 1.5
RUN_FIELDS = {"scrapedAt"}
METADATA_FIELDS = {"conversationTitle", "conversationId", "userId"}
CHAT_ID_JS = r"""
(root) => {
  const seen = new WeakSet();
  const normalize = (value) => {
    const text = String(value || "").replace(/\u200b/g, "").trim();
    if (!text) return "";
    const match = text.match(/^([^@\s]+@(?:c\.us|g\.us|lid))$/i);
    if (match) return match[1];
    if (/^[a-z0-9._:-]{6,}$/i.test(text)) return text;
    return "";
  };
  const fromChat = (chat) => normalize(chat?.__x_id?._serialized || chat?.id?._serialized || chat?.__x_id?.user || chat?.id?.user);
  const scan = (value, depth = 0) => {
    if (!value || depth > 6) return "";
    if (typeof value === "string") return "";
    if (typeof value !== "object" && typeof value !== "function") return "";
    if (seen.has(value)) return "";
    seen.add(value);
    const direct = fromChat(value);
    if (direct) return direct;
    for (const key of Object.getOwnPropertyNames(value).slice(0, 80)) {
      if (/^(child|sibling|return|alternate|stateNode|_debug|dependencies|memoizedState|updateQueue|ref|refs|containerInfo)$/i.test(key)) continue;
      let next;
      try { next = value[key]; } catch { continue; }
      if (/^(chat|contact|contactId|wid|jid|id|__x_id)$/i.test(key)) {
        const id = fromChat(next) || normalize(next?._serialized || next?.user || next);
        if (id) return id;
      }
      const found = scan(next, depth + 1);
      if (found) return found;
    }
    return "";
  };
  for (const selector of [
    "[data-chat-id]",
    "[data-contact-id]",
    "[data-jid]",
    "#main header [data-chat-id]",
    "#main header [data-contact-id]",
    "#main header [data-jid]",
  ]) {
    const node = (root || document).querySelector?.(selector);
    const id = normalize(node?.getAttribute("data-chat-id") || node?.getAttribute("data-contact-id") || node?.getAttribute("data-jid"));
    if (id) return id;
  }
  for (const node of [root, root?.querySelector?.("header"), document.querySelector("div#main header")].filter(Boolean)) {
    for (const prop of Object.getOwnPropertyNames(node).filter((key) => /reactFiber|reactProps/i.test(key))) {
      const id = scan(node[prop]);
      if (id) return id;
    }
  }
  return "";
}
"""
CHAT_LIST_JS = r"""
() => {
  const pane = document.querySelector("#pane-side");
  if (!pane) return { error: "WhatsApp chat list not found. Open https://web.whatsapp.com/ first." };
  const chatIdFor = %CHAT_ID_JS%;
  const browserTimeZone = Intl.DateTimeFormat().resolvedOptions().timeZone || "";
  const pad = (value) => String(value).padStart(2, "0");
  const localDay = (date) => `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
  const endOfDay = (date) => new Date(date.getFullYear(), date.getMonth(), date.getDate(), 23, 59, 59, 0);
  const parseClock = (text) => {
    const match = String(text || "").trim().match(/^(\d{1,2}):(\d{2})(?:\s?([ap]m))?$/i);
    if (!match) return null;
    let hours = Number(match[1]);
    const minutes = Number(match[2]);
    const meridiem = match[3]?.toLowerCase();
    if (meridiem) {
      hours %= 12;
      if (meridiem === "pm") hours += 12;
    }
    return { hours, minutes };
  };
  const monthNames = "jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december";
  const parseListTime = (value) => {
    const text = String(value || "").trim();
    if (!text) return {};
    const now = new Date();
    const clock = parseClock(text);
    if (clock) {
      const date = new Date(now.getFullYear(), now.getMonth(), now.getDate(), clock.hours, clock.minutes, 0, 0);
      return { iso: date.toISOString(), localDay: localDay(date) };
    }
    if (/^today$/i.test(text)) {
      const date = endOfDay(now);
      return { iso: date.toISOString(), localDay: localDay(date) };
    }
    if (/^yesterday$/i.test(text)) {
      const date = endOfDay(new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1));
      return { iso: date.toISOString(), localDay: localDay(date) };
    }
    const weekdays = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"];
    const weekday = weekdays.indexOf(text.toLowerCase());
    if (weekday >= 0) {
      const days = (now.getDay() - weekday + 7) % 7 || 7;
      const date = endOfDay(new Date(now.getFullYear(), now.getMonth(), now.getDate() - days));
      return { iso: date.toISOString(), localDay: localDay(date) };
    }
    const numeric = text.match(/^(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?$/);
    if (numeric) {
      let year = numeric[3] ? Number(numeric[3]) : now.getFullYear();
      if (year < 100) year += 2000;
      const date = endOfDay(new Date(year, Number(numeric[2]) - 1, Number(numeric[1])));
      return { iso: date.toISOString(), localDay: localDay(date) };
    }
    const month = text.match(new RegExp(`^(${monthNames})\\s+(\\d{1,2})$`, "i"));
    if (month) {
      const date = endOfDay(new Date(`${month[1]} ${month[2]}, ${now.getFullYear()}`));
      if (!Number.isNaN(date.getTime())) return { iso: date.toISOString(), localDay: localDay(date) };
    }
    return {};
  };
  const unreadFor = (row) => {
    const label = [
      row.getAttribute("aria-label") || "",
      ...[...row.querySelectorAll("[aria-label]")].map((node) => node.getAttribute("aria-label") || ""),
    ].join(" ");
    const unread = /\bunread\b/i.test(label);
    const count = label.match(/(\d+)\s+unread/i);
    return { unread, unreadCount: count ? Number(count[1]) : (unread ? 1 : 0), unreadText: label.trim() };
  };
  const rows = [...pane.querySelectorAll('[role="listitem"], [role="row"]')]
    .filter((row) => row.offsetParent && row.innerText.trim());
  const timePattern = new RegExp(`^(?:\\d{1,2}:\\d{2}(?:\\s?[ap]m)?|today|yesterday|monday|tuesday|wednesday|thursday|friday|saturday|sunday|\\d{1,2}[/-]\\d{1,2}(?:[/-]\\d{2,4})?|(?:${monthNames})\\s+\\d{1,2})$`, "i");
  return {
    scrollTop: pane.scrollTop,
    clientHeight: pane.clientHeight,
    scrollHeight: pane.scrollHeight,
    browserTimeZone,
    chats: rows.map((row, index) => {
      const lines = row.innerText.split(/\n+/).map((line) => line.trim()).filter(Boolean);
      const titled = [...row.querySelectorAll("[title]")]
        .map((node) => node.getAttribute("title") || "")
        .map((text) => text.trim())
        .filter((text) => text && !timePattern.test(text));
      const title = titled[0] || lines.find((line) => !timePattern.test(line)) || "";
      const lastActiveText = [...lines].reverse().find((line) => timePattern.test(line)) || "";
      const conversationId = chatIdFor(row);
      const parsed = parseListTime(lastActiveText);
      const unread = unreadFor(row);
      return {
        index,
        title,
        conversationId,
        lastActiveText,
        lastActiveTime: parsed.iso || "",
        lastActiveDay: parsed.localDay || "",
        browserTimeZone,
        ...unread,
        preview: lines.slice(0, 5).join(" | "),
      };
    }).filter((chat) => chat.title),
  };
}
""".replace("%CHAT_ID_JS%", CHAT_ID_JS)
CLICK_CHAT_JS = r"""
({ title, conversationId }) => {
  const pane = document.querySelector("#pane-side");
  const chatIdFor = %CHAT_ID_JS%;
  const rows = [...pane.querySelectorAll('[role="listitem"], [role="row"]')];
  const row = rows.find((candidate) => conversationId && chatIdFor(candidate) === conversationId)
    || rows.find((candidate) => [...candidate.querySelectorAll("[title]")].some((node) => node.getAttribute("title") === title));
  const titleNode = row?.querySelector(`[title="${CSS.escape(title)}"]`) || row?.querySelector("[title]") || row;
  if (!titleNode || !row) return false;
  titleNode.scrollIntoView({ block: "center" });
  for (const target of [titleNode, row]) {
    target.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, cancelable: true, view: window }));
    target.dispatchEvent(new MouseEvent("mouseup", { bubbles: true, cancelable: true, view: window }));
    target.click();
  }
  return true;
}
""".replace("%CHAT_ID_JS%", CHAT_ID_JS)
SCROLL_HISTORY_JS = r"""
({ cutoff, maxMessages, maxRounds, settleMs }) => new Promise(async (resolve) => {
  const sleep = (ms) => new Promise((done) => setTimeout(done, ms));
  const seen = Object.create(null);
  const richness = (value) => {
    if (value === null || value === undefined || value === "" || value === false) return 0;
    if (typeof value === "string") return value.length;
    if (Array.isArray(value)) return value.length;
    if (typeof value === "object") return Object.keys(value).length;
    return 1;
  };
  const merge = (oldRow, newRow) => {
    const row = { ...(oldRow || {}) };
    for (const [key, value] of Object.entries(newRow)) {
      if (richness(value) >= richness(row[key])) row[key] = value;
    }
    return row;
  };
  const parseClock = (value) => {
    const match = String(value || "").trim().match(/^(\d{1,2}):(\d{2})(?:\s*([ap]m))?$/i);
    if (!match) return null;
    let hours = Number(match[1]);
    const minutes = Number(match[2]);
    const meridiem = match[3]?.toLowerCase();
    if (meridiem) {
      hours %= 12;
      if (meridiem === "pm") hours += 12;
    }
    return { hours, minutes };
  };
  const parseDateLabel = (value) => {
    const text = String(value || "").trim();
    const now = new Date();
    const atEnd = (date) => new Date(date.getFullYear(), date.getMonth(), date.getDate(), 23, 59, 59, 0);
    if (/^today$/i.test(text)) return atEnd(now);
    if (/^yesterday$/i.test(text)) return atEnd(new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1));
    const weekdays = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"];
    const weekday = weekdays.indexOf(text.toLowerCase());
    if (weekday >= 0) {
      const days = (now.getDay() - weekday + 7) % 7 || 7;
      return atEnd(new Date(now.getFullYear(), now.getMonth(), now.getDate() - days));
    }
    const match = text.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
    if (match) return atEnd(new Date(Number(match[3]), Number(match[2]) - 1, Number(match[1])));
    return null;
  };
  const messageIdFromDataId = (value) => {
    const packed = String(value || "").match(/^(?:true|false)_[^@]+@[^_]+_([^_]+)/i);
    return packed ? packed[1] : String(value || "");
  };
  const visibleTimeForRow = (row) => [...row.querySelectorAll('[dir="auto"]')]
    .map((node) => node.textContent.trim())
    .filter((text) => parseClock(text))
    .at(-1);
  const fallbackText = (row, clock) => {
    const lines = String(row.innerText || "")
      .split(/\n+/)
      .map((line) => line.trim())
      .filter(Boolean)
      .filter((line) => line !== clock);
    if (!lines.length) return {};
    const author = lines.length > 1 && !/^(forwarded|forwarded many times|photo|video|pdf|document|voice message|this message was deleted)$/i.test(lines[0])
      ? lines[0]
      : undefined;
    const text = lines.filter((line) => !/^\+?\d[\d\s().-]{6,}$/.test(line)).join("\n").trim();
    return { ...(author ? { author } : {}), ...(text ? { text } : {}) };
  };
  const rowsFromDateChips = () => {
    const times = Object.create(null);
    const rows = Object.create(null);
    const main = document.querySelector("div#main");
    let currentDate = null;
    for (const node of main?.querySelectorAll("div, span") || []) {
      const row = node.matches?.('[role="row"]') ? node : null;
      if (row) {
        const dataId = row.querySelector("[data-id]")?.getAttribute("data-id");
        const clock = visibleTimeForRow(row);
        const parsed = parseClock(clock);
        if (dataId && currentDate && parsed) {
          const when = new Date(currentDate.getFullYear(), currentDate.getMonth(), currentDate.getDate(), parsed.hours, parsed.minutes, 0, 0);
          const messageId = messageIdFromDataId(dataId);
          times[messageId] = when.toISOString();
          rows[messageId] = {
            messageId,
            time: when.toISOString(),
            ...(row.querySelector(".message-out") ? { isOutgoing: true } : {}),
            ...fallbackText(row, clock),
          };
        }
        continue;
      }
      if (node.querySelector?.("[data-id]")) continue;
      const text = node.innerText?.trim();
      if (!text || text.length > 20) continue;
      const date = parseDateLabel(text);
      if (date) currentDate = date;
    }
    return { times, rows };
  };
  const gather = () => {
    const corrected = rowsFromDateChips();
    const messages = (globalThis.whatsappscraper?.whatsappMessages(document) || [])
      .filter((msg) => msg.messageId);
    for (const msg of messages) {
      if (corrected.times[msg.messageId]) msg.time = corrected.times[msg.messageId];
    }
    const messageIds = new Set(messages.map((msg) => msg.messageId));
    for (const row of Object.values(corrected.rows)) {
      if (!messageIds.has(row.messageId) && (row.text || row.author)) messages.push(row);
    }
    for (const msg of messages) seen[msg.messageId] = merge(seen[msg.messageId], msg);
    return Object.values(seen);
  };
  const scrollers = [...document.querySelectorAll("div#main div")]
    .filter((el) => el.scrollHeight > el.clientHeight + 200);
  const scroller = scrollers.sort((a, b) => b.scrollHeight - a.scrollHeight)[0];
  if (!scroller) return resolve({ rounds: 0, reason: "no-history-scroller", messages: gather() });
  let bottomJumps = 0;
  for (; bottomJumps < 80; bottomJumps += 1) {
    const button = document.querySelector('button[aria-label="Scroll to bottom"]');
    if (!button) break;
    button.click();
    await sleep(settleMs);
  }
  for (let jump = 0; jump < 4; jump += 1) {
    scroller.scrollTop = scroller.scrollHeight;
    scroller.dispatchEvent(new Event("scroll", { bubbles: true }));
    await sleep(settleMs);
  }
  let stale = 0;
  let previous = "";
  let reason = "max-rounds";
  let rounds = 0;
  for (; rounds < maxRounds; rounds += 1) {
    const messages = gather();
    const oldest = messages.map((msg) => msg.time).filter(Boolean).sort()[0] || "";
    const signature = `${scroller.scrollTop}:${scroller.scrollHeight}:${messages.length}:${oldest}`;
    if (maxMessages && messages.length >= maxMessages) {
      reason = "message-limit-reached";
      break;
    }
    if (cutoff && oldest && oldest <= cutoff) {
      reason = "cutoff-reached";
      break;
    }
    if (signature === previous) stale += 1;
    else stale = 0;
    if (stale >= 4) {
      reason = "plateau";
      break;
    }
    previous = signature;
    scroller.scrollTop = 0;
    scroller.dispatchEvent(new Event("scroll", { bubbles: true }));
    await sleep(settleMs);
  }
  gather();
  resolve({ bottomJumps, rounds, reason, messages: Object.values(seen) });
})
"""


def eprint(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def state_path() -> Path:
    return CACHE_DIR / "checked.json"


def load_checked_state() -> dict[str, Any]:
    path = state_path()
    return json.loads(path.read_text()) if path.exists() else {}


def write_checked_state(state: dict[str, Any]) -> None:
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{time.time_ns()}.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    tmp.replace(path)


def parse_time(value: str) -> dt.datetime:
    text = value.strip()
    if not text:
        raise ValueError("empty time")
    if match := re.fullmatch(r"(\d+)([dhm])", text, re.I):
        amount, unit = int(match[1]), match[2].lower()
        delta = {"d": dt.timedelta(days=amount), "h": dt.timedelta(hours=amount), "m": dt.timedelta(minutes=amount)}[unit]
        return dt.datetime.now(dt.UTC) - delta
    if match := re.fullmatch(r"(\d+)\s+months?\s+ago", text, re.I):
        return dt.datetime.now(dt.UTC) - dt.timedelta(days=30 * int(match[1]))
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        text += "T00:00:00"
    parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.datetime.now().astimezone().tzinfo)
    return parsed.astimezone(dt.UTC)


def parse_chat_list_time(value: str) -> dt.datetime | None:
    text = value.strip().lower()
    now = dt.datetime.now(dt.UTC).astimezone()
    if not text:
        return None
    if match := re.fullmatch(r"(\d{1,2}):(\d{2})(?:\s?([ap]m))?", text):
        hour = int(match[1])
        minute = int(match[2])
        meridiem = match[3]
        if meridiem:
            hour %= 12
            if meridiem == "pm":
                hour += 12
        return now.replace(hour=hour, minute=minute, second=0, microsecond=0).astimezone(dt.UTC)
    if text == "today":
        return now.replace(hour=23, minute=59, second=59, microsecond=0).astimezone(dt.UTC)
    if text == "yesterday":
        return (now - dt.timedelta(days=1)).replace(hour=23, minute=59, second=59, microsecond=0).astimezone(dt.UTC)
    weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    if text in weekdays:
        days = (now.weekday() - weekdays.index(text)) % 7 or 7
        return (now - dt.timedelta(days=days)).replace(hour=23, minute=59, second=59, microsecond=0).astimezone(dt.UTC)
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d-%m-%y"):
        try:
            parsed = dt.datetime.strptime(text.title(), fmt)
            return parsed.replace(hour=23, minute=59, second=59, tzinfo=now.tzinfo).astimezone(dt.UTC)
        except ValueError:
            pass
    for fmt in ("%Y %b %d", "%Y %B %d"):
        try:
            parsed = dt.datetime.strptime(f"{now.year} {text.title()}", fmt)
            return parsed.replace(hour=23, minute=59, second=59, tzinfo=now.tzinfo).astimezone(dt.UTC)
        except ValueError:
            pass
    return None


def safe_name(value: str, fallback: str = "untitled", limit: int = 180) -> str:
    name = re.sub(r"[/\\:\0-\x1f]+", " ", value)
    name = re.sub(r"\s+", " ", name).strip(" .")
    if not name:
        name = fallback
    return name[:limit]


def filename_for(title: str, conversation_id: str = "") -> Path:
    name = safe_name(title)
    if conversation_id:
        safe_id = safe_name(conversation_id, "unknown", 96)
        return OUT_DIR / f"{name[:160]} [{safe_id}].jsonl"
    return OUT_DIR / f"{name}.jsonl"


def files_for_id(conversation_id: str) -> list[Path]:
    if not conversation_id:
        return []
    safe_id = safe_name(conversation_id, "unknown", 96)
    return sorted(OUT_DIR.glob(f"* [{safe_id}].jsonl"))


def path_for(title: str, conversation_id: str = "") -> Path:
    if conversation_id:
        matches = files_for_id(conversation_id)
        if matches:
            return matches[0]
        return filename_for(title, conversation_id)
    return filename_for(title)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{time.time_ns()}.tmp")
    tmp.write_text("".join(compact_json(row) + "\n" for row in rows))
    tmp.replace(path)
    sync_mtime_to_latest_message(path, rows)


def history_path(path: Path) -> Path:
    return path.parent / ".history" / f"{path.stem}.history.jsonl"


def append_history(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    audit_path = history_path(path)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    with audit_path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(compact_json(row) + "\n")


def sync_mtime_to_latest_message(path: Path, rows: list[dict[str, Any]] | None = None) -> dt.datetime | None:
    latest = max_message_time(rows if rows is not None else load_jsonl(path))
    if latest is None:
        return None
    stamp = latest.timestamp()
    os.utime(path, (stamp, stamp))
    return latest


def backup_paths() -> list[Path]:
    return sorted([*OUT_DIR.glob("*.jsonl"), *OUT_DIR.glob("*.json")])


def latest_backup_mtime() -> dt.datetime | None:
    times = [dt.datetime.fromtimestamp(path.stat().st_mtime, dt.UTC) for path in backup_paths()]
    return max(times) if times else None


def incremental_stop_time() -> dt.datetime | None:
    latest = latest_backup_mtime()
    return latest - dt.timedelta(days=INCREMENTAL_LOOKBACK_DAYS) if latest else None


def chat_key(title: str, conversation_id: str) -> str:
    return conversation_id or f"title:{title}"


def chat_state(chat: dict[str, Any], list_time: dt.datetime | None, local_since: dt.datetime | None) -> dict[str, Any]:
    return {
        "title": chat["title"],
        "conversationId": chat.get("conversationId") or "",
        "lastActiveText": chat.get("lastActiveText") or "",
        "lastActiveDay": chat.get("lastActiveDay") or "",
        "browserTimeZone": chat.get("browserTimeZone") or "",
        "listTime": list_time.isoformat() if list_time else "",
        "localLatestTime": local_since.isoformat() if local_since else "",
        "checkedAt": dt.datetime.now(dt.UTC).isoformat(),
    }


def already_checked(state: dict[str, Any], key: str, chat: dict[str, Any], list_time: dt.datetime | None) -> bool:
    row = state.get(key)
    if not row:
        return False
    if row.get("lastActiveText") == (chat.get("lastActiveText") or "") and row.get("listTime") == (list_time.isoformat() if list_time else ""):
        return True
    return bool(row.get("lastActiveDay") and row.get("lastActiveDay") == (chat.get("lastActiveDay") or ""))


def chat_list_time(chat: dict[str, Any]) -> dt.datetime | None:
    if chat.get("lastActiveTime"):
        try:
            return parse_time(str(chat["lastActiveTime"]))
        except ValueError:
            pass
    return parse_chat_list_time(chat.get("lastActiveText", ""))


def local_day(when: dt.datetime, time_zone: str) -> str:
    try:
        zone = ZoneInfo(time_zone) if time_zone else dt.datetime.now().astimezone().tzinfo
    except ZoneInfoNotFoundError:
        zone = dt.datetime.now().astimezone().tzinfo
    return when.astimezone(zone).date().isoformat()


def known_no_new_content(chat: dict[str, Any], checked_state: dict[str, Any]) -> bool:
    if int(chat.get("unreadCount") or 0) > 0:
        return False
    title = chat["title"]
    conversation_id = chat.get("conversationId") or ""
    path = path_for(title, conversation_id)
    if not path.exists():
        return False
    local_since = max_message_time(load_jsonl(path))
    if local_since is None:
        return False
    list_time = chat_list_time(chat)
    if list_time and list_time <= local_since:
        return True
    key = chat_key(title, conversation_id)
    if already_checked(checked_state, key, chat, list_time):
        return True
    return bool(chat.get("lastActiveDay") and chat["lastActiveDay"] == local_day(local_since, chat.get("browserTimeZone") or ""))


def sorted_time_violations(chats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    violations = []
    previous_chat: dict[str, Any] | None = None
    previous_time: dt.datetime | None = None
    for chat in chats:
        when = chat_list_time(chat)
        if when is None:
            continue
        if previous_time and when > previous_time:
            violations.append({"previous": previous_chat, "previousTime": previous_time.isoformat(), "current": chat, "currentTime": when.isoformat()})
        previous_chat = chat
        previous_time = when
    return violations


def newest_chat_time(chats: list[dict[str, Any]]) -> dt.datetime | None:
    times = [chat_list_time(chat) for chat in chats]
    return max([when for when in times if when is not None], default=None)


def merge_jsonl_files(target: Path, sources: list[Path]) -> None:
    rows: dict[str, dict[str, Any]] = {}
    for path in [target, *sources]:
        for row in load_jsonl(path):
            key = row_key(row)
            rows[key], _ = merge_row(rows.get(key, {}), row)
    if rows:
        write_jsonl(target, sorted(rows.values(), key=sort_key))
    for source in sources:
        if source.exists() and source != target:
            source.unlink()


def migrate_path(title: str, conversation_id: str) -> Path:
    target = path_for(title, conversation_id)
    legacy = filename_for(title)
    sources = [legacy] if legacy.exists() and legacy != target else []
    extra = [path for path in files_for_id(conversation_id) if path != target]
    if sources or extra:
        merge_jsonl_files(target, [*sources, *extra])
    return target


def row_key(row: dict[str, Any]) -> str:
    if row.get("messageId"):
        return f"id:{row['messageId']}"
    return "fallback:" + compact_json({key: row.get(key) for key in ["time", "author", "text", "mediaType"]})


def richness(value: Any) -> int:
    if value in (None, "", [], {}, False):
        return 0
    if isinstance(value, str):
        return len(value)
    if isinstance(value, (list, dict)):
        return len(value)
    return 1


def merged_value(key: str, old: Any, new: Any) -> tuple[Any, bool]:
    if key in RUN_FIELDS:
        return new, old != new
    if key == "reactions":
        return new, old != new
    if key in METADATA_FIELDS:
        return (new, True) if richness(new) > richness(old) else (old, False)
    if richness(new) > richness(old):
        return new, True
    return old, False


def merge_row(old: dict[str, Any], new: dict[str, Any]) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    merged = dict(old)
    conflicts: dict[str, dict[str, Any]] = {}
    for key, value in new.items():
        current = merged.get(key)
        selected, changed = merged_value(key, current, value)
        if changed:
            merged[key] = selected
        elif key not in RUN_FIELDS and richness(value) and current not in (None, "", [], {}, False) and current != value:
            conflicts[key] = {"kept": current, "incoming": value}
    return merged, conflicts


def without_run_fields(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key not in RUN_FIELDS}


def sort_key(row: dict[str, Any]) -> tuple[str, str]:
    return (str(row.get("time") or ""), str(row.get("messageId") or ""))


def max_message_time(rows: list[dict[str, Any]]) -> dt.datetime | None:
    times = []
    for row in rows:
        if row.get("time"):
            try:
                times.append(parse_time(str(row["time"])))
            except ValueError:
                pass
    return max(times) if times else None


def in_range(row: dict[str, Any], since: dt.datetime | None, until: dt.datetime | None) -> bool:
    if not row.get("time"):
        return since is None and until is None
    try:
        when = parse_time(str(row["time"]))
    except ValueError:
        return since is None and until is None
    return (since is None or when >= since) and (until is None or when < until)


def filtered_messages(messages: list[dict[str, Any]], since: dt.datetime | None, until: dt.datetime | None, max_messages: int) -> list[dict[str, Any]]:
    rows = [message for message in messages if in_range(message, since, until)]
    if not max_messages or len(rows) <= max_messages:
        return rows
    return sorted(rows, key=sort_key, reverse=True)[:max_messages]


def update_conversation(path: Path, title: str, conversation_id: str, messages: list[dict[str, Any]], since: dt.datetime | None, until: dt.datetime | None, max_messages: int) -> int:
    existing = {row_key(row): row for row in load_jsonl(path)}
    scraped_at = dt.datetime.now(dt.UTC).isoformat()
    history: list[dict[str, Any]] = []
    changed = 0
    if conversation_id:
        for key, row in existing.items():
            if row.get("conversationId") != conversation_id:
                history.append(
                    {
                        "archivedAt": scraped_at,
                        "reason": "metadata-update",
                        "path": str(path),
                        "rowKey": key,
                        "messageId": row.get("messageId") or "",
                        "fields": {"conversationId": {"kept": row.get("conversationId"), "incoming": conversation_id}},
                    }
                )
                existing[key] = {**row, "conversationId": conversation_id}
                changed += 1
    for message in filtered_messages(messages, since, until, max_messages):
        row = {**message, "conversationTitle": title, "conversationId": conversation_id, "scrapedAt": scraped_at}
        key = row_key(row)
        current = existing.get(key)
        merged, conflicts = merge_row(current or {}, row)
        if current and conflicts:
            history.append(
                {
                    "archivedAt": scraped_at,
                    "reason": "conflict-kept-existing",
                    "path": str(path),
                    "rowKey": key,
                    "messageId": row.get("messageId") or "",
                    "fields": conflicts,
                }
            )
        if current and without_run_fields(current) == without_run_fields(merged):
            continue
        if current != merged:
            changed += 1
        existing[key] = merged
    append_history(path, history)
    write_jsonl(path, sorted(existing.values(), key=sort_key))
    return changed


def describe() -> dict[str, Any]:
    return {
        "name": "backupwhatsapp.py",
        "output": "~/Documents/data/whatsapp/{conversation title} [{immutable WhatsApp chat id}].jsonl",
        "primary_key": "messageId",
        "conversation_key": "conversationId",
        "history": "~/Documents/data/whatsapp/.history/{conversation file stem}.history.jsonl",
        "cdp": CDP_URL,
        "filters": ["--conversation", "--name", "--updated-since", "--updated-until", "--since", "--until", "--max-messages", "--limit"],
        "examples": [
            "backupwhatsapp.py --limit 5",
            "backupwhatsapp.py --conversation Family --format jsonl",
            "backupwhatsapp.py --since 2026-05-01 --until 2026-05-17",
        ],
    }


async def whatsapp_page(browser: Browser) -> Page:
    for context in browser.contexts:
        for page in context.pages:
            if "web.whatsapp.com" in page.url:
                await page.bring_to_front()
                return page
    raise RuntimeError("No WhatsApp Web tab found. Open https://web.whatsapp.com/ in a CDP-enabled browser first.")


async def inject_scraper(page: Page, scraper: Path) -> None:
    code = scraper.read_text()
    await page.evaluate(
        """async (src) => {
          if (globalThis.whatsappscraper?.whatsappMessages) return;
          const blob = new Blob([src], { type: "text/javascript" });
          const url = URL.createObjectURL(blob);
          try {
            await new Promise((resolve, reject) => {
              const script = document.createElement("script");
              script.src = url;
              script.onload = resolve;
              script.onerror = reject;
              document.head.appendChild(script);
            });
          } finally {
            URL.revokeObjectURL(url);
          }
        }""",
        code,
    )


async def current_chat_id(page: Page) -> str:
    return await page.evaluate(f"() => ({CHAT_ID_JS})(document.querySelector('div#main') || document)")


async def list_chats(page: Page) -> dict[str, Any]:
    data = await page.evaluate(CHAT_LIST_JS)
    if data.get("error"):
        raise RuntimeError(data["error"])
    return data


async def iter_chats(page: Page, max_scan: int, stop_at: dt.datetime | None = None, checked_state: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    await page.wait_for_selector(CHAT_LIST_SELECTOR, timeout=10000)
    await page.eval_on_selector(CHAT_LIST_SELECTOR, "(pane) => pane.scrollTop = 0")
    await page.wait_for_timeout(400)
    seen: dict[str, dict[str, Any]] = {}
    stale = 0
    warned_unsorted = False
    past_cutoff_pages = 0
    for _ in range(max_scan):
        data = await list_chats(page)
        before = len(seen)
        new_chats = []
        for chat in data["chats"]:
            key = chat.get("conversationId") or chat["title"]
            if key in seen:
                continue
            seen[key] = chat
            new_chats.append(chat)
        if len(seen) == before:
            stale += 1
        else:
            stale = 0
        ordered = list(seen.values())
        if checked_state is not None:
            violations = sorted_time_violations(ordered)
            if violations and not warned_unsorted:
                warned_unsorted = True
                violation = max(violations, key=lambda row: parse_time(row["currentTime"]) - parse_time(row["previousTime"]))
                previous = violation["previous"] or {}
                current = violation["current"] or {}
                eprint(
                    "warning: WhatsApp chat list has out-of-order latest-message dates; "
                    f"{previous.get('title', '?')}={violation['previousTime']} appears before "
                    f"{current.get('title', '?')}={violation['currentTime']}. "
                    "Using paged cutoff safety instead of sorted-list early-stop."
                )
        newest_new = newest_chat_time(new_chats)
        if stop_at and new_chats and newest_new and newest_new <= stop_at:
            past_cutoff_pages += 1
            if past_cutoff_pages >= INCREMENTAL_PAST_CUTOFF_PAGES:
                eprint(
                    f"incremental: stopping chat-list scan after {past_cutoff_pages} newly discovered pages "
                    f"at or before {newest_new.date()} (buffered cutoff {stop_at.date()})"
                )
                break
        elif new_chats:
            past_cutoff_pages = 0
        if checked_state is not None and stop_at is None and not warned_unsorted:
            covered_tail = 0
            for chat in ordered:
                covered_tail = covered_tail + 1 if known_no_new_content(chat, checked_state) else 0
            if covered_tail >= INCREMENTAL_SORT_SAFETY:
                break
        if data["scrollTop"] + data["clientHeight"] >= data["scrollHeight"] - 4 or stale >= 10:
            break
        await page.eval_on_selector(CHAT_LIST_SELECTOR, f"(pane) => pane.scrollTop += pane.clientHeight * {CHAT_LIST_SCROLL_PAGE_FACTOR}")
        await page.wait_for_timeout(500)
    await page.eval_on_selector(CHAT_LIST_SELECTOR, "(pane) => pane.scrollTop = 0")
    await page.wait_for_timeout(400)
    return list(seen.values())


async def open_chat(page: Page, title: str, conversation_id: str, max_scan: int) -> tuple[bool, str]:
    async def click_if_visible() -> bool | None:
        data = await list_chats(page)
        for chat in data["chats"]:
            if (conversation_id and chat.get("conversationId") == conversation_id) or (not conversation_id and chat["title"] == title):
                if not await page.evaluate(CLICK_CHAT_JS, {"title": title, "conversationId": conversation_id}):
                    return False
                await page.wait_for_selector(MAIN_SELECTOR, timeout=10000)
                await page.wait_for_timeout(1200)
                return True
        return None

    visible = await click_if_visible()
    if visible is not None:
        return visible, "visible"
    for _ in range(max_scan):
        data = await list_chats(page)
        if data["scrollTop"] + data["clientHeight"] >= data["scrollHeight"] - 4:
            break
        await page.eval_on_selector(CHAT_LIST_SELECTOR, f"(pane) => pane.scrollTop += pane.clientHeight * {CHAT_LIST_SCROLL_PAGE_FACTOR}")
        await page.wait_for_timeout(500)
        visible = await click_if_visible()
        if visible is not None:
            return visible, "scroll"
    await page.eval_on_selector(CHAT_LIST_SELECTOR, "(pane) => pane.scrollTop = 0")
    await page.wait_for_timeout(250)
    visible = await click_if_visible()
    if visible is not None:
        return visible, "reset-visible"
    for _ in range(max_scan):
        data = await list_chats(page)
        if data["scrollTop"] + data["clientHeight"] >= data["scrollHeight"] - 4:
            break
        await page.eval_on_selector(CHAT_LIST_SELECTOR, f"(pane) => pane.scrollTop += pane.clientHeight * {CHAT_LIST_SCROLL_PAGE_FACTOR}")
        await page.wait_for_timeout(500)
        visible = await click_if_visible()
        if visible is not None:
            return visible, "reset-scroll"
    return False, "not-found"


async def scrape_open_chat(page: Page, cutoff: dt.datetime | None, max_messages: int, max_rounds: int, settle_ms: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    await inject_scraper(page, SCRAPER)
    cutoff_text = cutoff.isoformat() if cutoff else ""
    scroll = await page.evaluate(SCROLL_HISTORY_JS, {"cutoff": cutoff_text, "maxMessages": max_messages, "maxRounds": max_rounds, "settleMs": settle_ms})
    messages = scroll.pop("messages", [])
    unique = {row_key(row): row for row in messages if row.get("messageId")}
    conversation_id = await current_chat_id(page)
    dom_counts = await page.evaluate(
        """() => ({
          parser_dom_count: document.querySelectorAll('div#main [data-id]').length,
          history_scroller_found: [...document.querySelectorAll('div#main div')].some((el) => el.scrollHeight > el.clientHeight + 200),
        })"""
    )
    for row in unique.values():
        if conversation_id:
            row.setdefault("userId", conversation_id)
    return list(unique.values()), {**scroll, **dom_counts, "scraper_dom_count": len(messages), "conversation_id": conversation_id}


async def run_backup(
    cdp_url: str,
    conversations: set[str],
    name: str,
    since: dt.datetime | None,
    until: dt.datetime | None,
    updated_since: dt.datetime | None,
    updated_until: dt.datetime | None,
    max_messages: int,
    limit: int,
    max_scan: int,
    max_scroll_rounds: int,
    settle_ms: int,
    dry_run: bool,
    format: str,
) -> None:
    cache_dir = Path("~/.cache/sanand-scripts/backupwhatsapp").expanduser()
    trace = obs.new_run(
        "backupwhatsapp",
        cache_dir=cache_dir,
        args=obs.sanitize_args(
            {
                "conversation": sorted(conversations),
                "name": name,
                "since": since.isoformat() if since else "",
                "until": until.isoformat() if until else "",
                "updated_since": updated_since.isoformat() if updated_since else "",
                "updated_until": updated_until.isoformat() if updated_until else "",
                "max_messages": max_messages,
                "limit": limit,
                "cdp_url": cdp_url,
                "out_dir": OUT_DIR,
                "max_scan": max_scan,
                "max_scroll_rounds": max_scroll_rounds,
                "settle_ms": settle_ms,
                "dry_run": dry_run,
                "format": format,
            }
        ),
    )
    page: Page | None = None
    run_stats: dict[str, Any] = {"opened_chats": 0, "skipped_chats": 0, "messages_seen": 0, "messages_kept": 0, "rows_changed": 0}
    try:
        async with async_playwright() as p:
            with trace.span("cdp_connection", {"cdp_url": cdp_url}):
                browser = await p.chromium.connect_over_cdp(cdp_url)
                trace.event("runtime", await obs.browser_versions(browser))
            with trace.span("page_discovery"):
                page = await whatsapp_page(browser)
                obs.attach_page_observers(page, trace)
                trace.event("page", {"url": page.url, "title": await page.title()})
            with trace.span("dom_validation"):
                await inject_scraper(page, SCRAPER)
                counts = await page.evaluate(
                    """() => ({
                      chat_list: document.querySelectorAll('#pane-side [role="listitem"], #pane-side [role="row"]').length,
                      main_data_id: document.querySelectorAll('div#main [data-id]').length,
                      main_present: Boolean(document.querySelector('div#main')),
                      pane_present: Boolean(document.querySelector('#pane-side')),
                    })"""
                )
                trace.event("selector_counts", counts)
            incremental_run = not (conversations or name or updated_since or updated_until or since or until)
            checked_state = load_checked_state() if incremental_run else {}
            stop_at = incremental_stop_time() if incremental_run else None
            if stop_at:
                eprint(
                    f"incremental: scanning chat list until {stop_at.date()} "
                    f"(latest local backup minus {INCREMENTAL_LOOKBACK_DAYS}d buffer; use explicit filters to override)"
                )
            with trace.span("scanning", {"incremental": incremental_run, "stop_at": stop_at.isoformat() if stop_at else ""}):
                chats = await iter_chats(page, max_scan, stop_at, checked_state if incremental_run else None)
                trace.event("chat_list_stats", {"chats": len(chats), "sorted_time_violations": len(sorted_time_violations(chats))})
            selected = []
            for chat in chats:
                title = chat["title"]
                conversation_id = chat.get("conversationId") or ""
                path = path_for(title, conversation_id)
                existing = load_jsonl(path)
                local_since = max_message_time(existing)
                list_time = chat_list_time(chat)
                effective_since = since or local_since
                matched = (not conversations or title in conversations) and (not name or name.lower() in title.lower())
                date_matched = (updated_since is None or list_time is None or list_time >= updated_since) and (updated_until is None or list_time is None or list_time < updated_until)
                incremental_window = not incremental_run or stop_at is None or list_time is None or list_time > stop_at
                stale = not path.exists() or list_time is None or local_since is None or list_time > local_since
                checked = incremental_run and stale and known_no_new_content(chat, checked_state)
                if matched and date_matched and incremental_window and not checked and (conversations or name or updated_since or updated_until or since or until or stale):
                    selected.append({**chat, "path": path, "since": effective_since, "local_rows": len(existing), "list_time": list_time, "local_since": local_since})
                if limit and len(selected) >= limit:
                    break
            run_stats["selected_chats"] = len(selected)
            trace.event("selection_stats", {"scanned_chats": len(chats), "selected_chats": len(selected)})
            if not selected and conversations:
                missing = conversations - {chat["title"] for chat in chats}
                if missing:
                    raise RuntimeError(f"conversation(s) not found in scanned chat list: {', '.join(sorted(missing))}")

            for pos, chat in enumerate(selected, 1):
                title = chat["title"]
                path = chat["path"]
                summary = {"conversation": title, "conversation_id": chat.get("conversationId") or "", "path": str(path), "event": "planned" if dry_run else "updated"}
                if dry_run:
                    emit(summary, format)
                    continue
                eprint(f"{pos}/{len(selected)}: {title}")
                expected_id = chat.get("conversationId") or ""
                with trace.span("opening_expanding", {"conversation_hash": obs.short_hash(chat_key(title, expected_id)), "position": pos}):
                    opened, fallback = await open_chat(page, title, expected_id, max_scan)
                    trace.event("open_chat_result", {"fallback_chosen": fallback, "opened": opened})
                if not opened:
                    run_stats["skipped_chats"] += 1
                    trace.event("chat_skipped", {"reason": "could-not-open", "conversation_hash": obs.short_hash(chat_key(title, expected_id))})
                    emit({**summary, "event": "skipped", "reason": "could-not-open"}, format)
                    continue
                run_stats["opened_chats"] += 1
                with trace.span("scrolling", {"conversation_hash": obs.short_hash(chat_key(title, expected_id))}):
                    messages, scroll = await scrape_open_chat(page, chat["since"], max_messages, max_scroll_rounds, settle_ms)
                conversation_id = scroll.get("conversation_id") or chat.get("conversationId") or ""
                chat_stats = {
                    "selected_chats": 1,
                    "opened_chats": 1,
                    "messages_seen": len(messages),
                    "local_rows": chat["local_rows"],
                    "newer_chat_list_activity": bool(chat["list_time"] and chat["local_since"] and chat["list_time"] > chat["local_since"]),
                    "expected_conversation_id": expected_id,
                    "opened_conversation_id": conversation_id,
                    **scroll,
                }
                anomalies = obs.classify_whatsapp_anomalies(chat_stats)
                if expected_id and conversation_id and conversation_id != expected_id:
                    run_stats["skipped_chats"] += 1
                    trace.event("chat_anomalies", {"anomalies": anomalies, "conversation_hash": obs.short_hash(chat_key(title, expected_id))})
                    emit({**summary, "event": "skipped", "reason": f"opened-different-conversation:{conversation_id}", "messages_seen": 0, "messages_kept": 0, "rows_changed": 0, "scroll": scroll}, format)
                    continue
                path = migrate_path(title, conversation_id) if conversation_id else path
                summary = {**summary, "conversation_id": conversation_id, "path": str(path)}
                with trace.span("validation"):
                    kept = filtered_messages(messages, since, until, max_messages)
                    run_stats["messages_seen"] += len(messages)
                    run_stats["messages_kept"] += len(kept)
                    trace.event("message_stats", {"conversation_hash": obs.short_hash(chat_key(title, conversation_id)), "messages_seen": len(messages), "messages_kept": len(kept), "missing_rates": obs.missing_rates(messages, ["messageId", "time"]), "scroll": scroll, "anomalies": anomalies})
                if not messages:
                    run_stats["skipped_chats"] += 1
                    emit({**summary, "event": "skipped", "reason": scroll.get("reason", "no-messages"), "messages_seen": 0, "messages_kept": 0, "rows_changed": 0, "scroll": scroll}, format)
                    continue
                before_rows = len(load_jsonl(path))
                with trace.span("writing", {"path": str(path), "before_rows": before_rows}):
                    changed = update_conversation(path, title, conversation_id, messages, since, until, max_messages)
                after_rows = len(load_jsonl(path))
                run_stats["rows_changed"] += changed
                trace.event("output_stats", {"path": str(path), "before_rows": before_rows, "after_rows": after_rows, "rows_changed": changed})
                if incremental_run:
                    local_since = max_message_time(load_jsonl(path))
                    checked_state[chat_key(title, conversation_id)] = chat_state({**chat, "conversationId": conversation_id}, chat["list_time"], local_since)
                    write_checked_state(checked_state)
                emit({**summary, "messages_seen": len(messages), "messages_kept": len(kept), "rows_changed": changed, "scroll": scroll}, format)
            dom = await obs.capture_dom_outline(page)
            await browser.close()
        run_anomalies = obs.classify_whatsapp_anomalies(run_stats)
        if run_anomalies:
            trace.write_zip("anomaly", {**run_stats, "status": "ok", "anomalies": run_anomalies}, dom)
        elif not obs.monthly_baseline_exists(cache_dir, trace.stamp):
            trace.write_zip("baseline", {**run_stats, "status": "ok"}, dom)
        trace.finish({**run_stats, "status": "ok", "anomalies": run_anomalies})
    except Exception as exc:
        trace.exception(exc)
        if page is not None:
            try:
                trace.write_zip("anomaly", {"status": "failed"}, await obs.capture_dom_outline(page))
            except Exception as zip_exc:
                trace.exception(zip_exc, during="failure_zip")
        trace.finish({"status": "failed", "error_type": type(exc).__name__, "error_message": str(exc)})
        raise


def emit(event: dict[str, Any], format: str) -> None:
    if format == "jsonl":
        print(compact_json(event), flush=True)
        return
    bits = [event["event"], event["conversation"]]
    if event.get("rows_changed") is not None:
        bits.append(f"changed={event['rows_changed']}")
    if event.get("messages_seen") is not None:
        bits.append(f"seen={event['messages_seen']}")
    if event.get("reason"):
        bits.append(str(event["reason"]))
    bits.append(f"-> {event['path']}")
    print(": ".join(bits), flush=True)


@app.command(help=__doc__)
def main(
    conversation: list[str] = typer.Option(None, "--conversation", "-c", help="Exact conversation title to back up. Repeatable."),
    name: str = typer.Option("", "--name", help="Case-insensitive substring filter on conversation titles."),
    since: str = typer.Option("", "--since", help="Inclusive message start: ISO, YYYY-MM-DD, 7d, 12h, or '2 months ago'."),
    until: str = typer.Option("", "--until", help="Exclusive message end: ISO or YYYY-MM-DD. Defaults to open-ended."),
    updated_since: str = typer.Option("", "--updated-since", help="Inclusive chat-list latest-message start."),
    updated_until: str = typer.Option("", "--updated-until", help="Exclusive chat-list latest-message end."),
    max_messages: int = typer.Option(0, "--max-messages", min=0, help="Maximum newest messages to update per conversation after date filtering."),
    limit: int = typer.Option(0, "--limit", "-n", min=0, help="Maximum conversations to process after filtering."),
    cdp_url: str = typer.Option(CDP_URL, "--cdp-url", help="Chrome DevTools Protocol URL."),
    out_dir: Path = typer.Option(OUT_DIR, "--out-dir", help="Directory for per-conversation JSONL files."),
    scraper: Path = typer.Option(SCRAPER, "--scraper", help="Built whatsappscraper.min.js bundle."),
    max_scan: int = typer.Option(120, "--max-scan", help="Maximum chat-list scroll pages to scan."),
    max_scroll_rounds: int = typer.Option(200, "--max-scroll-rounds", help="Maximum upward history scrolls per conversation."),
    settle_ms: int = typer.Option(900, "--settle-ms", help="Delay after each history scroll in milliseconds."),
    dry_run: bool = typer.Option(False, "--dry-run", help="List conversations that would be backed up."),
    format: str = typer.Option("text", "--format", help="text or jsonl."),
    describe_schema: bool = typer.Option(False, "--describe", help="Print machine-readable CLI/schema description and exit."),
) -> None:
    if describe_schema:
        print(compact_json(describe()))
        return
    if format not in {"text", "jsonl"}:
        raise typer.BadParameter("--format must be text or jsonl")
    if not scraper.exists():
        raise typer.BadParameter(f"scraper bundle not found: {scraper}")
    if since and until and parse_time(since) >= parse_time(until):
        raise typer.BadParameter("--since must be before --until")
    if updated_since and updated_until and parse_time(updated_since) >= parse_time(updated_until):
        raise typer.BadParameter("--updated-since must be before --updated-until")
    globals()["OUT_DIR"] = out_dir.expanduser()
    globals()["SCRAPER"] = scraper.expanduser()
    try:
        asyncio.run(
            run_backup(
                cdp_url,
                set(conversation or []),
                name,
                parse_time(since) if since else None,
                parse_time(until) if until else None,
                parse_time(updated_since) if updated_since else None,
                parse_time(updated_until) if updated_until else None,
                max_messages,
                limit,
                max_scan,
                max_scroll_rounds,
                settle_ms,
                dry_run,
                format,
            )
        )
    except Exception as exc:
        typer.echo(f"backupwhatsapp.py: {exc}", err=True)
        raise typer.Exit(1) from exc


if __name__ == "__main__":
    app()
