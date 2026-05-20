from __future__ import annotations

import json
import os
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
    assert payload["audio_format"] == "opus"
    assert payload["parallel"] == 4
    assert payload["output"].endswith("out.opus")


def test_parallel_cli_option_is_reported(tmp_path: Path) -> None:
    input_path = tmp_path / "script.md"
    input_path.write_text(SAMPLE, encoding="utf-8")

    result = RUNNER.invoke(
        podcast.app,
        [str(input_path), "--dry-run", "--format", "json", "--parallel", "2"],
    )

    assert result.exit_code == 0, result.stdout
    assert json.loads(result.stdout)["parallel"] == 2


def test_default_output_is_mp3(tmp_path: Path) -> None:
    input_path = tmp_path / "script.md"
    input_path.write_text(SAMPLE, encoding="utf-8")

    result = RUNNER.invoke(podcast.app, [str(input_path), "--dry-run", "--format", "json"])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["audio_format"] == "mp3"
    output_path = Path(payload["output"])
    assert output_path.suffix == ".mp3"
    assert output_path.name.startswith("script-")


def test_default_output_uses_markdown_basename(tmp_path: Path) -> None:
    input_path = tmp_path / "weekly.notes.md"
    input_path.write_text(SAMPLE, encoding="utf-8")

    result = RUNNER.invoke(podcast.app, [str(input_path), "--dry-run", "--format", "json"])

    assert result.exit_code == 0, result.stdout
    output_path = Path(json.loads(result.stdout)["output"])
    assert output_path.name.startswith("weekly.notes-")
    assert output_path.suffix == ".mp3"


def test_unexpected_gemini_response_logs_full_body(monkeypatch, capsys) -> None:
    body = {"candidates": [{"finishReason": "SAFETY", "safetyRatings": [{"blocked": True}]}]}

    def fake_post(*args, **kwargs):
        return podcast.httpx.Response(
            200,
            json=body,
            request=podcast.httpx.Request("POST", "https://example.test/generateContent"),
        )

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(podcast.httpx, "post", fake_post)

    try:
        podcast.request_gemini_audio(podcast.Segment("Alex", "Hello"), "Algieba", "test-model")
    except RuntimeError as exc:
        assert "inline audio data" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")

    assert json.dumps(body, separators=(",", ":")) in capsys.readouterr().err


def test_describe_does_not_require_input_file() -> None:
    result = RUNNER.invoke(podcast.app, ["--describe"])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["name"] == "podcast.py"
    assert "GEMINI_API_KEY" in payload["environment"]


def test_load_environment_falls_back_to_script_dir_env(tmp_path: Path, monkeypatch) -> None:
    current_dir = tmp_path / "current"
    script_dir = tmp_path / "script"
    current_dir.mkdir()
    script_dir.mkdir()
    script_dir.joinpath(".env").write_text("GEMINI_API_KEY=fallback-key\n", encoding="utf-8")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    podcast.load_environment(current_dir=current_dir, script_dir=script_dir)

    assert os.environ["GEMINI_API_KEY"] == "fallback-key"
