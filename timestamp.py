#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["typer>=0.12"]
# ///
"""Make chunked call-transcript timestamps cumulative."""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any

import typer

DEFAULT_ROOT = Path.home() / "Dropbox/notes/transcripts"
TRANSCRIPT_PART_SEPARATOR = "\n\n---\n\n"  # Candidate boundary written by `call`; only resets trigger shifts.
TRANSCRIPT_SECTION_RE = re.compile(r"(?ms)^##\s+Transcript\s*$\n?(?P<body>.*?)(?=^##\s+|\Z)")
TIMESTAMP_BRACKET_RE = re.compile(
    r"\[(?P<body>\d{1,3}:\d{2}(?::\d{2})?(?:\s*-\s*\d{1,3}:\d{2}(?::\d{2})?)?)\]"
)
TIME_TOKEN_RE = re.compile(r"\d{1,3}:\d{2}(?::\d{2})?")
FIVE_MINUTES = 5 * 60

app = typer.Typer(add_completion=False, no_args_is_help=False, help=__doc__)


@dataclass
class UpdateResult:
    text: str
    chunk_count: int
    adjusted_chunks: int
    timestamps_changed: int
    warnings: list[str]


def parse_time(token: str) -> int:
    """Return seconds for MM:SS or HH:MM:SS."""
    parts = [int(part) for part in token.split(":")]
    if len(parts) == 2:
        minutes, seconds = parts
        if seconds >= 60:
            raise ValueError(f"Invalid timestamp: {token}")
        return minutes * 60 + seconds
    hours, minutes, seconds = parts
    if minutes >= 60 or seconds >= 60:
        raise ValueError(f"Invalid timestamp: {token}")
    return hours * 3600 + minutes * 60 + seconds


def format_time(seconds: int, fields: int) -> str:
    """Format seconds using the source token's 2- or 3-field style."""
    if fields == 2:
        minutes, seconds = divmod(seconds, 60)
        return f"{minutes:02d}:{seconds:02d}"
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def timestamp_occurrences(chunk: str, first_line: int) -> list[tuple[int, int, str]]:
    """Return timestamp seconds, source line, and source token."""
    return [
        (
            parse_time(token.group()),
            first_line + chunk.count("\n", 0, bracket.start("body") + token.start()),
            token.group(),
        )
        for bracket in TIMESTAMP_BRACKET_RE.finditer(chunk)
        for token in TIME_TOKEN_RE.finditer(bracket.group("body"))
    ]


def timestamp_values(chunk: str) -> list[int]:
    """Return timestamp seconds, including both ends of ranges."""
    return [value for value, _, _ in timestamp_occurrences(chunk, 1)]


def shift_chunk(chunk: str, offset: int) -> tuple[str, int]:
    """Add offset seconds to every transcript timestamp in one chunk."""
    changed = 0

    def shift_bracket(bracket: re.Match[str]) -> str:
        nonlocal changed

        def shift_token(token: re.Match[str]) -> str:
            nonlocal changed
            changed += 1
            fields = token.group().count(":") + 1
            return format_time(parse_time(token.group()) + offset, fields)

        body = TIME_TOKEN_RE.sub(shift_token, bracket.group("body"))
        return f"[{body}]"

    return TIMESTAMP_BRACKET_RE.sub(shift_bracket, chunk), changed


def ceil_five_minutes(seconds: int) -> int:
    """Round up to a 5-minute boundary."""
    return (seconds + FIVE_MINUTES - 1) // FIVE_MINUTES * FIVE_MINUTES


