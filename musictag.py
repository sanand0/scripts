#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["beautifulsoup4", "mutagen", "typer"]
# ///

"""Dump, apply, search, check, and clean MP3 tags.

Examples:
  musictag.py dump
  musictag.py search "Album.Title.mp3" "Another Album.Another Title.mp3"
  musictag.py fix "Velai Illa Pattadhaari.What A Karavaad.mp3"
  musictag.py check | moor
"""

from __future__ import annotations

import csv
import json as jsonlib
import os
import re
import shlex
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator

import typer
from bs4 import BeautifulSoup
from mutagen import File
from mutagen.apev2 import delete as delete_apev2
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4FreeForm
from mutagen.id3 import (
    ID3,
    TALB,
    TCOM,
    TCON,
    TDRC,
    TEXT,
    TIT2,
    TOLY,
    TPE1,
    TRCK,
    TXXX,
    UFID,
    Encoding,
    ID3NoHeaderError,
)

app = typer.Typer(add_completion=False, help=__doc__)

TAG_FIELDS = [
    "TCON", "TDRC", "TALB", "TIT2", "TCOM", "TPE1", "TRCK", "TEXT",
    "TXXX:MusicBrainz Album Id",
    "UFID:http://musicbrainz.org",
    "TXXX:WIKIPEDIA_PAGEID",
]
FIELDS = ["filename"] + TAG_FIELDS[:8] + ["length"] + TAG_FIELDS[8:]
REQUIRED = TAG_FIELDS[:8]
FIX_OPTIONS = dict(zip(TAG_FIELDS, ("genre", "year", "album", "title", "composer", "artist", "track",
                                   "lyricist", "release-id", "recording-id", "wiki-id")))
RELEASE_ID, RECORDING_ID, WIKI_ID = TAG_FIELDS[8:]
SITES = ["MassTamilan", "StarMusiQ", "VmusiQ", "SenSongs", "IsaiKadal", "TamilWire", "NaaSongs", "Pagalworld", "SongsPk", "FriendsTamil"]
MANAGED = set(TAG_FIELDS)
MUSIC_CSV = Path("~/Music/musicdump.csv").expanduser()
SITE_RE = re.compile(r"(?:\s+-\s+|^)(?:" + "|".join(map(re.escape, SITES)) + r")(?:\.[a-z]+)?\s*$", re.IGNORECASE)
YEAR_RE = re.compile(r"^\d{4}$")
TEXT_FRAMES = {"TCON": TCON, "TDRC": TDRC, "TALB": TALB, "TIT2": TIT2, "TCOM": TCOM, "TPE1": TPE1, "TRCK": TRCK, "TEXT": TEXT, "TOLY": TOLY}
FALLBACK = {"TCON": ["©gen"], "TDRC": ["©day"], "TALB": ["©alb"], "TIT2": ["©nam"], "TCOM": ["©wrt"], "TPE1": ["©ART"], "TRCK": ["trkn"], "TEXT": ["----:com.apple.iTunes:LYRICIST"], "TXXX:MusicBrainz Album Id": ["----:com.apple.iTunes:MusicBrainz Album Id"], "UFID:http://musicbrainz.org": ["----:com.apple.iTunes:MusicBrainz Track Id"], "TXXX:WIKIPEDIA_PAGEID": ["----:com.apple.iTunes:WIKIPEDIA_PAGEID"]}
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
            if item == "trkn":
                track, total = val[0]
                return f"{track}/{total}" if total else str(track)
            if isinstance(val[0], bytes):
                return val[0].decode("utf-8")
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

def save_preserve_mtime(tags: ID3, path: Path, *, keep_multiple: bool = False) -> None:
    stat = path.stat()
    tags.save(path, v2_version=3, v23_sep=None if keep_multiple else "/")
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
        if key in values and not new and old:
            rows.append({"field": key, "old": old, "new": "", "status": "deleted"})
        elif new and old != new:
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
        if key in MANAGED:
            if value:
                write_tag(tags, key, value)
            else:
                tags.delall(key)

def apply_tag_updates(path: Path, tags: ID3, values: dict[str, str]) -> None:
    if not values:
        return
    for key, value in values.items():
        if value:
            write_tag(tags, key, value)
        else:
            tags.delall(key)
    save_preserve_mtime(tags, path, keep_multiple=True)
    # The inventory keys are basenames. An external file must not replace a library row.
    csv_path = path.resolve().with_name(MUSIC_CSV.name)
    if csv_path == MUSIC_CSV or csv_path.is_file():
        update_csv_row(path, read_id3(path), csv_path)

def search_key(value: str) -> str:
    return "".join(char for char in unicodedata.normalize("NFC", value).casefold()
                   if char.isalnum() or unicodedata.category(char).startswith("M"))

def tag_key(key: str, value: str) -> str:
    if key in {"TPE1", "TCOM", "TEXT"}:
        return ",".join(sorted(search_key(part) for part in value.split(",")))
    return search_key(value) if key != "TRCK" else value

