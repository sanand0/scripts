from __future__ import annotations

import json
import sqlite3
from pathlib import Path
import sys

from typer.testing import CliRunner

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agentlog import (
    CopilotBackend,
    SearchPattern,
    SessionEvent,
    SessionSummary,
    SourcePos,
    Stats,
    _extract_matching_lines,
    _event_kind,
    _parse_kind_filters,
    _parse_search_pattern,
    _truncate_search_line,
    build_app,
    build_root_app,
)


RUNNER = CliRunner()


class FakeBackend:
    name = "fake"
    default_root = Path("/tmp/fake")

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.last_kind_filter: frozenset[str] = frozenset()
        self.last_search_pattern: str | None = None

    def stream_sessions(self, **_: object):
        search_re = _.get("search_re")
        width = _["width"]
        self.calls.append("stream")
        self.last_search_pattern = None if search_re is None else search_re.pattern
        search_preview = ""
        if search_re is not None:
            lines = _extract_matching_lines(
                "Needle really long matching content that should be truncated for display",
                search_re,
                width,
            )
            search_preview = "\n".join(lines)
        matches = search_re is None or bool(search_preview)
        return (
            iter(
                [
                    SessionSummary(
                        session_id="streamed-session",
                        cwd="/tmp/project",
                        end_ts="2026-04-01T00:00:00Z",
                        first_prompt="Stream this output",
                        search_preview=search_preview,
                        files_count=2,
                        source_kind="jsonl",
                    )
                ]
                if matches
                else []
            ),
            Stats(),
        )

    def list_sessions(self, **_: object):
        search_re = _.get("search_re")
        width = _["width"]
        self.calls.append("list")
        self.last_search_pattern = None if search_re is None else search_re.pattern
        search_preview = ""
        if search_re is not None:
            lines = _extract_matching_lines(
                "Buffer Needle content used for filtered output",
                search_re,
                width,
            )
            search_preview = "\n".join(lines)
        matches = search_re is None or bool(search_preview)
        return (
            (
                [
                    SessionSummary(
                        session_id="buffered-session",
                        cwd="/tmp/project",
                        end_ts="2026-04-01T00:00:00Z",
                        first_prompt="Buffer this output",
                        search_preview=search_preview,
                        files_count=1,
                        source_kind="jsonl",
                    )
                ]
                if matches
                else []
            ),
            Stats(),
        )

    def resolve_session(self, **_: object):
        raise AssertionError("resolve_session should not be called in ls tests")

    def collect_events(self, **_: object):
        session_id = _["session_id"]
        return (
            [
                SessionEvent(
                    session_id=session_id,
                    timestamp="2026-04-01T00:00:00Z",
                    source=SourcePos("/tmp/fake.jsonl", 1),
                    raw={"type": "user"},
                ),
                SessionEvent(
                    session_id=session_id,
                    timestamp="2026-04-01T00:00:01Z",
                    source=SourcePos("/tmp/fake.jsonl", 2),
                    raw={"type": "assistant"},
                ),
                SessionEvent(
                    session_id=session_id,
                    timestamp="2026-04-01T00:00:02Z",
                    source=SourcePos("/tmp/fake.jsonl", 3),
                    raw={"type": "system"},
                ),
            ],
            Stats(),
        )

    def render_markdown(
        self,
        *,
        session_id: str,
        events: list[SessionEvent],
        include_meta: bool,
        open_details: bool,
        kind_filter: frozenset[str],
    ):
        del include_meta, open_details
        self.last_kind_filter = kind_filter
        return f"# {session_id}\n" + "\n".join(
            _event_kind(event.raw)
            for event in events
            if not kind_filter or _event_kind(event.raw) in kind_filter
        )


def test_ls_streams_by_default() -> None:
    backend = FakeBackend()

    result = RUNNER.invoke(build_app(backend), ["ls"])

    assert result.exit_code == 0, result.stdout
    assert backend.calls == ["stream"]
    assert "streamed-session" in result.stdout
    assert "Stream this output" in result.stdout


def test_ls_uses_buffered_path_when_filters_require_global_scan() -> None:
    backend = FakeBackend()

    result = RUNNER.invoke(build_app(backend), ["ls", "--cwd", "/tmp"])

    assert result.exit_code == 0, result.stdout
    assert backend.calls == ["list"]
    assert "buffered-session" in result.stdout
    assert "Buffer this output" in result.stdout


def test_root_app_routes_backend_subcommands() -> None:
    backend = FakeBackend()

    result = RUNNER.invoke(build_root_app({"claude": backend}), ["claude", "ls"])

    assert result.exit_code == 0, result.stdout
    assert backend.calls == ["stream"]
    assert "streamed-session" in result.stdout


def test_parse_kind_filters_accepts_commas_and_repeated_values() -> None:
    assert _parse_kind_filters(["user,system", "assistant", "system"]) == frozenset(
        {"user", "system", "assistant"}
    )


def test_md_kind_filter_accepts_comma_separated_values() -> None:
    backend = FakeBackend()

    result = RUNNER.invoke(build_app(backend), ["md", "session-1", "--kind", "user,system"])

    assert result.exit_code == 0, result.stdout
    assert backend.last_kind_filter == frozenset({"user", "system"})
    assert result.stdout.splitlines() == ["# session-1", "user", "system"]


def test_dump_kind_filter_accepts_repeated_flags() -> None:
    backend = FakeBackend()

    result = RUNNER.invoke(
        build_app(backend),
        ["dump", "session-1", "--kind", "user", "--kind", "system"],
    )

    assert result.exit_code == 0, result.stdout
    payloads = [json.loads(line) for line in result.stdout.splitlines()]
    assert [payload["type"] for payload in payloads] == ["user", "system"]


