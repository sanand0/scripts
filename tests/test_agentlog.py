from __future__ import annotations

import json
from pathlib import Path
import sys

from typer.testing import CliRunner

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agentlog import (
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
