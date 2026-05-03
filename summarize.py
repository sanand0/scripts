#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["typer>=0.9", "google-genai", "python-dotenv", "ruamel.yaml", "rich", "pydantic", "tenacity"]
# ///
"""
Add AI-generated YAML metadata to content files (transcripts, blog posts, etc.).

Content sets are defined in CONTENT_SETS. Each specifies a base directory, AI prompt,
and ordered list of fields to add. The entire file content (including YAML frontmatter)
is sent to the AI so it has full context.

HOW TO ADD A NEW CONTENT SET:
  1. Define FieldDef entries — each needs a name, AI description, Python type, and
     YAML formatter (str, flow_list, or list). Optionally add an extractor (regex
     shortcut before calling the AI) and a cleaner (normalize AI output).
  2. Append a ContentSet to CONTENT_SETS with name, base_dir, prompt, fields, and
     default_globs (patterns expanded against base_dir when no CLI patterns are given).
  3. No other code changes required.

Usage:
  uv run summarize.py transcript                             # all transcripts in base dir
  uv run summarize.py transcript "2026-04-*.md"              # relative glob (resolved from .)
  uv run summarize.py transcript "/other/path/*.md"          # absolute glob
  uv run summarize.py blog                                   # all blog posts/pages
  uv run summarize.py blog "2026-*.md"                       # relative glob
  uv run summarize.py --dry-run transcript "2026-04-*.md"    # preview changes
  uv run summarize.py --workers 8 transcript "*.md"          # 8 parallel workers
  uv run summarize.py --force transcript "2026-04-*.md"      # re-process all fields
"""

import concurrent.futures
import glob as glob_module
import json
import os
import re
import sys
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Optional

import typer
from dotenv import load_dotenv
from pydantic import Field as PydanticField, create_model
from rich.console import Console
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from tenacity import retry, stop_after_attempt, wait_exponential

app = typer.Typer(add_completion=False)
console = Console(stderr=True)
_print_lock = Lock()
MIN_CONTENT_LINES = 5

# Pricing in $ per 1M tokens (input, output) — update as needed
PRICING: dict[str, tuple[float, float]] = {
    "gemini-3-flash-preview": (0.075, 0.30),
    "gemini-3-pro-preview":   (1.25,  5.00),
    "gemini-2.5-flash":       (0.075, 0.30),
    "gemini-2.5-pro":         (1.25,  5.00),
    "gemini-2.0-flash":       (0.075, 0.30),
}
DEFAULT_PRICING = (0.075, 0.30)


# ── Field definition ────────────────────────────────────────────────────────────

@dataclass
class FieldDef:
    """Configuration for one YAML metadata field within a content set.

    Fields:
        name:          YAML key (e.g. "summary", "keywords")
        description:   Instruction embedded in the AI schema for this field
        pydantic_type: Python type annotation: str or list[str]
        to_yaml:       Converts the value for YAML: use str, flow_list, or list
        extract:       Optional (body: str) -> list; non-empty result skips AI call
        clean:         Optional normalizer applied to AI output before saving
    """
    name: str
    description: str
    pydantic_type: Any
    to_yaml: Callable
    extract: Callable[[str], list] | None = None
    clean: Callable[[Any], Any] | None = None


# ── Content set definition ──────────────────────────────────────────────────────

@dataclass
class ContentSet:
    """All configuration for one content type. See module docstring to add new sets."""
    name: str
    base_dir: Path
    prompt: str
    fields: list[FieldDef]
    default_globs: list[str] = field(default_factory=lambda: ["*.md"])
    meta_position: str = "before"  # "before": meta keys first; "after": meta keys last

    @property
    def meta_keys(self) -> list[str]:
        return [f.name for f in self.fields]


# ── YAML helpers ───────────────────────────────────────────────────────────────

def make_yaml() -> YAML:
    y = YAML()
    y.preserve_quotes = True
    y.default_flow_style = False
    y.width = 100000
    y.representer.add_representer(
        type(None),
        lambda d, _: d.represent_scalar("tag:yaml.org,2002:null", ""),
    )
    return y


