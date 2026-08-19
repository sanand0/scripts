#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["google-genai>=1.67.0", "python-dotenv>=1.0.1", "pyyaml>=6.0.2", "typer>=0.12"]
# ///
"""Transcribe audio files into Markdown call notes."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

import typer

DEFAULT_INPUT_DIR = Path("/home/sanand/Documents/calls")
DEFAULT_OUTPUT_DIR = Path("/home/sanand/Dropbox/notes/transcripts")
DEFAULT_PROMPT_FILE = Path("/home/sanand/code/blog/pages/prompts/transcribe-call-recording.md")
DEFAULT_SYSTEM_PROMPT = "Transcribe"
DEFAULT_MODEL = "gemini-3-flash-preview"
DEFAULT_CHUNK_MINUTES = 30.0
DEFAULT_CACHE_DIR = Path.home() / ".cache" / "sanand-scripts" / "transcribe_calls"
CHUNK_CACHE_TTL_SECONDS = 24 * 60 * 60
CHUNK_OVERLAP_SECONDS = 1.0
FRIENDLY_CHUNK_MINUTES = (30.0, 25.0, 20.0, 15.0)
CHUNK_CONTEXT_MAX_LINES = 40
CHUNK_CONTEXT_MAX_CHARS = 12_000
PRICES_URL = "https://raw.githubusercontent.com/simonw/llm-prices/refs/heads/main/data/google.json"
DEFAULT_PRICES_CACHE_PATH = DEFAULT_CACHE_DIR / "google-prices.json"
AUDIO_SUFFIXES = {".aac", ".flac", ".m4a", ".mp3", ".oga", ".ogg", ".opus", ".wav", ".webm"}
CODE_FENCE_RE = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)
TRANSCRIPT_PART_SEPARATOR = "\n\n---\n\n"
TRANSCRIPT_LINE_RE = re.compile(
    r"^\*\*[^*\n]+(?:\*\*:?|:\*\*)(?: \[\d{2}:\d{2}(?::\d{2})?\])? .+"
)
SPEAKER_LINE_RE = re.compile(r"^\*\*(?P<speaker>[^*\n]+?)(?:\*\*:?|:\*\*)")
FRONTMATTER_RE = re.compile(r"\A---\n(?P<body>.*?\n?)---\n?", re.DOTALL)
TRANSCRIPT_SECTION_RE = re.compile(
    r"(?ms)^##\s+Transcript\s*$\n?(?P<body>.*?)(?=^##\s+|\Z)"
)
TRANSCRIPT_CONTENT_RG_PATTERN = r"^##\s+Transcript\s*$\n(?:\s*\n)*(?!##\s+)\S"

app = typer.Typer(add_completion=False, no_args_is_help=False, help=__doc__)


def load_environment(current_dir: Path | None = None, script_dir: Path | None = None) -> None:
    """Load current .env first, then script-directory .env for a missing Gemini key."""
    from dotenv import dotenv_values, load_dotenv

    current_dir = current_dir or Path.cwd()
    script_dir = script_dir or Path(__file__).resolve().parent
    load_dotenv(dotenv_path=current_dir / ".env")
    if not os.environ.get("GEMINI_API_KEY"):
        api_key = dotenv_values(script_dir / ".env").get("GEMINI_API_KEY")
        if api_key:
            os.environ["GEMINI_API_KEY"] = api_key


@dataclass(frozen=True)
class UsageCost:
    prompt_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: float


@dataclass(frozen=True)
class TranscriptionResult:
    transcript: str
    usage: UsageCost
    warnings: tuple[InvalidTranscriptWarning, ...] = ()


@dataclass(frozen=True)
class InvalidTranscriptWarning:
    section_index: int
    section_count: int
    matching_lines: int


@dataclass(frozen=True)
class ResolvedPrompts:
    system_prompt: str
    user_prompt: str | None
    note_prompt: str


def resolve_prompts(system_prompt: str, stored_prompt: str | None, cli_prompt: str | None) -> ResolvedPrompts:
    """Resolve the prompt to send to Gemini and the prompt to persist in frontmatter.

    Both prefer the CLI `--prompt`, then the note's stored prompt, then the system prompt.
    The stored/system prompt is only sent to Gemini as user context when it differs from
    the system prompt; sending it verbatim as both would be redundant.
    """
    cleaned_system_prompt = system_prompt.strip()
    cleaned_stored_prompt = stored_prompt.strip() if stored_prompt else None
    if cli_prompt is not None:
        user_prompt = cli_prompt
    elif cleaned_stored_prompt and cleaned_stored_prompt != cleaned_system_prompt:
        user_prompt = cleaned_stored_prompt
    else:
        user_prompt = None
    note_prompt = cli_prompt or cleaned_stored_prompt or cleaned_system_prompt
    return ResolvedPrompts(system_prompt=system_prompt, user_prompt=user_prompt, note_prompt=note_prompt)


def render_prompt_metadata(prompt: str) -> str:
    """Render prompt metadata as a YAML block scalar."""
    lines = prompt.strip().splitlines() or [""]
    return "prompt: |-\n" + "".join(f"  {line}\n" for line in lines)


def extract_prompt_metadata(markdown: str) -> str | None:
    """Return the stored prompt metadata from the note frontmatter, if present."""
    import yaml

    match = FRONTMATTER_RE.match(markdown)
    if not match:
        return None
    frontmatter = yaml.safe_load(match.group("body")) or {}
    if not isinstance(frontmatter, dict) or "prompt" not in frontmatter:
        return None
    prompt = frontmatter["prompt"]
    if prompt is None:
        return None
    if isinstance(prompt, str):
        return prompt.rstrip()
    return str(prompt).rstrip()


def set_frontmatter_fields(markdown: str, fields: dict[str, str], *, prepend: bool) -> str:
    """Add or update the given YAML frontmatter keys, preserving unrelated ones.

    `prepend` controls whether the new keys go before or after what's kept, so callers can
    build up frontmatter (e.g. model/cost first, prompt last) across multiple calls.
    """
    new_lines = [
        render_prompt_metadata(value).rstrip() if key == "prompt" else f"{key}: {value}"
        for key, value in fields.items()
    ]
    match = FRONTMATTER_RE.match(markdown)
    if not match:
        body = "\n".join(new_lines)
        return f"---\n{body}\n---\n\n{markdown.lstrip()}"
    kept_lines: list[str] = []
    skipping = False
    for line in match.group("body").splitlines():
        if skipping:
            if line.startswith((" ", "\t")):
                continue
            skipping = False
        if line.split(":", 1)[0] in fields:
            skipping = True
            continue
        kept_lines.append(line)
    ordered_lines = new_lines + kept_lines if prepend else kept_lines + new_lines
    body = "\n".join(ordered_lines).strip()
    remainder = markdown[match.end() :].lstrip("\n")
    return f"---\n{body}\n---\n\n{remainder}" if remainder else f"---\n{body}\n---\n"


def set_prompt_metadata(markdown: str, prompt: str) -> str:
    """Add or update the prompt key in note frontmatter, keeping it last."""
    return set_frontmatter_fields(markdown, {"prompt": prompt}, prepend=False)


def set_model_cost_metadata(markdown: str, model: str, cost_usd: float) -> str:
    """Add or update the transcription model and dollar cost in note frontmatter, keeping them first."""
    return set_frontmatter_fields(markdown, {"model": model, "cost": f"{cost_usd:.6f}"}, prepend=True)


def extract_system_prompt(markdown: str) -> str:
    """Return the first fenced code block content, else the full Markdown body."""
    match = CODE_FENCE_RE.search(markdown)
    prompt = (match.group(1) if match else markdown).strip()
    if not prompt:
        raise ValueError("System prompt is empty.")
    return prompt


def load_system_prompt(prompt_file: Path) -> str:
    """Return the configured system prompt, falling back for the historical default path."""
    if prompt_file.is_file():
        return extract_system_prompt(prompt_file.read_text(encoding="utf-8"))
    if prompt_file == DEFAULT_PROMPT_FILE:
        typer.echo(
            f"WARNING default prompt file missing: {prompt_file}; using built-in system prompt {DEFAULT_SYSTEM_PROMPT!r}.",
            err=True,
        )
        return DEFAULT_SYSTEM_PROMPT
    raise typer.BadParameter(f"Prompt file does not exist: {prompt_file}")


def has_transcript_content(markdown: str) -> bool:
    """Return True when the document already has a non-empty transcript section."""
    match = TRANSCRIPT_SECTION_RE.search(markdown)
    return bool(match and match.group("body").strip())


def count_transcript_sections(markdown: str) -> int:
    """Return the number of transcript sections in a Markdown document."""
    return len(list(TRANSCRIPT_SECTION_RE.finditer(markdown)))


def render_new_document(title: str, transcript: str, prompt: str) -> str:
    """Render a new transcript Markdown file using the current note template."""
    cleaned = transcript.strip()
    if not cleaned:
        raise ValueError("Transcript output is empty.")
    return (
        "---\n"
        f"{render_prompt_metadata(prompt)}"
        "---\n\n"
        f"# {title}\n\n"
        "## Transcript\n\n"
        f"{cleaned}\n"
    )


def upsert_transcript_section(markdown: str, title: str, transcript: str, prompt: str | None = None) -> str:
    """Insert or replace the transcript section while preserving other sections."""
    cleaned = transcript.strip()
    if not cleaned:
        raise ValueError("Transcript output is empty.")
    if not markdown.strip():
        if prompt is None:
            raise ValueError("Prompt metadata is required for new transcript notes.")
        return render_new_document(title, cleaned, prompt=prompt)
    working_markdown = set_prompt_metadata(markdown, prompt) if prompt is not None else markdown
    if count_transcript_sections(markdown) > 1:
        raise ValueError("Document has multiple ## Transcript sections.")

    match = TRANSCRIPT_SECTION_RE.search(working_markdown)
    if not match:
        return f"{working_markdown.rstrip()}\n\n## Transcript\n\n{cleaned}\n"

    prefix = working_markdown[: match.start()].rstrip()
    suffix = working_markdown[match.end() :].lstrip("\n")
    rebuilt = "\n\n".join(part for part in (prefix, "## Transcript", cleaned) if part)
    if suffix:
        rebuilt = f"{rebuilt}\n\n{suffix.rstrip()}"
    return f"{rebuilt}\n"


def split_transcript_parts(transcript: str) -> list[str]:
    """Return transcript parts separated by the chunk delimiter."""
    cleaned = transcript.strip()
    if not cleaned:
        return []
    return [part.strip() for part in cleaned.split(TRANSCRIPT_PART_SEPARATOR)]


def patch_transcript_section(markdown: str, section_index: int, transcript: str, prompt: str | None = None) -> str:
    """Replace one transcript chunk inside an existing transcript section."""
    match = TRANSCRIPT_SECTION_RE.search(markdown)
    if not match or not match.group("body").strip():
        raise ValueError("Document has no transcript section to patch.")
    parts = split_transcript_parts(match.group("body"))
    if section_index < 1 or section_index > len(parts):
        raise ValueError(f"Document transcript has {len(parts)} section(s); cannot patch section {section_index}.")
    parts[section_index - 1] = transcript.strip()
    return upsert_transcript_section(markdown, "", TRANSCRIPT_PART_SEPARATOR.join(parts), prompt=prompt)


def find_invalid_transcript_sections(markdown: str) -> list[int]:
    """Return 1-based transcript section indices that do not look like transcript text."""
    match = TRANSCRIPT_SECTION_RE.search(markdown)
    if not match or not match.group("body").strip():
        return []
    return [
        index
        for index, part in enumerate(split_transcript_parts(match.group("body")), start=1)
        if not looks_like_transcript(part)
    ]


def count_matching_transcript_lines(transcript: str) -> int:
    """Count lines that look like transcript speaker lines."""
    return sum(1 for line in transcript.splitlines() if TRANSCRIPT_LINE_RE.match(line.strip()))


def looks_like_transcript(transcript: str, min_matching_lines: int = 5) -> bool:
    """Return True when the transcript resembles the expected speaker-line format."""
    return count_matching_transcript_lines(transcript) >= min_matching_lines


def resolve_audio_path(audio_arg: str, input_dir: Path) -> Path:
    """Resolve an audio argument to a file path.

    A path that exists (absolute, or relative to the cwd) is used directly. Otherwise the
    argument is matched case-insensitively against audio filenames in `input_dir`: an exact
    stem match wins outright, else it's matched as a substring of the stem. Since filenames
    start with `YYYY-MM-DD`, ties are broken by taking the most recent (highest-sorting) name.
    """
    given = Path(audio_arg)
    if given.exists():
        return given
    if given.is_absolute() or len(given.parts) > 1:
        raise typer.BadParameter(f"Audio file does not exist: {given}")
    query = (given.stem if given.suffix.lower() in AUDIO_SUFFIXES else str(given)).lower()
    audio_files = [
        path for path in input_dir.glob("*") if path.is_file() and path.suffix.lower() in AUDIO_SUFFIXES
    ]
    exact = [path for path in audio_files if path.stem.lower() == query]
    matches = exact or [path for path in audio_files if query in path.stem.lower()]
    if not matches:
        raise typer.BadParameter(f"No audio file matching {audio_arg!r} found in {input_dir}")
    return max(matches, key=lambda path: path.name)


def read_existing_note(note_path: Path) -> tuple[bool, str, int]:
    """Return whether a note exists, its content, and its transcript-section count."""
    if not note_path.exists():
        return False, "", 0
    try:
        markdown = note_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise RuntimeError(f"{note_path.name}: failed to read existing Markdown: {exc}") from exc
    transcript_sections = count_transcript_sections(markdown)
    if transcript_sections > 1:
        raise RuntimeError(f"{note_path.name}: document has multiple ## Transcript sections")
    return True, markdown, transcript_sections


def list_audio_files(input_dir: Path) -> list[Path]:
    """Return all supported audio files directly inside `input_dir`, sorted by name."""
    return sorted(
        path for path in input_dir.glob("*") if path.is_file() and path.suffix.lower() in AUDIO_SUFFIXES
    )


def find_notes_with_transcript_content(output_dir: Path) -> set[Path]:
    """Return transcript notes with content using one fast batch scan."""
    if not output_dir.exists():
        return set()
    result = subprocess.run(
        ["rg", "-l", "-U", "-P", TRANSCRIPT_CONTENT_RG_PATTERN, "--glob", "*.md", "--", str(output_dir)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode not in (0, 1):
        detail = result.stderr.strip() or f"rg exited {result.returncode}"
        raise RuntimeError(f"Failed to scan transcript notes: {detail}")
    return {Path(line) for line in result.stdout.splitlines()}


def emit_change_list(audio_files: list[Path], output_dir: Path) -> None:
    """Emit create/update actions as TSV for audio files without a transcript, without probing audio."""
    completed_notes = find_notes_with_transcript_content(output_dir)
    changes = 0
    for audio_path in audio_files:
        output_path = output_dir / f"{audio_path.stem}.md"
        if output_path in completed_notes:
            continue
        had_output, markdown, _ = read_existing_note(output_path)
        if has_transcript_content(markdown):
            continue
        typer.echo(f"{'update' if had_output else 'create'}\t{audio_path}\t{output_path}")
        changes += 1
    typer.echo(f"changes={changes}", err=True)


def normalize_model_id(model_id: str) -> str:
    """Normalize model identifiers so pricing ids and requested model names match."""
    return re.sub(r"-+", "-", model_id.strip().lower().replace(".", "-"))


def parse_google_pricing(payload: object, source: str) -> dict[str, dict[str, object]]:
    """Parse an llm-prices JSON payload into a normalized model-id -> price-entry map."""
    models = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(models, list):
        raise RuntimeError(f"Google pricing data from {source} is missing models.")
    pricing: dict[str, dict[str, object]] = {}
    for model_entry in models:
        if not isinstance(model_entry, dict):
            continue
        model_id = model_entry.get("id")
        history = model_entry.get("price_history")
        if not isinstance(model_id, str) or not isinstance(history, list) or not history:
            continue
        latest = history[0]
        if isinstance(latest, dict):
            pricing[normalize_model_id(model_id)] = latest
    if not pricing:
        raise RuntimeError(f"Google pricing data from {source} did not contain usable models.")
    return pricing


@lru_cache(maxsize=1)
def load_google_pricing() -> dict[str, dict[str, object]]:
    """Load Google pricing data from llm-prices, falling back to the last cached copy on
    a network failure so a flaky connection doesn't block transcription outright."""
    url = os.environ.get("TRANSCRIBE_CALLS_PRICES_URL", PRICES_URL)
    cache_path = Path(os.environ.get("TRANSCRIBE_CALLS_PRICES_CACHE", DEFAULT_PRICES_CACHE_PATH))
    try:
        with urlopen(url, timeout=30) as response:
            payload = json.load(response)
        pricing = parse_google_pricing(payload, url)
    except (OSError, URLError, json.JSONDecodeError, RuntimeError) as exc:
        if not cache_path.is_file():
            raise RuntimeError(f"Failed to load Google pricing data from {url}: {exc}") from exc
        typer.echo(
            f"WARNING failed to fetch Google pricing data from {url} ({exc}); using cached copy.",
            err=True,
        )
        return parse_google_pricing(json.loads(cache_path.read_text(encoding="utf-8")), str(cache_path))
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(payload), encoding="utf-8")
    return pricing


