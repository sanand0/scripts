from __future__ import annotations

import json
import os
import shlex
import sys
from pathlib import Path

from mutagen.apev2 import APEv2, APENoHeaderError
from mutagen.mp4 import MP4FreeForm, MP4Tags
from mutagen.id3 import APIC, COMM, ID3, Encoding, POPM, TALB, TCOM, TCON, TDRC, TEXT, TIT2, TOLY, TPE1, TPE2, TRCK, USLT
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
    assert musictag.strip_site_suffix("Song - MassTamilan.dev") == "Song"
    assert musictag.strip_site_suffix("MassTamilan.so") == ""
    assert musictag.strip_site_suffix("A MassTamilan reference") == "A MassTamilan reference"


def test_filename_split_uses_first_dot() -> None:
    assert musictag.filename_album_title(Path("Album.Title.With.Dot.mp3")) == ("Album", "Title.With.Dot")


def test_dump_mp4_track_and_freeform_values() -> None:
    tags = MP4Tags()
    tags["trkn"] = [(2, 10)]
    tags["----:com.apple.iTunes:LYRICIST"] = [MP4FreeForm("Lyricist".encode())]
    assert musictag.get_tag(tags, "TRCK") == "2/10"
    assert musictag.get_tag(tags, "TEXT") == "Lyricist"
    tags["trkn"] = [(2, 0)]
    assert musictag.get_tag(tags, "TRCK") == "2"


def test_apply_missing_csv_fails(tmp_path: Path) -> None:
    result = runner.invoke(musictag.app, ["apply", str(tmp_path / "missing.csv")])
    assert result.exit_code == 2


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
        COMM(encoding=Encoding.UTF8, lang="eng", desc="description", text=["Comment"]),
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


def test_fix_deletes_bare_site_value(tmp_path: Path) -> None:
    path = tagged(tmp_path / "Album.Title.mp3", text_frame(TEXT, "MassTamilan.dev"))
    tags = ID3(path)
    values, _ = musictag.planned_tags(path, tags, [], {}, False)
    assert {"field": "TEXT", "old": "MassTamilan.dev", "new": "", "status": "deleted"} in musictag.report_tags(tags, values)
    musictag.apply_changes(tags, values)
    assert "TEXT" not in tags


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


def test_apply_clears_blanks_deletes_all_comments_and_uses_csv_directory(tmp_path: Path) -> None:
    path = tagged(
        tmp_path / "Album.Title.mp3",
        text_frame(TEXT, "MassTamilan.dev"),
        text_frame(TALB, "Album"),
        COMM(encoding=Encoding.UTF8, lang="eng", desc="one", text=["Comment"]),
        COMM(encoding=Encoding.UTF8, lang="tam", desc="two", text=["Comment"]),
        POPM(email="me@example.com", rating=196, count=3),
    )
    old_ns = path.stat().st_mtime_ns
    csv_path = tmp_path / "updates.csv"
    csv_path.write_text(f"filename,TEXT\n{path.name},\n", encoding="utf-8")

    result = runner.invoke(musictag.app, ["apply", str(csv_path)])

    assert result.exit_code == 0, result.output
    tags = ID3(path)
    assert not tags.getall("COMM")
    assert "TEXT" not in tags
    assert str(tags["TALB"]) == "Album"
    assert tags["POPM:me@example.com"].rating == 196
    assert path.stat().st_mtime_ns == old_ns
    result = runner.invoke(musictag.app, ["apply", str(csv_path)])
    assert result.exit_code == 0
    assert "updated=0 noops=1 skipped=0" in result.stdout