def update_markdown(markdown: str, chunk_starts: list[int] | None = None) -> UpdateResult:
    """Return Markdown with cumulative timestamps inside only the Transcript section."""
    match = TRANSCRIPT_SECTION_RE.search(markdown)
    if not match:
        raise ValueError("No '## Transcript' section found")

    body = match.group("body")
    chunks = body.split(TRANSCRIPT_PART_SEPARATOR)
    if chunk_starts is not None and len(chunk_starts) != len(chunks):
        raise ValueError(f"--chunk-starts has {len(chunk_starts)} values but transcript has {len(chunks)} chunks")

    warnings: list[str] = []
    body_start = match.start("body")
    body_line = markdown[:body_start].count("\n") + 1
    separator_matches = list(re.finditer(r"(?m)^---[ \t]*$", body))
    delimiter_matches = list(re.finditer(re.escape(TRANSCRIPT_PART_SEPARATOR), body))
    delimiter_lines = {
        match.start() + match.group().find("---") for match in delimiter_matches
    }
    extra_separator_lines = [
        body_line + body.count("\n", 0, separator.start())
        for separator in separator_matches
        if separator.start() not in delimiter_lines
    ]
    line_separators = len(separator_matches)
    if line_separators > len(chunks) - 1:
        locations = ", ".join(str(line) for line in extra_separator_lines)
        location_label = "line" if len(extra_separator_lines) == 1 else "lines"
        warnings.append(
            f"{location_label} {locations}: found {line_separators - (len(chunks) - 1)} extra '---' line(s) "
            "inside Transcript; ignored as non-call separators"
        )

    adjusted_chunks = 0
    timestamps_changed = 0
    previous_last: int | None = None
    previous_origin: int | None = 0
    auto_ambiguity: str | None = None
    updated_chunks: list[str] = []
    body_offset = 0

    for index, chunk in enumerate(chunks, start=1):
        chunk_first_line = body_line + body.count("\n", 0, body_offset)
        content_offset = next((offset for offset, char in enumerate(chunk) if not char.isspace()), 0)
        chunk_line = chunk_first_line + chunk.count("\n", 0, content_offset)
        occurrences = timestamp_occurrences(chunk, chunk_first_line)
        values = [value for value, _, _ in occurrences]
        if not values:
            warnings.append(f"chunk {index} (line {chunk_line}): no timestamps")
            updated_chunks.append(chunk)
            previous_last = None
            previous_origin = None
            if chunk_starts is None and index < len(chunks):
                auto_ambiguity = f"timestamp-free chunk {index} (line {chunk_line})"
            body_offset += len(chunk) + (len(TRANSCRIPT_PART_SEPARATOR) if index < len(chunks) else 0)
            continue

        first_non_monotonic = next(
            (
                (previous, current)
                for previous, current in pairwise(occurrences)
                if current[0] < previous[0]
            ),
            None,
        )
        if first_non_monotonic:
            previous, current = first_non_monotonic
            warnings.append(
                f"chunk {index} (line {chunk_line}): non-monotonic timestamps; first example: "
                f"line {previous[1]} [{previous[2]}] -> line {current[1]} [{current[2]}]; review manually"
            )
        non_monotonic = first_non_monotonic is not None

        offset = 0
        if chunk_starts is not None:
            desired = chunk_starts[index - 1]
            # Raw call chunks normally restart near 00:00. Requiring a >=5m gap to the
            # requested absolute start makes explicit mode safe to rerun after overlaps.
            if desired and values[0] + FIVE_MINUTES <= desired:
                offset = desired
            elif desired and values[0] < desired:
                warnings.append(
                    f"chunk {index} (line {chunk_line}): first timestamp is <5m before requested start; "
                    "left unchanged for idempotence"
                )
        elif index > 1:
            if auto_ambiguity:
                warnings.append(
                    f"chunk {index} (line {chunk_line}): cannot infer offset after {auto_ambiguity}; "
                    "use --chunk-starts"
                )
            elif previous_last is not None and values[0] + FIVE_MINUTES <= previous_last:
                offset = ceil_five_minutes(previous_last)
                if previous_origin is not None:
                    inferred_minutes = (offset - previous_origin) / 60
                    if inferred_minutes < 15 or inferred_minutes > 30:
                        warnings.append(
                            f"chunk {index} (line {chunk_line}): inferred previous chunk length {inferred_minutes:g}m is unusual; "
                            "use --chunk-starts if this is wrong"
                        )
            elif previous_last is not None and values[0] < previous_last:
                warnings.append(
                    f"chunk {index} (line {chunk_line}): backward jump is <5m; left unchanged for idempotence"
                )

        if offset:
            chunk, changed = shift_chunk(chunk, offset)
            values = [value + offset for value in values]
            adjusted_chunks += 1
            timestamps_changed += changed

        updated_chunks.append(chunk)
        previous_last = values[-1]
        if chunk_starts is not None:
            previous_origin = chunk_starts[index - 1]
        elif offset:
            previous_origin = offset
        elif index == 1:
            previous_origin = 0
        else:
            previous_origin = None
        if non_monotonic and chunk_starts is None and index < len(chunks):
            auto_ambiguity = f"non-monotonic chunk {index} (line {chunk_line})"
        body_offset += len(chunk) + (len(TRANSCRIPT_PART_SEPARATOR) if index < len(chunks) else 0)

    updated_body = TRANSCRIPT_PART_SEPARATOR.join(updated_chunks)
    text = markdown[: match.start("body")] + updated_body + markdown[match.end("body") :]
    return UpdateResult(text, len(chunks), adjusted_chunks, timestamps_changed, warnings)