def select_price_entry(
    pricing: dict[str, dict[str, object]],
    requested_model: str,
    prompt_tokens: int,
    response_model: str | None = None,
) -> dict[str, object]:
    """Select the best pricing record for the requested model and token volume."""
    candidate_models = [requested_model]
    if response_model and response_model != requested_model:
        candidate_models.append(response_model)

    for model_name in candidate_models:
        normalized = normalize_model_id(model_name)
        explicit = pricing.get(normalized)
        if explicit and (normalized.endswith("-200k") or normalized.endswith("-128k")):
            return explicit
        if prompt_tokens > 200_000 and f"{normalized}-200k" in pricing:
            return pricing[f"{normalized}-200k"]
        if prompt_tokens > 128_000 and f"{normalized}-128k" in pricing:
            return pricing[f"{normalized}-128k"]
        if explicit:
            return explicit
    raise RuntimeError(f"No Google pricing entry found for model {requested_model}.")


def calculate_usage_cost(
    response: object,
    requested_model: str,
    pricing: dict[str, dict[str, object]],
) -> UsageCost:
    """Return token usage and estimated cost for one Gemini response."""
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        raise RuntimeError("Gemini response is missing usage metadata.")

    prompt_tokens = int(getattr(usage, "prompt_token_count", 0) or 0)
    cached_tokens = int(getattr(usage, "cached_content_token_count", 0) or 0)
    candidate_tokens = int(getattr(usage, "candidates_token_count", 0) or 0)
    thought_tokens = int(getattr(usage, "thoughts_token_count", 0) or 0)
    output_tokens = candidate_tokens + thought_tokens
    total_tokens = int(getattr(usage, "total_token_count", 0) or (prompt_tokens + output_tokens))

    price = select_price_entry(
        pricing,
        requested_model=requested_model,
        prompt_tokens=prompt_tokens,
        response_model=getattr(response, "model_version", None),
    )
    input_rate = float(price["input"])
    output_rate = float(price["output"])
    cached_rate_value = price.get("input_cached")
    cached_rate = float(cached_rate_value) if cached_rate_value is not None else input_rate
    uncached_prompt_tokens = max(prompt_tokens - cached_tokens, 0)
    cost_usd = (
        (uncached_prompt_tokens * input_rate)
        + (cached_tokens * cached_rate)
        + (output_tokens * output_rate)
    ) / 1_000_000

    return UsageCost(
        prompt_tokens=prompt_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        cost_usd=cost_usd,
    )


