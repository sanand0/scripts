# musictag.py

## Improve search, 27 Nov 2026

<!--
cd ~/code/scripts
codex --model gpt-6.2-sol --config model_reasoning_effort=high
-->

Though https://en.wikipedia.org/?curid=63423336 has the release date as "14 November 2020", `musictag.py search` wasn't able to get the year. The lyricist was mentioned in the page, but not in a structured way, perhaps, and `musictag.py search` didn't find it.

There are probably several such instances. How can we fix these to improve the search reliably?

For example, should we look in more fields for the year? Or might that be misleading? Research and find examples.
Should we look to see if specific lyricists, composers, artists, etc. are mentioned in the page? How do we ensure they're tagged properly (e.g. some composers are also artists, etc.)?

--- <!-- steering -->

Refer session 01a21cb2-5e5c-7ca2-bd21-1721a0a479de for more context

<!-- codex resume 01a21d35-1b40-7683-b879-95f76a5e1e47 -->

## Enable search, 27 Nov 2026

<!--
cd ~/code/scripts
codex --model gpt-6.2-sol --config model_reasoning_effort=high
-->

Enable `musictag.py search a.mp3 b.mp3 ...` which should update tags for the specified files.

If all required tags already exists for any file, it skips the file.
If any metadata can be deterministically filled, e.g. via search or lookups, it fills it for that file.
In case a metadata search reveals options that require me to guess something, e.g. between a few choices, print the musictag.py fix --write ... commands that will set the metadata for that file, one line per option, so I can pick the right ones.

For example: `musictag.py search Yuva.Badal.mp3 Next.Song.mp3` might print:

```bash
musictag.py fix --write 'Yuva.Badal.mp3'
  --genre Hindi
  --year 2004
  --year 2024
  --composer ARR
  --artist SPB,Harini
  --artist Hariharan,Nithyashri
musictag.py fix --write "Next.Song.mp3"
  ...
```

To see examples of how you might discover songs, here are some chats that have worked in the past. Use these to identify strategies for finding the tags:

- `~/Documents/chatgpt/GV Prakash Song Recommendations.md`
- `~/Documents/chatgpt/Download Truncated Tamil Songs from MassTamilan.md`
- `agentlog.py codex md 01a2024b-fe9e-7db3-909f-6401b55cab28`

Test this on a wide variety of songs and pick the strategy that leads to no mistakes AND the least work for me (not having to run any commands, or if I do, just a few options to choose from and the last amount of copy-paste.)

--- <!-- steering -->

~/Downloads/songs/AGENTS.md and the .py file there might help, too.

--- <!-- steering -->

Generate the `musictag.py fix ...` command output so that if I blindly copy-paste it, it will set the most likely correct values for the song.
That is, if there are multiple options, order them so that the most likely option is placed where `musictag.py fix ...` will end up applying it.

--- <!-- steering -->

When printing the options, prefer printing one per line, indented, just for where I need to choose, and keep the tags you're sure about on the first line, e.g.

```bash
musictag.py fix --write 'Yuva.Badal.mp3' --genre Hindi --composer ARR \
  --year 2004 \
  --year 2024 \
  --artist SPB,Harini \
  --artist Hariharan,Nithyashri
```

<!-- codex resume 01a21cb2-5e5c-7ca2-bd21-1721a0a479de -->

## Delete descriptions, 09 Oct 2026

<!--
cd ~/code/scripts
dev.sh -p ~/Music -- codex --yolo --model gpt-6.1-sol --config model_reasoning_effort=medium
-->

Modify `musictag.py fix` to delete COMM if it exists.
If it already does this, delete the COMM frame from everything in ~/Music.
Update ~/Music/musicdump.csv using `musictag.py dump` after the deletion.
Verify that musicdump.csv has no COMM frames.
Run `musictag.py apply` with the same music file and ensure that no COMM frames exist in the songs.
Also delete any Masstamil suffixes (e.g. ` - MassTamilan.com`) from fields in `musicdump.csv` and re-apply it.
Ensure that `dump` and `apply` work as I'd expect - and fix `musictag.py` if they don't.

<!-- codex resume 01a11ea0-94a4-7442-b9d6-0be5297d746b --yolo -->

## Allow overrides, 20 Jul 2026

<!--
cd ~/code/scripts
dev.sh -p ~/Music -- codex --yolo --model gpt-5.6-sol --config model_reasoning_effort=medium
-->

A few updates to musictag.py:

- `musictag.py fix` does not apply the fix without `--write`. Mention this on stderr at the end.
- `musictag.py apply` might not apply updates if a field is already present. Check if that is the case. If so, add a `--force` option to apply the update regardless of existing value. If it already does this, let me know - no action required.

---