def evidence_value(key: str, value: str) -> str:
    value = strip_site_suffix(value)
    if key in {"TPE1", "TCOM", "TEXT"}:
        value = re.sub(r"\s*,\s*", ", ", value)
    if value.casefold() in {"-", "—", "n/a", "unknown", "various artists", "[unknown]"} or not value.isprintable():
        return ""
    pattern = {
        "TDRC": r"[12][0-9]{3}", "TRCK": r"[1-9][0-9]*(?:/[1-9][0-9]*)?",
        RELEASE_ID: r"[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}",
        RECORDING_ID: r"[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}", WIKI_ID: r"[1-9][0-9]*",
    }.get(key)
    return value if not pattern or re.fullmatch(pattern, value) else ""

@dataclass
class TagEvidence:
    tags: dict[str, str]
    matched: bool
    source: str
    credits: bool = False
    edition: bool = False
    distance: float = float("inf")

def compatible(evidence: TagEvidence, current: dict[str, str]) -> bool:
    # Existing release/recording IDs and language can rule out namesakes. Other credits
    # may use different spellings or reflect errors already in the file.
    return all(tag_key(key, current[key]) == tag_key(key, evidence.tags[key])
               for key in {"TCON", "TDRC", RELEASE_ID, RECORDING_ID} & current.keys() & evidence.tags.keys())

def track_matches(first: str, second: str) -> bool:
    return first == second or (("/" not in first or "/" not in second) and
                               first.partition("/")[0] == second.partition("/")[0])

def library_evidence(path: Path, album: str, title: str, current: dict[str, str],
                     duration: float, rows: list[dict[str, str]]) -> Iterator[TagEvidence]:
    siblings = [row for row in rows if search_key(row_album(row)) == search_key(album)]
    for row in siblings:
        if row.get("filename") != path.name or not duration or not row.get("length"):
            continue
        if not close_duration(duration, float(row["length"])):
            continue
        tags = {key: value for key in TAG_FIELDS if (value := evidence_value(key, row.get(key) or ""))}
        if any(key in tags and search_key(tags[key]) != search_key(name)
               for key, name in (("TALB", album), ("TIT2", title))):
            continue
        if "TRCK" in current and "TRCK" in tags and not track_matches(current["TRCK"], tags["TRCK"]):
            continue
        yield TagEvidence(tags, True, str(MUSIC_CSV), edition=True)

    # Siblings identify an album or release, independently of its singers and track order.
    for anchor in (RELEASE_ID, WIKI_ID):
        anchored = [row for row in siblings if current.get(anchor) and row.get(anchor) == current[anchor]]
        for key in ("TCON", "TDRC") if anchor == RELEASE_ID else ("TCON",):
            values = {v for row in anchored if (v := evidence_value(key, row.get(key) or ""))}
            if len(values) == 1:
                yield TagEvidence({key: values.pop()}, True, str(MUSIC_CSV))

def search_decisions(candidates: list[TagEvidence], missing: set[str]) -> tuple[dict[str, str], list[TagEvidence]]:
    matched = [candidate for candidate in candidates if candidate.matched]

    def sources(key: str) -> list[dict[str, str]]:
        if key in {"TRCK", RELEASE_ID, RECORDING_ID}:
            return [candidate.tags for candidate in matched if candidate.edition]
        preferred = [candidate.tags for candidate in matched if candidate.credits and key in candidate.tags]
        if preferred and key in {"TPE1", "TCOM", "TEXT"}:
            return preferred
        return [candidate.tags for candidate in matched]

    identity_fields = {"TPE1", "TDRC", "TCON", RECORDING_ID}
    uncertain_identity = any(len({tag_key(key, row[key]) for row in sources(key) if key in row}) > 1
                             for key in identity_fields)
    agreed = {}
    for key in TAG_FIELDS:
        relevant = sources(key)
        values = [row[key] for row in relevant if key in row]
        sparse = len(values) < len(relevant)
        if key == "TRCK" and len({value.partition("/")[0] for value in values}) == 1:
            values = [value for value in values if "/" in value] or values
        if key not in missing or not values or len({tag_key(key, value) for value in values}) != 1:
            continue
        if uncertain_identity and key not in {"TCON", "TDRC", "TCOM"} and sparse:
            continue
        agreed[key] = values[0]

    choices = {}
    for candidate in candidates:
        tags = {key: candidate.tags[key] for key in TAG_FIELDS if key in (missing - agreed.keys()) & candidate.tags.keys()}
        if tags and (singer := candidate.tags.get("TPE1")):
            same_singers = [peer.tags for peer in candidates if tag_key("TPE1", peer.tags.get("TPE1", "")) ==
                            tag_key("TPE1", singer)]
            for key in {"TDRC", "TCOM", "TEXT"} & (missing - agreed.keys() - tags.keys()):
                values = [row[key] for row in same_singers if key in row]
                if len({tag_key(key, value) for value in values}) == 1:
                    tags[key] = values[0]
        tags = {key: tags[key] for key in TAG_FIELDS if key in tags}
        signature = tuple((key, tag_key(key, value)) for key, value in tags.items() if key in REQUIRED)
        if signature:
            choices.setdefault(signature, []).append((candidate, tags))

    by_option = {signature: max(support, key=lambda entry: evidence_rank(entry[0], entry[1]))
                 for signature, support in choices.items()}
    ranked = []
    for index, (signature, support) in enumerate(choices.items()):
        best, tags = by_option[signature]
        quality = evidence_rank(best, tags)
        if any(set(signature) < set(other) and quality[:3] <= evidence_rank(*entry)[:3]
               for other, entry in by_option.items()):
            continue
        tags = {key: value for key, value in tags.items() if key in REQUIRED or
                all(other.get(key) == value for _, other in support)}
        sources = {urllib.parse.urlsplit(candidate.source).netloc or candidate.source for candidate, _ in support}
        rank = (*quality[:2], len(sources), quality[2], quality[3], len(signature), -index)
        ranked.append((rank, TagEvidence(tags, best.matched, best.source)))
    return agreed, [option for _, option in sorted(ranked, key=lambda entry: entry[0])]

