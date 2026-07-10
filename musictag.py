#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["mutagen", "typer"]
# ///

"""Dump, apply, check, and clean MP3 tags using musicdump.csv as the record.

Examples:
  musictag.py dump
  musictag.py fix "Velai Illa Pattadhaari.What A Karavaad.mp3"
  musictag.py fix --write --genre Tamil --year 2014 *.mp3
  musictag.py check | moor
"""

from __future__ import annotations

import csv
import json as jsonlib
import os
import re
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

import typer
from mutagen import File
from mutagen.id3 import ID3, ID3NoHeaderError, Encoding, TALB, TCOM, TCON, TDRC, TEXT, TIT2, TOLY, TPE1, TRCK, TXXX, UFID

app = typer.Typer(add_completion=False, help=__doc__)

TAG_FIELDS = [
    "TCON", "TDRC", "TALB", "TIT2", "TCOM", "TPE1", "TRCK", "TEXT",
    "TXXX:MusicBrainz Album Id",
    "UFID:http://musicbrainz.org",
    "TXXX:WIKIPEDIA_PAGEID",
]
FIELDS = ["filename"] + TAG_FIELDS[:8] + ["length"] + TAG_FIELDS[8:]
SITES = ["MassTamilan", "StarMusiQ", "VmusiQ", "SenSongs", "IsaiKadal", "TamilWire", "NaaSongs", "Pagalworld", "SongsPk", "FriendsTamil"]
MANAGED = set(TAG_FIELDS)
MUSIC_CSV = Path("~/Music/musicdump.csv").expanduser()
SITE_RE = re.compile(r"\s+-\s+(?:" + "|".join(map(re.escape, SITES)) + r")(?:\.(?:com|in|net|org))?\s*$", re.I)
YEAR_RE = re.compile(r"^\d{4}$")
TEXT_FRAMES = {"TCON": TCON, "TDRC": TDRC, "TALB": TALB, "TIT2": TIT2, "TCOM": TCOM, "TPE1": TPE1, "TRCK": TRCK, "TEXT": TEXT, "TOLY": TOLY}
FALLBACK = {"TCON": ["©gen"], "TDRC": ["©day"], "TALB": ["©alb"], "TIT2": ["©nam"], "TCOM": ["©wrt"], "TPE1": ["©ART"], "TRCK": ["trkn"]}
STALE_KEYS = {
    "TXXX:MusicBrainz Album Artist Id",
    "TXXX:MusicBrainz Album Release Country",
    "TXXX:MusicBrainz Artist Id",
    "TXXX:MusicBrainz Release Group Id",
    "TXXX:MusicBrainz Track Id",
}

def get_tag(audio: Any, key: str) -> str:
    for item in [key] + FALLBACK.get(key, []):
        if item not in audio:
            continue
        val = audio[item]
        if hasattr(val, "data"):
            return val.data.decode("utf-8", errors="replace")
        if isinstance(val, list):
            return str(val[0])
        return str(val)
    return ""

def current_value(tags: ID3, key: str) -> str:
    if key not in tags:
        return ""
    val = tags[key]
    if hasattr(val, "data"):
        return val.data.decode("utf-8", errors="replace")
    if hasattr(val, "text"):
        return str(val.text[0]) if isinstance(val.text, list) and val.text else str(val.text or "")
    return str(val)

def frame_summary(tags: ID3, key: str) -> str:
    if key not in MANAGED and not preserved_frame(tags, key) and not hasattr(tags[key], "text") and not key.startswith("W"):
        return "<present>"
    val = current_value(tags, key)
    if val:
        return val if len(val) <= 120 else val[:117] + "..."
    return "<present>"

def write_tag(tags: ID3, key: str, value: str) -> None:
    if key.startswith("TXXX:"):
        desc = key[5:]
        tags.delall(f"TXXX:{desc}")
        tags.add(TXXX(encoding=Encoding.UTF8, desc=desc, text=[value]))
    elif key.startswith("UFID:"):
        owner = key[5:]
        tags.delall(f"UFID:{owner}")
        tags.add(UFID(owner=owner, data=value.encode("utf-8")))
    elif key in TEXT_FRAMES:
        tags.delall(key)
        tags.add(TEXT_FRAMES[key](encoding=Encoding.UTF8, text=[value]))

