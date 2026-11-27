#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["typer>=0.12"]
# ///
"""Prepare incremental personal-memory evidence and validate proposed claims.

Maintain evidence for editable Markdown memory. No model calls or source writes.
MEMORY.md is authoritative; SQLite is bookkeeping.

Examples:
  memory.py prepare --weekly --limit 20 | jaq .
  memory.py show 'chatgpt||conversation:turn'
  memory.py review proposals.jsonl --apply
  memory.py build
"""
from collections import Counter
import datetime as dt
import hashlib
import json
import os
import platform
import re
import sqlite3
from pathlib import Path

import typer

HOME = Path.home()
INDEX = HOME / "Documents/data/context/context.sqlite"
STATE = HOME / "Documents/data/memory/state.sqlite"
SGT = dt.timezone(dt.timedelta(hours=8))
SOURCES = ("chatgpt", "claude", "mail", "whatsapp", "transcript")
SELECT = """SELECT source,native_id,account,timestamp,title,body,summary,locator,author
  FROM items WHERE source IN ('chatgpt','claude','mail','whatsapp','transcript')
  AND (role='user' OR source='transcript')"""
KINDS = {"decision", "outcome", "experience", "preference", "position", "objective",
         "commitment", "project", "rejection", "lesson"}
AUTHORITIES = {"user_explicit", "user_reported", "inferred", "other_reported"}
SIGNALS = re.compile(r"\b(?:i (?:prefer|decided|chose|tried|learned|found|realized|realised)|"
                     r"fyi|results?:|that worked|didn.t work|no response required|"
                     r"going forward|from now on|we (?:decided|agreed))\b", re.I)
app = typer.Typer(add_completion=False, help=__doc__)
os.umask(0o077)


def day(timestamp: str) -> str:
    """Dates without times already describe the local event day."""
    if not timestamp or len(timestamp) == 10:
        return timestamp
    value = dt.datetime.fromisoformat(timestamp)
    return value.astimezone(SGT).date().isoformat() if value.tzinfo else value.date().isoformat()


def completed_week(today: dt.date) -> tuple[str, str]:
    """Sunday to Saturday SGT; upper bound is the next Sunday, exclusive."""
    until = today - dt.timedelta(days=(today.weekday() + 1) % 7)
    return (until - dt.timedelta(days=7)).isoformat(), until.isoformat()


def digest(row: dict) -> str:
    # Locators and row IDs may move across index rebuilds; evidence meaning may not.
    return hashlib.sha256(json.dumps([row[k] for k in ("timestamp", "title", "body", "summary")],
                                     ensure_ascii=False).encode()).hexdigest()


def source_id(row: dict) -> str:
    return "|".join(row[k] for k in ("source", "account", "native_id"))


