#!/usr/bin/env -S uv run --script

# /// script
# requires-python = ">=3.14"
# dependencies = ["fastmcp>=3.4,<4"]
# ///

# Usage: uv run mcpserver.py
#   Exposes an MCP server on localhost:2428 for local file work and bash commands.
#   curl localhost:2428/mcp2428 to test
# Test with
#   just test-mcpserver

import asyncio
import base64
import errno
import hashlib
import json
import mimetypes
import os
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, TypedDict
from urllib import parse, request

from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_context, get_http_request
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools.tool import ToolResult
from mcp.types import (
    BlobResourceContents,
    EmbeddedResource,
    TextContent,
    TextResourceContents,
)

SERVER_INSTRUCTIONS = """Prefer read_file/read_files/search/list_directory/file_info for local inspection and edit_block for exact text edits; use bash only when those tools cannot express the operation cleanly. Never automatically retry bash or a write after timeout/connection loss because side effects may already have happened. Re-read before retrying edit_block conflicts. Permission/read-only errors usually require changing the path or mount, not repeated retries."""
mcp = FastMCP("Local files and shell commands", instructions=SERVER_INSTRUCTIONS)
MCP_PATH = "/mcp2428"
LOG_DIR = Path.home() / ".local/share/sanand-scripts/mcpserver"
MAX_LINE_BYTES = 50 * 1024
TRIM_PREFIX_BYTES = 49 * 1024
TRIM_MARKER = "... [trimmed to 50KB/line] ..."
MAX_TOTAL_OUTPUT_BYTES = 512 * 1024
TOTAL_OUTPUT_HEAD_BYTES = 384 * 1024
TOTAL_TRIM_MARKER = "\n... [omitted {bytes} bytes to keep total output under 512 KiB] ...\n"
MAX_UPLOAD_BYTES = int(os.environ.get("MCPSERVER_MAX_UPLOAD_BYTES", str(100 * 1024 * 1024)))
DEFAULT_READ_LINES = 200
MAX_READ_LINES = 1000
MAX_READ_BYTES = 128 * 1024
MAX_READ_FILES = 12
CONSOLE_RESPONSE_CHARS = int(os.environ.get("MCPSERVER_CONSOLE_RESPONSE_CHARS", "1600"))
DEFAULT_LIST_ENTRIES = 200
MAX_LIST_ENTRIES = 1000
DEFAULT_LIST_PER_DIRECTORY = 80
MAX_LIST_DEPTH = 4
SEARCH_TIMEOUT_SECONDS = 15
SEARCH_CANDIDATE_CAP = 200
TRANSIENT_RETRY_DELAYS = (0.05, 0.2)
TRANSIENT_ERRNOS = {errno.EINTR, errno.EAGAIN, errno.EBUSY, getattr(errno, "ESTALE", 116)}
IMPORTANT_FILES = ("README.md", "AGENTS.md", "CLAUDE.md", "pyproject.toml", "package.json", "Justfile", "Makefile", "Dockerfile")
LOW_SIGNAL_DIRS = {"__pycache__", "node_modules", ".venv", "venv", ".git", ".cache"}
BASH_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="mcpserver-bash")


def output_schema(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


DOWNLOAD_FILE_OUTPUT_SCHEMA = output_schema(
    {
        "path": {"type": "string"},
        "mime_type": {"type": "string"},
        "encoding": {"type": "string", "enum": ["utf-8", "base64"]},
        "size": {"type": "integer", "minimum": 0},
        "bytes_read": {"type": "integer", "minimum": 0},
    }
)
BASH_OUTPUT_SCHEMA = output_schema(
    {
        "server_start_id": {"type": "string"},
        "request_id": {"type": ["string", "null"]},
        "started_at": {"type": "string"},
        "finished_at": {"type": "string"},
        "duration_ms": {"type": "number", "minimum": 0},
        "exit_code": {"type": ["integer", "null"]},
        "status": {"type": "string", "enum": ["success", "failed", "timeout", "error"]},
        "ok": {"type": "boolean"},
        "timed_out": {"type": "boolean"},
        "error": {"type": ["string", "null"]},
        "error_code": {"type": ["string", "null"]},
        "retryable": {"type": "boolean"},
        "cwd": {"type": "string"},
        "output": {"type": "string"},
        "output_path": {"type": ["string", "null"]},
        "stdout_bytes": {"type": "integer", "minimum": 0},
        "stderr_bytes": {"type": "integer", "minimum": 0},
        "output_bytes_before_limits": {"type": "integer", "minimum": 0},
        "output_bytes_after_limits": {"type": "integer", "minimum": 0},
        "line_trim_count": {"type": "integer", "minimum": 0},
        "line_trim_omitted_bytes": {"type": "integer", "minimum": 0},
        "total_limit_omitted_bytes": {"type": "integer", "minimum": 0},
        "total_truncation_omitted_bytes": {"type": "integer", "minimum": 0},
    }
)
SERVER_START_ID = uuid.uuid4().hex
RATE_TAGS = {
    "intent_miss",
    "source_miss",
    "version_miss",
    "too_much_evidence",
    "too_little_evidence",
    "tool_failure",
    "unsupported_conclusion",
}
MOUNTED_PATHS = [
    ("~/code/scripts/agents/*/SKILL.md", "coding + thinking skills"),
    ("~/code/blog/pages/skills/*/SKILL.md", "thinking skills"),
    (
        "~/Dropbox/notes/transcripts/YYYY-MM-DD*.md",
        "date-window by filename, then read narrow ranges",
    ),
    ("~/Dropbox/notes/about/*.md", "people or company specific notes"),
    ("~/Dropbox/notes/", "notes archive; recently edited files are useful"),
    (
        "~/Documents/data/s.anand@gramener.com/",
        "work email, chat, calendar exports. Use `gws` for latest",
    ),
    (
        "~/Documents/data/root.node@gmail.com/",
        "personal email, calendar exports. Use `gws` for latest",
    ),
    (
        "~/Documents/data/whatsapp/",
        "WhatsApp exports. Use `jaq` fields `.time`, `.author`, `.text`",
    ),
    (
        "~/Documents/data/context/context.sqlite",
        "cross-source context index; query via `uv run context.py ...`, then deep-read returned locators",
    ),
    (
        "~/Documents/data/browsing-history.db",
        "SELECT url, timestamp, visit_count, ... FROM activity",
    ),
    (
        "~/Documents/Mail/{*.mbox,mail-index.sqlite}",
        "2005-2025 email archives (use ?immutable=1)",
    ),
    ("~/Documents/data/linkedin-invites.json", "LinkedIn invites"),
    ("~/Documents/chatgpt/", "ChatGPT chat dumps"),
    ("~/Documents/claude/", "Claude chat dumps"),
    ("~/code/talks/README.md", "talk transcripts, slides"),
    ("~/code/datastories/config.json", "data stories"),
    ("~/code/llmdemos/config.json", "innovation team demos"),
    ("~/code/llmevals/README.md", "LLM evals"),
    (
        "~/code/blog/description.md",
        '20K files, 5K posts. Search for "- llm" for AI-related posts',
    ),
    ("~/code/til/README.md", "things I learnt"),
    ("~/code/README.md", "code repos"),
    ("~/r2/files/podcast", "podcasts written for myself"),
    ("~/Documents/activities/", "daily activity logs"),
]


class ChatGPTUpload(TypedDict):
    """File reference injected by ChatGPT for an openai/fileParams parameter."""

    download_url: str
    file_id: str
    file_name: str
    mime_type: str


def fit_utf8_prefix(text: str, byte_count: int) -> str:
    return text.encode()[:byte_count].decode(errors="ignore")


def fit_utf8_suffix(text: str, byte_count: int) -> str:
    return text.encode()[-byte_count:].decode(errors="ignore")


def trim_long_line(line: str) -> tuple[str, int]:
    original_bytes = len(line.encode())
    if original_bytes <= MAX_LINE_BYTES:
        return line, 0
    suffix_bytes = MAX_LINE_BYTES - TRIM_PREFIX_BYTES - len(TRIM_MARKER.encode())
    trimmed = fit_utf8_prefix(line, TRIM_PREFIX_BYTES) + TRIM_MARKER + fit_utf8_suffix(line, suffix_bytes)
    return trimmed, original_bytes - len(trimmed.encode())


def trim_long_lines_with_stats(text: str) -> tuple[str, int, int]:
    chunks = []
    trim_count = 0
    omitted_bytes = 0
    for line in text.splitlines(keepends=True):
        trimmed, omitted = trim_long_line(line.removesuffix("\n"))
        chunks.append(trimmed + ("\n" if line.endswith("\n") else ""))
        if omitted:
            trim_count += 1
            omitted_bytes += omitted
    return "".join(chunks), trim_count, omitted_bytes


def trim_long_lines(text: str) -> str:
    return trim_long_lines_with_stats(text)[0]


def limit_total_output(text: str) -> tuple[str, int]:
    data = text.encode()
    if len(data) <= MAX_TOTAL_OUTPUT_BYTES:
        return text, 0
    omitted = len(data) - MAX_TOTAL_OUTPUT_BYTES
    while True:
        marker = TOTAL_TRIM_MARKER.format(bytes=omitted)
        tail_bytes = MAX_TOTAL_OUTPUT_BYTES - TOTAL_OUTPUT_HEAD_BYTES - len(marker.encode())
        limited = fit_utf8_prefix(text, TOTAL_OUTPUT_HEAD_BYTES) + marker + fit_utf8_suffix(text, tail_bytes)
        new_omitted = len(data) - len(limited.encode())
        if new_omitted == omitted:
            return limited, omitted
        omitted = new_omitted


def iso_timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def markdown_code_block(text: str) -> str:
    fence = "```"
    while fence in text:
        fence += "`"
    return f"{fence}\n{text}\n{fence}"


def markdown_json(data: Any) -> str:
    return markdown_code_block(json.dumps(data, indent=2, default=str, ensure_ascii=False))


def http_request_info() -> dict[str, Any] | None:
    with suppress(RuntimeError):
        request = get_http_request()
        scope = request.scope
        headers = {
            name.decode("latin-1", errors="replace").lower(): value.decode("latin-1", errors="replace")
            for name, value in scope.get("headers", [])
        }
        info: dict[str, Any] = {
            "path": scope.get("path"),
            "user_agent": headers.get("user-agent"),
            "session_id": headers.get("mcp-session-id"),
            "protocol_version": headers.get("mcp-protocol-version"),
        }
        return info
    return None


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, separators=(",", ":"), default=str, ensure_ascii=False) + "\n")