def test_apply_retains_multiple_values_on_round_trip(tmp_path: Path) -> None:
    path = tagged(tmp_path / "Album.Title.mp3", TPE1(encoding=Encoding.UTF8, text=["One", "Two"]))
    csv_path = tmp_path / "updates.csv"
    csv_path.write_text(f"filename,TPE1\n{path.name},{musictag.get_tag(ID3(path), 'TPE1')}\n", encoding="utf-8")
    result = runner.invoke(musictag.app, ["apply", str(csv_path)])
    assert result.exit_code == 0
    assert "updated=0" in result.stdout
    assert ID3(path)["TPE1"].text == ["One", "Two"]


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


def test_search_skips_complete_and_validates_batch_first(tmp_path: Path, monkeypatch) -> None:
    def unexpected_lookup(*args, **kwargs):
        raise AssertionError("unexpected lookup")

    monkeypatch.setattr(musictag, "search_sources", unexpected_lookup)
    complete = tagged(tmp_path / "Album.Complete.mp3", *[
        text_frame(frame, value) for frame, value in (
            (TALB, "Album"), (TIT2, "Complete"), (TCON, "Tamil"), (TDRC, "2004"),
            (TCOM, "Composer"), (TPE1, "Artist"), (TRCK, "1/6"), (TEXT, "Writer"),
        )
    ])
    original = complete.read_bytes()
    assert runner.invoke(musictag.app, ["search", str(complete)]).exit_code == 0
    assert complete.read_bytes() == original

    incomplete = tagged(tmp_path / "Album.Incomplete.mp3")
    result = runner.invoke(musictag.app, ["search", str(incomplete), str(tmp_path / "missing.mp3")])
    assert result.exit_code == 2
    assert "TIT2" not in ID3(incomplete)


