#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "httpx>=0.27",
#   "python-dotenv>=1.0.1",
#   "pyyaml>=6.0.2",
#   "tenacity>=8.3",
#   "typer>=0.12",
# ]
# ///
"""Render a speaker-labeled Markdown file as a podcast with Gemini TTS.

Examples:
  podcast.py notes.md --dry-run
  podcast.py notes.md --output episode.opus
  podcast.py notes.md --dry-run --format json | jaq .speaker_voices
  podcast.py --describe | jaq .
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from typing import Any

from dotenv import load_dotenv
import httpx
import typer
import yaml
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential


DEFAULT_MODEL = "gemini-2.5-flash-preview-tts"
DEFAULT_CACHE_DIR = Path("~/.cache/sanand-scripts/podcast").expanduser()
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
VOICE_NAMES = [
    "Algieba",
    "Kore",
    "Orus",
    "Zephyr",
    "Achird",
    "Achernar",
    "Alnilam",
    "Aoede",
    "Charon",
    "Autonoe",
    "Enceladus",
    "Callirrhoe",
    "Fenrir",
    "Gacrux",
    "Iapetus",
    "Laomedeia",
    "Puck",
    "Leda",
    "Rasalgethi",
    "Pulcherrima",
    "Sadachbia",
    "Sulafat",
    "Sadaltager",
    "Vindemiatrix",
    "Schedar",
    "Umbriel",
    "Zubenelgenubi",
]

FRONTMATTER_RE = re.compile(r"\A---\s*\n(?P<body>.*?\n?)---\s*\n?", re.DOTALL)
SPEAKER_RE = re.compile(r"^\s*(?P<raw>\S+)\s*:\s*(?P<text>.*)$")

app = typer.Typer(add_completion=False, no_args_is_help=True, help=__doc__)
load_dotenv(dotenv_path=Path.cwd() / ".env")


@dataclass(frozen=True)
class Segment:
    speaker: str
    text: str


def log(message: str) -> None:
    """Write operator-facing status without polluting stdout."""
    print(message, file=sys.stderr, flush=True)


def default_output_path() -> Path:
    """Return the timestamped default output path."""
    return Path(f"podcast-{datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}.opus")


def split_frontmatter(markdown: str) -> tuple[dict[str, Any], str]:
    """Return YAML front matter and Markdown body."""
    match = FRONTMATTER_RE.match(markdown)
    if not match:
        return {}, markdown
    frontmatter = yaml.safe_load(match.group("body")) or {}
    if not isinstance(frontmatter, dict):
        raise typer.BadParameter("YAML front matter must be a mapping")
    return frontmatter, markdown[match.end() :]


def normalize_speaker(raw: str) -> str:
    """Strip a speaker label down to letters, numbers, hyphens, and underscores."""
    return re.sub(r"[^A-Za-z0-9_-]", "", raw).strip()


def parse_segments(markdown: str) -> list[Segment]:
    """Split speaker-labeled Markdown into sequential spoken segments."""
    segments: list[Segment] = []
    current_speaker: str | None = None
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_speaker, current_lines
        if current_speaker is None:
            return
        text = "\n".join(current_lines).strip()
        if text:
            segments.append(Segment(current_speaker, text))
        current_speaker = None
        current_lines = []

    for line in markdown.splitlines():
        match = SPEAKER_RE.match(line)
        speaker = normalize_speaker(match.group("raw")) if match else ""
        if match and speaker:
            flush()
            current_speaker = speaker
            current_lines = [match.group("text")]
        elif current_speaker is not None:
            current_lines.append(line)
        elif line.strip():
            raise typer.BadParameter(f"Text before first speaker label: {line[:80]}")

    flush()
    if not segments:
        raise typer.BadParameter("No speaker-labeled items found")
    return segments


def assign_voices(segments: list[Segment], configured: dict[str, Any]) -> dict[str, str]:
    """Assign configured voices first, then the first unused pre-built voices."""
    speakers = list(dict.fromkeys(segment.speaker for segment in segments))
    voice_map: dict[str, str] = {}
    used_voices = set()

    for speaker in speakers:
        voice = str(configured.get(speaker, "")).strip()
        if voice:
            if voice not in VOICE_NAMES:
                raise typer.BadParameter(f"Unknown voice {voice!r} for speaker {speaker!r}")
            voice_map[speaker] = voice
            used_voices.add(voice)

    unassigned = (voice for voice in VOICE_NAMES if voice not in used_voices)
    for speaker in speakers:
        if speaker in voice_map:
            continue
        try:
            voice_map[speaker] = next(unassigned)
        except StopIteration as exc:
            raise typer.BadParameter("More speakers than available pre-built voices") from exc
    return voice_map


def build_tts_prompt(segment: Segment) -> str:
    """Build a compact Gemini prompt for one segment."""
    return "\n".join(
        [
            "Synthesize speech for the following podcast segment.",
            "Do not read these instructions aloud.",
            "Only speak the transcript under TRANSCRIPT.",
            "TRANSCRIPT",
            segment.text.strip(),
        ]
    )


def build_gemini_payload(segment: Segment, voice: str) -> dict[str, Any]:
    """Build one Gemini TTS request payload."""
    return {
        "contents": [{"role": "user", "parts": [{"text": build_tts_prompt(segment)}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}},
            },
        },
    }


def cache_key(segment: Segment, voice: str, model: str) -> str:
    """Hash all request inputs that affect the cached segment audio."""
    payload = {
        "model": model,
        "voice": voice,
        "text": segment.text,
        "prompt_version": 1,
        "audio_format": "opus",
        "pcm": {"format": "s16le", "rate": 24000, "channels": 1},
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def cleanup_cache(cache_dir: Path) -> None:
    """Delete cache files older than one day."""
    if not cache_dir.exists():
        return
    cutoff = time.time() - timedelta(days=1).total_seconds()
    for path in cache_dir.rglob("*"):
        if path.is_file() and path.stat().st_mtime < cutoff:
            path.unlink()


def is_retryable(exc: BaseException) -> bool:
    """Return True for transient Gemini failures."""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in RETRYABLE_STATUS_CODES
    return isinstance(exc, httpx.TransportError)


def raise_for_status_with_body(response: httpx.Response) -> None:
    """Raise HTTP errors after echoing useful response text."""
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError:
        body = response.text.strip()
        if body:
            log(body[:2000])
        raise


@retry(
    retry=retry_if_exception(is_retryable),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)
def request_gemini_audio(segment: Segment, voice: str, model: str) -> bytes:
    """Call Gemini and return raw PCM audio bytes."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise typer.BadParameter("GEMINI_API_KEY is not set in .env or the environment")

    response = httpx.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        json=build_gemini_payload(segment, voice),
        timeout=300,
    )
    raise_for_status_with_body(response)
    result = response.json()
    audio_b64 = result["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
    return base64.b64decode(audio_b64)


def render_pcm_to_opus(audio_pcm: bytes, output_path: Path) -> None:
    """Convert Gemini raw 24kHz mono PCM to an Opus segment."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pcm_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pcm", dir=output_path.parent) as f:
            f.write(audio_pcm)
            pcm_path = Path(f.name)
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-v",
                "error",
                "-y",
                "-f",
                "s16le",
                "-ar",
                "24000",
                "-ac",
                "1",
                "-i",
                str(pcm_path),
                "-c:a",
                "libopus",
                "-b:a",
                "48k",
                str(output_path),
            ],
            check=True,
        )
    finally:
        if pcm_path and pcm_path.exists():
            pcm_path.unlink()


def stitch_segments(segment_paths: list[Path], output_path: Path) -> None:
    """Concatenate segment files into the final podcast."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    list_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", delete=False, suffix=".txt", dir=output_path.parent, encoding="utf-8"
        ) as f:
            for segment_path in segment_paths:
                f.write(f"file '{segment_path.resolve()}'\n")
            list_path = Path(f.name)
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-v",
                "error",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_path),
                "-c:a",
                "libopus",
                "-b:a",
                "48k",
                str(output_path),
            ],
            check=True,
        )
    finally:
        if list_path and list_path.exists():
            list_path.unlink()