def write_markdown_log(event: dict[str, Any]) -> None:
    operation = event["operation"]
    if operation not in {"tool_call", "bash", "download_file", "save_file"}:
        return
    now = datetime.now(UTC)
    timestamp = now.strftime("%Y-%m-%dT%H-%M-%S.%f")
    sections = [f"# mcpserver {operation} log {timestamp}"]
    if operation == "tool_call":
        sections += [
            "## Tool",
            markdown_code_block(event["tool"]),
            "## Arguments",
            markdown_json(event["arguments"]),
            "## Response",
            markdown_json(event["response"]),
            "## Duration",
            f"{event['duration_ms']} ms",
        ]
    if operation == "bash":
        sections += [
            "## Command",
            markdown_code_block(event["commands"]),
            "## Request",
            markdown_json(event["request"]),
            "## Output",
            markdown_code_block(event["output"]),
        ]
    if operation != "tool_call":
        sections += ["## Result", markdown_json(event["result"])]
    base = LOG_DIR / "tool-calls" if operation == "tool_call" else LOG_DIR
    path = base / now.strftime("%Y-%m") / f"{timestamp}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n\n".join(sections) + "\n", encoding="utf-8")


def write_request_log(event: dict[str, Any]) -> None:
    http = event.get("http") or {}
    record = {
        "server_start_id": event["server_start_id"],
        "timestamp": event["timestamp"],
        "session_id": http.get("session_id"),
        "mcp_method": event.get("method"),
        "http_path": http.get("path"),
        "user_agent": http.get("user_agent"),
        "protocol_version": http.get("protocol_version") or event.get("protocol_version"),
        "client_name": event.get("client_name"),
        "client_version": event.get("client_version"),
        "client_capabilities": event.get("client_capabilities"),
        "duration_ms": event.get("duration_ms"),
        "result": event.get("result"),
        "error": event.get("error"),
    }
    append_jsonl(
        LOG_DIR / f"requests-{datetime.now():%Y-%m-%d}.jsonl",
        {key: value for key, value in record.items() if value is not None},
    )


def log_event(operation: str, **data: Any) -> dict[str, Any]:
    """Append one compact, machine-readable tool event."""
    http = http_request_info()
    event = {
        "timestamp": iso_timestamp(),
        "server_start_id": SERVER_START_ID,
        "operation": operation,
        **({"http": http} if http else {}),
        **data,
    }
    append_jsonl(LOG_DIR / "events.jsonl", event)
    if operation == "request":
        write_request_log(event)
    else:
        write_markdown_log(event)
    if http and http.get("session_id"):
        (LOG_DIR / "latest-session").write_text(str(http["session_id"]), encoding="utf-8")
    return event




ANSI = {
    "cyan": "\033[36m",
    "green": "\033[32m",
    "red": "\033[31m",
    "yellow": "\033[33m",
    "dim": "\033[2m",
    "reset": "\033[0m",
}


def console_color(text: str, color: str) -> str:
    if not sys.stderr.isatty() or "NO_COLOR" in os.environ:
        return text
    return f"{ANSI[color]}{text}{ANSI['reset']}"