`musictag.py fix` should also delete old APEv2 tags via `mutagen.apev2.delete` if they exist. Modify MINIMALLY.

<!-- codex resume 019f7da9-c4a0-77d0-9eeb-adbadd1971f7 --yolo -->

## Initial script, 10 Jul 2026

<!--
cd ~/code/scripts
dev.sh -p ~/Music -- codex --yolo --model gpt-5.5 --config model_reasoning_effort=medium
-->

<!-- Prompt: https://claude.ai/chat/1ccc54aa-e04a-4d12-b61f-08e09f34d072 -->

```markdown
Build `~/code/scripts/musictag.py`: a single-file uv script
(PEP 723 header, `#!/usr/bin/env -S uv run --script`, deps: mutagen, typer),
in the style of `~/code/scripts/audiosync.py`.

It REPLACES `~/Music/musicdump.py` and `~/Music/musicupdate.py`.
Port their logic into subcommands. Delete nothing until I confirm parity.

## Contract (do not violate)

- `~/Music/musicdump.csv` is the golden record. CSV column names ARE the
  ID3 tag names. No mapping layers.
- Standard frames (the ONLY frames allowed in my files):
  TCON, TDRC, TALB, TIT2, TCOM, TPE1, TRCK,
  TXXX:MusicBrainz Album Id, UFID:http://musicbrainz.org,
  TXXX:WIKIPEDIA_PAGEID.
  One TAG_FIELDS constant, used everywhere.
- Filenames are `Album.Title.mp3` (split on FIRST dot) and are the most
  trusted source. Never rename files.
- Preserve file mtime on every write (see current musicupdate.py).
- Save as ID3 v2.3.

## Subcommands

- `dump` — port of musicdump.py: scan cwd, write musicdump.csv.
- `apply CSV` — port of musicupdate.py: apply CSV rows to files.
- `fix FILE...` — NEW, the main event. Per file:
  1. DELETE every frame not in TAG_FIELDS. Yes, including APIC,
     USLT, COMM, TCOP, TPUB, TENC, TSRC, TIT1, TIT3, TPE2-4, TOPE,
     TEXT, TIPL, TSSE, TBPM, and all W\* frames.
  2. Strip download-site suffixes from kept frames: trailing
     ` - SiteName` / ` - SiteName.com` etc. (MassTamilan, StarMusiQ,
     VmusiQ, SenSongs, IsaiKadal, TamilWire, NaaSongs, Pagalworld,
     SongsPk, FriendsTamil — keep the site list one editable constant).
  3. Set TALB/TIT2 from the filename.
  4. Fill missing TDRC/TCOM/TCON by majority vote over rows in
     musicdump.csv with the same TALB. On a tie or conflict, print the
     vote counts and pick the most common; never overwrite an existing
     clean value.
  5. Overrides (always win): --genre --year --composer --album
     --title --artist --track.
  6. `--musicbrainz` (off by default): if album vote fails, query the
     MusicBrainz API (respect 1 req/sec) for year, composer, TRCK,
     release ID, recording ID. Network errors = warn, not fail.
  7. TDRC must be a bare 4-digit year; anything else is an error.
  8. Update/append this file's row in musicdump.csv.
- `check` — report: files with non-whitelisted frames, files with
  site spam, M3U entries in ~/Music/\*.m3u pointing at missing files.

## Agent-friendly behavior

- `fix` is DRY-RUN by default: print an old → new diff per frame.
  `--write` commits. `--json` emits machine-readable results.
- Exit 0 = clean/fixed; 1 = needs human attention; 2 = error.
- Idempotent: running `fix --write` twice changes nothing the
  second time.

## Review aids (do these, in order)

1. First output a short PLAN listing functions and the TAG_FIELDS /
   SITES / whitelist constants. Wait for my OK.
2. Copy 5 real spammy files to /tmp and show me `fix` dry-run diffs on
   them, e.g. `Velai Illa Pattadhaari.What A Karavaad.mp3`,
   `Geetha Govindam.Inkem Inkem Inkem Kaavaale.mp3`,
   `Engeyum Kaadhal.Dhimu Dhimu.mp3`.
3. Prove parity: `musictag dump` output must match musicdump.py's
   output on ~/Music (diff the CSVs).
4. Add a few pytest tests (tmp files via mutagen): whitelist deletion,
   suffix strip, filename split on first dot, album vote, idempotency,
   mtime preserved.
