#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "markdown-it-py>=3.0.0",
#     "typer>=0.12.3",
# ]
# ///

"""Merge weekly about notes into per-person Markdown files.

Paste the About Updates prompt every Sunday at
https://chatgpt.com/g/g-p-6a40b2ac3dfc8191b48ad8d978d0e8bf-weekly/project

Examples:
  aboutmerge.py --dry-run
  aboutmerge.py --source-glob 'week-2026-06-06.md' --dry-run --format jsonl | jaq .
  aboutmerge.py --target-dir /tmp/about-copy --source-glob 'week-2026-06-06.md'
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Annotated, Iterable

from markdown_it import MarkdownIt
import typer

app = typer.Typer(add_completion=False, no_args_is_help=False)
MD = MarkdownIt("commonmark")
SKIP_H1 = {"review", "skipped", "checklist"}
DEFAULT_TARGET_DIR = Path("~/Dropbox/notes/about").expanduser()


@dataclass
class H2Section:
    title: str
    lines: list[str]


@dataclass
class H1Section:
    title: str
    h2s: list[H2Section]


@dataclass
class Event:
    action: str
    source: str
    target: str
    h2: str = ""
    line: int | None = None
    existing: int | None = None
    dry_run: bool = False


@dataclass
class Heading:
    level: int
    title: str
    start: int


def headings(lines: list[str]) -> list[Heading]:
    tokens = MD.parse("".join(lines))
    result: list[Heading] = []
    for index, token in enumerate(tokens):
        if token.type != "heading_open" or not token.map:
            continue
        inline = tokens[index + 1] if index + 1 < len(tokens) else None
        title = inline.content.strip() if inline and inline.type == "inline" else ""
        result.append(Heading(int(token.tag[1]), title, token.map[0]))
    return result


def parse_source(path: Path) -> list[H1Section]:
    lines = path.read_text().splitlines(keepends=True)
    source_headings = headings(lines)
    h1s: list[H1Section] = []
    for h1_index, h1 in enumerate(source_headings):
        if h1.level != 1 or h1.title.casefold() in SKIP_H1:
            continue
        next_h1_start = next(
            (h.start for h in source_headings[h1_index + 1 :] if h.level == 1),
            len(lines),
        )
        h2s: list[H2Section] = []
        section_headings = [
            (offset, h)
            for offset, h in enumerate(source_headings[h1_index + 1 :], h1_index + 1)
            if h.start < next_h1_start
        ]
        for offset, h2 in section_headings:
            if h2.level != 2:
                continue
            next_peer_start = next(
                (h.start for h in source_headings[offset + 1 :] if h.start < next_h1_start and h.level <= 2),
                next_h1_start,
            )
            h2s.append(H2Section(title=h2.title, lines=lines[h2.start : next_peer_start]))
        h1s.append(H1Section(title=h1.title, h2s=h2s))
    return h1s


def find_target(title: str, target_dir: Path) -> Path:
    expected = f"{title}.md"
    for path in target_dir.glob("*.md"):
        if path.name.casefold() == expected.casefold():
            return path
    return target_dir / expected


def target_h2_titles(lines: Iterable[str]) -> set[str]:
    return {h.title for h in headings(list(lines)) if h.level == 2}


def insertion_index(lines: list[str]) -> int:
    for h in headings(lines):
        if h.level >= 2:
            return h.start
    return len(lines)


def ensure_trailing_newline(lines: list[str]) -> list[str]:
    if lines and not lines[-1].endswith("\n"):
        return [*lines[:-1], f"{lines[-1]}\n"]
    return lines


def render_event(event: Event, fmt: str) -> None:
    if fmt == "jsonl":
        print(json.dumps(asdict(event), ensure_ascii=False), flush=True)
        return
    if event.action == "skip":
        print(f"skip source={Path(event.source).name} existing={event.existing}", file=sys.stderr, flush=True)
        return
    print(f"{event.action} target={event.target}:{event.line} h2={event.h2}", file=sys.stderr, flush=True)


def existing_source_h2_count(h1s: list[H1Section], target_dir: Path, state: dict[Path, list[str]]) -> int:
    existing = 0
    for h1 in h1s:
        target = find_target(h1.title, target_dir)
        if target in state:
            lines = state[target]
        elif target.exists():
            lines = target.read_text().splitlines(keepends=True)
        else:
            continue
        titles = target_h2_titles(lines)
        existing += sum(1 for h2 in h1.h2s if h2.title in titles)
        if existing >= 2:
            return existing
    return existing


def select_sources(sources: list[Path], target_dir: Path, fmt: str, dry_run: bool) -> tuple[list[Path], int]:
    required: list[Path] = []
    skipped = 0
    consecutive_skips = 0
    for source in sorted(sources, reverse=True):
        existing = existing_source_h2_count(parse_source(source), target_dir, {})
        if existing >= 2:
            skipped += 1
            consecutive_skips += 1
            render_event(Event("skip", str(source), "", existing=existing, dry_run=dry_run), fmt)
            if consecutive_skips == 2:
                break
            continue
        required.append(source)
        consecutive_skips = 0
    return sorted(required), skipped


def merge_source(source: Path, target_dir: Path, dry_run: bool, fmt: str, state: dict[Path, list[str]]) -> tuple[int, int]:
    created = 0
    inserted = 0
    h1s = parse_source(source)
    for h1 in h1s:
        target = find_target(h1.title, target_dir)
        if target in state:
            lines = state[target]
            target_created = False
        elif target.exists():
            lines = target.read_text().splitlines(keepends=True)
            target_created = False
        else:
            lines = [f"# {h1.title}\n", "\n"]
            created += 1
            target_created = True

        existing_h2s = target_h2_titles(lines)
        missing = [h2 for h2 in h1.h2s if h2.title not in existing_h2s]
        if not missing:
            state[target] = lines
            if not dry_run and not target.exists():
                target.write_text("".join(lines))
            continue

        lines = ensure_trailing_newline(lines)
        index = insertion_index(lines)
        block: list[str] = []
        for h2 in missing:
            if block and block[-1].strip():
                block.append("\n")
            h2_lines = ensure_trailing_newline(h2.lines)
            line_no = index + len(block) + 1
            render_event(
                Event("create" if target_created and not block else "insert", str(source), target.name, h2.title, line_no, dry_run=dry_run),
                fmt,
            )
            block.extend(h2_lines)
            inserted += 1

        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("".join([*lines[:index], *block, *lines[index:]]))
        state[target] = [*lines[:index], *block, *lines[index:]]
    return created, inserted


def describe() -> None:
    schema = {
        "name": "aboutmerge.py",
        "description": "Merge H2 sections from weekly about notes into H1-named target files.",
        "params": {
            "target_dir": "Directory containing week-*.md and target person files.",
            "source_glob": "Glob, relative to target_dir unless absolute.",
            "source_selection": "Scan sources in reverse alphabetical order, stopping after two consecutive skippable files.",
            "skip_existing": "Skip a source when at least two of its H2 sections already exist in targets.",
            "dry_run": "Preview creations and insertions without writing.",
            "format": "text logs to stderr, or jsonl events to stdout.",
        },
        "writes": "Only creates files and inserts missing H2 sections; never deletes or rewrites existing lines.",
    }
    print(json.dumps(schema, indent=2))


@app.command()
def main(
    target_dir: Annotated[Path, typer.Option(help="Directory containing weekly and target files.")] = DEFAULT_TARGET_DIR,
    source_glob: Annotated[str, typer.Option(help="Source glob, relative to target-dir unless absolute.")] = "week-*.md",
    dry_run: Annotated[bool, typer.Option(help="Show planned changes without writing.")] = False,
    format: Annotated[str, typer.Option(help="Output format: text or jsonl.")] = "text",
    describe_cli: Annotated[bool, typer.Option("--describe", help="Print machine-readable CLI schema and exit.")] = False,
) -> None:
    """Merge weekly about notes into per-person Markdown files.

    Examples:
      aboutmerge.py --dry-run
      aboutmerge.py --source-glob 'week-2026-06-06.md' --dry-run --format jsonl | jaq .
      aboutmerge.py --target-dir /tmp/about-copy --source-glob 'week-2026-06-06.md'
    """
    if describe_cli:
        describe()
        raise typer.Exit()
    if format not in {"text", "jsonl"}:
        raise typer.BadParameter("format must be text or jsonl")
    target_dir = target_dir.expanduser()
    if not target_dir.is_dir():
        raise typer.BadParameter(f"target-dir does not exist: {target_dir}")

    source_pattern = Path(source_glob).expanduser()
    sources = sorted(source_pattern.parent.glob(source_pattern.name) if source_pattern.is_absolute() else target_dir.glob(source_glob))
    if not sources:
        raise typer.BadParameter(f"no sources matched: {source_glob}")

    total_created = 0
    total_inserted = 0
    selected_sources, total_skipped = select_sources(sources, target_dir, format, dry_run)
    state: dict[Path, list[str]] = {}
    for source in selected_sources:
        created, inserted = merge_source(source, target_dir, dry_run, format, state)
        total_created += created
        total_inserted += inserted

    summary = {
        "sources": len(sources),
        "selected": len(selected_sources),
        "skipped": total_skipped,
        "created": total_created,
        "inserted": total_inserted,
        "dry_run": dry_run,
    }
    if format == "jsonl":
        print(json.dumps({"action": "summary", **summary}), flush=True)
    else:
        print(
            f"sources={summary['sources']} selected={summary['selected']} skipped={summary['skipped']} created={summary['created']} inserted={summary['inserted']} dry_run={dry_run}",
            file=sys.stderr,
            flush=True,
        )


if __name__ == "__main__":
    app()