def truncate_middle(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    marker_template = "\n… {omitted} chars omitted …\n"
    marker = marker_template.format(omitted=0)
    keep = max(0, max_chars - len(marker))
    head = keep // 2
    tail = keep - head
    omitted = len(text) - head - tail
    marker = marker_template.format(omitted=omitted)
    overflow = len(marker) + head + tail - max_chars
    if overflow > 0:
        tail = max(0, tail - overflow)
    return text[:head] + marker + (text[-tail:] if tail else "")


def middle_items(items: list[str], max_items: int) -> list[str]:
    if len(items) <= max_items:
        return items
    head = max_items // 2
    tail = max_items - head
    omitted = len(items) - max_items
    return items[:head] + [f"… {omitted} entries omitted …"] + items[-tail:]


def read_files_preview(files: list[dict[str, Any]], max_chars: int) -> str:
    headers = []
    bodies = []
    for item in files:
        path = console_path(item["path"])
        if "content" in item:
            headers.append(
                f"━━ {path} • lines {item.get('start_line')}–{item.get('end_line')} ━━"
            )
            bodies.append(item.get("content", ""))
        else:
            headers.append(f"━━ {path} • ERROR ━━")
            bodies.append(pretty_json(item.get("error")))

    separators = 2 * max(0, len(files) - 1)
    body_budget = max_chars - sum(len(header) + 1 for header in headers) - separators
    per_file = body_budget // len(files) if files else 0
    blocks = []
    for header, body in zip(headers, bodies):
        excerpt = truncate_middle(body, per_file) if per_file >= 60 else ""
        blocks.append(header + (f"\n{excerpt}" if excerpt else ""))
    return "\n\n".join(blocks)


def pretty_json(data: Any) -> str:
    return json.dumps(data, indent=2, default=str, ensure_ascii=False)


def indent_lines(text: str, prefix: str = "    ") -> str:
    return "\n".join(prefix + line for line in text.splitlines())


def human_size(size: int | None) -> str:
    if size is None:
        return "?"
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(value) < 1024 or unit == "TB":
            return f"{int(value)} B" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def human_datetime(value: str | None) -> str:
    if not value:
        return "?"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone()
        return f"{parsed.day} {parsed:%b %Y %H:%M}"
    except ValueError:
        return value


def console_path(value: str) -> str:
    return display_path(Path(value).expanduser())


def plural(value: int, singular: str, plural_word: str | None = None) -> str:
    return singular if value == 1 else plural_word or singular + "s"


def format_tool_request(tool: str, arguments: dict[str, Any]) -> list[str]:
    path = arguments.get("path")
    if tool in {"file_info", "download_file"} and path:
        suffix = " • sha256" if tool == "file_info" and arguments.get("sha256") else ""
        return [f"{console_path(path)}{suffix}"]
    if tool == "read_file" and path:
        start = arguments.get("start_line", 1)
        count = arguments.get("line_count", DEFAULT_READ_LINES)
        return [f"{console_path(path)} • lines {start}–{start + count - 1}"]
    if tool == "read_files":
        paths = arguments.get("paths") or []
        start = arguments.get("start_line", 1)
        count = arguments.get("line_count", 100)
        return [
            f"{len(paths)} files • lines {start}–{start + count - 1}",
            *[console_path(value) for value in paths],
        ]
    if tool == "list_directory" and path:
        extras = [
            f"depth {arguments.get('depth', 2)}",
            f"max {arguments.get('max_entries', DEFAULT_LIST_ENTRIES)}",
        ]
        if arguments.get("include_hidden"):
            extras.append("hidden")
        return [f"{console_path(path)} • {' • '.join(extras)}"]
    if tool == "search":
        query = json.dumps(arguments.get("query", ""), ensure_ascii=False)
        where = console_path(arguments.get("path", "."))
        extras = [arguments.get("mode", "content")]
        if arguments.get("file_glob"):
            extras.append(f"glob {arguments['file_glob']}")
        if arguments.get("regex"):
            extras.append("regex")
        if arguments.get("case_sensitive"):
            extras.append("case-sensitive")
        if arguments.get("hidden"):
            extras.append("hidden")
        if "max_results" in arguments:
            extras.append(f"max {arguments['max_results']}")
        return [f"{query} in {where} • {' • '.join(extras)}"]
    if tool == "edit_block" and path:
        expected = arguments.get("expected_replacements", 1)
        return [
            f"{console_path(path)} • expect {expected} {plural(expected, 'replacement')}",
            f"old:\n{arguments.get('old_string', '')}",
            f"new:\n{arguments.get('new_string', '')}",
        ]
    if tool == "bash":
        cwd = console_path(arguments["cwd"]) if arguments.get("cwd") else display_path(Path.cwd())
        timeout = arguments.get("timeout_ms", 30_000) / 1000
        return [f"{cwd} • timeout {timeout:g}s", arguments.get("commands", "")]
    if tool == "save_file":
        file = arguments.get("file") or {}
        source = file.get("file_name") or file.get("file_id") or "upload"
        destination = arguments.get("destination", "?")
        suffix = " • overwrite" if arguments.get("overwrite") else ""
        return [f"{source} → {console_path(destination)}{suffix}"]
    return [pretty_json(arguments)]


def format_error_response(
    tool: str, data: dict[str, Any], duration_ms: float
) -> list[str] | None:
    error = data.get("error")
    if not isinstance(error, dict):
        return None
    code = error.get("code", "error")
    message = error.get("message", "")
    retry = " • retryable" if error.get("retryable") else ""
    return [f"{tool} {duration_ms:.1f} ms • {code}{retry} • {message}"]


def format_tool_response(
    tool: str,
    response: dict[str, Any],
    duration_ms: float,
    is_error: bool,
) -> list[str]:
    data = response.get("structured_content")
    if not isinstance(data, dict):
        return [f"{tool} {duration_ms:.1f} ms", pretty_json(response.get("content"))]
    if is_error:
        formatted = format_error_response(tool, data, duration_ms)
        if formatted:
            return formatted

    if tool == "file_info":
        modified = human_datetime(data.get("modified"))
        if data.get("type") == "directory":
            entries = data.get("entry_count")
            detail = f"{entries:,} {plural(entries, 'entry', 'entries')}" if entries is not None else "directory"
        else:
            parts = [human_size(data.get("size"))]
            if data.get("line_count") is not None:
                parts.append(f"{data['line_count']:,} lines")
            detail = " • ".join(parts)
        if data.get("sha256"):
            detail += f" • sha256 {data['sha256'][:12]}…"
        return [f"{tool} {duration_ms:.1f} ms • {detail} • modified {modified}"]

    if tool == "read_file":
        content = data.get("content", "")
        parts = [
            f"{data.get('line_count', 0):,} lines",
            human_size(len(content.encode())),
        ]
        if data.get("next_start_line"):
            parts.append(f"more→{data['next_start_line']}")
        elif data.get("byte_limited"):
            parts.append("byte-limited")
        return [
            f"{tool} {duration_ms:.1f} ms • {' • '.join(parts)}",
            truncate_middle(content, CONSOLE_RESPONSE_CHARS),
        ]

    if tool == "read_files":
        files = data.get("files") or []
        good = [item for item in files if not item.get("error") and item.get("content") is not None]
        errors = len(files) - len(good)
        lines = sum(item.get("line_count", 0) for item in good)
        size = sum(len(item.get("content", "").encode()) for item in good)
        parts = [
            f"{len(good)}/{len(files)} files",
            f"{lines:,} lines",
            human_size(size),
        ]
        if errors:
            parts.append(f"{errors} {plural(errors, 'error')}")
        return [
            f"{tool} {duration_ms:.1f} ms • {' • '.join(parts)}",
            read_files_preview(files, CONSOLE_RESPONSE_CHARS),
        ]

    if tool == "list_directory":
        entries = data.get("entries") or []
        suffix = " • truncated" if data.get("truncated") else ""
        sample = " · ".join(
            middle_items([item.get("path", "") for item in entries], 12)
        )
        lines = [f"{tool} {duration_ms:.1f} ms • {len(entries):,} entries • depth {data.get('depth')}{suffix}"]
        return lines + ([sample] if sample else [])

    if tool == "search":
        matched_files = data.get("matched_files", 0)
        if data.get("broad"):
            bound = "≥" if data.get("matched_files_is_lower_bound") else ""
            groups = " · ".join(
                f"{item['group']}:{item['count']}" for item in (data.get("top_groups") or [])[:6]
            )
            sample = "\n".join(console_path(path) for path in (data.get("sample_files") or [])[:8])
            detail = "\n".join(value for value in (groups, sample) if value)
            lines = [
                f"{tool} {duration_ms:.1f} ms • broad • {bound}{matched_files:,} matching files"
            ]
            return lines + ([detail] if detail else [])
        matches = data.get("matches") or []
        total = data.get("total_matches", len(matches))
        preview = "\n".join(
            (
                f"{console_path(item['path'])}:{item['line']}  {item['text']}"
                if "line" in item
                else console_path(item["path"])
            )
            for item in matches
        )
        return [
            f"{tool} {duration_ms:.1f} ms • {total:,} {plural(total, 'match', 'matches')} "
            f"in {matched_files:,} {plural(matched_files, 'file')} • showing {len(matches):,}",
            preview,
        ]

    if tool == "edit_block":
        count = data.get("replacements", 0)
        return [
            f"{tool} {duration_ms:.1f} ms • {count} {plural(count, 'replacement')} "
            f"at line {data.get('first_line')}",
            data.get("preview", ""),
        ]

    if tool == "bash":
        status = data.get("status", "?")
        exit_code = data.get("exit_code")
        parts = [status]
        if exit_code is not None:
            parts.append(f"exit {exit_code}")
        if data.get("timed_out"):
            parts.append("timed out")
        return [f"{tool} {duration_ms:.1f} ms • {' • '.join(parts)}", data.get("output", "")]

    if tool in {"download_file", "save_file"}:
        destination = data.get("path")
        detail = human_size(data.get("size"))
        if destination:
            detail += f" • {console_path(destination)}"
        return [f"{tool} {duration_ms:.1f} ms • {detail}"]

    return [f"{tool} {duration_ms:.1f} ms", pretty_json(data)]


def tool_result_record(result: ToolResult) -> dict[str, Any]:
    record: dict[str, Any] = {
        "is_error": result.is_error,
        "structured_content": result.structured_content,
        "meta": result.meta,
    }
    if result.structured_content is None:
        record["content"] = [
            block.model_dump(mode="json") if hasattr(block, "model_dump") else str(block)
            for block in result.content
        ]
    return record


def console_tool_request(tool: str, arguments: dict[str, Any]) -> None:
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    lines = format_tool_request(tool, arguments)
    headline = f"{timestamp} ▶ {tool}" + (f" {lines[0]}" if lines else "")
    print(console_color(headline, "cyan"), file=sys.stderr)
    if len(lines) > 1:
        print(console_color(indent_lines("\n".join(lines[1:])), "dim"), file=sys.stderr)
    sys.stderr.flush()


def console_tool_response(
    tool: str,
    response: dict[str, Any],
    duration_ms: float,
    is_error: bool,
) -> None:
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    symbol, color = ("✗", "red") if is_error else ("✓", "green")
    lines = format_tool_response(tool, response, duration_ms, is_error)
    print(console_color(f"{timestamp} {symbol} {lines[0]}", color), file=sys.stderr)
    if len(lines) > 1 and lines[1]:
        preview = truncate_middle("\n".join(lines[1:]), CONSOLE_RESPONSE_CHARS)
        print(console_color(indent_lines(preview), "dim"), file=sys.stderr)
    sys.stderr.flush()


class ToolAuditMiddleware(Middleware):
    async def on_call_tool(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, ToolResult],
    ) -> ToolResult:
        tool = context.message.name
        arguments = json.loads(
            json.dumps(context.message.arguments or {}, default=str, ensure_ascii=False)
        )
        console_tool_request(tool, arguments)
        start = time.monotonic()
        try:
            result = await call_next(context)
        except Exception as error:
            duration_ms = round((time.monotonic() - start) * 1000, 3)
            response = {
                "is_error": True,
                "structured_content": structured_tool_error(error)
                if isinstance(error, ToolError)
                else {"ok": False, "error": {"code": "exception", "message": repr(error)}},
                "meta": None,
            }
            log_event(
                "tool_call",
                tool=tool,
                arguments=arguments,
                response=response,
                is_error=True,
                duration_ms=duration_ms,
            )
            console_tool_response(tool, response, duration_ms, True)
            raise

        duration_ms = round((time.monotonic() - start) * 1000, 3)
        response = tool_result_record(result)
        log_event(
            "tool_call",
            tool=tool,
            arguments=arguments,
            response=response,
            is_error=result.is_error,
            duration_ms=duration_ms,
        )
        console_tool_response(tool, response, duration_ms, result.is_error)
        return result


def client_metadata(context: MiddlewareContext[Any]) -> dict[str, Any]:
    message = context.message.model_dump()
    params = message.get("params") or {}
    client = params.get("clientInfo") or {}
    return {
        key: value
        for key, value in {
            "protocol_version": params.get("protocolVersion"),
            "client_name": client.get("name"),
            "client_version": client.get("version"),
            "client_capabilities": params.get("capabilities"),
        }.items()
        if value is not None
    }