def read_index(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    db.execute("BEGIN")
    return db


def open_state(path: Path, dry_run: bool = False) -> sqlite3.Connection:
    if not dry_run and platform.node().casefold().split(".")[0] == "plutonium":
        raise typer.BadParameter("Memory is maintained on Graphene. On Plutonium use read-only commands or --dry-run.")
    if dry_run:
        db = sqlite3.connect(":memory:")
        if path.exists():
            with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as old:
                old.backup(db)
    else:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.executescript("""
      CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS seen (
        id TEXT PRIMARY KEY, hash TEXT NOT NULL, source TEXT NOT NULL,
        native_id TEXT NOT NULL, account TEXT NOT NULL, eligible INTEGER NOT NULL,
        present INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS reviews (
        id TEXT NOT NULL, hash TEXT NOT NULL, claims TEXT NOT NULL,
        PRIMARY KEY(id,hash));
    """)
    return db


def exclusion(row: dict) -> str:
    """Known structural/non-user inputs; keep the raw evidence in context.py."""
    if not row["body"].strip():
        return "empty"
    if (row["source"] == "mail" and row["author"] == "TDS Trading Games <anand@study.iitm.ac.in>"
            and re.fullmatch(r"\d+ things? (?:is|are) waiting for you in TDS trading games", row["title"])):
        return "automated_tds_notification"
    if row["source"] == "whatsapp" and row["author"] not in {"Anand S", "S Anand", "Anand Subramanian", "Anand", "me"}:
        return "whatsapp_attribution_unverified"
    if row["source"] in {"chatgpt", "claude", "whatsapp"}:
        lines = [re.sub(r"^>\s?", "", line.strip()) for line in row["body"].splitlines()]
        if all(not line or line in {"audio_transcription", "real_time_user_audio_video_asset_pointer", "[Audio]"} for line in lines):
            return "media_placeholder"
    return ""


def preview(row: dict) -> str:
    """Bound first-pass input; never use a preview as the only evidence."""
    if row["source"] == "transcript" and row["summary"]:
        return "[Generated summary; verify against transcript]\n" + row["summary"][:2400]
    lines = row["body"].splitlines()
    if row["source"] in {"chatgpt", "claude"} and all(not l.strip() or l.lstrip().startswith(">") for l in lines):
        # Legacy exports wrap the entire user turn in Markdown blockquotes.
        text = "[Legacy quote wrapper; verify speaker and source]\n" + "\n".join(re.sub(r"^\s*> ?", "", l) for l in lines)
    else:
        text = "\n".join(l for l in lines if not l.lstrip().startswith(">"))
    if row["source"] in {"chatgpt", "claude"}:
        def strip_injection(match):
            try:
                value = json.loads(match[1])
            except ValueError:
                return match[0]
            if isinstance(value, dict) and {"start_timestamp", "stop_timestamp"} <= value.keys():
                if value.get("type") in {"injected_prompt_block", "tool_use", "tool_result"}:
                    return ""
            return match[0]
        fence = chr(96) * 3
        text = re.sub(r"(?ms)^[ \t]*" + fence + r"json[ \t]*\n(.*?)^[ \t]*" +
                      fence + r"[ \t]*(?:\n|$)", strip_injection, text)
    if len(text) <= 1600:
        return text
    return text[:1100] + "\n[... omitted; use show ...]\n" + text[-500:]


def evidence(row: dict) -> dict:
    reason = exclusion(row)
    excerpt = "" if reason else preview(row)
    return {k: row[k] for k in ("source", "native_id", "account", "timestamp", "title", "locator", "author")} | {
        "id": source_id(row), "hash": digest(row), "preview": excerpt,
        "text_hash": hashlib.sha256(" ".join(row["body"].split()).encode()).hexdigest(),
        "has_text": bool(row["body"].strip()), "exclusion": reason,
        "attribution": "verify" if row["source"] in {"whatsapp", "transcript"} else "indexed_role",
        "priority": int(bool(SIGNALS.search(excerpt))),
    }


def settings(db: sqlite3.Connection) -> dict:
    return dict(db.execute("SELECT key,value FROM settings"))


def scan(index: sqlite3.Connection, until: str) -> dict:
    rows = {}
    for raw in index.execute(SELECT):
        row = dict(raw)
        event_day = day(row["timestamp"])
        if until and (not event_day or event_day >= until):
            continue
        key = source_id(row)
        if not row["native_id"] or key in rows:
            raise ValueError(f"Missing or duplicate source identity: {key}")
        rows[key] = evidence(row)
    return rows


def find(index: sqlite3.Connection, seen: sqlite3.Row) -> dict | None:
    matches = index.execute(SELECT + " AND source=? AND native_id=? AND account=?",
                            (seen["source"], seen["native_id"], seen["account"])).fetchall()
    if len(matches) > 1:
        raise ValueError(f"Ambiguous source identity: {seen['id']}")
    return dict(matches[0]) if matches else None


@app.callback()
def main(ctx: typer.Context, index: Path = INDEX, state: Path = STATE):
    ctx.obj = (index, state)


@app.command()
def prepare(ctx: typer.Context, since: str = "", until: str = "", limit: int = 100,
            dry_run: bool = False, source: str = "", account: str = "", weekly: bool = False,
            week: str = ""):
    """Queue new/changed evidence; unreviewed items stay pending across runs.

    First run baselines earlier evidence without processing it. An optional
    exclusive local-date cutoff creates a historical replay.
    --weekly prioritizes last completed Sunday–Saturday (SGT), then older pending
    evidence; current-week records remain pending for next time.
    --week YYYY-MM-DD selects exactly one historical Sunday–Saturday.
    """
    index_path, state_path = ctx.obj
    with read_index(index_path) as index, open_state(state_path, dry_run) as db:
        db.execute("BEGIN IMMEDIATE")
        cfg = settings(db)
        if cfg:
            if (since and since != cfg["since"]) or (until and until != cfg["until"]):
                raise typer.BadParameter("Use a separate --state for a different replay window")
            since, until = cfg["since"], cfg["until"]
        elif not since:
            raise typer.BadParameter("Initial prepare requires --since YYYY-MM-DD")
        dt.date.fromisoformat(since)
        if until and dt.date.fromisoformat(until) <= dt.date.fromisoformat(since):
            raise typer.BadParameter("--until must be later than --since")
        if source and source not in SOURCES:
            raise typer.BadParameter(f"Unknown source: {source}")
        if limit < 0:
            raise typer.BadParameter("--limit must be nonnegative")
        if week and (weekly or dt.date.fromisoformat(week).weekday() != 6):
            raise typer.BadParameter("--week must be a Sunday; do not combine with --weekly")
        typer.echo("Scanning source identities and hashes...", err=True)
        rows = scan(index, until)
        old = {r["id"]: r for r in db.execute("SELECT * FROM seen")}
        if not rows:
            raise typer.BadParameter("No eligible source rows; check index coverage")
        if not cfg:
            db.executemany("INSERT INTO settings VALUES (?,?)", [("since", since), ("until", until)])
        changed = 0
        for key, row in rows.items():
            prior = old.get(key)
            is_change = prior is None or prior["hash"] != row["hash"]
            eligible = not row["exclusion"] and ((bool(prior["eligible"]) if prior else False)
                or day(row["timestamp"]) >= since or (bool(cfg) and is_change))
            changed += int(is_change and eligible)
            db.execute("INSERT OR REPLACE INTO seen VALUES (?,?,?,?,?,?,1)",
                       (key, row["hash"], row["source"], row["native_id"], row["account"], int(eligible)))
        # Disappearance is not deletion. The next successful snapshot may restore it.
        missing = set(old) - set(rows)
        db.executemany("UPDATE seen SET present=0 WHERE id=?", [(k,) for k in missing])
        pending = [rows[r["id"]] for r in db.execute("""
          SELECT s.id FROM seen s LEFT JOIN reviews r ON s.id=r.id AND s.hash=r.hash
          WHERE s.eligible AND s.present AND r.id IS NULL
        """)]
        pending.sort(key=lambda r: (-r["priority"], r["timestamp"], r["id"]))
        excluded = Counter(r["exclusion"] for r in rows.values()
                           if r["exclusion"] and day(r["timestamp"]) >= since)
        typer.echo(f"Excluded in reporting window: {dict(excluded)}", err=True)
        typer.echo(f"{len(rows)} scanned; {changed} new/changed eligible; "
                   f"{len(pending)} pending; {len(missing)} unavailable", err=True)
        pending = [r for r in pending if (not source or r["source"] == source)
                   and (not account or r["account"] == account)]
        if week:
            end = (dt.date.fromisoformat(week) + dt.timedelta(days=7)).isoformat()
            pending = [r for r in pending if week <= day(r["timestamp"]) < end]
            typer.echo(f"Week {week} to {end} (exclusive): {len(pending)} pending", err=True)
        elif weekly:
            start, end = completed_week(dt.datetime.now(SGT).date())
            pending = [r for r in pending if day(r["timestamp"]) < end]
            pending.sort(key=lambda r: (day(r["timestamp"]) < start, -r["priority"], r["timestamp"], r["id"]))
            recent = sum(day(r["timestamp"]) >= start for r in pending)
            typer.echo(f"Week {start} to {end} (exclusive): {recent} pending; "
                       f"{len(pending)-recent} earlier pending", err=True)
        duplicates = Counter((r["source"], r["account"], r["text_hash"]) for r in pending)
        for row in pending[:limit or None]:
            row["same_text_pending"] = duplicates[row["source"], row["account"], row["text_hash"]]
            typer.echo(json.dumps(row, ensure_ascii=False))


@app.command()
def show(ctx: typer.Context, id: str):
    """Read original indexed evidence; use its locator for authoritative verification."""
    index_path, state_path = ctx.obj
    with read_index(index_path) as index, open_state(state_path, True) as db:
        seen = db.execute("SELECT * FROM seen WHERE id=?", (id,)).fetchone()
        row = find(index, seen) if seen else None
        if not row:
            raise typer.BadParameter("Evidence not found; run prepare")
        typer.echo(json.dumps(evidence(row) | {"body": row["body"]}, ensure_ascii=False))


@app.command()
def review(ctx: typer.Context, proposals: Path, apply: bool = False, extractor: str = "manual"):
    """Validate JSONL proposals (empty claims means reviewed/skipped). Default dry run."""
    index_path, state_path = ctx.obj
    with read_index(index_path) as index, open_state(state_path, not apply) as db:
        db.execute("BEGIN IMMEDIATE")
        seen_ids = set()
        count = 0
        for line in proposals.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            key, version, claims = item["id"], item["hash"], item["claims"]
            reason = item.get("reason", "")
            if not claims and (not isinstance(reason, str) or not reason.strip()):
                raise ValueError(f"Skipped evidence requires a reason: {key}")
            if key in seen_ids or not isinstance(claims, list):
                raise ValueError(f"Duplicate proposal or invalid claims: {key}")
            seen_ids.add(key)
            seen = db.execute("SELECT * FROM seen WHERE id=?", (key,)).fetchone()
            row = find(index, seen) if seen and seen["eligible"] and seen["present"] else None
            if not row or exclusion(row) or seen["hash"] != version or digest(row) != version:
                raise ValueError(f"Stale or unqueued evidence: {key}")
            for claim in claims:
                if set(claim) != {"kind", "scope", "claim", "quote", "authority"}:
                    raise ValueError(f"Invalid claim fields: {key}")
                if not all(isinstance(v, str) and v.strip() for v in claim.values()):
                    raise ValueError(f"Empty/non-text claim fields: {key}")
                if (claim["kind"] not in KINDS or claim["authority"] not in AUTHORITIES
                        or claim["quote"] not in row["body"]):
                    raise ValueError(f"Unsupported kind or quote absent from body: {key}")
            db.execute("INSERT OR REPLACE INTO reviews VALUES (?,?,?)",
                       (key, version, json.dumps({"claims": claims, "reason": reason, "extractor": extractor}, ensure_ascii=False)))
            count += len(claims)
        typer.echo(f"{len(seen_ids)} reviewed evidence items; {count} proposed claims; "
                   + ("saved" if apply else "dry run"))


def active_claims(index: sqlite3.Connection, db: sqlite3.Connection):
    """Yield current, unapproved claims with IDs bound to exact evidence versions."""
    for seen in db.execute("""SELECT s.*,r.claims FROM seen s JOIN reviews r
         ON s.id=r.id AND s.hash=r.hash WHERE s.present ORDER BY s.id"""):
        row = find(index, seen)
        if not row or exclusion(row) or digest(row) != seen["hash"]:
            continue
        for claim in json.loads(seen["claims"])["claims"]:
            key = hashlib.sha256(json.dumps([seen["id"], seen["hash"], claim],
                                 sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            yield claim | {"claim_id": key, "evidence_id": seen["id"],
                           "hash": seen["hash"], "timestamp": row["timestamp"],
                           "locator": row["locator"]}


@app.command()
def build(ctx: typer.Context, format: str = "text", unrouted: Path | None = None):
    """Render current unapproved proposals; stale evidence is excluded live."""
    index_path, state_path = ctx.obj
    if format not in {"text", "jsonl"}:
        raise typer.BadParameter("Use text or jsonl")
    with read_index(index_path) as index, open_state(state_path, True) as db:
        if format == "text":
            typer.echo("# Extracted evidence — Markdown memory is authoritative\n")
        claims = list(active_claims(index, db))
        if unrouted is not None:
            routed = {json.loads(line)["claim_id"] for line in unrouted.read_text(encoding="utf-8").splitlines() if line.strip()}
            stale = routed - {c["claim_id"] for c in claims}
            typer.echo(f"{len(stale)} previously routed claims now stale; reconcile before publishing", err=True)
            claims = [c for c in claims if c["claim_id"] not in routed]
        for claim in claims:
            if format == "jsonl":
                typer.echo(json.dumps(claim, ensure_ascii=False))
            else:
                typer.echo(f"- [{claim['kind']}; {claim['scope']}; {claim['authority']}] {claim['claim']} "
                           f"({claim['timestamp']}; {claim['locator']})")


@app.command()
def plan(ctx: typer.Context, routes: Path):
    """Validate and group proposed dispositions. Never edit or publish target files."""
    index_path, state_path = ctx.obj
    with read_index(index_path) as index, open_state(state_path, True) as db:
        claims = {c["claim_id"]: c for c in active_claims(index, db)}
        groups = {}
        assigned = set()
        for line in routes.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if set(r) != {"claim_id", "action", "target", "reason"} or not all(
                    isinstance(v, str) and v.strip() for v in r.values()):
                raise ValueError("Route requires nonempty claim_id, action, target, reason")
            key, action, target = r["claim_id"], r["action"], r["target"]
            if key not in claims or key in assigned:
                raise ValueError(f"Stale, unknown or duplicate claim route: {key}")
            if action not in {"link", "update", "merge", "new", "hold", "drop"}:
                raise ValueError(f"Unknown route action: {action}")
            if action in {"link", "update"} and not Path(target.partition("#L")[0]).expanduser().is_file():
                raise ValueError(f"Existing target not found: {target}")
            assigned.add(key)
            groups.setdefault((action, target), []).append((claims[key], r["reason"]))
        typer.echo("# Consolidation plan — unapproved; no target writes\n")
        typer.echo(f"{len(assigned)} routed claims, {len(groups)} groups, "
                   f"{len(claims) - len(assigned)} unrouted claims.\n")
        for (action, target), members in sorted(groups.items()):
            typer.echo(f"## {action}: {target}\n")
            for claim, reason in members:
                typer.echo(f"- {claim['claim']} ({claim['timestamp']}; {claim['locator']}) — {reason}")
            typer.echo("")


@app.command()
def status(ctx: typer.Context):
    """Report queue state and index coverage (never implies source completeness)."""
    index_path, state_path = ctx.obj
    with read_index(index_path) as index, open_state(state_path, True) as db:
        counts = db.execute("""SELECT count(*) AS total, coalesce(sum(NOT s.present),0) AS missing,
          coalesce(sum(s.eligible AND s.present AND r.id IS NULL),0) AS pending,
          coalesce(sum(s.eligible AND s.present AND r.id IS NOT NULL),0) AS reviewed
          FROM seen s LEFT JOIN reviews r ON s.id=r.id AND s.hash=r.hash""").fetchone()
        coverage = [dict(r) for r in index.execute(
            "SELECT source,row_count,latest_item_time,warning FROM source_status") if r["source"] in SOURCES]
        invalidated = db.execute("""SELECT count(*) FROM reviews r LEFT JOIN seen s
          ON s.id=r.id AND s.hash=r.hash AND s.present WHERE s.id IS NULL""").fetchone()[0]
        typer.echo(json.dumps(dict(counts) | {"invalidated_review_versions": invalidated,
             "window": settings(db), "coverage": coverage}, indent=2))


if __name__ == "__main__":
    app()
