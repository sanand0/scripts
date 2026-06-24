from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import mcpserver


def test_trim_long_lines_keeps_each_line_under_50kb() -> None:
    line = "a" * (60 * 1024)

    trimmed = mcpserver.trim_long_lines(f"small\n{line}\nend")
    long_line = trimmed.splitlines()[1]

    assert len(long_line.encode()) == mcpserver.MAX_LINE_BYTES
    assert long_line.startswith("a" * mcpserver.TRIM_PREFIX_BYTES)
    assert mcpserver.TRIM_MARKER in long_line
    assert trimmed.splitlines() == ["small", long_line, "end"]


def test_log_bash_command_includes_request_after_command(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(mcpserver, "LOG_DIR", tmp_path)

    mcpserver.log_bash_command("printf ok", "ok", {"headers": [{"name": "x-test", "value": "1"}]})

    [log_path] = tmp_path.glob("*.md")
    markdown = log_path.read_text()
    assert markdown.index("## Command") < markdown.index("## Request") < markdown.index("## Output")
    assert '"x-test"' in markdown
    assert "printf ok" in markdown