class LocalToolError(ToolError):
    """Tool failure with machine-readable recovery semantics."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        path: str | Path | None = None,
        suggestion: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.path = str(path) if path is not None else None
        self.suggestion = suggestion


def structured_tool_error(error: ToolError) -> dict[str, Any]:
    if isinstance(error, LocalToolError):
        details = {
            "code": error.code,
            "retryable": error.retryable,
            "message": str(error),
            "path": error.path,
            "suggestion": error.suggestion,
        }
    else:
        details = {
            "code": "tool_error",
            "retryable": False,
            "message": str(error),
            "path": None,
            "suggestion": None,
        }
    return {
        "ok": False,
        "error": {key: value for key, value in details.items() if value is not None},
    }


class StructuredToolErrorsMiddleware(Middleware):
    async def on_call_tool(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, ToolResult],
    ) -> ToolResult:
        try:
            return await call_next(context)
        except ToolError as error:
            data = structured_tool_error(error)
            return ToolResult(
                content=[TextContent(type="text", text=json.dumps(data, separators=(",", ":")))],
                structured_content=data,
                is_error=True,
            )


class RequestLogMiddleware(Middleware):
    async def on_request(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, Any],
    ) -> Any:
        start = time.monotonic()
        try:
            result = await call_next(context)
        except Exception as e:
            log_event(
                "request",
                method=context.method,
                **client_metadata(context),
                duration_ms=round((time.monotonic() - start) * 1000, 3),
                error=repr(e),
            )
            raise
        log_event(
            "request",
            method=context.method,
            **client_metadata(context),
            duration_ms=round((time.monotonic() - start) * 1000, 3),
            result=type(result).__name__,
        )
        return result


class IgnoreUnknownParametersMiddleware(Middleware):
    async def on_call_tool(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, ToolResult],
    ) -> ToolResult:
        tool = await mcp.get_tool(context.message.name)
        if tool is None:
            return await call_next(context)
        arguments = context.message.arguments or {}
        unknown = arguments.keys() - tool.parameters.get("properties", {})
        if unknown:
            await context.fastmcp_context.warning(
                f"Unknown parameters will be ignored: {', '.join(sorted(unknown))}"
            )
            for name in unknown:
                arguments.pop(name)
        return await call_next(context)


mcp.add_middleware(ToolAuditMiddleware())
mcp.add_middleware(RequestLogMiddleware())
mcp.add_middleware(IgnoreUnknownParametersMiddleware())
mcp.add_middleware(StructuredToolErrorsMiddleware())


def stateless_http_enabled() -> bool:
    return os.environ.get("MCPSERVER_STATEFUL_HTTP", "").casefold() not in {
        "1",
        "true",
        "yes",
        "on",
    }


def log_startup_record() -> dict[str, Any]:
    record = {
        "server_start_id": SERVER_START_ID,
        "timestamp": iso_timestamp(),
        "pid": os.getpid(),
        "cwd": os.getcwd(),
        "stateless_http": stateless_http_enabled(),
    }
    append_jsonl(LOG_DIR / "startup.jsonl", record)
    mode = "stateless" if record["stateless_http"] else "stateful"
    print(f"MCP HTTP mode: {mode}", flush=True)
    print(mounted_paths_text(), flush=True)
    return record


def finalize_output(
    output: str,
    result: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    before_limits = len(output.encode())
    line_limited, line_trim_count, line_omitted = trim_long_lines_with_stats(output)
    total_limited, total_omitted = limit_total_output(line_limited)
    output_path = None
    if line_omitted or total_omitted:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", prefix="mcpserver-output-", suffix=".txt", delete=False
        ) as handle:
            handle.write(output)
            output_path = handle.name
    result.update(
        {
            "output_path": output_path,
            "output_bytes_before_limits": before_limits,
            "output_bytes_after_limits": len(total_limited.encode()),
            "line_trim_count": line_trim_count,
            "line_trim_omitted_bytes": line_omitted,
            "total_limit_omitted_bytes": total_omitted,
            "total_truncation_omitted_bytes": line_omitted + total_omitted,
        }
    )
    return total_limited, result


def bash_environment() -> dict[str, str]:
    """Return the container environment without mcpserver's private uv runtime."""
    env = os.environ.copy()
    env.pop("VIRTUAL_ENV", None)
    env.pop("UV_RUN_RECURSION_DEPTH", None)
    server_bin = str(Path(sys.executable).parent)
    env["PATH"] = os.pathsep.join(
        entry for entry in env.get("PATH", "").split(os.pathsep) if entry != server_bin
    )
    return env


def _stop_process_group(process: subprocess.Popen) -> tuple[str, str]:
    """Terminate the whole shell process group and collect remaining output."""
    with suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGTERM)
    try:
        return process.communicate(timeout=0.5)
    except subprocess.TimeoutExpired:
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        return process.communicate()


def run_bash_command(
    commands: str,
    timeout_ms: int,
    cwd: str | None = None,
    cancel_event: threading.Event | None = None,
) -> tuple[str, dict[str, Any]]:
    started_at = iso_timestamp()
    start = time.monotonic()
    result: dict[str, Any] = {
        "server_start_id": SERVER_START_ID,
        "started_at": started_at,
        "finished_at": None,
        "duration_ms": None,
        "exit_code": None,
        "timed_out": False,
        "error": None,
        "error_code": None,
        "retryable": False,
        "cwd": str(Path(cwd).expanduser().resolve() if cwd else Path.cwd().resolve()),
        "stdout_bytes": 0,
        "stderr_bytes": 0,
    }
    stdout = stderr = ""
    try:
        if not commands.strip():
            raise ValueError("commands must not be empty")
        if timeout_ms <= 0:
            raise ValueError("timeout_ms must be greater than zero")
        process = subprocess.Popen(
            ["/bin/bash", "-c", commands],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
            cwd=Path(cwd).expanduser() if cwd else None,
            env=bash_environment(),
        )
        deadline = time.monotonic() + timeout_ms / 1000
        while True:
            if cancel_event is not None and cancel_event.is_set():
                stdout, stderr = _stop_process_group(process)
                result["error"] = "Command cancelled by MCP client"
                result["error_code"] = "cancelled"
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                stdout, stderr = _stop_process_group(process)
                result["timed_out"] = True
                result["error"] = f"Command timed out after {timeout_ms} ms"
                result["error_code"] = "timeout"
                break
            try:
                stdout, stderr = process.communicate(timeout=min(0.1, remaining))
                result["exit_code"] = process.returncode
                break
            except subprocess.TimeoutExpired:
                continue

        result["stdout_bytes"] = len(stdout.encode())
        result["stderr_bytes"] = len(stderr.encode())
        output = stdout
        if stderr:
            output += f"\nSTDERR:\n{stderr}"
        if result["timed_out"]:
            output += f"\nCommand timed out after {timeout_ms} ms"
        elif result["error"] is not None:
            output += f"\n{result['error']}"
        elif result["exit_code"] != 0:
            output += f"\nReturn code: {result['exit_code']}"
    except Exception as error:
        result["error"] = repr(error)
        output = str(error)
    if result["timed_out"]:
        result["status"] = "timeout"
    elif result["error"] is not None:
        result["status"] = "error"
        result["error_code"] = result["error_code"] or "execution_error"
    elif result["exit_code"] == 0:
        result["status"] = "success"
    else:
        result["status"] = "failed"
        result["error_code"] = "nonzero_exit"
    result["ok"] = result["status"] == "success"
    result["finished_at"] = iso_timestamp()
    result["duration_ms"] = round((time.monotonic() - start) * 1000, 3)
    return finalize_output(output, result)


def display_path(path: Path) -> str:
    path = path.absolute()
    home = Path.home().absolute()
    try:
        relative = path.relative_to(home)
    except ValueError:
        return str(path)
    return "~" if relative == Path(".") else f"~/{relative}"


def path_access_mode(path: Path) -> str:
    writable = os.access(path, os.W_OK, effective_ids=True)
    with suppress(OSError):
        writable = writable and not os.statvfs(path).f_flag & os.ST_RDONLY
    return "rw" if writable else "ro"


def mount_probe_path(display: str) -> Path:
    parts = []
    for part in Path(display).expanduser().parts:
        if any(marker in part for marker in "*?[{"):
            break
        parts.append(part)
    return Path(*parts)


def mounted_paths_text(mounted_paths: list[tuple[str, str]] | None = None) -> str:
    entries = []
    for display, description in MOUNTED_PATHS if mounted_paths is None else mounted_paths:
        path = mount_probe_path(display)
        if path.exists():
            entries.append(f"  {path_access_mode(path)}: {display} - {description}")
    return "mounted paths (rw = read-write, ro = read-only):\n" + ("\n".join(entries) if entries else "(none detected)")