def render_podcast(
    markdown_path: Path,
    output_path: Path,
    model: str,
    cache_dir: Path,
    dry_run: bool,
) -> dict[str, Any]:
    """Parse Markdown, generate cached segments, and stitch the final audio."""
    cleanup_cache(cache_dir)
    frontmatter, body = split_frontmatter(markdown_path.read_text(encoding="utf-8"))
    configured_speakers = frontmatter.get("speakers", {})
    if configured_speakers is None:
        configured_speakers = {}
    if not isinstance(configured_speakers, dict):
        raise typer.BadParameter("front matter `speakers` must be a mapping")

    segments = parse_segments(body)
    voice_map = assign_voices(segments, configured_speakers)
    result = {
        "status": "dry-run" if dry_run else "ok",
        "input": str(markdown_path.resolve()),
        "output": str(output_path.resolve()),
        "model": model,
        "cache_dir": str(cache_dir.resolve()),
        "item_count": len(segments),
        "speaker_voices": voice_map,
        "items": [
            {
                "index": index,
                "speaker": segment.speaker,
                "voice": voice_map[segment.speaker],
                "chars": len(segment.text),
            }
            for index, segment in enumerate(segments, start=1)
        ],
    }

    log("Speaker voices: " + ", ".join(f"{speaker}={voice}" for speaker, voice in voice_map.items()))
    log(f"Items to generate: {len(segments)}")
    if dry_run:
        return result

    segment_dir = cache_dir / "segments"
    segment_paths = []
    for index, segment in enumerate(segments, start=1):
        voice = voice_map[segment.speaker]
        segment_path = segment_dir / f"{cache_key(segment, voice, model)}.opus"
        segment_paths.append(segment_path)
        prefix = f"{index}/{len(segments)}"
        if segment_path.exists():
            log(f"{prefix} cache hit {segment.speaker} ({voice})")
            continue
        log(f"{prefix} generating {segment.speaker} ({voice})")
        audio_pcm = request_gemini_audio(segment, voice, model)
        render_pcm_to_opus(audio_pcm, segment_path)

    log(f"Stitching {len(segment_paths)} segments -> {output_path}")
    stitch_segments(segment_paths, output_path)
    return result