def combine_usage_costs(costs: list[UsageCost]) -> UsageCost:
    """Sum usage and cost across chunked transcription requests."""
    return UsageCost(
        prompt_tokens=sum(cost.prompt_tokens for cost in costs),
        output_tokens=sum(cost.output_tokens for cost in costs),
        total_tokens=sum(cost.total_tokens for cost in costs),
        cost_usd=sum(cost.cost_usd for cost in costs),
    )


def chunk_cache_path(
    cache_dir: Path,
    audio_path: Path,
    window: tuple[float, float],
    chunk_index: int,
    chunk_count: int,
    model: str,
    system_prompt: str,
    user_prompt: str | None,
) -> Path:
    """Return the cache path for one exact chunk transcription request."""
    stat = audio_path.stat()
    cache_key = json.dumps(
        {
            "audio": str(audio_path.resolve()),
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "window": window,
            "chunk_index": chunk_index,
            "chunk_count": chunk_count,
            "model": model,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
        },
        sort_keys=True,
    ).encode()
    return cache_dir / f"chunk-{hashlib.sha256(cache_key).hexdigest()}.json"


def cleanup_chunk_cache(
    cache_dir: Path,
    *,
    now: float | None = None,
    ttl_seconds: int = CHUNK_CACHE_TTL_SECONDS,
) -> int:
    """Remove expired chunk transcript cache files and return the count.

    Only touches `chunk-*.json` files: `cache_dir` is shared with the pricing cache
    (one folder per script, per repo convention), and that file has its own lifecycle.
    """
    if not cache_dir.is_dir():
        return 0
    cutoff = (now if now is not None else time.time()) - ttl_seconds
    expired = [path for path in cache_dir.glob("chunk-*.json") if path.stat().st_mtime < cutoff]
    for path in expired:
        path.unlink()
    return len(expired)