def build_bash_description(
    cwd: Path | None = None,
    mounted_paths: list[tuple[str, str]] | None = None,
) -> str:
    cwd = cwd or Path.cwd()
    return f"""Runs multiline bash script. Prints output.

cwd: {display_path(cwd)} ({path_access_mode(cwd)})

{mounted_paths_text(mounted_paths)}

Prefer `read_file`/`read_files`, `list_directory`, `file_info`, `search`, and `edit_block` for routine local file work:
they are bounded, structured, and correctly marked read-only vs mutating. Use `bash` for pipelines,
transformations, specialized CLIs, or anything these tools cannot express cleanly.

Use `uv run context.py search QUERY` for cross-source personal context
(or `entity`, `recent`, `open-loops`, `thread`, `style`, `assets`) to find candidates.
Deep-read returned locators before using important claims as evidence;
fall back to direct source scans when needed.

Avoid broad scans over large file lists - `$HOME`, `~/.*`, `~/code`, `~/Documents`, or archives - unless necessary.
  Scope to known subdirs. Prefer `fd`/`ug` to respect `.gitignore` and shrink long listings.
  Check shape (dir count, file size, match count, ...) first.
Avoid wasting tool calls on wrong files, e.g.
  Verify paths with `pwd`, `ls`, or `test -e`.
  Locate best candidates with `fd`, `ug -l`, `rga -l`, READMEs/configs/indexes.
  Fuzzy match names, noisy sources like `ug -Z1`.
  Search best matches with `path:line` evidence.
Paths contain spaces. Prefer null-delimited loops (`fd -0`, `xargs -0`).

This is not Code Interpreter. There's no `/mnt/data`. Use /tmp or user/repo paths.

CLI tools: fd --max-depth 3 --type f, ug, rga for binary docs, jaq (faster jq), duckdb/sqlite3, sg (at search), git/gh, agent-browser, ...
Before using an unfamiliar/version-sensitive CLI, inspect `--help` / `--version`; do not infer flags.
Before querying structured data, inspect its type/schema/sample first (JSON vs JSONL, keys, columns).
Before lint/test/build, inspect project-native verification (`just --list`, package scripts, pyproject, Makefile, AGENTS.md); run focused checks before full suites.
For ad-hoc Python, prefer `uv run --no-project --with pkg1 --with pkg2 -- python - <<'PY'`.
Avoid running AI agents (codex, claude, gemini, ...) unless the user explicitly requests it.
Commands run transactionally; do not start persistent background servers.

gws can access work email, calendar, chat, drive:
  gws gmail users messages list --params '{{"userId":"me", "q": "from:..."}}'
  gws calendar events list --params '{{"calendarId":"s.anand@straive.com","timeMin":"...","timeMax":"...","singleEvents":true,"orderBy":"startTime"}}'
For personal email (root.node@gmail.com) use:
  GOOGLE_WORKSPACE_CLI_CONFIG_DIR="$HOME/.config/gws-root.node@gmail.com" gws gmail users messages list --params '{{"userId":"me", "q": "from:..."}}'

Prefer `set -euo pipefail` for deterministic scripts. If so, then:
  Handle expected misses (`ug ... || true`, `test -e`, optional files) printing concise diagnostics.
  Capped pipelines like `ug ... | head` can exit 141 from SIGPIPE.
  Wrap expected capped/no-match pipelines in `( ... | head -N || true )`.

stdout longer than {MAX_LINE_BYTES} bytes / line and over {MAX_TOTAL_OUTPUT_BYTES} bytes is trimmed.
When output is trimmed, the complete output is saved to `output_path`; use `download_file` if needed.
Save larger text or binaries to /tmp and use `download_file` tool to transfer.

Do not print secrets, tokens, or credentials, unless explicitly requested.
Summarize and cite paths/lines instead.
"""


async def bash(commands: str, timeout_ms: int = 30_000, cwd: str | None = None) -> ToolResult:
    ctx: Context = get_context()
    await ctx.info(f"bash: (cwd={cwd or os.getcwd()})\n{commands}")
    cancel_event = threading.Event()
    future = asyncio.get_running_loop().run_in_executor(
        BASH_EXECUTOR, run_bash_command, commands, timeout_ms, cwd, cancel_event
    )
    try:
        output, result = await future
    except asyncio.CancelledError:
        cancel_event.set()
        raise
    request_id = getattr(ctx, "request_id", None)
    result["request_id"] = str(request_id) if request_id is not None else None
    if result["stderr_bytes"]:
        await ctx.warning(f"ERROR: {result['stderr_bytes']} stderr bytes")
    await ctx.info(f"DONE: {len(output.encode())} bytes, return code {result['exit_code']}")
    request = {"server_start_id": SERVER_START_ID, "timeout_ms": timeout_ms, "cwd": cwd}
    log_event("bash", commands=commands, request=request, output=output, result=result)
    result["output"] = output
    return ToolResult(
        content=[TextContent(type="text", text=output)],
        structured_content=result,
        is_error=not result["ok"],
    )


bash.__doc__ = build_bash_description()
mcp.tool(description=bash.__doc__, output_schema=BASH_OUTPUT_SCHEMA)(bash)





def retry_transient_io(operation):
    """Retry a read-only OS operation on a short allowlist of transient errno values."""
    for delay in (*TRANSIENT_RETRY_DELAYS, None):
        try:
            return operation()
        except OSError as error:
            if error.errno not in TRANSIENT_ERRNOS or delay is None:
                raise
            time.sleep(delay)


def _resolved_existing_path(path: str) -> Path:
    resolved = Path(path).expanduser().resolve()
    try:
        retry_transient_io(resolved.stat)
    except FileNotFoundError as error:
        raise LocalToolError(
            "not_found",
            f"Path not found: {resolved}",
            path=resolved,
            suggestion="Check the path or locate it with search/list_directory before retrying.",
        ) from error
    except OSError as error:
        raise read_error("Cannot inspect path", resolved, error) from error
    return resolved


def _validate_range(start_line: int, line_count: int) -> None:
    if start_line < 1:
        raise LocalToolError("invalid_input", "start_line must be >= 1")
    if not 1 <= line_count <= MAX_READ_LINES:
        raise LocalToolError(
            "invalid_input", f"line_count must be between 1 and {MAX_READ_LINES}"
        )


def _read_file(path: str, start_line: int = 1, line_count: int = DEFAULT_READ_LINES) -> dict[str, Any]:
    """Read exact UTF-8 text with 1-based line pagination."""
    _validate_range(start_line, line_count)
    file_path = _resolved_existing_path(path)
    if not file_path.is_file():
        raise LocalToolError("not_a_file", f"Not a regular file: {file_path}", path=file_path)

    def read_once() -> dict[str, Any]:
        with file_path.open("rb") as handle:
            sample = handle.read(8192)
        if b"\0" in sample:
            raise LocalToolError(
                "binary_file",
                f"Binary file: {file_path}. Use download_file or bash/rga instead.",
                path=file_path,
            )
        try:
            sample.decode("utf-8")
        except UnicodeDecodeError as error:
            raise LocalToolError(
                "unsupported_encoding",
                f"Not UTF-8 text: {file_path}. Use download_file or bash instead.",
                path=file_path,
            ) from error

        lines: list[str] = []
        returned_bytes = 0
        next_start_line: int | None = None
        byte_limited = False
        partial_line = False
        with file_path.open("r", encoding="utf-8", newline="") as handle:
            for line_number, line in enumerate(handle, 1):
                if line_number < start_line:
                    continue
                if len(lines) >= line_count:
                    next_start_line = line_number
                    break
                encoded_size = len(line.encode())
                if returned_bytes + encoded_size > MAX_READ_BYTES:
                    byte_limited = True
                    if not lines:
                        lines.append(fit_utf8_prefix(line, MAX_READ_BYTES))
                        partial_line = True
                    else:
                        next_start_line = line_number
                    break
                lines.append(line)
                returned_bytes += encoded_size

        end_line = start_line + len(lines) - 1 if lines else None
        return {
            "path": str(file_path),
            "start_line": start_line,
            "end_line": end_line,
            "line_count": len(lines),
            "has_more": next_start_line is not None or byte_limited,
            "next_start_line": None if partial_line else next_start_line,
            "byte_limited": byte_limited,
            "content": "".join(lines),
        }

    try:
        return retry_transient_io(read_once)
    except UnicodeDecodeError as error:
        raise LocalToolError(
            "unsupported_encoding",
            f"Not UTF-8 text: {file_path}. Use download_file or bash instead.",
            path=file_path,
        ) from error
    except OSError as error:
        raise read_error("Cannot read file", file_path, error) from error


def _read_files(
    paths: list[str], start_line: int = 1, line_count: int = 100
) -> dict[str, Any]:
    if not 1 <= len(paths) <= MAX_READ_FILES:
        raise LocalToolError("invalid_input", f"read_files accepts at most {MAX_READ_FILES} paths")
    files = []
    for path in paths:
        try:
            files.append(_read_file(path, start_line, line_count))
        except ToolError as error:
            files.append({"path": str(Path(path).expanduser()), **structured_tool_error(error)})
    return {"files": files}


def _directory_entries(path: Path, include_hidden: bool) -> list[os.DirEntry[str]]:
    def scan_once() -> list[os.DirEntry[str]]:
        with os.scandir(path) as scan:
            return list(scan)

    try:
        entries = retry_transient_io(scan_once)
    except OSError as error:
        raise read_error("Cannot list directory", path, error) from error
    if not include_hidden:
        entries = [entry for entry in entries if not entry.name.startswith(".")]
    important = {name.casefold(): index for index, name in enumerate(IMPORTANT_FILES)}
    def sort_key(entry: os.DirEntry[str]) -> tuple[int, int | str]:
        name = entry.name.casefold()
        if name in important:
            return (0, important[name])
        if entry.is_dir(follow_symlinks=False) and name not in LOW_SIGNAL_DIRS:
            return (1, name)
        if not entry.is_dir(follow_symlinks=False):
            return (2, name)
        return (3, name)
    return sorted(entries, key=sort_key)


