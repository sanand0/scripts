# Usage

## Initial analysis, 05 Jun 2026

<!--
cd ~/code/scripts/
codex --model gpt-5.5 --config model_reasoning_effort=medium
-->

Update README.md with any executable scripts added in the last three months and not present in README.md. (It's entirely possible there are none.)

Review fish history with time stamps to understand which of these scripts in README.md have been used in which month and how often.

Based on that, I will take a call on which scripts to archive.

<!--
• Updated README.md:50 with 8 executable scripts added since 2026-03-05 that were missing: asu, backuplinkedin.py, backupwhatsapp.py, daily-activities, dock.sh, livetranscribe, skilluse.py, transcribe_calls.py.

  Verified: reran the detector and it reports remaining_missing_added_top_level_executables 0.

  Fish history reviewed from 2025-11-15 to 2026-06-05. Counts match documented executable script basenames in timestamped fish history; this can miss systemd/rofi/keybinding use and aliases that do not contain the script name.

  script                  total  months
  htmlemail.py            183    2026-01:69; 2026-02:32; 2026-03:30; 2026-04:28; 2026-05:22; 2026-06:2
  transcribe_calls.py     144    2026-03:47; 2026-04:50; 2026-05:45; 2026-06:2
  dev.sh                  107    2025-11:6; 2025-12:4; 2026-01:2; 2026-02:3; 2026-03:34; 2026-04:33; 2026-05:20; 2026-06:5
  mcpserver.py             69    2025-12:5; 2026-04:29; 2026-05:26; 2026-06:9
  discourse.py             38    2025-11:20; 2025-12:6; 2026-02:2; 2026-03:2; 2026-04:5; 2026-05:3
  agentlog.py              34    2026-04:30; 2026-05:4
  freeslots.py             34    2026-05:30; 2026-06:4
  podcast.py               30    2026-03:1; 2026-04:3; 2026-05:22; 2026-06:4
  summarize.py             30    2026-05:28; 2026-06:2
  gmail.py                 26    2026-01:4; 2026-03:2; 2026-04:6; 2026-05:14
  services/setup.sh        26    2025-11:2; 2025-12:5; 2026-01:3; 2026-02:3; 2026-03:4; 2026-04:3; 2026-05:6
  slide.py                 17    2026-01:12; 2026-03:3; 2026-04:1; 2026-05:1
  clean_markdown.py        16    2026-01:15; 2026-02:1
  rofi-files.sh            16    2025-11:15; 2026-03:1
  browsing_history.py      15    2026-05:15
  activities.py            14    2026-05:13; 2026-06:1
  backupmeet.py            11    2026-05:11
  gitget                   10    2025-11:3; 2025-12:3; 2026-03:4
  q                        10    2025-11:9; 2026-06:1
  ccusage                   9    2026-04:4; 2026-05:5
  rename_receipts.py        9    2026-02:8; 2026-04:1
  audiosync.py              8    2025-12:5; 2026-01:3
  backupgoogle.py           8    2026-05:7; 2026-06:1
  copy-to-markdown.sh       8    2025-11:3; 2025-12:4; 2026-01:1
  gwslog.py                 8    2026-05:8
  dock.sh                   6    2025-11:2; 2026-05:4
  rofi-prompts.sh           6    2026-05:6
  skilluse.py               6    2026-04:6
  dev.test.sh               5    2026-03:5
  asu                       4    2026-04:4
  backuplinkedin.py         4    2026-05:2; 2026-06:2
  rofi-chrome-tabs.sh       4    2025-11:4
  consolidate_transcripts.py 3   2025-11:1; 2025-12:1; 2026-01:1
  rofi-clip.sh              3    2026-02:2; 2026-04:1
  backupwhatsapp.py         2    2026-05:1; 2026-06:1
  codextools.py             2    2025-12:2
  livetranscribe            2    2026-04:2
  tsv.jq                    2    2026-05:2
  ask                       1    2026-05:1
  codexerrors.py            1    2025-12:1
  daily-activities          1    2026-05:1
  daydream                  1    2026-04:1
  git-uncommitted           1    2026-04:1
  jsonpaths.jq              1    2026-02:1
  update-files              1    2025-11:1
  askwin                    0
  chars                     0
  githubscore.py            0
  googleconnections.py      0
  histfreq                  0
  opencodelog.jq            0
  recall                    0
  rgb                       0
  whatsappthread.jq         0

  Strong archive candidates from fish history alone: the zero-use set above, plus one-off asu. Treat rofi/keybinding scripts and service wrappers cautiously because fish history undercounts them.
-->

<!--

#TODO

- Archive
  - asu: past event date
  - rgb: agents do this for me
  - histfreq: agents do this more reliably
  - opencodelog.jq: Incorporate into agentlog.py later based on need
  - daydream: I use ideator instead
- Retain?
  - chars: subsumed by rofi-clip.sh for conversion but still useful for detection
  - githubscore.py: tools.s-anand.net version is more used but still useful for automation
  - recall: need to use it more
  - git-uncommitted: handled by ~/code/update.py but might be useful for other paths
  - livetranscribe
  - tsv.jq
  - whatsappthread.jq
  - googleconnections.py
  - codextools.py
  - codexerrors.py
  - askwin
- Retain
  - update-files: used by shell scripts
  - jsonpaths.jq: might use it later
  - daily-activities: used by script
-->

<!-- codex resume 019e94ed-aa28-7ea3-ba29-fe5db323eff8 -->
