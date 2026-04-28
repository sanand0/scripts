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
import shlex
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Iterable
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
TRANSCRIPT_PART_SEPARATOR = "\n\n---\n\n"
TRANSCRIPT_LINE_RE = re.compile(
    r"^\*\*[^*\n]+(?:\*\*:?|:\*\*)(?: \[\d{2}:\d{2}(?::\d{2})?\])? .+"
)
FRONTMATTER_RE = re.compile(r"\A---\n(?P<body>.*?\n?)---\n?", re.DOTALL)
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
    warnings: tuple["InvalidTranscriptWarning", ...] = ()


@dataclass(frozen=True)
class InvalidTranscriptWarning:
    section_index: int
    section_count: int
    matching_lines: int


def build_note_prompt(system_prompt: str, user_prompt: str | None = None) -> str:
    """Return the stored prompt context for a transcript note."""
    if user_prompt:
        return user_prompt.strip()
    return system_prompt.strip()


def resolve_patch_prompts(
    system_prompt: str, stored_prompt: str | None, user_prompt: str | None
) -> tuple[str, str | None]:
    """Return `(system_prompt, user_prompt)` to use for a patch operation."""
    if user_prompt is not None:
        return system_prompt, user_prompt
    if not stored_prompt:
        return system_prompt, None
    cleaned_stored_prompt = stored_prompt.strip()
    cleaned_system_prompt = system_prompt.strip()
    if not cleaned_stored_prompt or cleaned_stored_prompt == cleaned_system_prompt:
        return system_prompt, None
    return system_prompt, cleaned_stored_prompt


def render_prompt_metadata(prompt: str) -> str:
    """Render prompt metadata as a YAML block scalar."""
    lines = prompt.strip().splitlines() or [""]
    return "prompt: |-\n" + "".join(f"  {line}\n" for line in lines)


def strip_prompt_metadata(frontmatter_body: str) -> str:
    """Remove any existing prompt metadata from YAML frontmatter text."""
    cleaned_lines: list[str] = []
    skipping_prompt = False
    for line in frontmatter_body.splitlines():
        if skipping_prompt:
            if line.startswith((" ", "\t")):
                continue
            skipping_prompt = False
        if line.startswith("prompt:"):
            skipping_prompt = True
            continue
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines).strip()


def extract_prompt_metadata(markdown: str) -> str | None:
    """Return the stored prompt metadata from the note frontmatter, if present."""
    match = FRONTMATTER_RE.match(markdown)
    if not match:
        return None
    lines = match.group("body").splitlines()
    for index, line in enumerate(lines):
        if not line.startswith("prompt:"):
            continue
        value = line[len("prompt:") :].strip()
        if not value.startswith(("|", ">")):
            return None
        block: list[str] = []
        for continuation in lines[index + 1 :]:
            if continuation.startswith((" ", "\t")):
                block.append(continuation[2:] if continuation.startswith("  ") else continuation.lstrip())
            else:
                break
        return "\n".join(block).rstrip()
    return None


def set_prompt_metadata(markdown: str, prompt: str) -> str:
    """Add or update the prompt key in note frontmatter."""
    prompt_block = render_prompt_metadata(prompt).rstrip()
    match = FRONTMATTER_RE.match(markdown)
    if not match:
        return f"---\n{prompt_block}\n---\n\n{markdown.lstrip()}"
    body = strip_prompt_metadata(match.group("body"))
    updated_body = f"{body}\n{prompt_block}" if body else prompt_block
    remainder = markdown[match.end() :].lstrip("\n")
    return f"---\n{updated_body}\n---\n\n{remainder}" if remainder else f"---\n{updated_body}\n---\n"


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


