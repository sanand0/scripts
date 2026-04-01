from __future__ import annotations

from pathlib import Path
import sys

from typer.testing import CliRunner

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sessionlog import SessionSummary, Stats, build_app


RUNNER = CliRunner()


class FakeBackend:
    name = "fake"
    default_root = Path("/tmp/fake")

    def __init__(self) -> None:
        self.calls: list[str] = []

    def stream_sessions(self, **_: object):
        self.calls.append("stream")
        return (
            iter(
                [
                    SessionSummary(
                        session_id="streamed-session",
                        cwd="/tmp/project",
                        end_ts="2026-04-01T00:00:00Z",
                        first_prompt="Stream this output",
                        files_count=2,
                        source_kind="jsonl",
                    )
                ]
            ),
            Stats(),
        )

    def list_sessions(self, **_: object):
        self.calls.append("list")
        return (
            [
                SessionSummary(
                    session_id="buffered-session",
                    cwd="/tmp/project",
                    end_ts="2026-04-01T00:00:00Z",
                    first_prompt="Buffer this output",
                    files_count=1,
                    source_kind="jsonl",
                )
            ],
            Stats(),
        )

    def resolve_session(self, **_: object):
        raise AssertionError("resolve_session should not be called in ls tests")

    def collect_events(self, **_: object):
        raise AssertionError("collect_events should not be called in ls tests")

    def render_markdown(self, **_: object):
        raise AssertionError("render_markdown should not be called in ls tests")


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