def evidence_rank(candidate: TagEvidence, tags: dict[str, str]) -> tuple[bool, bool, bool, float]:
    has_credits = candidate.credits and bool(tags.keys() & {"TPE1", "TCOM", "TEXT"})
    return candidate.matched, candidate.edition, has_credits, -candidate.distance

def choice_command(path: Path, confirmed: dict[str, str], options: list[TagEvidence]) -> str:
    def flags(values: dict[str, str]) -> list[str]:
        args = []
        for key in TAG_FIELDS:
            if key in values:
                flag, value = "--" + FIX_OPTIONS[key], values[key]
                args.extend([flag, value] if value and not value.startswith("-") else [f"{flag}={value}"])
        return args

    # Options sharing a field compete. Explicit empty values keep overlapping
    # choices self-contained when Typer takes the last occurrence of each flag.
    groups: list[set[str]] = []
    for option in options:
        fields = set(option.tags)
        overlaps = [group for group in groups if group & fields]
        groups = [group for group in groups if group not in overlaps] + [fields.union(*overlaps)]
    name = str(path)
    if name.startswith("-"):
        name = "./" + name
    defaults = confirmed.copy()
    lines = []
    for group in sorted(groups, key=lambda keys: min(TAG_FIELDS.index(key) for key in keys)):
        choices = [option.tags for option in options if group & option.tags.keys()]
        shared = {key: choices[-1][key] for key in group if len(choices) > 1 and
                  all(choice.get(key) for choice in choices) and
                  len({tag_key(key, choice[key]) for choice in choices}) == 1}
        defaults.update(shared)
        for choice in choices:
            values = {key: choice.get(key, "") for key in group - shared.keys()}
            lines.append("  " + shlex.join(flags(values)))
    first = shlex.join(["musictag.py", "fix", "--write", "--tags-only", name, *flags(defaults)])
    return " \\\n".join([first, *lines])

WIKIPEDIA = "https://en.wikipedia.org"
MUSICBRAINZ_API = "https://musicbrainz.org/ws/2/"
last_request: dict[str, float] = {}

@lru_cache(maxsize=192)
def search_response(url: str, **params: str) -> bytes:
    host = urllib.parse.urlsplit(url).netloc
    interval = 3.1 if host == "itunes.apple.com" else 1.1
    time.sleep(max(0, interval - (time.monotonic() - last_request.get(host, 0))))
    last_request[host] = time.monotonic()
    request = urllib.request.Request(url + ("?" + urllib.parse.urlencode(params) if params else ""),
                                     headers={"User-Agent": "musictag.py/1.0 (personal soundtrack catalog)"})
    with urllib.request.urlopen(request, timeout=8) as response:
        return response.read()

def search_json(url: str, **params: str) -> dict:
    return jsonlib.loads(search_response(url, **params))

def catalog_album(value: str) -> str:
    value = re.sub(r"\s*-\s*EP$", "", value, flags=re.I)
    value = re.sub(r"\s*\((?:(?:\d{4} )?film|soundtrack|original (?:motion picture )?soundtrack)\)$", "", value, flags=re.I)
    value = re.sub(r"\s+part\s*[-:]?\s*(?=[12]\s*$)", " ", value, flags=re.I)
    return search_key(re.sub(r"\bII?\b", lambda m: str(len(m[0])), value))

def album_matches(source: str, album: str) -> bool:
    return catalog_album(source) in {catalog_album(album), *(catalog_album(f"{album} {part}") for part in ("I", "II"))}

def catalog_song(value: str) -> str:
    return re.sub(r"([aeiou])\1+", r"\1", search_key(value))

def close_duration(local: float, source: float) -> bool:
    return bool(local and source and abs(local - source) <= 3)