def render_new_document(title: str, transcript: str, prompt: str) -> str:
    """Render a new transcript Markdown file using the current note template."""
    cleaned = transcript.strip()
    if not cleaned:
        raise ValueError("Transcript output is empty.")
    return (
        "---\n"
        "tags:\n"
        "goal:\n"
        "kind candor:\n"
        "effectiveness:\n"
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


def build_chunk_user_prompt(user_prompt: str | None, chunk_index: int, chunk_count: int) -> str:
    """Add chunk context so Gemini knows this audio is only one part of the call."""
    chunk_prompt = (
        f"This audio is part {chunk_index}/{chunk_count} of a longer recording. "
        "Transcribe this part faithfully; the final transcript will concatenate all parts in order."
    )
    if not user_prompt:
        return chunk_prompt
    return f"{user_prompt}\n\n{chunk_prompt}"


def build_patch_command(
    *,
    input_dir: Path,
    output_dir: Path,
    prompt_file: Path,
    audio_path: Path,
    model: str,
    user_prompt: str | None,
    chunk_minutes: float,
    patch_section: int,
) -> str:
    """Build a repair command that retranscribes one chunk and patches its transcript section."""
    relative_audio_path = audio_path.relative_to(input_dir).as_posix()
    args = [
        "uv",
        "run",
        str(Path(__file__).resolve()),
        str(input_dir),
        str(output_dir),
        str(prompt_file),
        "--glob",
        relative_audio_path,
        "--patch-section",
        str(patch_section),
        "--chunk",
        str(chunk_minutes),
        "--model",
        model,
    ]
    if user_prompt:
        args.extend(["--prompt", user_prompt])
    return " ".join(shlex.quote(arg) for arg in args)


def emit_invalid_transcript_warnings(
    *,
    audio_path: Path,
    output_path: Path,
    warnings: tuple[InvalidTranscriptWarning, ...],
    input_dir: Path,
    output_dir: Path,
    prompt_file: Path,
    model: str,
    user_prompt: str | None,
    chunk_minutes: float,
) -> None:
    """Log invalid transcript warnings together with a repair command."""
    for warning in warnings:
        typer.echo(
            f"WARNING {audio_path.name}: section {warning.section_index}/{warning.section_count} "
            f"matched only {warning.matching_lines} transcript-format lines; response may be invalid.",
            err=True,
        )
        typer.echo(
            f"Patch command for {output_path.name} section {warning.section_index}: "
            f"{build_patch_command(
                input_dir=input_dir,
                output_dir=output_dir,
                prompt_file=prompt_file,
                audio_path=audio_path,
                model=model,
                user_prompt=user_prompt,
                chunk_minutes=chunk_minutes,
                patch_section=warning.section_index,
            )}",
            err=True,
        )