def read_cached_chunk(cache_path: Path) -> TranscriptionResult | None:
    """Return a cached chunk transcript with zero new usage."""
    if not cache_path.is_file():
        return None
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    return TranscriptionResult(
        transcript=payload["transcript"],
        usage=UsageCost(prompt_tokens=0, output_tokens=0, total_tokens=0, cost_usd=0.0),
    )


def write_cached_chunk(cache_path: Path, transcript: str) -> None:
    """Persist one successful chunk transcript."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = cache_path.with_suffix(".tmp")
    temp_path.write_text(json.dumps({"transcript": transcript}), encoding="utf-8")
    temp_path.replace(cache_path)


@lru_cache(maxsize=1)
def load_genai() -> Any:
    """Import Gemini only on paths that need the API client."""
    from google import genai

    return genai


def build_client() -> Any:
    """Create a Gemini client from GEMINI_API_KEY loaded via dotenv."""
    load_environment()
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set.")
    genai = load_genai()
    return genai.Client(api_key=api_key)


def probe_audio_duration(audio_path: Path) -> float:
    """Return the audio duration in seconds using ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(audio_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise RuntimeError(f"ffprobe failed for {audio_path.name}: {exc}") from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f"ffprobe exited {result.returncode}"
        raise RuntimeError(f"ffprobe failed for {audio_path.name}: {detail}")
    try:
        duration = float(result.stdout.strip())
    except ValueError as exc:
        raise RuntimeError(f"ffprobe returned invalid duration for {audio_path.name}") from exc
    if duration <= 0:
        raise RuntimeError(f"ffprobe returned non-positive duration for {audio_path.name}")
    return duration


def build_chunk_windows(
    duration_seconds: float, chunk_seconds: float, overlap_seconds: float = CHUNK_OVERLAP_SECONDS
) -> list[tuple[float, float]]:
    """Return human-friendly `(start, length)` windows with 1-second overlap between chunks."""
    if chunk_seconds <= 0:
        raise ValueError("chunk_seconds must be positive.")
    if overlap_seconds >= chunk_seconds:
        raise ValueError("overlap_seconds must be smaller than chunk_seconds.")
    if duration_seconds <= chunk_seconds:
        return [(0.0, duration_seconds)]

    chunk_count = math.ceil(duration_seconds / chunk_seconds)
    candidate_chunk_seconds = sorted(
        {
            chunk_seconds,
            *(
                minutes * 60.0
                for minutes in FRIENDLY_CHUNK_MINUTES
                if overlap_seconds < minutes * 60.0 <= chunk_seconds
            ),
        }
    )
    nominal_chunk_seconds = chunk_seconds
    for candidate in candidate_chunk_seconds:
        if math.ceil(duration_seconds / candidate) == chunk_count:
            nominal_chunk_seconds = candidate
            break

    windows: list[tuple[float, float]] = []
    start = 0.0
    while start < duration_seconds:
        end = min(start + nominal_chunk_seconds, duration_seconds)
        window_start = 0.0 if not windows else max(0.0, start - overlap_seconds)
        windows.append((window_start, end - window_start))
        start = end
    return windows


def split_audio_chunks(
    audio_path: Path,
    temp_dir: Path,
    windows: list[tuple[float, float]],
) -> list[Path]:
    """Split a long audio file into overlapping chunks with ffmpeg."""
    if len(windows) == 1:
        return [audio_path]

    chunk_paths: list[Path] = []
    for index, (start, length) in enumerate(windows, start=1):
        chunk_path = temp_dir / f"{audio_path.stem}.part{index:03d}.opus"
        try:
            result = subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-ss",
                    f"{start:.3f}",
                    "-t",
                    f"{length:.3f}",
                    "-i",
                    str(audio_path),
                    "-vn",
                    "-c:a",
                    "libopus",
                    "-b:a",
                    "64k",
                    str(chunk_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:
            raise RuntimeError(f"ffmpeg failed for {audio_path.name}: {exc}") from exc
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or f"ffmpeg exited {result.returncode}"
            raise RuntimeError(f"ffmpeg failed for {audio_path.name}: {detail}")
        chunk_paths.append(chunk_path)
    return chunk_paths


def plan_audio_chunks(audio_path: Path, chunk_minutes: float) -> tuple[float, list[tuple[float, float]]]:
    """Return the duration and chunk windows that would be used for this audio file."""
    chunk_seconds = chunk_minutes * 60.0
    if chunk_seconds <= CHUNK_OVERLAP_SECONDS:
        raise RuntimeError("--chunk must be greater than 1/60 minute because chunks overlap by 1 second.")
    duration = probe_audio_duration(audio_path)
    try:
        windows = build_chunk_windows(
            duration,
            chunk_seconds,
            overlap_seconds=CHUNK_OVERLAP_SECONDS,
        )
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    return duration, windows


def extract_speaker_labels(transcript: str) -> list[str]:
    """Return speaker labels in first-seen order from transcript lines."""
    speakers: list[str] = []
    seen: set[str] = set()
    for line in transcript.splitlines():
        match = SPEAKER_LINE_RE.match(line.strip())
        if not match:
            continue
        speaker = match.group("speaker").strip()
        if speaker and speaker not in seen:
            speakers.append(speaker)
            seen.add(speaker)
    return speakers


def transcript_tail(transcript: str) -> str:
    """Return a bounded recent transcript excerpt for chunk-to-chunk continuity."""
    lines = [line.rstrip() for line in transcript.splitlines() if line.strip()]
    tail = "\n".join(lines[-CHUNK_CONTEXT_MAX_LINES:])
    if len(tail) <= CHUNK_CONTEXT_MAX_CHARS:
        return tail
    return tail[-CHUNK_CONTEXT_MAX_CHARS:].lstrip()


def build_prior_chunk_context(previous_transcripts: list[str]) -> str | None:
    """Return compact context from prior chunks for speaker and topic continuity."""
    if not previous_transcripts:
        return None
    speakers = extract_speaker_labels("\n".join(previous_transcripts))
    speaker_context = ", ".join(speakers) if speakers else "unknown"
    recent_context = transcript_tail(previous_transcripts[-1])
    if not recent_context:
        return None
    return (
        "Context from earlier chunks, for speaker-label continuity and ambiguity resolution only.\n"
        f"Known speaker labels so far: {speaker_context}\n\n"
        "Recent transcript excerpt from the immediately preceding chunk:\n"
        f"{recent_context}\n\n"
        "Use these labels and topics when they match the current audio. "
        "Do not repeat or summarize this context; transcribe only the current audio chunk."
    )


def build_chunk_user_prompt(
    user_prompt: str | None,
    chunk_index: int,
    chunk_count: int,
    prior_chunk_context: str | None = None,
) -> str:
    """Add chunk context so Gemini knows this audio is only one part of the call."""
    chunk_prompt = (
        f"This audio is part {chunk_index}/{chunk_count} of a longer recording. "
        "Transcribe this part faithfully; the final transcript will concatenate all parts in order."
    )
    prompt_parts = [part for part in (user_prompt, prior_chunk_context, chunk_prompt) if part]
    return "\n\n".join(prompt_parts)


def emit_remaining_warnings(
    audio_path: Path, warnings: tuple[InvalidTranscriptWarning, ...]
) -> None:
    """Log transcript sections that still look invalid after an automatic retry."""
    for warning in warnings:
        typer.echo(
            f"WARNING {audio_path.name}: section {warning.section_index}/{warning.section_count} "
            f"still does not look like a transcript after retry ({warning.matching_lines} matching "
            "lines). Run with --patch to try again.",
            err=True,
        )


def transcribe_single_audio(
    audio_path: Path,
    system_prompt: str,
    user_prompt: str | None,
    model: str,
    client: Any,
    pricing: dict[str, dict[str, object]],
) -> TranscriptionResult:
    """Upload one audio file to Gemini and return the transcription text."""
    genai = load_genai()
    try:
        uploaded_file = client.files.upload(file=audio_path)
        contents: list[object] = [uploaded_file]
        if user_prompt:
            contents = [user_prompt, uploaded_file]
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=genai.types.GenerateContentConfig(system_instruction=system_prompt),
        )
    except genai.errors.APIError as exc:
        raise RuntimeError(str(exc)) from exc
    usage = calculate_usage_cost(response, requested_model=model, pricing=pricing)
    transcript = (response.text or "").strip()
    if not transcript:
        raise RuntimeError("Gemini returned empty output.")
    return TranscriptionResult(transcript=transcript, usage=usage)


def transcribe_audio(
    audio_path: Path,
    system_prompt: str,
    user_prompt: str | None,
    model: str,
    client: Any,
    pricing: dict[str, dict[str, object]],
    chunk_minutes: float,
    patch_section: int | None = None,
    windows: list[tuple[float, float]] | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
    cache_dir: Path | None = None,
) -> TranscriptionResult:
    """Transcribe audio directly or through chunked ffmpeg splits."""
    if windows is None:
        _, windows = plan_audio_chunks(audio_path, chunk_minutes=chunk_minutes)
    if len(windows) == 1:
        if patch_section not in (None, 1):
            raise RuntimeError(f"{audio_path.name} has only 1 transcript section; cannot patch section {patch_section}.")
        if progress_callback is not None:
            progress_callback(1, 1)
        result = transcribe_single_audio(
            audio_path,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=model,
            client=client,
            pricing=pricing,
        )
        warnings = ()
        if not looks_like_transcript(result.transcript):
            warnings = (
                InvalidTranscriptWarning(
                    section_index=1,
                    section_count=1,
                    matching_lines=count_matching_transcript_lines(result.transcript),
                ),
            )
        return TranscriptionResult(transcript=result.transcript, usage=result.usage, warnings=warnings)

    with tempfile.TemporaryDirectory(prefix=f"{audio_path.stem}-chunks-") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        chunk_paths = split_audio_chunks(
            audio_path,
            temp_dir=temp_dir,
            windows=windows,
        )
        chunk_count = len(chunk_paths)
        if patch_section is not None and patch_section > chunk_count:
            raise RuntimeError(
                f"{audio_path.name} has only {chunk_count} transcript section(s); cannot patch section {patch_section}."
            )
        warnings: list[InvalidTranscriptWarning] = []
        transcripts: list[TranscriptionResult] = []
        target_chunks = (
            [(patch_section, chunk_paths[patch_section - 1])]
            if patch_section is not None
            else list(enumerate(chunk_paths, start=1))
        )
        for index, chunk_path in target_chunks:
            if progress_callback is not None:
                progress_callback(index, chunk_count)
            chunk_user_prompt = build_chunk_user_prompt(
                user_prompt,
                chunk_index=index,
                chunk_count=chunk_count,
                prior_chunk_context=build_prior_chunk_context(
                    [previous.transcript for previous in transcripts]
                ),
            )
            cache_path = (
                chunk_cache_path(
                    cache_dir,
                    audio_path,
                    windows[index - 1],
                    chunk_index=index,
                    chunk_count=chunk_count,
                    model=model,
                    system_prompt=system_prompt,
                    user_prompt=chunk_user_prompt,
                )
                if cache_dir is not None and patch_section is None
                else None
            )
            result = read_cached_chunk(cache_path) if cache_path is not None else None
            if result is None:
                result = transcribe_single_audio(
                    chunk_path,
                    system_prompt=system_prompt,
                    user_prompt=chunk_user_prompt,
                    model=model,
                    client=client,
                    pricing=pricing,
                )
                if cache_path is not None:
                    write_cached_chunk(cache_path, result.transcript)
            if not looks_like_transcript(result.transcript):
                warnings.append(
                    InvalidTranscriptWarning(
                        section_index=index,
                        section_count=chunk_count,
                        matching_lines=count_matching_transcript_lines(result.transcript),
                    )
                )
            transcripts.append(result)
    return TranscriptionResult(
        transcript=TRANSCRIPT_PART_SEPARATOR.join(result.transcript.strip() for result in transcripts),
        usage=combine_usage_costs([result.usage for result in transcripts]),
        warnings=tuple(warnings),
    )


@app.command(context_settings={"allow_extra_args": False, "ignore_unknown_options": False})
def main(
    audio: str | None = typer.Argument(
        None,
        help=(
            f"Audio file path, or a case-insensitive substring of a filename in "
            f"{DEFAULT_INPUT_DIR} (most recent match wins). Omit with --list-changes."
        ),
    ),
    user_prompt: str | None = typer.Option(
        None, "--prompt", help="Additional user prompt sent alongside the audio attachment."
    ),
    force: bool = typer.Option(
        False, "--force", help="Re-transcribe even if the note already has a transcript."
    ),
    patch: bool = typer.Option(
        False,
        "--patch",
        help="Detect invalid transcript sections in the existing note and re-transcribe just those.",
    ),
    model: str = typer.Option(
        DEFAULT_MODEL, "--model", envvar="TRANSCRIBE_CALLS_MODEL", help="Gemini model to use for transcription."
    ),
    chunk_minutes: float = typer.Option(
        DEFAULT_CHUNK_MINUTES,
        "--chunk",
        min=0.01,
        help="Chunk size in minutes for splitting long audio before transcription.",
    ),
    out_dir: Path = typer.Option(
        DEFAULT_OUTPUT_DIR, "--out", help="Folder for the transcript Markdown file."
    ),
    system_prompt_file: Path = typer.Option(
        DEFAULT_PROMPT_FILE,
        "--system-prompt",
        help="Markdown file containing the system prompt or first fenced prompt.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would happen and the chunk plan, without calling Gemini or writing files.",
    ),
    list_changes: bool = typer.Option(
        False,
        "--list-changes",
        help=(
            f"List create/update actions as TSV for every audio file in {DEFAULT_INPUT_DIR} "
            "without a transcript yet, without probing audio or writing files. Takes no AUDIO argument."
        ),
    ),
) -> None:
    """Transcribe one call recording into a Markdown note."""
    if out_dir.exists() and not out_dir.is_dir():
        raise typer.BadParameter(f"Output path is not a directory: {out_dir}")
    if list_changes:
        if audio is not None:
            raise typer.BadParameter("--list-changes takes no AUDIO argument.")
        emit_change_list(list_audio_files(DEFAULT_INPUT_DIR), out_dir)
        return
    if audio is None:
        raise typer.BadParameter("Missing argument 'AUDIO'.")
    if system_prompt_file.suffix.lower() != ".md":
        raise typer.BadParameter(f"Prompt file must be Markdown: {system_prompt_file}")
    if patch and force:
        raise typer.BadParameter("--patch cannot be used with --force.")
    if patch and dry_run:
        raise typer.BadParameter("--patch cannot be used with --dry-run.")

    audio_path = resolve_audio_path(audio, DEFAULT_INPUT_DIR)
    cleaned_user_prompt = user_prompt.strip() if user_prompt and user_prompt.strip() else None
    output_path = out_dir / f"{audio_path.stem}.md"

    try:
        had_output, existing_markdown, _ = read_existing_note(output_path)
    except RuntimeError as exc:
        typer.echo(f"ERROR {exc}", err=True)
        raise typer.Exit(1) from exc

    stored_prompt = extract_prompt_metadata(existing_markdown) if had_output else None
    has_transcript = has_transcript_content(existing_markdown)

    if patch:
        if not had_output or not has_transcript:
            typer.echo(f"ERROR {output_path.name}: no transcript section to patch", err=True)
            raise typer.Exit(1)
        target_sections = find_invalid_transcript_sections(existing_markdown)
        if not target_sections:
            typer.echo(f"No invalid transcript sections found in {output_path.name}")
            return
    elif has_transcript and not force:
        if cleaned_user_prompt is None or stored_prompt == cleaned_user_prompt:
            typer.echo(f"Already transcribed: {output_path.name} (use --force to re-transcribe)")
            return
        output_path.write_text(set_prompt_metadata(existing_markdown, cleaned_user_prompt), encoding="utf-8")
        typer.echo(f"updated prompt metadata: {output_path.name}")
        return

    if dry_run:
        try:
            duration_seconds, windows = plan_audio_chunks(audio_path, chunk_minutes=chunk_minutes)
        except RuntimeError as exc:
            typer.echo(f"ERROR {audio_path.name}: {exc}", err=True)
            raise typer.Exit(1) from exc
        action = "force re-transcribe" if force and has_transcript else ("update" if had_output else "create")
        typer.echo(
            f"dry-run {action} {audio_path.name} -> {output_path.name} "
            f"duration={duration_seconds:.1f}s chunks={len(windows)}"
        )
        return

    chunk_cache_dir = Path(os.environ.get("TRANSCRIBE_CALLS_CACHE_DIR", DEFAULT_CACHE_DIR))
    cleanup_chunk_cache(chunk_cache_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    prompts = resolve_prompts(load_system_prompt(system_prompt_file), stored_prompt, cleaned_user_prompt)

    try:
        client = build_client()
        pricing = load_google_pricing()
    except RuntimeError as exc:
        typer.echo(f"ERROR {exc}", err=True)
        raise typer.Exit(1) from exc

    try:
        _, windows = plan_audio_chunks(audio_path, chunk_minutes=chunk_minutes)
    except RuntimeError as exc:
        typer.echo(f"ERROR {audio_path.name}: {exc}", err=True)
        raise typer.Exit(1) from exc

    def log_progress(current_chunk: int, total_chunks: int) -> None:
        if total_chunks > 1:
            typer.echo(f"[{current_chunk}/{total_chunks}] transcribing {audio_path.name}")

    total_cost_usd = 0.0

    def log_cost(usage: UsageCost) -> None:
        nonlocal total_cost_usd
        total_cost_usd += usage.cost_usd
        typer.echo(f"tokens={usage.total_tokens} cost=${usage.cost_usd:.6f} total_cost=${total_cost_usd:.6f}")

    def retry_section(index: int) -> TranscriptionResult:
        """Re-transcribe one chunk, bypassing the cache so a failed attempt isn't replayed."""
        retry_result = transcribe_audio(
            audio_path,
            system_prompt=prompts.system_prompt,
            user_prompt=prompts.user_prompt,
            model=model,
            client=client,
            pricing=pricing,
            chunk_minutes=chunk_minutes,
            patch_section=index,
            windows=windows,
            progress_callback=log_progress,
        )
        log_cost(retry_result.usage)
        return retry_result

    try:
        if patch:
            updated_markdown = existing_markdown
            for section in target_sections:
                section_result = retry_section(section)
                emit_remaining_warnings(audio_path, section_result.warnings)
                updated_markdown = patch_transcript_section(
                    updated_markdown, section, section_result.transcript, prompt=prompts.note_prompt
                )
            output_path.write_text(
                set_model_cost_metadata(updated_markdown, model, total_cost_usd), encoding="utf-8"
            )
            typer.echo(f"patched section(s) {','.join(str(s) for s in target_sections)}: {output_path.name}")
            return

        result = transcribe_audio(
            audio_path,
            system_prompt=prompts.system_prompt,
            user_prompt=prompts.user_prompt,
            model=model,
            client=client,
            pricing=pricing,
            chunk_minutes=chunk_minutes,
            windows=windows,
            progress_callback=log_progress,
            cache_dir=chunk_cache_dir,
        )
        log_cost(result.usage)

        if result.warnings:
            parts = split_transcript_parts(result.transcript)
            remaining_warnings: list[InvalidTranscriptWarning] = []
            for warning in result.warnings:
                retry_result = retry_section(warning.section_index)
                if retry_result.warnings:
                    remaining_warnings.extend(retry_result.warnings)
                else:
                    parts[warning.section_index - 1] = retry_result.transcript
            result = TranscriptionResult(
                transcript=TRANSCRIPT_PART_SEPARATOR.join(parts),
                usage=result.usage,
                warnings=tuple(remaining_warnings),
            )
            emit_remaining_warnings(audio_path, result.warnings)
    except RuntimeError as exc:
        typer.echo(f"ERROR {audio_path.name}: {exc}", err=True)
        raise typer.Exit(1) from exc

    try:
        updated_markdown = upsert_transcript_section(
            existing_markdown, audio_path.stem, result.transcript, prompt=prompts.note_prompt
        )
        output_path.write_text(
            set_model_cost_metadata(updated_markdown, model, total_cost_usd), encoding="utf-8"
        )
    except (OSError, ValueError) as exc:
        typer.echo(f"ERROR {output_path.name}: {exc}", err=True)
        raise typer.Exit(1) from exc

    typer.echo(f"{'updated' if had_output else 'created'} {output_path.name}")


if __name__ == "__main__":
    app()