def flow_list(items: list) -> CommentedSeq:
    cs = CommentedSeq(items)
    cs.fa.set_flow_style()
    return cs


def parse_frontmatter(text: str) -> tuple[dict, str, bool]:
    if not text.startswith("---"):
        return {}, text, False
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text, False
    data = make_yaml().load(text[3:end]) or {}
    body = text[end + 4:].lstrip("\n")
    return data, body, True


def dump_metadata(metadata: dict) -> str:
    stream = StringIO()
    make_yaml().dump(metadata, stream)
    return stream.getvalue()


def strip_empty_values(metadata: dict) -> CommentedMap:
    """Remove keys whose value is None or empty string (keep empty lists — meaningful)."""
    result = CommentedMap()
    for key, val in metadata.items():
        if val is None or (isinstance(val, str) and not val.strip()):
            continue
        result[key] = val
    return result


def write_file(
    path: Path,
    had_fm: bool,
    original_text: str,
    updates: dict,
    meta_position: str,
    full_metadata: dict | None = None,
) -> None:
    """Write metadata updates to file.

    Normal mode (full_metadata=None): text-based insertion — serializes only the new
    keys and appends/prepends them to the existing frontmatter text verbatim.  Existing
    keys are never re-serialized, so their formatting (flow-map spaces, sequence
    indentation, quoting, etc.) is preserved exactly.

    Force mode (full_metadata provided): re-serializes the entire frontmatter from the
    parsed dict.  Formatting of existing keys may change.
    """
    if full_metadata is not None:
        new_fm = dump_metadata(strip_empty_values(full_metadata))
        if had_fm:
            end = original_text.find("\n---", 3)
            after_content = original_text[end + 4:].lstrip("\n")
            new_text = f"---\n{new_fm}---\n\n{after_content}"
        else:
            new_text = f"---\n{new_fm}---\n\n{original_text.lstrip(chr(10))}"
    else:
        new_data = CommentedMap()
        for key, val in updates.items():
            if val is not None and not (isinstance(val, str) and not val.strip()):
                new_data[key] = val
        new_keys_text = dump_metadata(new_data)
        if had_fm:
            end = original_text.find("\n---", 3)
            existing_fm = original_text[4:end + 1]  # preserves original text + trailing \n
            after_content = original_text[end + 4:].lstrip("\n")
            new_fm = (existing_fm + new_keys_text) if meta_position == "after" else (new_keys_text + existing_fm)
            new_text = f"---\n{new_fm}---\n\n{after_content}"
        else:
            new_text = f"---\n{new_keys_text}---\n\n{original_text.lstrip(chr(10))}"
    path.write_text(new_text, encoding="utf-8")


def reorder_metadata(old: dict, updates: dict, meta_keys: list[str], meta_position: str = "before") -> CommentedMap:
    """Build CommentedMap with meta_keys placed before or after existing keys."""
    result = CommentedMap()
    if meta_position == "after":
        for key, val in old.items():
            if key not in meta_keys:
                result[key] = val
        for key in meta_keys:
            val = updates.get(key, old.get(key))
            if val is not None:
                result[key] = val
    else:  # "before"
        for key in meta_keys:
            val = updates.get(key, old.get(key))
            if val is not None or key in old:
                result[key] = val
        for key, val in old.items():
            if key not in result:
                result[key] = val
    return result


# ── Speaker extraction helpers (transcript-specific) ──────────────────────────

_PLACEHOLDER = re.compile(
    r"(unknown|unsure|multiple|inaudible|speaker|participant|member|moderator"
    r"|researcher|voiceover|female|male|audience|narrator|host|interviewer)",
    re.IGNORECASE,
)


def _is_real_name(name: str) -> bool:
    return (
        bool(name)
        and not _PLACEHOLDER.search(name)
        and not re.search(r"\s\d+$", name)
        and len(name.split()) <= 3
    )


def _clean_name(raw: str) -> str:
    return re.sub(r"\s*\(.*?\)", "", str(raw)).strip()


