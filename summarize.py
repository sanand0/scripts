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
import hashlib
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass, field
from functools import lru_cache
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
    "gemini-3.5-flash":       (1.50,  9.00),
    "gemini-3.1-flash-lite":  (0.25,  1.50),
    "gemini-3.1-pro-preview": (2.00, 12.00),
    "gemini-3-flash-preview": (0.075, 0.30),
    "gemini-3-pro-preview":   (1.25,  5.00),
    "gemini-2.5-flash":       (0.075, 0.30),
    "gemini-2.5-pro":         (1.25,  5.00),
    "gemini-2.0-flash":       (0.075, 0.30),
}
# Default price if user specifies a model not in PRICING dict
DEFAULT_PRICING = (1.50,  9.00)


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
    exclude_names: list[str] = field(default_factory=list)  # basenames to skip (e.g. SKILL.md)
    meta_position: str = "before"  # "before": meta keys first; "after": meta keys last
    skip_if: Callable[[str], str | None] | None = None
    prompt_builder: Callable[[str, list[FieldDef] | None], str] | None = None

    @property
    def meta_keys(self) -> list[str]:
        return [f.name for f in self.fields]

    def prompt_for(self, text: str, fields: list["FieldDef"] | None = None) -> str:
        return self.prompt_builder(text, fields) if self.prompt_builder else self.prompt


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


def without_frontmatter_fields(text: str, names: set[str]) -> str:
    """Remove fields being regenerated so old AI output cannot anchor the new call."""
    metadata, body, had_fm = parse_frontmatter(text)
    if not had_fm:
        return text
    for name in names:
        metadata.pop(name, None)
    return f"---\n{dump_metadata(metadata)}---\n\n{body}"


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


def clean_ideas(ideas: list) -> list[str]:
    """Strip a leading '#IDEA' tag / stray quotes the model may echo from the notes."""
    out = []
    for raw in ideas:
        s = re.sub(r"^\s*#idea[:\s-]*", "", str(raw).strip(), flags=re.IGNORECASE).strip(" '\"")
        if s:
            out.append(s)
    return out


def clean_what_i_missed(items: list) -> list[str]:
    """Normalize the deliberately small reason taxonomy used by what-i-missed."""
    aliases = {
        "topic": "topic shift",
        "focus": "task focus",
        "solution": "premature solution mode",
        "time": "time pressure",
        "pace": "pace",
        "dominance": "conversational dominance",
    }
    out = []
    for raw in items:
        item = str(raw).strip()
        match = re.search(r"(?i)(Possible reason:\s*)([^.]+)(\.?)$", item)
        if match:
            reason = match.group(2).strip().lower()
            allowed = next((value for value in aliases.values() if value in reason), None)
            if allowed is None:
                allowed = next((value for key, value in aliases.items() if key in reason), "task focus")
            item = item[:match.start()] + match.group(1) + allowed + "."
        if item:
            out.append(item)
    return out


# ── Blog tag helpers ──────────────────────────────────────────────────────────

BLOG_TAGS_PATH = Path("/home/sanand/code/blog/metadata-tags.yml")
BLOG_PROPOSALS_PATH = BLOG_TAGS_PATH.with_name("metadata-tag-proposals.yml")
TAG_TOKEN_RE = re.compile(r"[a-z0-9]+")
MAX_BLOG_TAG_CANDIDATES = 80
COMMON_BLOG_TAGS = 25


def _tag_slug(value: str) -> str:
    text = str(value).strip().lower()
    text = text.replace("&", " and ").replace("+", " plus ").replace("'", "")
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    aliases = {
        "large-language-model": "llms",
        "large-language-models": "llms",
        "llm": "llms",
        "visualisation": "data-visualization",
        "visualization": "data-visualization",
        "data-visualisation": "data-visualization",
        "dataviz": "data-visualization",
        "books": "book",
        "genai": "generative-ai",
        "gen-ai": "generative-ai",
    }
    return aliases.get(text, text)


@lru_cache(maxsize=1)
def blog_tag_vocabulary() -> tuple[dict[str, dict], dict[str, str]]:
    data = make_yaml().load(BLOG_TAGS_PATH.read_text(encoding="utf-8")) or {}
    tags = data.get("tags") or {}
    alias_map: dict[str, str] = {}
    for tag, details in tags.items():
        alias_map[_tag_slug(tag)] = tag
        for alias in details.get("aliases") or []:
            alias_map[_tag_slug(str(alias))] = tag
    return tags, alias_map


