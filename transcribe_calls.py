#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["google-genai>=1.67.0", "python-dotenv>=1.0.1", "typer>=0.12"]
# ///
"""Transcribe audio files into Markdown call notes."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
import json
import math
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Iterable
from urllib.error import URLError
from urllib.request import urlopen

from dotenv import load_dotenv
from google import genai
import typer

DEFAULT_INPUT_DIR = Path("/home/sanand/Documents/calls")
DEFAULT_OUTPUT_DIR = Path("/home/sanand/Dropbox/notes/transcripts")
DEFAULT_PROMPT_FILE = Path("/home/sanand/code/blog/pages/prompts/transcribe-call-recording.md")
DEFAULT_MODEL = "gemini-3.1-pro-preview"
DEFAULT_CHUNK_MINUTES = 30.0
CHUNK_OVERLAP_SECONDS = 1.0
FRIENDLY_CHUNK_MINUTES = (30.0, 25.0, 20.0, 15.0)
PRICES_URL = "https://raw.githubusercontent.com/simonw/llm-prices/refs/heads/main/data/google.json"
AUDIO_SUFFIXES = {".aac", ".flac", ".m4a", ".mp3", ".oga", ".ogg", ".opus", ".wav", ".webm"}
CODE_FENCE_RE = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)
TRAILING_SINGLE_DIGIT_RE = re.compile(r"^(?P<base>.+?) (?P<digit>\d)$")
TRANSCRIPT_SECTION_RE = re.compile(
    r"(?ms)^##\s+Transcript\s*$\n?(?P<body>.*?)(?=^##\s+|\Z)"
)

app = typer.Typer(add_completion=False, no_args_is_help=False, help=__doc__)
load_dotenv(dotenv_path=Path.cwd() / ".env")


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


def extract_system_prompt(markdown: str) -> str:
    """Return the first fenced code block content, else the full Markdown body."""
    match = CODE_FENCE_RE.search(markdown)
    prompt = (match.group(1) if match else markdown).strip()
    if not prompt:
        raise ValueError("System prompt is empty.")
    return prompt


def has_transcript_content(markdown: str) -> bool:
    """Return True when the document already has a non-empty transcript section."""
    match = TRANSCRIPT_SECTION_RE.search(markdown)
    return bool(match and match.group("body").strip())


def count_transcript_sections(markdown: str) -> int:
    """Return the number of transcript sections in a Markdown document."""
    return len(list(TRANSCRIPT_SECTION_RE.finditer(markdown)))


def render_new_document(title: str, transcript: str, user_prompt: str | None = None) -> str:
    """Render a new transcript Markdown file using the current note template."""
    cleaned = transcript.strip()
    if not cleaned:
        raise ValueError("Transcript output is empty.")
    prompt_line = f"prompt: {json.dumps(user_prompt)}\n" if user_prompt else ""
    return (
        "---\n"
        "tags:\n"
        "goal:\n"
        "kind candor:\n"
        "effectiveness:\n"
        f"{prompt_line}"
        "---\n\n"
        f"# {title}\n\n"
        "## Transcript\n\n"
        f"{cleaned}\n"
    )


def upsert_transcript_section(
    markdown: str, title: str, transcript: str, user_prompt: str | None = None
) -> str:
    """Insert or replace the transcript section while preserving other sections."""
    cleaned = transcript.strip()
    if not cleaned:
        raise ValueError("Transcript output is empty.")
    if not markdown.strip():
        return render_new_document(title, cleaned, user_prompt=user_prompt)
    if count_transcript_sections(markdown) > 1:
        raise ValueError("Document has multiple ## Transcript sections.")

    match = TRANSCRIPT_SECTION_RE.search(markdown)
    if not match:
        return f"{markdown.rstrip()}\n\n## Transcript\n\n{cleaned}\n"

    prefix = markdown[: match.start()].rstrip()
    suffix = markdown[match.end() :].lstrip("\n")
    rebuilt = "\n\n".join(part for part in (prefix, "## Transcript", cleaned) if part)
    if suffix:
        rebuilt = f"{rebuilt}\n\n{suffix.rstrip()}"
    return f"{rebuilt}\n"


def iter_audio_files(input_dir: Path, pattern: str) -> Iterable[Path]:
    """Yield supported audio files matching the glob pattern in name order."""
    for path in sorted(input_dir.glob(pattern)):
        if path.is_file() and path.suffix.lower() in AUDIO_SUFFIXES:
            yield path


def find_colliding_stems(audio_files: list[Path]) -> list[str]:
    """Return sorted audio stems that would map to the same Markdown filename."""
    counts = Counter(path.stem for path in audio_files)
    return sorted(stem for stem, count in counts.items() if count > 1)


def find_base_transcript_path(output_dir: Path, audio_stem: str) -> Path | None:
    """Return the alternate base transcript path for stems ending in ` space + digit`."""
    match = TRAILING_SINGLE_DIGIT_RE.fullmatch(audio_stem)
    if not match:
        return None
    return output_dir / f"{match.group('base')}.md"


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


def normalize_model_id(model_id: str) -> str:
    """Normalize model identifiers so pricing ids and requested model names match."""
    return re.sub(r"-+", "-", model_id.strip().lower().replace(".", "-"))


@lru_cache(maxsize=1)
def load_google_pricing() -> dict[str, dict[str, object]]:
    """Load Google pricing data from llm-prices."""
    url = os.environ.get("TRANSCRIBE_CALLS_PRICES_URL", PRICES_URL)
    try:
        with urlopen(url, timeout=30) as response:
            payload = json.load(response)
    except (OSError, URLError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Failed to load Google pricing data from {url}: {exc}") from exc
    models = payload.get("models")
    if not isinstance(models, list):
        raise RuntimeError(f"Google pricing data from {url} is missing models.")
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
        raise RuntimeError(f"Google pricing data from {url} did not contain usable models.")
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


def build_client() -> genai.Client:
    """Create a Gemini client from GEMINI_API_KEY loaded via dotenv."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set.")
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
        chunk_path = temp_dir / f"{audio_path.stem}.part{index:03d}{audio_path.suffix}"
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
                    "-c",
                    "copy",
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