def test_md_accepts_multiple_session_ids() -> None:
    backend = FakeBackend()

    result = RUNNER.invoke(build_app(backend), ["md", "session-1", "session-2"])

    assert result.exit_code == 0, result.stdout
    assert "# session-1" in result.stdout
    assert "# session-2" in result.stdout


def test_ls_search_streams_search_results() -> None:
    backend = FakeBackend()

    result = RUNNER.invoke(build_app(backend), ["ls", "--search", "Needle"])

    assert result.exit_code == 0, result.stdout
    assert backend.calls == ["stream"]
    assert backend.last_search_pattern == "Needle"
    assert "streamed-session" in result.stdout
    assert "Needle really long matching content" in result.stdout
    assert "Stream this output" not in result.stdout


def test_parse_search_pattern_defaults_to_case_insensitive_substring() -> None:
    search = _parse_search_pattern("auth.")

    assert isinstance(search, SearchPattern)
    assert search.pattern == "auth."
    assert search.search("prefix AUTH.suffix")
    assert not search.search("prefix autx.suffix")


def test_parse_search_pattern_supports_regex_delimiters_and_i_flag() -> None:
    search = _parse_search_pattern(r"/auth./i")

    assert isinstance(search, SearchPattern)
    assert search.pattern == r"/auth./i"
    assert search.search("AUTHx")
    assert not search.search("autx")


def test_parse_search_pattern_supports_case_sensitive_regex() -> None:
    search = _parse_search_pattern(r"/auth./")

    assert isinstance(search, SearchPattern)
    assert search.search("authx")
    assert not search.search("AUTHx")


def test_search_output_truncates_lines_to_width() -> None:
    backend = FakeBackend()

    result = RUNNER.invoke(build_app(backend), ["ls", "--search", "Needle", "--width", "20"])

    assert result.exit_code == 0, result.stdout
    assert "Needle really..." in result.stdout
    assert "Needle really long matching content" not in result.stdout


def test_truncate_search_line_uses_ellipsis() -> None:
    assert _truncate_search_line("abcdefghijkl", 8) == "abcde..."


def test_copilot_md_includes_session_state_details_for_db_sessions(tmp_path: Path) -> None:
    root = tmp_path / "copilot"
    root.mkdir()
    conn = sqlite3.connect(root / "session-store.db")
    conn.execute(
        """
        create table sessions (
            id text primary key,
            cwd text,
            repository text,
            branch text,
            summary text,
            created_at text,
            updated_at text,
            host_type text
        )
        """
    )
    conn.execute(
        """
        create table turns (
            session_id text,
            turn_index integer,
            user_message text,
            assistant_response text,
            timestamp text
        )
        """
    )
    conn.execute(
        """
        insert into sessions (id, cwd, repository, branch, summary, created_at, updated_at, host_type)
        values (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "session-1",
            "/tmp/project",
            "owner/repo",
            "main",
            "Summary",
            "2026-04-01T00:00:00Z",
            "2026-04-01T00:00:10Z",
            "github",
        ),
    )
    conn.execute(
        """
        insert into turns (session_id, turn_index, user_message, assistant_response, timestamp)
        values (?, ?, ?, ?, ?)
        """,
        (
            "session-1",
            0,
            "User asks",
            "Assistant replies",
            "2026-04-01T00:00:05Z",
        ),
    )
    conn.commit()
    conn.close()

    events_path = root / "session-state" / "session-1" / "events.jsonl"
    events_path.parent.mkdir(parents=True)
    rows = [
        {
            "type": "assistant.message",
            "timestamp": "2026-04-01T00:00:05Z",
            "data": {
                "content": "Assistant replies",
                "reasoningText": "Step-by-step reasoning",
                "toolRequests": [
                    {
                        "toolCallId": "tool-1",
                        "name": "read_bash",
                        "arguments": {"shellId": "abc"},
                    }
                ],
            },
        },
        {
            "type": "tool.execution_start",
            "timestamp": "2026-04-01T00:00:06Z",
            "data": {
                "toolCallId": "tool-1",
                "toolName": "read_bash",
                "arguments": {"shellId": "abc"},
            },
        },
        {
            "type": "tool.execution_complete",
            "timestamp": "2026-04-01T00:00:07Z",
            "data": {
                "toolCallId": "tool-1",
                "success": True,
                "result": {"content": "tool output"},
            },
        },
        {
            "type": "skill.invoked",
            "timestamp": "2026-04-01T00:00:08Z",
            "data": {
                "name": "plan",
                "path": "/tmp/skills/plan/SKILL.md",
                "content": "# plan",
            },
        },
        {
            "type": "hook.start",
            "timestamp": "2026-04-01T00:00:09Z",
            "data": {"hookType": "postToolUse", "input": {"toolName": "read_bash"}},
        },
    ]
    with events_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row))
            handle.write("\n")

    backend = CopilotBackend()
    events, _ = backend.collect_events(root=root, strict=True, session_id="session-1")
    markdown = backend.render_markdown(
        session_id="session-1",
        events=events,
        include_meta=False,
        open_details=False,
        kind_filter=frozenset(),
    )

    assert "## user" in markdown
    assert "## assistant" in markdown
    assert "<summary><strong>reasoning</strong></summary>" in markdown
    assert "<summary><strong>tool request: read_bash (tool-1)</strong></summary>" in markdown
    assert "<summary><strong>tool start: read_bash (tool-1)</strong></summary>" in markdown
    assert "<summary><strong>tool result: tool-1</strong></summary>" in markdown
    assert "<summary><strong>skill invoked: plan</strong></summary>" in markdown
    assert "<summary><strong>hook.start</strong></summary>" in markdown