def possible_duration(local: float, source: float) -> bool:
    return not local or not source or abs(local - source) <= 12

def duration_gap(local: float, source: float) -> float:
    return abs(local - source) if local and source else float("inf")

def apple_credits(url: str) -> dict[str, str]:
    soup = BeautifulSoup(search_response(url), "html.parser")
    script = soup.select_one("#serialized-server-data")
    if not script or not script.string:
        return {}
    roles: dict[str, list[str]] = {}
    for item in jsonlib.loads(script.string).get("data", []):
        for section in item.get("data", {}).get("sections", []):
            for credit in section.get("items", []):
                for role in credit.get("roleNames", []):
                    roles.setdefault(role, []).append(credit["name"])
    composers = roles.get("Composer", [])
    writers = roles.get("Lyrics", []) + roles.get("Lyricist", [])
    singers = roles.get("Vocals", []) + roles.get("Lead Vocals", [])
    # A generic performer credit may contain an otherwise unlabelled singer.
    if set(roles.get("Performer", [])) - set(composers + writers + singers + roles.get("Songwriter", [])):
        singers = []
    return {key: ", ".join(dict.fromkeys(names)) for key, names in
            (("TCOM", composers), ("TEXT", writers), ("TPE1", singers)) if names}

def apple_evidence(album: str, title: str, duration: float, needed: set[str]) -> Iterator[TagEvidence]:
    results = search_json("https://itunes.apple.com/search", term=f"{album} {title}", country="IN",
                          media="music", entity="song", limit="20").get("results", [])
    matches = []
    for result in results:
        name = re.sub(r'\s+\(From ["“].+?["”]\)$', "", result.get("trackName", ""))
        if result.get("kind") != "song" or not album_matches(result.get("collectionName", ""), album):
            continue
        if catalog_song(name) != catalog_song(title):
            continue
        seconds = result.get("trackTimeMillis", 0) / 1000
        if possible_duration(duration, seconds):
            matches.append((result, seconds))
    for result, seconds in matches:
        matched = close_duration(duration, seconds)
        number, total = result.get("trackNumber"), result.get("trackCount")
        url = f"https://music.apple.com/in/song/{int(result['trackId'])}"
        tags = {"TRCK": f"{number}/{total}"} if number and total and result.get("discNumber", 1) == 1 else {}
        if needed & {"TCOM", "TPE1", "TEXT"} and (matched or len(matches) == 1):
            try:
                tags.update(apple_credits(url))
            except (OSError, ValueError) as error:
                typer.echo(f"{album}.{title}: Apple Music credits lookup failed ({error})", err=True)
        yield TagEvidence({k: v for k, raw in tags.items() if (v := evidence_value(k, raw))}, matched, url,
                          credits=True, distance=duration_gap(duration, seconds))

def wiki_soundtrack_year(article, album: str, soundtrack: bool, boxes: list[dict]) -> str:
    dates = {year for box in boxes if "released" in box
             for year in re.findall(r"\b[12]\d{3}\b", box["released"].get_text(" ", strip=True))}
    if not dates:
        section = ""
        release = re.compile(
            r"(?:^|(?<=[.!?])\s+)the (?:(?:original|full) )?(?:soundtrack(?: album)?|album)"
            r"(?: of (?P<album>[^.!?]+?))? was released(?: by [^.!?]+?)?"
            r" on \d{1,2} [a-z]+ (?P<year>[12]\d{3})\b", re.I,
        )
        for element in article.find_all(["h2", "p"]):
            if element.name == "h2":
                section = search_key(element.get_text(" ", strip=True))
            elif section in {"music", "soundtrack"} or (soundtrack and section in {"", "release"}):
                dates.update(match["year"] for match in release.finditer(element.get_text(" ", strip=True))
                             if not match["album"] or catalog_album(match["album"]) == catalog_album(album))
    return next(iter(dates)) if len(dates) == 1 else ""