def _list_directory(
    path: str,
    depth: int = 2,
    max_entries: int = DEFAULT_LIST_ENTRIES,
    per_directory: int = DEFAULT_LIST_PER_DIRECTORY,
    include_hidden: bool = False,
) -> dict[str, Any]:
    if not 1 <= depth <= MAX_LIST_DEPTH:
        raise LocalToolError("invalid_input", f"depth must be between 1 and {MAX_LIST_DEPTH}")
    if not 1 <= max_entries <= MAX_LIST_ENTRIES:
        raise LocalToolError(
            "invalid_input", f"max_entries must be between 1 and {MAX_LIST_ENTRIES}"
        )
    if not 1 <= per_directory <= max_entries:
        raise LocalToolError("invalid_input", "per_directory must be between 1 and max_entries")

    root = _resolved_existing_path(path)
    if not root.is_dir():
        raise LocalToolError("not_a_directory", f"Not a directory: {root}", path=root)

    queue = deque([(root, Path("."), 1)])
    result: list[dict[str, str]] = []
    omitted: list[dict[str, Any]] = []
    global_truncated = False
    while queue:
        directory, relative_dir, level = queue.popleft()
        entries = _directory_entries(directory, include_hidden)
        shown = entries[:per_directory]
        if len(entries) > len(shown):
            omitted.append(
                {
                    "path": "." if relative_dir == Path(".") else relative_dir.as_posix() + "/",
                    "omitted": len(entries) - len(shown),
                }
            )
        for entry in shown:
            if len(result) >= max_entries:
                global_truncated = True
                break
            child = Path(entry.path)
            relative = child.relative_to(root)
            is_dir = entry.is_dir(follow_symlinks=False)
            is_link = entry.is_symlink()
            kind = "symlink" if is_link else "directory" if is_dir else "file"
            display = relative.as_posix() + ("/" if is_dir else "")
            result.append({"path": display, "type": kind})
            if is_dir and not is_link and entry.name.casefold() not in LOW_SIGNAL_DIRS and level < depth:
                queue.append((child, relative, level + 1))
        if global_truncated:
            break

    return {
        "path": str(root),
        "depth": depth,
        "entries": result,
        "omitted": omitted,
        "truncated": global_truncated or bool(omitted) or bool(queue),
        "hint": "Narrow path or reduce depth to inspect omitted entries."
        if global_truncated or omitted or queue
        else None,
    }


def _sha256_file(path: Path) -> str:
    def hash_once() -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()

    return retry_transient_io(hash_once)


def _file_info(path: str, sha256: bool = False) -> dict[str, Any]:
    file_path = _resolved_existing_path(path)
    try:
        info = retry_transient_io(file_path.stat)
    except OSError as error:
        raise read_error("Cannot inspect path", file_path, error) from error

    result: dict[str, Any] = {
        "path": str(file_path),
        "type": "directory" if file_path.is_dir() else "file" if file_path.is_file() else "other",
        "size": info.st_size,
        "modified": datetime.fromtimestamp(info.st_mtime, UTC).isoformat(),
        "mode": oct(stat.S_IMODE(info.st_mode)),
        "access": path_access_mode(file_path),
        "mime_type": None,
        "line_count": None,
        "entry_count": None,
        "sha256": None,
    }
    if file_path.is_dir():
        try:
            result["entry_count"] = retry_transient_io(
                lambda: sum(1 for _ in os.scandir(file_path))
            )
        except OSError as error:
            raise read_error("Cannot list directory", file_path, error) from error
        return result
    if not file_path.is_file():
        return result

    try:
        def inspect_file_once() -> tuple[bytes, bytes | None]:
            with file_path.open("rb") as handle:
                sample = handle.read(8192)
            data = (
                file_path.read_bytes()
                if info.st_size <= 5 * 1024 * 1024 and b"\0" not in sample
                else None
            )
            return sample, data

        sample, data = retry_transient_io(inspect_file_once)
        result["mime_type"] = file_mime_type(file_path, sample)
        if data is not None:
            with suppress(UnicodeDecodeError):
                data.decode("utf-8")
                result["line_count"] = data.count(b"\n") + int(
                    bool(data) and not data.endswith(b"\n")
                )
        if sha256:
            result["sha256"] = _sha256_file(file_path)
    except OSError as error:
        raise read_error("Cannot read file", file_path, error) from error
    return result


def _edit_block(
    path: str,
    old_string: str,
    new_string: str,
    expected_replacements: int = 1,
) -> dict[str, Any]:
    if not old_string:
        raise LocalToolError("invalid_input", "old_string must not be empty")
    if expected_replacements < 1:
        raise LocalToolError("invalid_input", "expected_replacements must be >= 1")

    file_path = _resolved_existing_path(path)
    if not file_path.is_file():
        raise LocalToolError("not_a_file", f"Not a regular file: {file_path}", path=file_path)
    if path_access_mode(file_path) != "rw":
        raise LocalToolError(
            "read_only",
            f"File is read-only: {file_path}",
            path=file_path,
            suggestion="Restart LocalMCP2 with this path mounted writable if modification is required.",
        )

    try:
        def read_once() -> str:
            with file_path.open("r", encoding="utf-8", newline="") as handle:
                return handle.read()

        content = retry_transient_io(read_once)
    except UnicodeDecodeError as error:
        raise LocalToolError(
            "unsupported_encoding", f"Not UTF-8 text: {file_path}", path=file_path
        ) from error
    except OSError as error:
        raise read_error("Cannot read file", file_path, error) from error

    count = content.count(old_string)
    if count != expected_replacements:
        raise LocalToolError(
            "conflict",
            f"Expected {expected_replacements} occurrence(s) of old_string but found {count}; "
            "no changes made. Re-read/search the file and retry with exact current text.",
            path=file_path,
            suggestion="Re-read or search the current file, then retry with exact current text.",
        )

    first_offset = content.index(old_string)
    first_line = content.count("\n", 0, first_offset) + 1
    updated = content.replace(old_string, new_string)
    before_sha256 = hashlib.sha256(content.encode()).hexdigest()
    after_sha256 = hashlib.sha256(updated.encode()).hexdigest()
    try:
        file_stat = file_path.stat()
        fd, temp_name = tempfile.mkstemp(dir=file_path.parent, prefix=f".{file_path.name}.")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
                handle.write(updated)
            os.chmod(temp_name, stat.S_IMODE(file_stat.st_mode))
            os.replace(temp_name, file_path)
        finally:
            with suppress(OSError):
                os.unlink(temp_name)
    except OSError as error:
        raise LocalToolError(
            "write_failed",
            f"Could not edit file: {file_path}: {error.strerror or error}",
            path=file_path,
            suggestion="Inspect the current file/mount state before deciding whether to retry.",
        ) from error

    lines = updated.splitlines()
    preview_start = max(0, first_line - 3)
    preview_end = min(len(lines), first_line + max(3, new_string.count("\n") + 2))
    return {
        "path": str(file_path),
        "replacements": count,
        "first_line": first_line,
        "before_sha256": before_sha256,
        "after_sha256": after_sha256,
        "preview_start_line": preview_start + 1,
        "preview": "\n".join(lines[preview_start:preview_end]),
    }


def _run_search_command(args: list[str]) -> str:
    try:
        completed = retry_transient_io(
            lambda: subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=SEARCH_TIMEOUT_SECONDS,
                env=bash_environment(),
            )
        )
    except subprocess.TimeoutExpired as error:
        raise LocalToolError(
            "timeout",
            f"Search exceeded {SEARCH_TIMEOUT_SECONDS}s. Narrow path/query or use bash for exhaustive scans.",
            suggestion="Narrow path/query/file_glob rather than repeating the same broad search.",
        ) from error
    except OSError as error:
        raise read_error("Could not start search", Path(args[0]), error) from error
    if completed.returncode not in {0, 1}:
        message = completed.stderr.strip() or completed.stdout.strip() or f"exit {completed.returncode}"
        raise LocalToolError(
            "search_failed",
            f"Search failed: {message}",
            suggestion="Check the query/path/tool diagnostics before retrying.",
        )
    return completed.stdout


def _search_summary(
    paths: list[str], root: Path, sample_limit: int, literal_query: str | None
) -> dict[str, Any]:
    base = root if root.is_dir() else root.parent
    groups, extensions = Counter(), Counter()
    dated = []
    for value in paths:
        path = Path(value)
        with suppress(ValueError):
            relative = path.relative_to(base)
            groups[relative.parts[0] if len(relative.parts) > 1 else "."] += 1
        extensions[path.suffix.lower() or "[none]"] += 1
        with suppress(OSError):
            dated.append((path.stat().st_mtime, str(path)))
    dated.sort(reverse=True)
    name_hits = (
        [value for _, value in dated if literal_query.casefold() in Path(value).name.casefold()]
        if literal_query
        else []
    )
    sample_files = list(dict.fromkeys(name_hits + [value for _, value in dated]))[:sample_limit]
    return {
        "top_groups": [{"group": name, "count": count} for name, count in groups.most_common(8)],
        "top_extensions": [
            {"extension": name, "count": count} for name, count in extensions.most_common(8)
        ],
        "sample_files": sample_files,
    }


