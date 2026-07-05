from __future__ import annotations

from contextlib import contextmanager
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import platform
import secrets
import subprocess
import sys
import time
import traceback
from typing import Any
from urllib.parse import urlsplit, urlunsplit
import zipfile

MAX_EVENT_BYTES = 64_000
MAX_EVENTS_IN_ZIP = 400
MAX_DOM_ITEMS = 300
PRIVATE_KEYS = {
    "authorization",
    "body",
    "contact",
    "contactname",
    "cookie",
    "headers",
    "messagetext",
    "name",
    "phone",
    "requestbody",
    "responsebody",
    "text",
    "token",
}


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def short_hash(value: Any) -> str:
    return hashlib.sha256(str(value).encode("utf-8", "replace")).hexdigest()[:12]


def clean_url(value: str) -> str:
    parts = urlsplit(value)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def redacted_string(value: str) -> dict[str, Any]:
    return {"redacted": True, "chars": len(value), "sha256": short_hash(value)}


def redact(value: Any, *, key: str = "", depth: int = 0) -> Any:
    if depth > 8:
        return "[max-depth]"
    normalized = key.lower().replace("_", "").replace("-", "")
    if normalized in PRIVATE_KEYS:
        return redacted_string(value) if isinstance(value, str) else "[redacted]"
    if isinstance(value, str):
        if key.lower() in {"url", "page_url", "request_url"} or value.startswith(("http://", "https://")):
            return clean_url(value)
        if len(value) > 500:
            return redacted_string(value)
        return value
    if isinstance(value, dict):
        return {str(k): redact(v, key=str(k), depth=depth + 1) for k, v in list(value.items())[:200]}
    if isinstance(value, list):
        return [redact(item, key=key, depth=depth + 1) for item in value[:500]]
    if isinstance(value, tuple):
        return [redact(item, key=key, depth=depth + 1) for item in value[:500]]
    return value


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{time.time_ns()}.tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(redact(value), ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    tmp.replace(path)


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = compact_json(redact(row))
    if len(line.encode("utf-8")) > MAX_EVENT_BYTES:
        line = compact_json(
            {
                "ts": row.get("ts"),
                "run_id": row.get("run_id"),
                "event": row.get("event"),
                "truncated": True,
                "sha256": short_hash(line),
                "bytes": len(line.encode("utf-8")),
            }
        )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def git_hash(cwd: Path | None = None) -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=cwd,
            capture_output=True,
            check=False,
            text=True,
            timeout=2,
        ).stdout.strip()
    except Exception:
        return ""


def month_from_stamp(stamp: str) -> str:
    return stamp[:7]


def safe_stamp(now: str | None = None) -> str:
    if now:
        return now.replace(":", "-")
    return utc_now().replace(microsecond=0).isoformat().replace("+00:00", "Z").replace(":", "-")


def stamp_to_iso(stamp: str) -> str:
    return f"{stamp[:13]}:{stamp[14:16]}:{stamp[17:]}" if len(stamp) >= 20 else stamp


def new_run(script: str, *, cache_dir: Path | None = None, args: dict[str, Any] | None = None, now: str | None = None) -> RunTrace:
    stamp = safe_stamp(now)
    run_id = f"{stamp}-{secrets.token_hex(3)}"
    root = cache_dir or Path(f"~/.cache/sanand-scripts/{script}").expanduser()
    return RunTrace(script=script, cache_dir=root, stamp=stamp, run_id=run_id, args=args or {})