def read_id3(path: Path) -> ID3:
    try:
        return ID3(path)
    except ID3NoHeaderError:
        return ID3()

def save_preserve_mtime(tags: ID3, path: Path) -> None:
    stat = path.stat()
    tags.save(path, v2_version=3)
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))

def strip_site_suffix(value: str) -> str:
    prev = value.strip()
    while True:
        new = SITE_RE.sub("", prev).strip()
        if new == prev:
            return new
        prev = new

def value_has_site_spam(value: str) -> bool:
    return any(site.lower() in value.lower() for site in SITES)

def preserved_frame(tags: ID3, key: str) -> bool:
    value = current_value(tags, key)
    return key.startswith("POPM") or (key.startswith("USLT") and len(value) > 200 and not value_has_site_spam(value))

def filename_album_title(path: Path) -> tuple[str, str]:
    stem = path.stem
    if "." not in stem:
        return stem, ""
    return tuple(stem.split(".", 1))  # type: ignore[return-value]

def read_rows(csv_path: Path = MUSIC_CSV) -> list[dict[str, str]]:
    if not csv_path.exists():
        return []
    with csv_path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def write_rows(rows: list[dict[str, str]], csv_path: Path = MUSIC_CSV) -> None:
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, FIELDS)
        writer.writeheader()
        writer.writerows(rows)

def row_for(path: Path, tags: ID3) -> dict[str, str]:
    row = {"filename": path.name, "length": ""}
    audio = File(path)
    if audio and getattr(audio, "info", None):
        row["length"] = f"{audio.info.length:.1f}"
    row.update({key: current_value(tags, key) for key in TAG_FIELDS})
    return row

def update_csv_row(path: Path, tags: ID3, csv_path: Path = MUSIC_CSV) -> None:
    rows = read_rows(csv_path)
    row = row_for(path, tags)
    for i, old in enumerate(rows):
        if old.get("filename") == path.name:
            rows[i] = row
            break
    else:
        rows.append(row)
    write_rows(rows, csv_path)

def row_album(row: dict[str, str]) -> str:
    return filename_album_title(Path(row.get("filename", "")))[0]

def album_vote(rows: list[dict[str, str]], album: str, key: str, verbose: bool = True) -> str:
    values = [strip_site_suffix(row.get(key, "")) for row in rows if row_album(row) == album and row.get(key)]
    counts = Counter(v for v in values if v)
    if not counts:
        return ""
    if verbose and (len(counts) > 1 or list(counts.values()).count(counts.most_common(1)[0][1]) > 1):
        typer.echo(f"{album} {key} votes: {dict(counts)}", err=True)
    return counts.most_common(1)[0][0]

def album_conflicts(rows: list[dict[str, str]], album: str, values: dict[str, str]) -> list[str]:
    warnings = []
    for key in ["TALB", "TDRC", "TCOM", "TCON"]:
        vote = album_vote(rows, album, key, verbose=False)
        if vote and values.get(key) and values[key] != vote:
            counts = Counter(strip_site_suffix(row.get(key, "")) for row in rows if row_album(row) == album and row.get(key))
            warnings.append(f"{key} differs from album majority {dict(counts)}; keeping {values[key]!r}")
    return warnings