def wiki_tracks(page: dict, album: str, title: str, duration: float,
                film: dict | None = None) -> Iterator[TagEvidence]:
    soup = BeautifulSoup(page["text"], "html.parser")
    for note in soup.select("sup.reference, .mw-editsection, .sortkey"):
        note.decompose()
    article = soup.select_one(".mw-parser-output") or soup
    infoboxes = article.select("table.infobox")
    boxes = [
        {row.th.get_text(" ", strip=True).lower(): row.td for row in box.select("tr") if row.th and row.td}
        for box in infoboxes
    ]
    soundtrack_boxes = [box for node, box in zip(infoboxes, boxes)
                        if any(re.match(r"Soundtrack (?:album|EP) by\b", row.get_text(" ", strip=True), re.I)
                               for row in node.select("tr"))]
    wiki_id = str((film or page)["pageid"])
    film_boxes = (film or {}).get("boxes", boxes)
    languages = {b["language"].get_text(" ", strip=True) for b in film_boxes if "language" in b}
    language = next(iter(languages)) if len(languages) == 1 else ""
    composers = [b["music by"] for b in film_boxes if "music by" in b]
    composer = ""
    if len(composers) == 1 and not composers[0].select("br, li"):
        credit = composers[0].get_text(" ", strip=True)
        if not re.search(r",|&|\band\b", credit, re.I):
            composer = credit
    soundtrack = page["title"].endswith(" (soundtrack)")
    if soundtrack:
        # A lead credit for the album is more specific than the film's music credit.
        for element in article.find_all(["h2", "p"]):
            if element.name == "h2":
                break
            for link in element.select("a"):
                if (re.search(r"\b(?:soundtrack(?: album)?|the album featured \w+ songs) composed by\s*$",
                              str(link.previous_sibling), re.I)
                        and re.match(r"\s+(?:for|to|and arranged by)\b", str(link.next_sibling), re.I)):
                    composer = link.get_text(" ", strip=True)
    year = wiki_soundtrack_year(article, album, soundtrack, boxes if soundtrack else soundtrack_boxes)

    # Follow an explicitly linked soundtrack article when the film article delegates credits.
    links = list(dict.fromkeys(a["title"] for a in soup.select(".hatnote a[title]")
                              if a["title"].endswith(" (soundtrack)") and album_matches(a["title"], album)))
    if film is None and links:
        linked = wiki_page(links[0])
        if linked:
            yield from wiki_tracks(linked, album, title, duration, {**page, "boxes": boxes})

    for table in article.select("table.tracklist, table.wikitable"):
        rows = [[c.get_text(" ", strip=True) for c in r.find_all(["th", "td"], recursive=False)]
                for r in table.find_all("tr")]
        header_index = next((i for i, row in enumerate(rows[:3])
                             if any(search_key(c) in {"title", "song", "songtitle", "track"} for c in row)), None)
        if header_index is None or table.find("td", rowspan=True):
            continue
        headers = [search_key(cell) for cell in rows[header_index]]
        fields = {"TIT2": {"title", "song", "songtitle", "track"}, "TPE1": {"singer", "singers", "vocals", "playbacksingers"},
                  "TEXT": {"lyrics", "lyricist", "lyricists"}, "TCOM": {"music", "composer", "composers"},
                  "TRCK": {"no", "number", "tracknumber"}, "length": {"length", "duration"}}
        columns = {key: next(i for i, name in enumerate(headers) if name in names)
                   for key, names in fields.items() if names.intersection(headers)}
        if table.get("class") == ["wikitable"] and not columns.keys() & {"TPE1", "TEXT", "TCOM"}:
            continue
        data_rows = [row for row in rows[header_index + 1:] if len(row) == len(headers)]
        caption = table.caption.get_text(" ", strip=True) if table.caption else ""
        parent = table.find_parent(class_="track-listing") or table
        nearby = parent.find_previous_sibling(lambda node: node.name not in {"link", "style"})
        context = caption or (nearby.get_text(" ", strip=True) if nearby else "")
        edition_language = re.search(r"\b(Tamil|Hindi|Telugu|Malayalam|Kannada|Bengali|Marathi|English)\b", context, re.I)
        table_language = edition_language[1].title() if edition_language and len(context) < 60 else language
        intro = table.find_previous_sibling()
        lyricist = re.fullmatch(r"All lyrics are written by ([^;]+?)(?:\s*;\s*all music is composed by .+)?\s*\.",
                                intro.get_text(" ", strip=True), re.I) if intro and intro.name == "p" else None
        for row in data_rows:
            values = {key: row[i] for key, i in columns.items()}
            name = values["TIT2"]
            if catalog_song(name) != catalog_song(title):
                continue
            length = re.fullmatch(r"(\d+)\s*:\s*([0-5]\d)", values.pop("length", ""))
            seconds = int(length[1]) * 60 + int(length[2]) if length else 0
            if not possible_duration(duration, seconds):
                continue
            if not language or table_language == language:
                values["TDRC"] = year
            number = values.pop("TRCK", "").rstrip(".")
            # Table order describes one possible edition.
            if number.isdecimal() and all(r[columns["TRCK"]].rstrip(".") == str(i) for i, r in enumerate(data_rows, 1)):
                values["TRCK"] = f"{number}/{len(data_rows)}"
            if composer:
                values.setdefault("TCOM", composer)
            instrumental = re.search(r"\binstrumental\b", f'{name} {values.get("TPE1", "")}', re.I)
            if lyricist and not values.get("TEXT") and not instrumental:
                credit = lyricist[1].strip()
                if not re.search(r"\b(?:except|unless|otherwise)\b", credit, re.I):
                    values["TEXT"] = credit
            if table_language:
                values["TCON"] = table_language
            values[WIKI_ID] = wiki_id
            source = f"https://en.wikipedia.org/?curid={page['pageid']}"
            yield TagEvidence({k: v for k, raw in values.items() if (v := evidence_value(k, raw))},
                              close_duration(duration, seconds), source, distance=duration_gap(duration, seconds))