class RunTrace:
    def __init__(self, script: str, cache_dir: Path, stamp: str, run_id: str, args: dict[str, Any]) -> None:
        self.script = script
        self.cache_dir = cache_dir
        self.stamp = stamp
        self.run_id = run_id
        self.started = time.monotonic()
        self.events_path = cache_dir / f"{month_from_stamp(stamp)}-runs.jsonl"
        self.latest_path = cache_dir / "latest.json"
        self.events: list[dict[str, Any]] = []
        self.errors: list[dict[str, Any]] = []
        self.counters: dict[str, Any] = {}
        self.event(
            "run_start",
            {
                "script": script,
                "args": args,
                "python": sys.version.split()[0],
                "platform": platform.platform(),
                "git": git_hash(Path.cwd()),
            },
        )

    def zip_path(self, kind: str) -> Path:
        return self.cache_dir / f"{self.run_id}-{kind}.zip"

    def event(self, name: str, data: dict[str, Any] | None = None) -> None:
        row = {
            "ts": utc_now().isoformat(),
            "run_id": self.run_id,
            "script": self.script,
            "event": name,
            **(data or {}),
        }
        self.events.append(redact(row))
        self.events = self.events[-MAX_EVENTS_IN_ZIP:]
        append_jsonl(self.events_path, row)

    @contextmanager
    def span(self, name: str, data: dict[str, Any] | None = None):
        start = time.monotonic()
        self.event("span_start", {"span": name, **(data or {})})
        try:
            yield
        except Exception as exc:
            self.exception(exc, span=name)
            raise
        finally:
            self.event("span_end", {"span": name, "duration_ms": round((time.monotonic() - start) * 1000, 1)})

    def exception(self, exc: BaseException, **data: Any) -> None:
        details = {
            "type": type(exc).__name__,
            "message": str(exc),
            "stack": "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[-16000:],
            **data,
        }
        self.errors.append(redact(details))
        self.event("exception", details)

    def finish(self, summary: dict[str, Any]) -> None:
        payload = {
            "run_id": self.run_id,
            "script": self.script,
            "started_at": stamp_to_iso(self.stamp),
            "duration_ms": round((time.monotonic() - self.started) * 1000, 1),
            "events_path": str(self.events_path),
            "errors": self.errors[-20:],
            **self.counters,
            **summary,
        }
        atomic_write_json(self.latest_path, payload)
        self.event("run_finish", summary)

    def write_zip(self, kind: str, manifest: dict[str, Any], dom: dict[str, Any] | None = None, aria: Any | None = None) -> Path:
        path = self.zip_path(kind)
        path.parent.mkdir(parents=True, exist_ok=True)
        clean_manifest = redact({"run_id": self.run_id, "script": self.script, "kind": kind, **manifest})
        dom_payload = dict(dom) if isinstance(dom, dict) else dom
        if aria is None and isinstance(dom_payload, dict) and "aria_snapshot" in dom_payload:
            aria = dom_payload.pop("aria_snapshot")
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            archive.writestr("manifest.json", json.dumps(clean_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
            archive.writestr("events.jsonl", "".join(compact_json(event) + "\n" for event in self.events[-MAX_EVENTS_IN_ZIP:]))
            if dom_payload is not None:
                archive.writestr("dom-outline.json", json.dumps(redact(dom_payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n")
            if aria is not None:
                archive.writestr("aria-snapshot.json", json.dumps(redact(aria), ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        self.event("zip_written", {"kind": kind, "path": str(path)})
        return path


def missing_rates(rows: list[dict[str, Any]], fields: list[str]) -> dict[str, float]:
    if not rows:
        return {field: 1.0 for field in fields}
    return {field: round(sum(1 for row in rows if not row.get(field)) / len(rows), 4) for field in fields}


def classify_linkedin_anomalies(stats: dict[str, Any]) -> list[str]:
    anomalies: list[str] = []
    if stats.get("post_containers", 0) and stats.get("post_rows", 0) == 0:
        anomalies.append("linkedin_containers_without_rows")
    if (
        stats.get("post_containers", 0)
        and stats.get("post_rows", 0) < stats.get("post_containers", 0) * 0.5
        and not (stats.get("limit") and stats.get("post_rows", 0) >= stats.get("limit"))
    ):
        anomalies.append("linkedin_fewer_rows_than_containers")
    if stats.get("previous_selector") and stats.get("selector_used") != stats.get("previous_selector"):
        anomalies.append("linkedin_selector_candidate_changed")
    for field, rate in (stats.get("missing_rates") or {}).items():
        if rate >= 0.8:
            anomalies.append(f"linkedin_missing_{field}")
    return anomalies


def classify_whatsapp_anomalies(stats: dict[str, Any]) -> list[str]:
    anomalies: list[str] = []
    if stats.get("selected_chats") and stats.get("opened_chats") and stats.get("messages_seen", 0) == 0 and stats.get("local_rows", 0):
        anomalies.append("whatsapp_zero_messages_with_existing_history")
    if stats.get("newer_chat_list_activity") and stats.get("messages_seen", 0) == 0:
        anomalies.append("whatsapp_zero_messages_with_newer_activity")
    if stats.get("expected_conversation_id") and stats.get("opened_conversation_id") and stats["expected_conversation_id"] != stats["opened_conversation_id"]:
        anomalies.append("whatsapp_opened_different_conversation")
    if stats.get("parser_dom_count") is not None and stats.get("scraper_dom_count") is not None and stats["parser_dom_count"] != stats["scraper_dom_count"]:
        anomalies.append("whatsapp_parser_dom_count_disagrees")
    if stats.get("history_scroller_found") is False:
        anomalies.append("whatsapp_no_history_scroller")
    if stats.get("selected_chats") and stats.get("skipped_chats") == stats.get("selected_chats"):
        anomalies.append("whatsapp_all_selected_items_skipped")
    return anomalies


def sanitize_args(args: dict[str, Any]) -> dict[str, Any]:
    clean = {}
    for key, value in args.items():
        if key in {"conversation", "name", "username"}:
            clean[f"{key}_hash"] = short_hash(value)
            clean[f"{key}_present"] = bool(value)
            continue
        clean[key] = str(value) if isinstance(value, Path) else value
    return redact(clean)


def latest_summary(cache_dir: Path) -> dict[str, Any]:
    path = cache_dir / "latest.json"
    try:
        return json.loads(path.read_text()) if path.exists() else {}
    except Exception:
        return {}


def monthly_baseline_exists(cache_dir: Path, stamp: str) -> bool:
    return any(cache_dir.glob(f"{stamp[:7]}-*-baseline.zip"))


async def browser_versions(browser: Any) -> dict[str, Any]:
    try:
        return {"browser_version": await browser.version()}
    except Exception as exc:
        return {"browser_version_error": f"{type(exc).__name__}: {exc}"}


def attach_page_observers(page: Any, trace: RunTrace) -> None:
    def console(message: Any) -> None:
        if getattr(message, "type", "") in {"error", "warning"}:
            trace.event("console_error", {"level": message.type, "message": getattr(message, "text", "")})

    def pageerror(error: Any) -> None:
        trace.event("page_error", {"message": str(error)})

    def requestfailed(request: Any) -> None:
        trace.event("request_failed", {"url": getattr(request, "url", ""), "failure": request.failure})

    page.on("console", console)
    page.on("pageerror", pageerror)
    page.on("requestfailed", requestfailed)


DOM_OUTLINE_JS = """
(limit) => {
  const interesting = [...document.querySelectorAll('main, [role], article, button, a, input, [data-urn], [data-id], #pane-side, div#main')]
    .slice(0, limit);
  return {
    url: location.href,
    title: document.title,
    counts: {
      articles: document.querySelectorAll('article').length,
      roles: document.querySelectorAll('[role]').length,
      dataUrn: document.querySelectorAll('[data-urn]').length,
      dataId: document.querySelectorAll('[data-id]').length,
      buttons: document.querySelectorAll('button').length,
    },
    outline: interesting.map((el, index) => ({
      index,
      tag: el.tagName.toLowerCase(),
      role: el.getAttribute('role') || '',
      idPresent: Boolean(el.id),
      classHash: el.className ? String(el.className).split(/\\s+/).slice(0, 8).join('.') : '',
      dataUrnPresent: Boolean(el.getAttribute('data-urn')),
      dataIdPresent: Boolean(el.getAttribute('data-id')),
      ariaChars: (el.getAttribute('aria-label') || '').length,
      textChars: (el.innerText || el.textContent || '').length,
      childCount: el.children.length,
    })),
  };
}
"""


async def capture_dom_outline(page: Any, *, include_aria: bool = True) -> dict[str, Any]:
    dom = await page.evaluate(DOM_OUTLINE_JS, MAX_DOM_ITEMS)
    if include_aria:
        try:
            aria = await page.locator("body").aria_snapshot(timeout=1500)
            dom["aria_snapshot"] = aria
        except Exception as exc:
            dom["aria_snapshot_error"] = f"{type(exc).__name__}: {exc}"
    return dom