def parse_start_value(value: str | int | float) -> int:
    """Parse a chunk start: bare numbers are minutes; colon values are timestamps."""
    if isinstance(value, (int, float)):
        seconds = round(float(value) * 60)
    else:
        value = value.strip()
        seconds = parse_time(value) if ":" in value else round(float(value) * 60)
    if seconds < 0:
        raise ValueError("Chunk starts cannot be negative")
    return seconds


def parse_chunk_starts(value: str | list[Any]) -> list[int]:
    """Parse comma-separated or JSON-array chunk starts into seconds."""
    values = value if isinstance(value, list) else [item.strip() for item in value.split(",") if item.strip()]
    starts = [parse_start_value(item) for item in values]
    if any(current < previous for previous, current in zip(starts, starts[1:])):
        raise ValueError("Chunk starts must be non-decreasing")
    return starts


def resolve_transcript(spec: str, root: Path = DEFAULT_ROOT) -> Path:
    """Resolve an existing path, else the latest descending filename substring match."""
    candidate = Path(spec).expanduser()
    if candidate.exists():
        if not candidate.is_file():
            raise ValueError(f"Not a file: {candidate}")
        return candidate.resolve()
    if candidate.is_absolute() or candidate.parent != Path("."):
        raise FileNotFoundError(f"Transcript does not exist: {candidate}")
    if not root.is_dir():
        raise FileNotFoundError(f"Transcript directory does not exist: {root}")
    needle = spec.casefold()
    matches = sorted(
        (path for path in root.glob("*.md") if needle in path.name.casefold()),
        key=lambda path: path.name,
        reverse=True,
    )
    if not matches:
        raise FileNotFoundError(f"No transcript matching '{spec}' in {root}")
    return matches[0]


def describe() -> dict[str, Any]:
    return {
        "name": "timestamp.py",
        "purpose": "Make call-transcript chunk timestamps cumulative.",
        "inputs": {
            "files": "One or more paths or filename substrings; latest descending match wins.",
            "chunk_starts": "Optional absolute starts, one per chunk. Bare numbers are minutes; MM:SS/HH:MM:SS accepted.",
            "params": {"files": ["Naveen"], "chunk_starts": [0, 20]},
        },
        "writes": "In place by default; --output-dir writes copies elsewhere; --dry-run writes nothing.",
        "formats": ["auto", "text", "jsonl"],
        "examples": [
            "timestamp.py Naveen",
            "timestamp.py Naveen Ankor --dry-run",
            "timestamp.py '2026-09-01 GIPCL' --chunk-starts 0,30,60,90,120",
            "timestamp.py --params '{\"files\":[\"Naveen\"],\"chunk_starts\":[0,20]}' --format jsonl",
        ],
    }


def load_params(raw: str | None) -> dict[str, Any]:
    if raw is None:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid --params JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("--params must be a JSON object")
    allowed = {"files", "chunk_starts", "output_dir", "dry_run", "format"}
    unknown = set(data) - allowed
    if unknown:
        raise ValueError(f"Unknown --params field(s): {', '.join(sorted(unknown))}")
    if "files" in data and (not isinstance(data["files"], list) or not all(isinstance(x, str) for x in data["files"])):
        raise ValueError("--params files must be an array of strings")
    if "dry_run" in data and not isinstance(data["dry_run"], bool):
        raise ValueError("--params dry_run must be boolean")
    return data