def musicbrainz_lookup(album: str, title: str) -> tuple[dict[str, str], list[str]]:
    time.sleep(1)
    query = urllib.parse.quote(f'recording:"{title}" AND release:"{album}"')
    url = f"https://musicbrainz.org/ws/2/recording/?query={query}&fmt=json&limit=1&inc=releases+artist-credits"
    req = urllib.request.Request(url, headers={"User-Agent": "musictag.py/1.0 (local script)"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = jsonlib.load(r)
    except Exception as e:
        return {}, [f"MusicBrainz lookup failed: {e}"]
    recordings = data.get("recordings") or []
    if not recordings:
        return {}, ["MusicBrainz lookup found no recording"]
    rec = recordings[0]
    release = (rec.get("releases") or [{}])[0]
    artist = ", ".join(a.get("name", "") for a in rec.get("artist-credit", []) if isinstance(a, dict))
    year = (release.get("date") or "")[:4]
    out = {"UFID:http://musicbrainz.org": rec.get("id", ""), "TXXX:MusicBrainz Album Id": release.get("id", ""), "TCOM": artist}
    if year:
        out["TDRC"] = year
    mediums = release.get("media") or []
    tracks = (mediums[0].get("tracks") if mediums else []) or []
    for track in tracks:
        if (track.get("recording") or {}).get("id") == rec.get("id") and track.get("number"):
            out["TRCK"] = str(track["number"])
    return {k: v for k, v in out.items() if v}, []

def planned_tags(path: Path, tags: ID3, rows: list[dict[str, str]], overrides: dict[str, str], use_mb: bool) -> tuple[dict[str, str], list[str]]:
    album, title = filename_album_title(path)
    values = {key: strip_site_suffix(current_value(tags, key)) for key in TAG_FIELDS if current_value(tags, key)}
    if not values.get("TEXT") and current_value(tags, "TOLY"):
        values["TEXT"] = strip_site_suffix(current_value(tags, "TOLY"))
    values["TALB"] = album
    values["TIT2"] = title
    warnings: list[str] = []
    for key in ["TDRC", "TCOM", "TCON"]:
        if not values.get(key):
            vote = album_vote(rows, album, key)
            if vote:
                values[key] = vote
    if use_mb and not any(row_album(row) == album for row in rows):
        mb, mb_warnings = musicbrainz_lookup(album, title)
        warnings.extend(mb_warnings)
        for key, value in mb.items():
            values.setdefault(key, value)
    values.update({k: v for k, v in overrides.items() if v})
    warnings.extend(album_conflicts(rows, album, values))
    if values.get("TDRC") and not YEAR_RE.match(values["TDRC"]):
        raise ValueError(f"{path.name}: TDRC must be a bare 4-digit year: {values['TDRC']}")
    return values, warnings

def diff_tags(tags: ID3, values: dict[str, str]) -> list[dict[str, str]]:
    return [row for row in report_tags(tags, values) if row["status"] != "retained"]

def report_tags(tags: ID3, values: dict[str, str]) -> list[dict[str, str]]:
    rows = []
    for key in sorted(tags.keys()):
        if key not in MANAGED and preserved_frame(tags, key):
            rows.append({"field": key, "old": frame_summary(tags, key), "new": frame_summary(tags, key), "status": "retained"})
        elif key not in MANAGED:
            rows.append({"field": key, "old": frame_summary(tags, key), "new": "", "status": "deleted"})
    for key in TAG_FIELDS:
        old = current_value(tags, key)
        new = values.get(key, "")
        if new and old != new:
            rows.append({"field": key, "old": old, "new": new, "status": "changed"})
        elif old or new:
            rows.append({"field": key, "old": old or new, "new": new or old, "status": "retained"})
    return rows

def line_value(value: str) -> str:
    return (value or "<empty>").replace("\\", "\\\\").replace("\r", "\\r").replace("\n", "\\n")

def format_report(path: Path, row: dict[str, str]) -> str:
    icon = {"deleted": "🔴", "changed": "🟡", "retained": "🟢"}[row["status"]]
    if row["status"] == "retained":
        return f"{path.name}: {icon} {row['field']}: {line_value(row['new'])}"
    return f"{path.name}: {icon} {row['field']}: {line_value(row['old'])} -> {line_value(row['new'] or '<deleted>')}"

def apply_changes(tags: ID3, values: dict[str, str]) -> None:
    for key in list(tags.keys()):
        if key not in MANAGED and not preserved_frame(tags, key):
            del tags[key]
    for key, value in values.items():
        if key in MANAGED and value:
            write_tag(tags, key, value)

@app.command()
def dump() -> None:
    rows = []
    for f in sorted(Path(".").glob("*.[mM][pP][34]")):
        audio = File(f)
        if audio:
            row = {"filename": f.name, "length": f"{audio.info.length:.1f}"}
            row.update({key: get_tag(audio, key) for key in TAG_FIELDS})
            rows.append(row)
    with open("musicdump.csv", "w", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, FIELDS)
        writer.writeheader()
        writer.writerows(rows)

@app.command("apply")
def apply_cmd(csv_file: Path) -> None:
    updated = noops = skipped = 0
    for row in read_rows(csv_file):
        path = Path((row.get("filename") or "").strip())
        if not path.name:
            skipped += 1
            typer.echo("missing filename")
            continue
        if path.suffix.lower() != ".mp3" or not path.exists():
            skipped += 1
            typer.echo(f"{path}: {'skip non-mp3' if path.suffix.lower() != '.mp3' else 'file not found'}")
            continue
        tags = read_id3(path)
        before = {key: current_value(tags, key) for key in TAG_FIELDS}
        changed = False
        for key in STALE_KEYS:
            if key in tags:
                tags.delall(key)
                changed = True
        for key in TAG_FIELDS:
            if row.get(key, "").strip():
                write_tag(tags, key, row[key].strip())
        after = {key: current_value(tags, key) for key in TAG_FIELDS}
        if changed or before != after:
            save_preserve_mtime(tags, path)
            updated += 1
        else:
            noops += 1
    typer.echo(f"updated={updated} noops={noops} skipped={skipped}")
    if skipped:
        raise typer.Exit(1)

@app.command()
def fix(
    files: list[Path],
    write: bool = False,
    json_output: bool = typer.Option(False, "--json"),
    musicbrainz: bool = False,
    genre: str = "",
    year: str = "",
    composer: str = "",
    album: str = "",
    title: str = "",
    artist: str = "",
    track: str = "",
) -> None:
    rows = read_rows()
    overrides = {"TCON": genre, "TDRC": year, "TCOM": composer, "TALB": album, "TIT2": title, "TPE1": artist, "TRCK": track}
    results = []
    exit_code = 0
    for path in files:
        tags = read_id3(path)
        try:
            values, warnings = planned_tags(path, tags, rows, overrides, musicbrainz)
        except ValueError as e:
            typer.echo(str(e), err=True)
            raise typer.Exit(2)
        frames = report_tags(tags, values)
        changes = [row for row in frames if row["status"] != "retained"]
        if changes and not write:
            exit_code = 1
        if write and changes:
            apply_changes(tags, values)
            save_preserve_mtime(tags, path)
            update_csv_row(path, read_id3(path))
        result = {"file": str(path), "changed": bool(changes), "written": bool(write and changes), "changes": changes, "frames": frames, "warnings": warnings}
        results.append(result)
        if not json_output:
            for warning in warnings:
                typer.echo(f"{path.name}: {warning}", err=True)
            for frame in frames:
                typer.echo(format_report(path, frame))
    if json_output:
        typer.echo(jsonlib.dumps(results, indent=2))
    raise typer.Exit(exit_code)

def has_site_spam(tags: ID3) -> bool:
    for key in tags.keys():
        if key.startswith("APIC"):
            continue
        value = current_value(tags, key) or str(tags[key])
        if value_has_site_spam(value):
            return True
    return False

@app.command()
def check() -> None:
    issues = 0
    for path in sorted(Path(".").glob("*.[mM][pP]3")):
        tags = read_id3(path)
        extra = sorted(k for k in tags.keys() if k not in MANAGED and not preserved_frame(tags, k))
        if extra:
            issues += 1
            typer.echo(f"{path.name}: non-whitelisted frames: {', '.join(extra)}")
        if has_site_spam(tags):
            issues += 1
            typer.echo(f"{path.name}: site spam")
    music = Path("~/Music").expanduser()
    for m3u in music.glob("*.m3u"):
        for line in m3u.read_text(errors="replace").splitlines():
            item = line.strip()
            if item and not item.startswith("#") and not (m3u.parent / item).exists():
                issues += 1
                typer.echo(f"{m3u.name}: missing {item}")
    raise typer.Exit(1 if issues else 0)

if __name__ == "__main__":
    app()