def build_chunk_user_prompt(user_prompt: str | None, chunk_index: int, chunk_count: int) -> str:
    """Add chunk context so Gemini knows this audio is only one part of the call."""
    chunk_prompt = (
        f"This audio is part {chunk_index}/{chunk_count} of a longer recording. "
        "Transcribe this part faithfully; the final transcript will concatenate all parts in order."
    )
    if not user_prompt:
        return chunk_prompt
    return f"{user_prompt}\n\n{chunk_prompt}"


def transcribe_single_audio(
    audio_path: Path,
    system_prompt: str,
    user_prompt: str | None,
    model: str,
    client: genai.Client,
    pricing: dict[str, dict[str, object]],
) -> TranscriptionResult:
    """Upload one audio file to Gemini and return the transcription text."""
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
    client: genai.Client,
    pricing: dict[str, dict[str, object]],
    chunk_minutes: float,
) -> TranscriptionResult:
    """Transcribe audio directly or through chunked ffmpeg splits."""
    _, windows = plan_audio_chunks(audio_path, chunk_minutes=chunk_minutes)
    if len(windows) == 1:
        return transcribe_single_audio(
            audio_path,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=model,
            client=client,
            pricing=pricing,
        )

    with tempfile.TemporaryDirectory(prefix=f"{audio_path.stem}-chunks-") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        chunk_paths = split_audio_chunks(
            audio_path,
            temp_dir=temp_dir,
            windows=windows,
        )
        transcripts = [
            transcribe_single_audio(
                chunk_path,
                system_prompt=system_prompt,
                user_prompt=build_chunk_user_prompt(user_prompt, chunk_index=index, chunk_count=len(chunk_paths)),
                model=model,
                client=client,
                pricing=pricing,
            )
            for index, chunk_path in enumerate(chunk_paths, start=1)
        ]
    return TranscriptionResult(
        transcript="\n\n---\n\n".join(result.transcript.strip() for result in transcripts),
        usage=combine_usage_costs([result.usage for result in transcripts]),
    )