def extract_speakers(body: str) -> list[str]:
    """Extract bold speaker names (e.g. **Anand**: ...) from transcript body."""
    names = (_clean_name(raw) for raw in re.findall(r"\*\*([^*]+)\*\*\s*:", body))
    return list(dict.fromkeys(n for n in names if _is_real_name(n)))


def clean_people(people: list) -> list[str]:
    return [_clean_name(n) for n in people if _is_real_name(_clean_name(str(n).strip()))]


# ── Shared helpers ─────────────────────────────────────────────────────────────

def is_unprocessed(val: Any) -> bool:
    """Needs AI if None/missing/empty-string. Empty list [] = processed-but-empty."""
    return val is None or (isinstance(val, str) and not val.strip())


def count_content_lines(text: str) -> int:
    return sum(1 for ln in text.splitlines() if (s := ln.strip()) and not s.startswith("#"))


# ── Content set registry ───────────────────────────────────────────────────────
# To add a new content set: define FieldDefs and append a ContentSet below.

CONTENT_SETS: list[ContentSet] = [
    ContentSet(
        name="transcript",
        base_dir=Path("/home/sanand/Dropbox/notes/transcripts"),
        prompt=(
            "Analyze this meeting transcript and extract metadata.\n\n"
            "For 'actions': format each as \"Owner: Details of action\" "
            "(e.g. \"Anand: Send slides to Vikram\", \"Team: Review dashboard by Friday\").\n"
            "For 'people': include only clearly named speakers — no placeholders.\n\n"
        ),
        fields=[
            FieldDef(
                name="summary",
                description="1-2 sentences naming key speakers and what they argued or decided.",
                pydantic_type=str,
                to_yaml=str,
            ),
            FieldDef(
                name="keywords",
                description="5-15 topics, names, tools, and concepts for keyword search.",
                pydantic_type=list[str],
                to_yaml=flow_list,
            ),
            FieldDef(
                name="people",
                description="First names of clearly identified speakers only. Empty list if none.",
                pydantic_type=list[str],
                to_yaml=flow_list,
                extract=extract_speakers,  # try regex first; falls back to AI if empty
                clean=clean_people,        # filter placeholder names from AI output
            ),
            FieldDef(
                name="actions",
                description='Action items as "Owner: Details" e.g. "Alok: Test GCS buckets". Empty list if none.',
                pydantic_type=list[str],
                to_yaml=list,
            ),
        ],
    ),
    ContentSet(
        name="blog",
        base_dir=Path("/home/sanand/code/blog"),
        prompt=(
            "Generate a description and keywords for this blog post's metadata.\n\n"
            "Write the description in first person (\"I\") when the post is personal — "
            "i.e. when the author did, found, built, or decided something. "
            "Use imperative or neutral voice only for instructional or concept posts. "
            "Never use \"the author\". Be direct and conversational, not formal.\n\n"
        ),
        fields=[
            FieldDef(
                name="description",
                description=(
                    "20-40 word main point or most useful takeaway. "
                    "Prefer concrete ideas over framing. "
                    "Use first person when the post is personal (author did/found/built something). "
                    "Include distinctive methods, domains, tools, or concepts when central."
                ),
                pydantic_type=str,
                to_yaml=str,
            ),
            FieldDef(
                name="keywords",
                description=(
                    "4-8 lower-case topics (names, tools, concepts) for keyword search. "
                    "No generic tags, redundant synonyms."
                ),
                pydantic_type=list[str],
                to_yaml=flow_list,
            ),
        ],
        default_globs=["posts/**/*.md", "pages/**/*.md"],
        meta_position="after",
    ),
]

CONTENT_SET_MAP: dict[str, ContentSet] = {cs.name: cs for cs in CONTENT_SETS}


# ── Token/cost tracking ───────────────────────────────────────────────────────

@dataclass
class Usage:
    prompt: int = 0
    output: int = 0
    calls: int = 0

    def add(self, prompt: int, output: int) -> None:
        self.prompt += prompt
        self.output += output
        self.calls += 1

    def cost(self, model: str) -> float:
        p_in, p_out = PRICING.get(model, DEFAULT_PRICING)
        return self.prompt / 1e6 * p_in + self.output / 1e6 * p_out

    def as_dict(self) -> dict:
        return {"prompt": self.prompt, "output": self.output, "calls": self.calls}