def test_search_writes_shared_tags_and_emits_complete_linked_choices(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(musictag, "MUSIC_CSV", tmp_path / "musicdump.csv")
    path = tagged(
        tmp_path / "-Album.Title's & song.mp3",
        text_frame(TCOM, "Existing composer"),
        COMM(encoding=Encoding.UTF8, lang="eng", desc="personal", text=["Keep"]),
    )
    with path.open("ab") as audio:
        audio.write((b"\xff\xfb\x90\x64" + b"\0" * 413) * 10)
    candidates = [
        musictag.TagEvidence({"TCON": "Hindi", "TDRC": "2004", "TPE1": "First singer", "TEXT": "Writer A", "TRCK": "1/6", musictag.WIKI_ID: "123"}, True, "first", distance=2),
        musictag.TagEvidence({"TCON": "Hindi", "TDRC": "2024", "TPE1": "Second singer", "TEXT": "Writer B", "TRCK": "2/7"}, True, "second", distance=1),
    ]
    monkeypatch.setattr(musictag, "search_sources", lambda *args: iter(candidates))
    old_ns = path.stat().st_mtime_ns
    before = path.read_bytes()
    result = runner.invoke(musictag.app, ["search", "--dry-run", "--", path.name])
    assert result.exit_code == 1, result.output
    assert path.read_bytes() == before
    result = runner.invoke(musictag.app, ["search", "--", path.name])
    assert result.exit_code == 1, result.output
    lines = result.stdout.splitlines()
    assert len(lines) == 3
    assert lines[0].startswith("musictag.py fix --write --tags-only ")
    assert "--genre Hindi" in lines[0]
    assert lines[1].startswith("  --year 2004") and "'First singer'" in lines[1]
    assert lines[2].startswith("  --year 2024") and "'Second singer'" in lines[2]
    assert "--wiki-id=" in lines[2]
    assert ID3(path)["TCON"].text == ["Hindi"]
    assert ID3(path)["TIT2"].text == ["Title's & song"]
    assert "TDRC" not in ID3(path)
    assert path.stat().st_mtime_ns == old_ns
    args = shlex.split(result.stdout.replace("\\\n", ""))
    fixed = runner.invoke(musictag.app, args[1:])
    assert fixed.exit_code == 0, fixed.output
    tags = ID3(path)
    assert str(tags["TDRC"]) == "2024"
    assert str(tags["TEXT"]) == "Writer B"
    assert str(tags["TRCK"]) == "2/7"
    assert str(tags["TCOM"]) == "Existing composer"
    assert musictag.WIKI_ID not in tags
    assert "COMM:personal:eng" in tags
    assert musictag.read_rows(tmp_path / "musicdump.csv")[0]["TPE1"] == "Second singer"


def test_search_protects_unknown_editions_and_prefers_explicit_label_credits(monkeypatch) -> None:
    release_a = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    release_b = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    doc = {"data": [{"data": {"sections": [{"items": [
        {"name": "Right lyricist", "roleNames": ["Lyrics"]},
        {"name": "Singer", "roleNames": ["Vocals"]},
        {"name": "Actor", "roleNames": ["Actor"]},
        {"name": "Someone", "roleNames": ["Songwriter"]},
    ]}]}}]}
    html = f'<script id="serialized-server-data">{json.dumps(doc)}</script>'.encode()
    monkeypatch.setattr(musictag, "search_response", lambda url: html)
    credits = musictag.apple_credits("https://music.apple.com/in/song/1234")
    assert credits == {"TEXT": "Right lyricist", "TPE1": "Singer"}

    evidence = [
        musictag.TagEvidence({"TEXT": "Wrong lyricist"}, True, "wikipedia"),
        musictag.TagEvidence(credits | {"TRCK": "3/8"}, True, "apple", credits=True),
        musictag.TagEvidence({"TRCK": "3/8", musictag.RELEASE_ID: release_a}, True, "release A"),
        musictag.TagEvidence({"TRCK": "3/8", musictag.RELEASE_ID: release_b}, True, "release B"),
        musictag.TagEvidence({"TRCK": "8/8"}, True, "other edition"),
    ]
    missing = {"TEXT", "TRCK", musictag.RELEASE_ID}
    agreed, choices = musictag.search_decisions(evidence, missing)
    assert agreed == {"TEXT": "Right lyricist"}
    assert [choice.tags for choice in choices] == [{"TRCK": "8/8"}, {"TRCK": "3/8"}]
    evidence.append(musictag.TagEvidence({"TRCK": "8/8", musictag.RELEASE_ID: release_b}, True, "local", edition=True))
    assert musictag.search_decisions(evidence, missing) == (
        {"TEXT": "Right lyricist", "TRCK": "8/8", musictag.RELEASE_ID: release_b}, [],
    )


def test_wiki_search_uses_the_matched_row_and_duration() -> None:
    html = """
    <table class="infobox"><tr><th>Music by</th><td>Several<br>Composers</td></tr></table>
    <table class="infobox"><tr><th>Soundtrack album by Someone</th></tr>
    <tr><th>Released</th><td>1 April 2010</td></tr></table>
    <div class="track-listing">
    <p>All lyrics are written by This Writer.</p>
    <table class="tracklist">
    <caption>Telugu</caption>
    <tr><th>No.</th><th>Title</th><th>Singer(s)</th><th>Music</th><th>Length</th></tr>
    <tr><th>1.</th><td>"Other Song"</td><td>Other Singer</td><td>Other Composer</td><td>3:30</td></tr>
    <tr><th>2.</th><td>"This Song"</td><td>This Singer</td><td>This Composer</td><td>3:30</td></tr>
    </table></div>
    """
    page = {"pageid": 123, "title": "Album", "text": html}
    matches = list(musictag.wiki_tracks(page, "Album", "This Song", 210))
    assert matches[0].matched
    assert matches[0].tags == {
        "TIT2": '"This Song"', "TEXT": "This Writer", "TCOM": "This Composer",
        "TPE1": "This Singer", "TDRC": "2010", "TCON": "Telugu", "TRCK": "2/2", musictag.WIKI_ID: "123",
    }
    assert not matches[0].edition
    assert list(musictag.wiki_tracks(page, "Album", "This Song", 285)) == []


def test_wiki_year_uses_soundtrack_prose_for_the_original_language() -> None:
    html = """
    <table class="infobox"><tr><th>Language</th><td>Tamil</td></tr>
    <tr><th>Release date</th><td>2 February 2013</td></tr></table>
    <div class="mw-heading"><h2>Music</h2></div>
    <p>The music is composed by A Composer, with lyrics written by A Writer.
    The first single was released on 2 November 2012.
    The full album was released by Example Music on 7 December 2012.</p>
    <table class="tracklist"><caption>Tamil</caption>
    <tr><th>Title</th><th>Singer(s)</th><th>Length</th></tr>
    <tr><td>This Song</td><td>Singer</td><td>2:57</td></tr></table>
    <table class="tracklist"><caption>Telugu</caption>
    <tr><th>Title</th><th>Singer(s)</th><th>Length</th></tr>
    <tr><td>This Song</td><td>Singer</td><td>2:57</td></tr></table>
    <h2>Sequel</h2><p>The full album was released on 6 November 2026.</p>
    """
    page = {"pageid": 123, "title": "Album", "text": html}
    original, dub = musictag.wiki_tracks(page, "Album", "This Song", 178)
    assert original.tags["TDRC"] == "2012"
    assert "TDRC" not in dub.tags
    assert all("TEXT" not in match.tags for match in (original, dub))

    page["text"] = html.replace("The full album was released by Example Music on 7 December 2012.", "")
    assert all("TDRC" not in match.tags for match in musictag.wiki_tracks(page, "Album", "This Song", 178))
    page["text"] = html.replace("The full album was released by Example Music on 7 December 2012.",
                                "For the Telugu edition, the album was released on 7 January 2013.")
    assert all("TDRC" not in match.tags for match in musictag.wiki_tracks(page, "Album", "This Song", 178))


def test_wiki_soundtrack_uses_explicit_composer_instead_of_album_artist() -> None:
    html = """
    <table class="infobox"><tr><th>Soundtrack album by Album Artist</th></tr>
    <tr><th>Released</th><td>17 May 2013</td></tr></table>
    <p>Album is the soundtrack album composed by <a>Actual Composer</a> for the 2013 film.</p>
    <h2>Track listing</h2>
    <table class="tracklist"><tr><th>Title</th><th>Singer(s)</th><th>Length</th></tr>
    <tr><td>This Song</td><td>Singer</td><td>2:57</td></tr></table>
    """
    page = {"pageid": 123, "title": "Album (soundtrack)", "text": html}
    assert next(musictag.wiki_tracks(page, "Album", "This Song", 178)).tags["TCOM"] == "Actual Composer"
    page["text"] = html.replace("composed by <a>Actual Composer</a> ", "")
    assert "TCOM" not in next(musictag.wiki_tracks(page, "Album", "This Song", 178)).tags


def test_brainz_credits_follow_recording_roles_and_its_work(monkeypatch) -> None:
    def relation(role, name, attributes=()):
        return {"type": role, "artist": {"name": name}, "attributes": attributes}

    def lookup(url, **params):
        assert url.endswith("/recording/recording-id")
        assert params == {"fmt": "json", "inc": "artist-rels+work-rels+work-level-rels"}
        return {"relations": [
            relation("vocal", "Composer Singer", ["lead vocals"]),
            relation("vocal", "Backing Singer", ["background vocals"]),
            relation("instrument", "Guitarist"),
            {"type": "performance", "work": {"relations": [
                relation("composer", "Composer Singer"),
                relation("lyricist", "Composer Singer"),
                relation("lyricist", "Second Writer"),
                relation("writer", "Unspecified Writer"),
            ]}},
        ]}

    monkeypatch.setattr(musictag, "search_json", lookup)
    assert musictag.brainz_credits("recording-id") == {
        "TPE1": "Composer Singer", "TCOM": "Composer Singer", "TEXT": "Composer Singer, Second Writer",
    }