def _ug_options(
    query: str,
    *,
    regex: bool,
    case_sensitive: bool,
    hidden: bool,
    file_glob: str | None,
) -> list[str]:
    options = ["ug", "-r", "-I", "--ignore-files"]
    if not regex:
        options.append("-F")
    if not case_sensitive:
        options.append("-i")
    if hidden:
        options.append("--hidden")
    if file_glob:
        options.append(f"--include={file_glob}")
    return options


def _search(
    query: str,
    path: str = ".",
    mode: Literal["content", "files"] = "content",
    file_glob: str | None = None,
    regex: bool = False,
    case_sensitive: bool = False,
    hidden: bool = False,
    max_results: int = 50,
    max_files: int = 20,
) -> dict[str, Any]:
    if not query:
        raise LocalToolError("invalid_input", "query must not be empty")
    if mode not in {"content", "files"}:
        raise LocalToolError("invalid_input", "mode must be 'content' or 'files'")
    if mode == "files" and file_glob:
        raise LocalToolError(
            "invalid_input",
            "file_glob applies to content search; use a regex query to filter file names",
        )
    if not 1 <= max_results <= 200:
        raise LocalToolError("invalid_input", "max_results must be between 1 and 200")
    if not 1 <= max_files <= 50:
        raise LocalToolError("invalid_input", "max_files must be between 1 and 50")
    root = _resolved_existing_path(path)

    candidate_limit = max(SEARCH_CANDIDATE_CAP + 1, max_files + 1, max_results + 1)
    if mode == "files":
        args = ["fd", "--type", "f", "--max-results", str(candidate_limit)]
        if not regex:
            args.append("--fixed-strings")
        if not case_sensitive:
            args.append("--ignore-case")
        if hidden:
            args.append("--hidden")
        args += [query, str(root)]
        raw_paths = [line for line in _run_search_command(args).splitlines() if line]
        candidate_truncated = len(raw_paths) >= candidate_limit
        candidates = raw_paths[:SEARCH_CANDIDATE_CAP] if candidate_truncated else raw_paths
        broad = len(candidates) > max_results or candidate_truncated
        return {
            "query": query,
            "path": str(root),
            "mode": mode,
            "broad": broad,
            "matched_files": len(candidates),
            "matched_files_is_lower_bound": candidate_truncated,
            "total_matches": None if candidate_truncated else len(candidates),
            "matches": [] if broad else [{"path": value} for value in candidates[:max_results]],
            **_search_summary(candidates, root, min(max_files, max_results), None if regex else query),
            "summary_is_sample": candidate_truncated,
            "hint": "Narrow path/query to see concrete files." if broad else None,
        }

    candidate_args = _ug_options(
        query,
        regex=regex,
        case_sensitive=case_sensitive,
        hidden=hidden,
        file_glob=file_glob,
    )
    candidate_args += ["-l", f"--max-files={candidate_limit}", "--", query, str(root)]
    raw_candidates = [line for line in _run_search_command(candidate_args).splitlines() if line]
    candidate_truncated = len(raw_candidates) >= candidate_limit
    candidates = raw_candidates[:SEARCH_CANDIDATE_CAP] if candidate_truncated else raw_candidates
    if not candidates:
        return {
            "query": query,
            "path": str(root),
            "mode": mode,
            "broad": False,
            "matched_files": 0,
            "matched_files_is_lower_bound": False,
            "total_matches": 0,
            "matches": [],
            "top_groups": [],
            "top_extensions": [],
            "sample_files": [],
            "summary_is_sample": False,
            "hint": None,
        }

    if len(candidates) > max_files or candidate_truncated:
        return {
            "query": query,
            "path": str(root),
            "mode": mode,
            "broad": True,
            "matched_files": len(candidates),
            "matched_files_is_lower_bound": candidate_truncated,
            "total_matches": None,
            "matches": [],
            **_search_summary(candidates, root, max_files, None if regex else query),
            "summary_is_sample": candidate_truncated,
            "hint": (
                "Too many matching files for useful line dumps. Narrow path/query/file_glob. "
                "Summary is based on the first 200 matching files."
                if candidate_truncated
                else "Too many matching files for useful line dumps. Narrow path/query/file_glob."
            ),
        }

    base_options = _ug_options(
        query,
        regex=regex,
        case_sensitive=case_sensitive,
        hidden=hidden,
        file_glob=None,
    )
    count_data = json.loads(
        _run_search_command(base_options + ["--json", "-c", "--", query, *candidates]) or "[]"
    )
    counts = {
        item["file"]: int(item["matches"][0]["match"])
        for item in count_data
        if item.get("matches")
    }
    total_matches = sum(counts.values())

    per_file = min(10, max(3, (max_results + len(candidates) - 1) // len(candidates)))
    line_data = json.loads(
        _run_search_command(
            base_options + ["--json", "-n", f"-m{per_file}", "--", query, *candidates]
        )
        or "[]"
    )
    buckets: list[list[dict[str, Any]]] = []
    for item in line_data:
        bucket = []
        for match in item.get("matches", []):
            text = str(match.get("match", "")).rstrip("\r\n")
            truncated = len(text) > 500
            if truncated:
                text = text[:497] + "..."
            bucket.append(
                {
                    "path": item["file"],
                    "line": int(match["line"]),
                    "text": text,
                    "text_truncated": truncated,
                }
            )
        buckets.append(bucket)

    matches = []
    index = 0
    while len(matches) < max_results and any(index < len(bucket) for bucket in buckets):
        for bucket in buckets:
            if index < len(bucket) and len(matches) < max_results:
                matches.append(bucket[index])
        index += 1

    return {
        "query": query,
        "path": str(root),
        "mode": mode,
        "broad": False,
        "matched_files": len(candidates),
        "matched_files_is_lower_bound": False,
        "total_matches": total_matches,
        "matches": matches,
        "top_groups": [],
        "top_extensions": [],
        "sample_files": [],
        "summary_is_sample": False,
        "hint": "Showing representative line matches; use read_file around a line for context."
        if total_matches > len(matches)
        else None,
    }


@mcp.tool(
    annotations={"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False}
)
async def read_file(
    path: str, start_line: int = 1, line_count: int = DEFAULT_READ_LINES
) -> dict[str, Any]:
    """Read exact UTF-8 text with 1-based lines; next_start_line tells you how to continue."""
    result = await asyncio.to_thread(_read_file, path, start_line, line_count)
    log_event("read_file", request={"path": result["path"], "start_line": start_line, "line_count": line_count})
    return result


@mcp.tool(
    annotations={"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False}
)
async def read_files(paths: list[str], start_line: int = 1, line_count: int = 100) -> dict[str, Any]:
    """Read up to 12 known UTF-8 text files; individual failures do not fail the batch."""
    result = await asyncio.to_thread(_read_files, paths, start_line, line_count)
    log_event("read_files", request={"paths": paths, "start_line": start_line, "line_count": line_count})
    return result


@mcp.tool(
    annotations={"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False}
)
async def list_directory(
    path: str,
    depth: int = 2,
    max_entries: int = DEFAULT_LIST_ENTRIES,
    include_hidden: bool = False,
) -> dict[str, Any]:
    """Inspect directory shape: entrypoint files first, breadth-first, without expanding cache/vendor trees."""
    result = await asyncio.to_thread(
        _list_directory,
        path,
        depth,
        max_entries,
        min(DEFAULT_LIST_PER_DIRECTORY, max_entries),
        include_hidden,
    )
    log_event("list_directory", request={"path": result["path"], "depth": depth, "max_entries": max_entries})
    return result


@mcp.tool(
    annotations={"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False}
)
async def file_info(path: str, sha256: bool = False) -> dict[str, Any]:
    """Return compact file/directory metadata. Hashing is opt-in; line counts are computed only for small text."""
    result = await asyncio.to_thread(_file_info, path, sha256)
    log_event("file_info", request={"path": result["path"], "sha256": sha256}, result=result)
    return result


@mcp.tool(
    annotations={"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False}
)
async def search(
    query: str,
    path: str = ".",
    mode: Literal["content", "files"] = "content",
    file_glob: str | None = None,
    regex: bool = False,
    case_sensitive: bool = False,
    hidden: bool = False,
    max_results: int = 50,
) -> dict[str, Any]:
    """Search content or filenames, literal/case-insensitive by default; broad queries return shape + a sample."""
    result = await asyncio.to_thread(
        _search, query, path, mode, file_glob, regex, case_sensitive, hidden, max_results, 20
    )
    log_event(
        "search",
        request={"query": query, "path": result["path"], "mode": mode, "file_glob": file_glob, "regex": regex},
        result={"broad": result["broad"], "matched_files": result["matched_files"], "total_matches": result["total_matches"]},
    )
    return result


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    }
)
async def edit_block(
    path: str,
    old_string: str,
    new_string: str,
    expected_replacements: int = 1,
) -> dict[str, Any]:
    """Atomically replace exact text. Refuses ambiguous/stale edits; use read_file/search first."""
    result = await asyncio.to_thread(
        _edit_block, path, old_string, new_string, expected_replacements
    )
    log_event(
        "edit_block",
        request={"path": result["path"], "expected_replacements": expected_replacements},
        result=result,
    )
    return result


def is_text_mime_type(mime_type: str) -> bool:
    return (
        mime_type.startswith("text/")
        or mime_type in {"application/json", "application/javascript", "application/xml"}
        or mime_type.endswith(("+json", "+xml"))
    )


def looks_like_utf8_text(data: bytes) -> bool:
    if b"\0" in data:
        return False
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return all(char.isprintable() or char in "\t\n\r" for char in text)


def file_mime_type(path: Path, sample: bytes) -> str:
    mime_type = mimetypes.guess_type(path.name, strict=False)[0]
    if mime_type is None and looks_like_utf8_text(sample):
        return "text/plain"
    return mime_type or "application/octet-stream"


def read_error(action: str, path: Path, error: OSError) -> ToolError:
    if isinstance(error, PermissionError):
        return LocalToolError(
            "permission_denied",
            f"{action}: {path}: {error.strerror or error}",
            path=path,
            suggestion="Check the container mount/path permissions; repeated retries usually will not help.",
        )
    code = "transient_io" if error.errno in TRANSIENT_ERRNOS else "io_error"
    return LocalToolError(
        code,
        f"{action}: {path}: {error.strerror or error}",
        retryable=code == "transient_io",
        path=path,
        suggestion="Retry once after the transient condition clears." if code == "transient_io" else None,
    )


def _download_file(path: str) -> ToolResult:
    file_path = Path(path).expanduser().resolve()
    try:
        file_stat = retry_transient_io(file_path.stat)
    except FileNotFoundError as error:
        raise LocalToolError(
            "not_found",
            f"File not found: {file_path}: {error.strerror or error}",
            path=file_path,
            suggestion="Check the path or locate it with search/list_directory before retrying.",
        ) from error
    except OSError as error:
        raise read_error("Cannot inspect file", file_path, error) from error
    if not stat.S_ISREG(file_stat.st_mode):
        raise LocalToolError("not_a_file", f"Not a regular file: {file_path}", path=file_path)

    try:
        data = retry_transient_io(file_path.read_bytes)
    except OSError as error:
        raise read_error("Cannot read file", file_path, error) from error

    mime_type = file_mime_type(file_path, data[:8192])
    text = None
    if is_text_mime_type(mime_type):
        with suppress(UnicodeDecodeError):
            text = data.decode()
    uri = file_path.as_uri()
    if text is not None:
        resource = TextResourceContents(uri=uri, mimeType=mime_type, text=text)
        encoding = "utf-8"
    else:
        resource = BlobResourceContents(
            uri=uri,
            mimeType=mime_type,
            blob=base64.b64encode(data).decode("ascii"),
        )
        encoding = "base64"

    metadata = {
        "path": str(file_path),
        "mime_type": mime_type,
        "encoding": encoding,
        "size": file_stat.st_size,
        "bytes_read": len(data),
    }
    return ToolResult(
        content=[
            TextContent(type="text", text=json.dumps(metadata, separators=(",", ":"))),
            EmbeddedResource(type="resource", resource=resource),
        ],
        structured_content=metadata,
    )


@mcp.tool(
    annotations={"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
    output_schema=DOWNLOAD_FILE_OUTPUT_SCHEMA,
)
async def download_file(path: str) -> ToolResult:
    """Download large/binary files as an MCP embedded resource. Use read_file for normal text."""
    result = await asyncio.to_thread(_download_file, path)
    metadata = result.structured_content
    await get_context().info(f"download_file: {metadata['path']} ({metadata['size']} bytes)")
    log_event("download_file", result=metadata)
    return result


def writable_roots() -> list[Path]:
    """Return detected writable working and mounted directories."""
    candidates = [Path.cwd(), *(mount_probe_path(display) for display, _ in MOUNTED_PATHS)]
    roots = []
    for candidate in candidates:
        if candidate.is_file():
            candidate = candidate.parent
        if candidate.is_dir() and path_access_mode(candidate) == "rw":
            resolved = candidate.resolve()
            if resolved not in roots:
                roots.append(resolved)
    return roots


def _save_file(file: ChatGPTUpload, destination: str, overwrite: bool = False) -> dict[str, Any]:
    """Stream a ChatGPT-uploaded file to an allowed writable local path."""
    required = {"download_url", "file_id", "file_name", "mime_type"}
    missing = required - file.keys()
    if missing or any(not isinstance(file.get(name), str) or not file[name] for name in required):
        raise LocalToolError(
            "invalid_upload",
            f"Invalid file object; required string fields: {', '.join(sorted(required))}",
        )
    url = file["download_url"]
    if parse.urlsplit(url).scheme.lower() != "https":
        raise LocalToolError("insecure_url", "download_url must use HTTPS")

    path = Path(destination).expanduser().resolve()
    if not any(path.is_relative_to(root) for root in writable_roots()):
        raise LocalToolError(
            "outside_writable_root",
            f"Destination is not under a detected writable root: {path}",
            path=path,
            suggestion="Choose a writable mounted path or restart LocalMCP2 with the required mount.",
        )
    if path.exists() and not overwrite:
        raise LocalToolError(
            "already_exists",
            f"Destination already exists (set overwrite=true to replace it): {path}",
            path=path,
        )
    path.parent.mkdir(parents=True, exist_ok=True)

    digest = hashlib.sha256()
    size = 0
    temp_path: Path | None = None
    try:
        with request.urlopen(request.Request(url, headers={"User-Agent": "mcpserver/1"}), timeout=30) as response:
            if parse.urlsplit(response.geturl()).scheme.lower() != "https":
                raise LocalToolError("insecure_url", "download_url redirected to a non-HTTPS URL")
            content_length = response.headers.get("Content-Length")
            if content_length is not None and int(content_length) > MAX_UPLOAD_BYTES:
                raise LocalToolError(
                    "too_large", f"Upload exceeds the {MAX_UPLOAD_BYTES}-byte size limit"
                )
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
                temp_path = Path(handle.name)
                while chunk := response.read(64 * 1024):
                    size += len(chunk)
                    if size > MAX_UPLOAD_BYTES:
                        raise LocalToolError(
                            "too_large", f"Upload exceeds the {MAX_UPLOAD_BYTES}-byte size limit"
                        )
                    handle.write(chunk)
                    digest.update(chunk)
        if overwrite:
            os.replace(temp_path, path)
        else:
            try:
                os.link(temp_path, path)
            except FileExistsError as error:
                raise LocalToolError(
                    "already_exists",
                    f"Destination already exists (set overwrite=true to replace it): {path}",
                    path=path,
                ) from error
            with suppress(OSError):
                temp_path.unlink()
        temp_path = None
    except ToolError:
        raise
    except Exception as error:
        raise LocalToolError(
            "upload_failed",
            f"Could not save upload: {error}",
            path=path,
            suggestion="Inspect the download/network/destination error before retrying.",
        ) from error
    finally:
        if temp_path is not None:
            with suppress(OSError):
                temp_path.unlink(missing_ok=True)

    result = {
        "path": str(path),
        "size": size,
        "mime_type": file["mime_type"],
        "sha256": digest.hexdigest(),
        "file_id": file["file_id"],
    }
    return result


@mcp.tool(
    meta={"openai/fileParams": ["file"]},
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def save_file(file: ChatGPTUpload, destination: str, overwrite: bool = False) -> dict[str, Any]:
    """Stream a ChatGPT-uploaded file to an allowed writable local path."""
    result = await asyncio.to_thread(_save_file, file, destination, overwrite)
    await get_context().info(f"save_file: {result['path']} ({result['size']} bytes)")
    log_event("save_file", result=result)
    return result


def latest_session_id() -> str:
    with suppress(OSError):
        return (LOG_DIR / "latest-session").read_text(encoding="utf-8").strip()
    return ""


def mcp_rate(args: list[str]) -> int:
    if not args or args[0] not in {"0", "1", "2"}:
        raise SystemExit("Usage: mcp-rate SCORE [TAG] [NOTE...] where SCORE is 0|1|2")
    score = args[0]
    tag = args[1] if len(args) > 1 else ""
    if tag and tag not in RATE_TAGS:
        raise SystemExit(f"Tag must be one of: {', '.join(sorted(RATE_TAGS))}")
    note = " ".join(args[2:]) if len(args) > 2 else ""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with (LOG_DIR / "ratings.tsv").open("a", encoding="utf-8") as handle:
        handle.write(f"{iso_timestamp()}\t{latest_session_id()}\t{score}\t{tag}\t{note}\n")
    return 0


def main() -> None:
    if Path(sys.argv[0]).name == "mcp-rate" or (len(sys.argv) > 1 and sys.argv[1] == "mcp-rate"):
        offset = 1 if Path(sys.argv[0]).name == "mcp-rate" else 2
        raise SystemExit(mcp_rate(sys.argv[offset:]))
    log_startup_record()
    run_args: dict[str, Any] = {"transport": "http", "port": 2428, "path": MCP_PATH}
    if stateless_http_enabled():
        run_args["stateless_http"] = True
    mcp.run(**run_args)


if __name__ == "__main__":
    main()
