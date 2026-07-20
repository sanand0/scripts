from __future__ import annotations

import os
import sys
from pathlib import Path

from mutagen.apev2 import APEv2, APENoHeaderError
from mutagen.id3 import APIC, ID3, Encoding, POPM, TALB, TCOM, TCON, TDRC, TEXT, TIT2, TOLY, TPE2, USLT
from typer.testing import CliRunner

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import musictag


runner = CliRunner()


def tagged(path: Path, *frames) -> Path:
    path.write_bytes(b"")
    tags = ID3()
    for frame in frames:
        tags.add(frame)
    tags.save(path)
    return path


def text_frame(cls, value: str):
    return cls(encoding=Encoding.UTF8, text=[value])


def test_strip_site_suffix() -> None:
    assert musictag.strip_site_suffix("Song - MassTamilan.com") == "Song"
    assert musictag.strip_site_suffix("Song - StarMusiQ.Com - MassTamilan") == "Song"


def test_filename_split_uses_first_dot() -> None:
    assert musictag.filename_album_title(Path("Album.Title.With.Dot.mp3")) == ("Album", "Title.With.Dot")


def test_album_vote_picks_most_common() -> None:
    rows = [
        {"filename": "Album.One.mp3", "TALB": "Dirty", "TDRC": "2001"},
        {"filename": "Album.Two.mp3", "TALB": "Dirty", "TDRC": "2001"},
        {"filename": "Album.Three.mp3", "TALB": "Other", "TDRC": "2002"},
    ]
    assert musictag.album_vote(rows, "Album", "TDRC", verbose=False) == "2001"


def test_whitelist_deletion_and_filename_tags(tmp_path: Path) -> None:
    path = tagged(
        tmp_path / "Album.Title.mp3",
        text_frame(TALB, "Old - MassTamilan.com"),
        text_frame(TIT2, "Wrong - MassTamilan"),
        text_frame(TDRC, "2020"),
        text_frame(TCON, "Tamil"),
        text_frame(TCOM, "Composer - MassTamilan"),
        text_frame(TEXT, "Lyricist - MassTamilan"),
        text_frame(TPE2, "Delete Me"),
        APIC(encoding=Encoding.LATIN1, mime="image/jpeg", type=3, desc="", data=b"jpg"),
    )
    tags = musictag.read_id3(path)
    values, _ = musictag.planned_tags(path, tags, [], {}, False)
    musictag.apply_changes(tags, values)

    assert set(tags.keys()) <= musictag.MANAGED
    assert musictag.current_value(tags, "TALB") == "Album"
    assert musictag.current_value(tags, "TIT2") == "Title"
    assert musictag.current_value(tags, "TCOM") == "Composer"
    assert musictag.current_value(tags, "TEXT") == "Lyricist"


def test_preserves_popm_and_clean_long_uslt(tmp_path: Path) -> None:
    lyrics = "Clean personal lyrics. " * 12
    path = tagged(
        tmp_path / "Album.Title.mp3",
        text_frame(TDRC, "2020"),
        POPM(email="me@example.com", rating=196, count=3),
        USLT(encoding=Encoding.UTF8, lang="eng", desc="", text=lyrics),
    )
    tags = musictag.read_id3(path)
    values, _ = musictag.planned_tags(path, tags, [], {}, False)
    musictag.apply_changes(tags, values)

    assert "POPM:me@example.com" in tags
    assert "USLT::eng" in tags


def test_deletes_short_or_spammy_uslt(tmp_path: Path) -> None:
    path = tagged(
        tmp_path / "Album.Title.mp3",
        text_frame(TDRC, "2020"),
        USLT(encoding=Encoding.UTF8, lang="eng", desc="", text="MassTamilan " * 30),
    )
    tags = musictag.read_id3(path)
    values, _ = musictag.planned_tags(path, tags, [], {}, False)
    musictag.apply_changes(tags, values)

    assert "USLT::eng" not in tags


def test_toly_migrates_to_empty_text_then_deletes(tmp_path: Path) -> None:
    path = tagged(tmp_path / "Album.Title.mp3", text_frame(TOLY, "Lyricist - MassTamilan"))
    tags = musictag.read_id3(path)
    values, _ = musictag.planned_tags(path, tags, [], {}, False)
    musictag.apply_changes(tags, values)

    assert "TOLY" not in tags
    assert musictag.current_value(tags, "TEXT") == "Lyricist"