@app.command(context_settings={"allow_extra_args": False, "ignore_unknown_options": False})
def main(
    input_dir: Path = typer.Argument(DEFAULT_INPUT_DIR, help="Folder containing audio files."),
    output_dir: Path = typer.Argument(DEFAULT_OUTPUT_DIR, help="Folder for transcript Markdown files."),
    prompt_file: Path = typer.Argument(
        DEFAULT_PROMPT_FILE,
        help="Markdown file containing the system prompt or first fenced prompt.",
    ),
    model: str = typer.Option(
        DEFAULT_MODEL,
        "--model",
        envvar="TRANSCRIBE_CALLS_MODEL",
        help="Gemini model to use for transcription.",
    ),
    user_prompt: str | None = typer.Option(
        None,
        "--prompt",
        help="Additional user prompt sent alongside the audio attachment.",
    ),
    chunk_minutes: float = typer.Option(
        DEFAULT_CHUNK_MINUTES,
        "--chunk",
        min=0.01,
        help="Chunk size in minutes for splitting long audio before transcription.",
    ),
    glob_pattern: str = typer.Option(
        "*",
        "--glob",
        help="Glob pattern, relative to the input folder, for filtering audio files.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="List work, duration, and chunk count without calling Gemini or ffmpeg, and without writing files.",
    ),
) -> None:
    """Transcribe every missing call recording in the input folder."""
    if not input_dir.is_dir():
        raise typer.BadParameter(f"Input folder does not exist: {input_dir}")
    if prompt_file.suffix.lower() != ".md":
        raise typer.BadParameter(f"Prompt file must be Markdown: {prompt_file}")
    if not prompt_file.is_file():
        raise typer.BadParameter(f"Prompt file does not exist: {prompt_file}")
    if output_dir.exists() and not output_dir.is_dir():
        raise typer.BadParameter(f"Output path is not a directory: {output_dir}")

    system_prompt = extract_system_prompt(prompt_file.read_text(encoding="utf-8"))
    cleaned_user_prompt = user_prompt.strip() if user_prompt and user_prompt.strip() else None
    audio_files = list(iter_audio_files(input_dir, pattern=glob_pattern))
    if not audio_files:
        typer.echo(f"No audio files found in {input_dir} matching {glob_pattern!r}")
        raise typer.Exit(0)
    if collisions := find_colliding_stems(audio_files):
        joined = ", ".join(collisions)
        raise typer.BadParameter(
            f"Duplicate audio basenames would collide in output: {joined}"
        )

    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)

    created = 0
    updated = 0
    skipped = 0
    failures: list[str] = []
    total = len(audio_files)
    client: genai.Client | None = None
    pricing: dict[str, dict[str, object]] | None = None
    total_cost_usd = 0.0

    for index, audio_path in enumerate(audio_files, start=1):
        output_path = output_dir / f"{audio_path.stem}.md"
        try:
            had_output, existing_markdown, transcript_sections = read_existing_note(output_path)
        except RuntimeError as exc:
            failures.append(str(exc))
            typer.echo(f"ERROR {exc}", err=True)
            continue

        if has_transcript_content(existing_markdown):
            skipped += 1
            continue

        base_output_path = find_base_transcript_path(output_dir, audio_path.stem)
        if base_output_path is not None:
            try:
                has_base_output, base_markdown, _ = read_existing_note(base_output_path)
            except RuntimeError as exc:
                failures.append(str(exc))
                typer.echo(f"ERROR {exc}", err=True)
                continue
            if has_base_output and has_transcript_content(base_markdown):
                skipped += 1
                continue

        action = "update" if had_output else "create"
        note = " (existing file missing transcript section)" if had_output and transcript_sections == 0 else ""
        if dry_run:
            try:
                duration_seconds, windows = plan_audio_chunks(audio_path, chunk_minutes=chunk_minutes)
            except RuntimeError as exc:
                failures.append(f"{audio_path.name}: {exc}")
                typer.echo(f"ERROR {audio_path.name}: {exc}", err=True)
                continue
            stats = f" duration={duration_seconds:.1f}s chunks={len(windows)}"
            typer.echo(
                f"[{index}/{total}] dry-run {action} {audio_path.name} -> {output_path.name}{note}{stats}"
            )
            continue

        if client is None:
            try:
                client = build_client()
                pricing = load_google_pricing()
            except RuntimeError as exc:
                typer.echo(f"ERROR {exc}", err=True)
                raise typer.Exit(1) from exc

        typer.echo(f"[{index}/{total}] {action} {audio_path.name} -> {output_path.name}{note}")
        try:
            result = transcribe_audio(
                audio_path,
                system_prompt=system_prompt,
                user_prompt=cleaned_user_prompt,
                model=model,
                client=client,
                pricing=pricing or {},
                chunk_minutes=chunk_minutes,
            )
        except RuntimeError as exc:
            failures.append(f"{audio_path.name}: {exc}")
            typer.echo(f"ERROR {audio_path.name}: {exc}", err=True)
            continue

        total_cost_usd += result.usage.cost_usd
        typer.echo(
            f"tokens={result.usage.total_tokens} cost=${result.usage.cost_usd:.6f} total_cost=${total_cost_usd:.6f}"
        )
        try:
            output_path.write_text(
                upsert_transcript_section(
                    existing_markdown,
                    audio_path.stem,
                    result.transcript,
                    user_prompt=cleaned_user_prompt,
                ),
                encoding="utf-8",
            )
        except (OSError, ValueError) as exc:
            failures.append(f"{output_path.name}: {exc}")
            typer.echo(f"ERROR {output_path.name}: {exc}", err=True)
            continue
        if had_output:
            updated += 1
        else:
            created += 1

    typer.echo(f"created={created} updated={updated} skipped={skipped} errors={len(failures)}")
    if failures:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
