# Scripts

These are personal productivity utilities that simplify my workflow on Windows (Cygwin) and Linux. These are in 2 places:

| Type    | Location                                         | Windows Path          | Linux Path            |
| ------- | ------------------------------------------------ | --------------------- | --------------------- |
| Public  | [GitHub](https://github.com/sanand0/scripts)     | `C:\code\scripts\`    | `~/code/scripts/`     |
| Private | [Dropbox](https://www.dropbox.com/home/scripts/) | `C:\Dropbox\scripts\` | `/c/Dropbox/scripts/` |

**Note**: I use `/c/Dropbox` as a symlink to `C:\Dropbox` in Cygwin to standardize scripts.

## Common Setup

```bash
echo 'source ~/code/scripts/setup.fish' >> ~/.config/fish/config.fish
echo 'source ~/code/scripts/setup.bash' >> ~/.bashrc
```

See [`agents/`](agents/README.md) for setting up AI code editors.

## Windows Setup

On an **Admin** command prompt, run:

```
CD /D C:\cygwin\home\Anand\
MKLINK /H .gitconfig C:\code\scripts\.gitconfig
MKLINK /D .ssh C:\Dropbox\scripts\.ssh
REM TODO: Set up `llm` keys.json on Windows
```

[Disable inherited permissions](https://stackoverflow.com/a/58275268/100904), remove all permissions,
and only add yourself with full permissions.

## System setup

Here are the setup details for my laptops.

- [Linux](setup/linux.md)
  - [Media Keys](setup/media-keys.dconf): Gnome keybindings
- [Windows](setup/windows.md)
- [Android](setup/android.md)
- [Online tools](setup/online.md) replacing installed software

# Scripts

- [activities.py](activities.py) generates daily activity reports in `~/Documents/activities/YYYY-MM-DD.tsv` from calendar events, sent mail, commits, browser history, and coding-agent prompts. By default it fills pending days through yesterday. Examples: `activities.py --date 2026-05-14`, `activities.py --days 3 --limit-per-source 50`, `activities.py --sources calendar,email,commit --dry-run`.
- [ask](ask) records a short voice note, sends it to `llm` for custom action (transcribe, bash code, fish code, ...), copies to clipboard
- [askwin](askwin) calls [ask](ask) and pastes on window we called it from. Triggered by Ctrl + Alt + 0
- [asu](asu) is a one-off ASU GSV calendar query helper for April 2026 events; the script itself says to delete it after 20 Apr 2026.
- [audiosync.py](audiosync.py) syncs audio and video files using cross-correlation. Usage: `uv run audiosync.py video.mkv audio.opus output.mkv`. I use this to sync screen recordings via `videorecord` with phone audio recordings of better quality.
- [backupgoogle.py](backupgoogle.py) archives Google Mail, Calendar, and Chat from currently logged in `gws` user into `/home/sanand/Documents/data/$EMAIL/`. `backupgoogle.py --since YYYY-MM-DD --until YYYY-MM-DD`.
- [backuplinkedin.py](backuplinkedin.py) backs up LinkedIn posts and comments that the standard export misses via a logged-in CDP browser. Examples: `backuplinkedin.py posts --username sanand0 --limit 5`, `backuplinkedin.py posts --username sanand0 --no-comments --dry-run`, `backuplinkedin.py --describe | jaq .`.
- [backupmeet.py](backupmeet.py) archives owned Google Meet recordings/transcripts from `root.node@gmail.com` Drive into `/home/sanand/Documents/Meet Recordings/`, renames files to start with the meeting date, converts `.mp4` files to `.opus` in `/home/sanand/Documents/calls/`, and deletes Drive originals older than `--older-than 7d` after a verified copy. It refuses to run against any other `gws` account. Set up the isolated login with `GOOGLE_WORKSPACE_CLI_CONFIG_DIR="$HOME/.config/gws-root.node@gmail.com" gws auth login`, then run e.g. `backupmeet.py --dry-run`, `backupmeet.py --older-than 365d --type video --limit 3`, or `backupmeet.py --before "6 months ago" --type transcript`.
- [backupwhatsapp.py](backupwhatsapp.py) backs up WhatsApp Web conversations through Chrome DevTools Protocol into `~/Documents/data/whatsapp/`. Examples: `backupwhatsapp.py --limit 5`, `backupwhatsapp.py --conversation "Family" --format jsonl`, `backupwhatsapp.py --since 2026-05-01 --until 2026-05-17 --limit 20 | moor`.
- [browsing_history.py](browsing_history.py) syncs Microsoft Edge URL activity from `History` and recoverable `Shortcuts` records into `~/Documents/data/browsing-history.db`, then queries it as TSV, CSV, or JSON. Examples: `browsing_history.py --root ~/.config/microsoft-edge --sync-only`, `browsing_history.py --no-sync --since 6m --fields timestamp,activity_source,url,title --limit 100`.
- [ccusage](ccusage) shows Claude Code usage and reset times - if you're already logged into Claude Code CLI.
- [chars](chars) lists non-ASCII characters in files.
- [clean_markdown.py](clean_markdown.py) normalizes Markdown list spacing (removes extra blank lines inside lists while preserving paragraph breaks). Supports file, clipboard (`--xclip`), and self-tests (`--test`).
- [copy-to-markdown.sh](copy-to-markdown.sh) converts clipboard rich text (HTML) to Markdown in clipboard. Usage: Ctrl + C, then Ctrl + Alt + C
- [daily-activities](daily-activities) runs daily personal activity and backup jobs under a lock, including `activities.py`, Google backups, summarizers, and unmetered-only rsync/rclone jobs. It is normally invoked by the `daily-activities.*` systemd service.
- [dev.sh](dev.sh) runs a development container for safer experimentation.
  - [dev.dockerfile](dev.dockerfile) contains the image spec.
  - [dev.test.sh](dev.test.sh) smoke-tests the dev tool environment. By default it re-runs itself through `dev.sh`; use `--local-only` to test the current shell instead.
- [consolidate_transcripts.py](consolidate_transcripts.py) aggregates lessons from my call transcript into a unified transcripts.md.
- [daydream](daydream) fuses recalled concepts into radical ideas. Example: `daydream -c llm -c oblique-strategies "web app"`
- [discourse.py](discourse.py) extracts recent posts from a Discourse category or topic.
- [dock.sh](dock.sh) restarts GNOME user extensions and the Ubuntu AppIndicators extension after screen blanking breaks the dock/tray state.
- [freeslots.py](freeslots.py) suggests preferred and fallback meeting slots from Google Calendar free/busy data via `gws`, explicitly showing my time zone and the requested time zone with DST-aware abbreviations. It skips weekends for broad searches, moves recognized-holiday slots to the fallback section with the holiday name, honors explicit one-day dates, and keeps the longest 3 slots per day unless overridden. Examples: `freeslots.py --timezone UK --days 7`, `freeslots.py --timezone "San Francisco" --since tomorrow --until "next friday" --slots-per-day 2`, `freeslots.py --timezone ET --duration 45 --include-weekends --format json | jaq .`.
- [gitget](gitget) clones a git repository and copies specific paths to local directories.
- [git-size](git-size) shows the size of changes that `git add <repo-root>` would stage in net lines and total bytes. <!-- https://chatgpt.com/c/6a237662-c664-83ec-9416-97eb1a4b82a1 -->
- [git-stage-repo](git-stage-repo) stages committed files from a repo _under_ the current repo. Useful when experimenting in sub-folders with git, then squashing the changes in the parent. Same files are tracked by parent and child repos. <!-- https://chatgpt.com/c/6a1d25bf-49f4-83ec-8e02-5905a22f4fe0 -->
- [git-uncommitted](git-uncommitted) lists directories not git-synced with remote.
- [githubscore.py](githubscore.py) evaluates GitHub developer quality.
- [googleconnections.py](googleconnections.py) lists apps connected to the Google Account in a CDP browser on port 9222, including URL, app name, access time, permissions, and connection ID. Defaults to TSV sorted by URL; use `googleconnections.py --format csv` for CSV or `googleconnections.py --format jsonl --limit 5` for a small structured sample.
- [gmail](gmail.py): Gmail search CLI. Uses OAuth tokens from [google_oauth.py](google_oauth.py).
- [gwslog.py](gwslog.py) shows recent Google Drive changes through `gws`, with cached folder paths and shared-drive names.
  - Recent Docs: `gwslog.py --since 7d --type doc`
  - Path/user feed: `gwslog.py --path Innovation --user s.anand@gramener.com --since 30d --format jsonl`
  - Copy a compact list: `gwslog.py --since 1d --columns "iso user title path link" | xclip -selection clipboard`
  - Incremental feed from another account: `GOOGLE_WORKSPACE_CLI_CONFIG_DIR=~/.config/gws-root.node@gmail.com gwslog.py since`
- [histfreq](histfreq) ranks the most common commands from a NUL-delimited shell history stream. `history --null | uv run histfreq.py -n 40`.
- [htmlemail.py](htmlemail.py) renders Markdown to HTML and sends as email via Gmail API. Usage: `uv run htmlemail.py --from EMAIL --email EMAIL body.md`.
  - Initialized via `htmlemail.py --init --client-secrets google-root.node-desktop_872568319651-7pde9a28vem61qfvon8pu0d9bgijv8lf.apps.googleusercontent.com.json` with Google OAuth desktop client secrets JSON.
- [livetranscribe](livetranscribe) watches a growing `.opus` recording and streams timestamped transcription via the Gemini Live API. Examples: `livetranscribe ~/Documents/calls/meeting.opus`, `livetranscribe meeting.opus --output notes.txt --prompt "Technical meeting"`, `livetranscribe meeting.opus --dry-run`.
- [mcpserver.py](mcpserver.py) exposes an MCP server on localhost:8000 that lets LLMs run bash commands. Useful for ChatGPT to control your machine. Run in sandbox to reduce risk.
- [q](q) is a terminal AI chat interface. `q 'What is 2 + 2?' --llm chatgpt` opens Google AI mode, asks the question, and prints the answer. `q --m chatgpt 'What is 2 + 2?'` does the same with ChatGPT.
- [recall](recall) shows a random note bullet. Example: `recall` or `recall talks`
- [rename_receipts.py](rename_receipts.py) renames PDF receipts to `YYYY-MM-DD Service $0.00 Card-1234.pdf` by extracting date, vendor, amount, and last-4 card details from invoice text.
- [rgb](rgb) converts RGB to hex and vice versa.
- [rofi-files.sh](rofi-files.sh) and [rofi-chrome-tabs.sh](rofi-chrome-tabs.sh) are used by rofi to get recent files. Triggered by Ctrl + Alt + F.
- [rofi-clip.sh](rofi-clip.sh) opens a rofi clipboard transform menu (text/Markdown/Rich text/URL/date utilities), applies the selected transform, and writes back to clipboard. Triggered by Ctrl + Alt + M (since it's mostly Markdown related).
- [rofi-prompts.sh](rofi-prompts.sh) shows prompts from Markdown files in `~/code/blog/pages/prompts` and `~/code/scripts/agents/**/SKILL.md` lets you pick one via rofi, then copies/pastes the selected fenced code block. Triggered by Ctrl + Alt + P.
- [skilluse.py](skilluse.py) scans Codex, Claude, and Copilot logs for agent skill usage. Examples: `skilluse.py --agent codex --skill "github:*"`, `skilluse.py --format json | jaq .`, `skilluse.py --describe | jaq .`.
- [slide.py](slide.py) creates slides from Markdown files. Usage: `uvx slide presentation.md`
- [summarize.py](summarize.py) adds AI-generated metadata (summary, keywords, people, actions for transcripts; description and keywords for blog posts) to Markdown files. Already-processed files are skipped.
  - New transcripts: `summarize.py transcript "/home/sanand/Dropbox/notes/transcripts/2026-04-*.md"` (edit `2026-04` to the target month)
  - New blog posts: `ug -rl '^date: "?2026-04' /home/sanand/code/blog/posts/ | xargs summarize.py blog` (edit `2026-04` to the target month)
- [touchegg.conf](touchegg.conf) is my touchpad gesture config for Touchegg on Ubuntu.
  - Global Gestures (Application: All)
    - Swipe Up 4 fingers: Increase volume 5%
    - Swipe Down 4 fingers: Decrease volume 5%
    - Swipe Left/Right 4 fingers: Pause / Play on VLC
    - Tap 2 fingers: Right mouse click (Button 3) on gesture begin.
    - Tap 3 fingers: Middle mouse click (Button 2) on gesture begin.
  - Application: microsoft-edge
    - Pinch Out 2 fingers: Zoom In
    - Pinch In 2 fingers: Zoom Out
    - Swipe Left 3 fingers: Back
    - Swipe Right 3 fingers: Forward
- [unbrace.js](unbrace.js) unwraps single-statement JavaScript blocks.
- [transcribe_calls.py](transcribe_calls.py) transcribes missing audio call recordings from `~/Documents/calls` into Markdown notes under `~/Dropbox/notes/transcripts`, with chunking and patching for invalid transcript sections. Examples: `transcribe_calls.py --dry-run`, `transcribe_calls.py --glob "*.opus"`, `transcribe_calls.py --patch-invalid-sections`.
- [update-files](update-files) caches directory listings so `rofi-files.sh` can stay fast even on large mounts.
- [viz.py](viz.py) embeds CSV files a HTML templates. This is the script that started [Gramener](http://gramener.com/) in 2011.

## AI coding agent scripts

- [agentlog.py](agentlog.py) reads logs from all AI coding agents: Codex, Claude, and Copilot
- [opencodelog.jq](opencodelog.jq) converts OpenCode session logs to Markdown (from `opencode export sessionID`) but I rarely use it since I don't use OpenCode much.
- [codextools.py](codextools.py) lists tools used by Codex
- [codexerrors.py](codexerrors.py) lists tool errors by Codex
- [podcast.py](podcast.py) renders speaker-labeled Markdown into a compact MP3 or Opus podcast with Gemini TTS, cached per segment for cheap resumes. Examples: `podcast.py notes.md --dry-run`, `podcast.py notes.md --output episode.mp3`, `podcast.py notes.md --parallel 8`.

## jq scripts

- [jsonpaths.jq](jsonpaths.jq) lists all unique JSON paths in a JSON/NDJSON file
- [tsv.jq](tsv.jq) converts a JSON array of objects into TSV
- [whatsappthread.jq](whatsappthread.jq) converts https://tools.s-anand.net/whatsappscraper/ JSON into LLM-friendly JSONL + thread_id + urls[]

## Others

- [generate/](generate/) has scripts to generate data.
- [pdbhook/](pdbhook/) runs Python debugger on error. Usage: `PYTHONPATH=~/code/scripts/pdbhook uv run script.py`

## Services

`services/` has systemd services that are installed by [`services/setup.sh`](services/setup.sh). Current services are:

- `consolidate-transcripts-daily.*`: Consolidate transcript learnings
- `daily-activities.*`: Run daily activity reports, metadata summarizers, and unmetered-only personal backup/sync jobs
- `trending-repo-weekly.*`: Update trending GitHub repos
- `update-files-daily.*`: Update local files
- `update-files-weekly.*`: Update mounted files