@app.command(context_settings={"allow_extra_args": False, "ignore_unknown_options": False})
def main(
    files: list[str] | None = typer.Argument(
        None, help="Transcript path(s), or filename substrings searched under ~/Dropbox/notes/transcripts."
    ),
    chunk_starts: str | None = typer.Option(
        None, "--chunk-starts", help="Absolute chunk starts, e.g. 0,25,50 or 00:00,25:00,50:00."
    ),
    output_dir: Path | None = typer.Option(None, "--output-dir", help="Write transformed copies here instead of in place."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Analyze and report without writing."),
    fmt: str = typer.Option("auto", "--format", help="Output format: auto|text|jsonl."),
    params: str | None = typer.Option(None, "--params", help="JSON object with files/chunk_starts/output_dir/dry_run/format."),
    show_describe: bool = typer.Option(False, "--describe", help="Print machine-readable CLI metadata and exit."),
) -> None:
    """Update one or more transcript files.

    Examples:
      timestamp.py Naveen
      timestamp.py Naveen Ankor --dry-run
      timestamp.py "2026-09-01 GIPCL" --chunk-starts 0,30,60,90,120
      timestamp.py Naveen --output-dir /tmp/timestamps --format jsonl | jaq .
    """
    if show_describe:
        print(json.dumps(describe(), indent=2))
        return

    try:
        data = load_params(params)
        specs = list(files or data.get("files") or [])
        starts = parse_chunk_starts(chunk_starts) if chunk_starts is not None else None
        if starts is None and data.get("chunk_starts") is not None:
            starts = parse_chunk_starts(data["chunk_starts"])
        if output_dir is None and data.get("output_dir"):
            output_dir = Path(data["output_dir"]).expanduser()
        dry_run = dry_run or bool(data.get("dry_run", False))
        if fmt == "auto" and data.get("format"):
            fmt = str(data["format"])
        if not specs:
            raise ValueError("Provide at least one transcript FILE, or files via --params")
        if fmt not in {"auto", "text", "jsonl"}:
            raise ValueError("--format must be auto, text, or jsonl")
        fmt = ("text" if sys.stdout.isatty() else "jsonl") if fmt == "auto" else fmt

        paths = [resolve_transcript(spec) for spec in specs]
        if len(set(paths)) != len(paths):
            raise ValueError("Multiple arguments resolved to the same transcript")
        targets = [output_dir / path.name if output_dir else path for path in paths]
        if len(set(targets)) != len(targets):
            raise ValueError("Multiple inputs would write to the same output file")

        for path, target in zip(paths, targets):
            typer.echo(f"READ {path}", err=True)
            source = path.read_text(encoding="utf-8")
            result = update_markdown(source, starts)
            changed = result.text != source
            status = "dry-run" if dry_run else ("updated" if changed else ("copied" if output_dir else "unchanged"))
            if not dry_run and (changed or output_dir is not None):
                typer.echo(f"WRITE {target}", err=True)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(result.text, encoding="utf-8")
            for warning in result.warnings:
                typer.echo(f"WARNING {path.name}: {warning}", err=True)
            record = {
                "status": status, "input": str(path), "output": str(target), "chunks": result.chunk_count,
                "adjusted_chunks": result.adjusted_chunks, "timestamps_changed": result.timestamps_changed,
                "warnings": result.warnings,
            }
            if fmt == "jsonl":
                print(json.dumps(record, ensure_ascii=False))
            else:
                print(f"{status}\tchunks={result.chunk_count}\tadjusted={result.adjusted_chunks}\t"
                      f"timestamps={result.timestamps_changed}\t{path}")
    except (ValueError, FileNotFoundError, OSError) as exc:
        typer.echo(f"ERROR {exc}", err=True)
        raise typer.Exit(1) from exc


if __name__ == "__main__":
    app()