def describe() -> dict[str, Any]:
    """Return a compact machine-readable CLI contract."""
    return {
        "name": "podcast.py",
        "description": __doc__,
        "input": "One Markdown file with speaker labels like `Alex: words`.",
        "environment": ["GEMINI_API_KEY"],
        "options": {
            "markdown_file": "Required path to the input Markdown file.",
            "--output": "Output audio path. Defaults to podcast-YYYY-MM-DD-HH-MM-SS.opus.",
            "--model": f"Gemini TTS model. Default: {DEFAULT_MODEL}.",
            "--dry-run": "Parse and report work without calling Gemini or ffmpeg.",
            "--format": "text or json.",
        },
        "examples": [
            "podcast.py notes.md --dry-run",
            "podcast.py notes.md --output episode.opus",
            "podcast.py notes.md --dry-run --format json | jaq .speaker_voices",
        ],
    }


@app.command()
def main(
    markdown_file: Path | None = typer.Argument(None, dir_okay=False, help="Input Markdown file."),
    output: Path | None = typer.Option(None, "--output", "-o", help="Output .opus path."),
    model: str = typer.Option(DEFAULT_MODEL, "--model", help="Gemini TTS model."),
    cache_dir: Path = typer.Option(DEFAULT_CACHE_DIR, "--cache-dir", help="Cache directory."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Parse only; do not call Gemini or ffmpeg."),
    output_format: str = typer.Option("text", "--format", help="text or json."),
    show_describe: bool = typer.Option(False, "--describe", help="Print machine-readable CLI contract."),
) -> None:
    """Render a speaker-labeled Markdown file as a podcast.

    Examples:
      podcast.py notes.md --dry-run
      podcast.py notes.md --output episode.opus
      podcast.py notes.md --dry-run --format json | jaq .speaker_voices
      podcast.py --describe | jaq .
    """
    if show_describe:
        print(json.dumps(describe(), indent=2))
        return
    if markdown_file is None:
        raise typer.BadParameter("markdown_file is required unless --describe is used")
    if not markdown_file.exists():
        raise typer.BadParameter(f"{markdown_file} does not exist")
    if output_format not in {"text", "json"}:
        raise typer.BadParameter("--format must be text or json")

    result = render_podcast(
        markdown_file,
        output or default_output_path(),
        model=model,
        cache_dir=cache_dir.expanduser(),
        dry_run=dry_run,
    )
    if output_format == "json":
        print(json.dumps(result, indent=2))
    else:
        print(f"{result['status']}\t{result['output']}\t{result['item_count']} items")


if __name__ == "__main__":
    app()
