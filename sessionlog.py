from __future__ import annotations

import dataclasses
import datetime as dt
import json
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any, Iterable, Optional, Protocol

import typer

TS_MIN = "0001-01-01T00:00:00.000Z"
TS_MAX = "9999-12-31T23:59:59.999Z"
LOCAL_COMMAND_RE = re.compile(r"<command-name>/|^<local-command-stdout>", re.IGNORECASE)
ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


@dataclasses.dataclass
class Stats:
    files_scanned: int = 0
    files_empty: int = 0
    read_errors: int = 0
    invalid_json_lines: int = 0
    events_scanned: int = 0
    events_matched: int = 0
    db_sessions_scanned: int = 0
    db_turns_scanned: int = 0


@dataclasses.dataclass(frozen=True)
class SourcePos:
    file_path: str
    line_no: int


@dataclasses.dataclass(frozen=True)
class SessionEvent:
    session_id: str
    timestamp: str
    source: SourcePos
    raw: dict[str, Any]


@dataclasses.dataclass
class SessionSummary:
    session_id: str
    cwd: str = ""
    start_ts: Optional[str] = None
    end_ts: Optional[str] = None
    first_prompt: str = ""
    files_count: int = 0
    source_kind: str = ""


def parse_iso8601(ts: Any) -> Optional[dt.datetime]:
    if not isinstance(ts, str) or not ts:
        return None
    try:
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return dt.datetime.fromisoformat(ts)
    except Exception:
        return None


def ts_key(ts: Any) -> tuple[int, str]:
    parsed = parse_iso8601(ts)
    if parsed is None:
        return (1, TS_MAX)
    return (0, parsed.isoformat())


def in_time_range(ts: Optional[str], since: str, until: str) -> bool:
    if ts is None:
        return False
    return ts_key(since) <= ts_key(ts) <= ts_key(until)


def json_pretty(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True)


def indent_block(text: str, indent: str = "    ") -> str:
    return indent + text.replace("\n", "\n" + indent) + "\n"


