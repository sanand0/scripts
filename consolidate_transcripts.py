#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["typer>=0.12"]
# ///
"""Aggregate transcript sections into a unified transcripts.md file."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

import typer

TARGET_SECTIONS: Sequence[str] = (
    "Try out",
    "What I missed",
    "Insights",
    "Corrections",
    "Persona",
    "What they missed",
)


def slugify(label: str) -> str:
    """Return consolidate-like slug for a label."""
    slug = re.sub(r"[^a-zA-Z0-9\s_-]+", "", label).strip().lower()
    slug = re.sub(r"[\s_]+", "-", slug)
    return re.sub(r"-+", "-", slug).strip("-")


AUTO_EXCLUDE = {"transcripts.md", "try-out.md", "insights.md", "what-i-missed.md"}
AUTO_EXCLUDE.update(f"{slugify(label)}.md" for label in TARGET_SECTIONS)


def build_header_regex(label: str) -> re.Pattern[str]:
    """Create a case-insensitive regex matching the section label as a bullet."""
    words = re.split(r"\s+", label.strip())
    joined = r"[ \-]".join(map(re.escape, words)) if words else ""
    pattern = rf"^[ \t]*[-*][ \t]+(?:\*\*)?\s*(?:{joined})\s*(?:\*\*)?[ \t]*:?[ \t]*$"
    return re.compile(pattern, re.IGNORECASE)


def is_section_break(line: str) -> bool:
    """Return True if line likely starts a new top-level section/bullet."""
    if not line:
        return False
    if line.startswith("  ") or line.startswith("\t"):
        return False
    if line.startswith(("#", "- ", "* ")):
        return True
    if line[:1].strip() and not line.startswith(("-", "*")):
        return True
    return False


def find_sections(lines: List[str], header_re: re.Pattern[str], max_scan: int) -> List[List[str]]:
    """Find and return all targeted bullet sections and nested items (raw lines)."""
    scan_upto = min(len(lines), max_scan)
    out: List[List[str]] = []
    i = 0
    while i < scan_upto:
        line = lines[i].rstrip("\n")
        if header_re.match(line):
            collected: List[str] = [line]
            j = i + 1
            while j < len(lines):
                next_line = lines[j].rstrip("\n")
                if is_section_break(next_line):
                    break
                if next_line.startswith(("  ", "\t")) or next_line.strip() == "":
                    collected.append(next_line)
                    j += 1
                    continue
                break
            out.append(collected)
            i = j
            continue
        i += 1
    return out


def iter_markdown_files(root: Path, exclude: set[str] | None = None) -> Iterable[Path]:
    """Yield .md files in the directory (non-recursive)."""
    exclude = exclude or set()
    for path in sorted(root.iterdir(), reverse=True):
        if path.is_file() and path.suffix.lower() == ".md" and path.name not in exclude:
            yield path


def collect_sections(
    root: Path, label_patterns: Dict[str, re.Pattern[str]], max_scan: int
) -> Dict[str, Dict[str, List[str]]]:
    """Return nested mapping of section -> file -> copied bullet lines."""
    collected: Dict[str, Dict[str, List[str]]] = {label: {} for label in TARGET_SECTIONS}
    for md in iter_markdown_files(root, exclude=set(AUTO_EXCLUDE)):
        text = md.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()

        for label in TARGET_SECTIONS:
            buckets = find_sections(lines, label_patterns[label], max_scan=max_scan)
            bullet_lines: List[str] = []
            for bucket in buckets:
                bullet_lines.extend(line for line in bucket[1:] if line.strip())
            if bullet_lines:
                collected[label][md.name] = bullet_lines

    return collected


def render_transcripts(collected: Dict[str, Dict[str, List[str]]]) -> str:
    """Render the transcripts markdown respecting the required ordering."""
    lines: List[str] = []
    for idx, label in enumerate(TARGET_SECTIONS):
        if idx:
            lines.append("")
        lines.append(f"## {label}")
        files = collected[label]
        if not files:
            continue
        lines.append("")
        for idx, (name, bullet_lines) in enumerate(files.items()):
            if idx:
                lines.append("")
            lines.append(f"- {name}")
            for entry in bullet_lines:
                lines.append(entry if entry.startswith((" ", "\t")) else f"  {entry}")
    lines.append("")
    return "\n".join(lines)


app = typer.Typer(add_completion=False, help=__doc__)


@app.command(context_settings={"allow_extra_args": False, "ignore_unknown_options": False})
def main(max_scan: int = typer.Option(300, help="Max lines to scan per file")) -> None:
    """Generate transcripts.md with fixed section ordering."""
    root = Path("/home/sanand/Dropbox/notes/transcripts")
    label_patterns = {label: build_header_regex(label) for label in TARGET_SECTIONS}
    collected = collect_sections(root, label_patterns=label_patterns, max_scan=max_scan)
    target = Path("/home/sanand/code/notes/transcripts.md")
    with open(target, "w", encoding="utf-8") as f:
        f.write(render_transcripts(collected))


if __name__ == "__main__":
    app()