def emit_transcription_progress(
    *,
    current: int,
    total: int,
    action: str,
    audio_path: Path,
    output_path: Path,
    note: str = "",
) -> None:
    """Log progress for a transcription step."""
    typer.echo(f"[{current}/{total}] {action} {audio_path.name} -> {output_path.name}{note}")


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
    patch_section: int | None = None,
    windows: list[tuple[float, float]] | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
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
            result = transcribe_single_audio(
                chunk_path,
                system_prompt=system_prompt,
                user_prompt=build_chunk_user_prompt(user_prompt, chunk_index=index, chunk_count=chunk_count),
                model=model,
                client=client,
                pricing=pricing,
            )
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
    patch_invalid_sections: bool = typer.Option(
        False,
        "--patch-invalid-sections",
        help="Detect invalid transcript sections in the existing note and patch all of them.",
    ),
    patch_section: int | None = typer.Option(
        None,
        "--patch-section",
        min=1,
        help="Re-transcribe one chunk and replace that transcript section in the existing note.",
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
    if patch_invalid_sections and patch_section is not None:
        raise typer.BadParameter("--patch-invalid-sections cannot be used with --patch-section.")
    if (patch_section is not None or patch_invalid_sections) and dry_run:
        raise typer.BadParameter("Patch options cannot be used with --dry-run.")

    system_prompt = extract_system_prompt(prompt_file.read_text(encoding="utf-8"))
    cleaned_user_prompt = user_prompt.strip() if user_prompt and user_prompt.strip() else None
    audio_files = list(iter_audio_files(input_dir, pattern=glob_pattern))
    if not audio_files:
        typer.echo(f"No audio files found in {input_dir} matching {glob_pattern!r}")
        raise typer.Exit(0)
    if (patch_section is not None or patch_invalid_sections) and len(audio_files) != 1:
        raise typer.BadParameter("Patch options require exactly one matching audio file.")
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
    patch_mode = patch_section is not None or patch_invalid_sections

    for index, audio_path in enumerate(audio_files, start=1):
        output_path = output_dir / f"{audio_path.stem}.md"
        try:
            had_output, existing_markdown, transcript_sections = read_existing_note(output_path)
        except RuntimeError as exc:
            failures.append(str(exc))
            typer.echo(f"ERROR {exc}", err=True)
            continue

        base_output_path = find_base_transcript_path(output_dir, audio_path.stem)
        if not patch_mode and base_output_path is not None:
            try:
                has_base_output, base_markdown, _ = read_existing_note(base_output_path)
            except RuntimeError as exc:
                failures.append(str(exc))
                typer.echo(f"ERROR {exc}", err=True)
                continue
            if has_base_output and has_transcript_content(base_markdown):
                skipped += 1
                continue

        target_sections: list[int] = []
        stored_prompt = extract_prompt_metadata(existing_markdown) if had_output else None
        desired_prompt = build_note_prompt(system_prompt, cleaned_user_prompt)
        if not patch_mode and has_transcript_content(existing_markdown):
            if stored_prompt == desired_prompt:
                skipped += 1
                continue
            if dry_run:
                typer.echo(f"[{index}/{total}] dry-run update metadata {audio_path.name} -> {output_path.name}")
                continue
            typer.echo(f"[{index}/{total}] update metadata {audio_path.name} -> {output_path.name}")
            try:
                output_path.write_text(set_prompt_metadata(existing_markdown, desired_prompt), encoding="utf-8")
            except OSError as exc:
                failures.append(f"{output_path.name}: {exc}")
                typer.echo(f"ERROR {output_path.name}: {exc}", err=True)
                continue
            updated += 1
            continue
        if patch_mode:
            if not had_output:
                failures.append(f"{output_path.name}: transcript file does not exist for patching")
                typer.echo(f"ERROR {output_path.name}: transcript file does not exist for patching", err=True)
                continue
            if not has_transcript_content(existing_markdown):
                failures.append(f"{output_path.name}: document has no transcript section to patch")
                typer.echo(f"ERROR {output_path.name}: document has no transcript section to patch", err=True)
                continue
            target_sections = [patch_section] if patch_section is not None else find_invalid_transcript_sections(
                existing_markdown
            )
            if patch_invalid_sections and not target_sections:
                skipped += 1
                typer.echo(f"No invalid transcript sections found in {output_path.name}")
                continue
        note_prompt = desired_prompt if cleaned_user_prompt is not None or not stored_prompt else stored_prompt
        transcription_system_prompt, effective_user_prompt = resolve_patch_prompts(
            system_prompt, stored_prompt if patch_mode else None, cleaned_user_prompt
        )
        action = (
            f"patch section {patch_section}"
            if patch_section is not None
            else (
                f"patch invalid sections {','.join(str(section) for section in target_sections)}"
                if patch_invalid_sections
                else ("update" if had_output else "create")
            )
        )
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

        try:
            _, windows = plan_audio_chunks(audio_path, chunk_minutes=chunk_minutes)
        except RuntimeError as exc:
            failures.append(f"{audio_path.name}: {exc}")
            typer.echo(f"ERROR {audio_path.name}: {exc}", err=True)
            continue

        def log_progress(current_chunk: int, total_chunks: int) -> None:
            if total_chunks == 1:
                emit_transcription_progress(
                    current=index,
                    total=total,
                    action=action,
                    audio_path=audio_path,
                    output_path=output_path,
                    note=note,
                )
                return
            emit_transcription_progress(
                current=current_chunk,
                total=total_chunks,
                action=action,
                audio_path=audio_path,
                output_path=output_path,
                note=note,
            )

        try:
            result = transcribe_audio(
                audio_path,
                system_prompt=transcription_system_prompt,
                user_prompt=effective_user_prompt,
                model=model,
                client=client,
                pricing=pricing or {},
                chunk_minutes=chunk_minutes,
                patch_section=(target_sections[0] if patch_invalid_sections else patch_section),
                windows=windows,
                progress_callback=log_progress,
            )
        except RuntimeError as exc:
            failures.append(f"{audio_path.name}: {exc}")
            typer.echo(f"ERROR {audio_path.name}: {exc}", err=True)
            continue

        emit_invalid_transcript_warnings(
            audio_path=audio_path,
            output_path=output_path,
            warnings=result.warnings,
            input_dir=input_dir,
            output_dir=output_dir,
            prompt_file=prompt_file,
            model=model,
            user_prompt=effective_user_prompt,
            chunk_minutes=chunk_minutes,
        )

        total_cost_usd += result.usage.cost_usd
        typer.echo(
            f"tokens={result.usage.total_tokens} cost=${result.usage.cost_usd:.6f} total_cost=${total_cost_usd:.6f}"
        )
        try:
            if patch_invalid_sections:
                updated_markdown = existing_markdown
                combined_usage = [result.usage]
                for section in target_sections:
                    section_result = (
                        result
                        if section == target_sections[0]
                        else transcribe_audio(
                            audio_path,
                            system_prompt=transcription_system_prompt,
                            user_prompt=effective_user_prompt,
                            model=model,
                                client=client,
                                pricing=pricing or {},
                                chunk_minutes=chunk_minutes,
                                patch_section=section,
                                windows=windows,
                                progress_callback=log_progress,
                            )
                    )
                    if section != target_sections[0]:
                        total_cost_usd += section_result.usage.cost_usd
                        combined_usage.append(section_result.usage)
                        typer.echo(
                            f"tokens={section_result.usage.total_tokens} cost=${section_result.usage.cost_usd:.6f} total_cost=${total_cost_usd:.6f}"
                        )
                        emit_invalid_transcript_warnings(
                            audio_path=audio_path,
                            output_path=output_path,
                            warnings=section_result.warnings,
                            input_dir=input_dir,
                            output_dir=output_dir,
                            prompt_file=prompt_file,
                            model=model,
                            user_prompt=effective_user_prompt,
                            chunk_minutes=chunk_minutes,
                        )
                    updated_markdown = patch_transcript_section(
                        updated_markdown, section, section_result.transcript, prompt=note_prompt
                    )
                output_path.write_text(updated_markdown, encoding="utf-8")
            else:
                output_path.write_text(
                    (
                        patch_transcript_section(existing_markdown, patch_section, result.transcript, prompt=note_prompt)
                        if patch_section is not None
                        else upsert_transcript_section(
                            existing_markdown,
                            audio_path.stem,
                            result.transcript,
                            prompt=note_prompt,
                        )
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