def wiki_page(name: str = "", page_id: str = "") -> dict:
    encoded = urllib.parse.quote(name.replace(" ", "_"), safe=":()")
    url = f"{WIKIPEDIA}/w/index.php?curid={page_id}" if page_id else f"{WIKIPEDIA}/wiki/{encoded}"
    try:
        html = search_response(url).decode()
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return {}
        raise
    ident = re.search(r'"wgArticleId":([1-9]\d*)', html)
    heading = re.search(r"<title>(.+?) - Wikipedia</title>", html)
    if not ident or not heading:
        return {}
    return {"pageid": ident[1], "title": BeautifulSoup(heading[1], "html.parser").get_text(), "text": html}

def wiki_evidence(album: str, title: str, current: dict[str, str], duration: float) -> list[TagEvidence]:
    page = wiki_page(album, evidence_value(WIKI_ID, current.get(WIKI_ID, "")))
    matches = list(wiki_tracks(page, album, title, duration)) if page and (
        current.get(WIKI_ID) or album_matches(page["title"], album)) else []
    if matches:
        return matches
    links = BeautifulSoup(page.get("text", ""), "html.parser").select(".hatnote a[title], li a[title]")
    if not any(album_matches(a["title"], album) for a in links):
        index = wiki_page(album + " (disambiguation)")
        links.extend(BeautifulSoup(index.get("text", ""), "html.parser").select("li a[title]"))
    names = dict.fromkeys(a["title"] for a in links if a["title"] != page.get("title")
                          and album_matches(a["title"], album))
    year = current.get("TDRC")
    for name in sorted(names, key=lambda name: bool(year and year in name), reverse=True)[:4]:
        candidate = wiki_page(name)
        if candidate:
            matches.extend(wiki_tracks(candidate, album, title, duration))
    return matches

