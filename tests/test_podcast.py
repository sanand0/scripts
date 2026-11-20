from __future__ import annotations

import json
import math
import os
from pathlib import Path
import struct
import subprocess
import sys

import pytest

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


def test_parse_segments_ignores_intro_before_first_speaker() -> None:
    segments = podcast.parse_segments(
        """# Episode notes
<!-- producer note -->

Alex: First spoken line.
Maya: Second spoken line.
"""
    )

    assert [(item.speaker, item.text) for item in segments] == [
        ("Alex", "First spoken line."),
        ("Maya", "Second spoken line."),
    ]


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
    assert output_path.name == "script.mp3"


def test_default_output_uses_markdown_basename(tmp_path: Path) -> None:
    input_path = tmp_path / "weekly.notes.md"
    input_path.write_text(SAMPLE, encoding="utf-8")

    result = RUNNER.invoke(podcast.app, [str(input_path), "--dry-run", "--format", "json"])

    assert result.exit_code == 0, result.stdout
    output_path = Path(json.loads(result.stdout)["output"])
    assert output_path.name == "weekly.notes.mp3"


def test_default_output_adds_timestamp_on_collision(tmp_path: Path) -> None:
    input_path = tmp_path / "script.md"
    input_path.write_text(SAMPLE, encoding="utf-8")
    input_path.with_suffix(".mp3").touch()

    result = RUNNER.invoke(podcast.app, [str(input_path), "--dry-run", "--format", "json"])

    assert result.exit_code == 0, result.stdout
    output_path = Path(json.loads(result.stdout)["output"])
    assert output_path.name.startswith("script-")
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


@pytest.mark.parametrize("format_name", ["opus", "mp3"])
def test_lossless_segment_cache_and_gapless_final_encode(tmp_path: Path, format_name: str) -> None:
    """FLAC preserves exact PCM between turns; the output has no accumulated padding."""
    durations = (0.19, 0.67, 1.03, 0.31, 0.89)
    parts = [
        b"".join(
            struct.pack("<h", int(21000 * math.sin(2 * math.pi * (350 + i * 125) * j / 24000)))
            for j in range(int(24000 * seconds))
        )
        for i, seconds in enumerate(durations)
    ]
    paths = []
    for i, pcm in enumerate(parts):
        path = tmp_path / f"{i}.flac"
        podcast.render_pcm_to_flac(pcm, path)
        paths.append(path)

    listing = tmp_path / "segments.txt"
    listing.write_text("".join(f"file '{path}'\n" for path in paths))
    decoded_lossless = subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-f", "concat", "-safe", "0",
         "-i", str(listing), "-f", "s16le", "-ac", "1", "-ar", "24000", "-"],
        check=True, capture_output=True,
    ).stdout
    assert decoded_lossless == b"".join(parts)

    output = tmp_path / f"episode.{format_name}"
    podcast.stitch_segments(paths, output, format_name)
    codec = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
         "stream=codec_name", "-of", "default=nk=1:nw=1", str(output)],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    assert codec == format_name
    decoded = subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-i", str(output),
         "-f", "s16le", "-ac", "1", "-ar", "24000", "-"],
        check=True, capture_output=True,
    ).stdout
    assert abs(len(decoded) - sum(map(len, parts))) <= 480  # 10 ms at 24kHz, 16-bit


def test_podcast_reuses_lossless_cache_across_formats(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "notes.md"
    source.write_text("Alex: Hello\nMaya: Goodbye\nAlex: Hello\n")
    calls = []

    def fake_gemini(segment: podcast.Segment, voice: str, model: str) -> bytes:
        calls.append((segment.text, voice, model))
        return b"\x00\x00" * 4800  # 200 ms of 24kHz mono PCM

    monkeypatch.setattr(podcast, "request_gemini_audio", fake_gemini)
    cache = tmp_path / "cache"
    podcast.render_podcast(source, tmp_path / "episode.mp3", "test-model", cache, False, 2)
    podcast.render_podcast(source, tmp_path / "episode.opus", "test-model", cache, False, 2)
    assert len(calls) == 2
    assert len(list((cache / "segments").glob("*.flac"))) == 2
    assert (tmp_path / "episode.mp3").stat().st_size > 0
    assert (tmp_path / "episode.opus").stat().st_size > 0


def test_stitch_handles_apostrophe_in_cache_path(tmp_path: Path) -> None:
    segment = tmp_path / "someone's cache" / "sample.flac"
    podcast.render_pcm_to_flac(b"\x00\x00" * 4800, segment)
    output = tmp_path / "episode.opus"
    podcast.stitch_segments([segment], output, "opus")
    assert output.stat().st_size > 0


def test_failed_encoding_does_not_clobber_existing_output(tmp_path: Path, monkeypatch) -> None:
    cached = tmp_path / "cached.flac"
    output = tmp_path / "episode.opus"
    cached.write_bytes(b"old cached content")
    output.write_bytes(b"old podcast content")

    def fail_after_partial_output(args: list[str], **kwargs) -> None:
        Path(args[-1]).write_bytes(b"partial output")
        raise subprocess.CalledProcessError(1, args)

    monkeypatch.setattr(podcast.subprocess, "run", fail_after_partial_output)
    with pytest.raises(subprocess.CalledProcessError):
        podcast.render_pcm_to_flac(b"\x00\x00" * 4800, cached)
    with pytest.raises(subprocess.CalledProcessError):
        podcast.stitch_segments([cached], output, "opus")

    assert cached.read_bytes() == b"old cached content"
    assert output.read_bytes() == b"old podcast content"
    assert not list(tmp_path.glob(".podcast-*"))