# ── AI call ───────────────────────────────────────────────────────────────────

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30))
def call_gemini(client, model: str, content_set: ContentSet, text: str):
    from google.genai import types  # noqa: PLC0415

    ResponseModel = create_model(
        "ResponseModel",
        **{f.name: (f.pydantic_type, PydanticField(description=f.description))
           for f in content_set.fields},
    )
    response = client.models.generate_content(
        model=model,
        contents=content_set.prompt + text,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema=ResponseModel.model_json_schema(),
        ),
    )
    if response.text is None:
        reason = str(response.candidates[0].finish_reason) if response.candidates else "unknown"
        raise ValueError(f"Gemini returned no text (finish_reason={reason})")

    meta = ResponseModel.model_validate_json(response.text)
    usage = Usage()
    if response.usage_metadata:
        usage.add(
            response.usage_metadata.prompt_token_count or 0,
            response.usage_metadata.candidates_token_count or 0,
        )
    return meta, usage


# ── Per-file processing ───────────────────────────────────────────────────────

def process_file(
    path: Path, client, model: str, dry_run: bool, force: bool, content_set: ContentSet
) -> dict:
    result: dict = {
        "file": str(path),
        "name": path.name,
        "status": "skipped",
        "added_fields": [],
        "skipped_reason": None,
        "tokens": {"prompt": 0, "output": 0},
        "cost_usd": 0.0,
    }

    text = path.read_text(encoding="utf-8")
    metadata, body, had_fm = parse_frontmatter(text)
    meta_keys = content_set.meta_keys

    missing = [k for k in meta_keys if force or is_unprocessed(metadata.get(k))]
    if not missing:
        result["skipped_reason"] = "all fields present"
        return result

    if count_content_lines(text) < MIN_CONTENT_LINES:
        result["skipped_reason"] = f"trivial content"
        return result

    updates: dict = {}

    # Pre-extraction: try regex (no API call)
    for fdef in content_set.fields:
        if fdef.name not in missing or fdef.extract is None:
            continue
        if extracted := fdef.extract(body):
            updates[fdef.name] = fdef.to_yaml(extracted)
            result["added_fields"].append(fdef.name)
            missing.remove(fdef.name)

    # AI for remaining missing fields
    if missing:
        try:
            ai, usage = call_gemini(client, model, content_set, text)
            result["tokens"] = usage.as_dict()
            result["cost_usd"] = round(usage.cost(model), 6)
            for fdef in content_set.fields:
                if fdef.name not in missing:
                    continue
                val = getattr(ai, fdef.name)
                if fdef.clean is not None:
                    val = fdef.clean(val)
                # Always write, even [] — marks field as processed so we don't re-run
                updates[fdef.name] = fdef.to_yaml(val)
                result["added_fields"].append(fdef.name)
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e.__cause__ or e)
            return result

    full_meta = reorder_metadata(metadata, updates, meta_keys, content_set.meta_position) if force else None
    if not dry_run:
        write_file(path, had_fm, text, updates, content_set.meta_position, full_metadata=full_meta)
    result["status"] = "dry-run" if dry_run else "updated"
    return result


# ── CLI ───────────────────────────────────────────────────────────────────────