def brainz_tracks(album: str, title: str, release_id: str) -> Iterator[tuple[dict, dict, dict, dict, bool]]:
    if release_id:
        release = search_json(MUSICBRAINZ_API + "release/" + release_id,
                              inc="recordings+artist-credits+release-groups", fmt="json")
        for medium in release.get("media", []):
            for track in medium.get("tracks", []):
                if catalog_song(track["title"]) == catalog_song(title):
                    yield release, medium, track, track["recording"], True
        return

    def quote_query(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')

    query = f'recording:"{quote_query(title)}" AND release:"{quote_query(album)}"'
    data = search_json(MUSICBRAINZ_API + "recording/", query=query, fmt="json", limit="25")
    recordings = data.get("recordings", [])
    complete = data.get("count", 0) <= len(recordings)
    for recording in recordings:
        if catalog_song(recording["title"]) != catalog_song(title):
            continue
        for release in recording.get("releases", []):
            if release.get("status") != "Official" or not album_matches(release["title"], album):
                continue
            for medium in release.get("media", []):
                for track in medium.get("track", []):
                    if catalog_song(track["title"]) == catalog_song(title):
                        yield release, medium, track, recording, complete

def brainz_credits(recording_id: str) -> dict[str, str]:
    recording = search_json(MUSICBRAINZ_API + "recording/" + recording_id, fmt="json",
                            inc="artist-rels+work-rels+work-level-rels")
    relations = recording.get("relations", [])
    works = [rel["work"] for rel in relations if rel["type"] == "performance" and "work" in rel]
    roles = {
        "TPE1": [rel for rel in relations if rel["type"] == "vocal" and
                 not {"background vocals", "spoken vocals"}.intersection(rel.get("attributes", []))],
    }
    if len(works) == 1:
        work_relations = works[0].get("relations", [])
        roles.update({key: [rel for rel in work_relations if rel["type"] == role]
                      for key, role in (("TCOM", "composer"), ("TEXT", "lyricist"))})
    return {key: ", ".join(names) for key, credits in roles.items()
            if (names := dict.fromkeys(rel["artist"]["name"] for rel in credits if "artist" in rel))}

def brainz_evidence(album: str, title: str, duration: float, current: dict[str, str],
                    needed: set[str], *, soundtrack: bool = False) -> Iterator[TagEvidence]:
    release_id = evidence_value(RELEASE_ID, current.get(RELEASE_ID, ""))
    for release, medium, track, recording, complete in brainz_tracks(album, title, release_id):
        seconds = (track.get("length") or recording.get("length") or 0) / 1000
        if not possible_duration(duration, seconds):
            continue
        tags = {RELEASE_ID: release["id"], RECORDING_ID: recording["id"]}
        if not compatible(TagEvidence(tags, False, ""), current):
            continue
        number, total = track.get("number"), medium.get("track-count")
        if number and medium.get("position", 1) == 1:
            tags["TRCK"] = f"{number}/{total}" if total else number
        if "TRCK" in current and "TRCK" in tags and not track_matches(current["TRCK"], tags["TRCK"]):
            continue
        group = release.get("release-group", {})
        if not soundtrack and "Soundtrack" not in group.get("secondary-types", []) and "soundtrack" not in release["title"].lower():
            tags["TPE1"] = ", ".join(credit["name"] for credit in recording.get("artist-credit", []))
        matched = complete and close_duration(duration, seconds)
        if "TDRC" in needed and matched and group.get("id"):
            try:
                if "first-release-date" not in group:
                    group = search_json(MUSICBRAINZ_API + "release-group/" + group["id"], fmt="json")
                tags["TDRC"] = (group.get("first-release-date") or "")[:4]
            except (OSError, ValueError) as error:
                typer.echo(f"{album}.{title}: MusicBrainz release date lookup failed ({error})", err=True)
        credit_fields = needed & {"TCOM", "TPE1", "TEXT"}
        credits = {}
        if matched and credit_fields:
            try:
                credits = brainz_credits(recording["id"])
            except (OSError, ValueError) as error:
                typer.echo(f"{album}.{title}: MusicBrainz credits lookup failed ({error})", err=True)
        if credits:
            tags.pop("TPE1", None)
            tags.update(credits)
        source = ("https://musicbrainz.org/recording/" + recording["id"] if credits else
                  "https://musicbrainz.org/release/" + release["id"])
        yield TagEvidence({k: v for k, raw in tags.items() if (v := evidence_value(k, raw))},
                          matched, source, credits=bool(credits), edition=bool(release_id),
                          distance=duration_gap(duration, seconds))

def search_sources(album: str, title: str, current: dict[str, str], duration: float,
                   needed: set[str]) -> Iterator[TagEvidence]:
    wiki = []
    try:
        wiki = wiki_evidence(album, title, current, duration)
        yield from wiki
    except (OSError, ValueError) as error:
        typer.echo(f"{album}.{title}: Wikipedia lookup failed ({error})", err=True)
    # Search the catalog's spelling when Wikipedia resolved a transliteration.
    spellings = {candidate.tags["TIT2"].strip('"') for candidate in wiki if "TIT2" in candidate.tags}
    lookup_title = next(iter(spellings)) if len(spellings) == 1 else title
    if needed & {"TCOM", "TPE1", "TEXT", "TRCK"}:
        try:
            yield from apple_evidence(album, lookup_title, duration, needed)
        except (OSError, ValueError) as error:
            typer.echo(f"{album}.{title}: Apple Music lookup failed ({error})", err=True)
    try:
        yield from brainz_evidence(album, lookup_title, duration, current, needed, soundtrack=bool(wiki))
    except (OSError, ValueError) as error:
        typer.echo(f"{album}.{title}: MusicBrainz lookup failed ({error})", err=True)

@app.command()
def search(
    files: list[Path] = typer.Argument(..., exists=True, dir_okay=False, readable=True),
    dry_run: bool = False,
) -> None:
    """Fill missing MP3 tags from the library and online catalogs. Print choices as fix commands."""
    for path in files:
        if path.suffix.lower() != ".mp3":
            raise typer.BadParameter(f"Expected an MP3 file: {path}", param_hint="FILES")
    library = None
    incomplete = False
    seen_paths = set()
    for path in files:
        resolved = path.resolve()
        if resolved in seen_paths:
            continue
        seen_paths.add(resolved)
        tags = read_id3(path)
        current = {key: value for key in TAG_FIELDS if (value := strip_site_suffix(current_value(tags, key)))}
        missing = set(TAG_FIELDS) - current.keys()
        if not missing.intersection(REQUIRED):
            continue

        album, title = filename_album_title(path)
        if not album or not title:
            album, title = current.get("TALB", ""), current.get("TIT2", "")
        local = {"TALB": album, "TIT2": title, "TEXT": current_value(tags, "TOLY")}
        changes = {key: value for key, raw in local.items() if key in missing and (value := evidence_value(key, raw))}
        missing -= changes.keys()
        candidates = []
        if album and title and missing.intersection(REQUIRED):
            typer.echo(f"{path}: looking up missing tags", err=True)
            duration = MP3(path).info.length
            if library is None:
                library = read_rows(MUSIC_CSV)
            candidates = [candidate for candidate in library_evidence(path, album, title, current, duration, library)
                          if compatible(candidate, current)]
            agreed, _ = search_decisions(candidates, missing)
            if (missing - agreed.keys()).intersection(REQUIRED):
                candidates.extend(candidate for candidate in search_sources(album, title, current, duration, missing - agreed.keys())
                                  if compatible(candidate, current))
        agreed, options = search_decisions(candidates, missing)
        changes.update(agreed)
        if changes:
            if not dry_run:
                apply_tag_updates(path, tags, changes)
            status = "would fill" if dry_run else "filled"
            summary = ", ".join(f"{FIX_OPTIONS[key]}={value}" for key, value in changes.items())
            typer.echo(f"{path}: {status} {summary}", err=True)
        unresolved = [FIX_OPTIONS[key] for key in REQUIRED if key in missing - agreed.keys()]
        if unresolved:
            incomplete = True
            typer.echo(f"{path}: unresolved {', '.join(unresolved)}", err=True)
        if options:
            typer.echo(choice_command(path, changes, options))
            for source in dict.fromkeys(option.source for option in options):
                typer.echo(f"  {source}", err=True)
    if incomplete:
        raise typer.Exit(1)

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
def apply_cmd(csv_file: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True)) -> None:
    """Apply supplied columns, clearing blank cells; filenames are relative to CSV."""
    updated = noops = skipped = 0
    for row in read_rows(csv_file):
        filename = row.get("filename") or ""
        if not filename:
            skipped += 1
            typer.echo("missing filename", err=True)
            continue
        path = csv_file.parent / filename
        if path.suffix.lower() not in {".mp3", ".mp4", ".m4a"} or not path.exists():
            skipped += 1
            typer.echo(f"{path}: {'unsupported file type' if path.exists() else 'file not found'}", err=True)
            continue
        if path.suffix.lower() != ".mp3":
            audio = File(path)
            before = {key: get_tag(audio, key) for key in TAG_FIELDS}
            if audio.tags is None:
                audio.add_tags()
            changed = "©cmt" in audio.tags
            audio.tags.pop("©cmt", None)
            for key in TAG_FIELDS:
                if key not in row:
                    continue
                value = row[key].strip()
                if value == before[key]:
                    continue
                atom = FALLBACK[key][0]
                if not value:
                    audio.tags.pop(atom, None)
                elif atom == "trkn":
                    track, _, total = value.partition("/")
                    audio.tags[atom] = [(int(track), int(total or 0))]
                elif atom.startswith("----:"):
                    audio.tags[atom] = [MP4FreeForm(value.encode("utf-8"))]
                else:
                    audio.tags[atom] = [value]
            if changed or before != {key: get_tag(audio, key) for key in TAG_FIELDS}:
                stat = path.stat()
                audio.save()
                os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
                updated += 1
            else:
                noops += 1
            continue
        tags = read_id3(path)
        before = {key: get_tag(tags, key) for key in TAG_FIELDS}
        changed = False
        for key in STALE_KEYS | {"COMM"}:
            if tags.getall(key):
                tags.delall(key)
                changed = True
        for key in TAG_FIELDS:
            if key in row:
                if row[key].strip():
                    if row[key].strip() != before[key]:
                        write_tag(tags, key, row[key].strip())
                else:
                    changed |= bool(tags.getall(key))
                    tags.delall(key)
        after = {key: get_tag(tags, key) for key in TAG_FIELDS}
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
    genre: str | None = None,
    year: str | None = None,
    composer: str | None = None,
    album: str | None = None,
    title: str | None = None,
    artist: str | None = None,
    track: str | None = None,
    lyricist: str | None = None,
    release_id: str | None = None,
    recording_id: str | None = None,
    wiki_id: str | None = None,
    tags_only: bool = typer.Option(False, help="Set only supplied tags. An empty value clears a tag."),
) -> None:
    supplied = (genre, year, album, title, composer, artist, track, lyricist, release_id, recording_id, wiki_id)
    overrides = {key: value for key, value in zip(TAG_FIELDS, supplied) if value is not None}
    rows = [] if tags_only else read_rows()
    if tags_only:
        for key, value in overrides.items():
            if value and not evidence_value(key, value):
                raise typer.BadParameter(f"Invalid value: {value!r}", param_hint=f"--{FIX_OPTIONS[key]}")
    results = []
    exit_code = 0
    for path in files:
        tags = read_id3(path)
        try:
            if tags_only:
                values = overrides
                warnings = []
            else:
                values, warnings = planned_tags(path, tags, rows, overrides, musicbrainz)
        except ValueError as e:
            typer.echo(str(e), err=True)
            raise typer.Exit(2)
        frames = report_tags(tags, values)
        if tags_only:
            frames = [frame for frame in frames if frame["field"] in values]
        changes = [row for row in frames if row["status"] != "retained"]
        if changes and not write:
            exit_code = 1
        if write and changes:
            if tags_only:
                apply_tag_updates(path, tags, {frame["field"]: frame["new"] for frame in changes})
            else:
                apply_changes(tags, values)
                save_preserve_mtime(tags, path)
                update_csv_row(path, read_id3(path))
        if write and not tags_only:
            delete_apev2(path)
        result = {"file": str(path), "changed": bool(changes), "written": bool(write and changes), "changes": changes, "frames": frames, "warnings": warnings}
        results.append(result)
        if not json_output:
            for warning in warnings:
                typer.echo(f"{path.name}: {warning}", err=True)
            for frame in frames:
                typer.echo(format_report(path, frame))
    if json_output:
        typer.echo(jsonlib.dumps(results, indent=2))
    if not write:
        typer.echo("No changes written. Re-run with --write to apply fixes.", err=True)
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