def _tokens(text: str) -> set[str]:
    return set(TAG_TOKEN_RE.findall(text.lower()))


def blog_tag_candidates(text: str, limit: int = MAX_BLOG_TAG_CANDIDATES) -> list[str]:
    tags, _ = blog_tag_vocabulary()
    doc_tokens = _tokens(text)
    scored: list[tuple[int, int, str]] = []
    for tag, details in tags.items():
        tag_text = " ".join([tag, details.get("description") or "", *[str(a) for a in details.get("aliases") or []]])
        overlap = len(doc_tokens & _tokens(tag_text))
        count = int(details.get("count") or 0)
        if overlap:
            scored.append((overlap, count, tag))
    candidates = [tag for _, _, tag in sorted(scored, key=lambda item: (-item[0], -item[1], item[2]))[:limit]]
    for tag in list(tags)[:COMMON_BLOG_TAGS]:
        if tag not in candidates:
            candidates.append(tag)
    return candidates[:limit]


def blog_prompt(text: str, fields: list[FieldDef] | None = None) -> str:
    field_names = {field.name for field in (fields or [])}
    tags, _ = blog_tag_vocabulary()
    candidates = blog_tag_candidates(text)
    tag_lines = "\n".join(
        f"- {tag}: {tags[tag].get('description', '').removeprefix('Posts about ').rstrip('.')}"
        for tag in candidates
    )
    if field_names == {"tags"}:
        return (
            "Generate only canonical tags for this blog post's metadata.\n\n"
            "Choose 3-8 slugs from this compact candidate list. Strongly prefer these existing tags. "
            "If nothing fits an important topic, include it as proposed:new-tag; the script will flag it for review "
            "and will not save it as a canonical tag.\n\n"
            f"Candidate canonical tags:\n{tag_lines}\n\n"
        )
    if field_names == {"description"}:
        return (
            "Generate only a description for this blog post's metadata.\n\n"
            "Use first person (\"I\", never \"the author\") for personal posts. "
            "Use imperative or neutral voice only for instructional or concept posts. "
            "Be direct and conversational, not formal.\n\n"
        )
    return (
        "Generate a description and canonical tags for this blog post's metadata.\n\n"
        "Use first person (\"I\", never \"the author\") for personal posts. "
        "Use imperative or neutral voice only for instructional or concept posts. "
        "Be direct and conversational, not formal.\n\n"
        "For tags, choose 3-8 slugs from this compact candidate list. Strongly prefer these existing tags. "
        "If nothing fits an important topic, include it as proposed:new-tag; the script will flag it for review "
        "and will not save it as a canonical tag.\n\n"
        f"Candidate canonical tags:\n{tag_lines}\n\n"
    )


def split_blog_tags(values: Any) -> tuple[list[str], list[str]]:
    """Return canonical tags and normalized proposals without mixing the two."""
    _, aliases = blog_tag_vocabulary()
    tags: list[str] = []
    proposals: set[str] = set()
    for raw in values or []:
        item = str(raw).strip()
        if not item:
            continue
        lowered = item.lower()
        if lowered.startswith("proposed:"):
            if proposal := _tag_slug(item.split(":", 1)[1]):
                proposals.add(proposal)
            continue
        tag = aliases.get(_tag_slug(item))
        if tag and tag not in tags:
            tags.append(tag)
        elif item:
            if proposal := _tag_slug(item):
                proposals.add(proposal)
    return tags, sorted(proposals)


def clean_blog_tags(values: Any) -> list[str]:
    tags, proposals = split_blog_tags(values)
    if proposals:
        console.print(f"[yellow]Proposed blog tags retained for review: {proposals}[/yellow]")
    return tags