def test_album_conflict_warnings_are_filename_based() -> None:
    rows = [{"filename": "Album.One.mp3", "TALB": "Album", "TCOM": "Common Composer"}]
    warnings = musictag.album_conflicts(rows, "Album", {"TALB": "Album", "TCOM": "Other Composer"})

    assert warnings == ["TCOM differs from album majority {'Common Composer': 1}; keeping 'Other Composer'"]


def test_report_lines_include_retained_status_and_escape_newlines(tmp_path: Path) -> None:
    path = tagged(tmp_path / "Album.Title.mp3", text_frame(TDRC, "2020"), text_frame(TEXT, "One\nTwo - MassTamilan"))
    tags = musictag.read_id3(path)
    values, _ = musictag.planned_tags(path, tags, [], {}, False)
    frames = musictag.report_tags(tags, values)

    assert {"field": "TDRC", "old": "2020", "new": "2020", "status": "retained"} in frames
    text = next(frame for frame in frames if frame["field"] == "TEXT")
    assert musictag.format_report(path, text) == "Album.Title.mp3: 🟡 TEXT: One\\nTwo - MassTamilan -> One\\nTwo"


def test_fix_helpers_are_idempotent(tmp_path: Path) -> None:
    path = tagged(
        tmp_path / "Album.Title.mp3",
        text_frame(TALB, "Album - MassTamilan"),
        text_frame(TIT2, "Title - MassTamilan"),
        text_frame(TDRC, "2020"),
        text_frame(TPE2, "Delete Me"),
    )
    tags = musictag.read_id3(path)
    values, _ = musictag.planned_tags(path, tags, [], {}, False)
    assert musictag.diff_tags(tags, values)
    musictag.apply_changes(tags, values)
    musictag.save_preserve_mtime(tags, path)

    tags = musictag.read_id3(path)
    values, _ = musictag.planned_tags(path, tags, [], {}, False)
    assert musictag.diff_tags(tags, values) == []


def test_mtime_preserved(tmp_path: Path) -> None:
    path = tagged(tmp_path / "Album.Title.mp3", text_frame(TDRC, "2020"))
    old_ns = 1_700_000_000_123_456_789
    os.utime(path, ns=(old_ns, old_ns))
    tags = musictag.read_id3(path)
    musictag.write_tag(tags, "TIT2", "Title")
    musictag.save_preserve_mtime(tags, path)

    assert path.stat().st_mtime_ns == old_ns


def test_apply_overwrites_existing_value(tmp_path: Path, monkeypatch) -> None:
    path = tagged(tmp_path / "Album.Title.mp3", text_frame(TALB, "Old Album"))
    csv_path = tmp_path / "updates.csv"
    csv_path.write_text(f"filename,TALB\n{path.name},New Album\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(musictag.app, ["apply", str(csv_path)])

    assert result.exit_code == 0
    assert "updated=1" in result.stdout
    assert musictag.current_value(musictag.read_id3(path), "TALB") == "New Album"


def test_fix_preview_ends_with_write_reminder(tmp_path: Path) -> None:
    path = tagged(tmp_path / "Album.Title.mp3", text_frame(TALB, "Old Album"))

    result = runner.invoke(musictag.app, ["fix", str(path)])

    assert result.exit_code == 1
    assert result.stderr.rstrip().endswith("No changes written. Re-run with --write to apply fixes.")


def test_fix_write_deletes_apev2_tags(tmp_path: Path, monkeypatch) -> None:
    path = tagged(tmp_path / "Album.Title.mp3", text_frame(TALB, "Album"), text_frame(TIT2, "Title"))
    ape = APEv2()
    ape["Title"] = "Old title"
    ape.save(path)
    monkeypatch.setattr(musictag, "read_rows", lambda: [])

    result = runner.invoke(musictag.app, ["fix", "--write", str(path)])

    assert result.exit_code == 0
    try:
        APEv2(path)
    except APENoHeaderError:
        pass
    else:
        raise AssertionError("APEv2 tags were not deleted")
