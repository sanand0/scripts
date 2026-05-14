from __future__ import annotations

import json
from pathlib import Path
import sys

from typer.testing import CliRunner

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import podcast


RUNNER = CliRunner()


SAMPLE = """---
speakers:
  Alex: Algieba
---
Alex: First speaker's words
which may span multiple lines

including with empty lines in between

- or a list
- with multiple items.

  **Maya**: Second speaker's words.
Alex: First speaker again.
Maya: There may not be any spaces between speakers.
"""


def test_parse_markdown_segments_and_frontmatter() -> None:
    frontmatter, body = podcast.split_frontmatter(SAMPLE)
    segments = podcast.parse_segments(body)
    voice_map = podcast.assign_voices(segments, frontmatter.get("speakers", {}))

    assert [(item.speaker, item.text.splitlines()[0]) for item in segments] == [
        ("Alex", "First speaker's words"),
        ("Maya", "Second speaker's words."),
        ("Alex", "First speaker again."),
        ("Maya", "There may not be any spaces between speakers."),
    ]
    assert "including with empty lines in between" in segments[0].text
    assert "- with multiple items." in segments[0].text
    assert voice_map == {"Alex": "Algieba", "Maya": "Kore"}


def test_dry_run_cli_reports_mapping_and_items(tmp_path: Path) -> None:
    input_path = tmp_path / "script.md"
    input_path.write_text(SAMPLE, encoding="utf-8")

    result = RUNNER.invoke(
        podcast.app,
        [str(input_path), "--dry-run", "--format", "json", "--output", str(tmp_path / "out.opus")],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["status"] == "dry-run"
    assert payload["item_count"] == 4
    assert payload["speaker_voices"] == {"Alex": "Algieba", "Maya": "Kore"}
    assert payload["output"].endswith("out.opus")


def test_describe_does_not_require_input_file() -> None:
    result = RUNNER.invoke(podcast.app, ["--describe"])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["name"] == "podcast.py"
    assert "GEMINI_API_KEY" in payload["environment"]