def _atomic_yaml_write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            make_yaml().dump(data, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def merge_blog_tag_proposals(path: Path, evidence: list[dict]) -> None:
    """Reconcile processed sources into the proposal ledger with one atomic write."""
    existing = make_yaml().load(path.read_text(encoding="utf-8")) if path.exists() else {}
    proposals = (existing or {}).get("proposals") or {}
    processed_sources = {item["source"] for item in evidence}
    merged: dict[str, dict[str, dict[str, str]]] = {}
    for proposal, details in proposals.items():
        sources = {
            source: dict(source_details)
            for source, source_details in (details.get("sources") or {}).items()
            if source not in processed_sources
        }
        if sources:
            merged[str(proposal)] = {"sources": sources}
    for item in evidence:
        source_details = {"content_hash": item["content_hash"]}
        for proposal in sorted(set(item.get("proposals") or [])):
            merged.setdefault(proposal, {"sources": {}})["sources"][item["source"]] = source_details
    normalized = {
        proposal: {"sources": dict(sorted(details["sources"].items()))}
        for proposal, details in sorted(merged.items())
    }
    _atomic_yaml_write(path, {"version": 1, "proposals": normalized})


def blog_source_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


# ── Shared helpers ─────────────────────────────────────────────────────────────

def is_unprocessed(val: Any) -> bool:
    """Needs AI if None/missing/empty-string. Empty list [] = processed-but-empty."""
    return val is None or (isinstance(val, str) and not val.strip())


def count_content_lines(text: str) -> int:
    return sum(1 for ln in text.splitlines() if (s := ln.strip()) and not s.startswith("#"))


MIN_TRANSCRIPT_CHARS = 200


def _transcript_skip(body: str) -> str | None:
    """Skip if ## Transcript section is missing or under MIN_TRANSCRIPT_CHARS chars."""
    m = re.search(r'^## Transcript\s*$', body, re.MULTILINE)
    if not m or len(body[m.end():].strip()) < MIN_TRANSCRIPT_CHARS:
        return "empty transcript"
    return None


# ── Content set registry ───────────────────────────────────────────────────────
# To add a new content set: define FieldDefs and append a ContentSet below.

CONTENT_SETS: list[ContentSet] = [
    ContentSet(
        name="transcript",
        base_dir=Path("/home/sanand/Dropbox/notes/transcripts"),
        prompt=(
            "Analyze this meeting transcript and extract only the requested metadata fields. "
            "Use only transcript evidence. Treat a leading YYYY-MM-DD in the title as the meeting date. "
            "Be conservative: false positives are worse than omissions. Never invent dates, channels, recipients, "
            "cc lists, deliverables, commitments, workflow details, motives, or emotional states. When evidence is "
            "insufficient, omit the detail. Before output, silently falsify every item against later transcript evidence.\n\n"
            "For 'people': include only clearly named speakers — no placeholders.\n"
            "For 'ideas': capture forward-looking sparks worth revisiting later — business or market "
            "opportunities, product/venture concepts, experiments to try, provocative \"what if\" questions, "
            "go-to-market or recruiting tactics, tooling ideas, and reusable principles. Include BOTH ideas "
            "explicitly raised in the conversation AND fresh ones that emerge from its context. Lines the "
            "note-taker already tagged with \"#IDEA\" are exactly this kind of spark — always carry those "
            "forward (but drop the literal \"#IDEA\" tag from the text). Write the way the note-taker does: "
            "terse, concrete, ~6-15 words, plain conversational English. A sentence fragment or a bare "
            "question is good. NO preamble verbs like \"Leverage/Utilize/Implement\", no buzzwords, no "
            "phrases-in-quotes, no two-clause explanations. Ideas are generative, not a recap of what was "
            "said (that's 'summary') and not assigned to-dos (those are 'actions').\n\n"
        ),
        skip_if=_transcript_skip,
        fields=[
            FieldDef(
                name="summary",
                description="3-8 who-said-what summaries of the most important items, one sentence each.",
                pydantic_type=list[str],
                to_yaml=list,
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
                description=(
                    "ALL agreed or clearly assigned actions. Silently build a final commitment ledger: for each "
                    "owner and outcome, scan the entire transcript and keep only the latest accepted instruction. "
                    "A later explicit direction overrides an earlier one, especially phrases such as 'instead' or "
                    "'no choice but', or a changed model, approach, or plan. Merge due date, artifact, recipient or "
                    "handoff, channel, escalation, and completion condition only when stated. Preserve explicit scope "
                    "such as both, each, all, and same. Drop completed-during-call work unless follow-up remains, "
                    "unaccepted suggestions, optional or conditional plans, exploratory ideas, duplicates, and "
                    "superseded actions. Format each as 'Owner: By D Mon YYYY. Specific observable action or "
                    "handoff.' Omit the date and any other unsupported detail. Resolve relative dates from the meeting "
                    "date, never the script run date. Empty list if none."
                ),
                pydantic_type=list[str],
                to_yaml=list,
            ),
            FieldDef(
                name="what-i-missed",
                description=(
                    "List the highest-leverage moments where I (Anand) missed or under-reacted to a “bid” "
                    "(request, concern, constraint, opportunity, or emotional signal) from others. "
                    "Read between the lines. Consider what went unsaid. Mentally list, pick the top. "
                    "For each moment, concisely include "
                    "(a) the exact quote, fragment or a close paraphrase of what they said, "
                    "(b) the follow-up question or move I _should_ have made in the moment, and "
                    "(c) why I might have missed it (cognitive, bias, interaction, time pressure, etc.)."
                    "Empty list if none."
                ),
                pydantic_type=list[str],
                to_yaml=list,
                clean=clean_what_i_missed,
            ),
            FieldDef(
                name="ideas",
                description=(
                    "3-10 forward-looking sparks worth revisiting — opportunities, product/venture concepts, "
                    "experiments to try, provocative \"what if\" questions, go-to-market/recruiting tactics, "
                    "tooling ideas, or reusable principles. Capture BOTH ideas explicitly raised (including any "
                    "lines tagged \"#IDEA\", but omit that literal tag) AND fresh ones that emerge from the "
                    "discussion. Each a terse, concrete one-liner of ~6-15 words in plain conversational English; "
                    "a fragment or a bare question is fine. No \"Leverage/Utilize/Implement\" preambles, no "
                    "buzzwords, no quoted phrases. Generative sparks, not a recap and not to-dos. Empty list if none."
                ),
                pydantic_type=list[str],
                to_yaml=list,
                clean=clean_ideas,
            ),
        ],
    ),
    ContentSet(
        name="blog",
        base_dir=Path("/home/sanand/code/blog"),
        prompt="",
        prompt_builder=blog_prompt,
        fields=[
            FieldDef(
                name="description",
                description=(
                    "20-40 word main point, preferably the most USEFUL takeaway or action item(s). "
                    "Prefer concrete ideas over framing. A focused subset and examples beat vague completeness. "
                    "Include distinctive methods, domains, tools, or concepts when central."
                ),
                pydantic_type=str,
                to_yaml=str,
            ),
            FieldDef(
                name="tags",
                description=(
                    "3-8 canonical tag slugs from the supplied candidate list. "
                    "Use proposed:new-tag only when no canonical tag fits an important topic."
                ),
                pydantic_type=list[str],
                to_yaml=flow_list,
                clean=clean_blog_tags,
            ),
        ],
        default_globs=["posts/**/*.md", "pages/**/*.md"],
        exclude_names=["SKILL.md"],
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
def call_gemini(client, model: str, content_set: ContentSet, text: str, fields: list[FieldDef]):
    from google.genai import types  # noqa: PLC0415

    ResponseModel = create_model(
        "ResponseModel",
        **{f.name: (f.pydantic_type, PydanticField(description=f.description))
           for f in fields},
    )
    response = client.models.generate_content(
        model=model,
        contents=(
            content_set.prompt_for(text, fields)
            + without_frontmatter_fields(text, {field.name for field in fields})
        ),
        config=types.GenerateContentConfig(
            temperature=0,
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
    path: Path, client, model: str, dry_run: bool, force: bool, content_set: ContentSet,
    selected_fields: set[str] | None = None,
) -> dict:
    result: dict = {
        "file": str(path),
        "name": path.name,
        "status": "skipped",
        "added_fields": [],
        "skipped_reason": None,
        "tokens": {"prompt": 0, "output": 0},
        "cost_usd": 0.0,
        "proposals": [],
    }

    text = path.read_text(encoding="utf-8")
    metadata, body, had_fm = parse_frontmatter(text)
    meta_keys = content_set.meta_keys

    eligible_keys = [k for k in meta_keys if selected_fields is None or k in selected_fields]
    missing = [k for k in eligible_keys if force or is_unprocessed(metadata.get(k))]
    if not missing:
        result["skipped_reason"] = "all fields present"
        return result

    if count_content_lines(text) < MIN_CONTENT_LINES:
        result["skipped_reason"] = "trivial content"
        return result

    if content_set.skip_if and (reason := content_set.skip_if(body)):
        result["skipped_reason"] = reason
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
            missing_fields = [fdef for fdef in content_set.fields if fdef.name in missing]
            ai, usage = call_gemini(client, model, content_set, text, missing_fields)
            for fdef in content_set.fields:
                if fdef.name not in missing:
                    continue
                val = getattr(ai, fdef.name)
                if content_set.name == "blog" and fdef.name == "tags":
                    val, result["proposals"] = split_blog_tags(val)
                elif fdef.clean is not None:
                    val = fdef.clean(val)
                # Always write, even [] — marks field as processed so we don't re-run
                updates[fdef.name] = fdef.to_yaml(val)
                result["added_fields"].append(fdef.name)
            result["tokens"] = usage.as_dict()
            result["cost_usd"] = round(usage.cost(model), 6)
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e.__cause__ or e)
            return result

    full_meta = reorder_metadata(metadata, updates, meta_keys, content_set.meta_position) if force else None
    if not dry_run:
        write_file(path, had_fm, text, updates, content_set.meta_position, full_metadata=full_meta)
        if content_set.name == "blog":
            result["source"] = blog_source_path(path, content_set.base_dir)
            result["content_hash"] = hashlib.sha256(path.read_bytes()).hexdigest()
    result["status"] = "dry-run" if dry_run else "updated"
    return result


# ── CLI ───────────────────────────────────────────────────────────────────────

@app.command()
def main(
    content_set_name: str             = typer.Argument(..., help=f"Content set: {', '.join(CONTENT_SET_MAP)}"),
    patterns:  Optional[list[str]]    = typer.Argument(None, help="Glob patterns; relative resolved from ., absolute start with /"),
    model:     str                    = typer.Option("gemini-3.5-flash", help="Gemini model ID"),
    workers:   int                    = typer.Option(4, "--workers", help="Parallel API workers"),
    dry_run:   bool                   = typer.Option(False, "--dry-run",   help="Show changes without writing"),
    force:     bool                   = typer.Option(False, "--force",    help="Re-process all fields via API"),
    fmt:       str                    = typer.Option("auto", "--format",   help="Output: text|json|auto"),
    verbose:   bool                   = typer.Option(False, "--verbose", "-v", help="Show skipped files"),
    fields:    Optional[str]          = typer.Option(None, "--fields", help="Comma-separated fields to process"),
) -> None:
    """Add AI-generated metadata to content files (transcripts, blog posts, etc.)."""
    if content_set_name not in CONTENT_SET_MAP:
        valid = ", ".join(CONTENT_SET_MAP)
        console.print(f"[red]Unknown content set '{content_set_name}'. Valid: {valid}[/red]")
        raise typer.Exit(1)

    content_set = CONTENT_SET_MAP[content_set_name]
    selected_fields = None
    if fields:
        requested = {name.strip() for name in fields.split(",") if name.strip()}
        unknown = requested - set(content_set.meta_keys)
        if unknown:
            console.print(f"[red]Unknown fields: {', '.join(sorted(unknown))}[/red]")
            raise typer.Exit(1)
        selected_fields = requested

    load_dotenv()
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        console.print("[red]GEMINI_API_KEY not found in environment or .env[/red]")
        raise typer.Exit(1)

    quiet = os.environ.get("DAILY_ACTIVITIES_QUIET") == "1"
    use_json = fmt == "json" or (fmt == "auto" and not quiet and not sys.stdout.isatty())
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
        total_usage.prompt += t.get("prompt", 0)
        total_usage.output += t.get("output", 0)
        total_usage.calls += t.get("calls", 0)
        with _print_lock:
            if use_json:
                print(json.dumps(result), flush=True)
            else:
                status = result["status"]
                name = result["name"]
                if status == "skipped":
                    if verbose:
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
            pool.submit(
                process_file, path, client, model, dry_run, force, content_set, selected_fields
            ): path
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

    if content_set.name == "blog" and not dry_run:
        evidence = [
            result for result in results
            if result["status"] == "updated" and "content_hash" in result
        ]
        if evidence:
            merge_blog_tag_proposals(BLOG_PROPOSALS_PATH, evidence)

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
    else:
        files = []
        for pattern in patterns:
            root = pattern if pattern.startswith("/") else str(Path(".") / pattern)
            files.extend(Path(f) for f in glob_module.glob(root, recursive=True))

    if content_set.exclude_names:
        excluded = set(content_set.exclude_names)
        files = [f for f in files if f.name not in excluded]
    return sorted(set(files), reverse=True)


if __name__ == "__main__":
    app()