@app.command()
def main(
    content_set_name: str             = typer.Argument(..., help=f"Content set: {', '.join(CONTENT_SET_MAP)}"),
    patterns:  Optional[list[str]]    = typer.Argument(None, help="Glob patterns; relative resolved from ., absolute start with /"),
    model:     str                    = typer.Option("gemini-3-flash-preview", help="Gemini model ID"),
    workers:   int                    = typer.Option(4, "--workers", help="Parallel API workers"),
    dry_run:   bool                   = typer.Option(False, "--dry-run", help="Show changes without writing"),
    force:     bool                   = typer.Option(False, "--force",   help="Re-process all fields via API"),
    fmt:       str                    = typer.Option("auto", "--format",  help="Output: text|json|auto"),
) -> None:
    """Add AI-generated metadata to content files (transcripts, blog posts, etc.)."""
    if content_set_name not in CONTENT_SET_MAP:
        valid = ", ".join(CONTENT_SET_MAP)
        console.print(f"[red]Unknown content set '{content_set_name}'. Valid: {valid}[/red]")
        raise typer.Exit(1)

    content_set = CONTENT_SET_MAP[content_set_name]

    load_dotenv()
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        console.print("[red]GEMINI_API_KEY not found in environment or .env[/red]")
        raise typer.Exit(1)

    use_json = fmt == "json" or (fmt == "auto" and not sys.stdout.isatty())
    files = resolve_files(patterns or [], content_set)
    if not files:
        msg = f"No files matched: {patterns}"
        print(json.dumps({"error": msg}) if use_json else msg)
        raise typer.Exit(1)

    from google import genai  # noqa: PLC0415
    client = genai.Client(api_key=api_key)

    results: list[dict] = []
    total_usage = Usage()

    def on_done(result: dict) -> None:
        results.append(result)
        t = result.get("tokens", {})
        total_usage.add(t.get("prompt", 0), t.get("output", 0))
        with _print_lock:
            if use_json:
                print(json.dumps(result), flush=True)
            else:
                status = result["status"]
                name = result["name"]
                if status == "skipped":
                    console.print(f"[dim]SKIP {name}: {result['skipped_reason']}[/dim]")
                elif status == "error":
                    console.print(f"[red]ERROR {name}: {result.get('error')}[/red]")
                else:
                    tag = "[yellow]DRY-RUN[/yellow]" if dry_run else "[green]UPDATED[/green]"
                    added = result["added_fields"]
                    tok = result["tokens"]
                    cost = result["cost_usd"]
                    console.print(
                        f"{tag} {name} +{added} | "
                        f"[dim]{tok['prompt']}in/{tok['output']}out tok ${cost:.4f}[/dim]"
                    )

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(process_file, path, client, model, dry_run, force, content_set): path
            for path in files
        }
        for future in concurrent.futures.as_completed(futures):
            try:
                on_done(future.result())
            except Exception as e:
                path = futures[future]
                on_done({
                    "file": str(path), "name": path.name, "status": "error",
                    "added_fields": [], "skipped_reason": None,
                    "tokens": {"prompt": 0, "output": 0}, "cost_usd": 0.0,
                    "error": str(e),
                })

    if not use_json:
        n_updated = sum(1 for r in results if r["status"] in ("updated", "dry-run"))
        n_skipped = sum(1 for r in results if r["status"] == "skipped")
        n_errors  = sum(1 for r in results if r["status"] == "error")
        console.print(
            f"\n[bold]Done:[/bold] {n_updated} updated, {n_skipped} skipped, {n_errors} errors"
        )
        pricing = PRICING.get(model, DEFAULT_PRICING)
        console.print(
            f"[bold]Tokens:[/bold] {total_usage.prompt:,} in + {total_usage.output:,} out"
            f" ({total_usage.calls} calls) | "
            f"[bold]Cost:[/bold] ${total_usage.cost(model):.4f} "
            f"[dim](${pricing[0]}/1M in, ${pricing[1]}/1M out)[/dim]"
        )

    raise typer.Exit(1 if any(r["status"] == "error" for r in results) else 0)


def resolve_files(patterns: list[str], content_set: ContentSet) -> list[Path]:
    """Resolve file patterns to a sorted, deduplicated list of paths.

    - No patterns → expand content_set.default_globs against content_set.base_dir
    - Relative pattern (no leading /) → expand against current directory (.)
    - Absolute pattern (starts with /) → use as-is
    """
    if not patterns:
        files: list[Path] = []
        for g in content_set.default_globs:
            files.extend(Path(p) for p in glob_module.glob(
                str(content_set.base_dir / g), recursive=True
            ))
        return sorted(set(files))

    files = []
    for pattern in patterns:
        root = pattern if pattern.startswith("/") else str(Path(".") / pattern)
        files.extend(Path(f) for f in glob_module.glob(root, recursive=True))
    return sorted(set(files))


if __name__ == "__main__":
    app()
