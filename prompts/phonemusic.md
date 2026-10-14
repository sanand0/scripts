# phonemusic

## Build sync script, 14 Oct 2026

<!--
cd ~/code/scripts
codex --model gpt-6-luna --config model_reasoning_effort=high
-->

See ~/code/infra/android-file-transfer/ for how I connect to my phone music directory.

Write an agent-friendly script `phonemusic` - similar to other scripts in this repo - that will sync music files from my `~/Music` folder to my phone's Internal shared storage / Music folder.

I will reconnect the phone periodically and the mount point may change. Infer dynamically.

`phonemusic sync` should sync files. Specifically:

- All .mp3 files directly under `~/Music` (not sub-directories, not non-mp3 files) should be copied to the phone's Internal shared storage / Music folder.
- Any extra files in the phone's Internal shared storage / Music folder that are not in `~/Music` should be logged as extra files (warning), not deleted.
- Copy ~/Music/musicdump.csv - overwriting any existing file on the phone
- Merge music-history.tsv across the phone and local copies, i.e. no rows should be lost and both files should have the same contents at the end, sorted by timestamp.
- Do not touch queue.tsv or any other files.
- Print stats, one per line, like this:
  - Copied: xx MP3 - xx.x MB
  - Laptop has: xx MP3 - xx.x GB
  - Phone has: xx MP3 (xx extra) - xx.x GB
  - History merged: xx from laptop, xx from phone

If the phone is not accesible or mounted, or faces any issues, warn and exit.

---

Log songs as they're being copied, so I can see progress.
If the sync is interrupted, make sure it's resumable.
Maybe the script is already doing these - in which case, no action required.

---

Add a simple sub-command to phonemusic that prints the path where the phone's Internal shared storage / Music folder is mounted.

---

Don't treat non-MP3 files as extra phone files. Only MP3s and the specific files I mentioned (musicdump.csv, music-history.tsv) need to be synced. (So, no need to warn saying queue.tsv is an extra file on the phone.)

---

`phonemusic sync --delete` should delete extra MP3 files (not other file types) on the phone that are not in `~/Music`.

---

Do not log already synced files.

---

History merged: should report the number of rows ADDED - skipping common rows as part of the count.

<!-- codex resume 01a139af-7b90-7240-bb45-fcbc012f5199 -->