5. Keep it under ~350 lines. Comments only where the WHY is not obvious.
```

---

When I run `musictag.py fix "Velai Illa Pattadhaari.What A Karavaad.mp3"`, I get:

```
Velai Illa Pattadhaari.What A Karavaad.mp3: APIC:: <present> -> <deleted>
Velai Illa Pattadhaari.What A Karavaad.mp3: TCOP: MassTamilan -> <deleted>
Velai Illa Pattadhaari.What A Karavaad.mp3: TENC: MassTamilan -> <deleted>
Velai Illa Pattadhaari.What A Karavaad.mp3: TEXT: Dhanush - MassTamilan -> <deleted>
Velai Illa Pattadhaari.What A Karavaad.mp3: TIT1: MassTamilan -> <deleted>
Velai Illa Pattadhaari.What A Karavaad.mp3: TIT3: MassTamilan -> <deleted>
Velai Illa Pattadhaari.What A Karavaad.mp3: TOPE: Anirudh Ravichander - MassTamilan -> <deleted>
Velai Illa Pattadhaari.What A Karavaad.mp3: TPE2: Anirudh Ravichander - MassTamilan -> <deleted>
Velai Illa Pattadhaari.What A Karavaad.mp3: TPE3: Anirudh Ravichander - MassTamilan -> <deleted>
Velai Illa Pattadhaari.What A Karavaad.mp3: TPUB: MassTamilan -> <deleted>
Velai Illa Pattadhaari.What A Karavaad.mp3: TRSN: MassTamilan -> <deleted>
Velai Illa Pattadhaari.What A Karavaad.mp3: TRSO: MassTamilan -> <deleted>
Velai Illa Pattadhaari.What A Karavaad.mp3: TSRC: MassTamilan -> <deleted>
Velai Illa Pattadhaari.What A Karavaad.mp3: USLT::tam: What a Karuvaad What a Karuvaad
What a Karuvaadu What a Karuvaad
Eh Sutta Vada Pochuda What a Karuvaad
Ae Pattam Kizh... -> <deleted>
Velai Illa Pattadhaari.What A Karavaad.mp3: TALB: Velaiyilla Pattathari (VIP) - MassTamilan -> Velai Illa Pattadhaari
Velai Illa Pattadhaari.What A Karavaad.mp3: TIT2: What A Karavad - MassTamilan -> What A Karavaad
Velai Illa Pattadhaari.What A Karavaad.mp3: TCOM: Anirudh Ravichander - MassTamilan -> Anirudh Ravichander
Velai Illa Pattadhaari.What A Karavaad.mp3: TPE1: Anirudh Ravichander, Dhanush - MassTamilan -> Anirudh Ravichander, Dhanush
```

This looks fine. A few points:

- What Genre and Year will be set? Ideally, it should have picked it up from `Velai Illa Pattadhaari.Amma Amma.mp3` - and if there's a conflict between the existing values, let's flag it?
- Do TALB, TCOM, and anything else that's album specific match the most common values from `Velai Illa Pattadhaari.*.mp3` - and if not, let's flag it?
- Let's retain TEXT and proces it like TALB, TIT2, TPE1, etc.

---

For completeness, I would like `fix` to also show retained values.

Ensure 1 line per frame, e.g. `USLT::tam` and all fields can use `\n` for multi-line values.

Use colored circles to indicate changes. 🔴 Deletion 🟡 Change 🟢 Retained

Velai Illa Pattadhaari.What A Karavaad.mp3: TIT3: 🔴 MassTamilan -> <deleted>
Velai Illa Pattadhaari.What A Karavaad.mp3: TIT2: 🟡 What A Karavad - MassTamilan -> What A Karavaad
Velai Illa Pattadhaari.What A Karavaad.mp3: TDRC: 🟢 2014

---

Move the circles BEFORE the frame, e.g.:

Velai Illa Pattadhaari.What A Karavaad.mp3: 🔴 TIT3: MassTamilan -> <deleted>
Velai Illa Pattadhaari.What A Karavaad.mp3: 🟡 TIT2: What A Karavad - MassTamilan -> What A Karavaad
Velai Illa Pattadhaari.What A Karavaad.mp3: 🟢 TDRC: 2014

---

Let's revise the frames as follows: managed (synced to CSV) vs preserved (historical personal data I don't want to curate but shouldn't destroy).

- MANAGED frames (TAG_FIELDS, = CSV columns):
  TCON, TDRC, TALB, TIT2, TCOM, TPE1, TRCK, TEXT,
  TXXX:MusicBrainz Album Id, UFID:http://musicbrainz.org,
  TXXX:WIKIPEDIA_PAGEID.
- PRESERVED frames (never delete, never manage, not in CSV):
  POPM (my ratings); USLT only if >200 chars and no site spam.
- fix: copy TOLY into TEXT when TEXT is empty (strip site
  suffix first), then delete TOLY.
- DELETE every other frame.

---

Add usage examples to the docstring. Update README.md.

<!-- codex resume 019f4a7a-612d-7262-a8ee-87c9403651fe --yolo -->