def truncate_middle(text: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    half = max_chars // 2
    return text[:half] + "...truncated..." + text[-half:]


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def looks_like_local_command(text: str) -> bool:
    return bool(LOCAL_COMMAND_RE.search(text.strip()))


def is_warmup(text: str) -> bool:
    return text.strip().lower() == "warmup"


def md_heading(level: int, title: str) -> str:
    return "\n\n" + ("#" * level) + " " + title + "\n\n"


def md_code(lang: str, body: str) -> str:
    return f"```{lang}\n{body.rstrip()}\n```\n"


def md_details(summary: str, body: str, *, open_details: bool) -> str:
    open_attr = " open" if open_details else ""
    payload = body.rstrip()
    if payload:
        payload += "\n\n"
    return f"\n\n<details{open_attr}><summary><strong>{summary}</strong></summary>\n\n{payload}</details>"


class Colors:
    def __init__(self) -> None:
        self.enabled = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
        self.reset = "\033[0m" if self.enabled else ""
        self.header = "\033[1;36m" if self.enabled else ""
        self.time = "\033[2;37m" if self.enabled else ""
        self.cwd = "\033[0;34m" if self.enabled else ""
        self.prompt = "\033[0m" if self.enabled else ""
        self.meta = "\033[2;90m" if self.enabled else ""

    def wrap(self, style: str, text: str) -> str:
        if not self.enabled:
            return text
        return f"{style}{text}{self.reset}"


def read_jsonl(
    path: Path, *, strict: bool, stats: Stats
) -> list[tuple[int, dict[str, Any]]]:
    rows: list[tuple[int, dict[str, Any]]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    stats.invalid_json_lines += 1
                    if strict:
                        raise
                    continue
                if not isinstance(obj, dict):
                    stats.invalid_json_lines += 1
                    if strict:
                        raise ValueError(f"Non-object JSON on {path}:{line_no}")
                    continue
                rows.append((line_no, obj))
    except Exception:
        stats.read_errors += 1
        if strict:
            raise
    return rows


class Backend(Protocol):
    name: str
    default_root: Path

    def list_sessions(
        self,
        *,
        root: Path,
        strict: bool,
        cwd_filter: str,
        since: str,
        until: str,
        limit: int,
        max_chars: int,
        include_empty: bool,
        allow_warmup: bool,
        allow_local_commands: bool,
    ) -> tuple[list[SessionSummary], Stats]: ...

    def stream_sessions(
        self,
        *,
        root: Path,
        strict: bool,
        cwd_filter: str,
        since: str,
        until: str,
        limit: int,
        max_chars: int,
        include_empty: bool,
        allow_warmup: bool,
        allow_local_commands: bool,
    ) -> tuple[Iterable[SessionSummary], Stats]: ...

    def resolve_session(
        self, *, root: Path, strict: bool, session_id: str
    ) -> tuple[list[str], Stats]: ...

    def collect_events(
        self, *, root: Path, strict: bool, session_id: str
    ) -> tuple[list[SessionEvent], Stats]: ...

    def render_markdown(
        self,
        *,
        session_id: str,
        events: list[SessionEvent],
        include_meta: bool,
        open_details: bool,
    ) -> str: ...


def _session_header(events: list[SessionEvent], session_id: str, cwd: str = "") -> str:
    start_ts: Optional[str] = None
    end_ts: Optional[str] = None
    files = sorted({event.source.file_path for event in events})
    for event in events:
        ts = event.raw.get("timestamp")
        if isinstance(ts, str):
            if start_ts is None or ts_key(ts) < ts_key(start_ts):
                start_ts = ts
            if end_ts is None or ts_key(ts) > ts_key(end_ts):
                end_ts = ts
    parts = [f"# {session_id}\n"]
    if cwd:
        parts.append(f"\n**cwd:** `{cwd}`\n")
    if start_ts is not None or end_ts is not None:
        parts.append(f"\n**when:** `{start_ts or ''}` .. `{end_ts or ''}`\n")
    parts.append("\n**files:**\n")
    for path in files:
        parts.append(f"- `{path}`\n")
    return "".join(parts)


def _can_stream_ls(*, cwd_filter: str, since: str, until: str) -> bool:
    return not cwd_filter and since == TS_MIN and until == TS_MAX


def _print_summary(summary: SessionSummary, colors: Colors) -> None:
    header = colors.wrap(colors.header, f"# {summary.session_id}")
    suffix = f" [{summary.source_kind}]" if summary.source_kind else ""
    print(header + suffix + " " + colors.wrap(colors.time, summary.end_ts or ""), flush=True)
    print(colors.wrap(colors.cwd, indent_block(summary.cwd).rstrip()), flush=True)
    print(colors.wrap(colors.prompt, indent_block(summary.first_prompt).rstrip()), flush=True)
    print(
        colors.wrap(colors.meta, indent_block(f"files: {summary.files_count}").rstrip()),
        flush=True,
    )
    print(flush=True)


class ClaudeBackend:
    name = "claude"
    default_root = Path("~/.claude/projects").expanduser()

    def _iter_files(self, root: Path, stats: Stats) -> Iterable[Path]:
        if not root.exists():
            return []
        files: list[Path] = []
        for project_dir in sorted(entry for entry in root.iterdir() if entry.is_dir()):
            for path in project_dir.rglob("*.jsonl"):
                if not path.is_file():
                    continue
                stats.files_scanned += 1
                try:
                    if path.stat().st_size == 0:
                        stats.files_empty += 1
                        continue
                except Exception:
                    pass
                files.append(path)
        return files

    def _normalize_text(self, content: Any) -> str:
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "\n\n".join(
                item.get("text", "")
                for item in content
                if isinstance(item, dict)
                and item.get("type") == "text"
                and item.get("text")
            )
        return ""

    def _first_prompt(
        self,
        event: dict[str, Any],
        *,
        allow_warmup: bool,
        allow_local_commands: bool,
    ) -> str:
        if event.get("type") != "user" or event.get("isMeta") is True:
            return ""
        message = event.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        text = self._normalize_text(content).strip()
        if not text:
            return ""
        if (not allow_warmup) and is_warmup(text):
            return ""
        if (not allow_local_commands) and looks_like_local_command(text):
            return ""
        return text

    def list_sessions(self, **kwargs: Any) -> tuple[list[SessionSummary], Stats]:
        root: Path = kwargs["root"]
        strict: bool = kwargs["strict"]
        cwd_filter: str = kwargs["cwd_filter"]
        since: str = kwargs["since"]
        until: str = kwargs["until"]
        limit: int = kwargs["limit"]
        max_chars: int = kwargs["max_chars"]
        include_empty: bool = kwargs["include_empty"]
        allow_warmup: bool = kwargs["allow_warmup"]
        allow_local_commands: bool = kwargs["allow_local_commands"]
        stats = Stats()
        sessions: dict[str, SessionSummary] = {}
        for path in self._iter_files(root, stats):
            for _, event in read_jsonl(path, strict=strict, stats=stats):
                stats.events_scanned += 1
                sid = event.get("sessionId")
                if not isinstance(sid, str) or not sid:
                    continue
                ts = event.get("timestamp")
                if since != TS_MIN or until != TS_MAX:
                    if not in_time_range(
                        ts if isinstance(ts, str) else None, since, until
                    ):
                        continue
                session = sessions.setdefault(
                    sid, SessionSummary(session_id=sid, source_kind="jsonl")
                )
                session.files_count += (
                    0 if str(path) in getattr(session, "_files", set()) else 1
                )
                if not hasattr(session, "_files"):
                    setattr(session, "_files", set())
                getattr(session, "_files").add(str(path))
                cwd = event.get("cwd")
                if isinstance(cwd, str) and cwd and not session.cwd:
                    session.cwd = cwd
                if isinstance(ts, str):
                    if session.start_ts is None or ts_key(ts) < ts_key(
                        session.start_ts
                    ):
                        session.start_ts = ts
                    if session.end_ts is None or ts_key(ts) > ts_key(session.end_ts):
                        session.end_ts = ts
                if not session.first_prompt:
                    session.first_prompt = self._first_prompt(
                        event,
                        allow_warmup=allow_warmup,
                        allow_local_commands=allow_local_commands,
                    )
        summaries = []
        for session in sessions.values():
            if cwd_filter and cwd_filter not in session.cwd:
                continue
            if not include_empty and not session.first_prompt:
                continue
            session.first_prompt = truncate_middle(session.first_prompt, max_chars)
            summaries.append(session)
        summaries.sort(
            key=lambda s: (ts_key(s.end_ts or TS_MIN), s.session_id), reverse=True
        )
        if limit > 0:
            summaries = summaries[:limit]
        return summaries, stats

    def stream_sessions(self, **kwargs: Any) -> tuple[Iterable[SessionSummary], Stats]:
        root: Path = kwargs["root"]
        strict: bool = kwargs["strict"]
        limit: int = kwargs["limit"]
        max_chars: int = kwargs["max_chars"]
        include_empty: bool = kwargs["include_empty"]
        allow_warmup: bool = kwargs["allow_warmup"]
        allow_local_commands: bool = kwargs["allow_local_commands"]
        stats = Stats()

        def iterator() -> Iterable[SessionSummary]:
            sessions: dict[str, SessionSummary] = {}
            emitted: set[str] = set()
            emitted_count = 0
            for path in self._iter_files(root, stats):
                file_sessions: set[str] = set()
                for _, event in read_jsonl(path, strict=strict, stats=stats):
                    stats.events_scanned += 1
                    sid = event.get("sessionId")
                    if not isinstance(sid, str) or not sid:
                        continue
                    session = sessions.setdefault(
                        sid, SessionSummary(session_id=sid, source_kind="jsonl")
                    )
                    if not hasattr(session, "_files"):
                        setattr(session, "_files", set())
                    files = getattr(session, "_files")
                    if str(path) not in files:
                        files.add(str(path))
                        session.files_count += 1
                    file_sessions.add(sid)
                    cwd = event.get("cwd")
                    if isinstance(cwd, str) and cwd and not session.cwd:
                        session.cwd = cwd
                    ts = event.get("timestamp")
                    if isinstance(ts, str):
                        if session.start_ts is None or ts_key(ts) < ts_key(session.start_ts):
                            session.start_ts = ts
                        if session.end_ts is None or ts_key(ts) > ts_key(session.end_ts):
                            session.end_ts = ts
                    if not session.first_prompt:
                        session.first_prompt = self._first_prompt(
                            event,
                            allow_warmup=allow_warmup,
                            allow_local_commands=allow_local_commands,
                        )
                for sid in file_sessions:
                    if sid in emitted:
                        continue
                    session = sessions[sid]
                    if not include_empty and not session.first_prompt:
                        continue
                    emitted.add(sid)
                    emitted_count += 1
                    yield dataclasses.replace(
                        session,
                        first_prompt=truncate_middle(session.first_prompt, max_chars),
                    )
                    if limit > 0 and emitted_count >= limit:
                        return

        return iterator(), stats

    def resolve_session(
        self, *, root: Path, strict: bool, session_id: str
    ) -> tuple[list[str], Stats]:
        stats = Stats()
        hits: list[str] = []
        for path in self._iter_files(root, stats):
            for _, event in read_jsonl(path, strict=strict, stats=stats):
                if event.get("sessionId") == session_id:
                    hits.append(str(path))
                    break
        return hits, stats

    def collect_events(
        self, *, root: Path, strict: bool, session_id: str
    ) -> tuple[list[SessionEvent], Stats]:
        stats = Stats()
        events: list[SessionEvent] = []
        for path in self._iter_files(root, stats):
            for line_no, event in read_jsonl(path, strict=strict, stats=stats):
                stats.events_scanned += 1
                if event.get("sessionId") != session_id:
                    continue
                ts = event.get("timestamp")
                events.append(
                    SessionEvent(
                        session_id=session_id,
                        timestamp=ts if isinstance(ts, str) else TS_MAX,
                        source=SourcePos(str(path), line_no),
                        raw=event,
                    )
                )
                stats.events_matched += 1
        events.sort(
            key=lambda event: (
                ts_key(event.timestamp),
                event.source.file_path,
                event.source.line_no,
            )
        )
        return events, stats

    def render_markdown(
        self,
        *,
        session_id: str,
        events: list[SessionEvent],
        include_meta: bool,
        open_details: bool,
    ) -> str:
        cwd = ""
        for event in events:
            raw_cwd = event.raw.get("cwd")
            if isinstance(raw_cwd, str) and raw_cwd:
                cwd = raw_cwd
                break
        parts = [_session_header(events, session_id, cwd)]
        for event in events:
            raw = event.raw
            kind = raw.get("type")
            if kind not in {"user", "assistant", "system"}:
                continue
            owner = str(kind)
            message = raw.get("message")
            content = message.get("content") if isinstance(message, dict) else None
            text = self._normalize_text(content).strip()
            extras: list[str] = []
            if isinstance(content, list):
                for item in content:
                    if not isinstance(item, dict):
                        continue
                    item_type = item.get("type")
                    if item_type == "tool_use":
                        extras.append(
                            md_details(
                                f"{owner}: tool: {item.get('name', '')}".strip(),
                                md_code("json", json_pretty(item.get("input"))),
                                open_details=open_details,
                            )
                        )
                    elif item_type == "tool_result":
                        result_body = item.get("content")
                        if isinstance(result_body, str):
                            body = md_code("txt", result_body)
                        else:
                            body = md_code("json", json_pretty(result_body))
                        extras.append(
                            md_details(
                                f"{owner}: tool result".strip(),
                                body,
                                open_details=open_details,
                            )
                        )
            if text:
                if owner == "user" and looks_like_local_command(text):
                    text = strip_ansi(text)
                parts.append(md_heading(2, owner))
                parts.append(text + "\n")
            parts.extend(extras)
            if include_meta:
                meta = {
                    key: raw.get(key)
                    for key in (
                        "timestamp",
                        "sessionId",
                        "cwd",
                        "agentId",
                        "isSidechain",
                    )
                    if raw.get(key) is not None
                }
                if meta:
                    parts.append(
                        md_details(
                            "meta",
                            md_code("json", json_pretty(meta)),
                            open_details=open_details,
                        )
                    )
        return "".join(parts).lstrip()


class CopilotBackend:
    name = "copilot"
    default_root = Path("~/.copilot").expanduser()

    def _db_path(self, root: Path) -> Path:
        return root / "session-store.db"

    def _legacy_root(self, root: Path) -> Path:
        return root / "session-state"

    def _connect(self, root: Path) -> Optional[sqlite3.Connection]:
        db_path = self._db_path(root)
        if not db_path.exists():
            return None
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    def _legacy_file_id(self, path: Path) -> str:
        return path.stem

    def _legacy_session_id(self, event: dict[str, Any], path: Path) -> str:
        data = event.get("data")
        if isinstance(data, dict) and isinstance(data.get("sessionId"), str):
            return data["sessionId"]
        return self._legacy_file_id(path)

    def _legacy_cwd(self, event: dict[str, Any]) -> str:
        data = event.get("data")
        if not isinstance(data, dict):
            return ""
        context = data.get("context")
        if isinstance(context, dict) and isinstance(context.get("cwd"), str):
            return context["cwd"]
        cwd = data.get("cwd")
        return cwd if isinstance(cwd, str) else ""

    def _legacy_first_prompt(
        self,
        event: dict[str, Any],
        *,
        allow_warmup: bool,
        allow_local_commands: bool,
    ) -> str:
        if event.get("type") != "user.message":
            return ""
        data = event.get("data")
        text = data.get("content") if isinstance(data, dict) else None
        if not isinstance(text, str):
            return ""
        text = text.strip()
        if not text:
            return ""
        if (not allow_warmup) and is_warmup(text):
            return ""
        if (not allow_local_commands) and looks_like_local_command(text):
            return ""
        return text

    def _legacy_files(self, root: Path, stats: Stats) -> list[Path]:
        legacy_root = self._legacy_root(root)
        if not legacy_root.exists():
            return []
        files = sorted(legacy_root.glob("*.jsonl"))
        stats.files_scanned += len(files)
        return files

    def list_sessions(self, **kwargs: Any) -> tuple[list[SessionSummary], Stats]:
        root: Path = kwargs["root"]
        strict: bool = kwargs["strict"]
        cwd_filter: str = kwargs["cwd_filter"]
        since: str = kwargs["since"]
        until: str = kwargs["until"]
        limit: int = kwargs["limit"]
        max_chars: int = kwargs["max_chars"]
        include_empty: bool = kwargs["include_empty"]
        allow_warmup: bool = kwargs["allow_warmup"]
        allow_local_commands: bool = kwargs["allow_local_commands"]
        stats = Stats()
        summaries: list[SessionSummary] = []
        conn = self._connect(root)
        db_ids: set[str] = set()
        if conn is not None:
            for row in conn.execute(
                """
                select
                    s.id,
                    s.cwd,
                    s.created_at,
                    s.updated_at,
                    coalesce((select user_message from turns t where t.session_id = s.id order by turn_index asc limit 1), '') as first_prompt,
                    coalesce((select count(*) from session_files f where f.session_id = s.id), 0) as files_count
                from sessions s
                order by s.updated_at desc, s.created_at desc, s.id desc
                """
            ):
                stats.db_sessions_scanned += 1
                sid = str(row["id"])
                db_ids.add(sid)
                ts = row["updated_at"] or row["created_at"]
                if since != TS_MIN or until != TS_MAX:
                    if not in_time_range(ts, since, until):
                        continue
                cwd = (row["cwd"] or "").strip()
                if cwd_filter and cwd_filter not in cwd:
                    continue
                first_prompt = (row["first_prompt"] or "").strip()
                if first_prompt:
                    if (not allow_warmup) and is_warmup(first_prompt):
                        first_prompt = ""
                    if (not allow_local_commands) and looks_like_local_command(
                        first_prompt
                    ):
                        first_prompt = ""
                if not include_empty and not first_prompt:
                    continue
                summaries.append(
                    SessionSummary(
                        session_id=sid,
                        cwd=cwd,
                        start_ts=row["created_at"],
                        end_ts=row["updated_at"],
                        first_prompt=truncate_middle(first_prompt, max_chars),
                        files_count=int(row["files_count"] or 0),
                        source_kind="db",
                    )
                )
        for path in self._legacy_files(root, stats):
            rows = read_jsonl(path, strict=strict, stats=stats)
            if not rows:
                continue
            sid = self._legacy_file_id(path)
            if sid in db_ids:
                continue
            summary = SessionSummary(
                session_id=sid, files_count=1, source_kind="legacy"
            )
            for _, event in rows:
                stats.events_scanned += 1
                sid = self._legacy_session_id(event, path)
                summary.session_id = sid
                ts = event.get("timestamp")
                if isinstance(ts, str):
                    if summary.start_ts is None or ts_key(ts) < ts_key(
                        summary.start_ts
                    ):
                        summary.start_ts = ts
                    if summary.end_ts is None or ts_key(ts) > ts_key(summary.end_ts):
                        summary.end_ts = ts
                if not summary.cwd:
                    summary.cwd = self._legacy_cwd(event)
                if not summary.first_prompt:
                    summary.first_prompt = self._legacy_first_prompt(
                        event,
                        allow_warmup=allow_warmup,
                        allow_local_commands=allow_local_commands,
                    )
            if since != TS_MIN or until != TS_MAX:
                if not in_time_range(summary.end_ts or summary.start_ts, since, until):
                    continue
            if cwd_filter and cwd_filter not in summary.cwd:
                continue
            if not include_empty and not summary.first_prompt:
                continue
            summary.first_prompt = truncate_middle(summary.first_prompt, max_chars)
            summaries.append(summary)
        summaries.sort(
            key=lambda s: (ts_key(s.end_ts or TS_MIN), s.session_id), reverse=True
        )
        if limit > 0:
            summaries = summaries[:limit]
        return summaries, stats

    def stream_sessions(self, **kwargs: Any) -> tuple[Iterable[SessionSummary], Stats]:
        root: Path = kwargs["root"]
        strict: bool = kwargs["strict"]
        cwd_filter: str = kwargs["cwd_filter"]
        since: str = kwargs["since"]
        until: str = kwargs["until"]
        limit: int = kwargs["limit"]
        max_chars: int = kwargs["max_chars"]
        include_empty: bool = kwargs["include_empty"]
        allow_warmup: bool = kwargs["allow_warmup"]
        allow_local_commands: bool = kwargs["allow_local_commands"]
        stats = Stats()

        def iterator() -> Iterable[SessionSummary]:
            emitted_count = 0
            conn = self._connect(root)
            db_ids: set[str] = set()
            if conn is not None:
                for row in conn.execute(
                    """
                    select
                        s.id,
                        s.cwd,
                        s.created_at,
                        s.updated_at,
                        coalesce((select user_message from turns t where t.session_id = s.id order by turn_index asc limit 1), '') as first_prompt,
                        coalesce((select count(*) from session_files f where f.session_id = s.id), 0) as files_count
                    from sessions s
                    order by s.updated_at desc, s.created_at desc, s.id desc
                    """
                ):
                    stats.db_sessions_scanned += 1
                    sid = str(row["id"])
                    db_ids.add(sid)
                    ts = row["updated_at"] or row["created_at"]
                    if since != TS_MIN or until != TS_MAX:
                        if not in_time_range(ts, since, until):
                            continue
                    cwd = (row["cwd"] or "").strip()
                    if cwd_filter and cwd_filter not in cwd:
                        continue
                    first_prompt = (row["first_prompt"] or "").strip()
                    if first_prompt:
                        if (not allow_warmup) and is_warmup(first_prompt):
                            first_prompt = ""
                        if (not allow_local_commands) and looks_like_local_command(
                            first_prompt
                        ):
                            first_prompt = ""
                    if not include_empty and not first_prompt:
                        continue
                    emitted_count += 1
                    yield SessionSummary(
                        session_id=sid,
                        cwd=cwd,
                        start_ts=row["created_at"],
                        end_ts=row["updated_at"],
                        first_prompt=truncate_middle(first_prompt, max_chars),
                        files_count=int(row["files_count"] or 0),
                        source_kind="db",
                    )
                    if limit > 0 and emitted_count >= limit:
                        return
            for path in self._legacy_files(root, stats):
                rows = read_jsonl(path, strict=strict, stats=stats)
                if not rows:
                    continue
                sid = self._legacy_file_id(path)
                if sid in db_ids:
                    continue
                summary = SessionSummary(session_id=sid, files_count=1, source_kind="legacy")
                for _, event in rows:
                    stats.events_scanned += 1
                    sid = self._legacy_session_id(event, path)
                    summary.session_id = sid
                    ts = event.get("timestamp")
                    if isinstance(ts, str):
                        if summary.start_ts is None or ts_key(ts) < ts_key(summary.start_ts):
                            summary.start_ts = ts
                        if summary.end_ts is None or ts_key(ts) > ts_key(summary.end_ts):
                            summary.end_ts = ts
                    if not summary.cwd:
                        summary.cwd = self._legacy_cwd(event)
                    if not summary.first_prompt:
                        summary.first_prompt = self._legacy_first_prompt(
                            event,
                            allow_warmup=allow_warmup,
                            allow_local_commands=allow_local_commands,
                        )
                if since != TS_MIN or until != TS_MAX:
                    if not in_time_range(summary.end_ts or summary.start_ts, since, until):
                        continue
                if cwd_filter and cwd_filter not in summary.cwd:
                    continue
                if not include_empty and not summary.first_prompt:
                    continue
                summary.first_prompt = truncate_middle(summary.first_prompt, max_chars)
                emitted_count += 1
                yield summary
                if limit > 0 and emitted_count >= limit:
                    return

        return iterator(), stats

    def resolve_session(
        self, *, root: Path, strict: bool, session_id: str
    ) -> tuple[list[str], Stats]:
        stats = Stats()
        hits: list[str] = []
        conn = self._connect(root)
        if conn is not None:
            row = conn.execute(
                "select 1 from sessions where id = ? limit 1", (session_id,)
            ).fetchone()
            if row is not None:
                hits.append(str(self._db_path(root)))
        session_events = root / "session-state" / session_id / "events.jsonl"
        if session_events.exists():
            hits.append(str(session_events))
        for path in self._legacy_files(root, stats):
            if path.stem == session_id:
                hits.append(str(path))
                break
        return hits, stats

    def collect_events(
        self, *, root: Path, strict: bool, session_id: str
    ) -> tuple[list[SessionEvent], Stats]:
        stats = Stats()
        events: list[SessionEvent] = []
        conn = self._connect(root)
        if conn is not None:
            session = conn.execute(
                "select id, cwd, repository, branch, summary, created_at, updated_at, host_type from sessions where id = ?",
                (session_id,),
            ).fetchone()
            if session is not None:
                events.append(
                    SessionEvent(
                        session_id=session_id,
                        timestamp=str(session["created_at"] or TS_MIN),
                        source=SourcePos(str(self._db_path(root)), 1),
                        raw={
                            "type": "session.start",
                            "timestamp": session["created_at"],
                            "sessionId": session_id,
                            "cwd": session["cwd"],
                            "repository": session["repository"],
                            "branch": session["branch"],
                            "summary": session["summary"],
                            "hostType": session["host_type"],
                        },
                    )
                )
                for row in conn.execute(
                    "select turn_index, user_message, assistant_response, timestamp from turns where session_id = ? order by turn_index asc",
                    (session_id,),
                ):
                    stats.db_turns_scanned += 1
                    ts = str(row["timestamp"] or TS_MAX)
                    turn_index = int(row["turn_index"])
                    user_message = (row["user_message"] or "").strip()
                    assistant_response = (row["assistant_response"] or "").strip()
                    if user_message:
                        events.append(
                            SessionEvent(
                                session_id=session_id,
                                timestamp=ts,
                                source=SourcePos(
                                    str(self._db_path(root)), turn_index * 2 + 2
                                ),
                                raw={
                                    "type": "user.message",
                                    "timestamp": ts,
                                    "sessionId": session_id,
                                    "turnIndex": turn_index,
                                    "data": {"content": user_message},
                                },
                            )
                        )
                    if assistant_response:
                        events.append(
                            SessionEvent(
                                session_id=session_id,
                                timestamp=ts,
                                source=SourcePos(
                                    str(self._db_path(root)), turn_index * 2 + 3
                                ),
                                raw={
                                    "type": "assistant.message",
                                    "timestamp": ts,
                                    "sessionId": session_id,
                                    "turnIndex": turn_index,
                                    "data": {
                                        "content": assistant_response,
                                        "toolRequests": [],
                                    },
                                },
                            )
                        )
                return events, stats
        for path in self._legacy_files(root, stats):
            rows = read_jsonl(path, strict=strict, stats=stats)
            if not rows:
                continue
            if path.stem != session_id:
                if all(
                    self._legacy_session_id(event, path) != session_id
                    for _, event in rows
                ):
                    continue
            for line_no, event in rows:
                stats.events_scanned += 1
                if self._legacy_session_id(event, path) != session_id:
                    continue
                ts = event.get("timestamp")
                events.append(
                    SessionEvent(
                        session_id=session_id,
                        timestamp=ts if isinstance(ts, str) else TS_MAX,
                        source=SourcePos(str(path), line_no),
                        raw=event,
                    )
                )
                stats.events_matched += 1
        events.sort(
            key=lambda event: (
                ts_key(event.timestamp),
                event.source.file_path,
                event.source.line_no,
            )
        )
        return events, stats

    def render_markdown(
        self,
        *,
        session_id: str,
        events: list[SessionEvent],
        include_meta: bool,
        open_details: bool,
    ) -> str:
        cwd = ""
        for event in events:
            raw = event.raw
            if isinstance(raw.get("cwd"), str) and raw["cwd"]:
                cwd = raw["cwd"]
                break
            data = raw.get("data")
            context = data.get("context") if isinstance(data, dict) else None
            if isinstance(context, dict) and isinstance(context.get("cwd"), str):
                cwd = context["cwd"]
                break
        parts = [_session_header(events, session_id, cwd)]
        for event in events:
            raw = event.raw
            kind = raw.get("type")
            if kind == "session.start":
                summary = raw.get("summary")
                if isinstance(summary, str) and summary.strip():
                    parts.append(md_heading(2, "session"))
                    parts.append(summary.strip() + "\n")
                continue
            if kind == "user.message":
                data = raw.get("data")
                text = data.get("content") if isinstance(data, dict) else None
                if isinstance(text, str) and text.strip():
                    parts.append(md_heading(2, "user"))
                    parts.append(text.rstrip() + "\n")
            elif kind == "assistant.message":
                data = raw.get("data")
                content = data.get("content") if isinstance(data, dict) else ""
                if isinstance(content, str) and content.strip():
                    parts.append(md_heading(2, "assistant"))
                    parts.append(content.rstrip() + "\n")
                tool_requests = (
                    data.get("toolRequests") if isinstance(data, dict) else None
                )
                if isinstance(tool_requests, list):
                    for item in tool_requests:
                        if not isinstance(item, dict):
                            continue
                        label = f"tool request: {item.get('name', '')}".strip()
                        tool_call_id = item.get("toolCallId")
                        if isinstance(tool_call_id, str) and tool_call_id:
                            label += f" ({tool_call_id})"
                        parts.append(
                            md_details(
                                label,
                                md_code("json", json_pretty(item.get("arguments"))),
                                open_details=open_details,
                            )
                        )
            elif kind in {"tool.execution_start", "tool.execution_complete"}:
                data = raw.get("data")
                if not isinstance(data, dict):
                    continue
                if kind == "tool.execution_start":
                    label = f"tool start: {data.get('toolName', '')}".strip()
                    tool_call_id = data.get("toolCallId")
                    if isinstance(tool_call_id, str) and tool_call_id:
                        label += f" ({tool_call_id})"
                    body = md_code("json", json_pretty(data.get("arguments")))
                else:
                    label = f"tool result: {data.get('toolCallId', '')}".strip()
                    result = data.get("result")
                    if isinstance(result, dict) and isinstance(
                        result.get("content"), str
                    ):
                        body = (
                            f"**success:** {'true' if data.get('success') else 'false'}\n\n"
                            + md_code("txt", result["content"])
                        )
                    else:
                        body = (
                            f"**success:** {'true' if data.get('success') else 'false'}\n\n"
                            + md_code("json", json_pretty(result))
                        )
                parts.append(md_details(label, body, open_details=open_details))
            if include_meta:
                meta = {
                    key: raw.get(key)
                    for key in (
                        "timestamp",
                        "sessionId",
                        "cwd",
                        "turnIndex",
                        "repository",
                        "branch",
                        "hostType",
                    )
                    if raw.get(key) is not None
                }
                if meta:
                    parts.append(
                        md_details(
                            "meta",
                            md_code("json", json_pretty(meta)),
                            open_details=open_details,
                        )
                    )
        return "".join(parts).lstrip()


class CodexBackend:
    name = "codex"
    default_root = Path("~/.codex").expanduser()

    def _roots(self, root: Path) -> list[Path]:
        return [root / "sessions", root / "archived_sessions"]

    def _iter_files(self, root: Path, stats: Stats) -> list[Path]:
        files: list[Path] = []
        for base in self._roots(root):
            if not base.exists():
                continue
            if base.name == "sessions":
                iterator = base.rglob("*.jsonl")
            else:
                iterator = base.glob("*.jsonl")
            for path in iterator:
                if not path.is_file():
                    continue
                stats.files_scanned += 1
                try:
                    if path.stat().st_size == 0:
                        stats.files_empty += 1
                        continue
                except Exception:
                    pass
                files.append(path)
        return sorted(files, reverse=True)

    def _content_text(self, content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if not isinstance(item, dict):
                    continue
                if item.get("type") in {"input_text", "output_text"} and isinstance(
                    item.get("text"), str
                ):
                    parts.append(item["text"])
            return "\n\n".join(parts)
        return ""

    def _tool_args(self, raw_args: Any) -> Any:
        if isinstance(raw_args, str):
            try:
                return json.loads(raw_args)
            except Exception:
                return raw_args
        return raw_args

    def _tool_command(self, args: Any) -> str:
        if isinstance(args, dict):
            if "cmd" in args and isinstance(args["cmd"], str):
                return args["cmd"]
            if "command" in args:
                command = args["command"]
                if isinstance(command, list):
                    return " ".join(str(part) for part in command)
                if isinstance(command, str):
                    return command
            if "tool_uses" in args and isinstance(args["tool_uses"], list):
                return f"{len(args['tool_uses'])} parallel calls"
        if isinstance(args, str):
            return args
        return ""

    def _session_id(self, rows: list[tuple[int, dict[str, Any]]], path: Path) -> str:
        for _, event in rows:
            if event.get("type") == "session_meta":
                payload = event.get("payload")
                sid = payload.get("id") if isinstance(payload, dict) else None
                if isinstance(sid, str) and sid:
                    return sid
        return path.stem

    def _summary_from_rows(
        self,
        rows: list[tuple[int, dict[str, Any]]],
        path: Path,
        *,
        since: str,
        until: str,
        cwd_filter: str,
        max_chars: int,
        include_empty: bool,
    ) -> Optional[SessionSummary]:
        sid = self._session_id(rows, path)
        summary = SessionSummary(session_id=sid, files_count=1, source_kind="jsonl")
        for _, event in rows:
            ts = event.get("timestamp")
            if isinstance(ts, str):
                if summary.start_ts is None or ts_key(ts) < ts_key(summary.start_ts):
                    summary.start_ts = ts
                if summary.end_ts is None or ts_key(ts) > ts_key(summary.end_ts):
                    summary.end_ts = ts
            payload = event.get("payload")
            if event.get("type") == "session_meta" and isinstance(payload, dict):
                cwd = payload.get("cwd")
                if isinstance(cwd, str) and cwd and not summary.cwd:
                    summary.cwd = cwd
            if (
                event.get("type") == "turn_context"
                and isinstance(payload, dict)
                and not summary.cwd
            ):
                cwd = payload.get("cwd")
                if isinstance(cwd, str) and cwd:
                    summary.cwd = cwd
            if (
                not summary.first_prompt
                and event.get("type") == "event_msg"
                and isinstance(payload, dict)
            ):
                if payload.get("type") == "user_message" and isinstance(
                    payload.get("message"), str
                ):
                    summary.first_prompt = payload["message"].strip()
        if since != TS_MIN or until != TS_MAX:
            if not in_time_range(summary.end_ts or summary.start_ts, since, until):
                return None
        if cwd_filter and cwd_filter not in summary.cwd:
            return None
        if not include_empty and not summary.first_prompt:
            return None
        summary.first_prompt = truncate_middle(summary.first_prompt, max_chars)
        return summary

    def list_sessions(self, **kwargs: Any) -> tuple[list[SessionSummary], Stats]:
        root: Path = kwargs["root"]
        strict: bool = kwargs["strict"]
        cwd_filter: str = kwargs["cwd_filter"]
        since: str = kwargs["since"]
        until: str = kwargs["until"]
        limit: int = kwargs["limit"]
        max_chars: int = kwargs["max_chars"]
        include_empty: bool = kwargs["include_empty"]
        stats = Stats()
        summaries: list[SessionSummary] = []
        for path in self._iter_files(root, stats):
            rows = read_jsonl(path, strict=strict, stats=stats)
            if not rows:
                continue
            stats.events_scanned += len(rows)
            summary = self._summary_from_rows(
                rows,
                path,
                since=since,
                until=until,
                cwd_filter=cwd_filter,
                max_chars=max_chars,
                include_empty=include_empty,
            )
            if summary is not None:
                summaries.append(summary)
                if (
                    limit > 0
                    and len(summaries) >= limit
                    and not cwd_filter
                    and since == TS_MIN
                    and until == TS_MAX
                ):
                    break
        summaries.sort(
            key=lambda s: (ts_key(s.end_ts or TS_MIN), s.session_id), reverse=True
        )
        if limit > 0:
            summaries = summaries[:limit]
        return summaries, stats

    def stream_sessions(self, **kwargs: Any) -> tuple[Iterable[SessionSummary], Stats]:
        root: Path = kwargs["root"]
        strict: bool = kwargs["strict"]
        cwd_filter: str = kwargs["cwd_filter"]
        since: str = kwargs["since"]
        until: str = kwargs["until"]
        limit: int = kwargs["limit"]
        max_chars: int = kwargs["max_chars"]
        include_empty: bool = kwargs["include_empty"]
        stats = Stats()

        def iterator() -> Iterable[SessionSummary]:
            emitted_count = 0
            for path in self._iter_files(root, stats):
                rows = read_jsonl(path, strict=strict, stats=stats)
                if not rows:
                    continue
                stats.events_scanned += len(rows)
                summary = self._summary_from_rows(
                    rows,
                    path,
                    since=since,
                    until=until,
                    cwd_filter=cwd_filter,
                    max_chars=max_chars,
                    include_empty=include_empty,
                )
                if summary is None:
                    continue
                emitted_count += 1
                yield summary
                if limit > 0 and emitted_count >= limit:
                    return

        return iterator(), stats

    def resolve_session(
        self, *, root: Path, strict: bool, session_id: str
    ) -> tuple[list[str], Stats]:
        stats = Stats()
        hits: list[str] = []
        for path in self._iter_files(root, stats):
            rows = read_jsonl(path, strict=strict, stats=stats)
            if not rows:
                continue
            if self._session_id(rows, path) == session_id:
                hits.append(str(path))
                break
        return hits, stats

    def collect_events(
        self, *, root: Path, strict: bool, session_id: str
    ) -> tuple[list[SessionEvent], Stats]:
        stats = Stats()
        events: list[SessionEvent] = []
        for path in self._iter_files(root, stats):
            rows = read_jsonl(path, strict=strict, stats=stats)
            if not rows or self._session_id(rows, path) != session_id:
                continue
            for line_no, event in rows:
                stats.events_scanned += 1
                ts = event.get("timestamp")
                events.append(
                    SessionEvent(
                        session_id=session_id,
                        timestamp=ts if isinstance(ts, str) else TS_MAX,
                        source=SourcePos(str(path), line_no),
                        raw=event,
                    )
                )
                stats.events_matched += 1
            break
        events.sort(
            key=lambda event: (
                ts_key(event.timestamp),
                event.source.file_path,
                event.source.line_no,
            )
        )
        return events, stats

    def render_markdown(
        self,
        *,
        session_id: str,
        events: list[SessionEvent],
        include_meta: bool,
        open_details: bool,
    ) -> str:
        cwd = ""
        call_map: dict[str, dict[str, Any]] = {}
        parts: list[str] = []
        for event in events:
            raw = event.raw
            payload = raw.get("payload")
            if raw.get("type") == "session_meta" and isinstance(payload, dict):
                raw_cwd = payload.get("cwd")
                if isinstance(raw_cwd, str) and raw_cwd:
                    cwd = raw_cwd
                    break
        parts.append(_session_header(events, session_id, cwd))
        for event in events:
            raw = event.raw
            kind = raw.get("type")
            payload = raw.get("payload")
            if kind == "session_meta" and isinstance(payload, dict):
                details = {
                    key: payload.get(key)
                    for key in (
                        "id",
                        "timestamp",
                        "cwd",
                        "originator",
                        "cli_version",
                        "source",
                        "model_provider",
                    )
                    if payload.get(key) is not None
                }
                parts.append(md_heading(2, "session"))
                parts.append(
                    "\n".join(f"**{key}:** {value}" for key, value in details.items())
                    + "\n"
                )
                continue
            if kind == "turn_context" and isinstance(payload, dict):
                details = {
                    key: payload.get(key)
                    for key in ("cwd", "approval_policy", "model", "effort", "summary")
                    if payload.get(key) is not None
                }
                sandbox = payload.get("sandbox_policy")
                if isinstance(sandbox, dict):
                    details["sandbox"] = sandbox.get("mode") or sandbox.get("type")
                    details["network"] = sandbox.get("network_access")
                parts.append(
                    md_details(
                        "context",
                        "\n".join(f"**{k}:** {v}" for k, v in details.items()),
                        open_details=False,
                    )
                )
                continue
            if kind == "event_msg" and isinstance(payload, dict):
                if payload.get("type") == "user_message" and isinstance(
                    payload.get("message"), str
                ):
                    parts.append(md_heading(2, "user"))
                    parts.append(payload["message"].rstrip() + "\n")
                elif payload.get("type") == "agent_message" and isinstance(
                    payload.get("message"), str
                ):
                    parts.append(md_heading(2, "assistant"))
                    parts.append(payload["message"].rstrip() + "\n")
                elif payload.get("type") == "agent_reasoning" and isinstance(
                    payload.get("text"), str
                ):
                    parts.append(
                        md_details("reasoning", payload["text"], open_details=True)
                    )
                continue
            if kind == "response_item" and isinstance(payload, dict):
                payload_type = payload.get("type")
                if payload_type == "reasoning":
                    summary = payload.get("summary")
                    if isinstance(summary, list):
                        text = "\n\n".join(
                            item.get("text", "")
                            for item in summary
                            if isinstance(item, dict)
                            and isinstance(item.get("text"), str)
                        )
                    else:
                        text = ""
                    if text:
                        parts.append(md_details("reasoning", text, open_details=True))
                elif payload_type in {"function_call", "custom_tool_call"}:
                    args = self._tool_args(payload.get("arguments"))
                    command = self._tool_command(args)
                    call_id = payload.get("call_id")
                    if isinstance(call_id, str):
                        call_map[call_id] = {
                            "name": payload.get("name", ""),
                            "command": command,
                        }
                    has_args = not (
                        args is None
                        or args == ""
                        or (isinstance(args, dict) and not args)
                        or (isinstance(args, list) and not args)
                    )
                    body = (md_code("bash", command) if command else "") + (
                        md_code("json", json_pretty(args)) if has_args else ""
                    )
                    parts.append(
                        md_details(
                            f"tool: {payload.get('name', '')}".strip(),
                            body,
                            open_details=False,
                        )
                    )
                elif payload_type in {
                    "function_call_output",
                    "custom_tool_call_output",
                }:
                    call = call_map.get(str(payload.get("call_id")), {})
                    output = payload.get("output")
                    text = output if isinstance(output, str) else json_pretty(output)
                    label = f"tool output: {call.get('name', 'unknown')}".strip()
                    parts.append(
                        md_details(label, md_code("txt", text), open_details=False)
                    )
            if include_meta:
                meta = {
                    key: raw.get(key)
                    for key in ("timestamp", "type")
                    if raw.get(key) is not None
                }
                if meta:
                    parts.append(
                        md_details(
                            "meta",
                            md_code("json", json_pretty(meta)),
                            open_details=open_details,
                        )
                    )
        return "".join(parts).lstrip()


BACKENDS: dict[str, Backend] = {
    "claude": ClaudeBackend(),
    "copilot": CopilotBackend(),
    "codex": CodexBackend(),
}


def build_app(backend: Backend) -> typer.Typer:
    app = typer.Typer(add_completion=False)

    @app.command("ls")
    @app.command("list", hidden=True)
    def list_sessions(
        root: Path = typer.Option(
            backend.default_root, help=f"Log root (default: {backend.default_root})."
        ),
        strict: bool = typer.Option(False, help="Fail fast on invalid JSON lines."),
        stats: bool = typer.Option(False, help="Print scan stats as JSON to stderr."),
        cwd: str = typer.Option(
            "", help="Only show sessions whose cwd contains this substring."
        ),
        since: str = typer.Option(
            TS_MIN, help="Keep sessions on/after this timestamp (ISO8601)."
        ),
        until: str = typer.Option(
            TS_MAX, help="Keep sessions on/before this timestamp (ISO8601)."
        ),
        limit: int = typer.Option(0, help="Show at most N sessions (0 = no limit)."),
        max_chars: int = typer.Option(
            500, help="Truncate the displayed first prompt to N characters."
        ),
        include_empty: bool = typer.Option(
            False, help="Include sessions even if no prompt is found."
        ),
        allow_warmup: bool = typer.Option(
            False, help="Allow 'Warmup' as the first prompt."
        ),
        allow_local_commands: bool = typer.Option(
            False, help="Allow local-command XML/stdout as the first prompt."
        ),
    ) -> None:
        colors = Colors()
        args = dict(
            root=root.expanduser(),
            strict=strict,
            cwd_filter=cwd,
            since=since,
            until=until,
            limit=limit,
            max_chars=max_chars,
            include_empty=include_empty,
            allow_warmup=allow_warmup,
            allow_local_commands=allow_local_commands,
        )
        if _can_stream_ls(cwd_filter=cwd, since=since, until=until):
            summaries, summary_stats = backend.stream_sessions(**args)
        else:
            buffered, summary_stats = backend.list_sessions(**args)
            summaries = buffered
        for summary in summaries:
            _print_summary(summary, colors)
        if stats:
            print(json_pretty(dataclasses.asdict(summary_stats)), file=sys.stderr)

    @app.command()
    def resolve(
        session_id: str = typer.Argument(..., help="Session ID to resolve."),
        root: Path = typer.Option(
            backend.default_root, help=f"Log root (default: {backend.default_root})."
        ),
        strict: bool = typer.Option(False, help="Fail fast on invalid JSON lines."),
        stats: bool = typer.Option(False, help="Print scan stats as JSON to stderr."),
    ) -> None:
        hits, resolve_stats = backend.resolve_session(
            root=root.expanduser(), strict=strict, session_id=session_id
        )
        if not hits:
            if stats:
                print(json_pretty(dataclasses.asdict(resolve_stats)), file=sys.stderr)
            raise typer.Exit(code=3)
        for hit in hits:
            print(hit)
        if stats:
            print(json_pretty(dataclasses.asdict(resolve_stats)), file=sys.stderr)

    @app.command()
    def md(
        session_id: str = typer.Argument(..., help="Session ID to render."),
        root: Path = typer.Option(
            backend.default_root, help=f"Log root (default: {backend.default_root})."
        ),
        strict: bool = typer.Option(False, help="Fail fast on invalid JSON lines."),
        stats: bool = typer.Option(False, help="Print scan stats as JSON to stderr."),
        out: str = typer.Option("-", help="Output path or '-' for stdout."),
        include_meta: bool = typer.Option(
            False, help="Include per-event meta <details> blocks."
        ),
        open_details: bool = typer.Option(
            False, help="Render <details open> for easier scanning."
        ),
    ) -> None:
        events, event_stats = backend.collect_events(
            root=root.expanduser(), strict=strict, session_id=session_id
        )
        if not events:
            if stats:
                print(json_pretty(dataclasses.asdict(event_stats)), file=sys.stderr)
            raise typer.Exit(code=3)
        markdown = backend.render_markdown(
            session_id=session_id,
            events=events,
            include_meta=include_meta,
            open_details=open_details,
        )
        if out == "-" or not out:
            sys.stdout.write(markdown)
        else:
            Path(out).write_text(markdown, encoding="utf-8")
        if stats:
            print(json_pretty(dataclasses.asdict(event_stats)), file=sys.stderr)

    @app.command()
    def dump(
        session_id: str = typer.Argument(..., help="Session ID to dump."),
        root: Path = typer.Option(
            backend.default_root, help=f"Log root (default: {backend.default_root})."
        ),
        strict: bool = typer.Option(False, help="Fail fast on invalid JSON lines."),
        stats: bool = typer.Option(False, help="Print scan stats as JSON to stderr."),
    ) -> None:
        events, event_stats = backend.collect_events(
            root=root.expanduser(), strict=strict, session_id=session_id
        )
        if not events:
            if stats:
                print(json_pretty(dataclasses.asdict(event_stats)), file=sys.stderr)
            raise typer.Exit(code=3)
        for event in events:
            obj = dict(event.raw)
            obj["_source"] = {
                "file": event.source.file_path,
                "line": event.source.line_no,
            }
            sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
        if stats:
            print(json_pretty(dataclasses.asdict(event_stats)), file=sys.stderr)

    return app


def run_backend(name: str) -> None:
    backend = BACKENDS[name]
    app = build_app(backend)
    app()
