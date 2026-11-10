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

See [sanand0/skills](https://github.com/sanand0/skills) for reusable agent skills and setup instructions.

## Tests

Run the complete suite with `just test`. The first run downloads the Chromium build pinned to the Playwright tests; later runs reuse it from Playwright's cache. Each test module has a focused recipe such as `just test-chatgpt` or `just test-mcpserver`; list them with `just --list`. Recipes use isolated, cached uv environments, so there is no test requirements file or lockfile to maintain.

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

# Config files

- [setup.fish](setup.fish): fish config file. Symlinked to `~/.config/fish/config.fish` on Linux/Cygwin.
- [setup.bash](setup.bash): bash config file. Symlinked to `~/.bashrc` on Linux/Cygwin.
- [.gitconfig](.gitconfig): git config file. Symlinked to `~/.gitconfig` on Linux/Cygwin.
- [git-ignore](git-ignore): global git ignore file. Symlinked to `~/.config/git/ignore` on Linux/Cygwin.
- [.tmux.conf](.tmux.conf): tmux config file. Symlinked to `~/.tmux.conf` on Linux/Cygwin.
- [espanso-match-base.yml](espanso-match-base.yml): espanso match file. Symlinked to `~/.config/espanso/match/base.yml` on Linux/Cygwin.
- [touchegg.conf](touchegg.conf): touchpad gesture config file. Symlinked to `~/.config/touchegg/touchegg.conf` on Linux/Cygwin.
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
- [redirector.json](redirector.json): config for [Redirector](https://chromewebstore.google.com/detail/redirector/lioaeidejmlpffbndjhaameocfldlhin) browser extension.

# Scripts

- [aboutmerge.py](aboutmerge.py). Updates people-specific notes from my transcripts. I run [About Updates](https://github.com/sanand0/blog/blob/45ff12dee5c617d6ef27abcd9865077877146479/pages/prompts/about-updates.md) on ChatGPT, save output in `~/Dropbox/notes/about/week-YYYY-MM-DD.md`, and run `aboutmerge.py` to merge the new notes into `~/Dropbox/notes/about/*.md`.
- [accept-invites](accept-invites). Accepts calendar invites shared between my work and personal calendars and cleans up the invites and acceptances.
- [activities.py](activities.py) generates daily activity reports in `~/Documents/activities/YYYY-MM-DD.tsv` from calendar events, sent mail, commits, browser history, and coding-agent prompts. By default it fills pending days through yesterday. Examples: `activities.py --date 2026-05-14`, `activities.py --days 3 --limit-per-source 50`, `activities.py --sources calendar,email,commit --dry-run`.
- [ask](ask) records a short voice note, sends it to `llm` for custom action (transcribe, bash code, fish code, ...), copies to clipboard
- [askwin](askwin) calls [ask](ask) and pastes on window we called it from. Triggered by Ctrl + Alt + 0
- [audiosync.py](audiosync.py) syncs audio and video files using cross-correlation. Usage: `uv run audiosync.py video.mkv audio.opus output.mkv`. I use this to sync screen recordings via `videorecord` with phone audio recordings of better quality.
- [backupgoogle.py](backupgoogle.py) archives Google Mail, Calendar, and Chat from currently logged in `gws` user into `~/Documents/data/$EMAIL/{source}-YYYY-MM.jsonl`. `backupgoogle.py --since YYYY-MM-DD --until YYYY-MM-DD`. Use `--config-dir ~/.config/gws-root.node@gmail.com` for the personal account or `--config-dir ~/.config/gws-anand@study.iitm.ac.in` for IITM. `daily-activities` backs up all three accounts. Account setup and service checks: `~/Dropbox/notes/gws-cli.md`.
- [backupchatgpt.py](backupchatgpt.py) backs up rendered ChatGPT conversations via `../tools/aiscrapers/{chatgptscraper,chatgpt-sidebar-scraper}.js`. Daily: `uv run backupchatgpt.py --limit 20 --format jsonl`. Weekly: `uv run backupchatgpt.py --rescan --limit 5`. Retry: `uv run backupchatgpt.py --conversation 'https://chatgpt.com/c/UUID' --format jsonl`. Logs: `~/.cache/sanand-scripts/backupchatgpt/YYYY-MM-runs.jsonl`
- [backupwhatsapp.py](backupwhatsapp.py) backs up WhatsApp Web conversations through Chrome DevTools Protocol into `~/Documents/data/whatsapp/`. Examples: `backupwhatsapp.py --limit 5`, `backupwhatsapp.py --conversation "Family" --format jsonl`, `backupwhatsapp.py --since 2026-05-01 --until 2026-05-17 --limit 20 | moor`.
- [browsing_history.py](browsing_history.py) syncs Microsoft Edge URL activity from `History` and recoverable `Shortcuts` records into `~/Documents/data/browsing-history.db`, then queries it as TSV, CSV, or JSON. Examples: `browsing_history.py --root ~/.config/microsoft-edge --sync-only`, `browsing_history.py --no-sync --since 6m --fields timestamp,activity_source,url,title --limit 100`.
- [ccusage](ccusage) reports Claude Code subscription quota and resets; `ccusage --json` for agents; uses the regular Claude Code login (restart Claude Code if its token expires).
- [codexusage](codexusage) reports Codex quota and resets; `codexusage --json` for agents.
- [ai-usage/](ai-usage/) is the GNOME panel widget for both, with colored quotas, reset countdowns, and adjustable refresh. Install with `cd ~/code/scripts/ai-usage && ./install.sh`; see its [README](ai-usage/README.md).
- [chars](chars) lists non-ASCII characters in files.
- [chatgpt](chatgpt) opens ChatGPT through a CDP browser, prepares prompts with optional files, model URL, project, connector mentions, reasoning selection, submit/no-submit modes, and `--save [TARGET]` Markdown capture. Use `chatgpt --inspect --format json | jaq .` before relying on current UI labels; examples: `chatgpt --save "Draft this"`, `chatgpt --file report.pdf --project "Transcripts" "Analyze this"`, `cat prompt.md | chatgpt --connector "Google Drive" --format json`.
- [chatgpt-export](chatgpt-export) exports ChatGPT data dumps avoiding the 3-minute OpenAI server timeout via HTTP ranges in an authenticated Edge tab. Copy the export link from email, then run: `chatgpt-export`. <!-- https://chatgpt.com/c/6aed288f-c17c-83e8-91de-bc294d1654f9 -->
- [clean_markdown.py](clean_markdown.py) normalizes Markdown list spacing (removes extra blank lines inside lists while preserving paragraph breaks). Supports file, clipboard (`--xclip`), and self-tests (`--test`).
- [daily-activities](daily-activities) runs daily personal activity and backup jobs under a lock, including `activities.py`, open tab snapshots in `~/Documents/data/open-tabs/`, Google backups, summarizers, and unmetered-only rsync/rclone jobs. It is normally invoked by the `daily-activities.*` systemd service.
- [dev.sh](dev.sh) runs a development container for safer experimentation.
  - [dev.dockerfile](dev.dockerfile) contains the image spec.
  - [dev.test.sh](dev.test.sh) smoke-tests the dev tool environment. By default it re-runs itself through `dev.sh`; use `--local-only` to test the current shell instead.
- [consolidate_transcripts.py](consolidate_transcripts.py) aggregates lessons from my call transcript into a unified transcripts.md.
- [context.py](context.py) builds a deterministic SQLite FTS5 index across transcripts, profiles, messages, conversations, and project assets, preserving source IDs and locators for follow-up reads.
  - Rebuild the index with `context.py rebuild`; query it with `context.py search "QUERY"`, `context.py entity PERSON`, or `context.py open-loops`.
- [discourse.py](discourse.py) extracts recent posts from a Discourse category or topic.
- [edge](edge) inspects and controls Microsoft Edge through session data and CDP. Examples: `edge tabs`, `edge md 'article title'`, `edge js 'WhatsApp' 'document.title'`, `edge open --reuse --window mail.google https://chatgpt.com/`. `--window` selects the window with the matching tab - else window with the most tabs.
- [edgeserver](edgeserver) + [edgeserver.html](edgeserver.html): phone remote for presenting Edge tabs at workshops. Serves on 127.0.0.1, drives Edge CDP (localhost:9222), and is exposed to the phone via `tailscale serve` HTTPS on a dedicated port (CDP is never exposed). The phone is a blind trackpad mapped onto the stage tab: drag = scroll, two fingers = aim then pinch/pan, double-tap = last checkpoint, hold-then-drag = pointer ring, bottom corners = prev/next playlist tab, swipe down from the header strip = Select (windows, tabs, playlist, lock, viewpoints).
  - `edgeserver` (or `edge serve`) starts it and prints the phone URL `https://<host>.ts.net:8765/`.
  - `edgeserver check` is the pre-talk check: CDP, server, serve config, `tailscale ping` to the phone (direct vs relayed).
  - `edgeserver --no-tailscale` serves only on 127.0.0.1.
- [edge-cdp-approve.ps1](edge-cdp-approve.ps1) keeps Plutonium's existing Edge profile accessible via CDP by opening a window and auto-approving prompts (task `EdgeCDPUnattended`); logs to `edge-cdp-approve.log` beside the script.
- [fish_usage.py](fish_usage.py) shows the most common fish commands used in the last 90 days.
- [freeslots.py](freeslots.py) suggests preferred and fallback meeting slots from Google Calendar free/busy data via `gws`, explicitly showing my time zone and the requested time zone with DST-aware abbreviations. It skips weekends for broad searches, moves recognized-holiday slots to the fallback section with the holiday name, honors explicit one-day dates, and keeps the longest 3 slots per day unless overridden. Examples: `freeslots.py --timezone UK --days 7`, `freeslots.py --timezone "San Francisco" --since tomorrow --until "next friday" --slots-per-day 2`, `freeslots.py --timezone ET --duration 45 --include-weekends --format json | jaq .`.
- [gitget](gitget) clones a git repository and copies specific paths to local directories.
- [git-size](git-size) shows the size of changes that `git add <repo-root>` would stage in net lines and total bytes. <!-- https://chatgpt.com/c/6a237662-c664-83ec-9416-97eb1a4b82a1 -->
- [git-stage-repo](git-stage-repo) stages committed files from a repo _under_ the current repo. Useful when experimenting in sub-folders with git, then squashing the changes in the parent. Same files are tracked by parent and child repos. <!-- https://chatgpt.com/c/6a1d25bf-49f4-83ec-8e02-5905a22f4fe0 -->
- [git-uncommitted](git-uncommitted) lists directories not git-synced with remote.
- [googleconnections.py](googleconnections.py) lists apps connected to the Google Account in a CDP browser on port 9222, including URL, app name, access time, permissions, and connection ID. Defaults to TSV sorted by URL; use `googleconnections.py --format csv` for CSV or `googleconnections.py --format jsonl --limit 5` for a small structured sample.
- [histfreq](histfreq) ranks the most common commands from a NUL-delimited shell history stream. `history --null | uv run histfreq.py -n 40`.
- [htmlemail.py](htmlemail.py) renders Markdown to HTML and sends as email via Gmail API. Usage: `uv run htmlemail.py --from EMAIL --email EMAIL body.md`.
  - Initialized via `htmlemail.py --init --client-secrets google-root.node-desktop_872568319651-7pde9a28vem61qfvon8pu0d9bgijv8lf.apps.googleusercontent.com.json` with Google OAuth desktop client secrets JSON.
- [linkedin](linkedin) CLI. Sub-commands: `linkedin profile "Person"`, `linkedin activity "Person"`, `linkedin search people engineer --location Chennai --organization Tata --degree 2`, `linkedin scheduled --refresh`, `linkedin sync analytics me`, `linkedin backup me`, ...
- [mailindex.py](mailindex.py) builds a compact, resumable SQLite FTS index for `~/Documents/Mail/*.mbox` at `~/Documents/Mail/mail-index.sqlite`.
- [mcpserver](mcpserver) runs [mcpserver.py](mcpserver.py) in the development container, waits for it to respond, then starts or reuses the LocalMCP2 OpenAI tunnel. Pass `dev.sh` options directly, for example `mcpserver -p ~/code/talks,~/Downloads,~/code:ro,~/r2:ro`; do not add `-- mcpserver.py`. See the [LocalMCP2 setup and operations guide](setup/localmcp.md).
- [mcpserver.py](mcpserver.py) exposes an MCP server at `http://127.0.0.1:2428/mcp2428` that lets LLMs run Bash commands and transfer files. It runs through `dev.sh` for a consistent container environment, but this is not a hard security boundary: `dev.sh` has default host mounts, including the Docker socket, in addition to explicit `-p` mounts. See the setup guide before granting access.
- [musictag.py](musictag.py) manages MP3 ID3 tags from `~/Music/musicdump.csv`, with dry-run cleanup diffs, CSV dump/apply parity, managed tag columns, and preserved personal `POPM`/clean long `USLT` frames. Examples: `musictag.py dump`, `musictag.py fix "Album.Title.mp3"`, `musictag.py fix --write --genre Tamil --year 2014 *.mp3`, `musictag.py check | moor`.
  - Run `dump` from `~/Music` to export top-level MP3/MP4 files. Run `musictag.py apply ~/Music/musicdump.csv` from any directory to apply MP3/MP4 tags: supplied blank cells clear fields, omitted columns stay unchanged, and comments are deleted. File mtimes are preserved.
- [play-music](play-music) plays a selected MP3 in VLC followed by 10 random MP3s from `~/Music`; `rofi-files.sh` uses it for MP3s opened from the file picker.
- [phonemusic](phonemusic) syncs top-level MP3s, `musicdump.csv`, and merged `music-history.tsv` from `~/Music` to the first mounted Android MTP phone. Run `phonemusic path` to print the current Music folder mount, or `phonemusic sync` to copy; sync logs each MP3 and resumes completed copies from per-phone checkpoints in `~/.cache/sanand-scripts/phonemusic/`. Extra phone MP3s are warned about and kept unless you pass `phonemusic sync --delete`, which removes only those extra MP3s.
- [prompt](prompt) shows Markdown prompts and skills, lets you pick one via rofi, or prints the closest fuzzy match when given a filter. Triggered by Ctrl + Alt + P; `prompt git-commit` is suitable for shell pipelines.
- [rgb](rgb) converts RGB to hex and vice versa.
- [rofi-picker](rofi-picker) powers **Ctrl+Alt+F**. Type one key: [F]iles, [W]indows, [D]irectories, [B]rowser [T]abs, [P]rompts (`Ctrl+Alt+P`), [M]ap clipboard (`Ctrl+Alt+M`), [C]ommands. **Enter** runs, **Ctrl/Alt+Enter** opens contextual actions. Directories use zoxide frecency (plus Git repositories); Git actions appear only inside repositories. [File](rofi/rofi-files.sh), [directory](rofi/rofi-directories.sh), [tab](rofi/rofi-chrome-tabs.sh), and [window](rofi/rofi-window-actions.sh) handlers stay independent. VS Code terminal actions use the existing [terminal-focus binding](setup/linux.md) and type the actual command into an idle shell so fish records it.
- [rofi-clip.sh](rofi/rofi-clip.sh) opens a rofi clipboard transform menu (text/Markdown/Rich text/URL/date utilities), applies the selected transform, and writes back to clipboard. Triggered by Ctrl + Alt + M (since it's mostly Markdown related). Ctrl + Alt + C runs `rofi/rofi-clip.sh --html-to-markdown` directly, converting clipboard HTML to Markdown in both the clipboard and primary selection.
- [rss-archive-page](rss-archive-page) is called by `uvx feed2exec fetch` via `~/.config/feed2exec.ini` to download RSS feeds into `~/Documents/rss/$FEED/*.html` as single-page HTMLs.
- [run-at](run-at) runs a command at a specific time, setting up systemd timers. Example: `run-at '2026-08-15 14:00' bash -c "echo 'hello' > /tmp/hello.txt"`.
- [skilluse.py](skilluse.py) scans Codex, Claude, and Copilot logs for agent skill usage. Examples: `skilluse.py --agent codex --skill "github:*"`, `skilluse.py --format json | jaq .`, `skilluse.py --describe | jaq .`.
- [slide.py](slide.py) creates slides from Markdown files. Usage: `slide.py presentation.md`
- [summarize.py](summarize.py) adds AI-generated metadata (summary, keywords, people, actions for transcripts; description and keywords for blog posts) to Markdown files. Already-processed files are skipped.
  - New transcripts: `summarize.py transcript "/home/sanand/Dropbox/notes/transcripts/2026-04-*.md"` (edit `2026-04` to the target month)
  - New blog posts: `ug -rl '^date: "?2026-04' /home/sanand/code/blog/posts/ | xargs summarize.py blog` (edit `2026-04` to the target month)
- [timers](timers) picks a systemd user timer with `fzf`, sorted by its most recent run, then follows the activated service's journal.
- [transcribe](transcribe) transcribes audio files into adjacent `.md` files, skipping existing files. Example: `transcribe a.mp3 /x/b.opus`. Supports `--prompt`, `--model`. Retries empty responses at `medium`, then `high` thinking
- [translate](translate) creates a virtual mic that translates what I say into any other language. Useful for Google Meet, etc.
- [call](call) transcribes matching paths from `~/Documents/calls` into `~/Dropbox/notes/transcripts/*.md` with cumulative timestamps. Uses [timestamp.py](timestamp.py) helpers.
  - Transcribe/resume: `call "Meeting"`; add context with `call "Meeting" --prompt "Speaker names and context"`.
  - Plan: `call "Meeting" --dry-run`; list pending/incomplete notes: `call --list-changes | moor`. Both save logs.
  - Logs in `~/.cache/sanand-scripts/transcribe_calls/run.jsonl`
- [timestamp.py](timestamp.py) repairs timestamps in older/ambiguous transcripts; new `call` output already uses cumulative timestamps. It idempotently makes timestamps cumulative across legacy chunks. Bare names resolve to the latest descending filename match under `~/Dropbox/notes/transcripts`; use `--chunk-starts 0,25,50` for ambiguous chunk boundaries. Examples: `timestamp.py Naveen`, `timestamp.py Naveen Ankor --dry-run`, `timestamp.py "2026-09-01 GIPCL" --chunk-starts 0,30,60,90,120`, `timestamp.py --describe | jaq .`.
- [update-files](update-files) caches directory listings for `rofi-files.sh`. It excludes bulky generated/archive trees (e.g. HostGator backup, Go modules, MCP temp files, old GitLab copies, Hugo output), but not file types. Previously selected paths remain available through `frecent.txt`; to find a different file in an excluded tree, browse or search that directory explicitly.

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

- `daily-activities.*`: Run daily activity reports, open tab snapshots, metadata summarizers, and unmetered-only personal backup/sync jobs
- `trending-repo-weekly.*`: Update trending GitHub repos
- `update-files-daily.*`: Update local files
- `vlc-history.service`: Log VLC playback paths with timestamps to `~/Music/music-history.tsv`

## Archive

- [backupmeet.py](archive/backupmeet.py): I use ChatGPT when required, including to automate bulk downloads. Removed from the daily jobs.
- [emailai](archive/emailai): I use ChatGPT because it has more context.
- [codexlist](archive/codexlist): I use [agentlog.py](agentlog.py).
- [githubscore.py](archive/githubscore.py): I use ChatGPT because it evaluates developers on broader, evolving criteria.
- [gwslog.py](archive/gwslog.py): I use ChatGPT weekly, when required, to summarize Drive activity rather than just list it.
- [q](archive/q): I do not query ChatGPT, Claude, or other assistants from the CLI.

- [backuplinkedin.py](archive/backuplinkedin.py) is the archived backup implementation. Use `linkedin backup me`; the native CLI preserves the existing blog-compatible JSONL archive.
- [daydream](archive/daydream) fuses recalled concepts into radical ideas. Example: `daydream -c llm -c oblique-strategies "web app"`
- [gmail.py](archive/gmail.py): Gmail search CLI. Uses OAuth tokens from [google_oauth.py](google_oauth.py). Archived in favor of `gws`.
- [linkedin.py](archive/linkedin.py) is a CLI for LinkedIn that uses CDP to fetch profiles, etc. `linkedin.py profile sanand0` fetches my profile. Replaced by `linkedin`.
- [livetranscribe](archive/livetranscribe) watches a growing `.opus` recording and streams timestamped transcription via the Gemini Live API. Examples: `livetranscribe ~/Documents/calls/meeting.opus`, `livetranscribe meeting.opus --output notes.txt --prompt "Technical meeting"`, `livetranscribe meeting.opus --dry-run`.
- [recall](archive/recall) shows a random note bullet. Example: `recall` or `recall talks`
- [unbrace.js](archive/unbrace.js) unwraps single-statement JavaScript blocks.
- [viz.py](archive/viz.py) embeds CSV files a HTML templates. This is the script that started [Gramener](http://gramener.com/) in 2011.
- `rename_receipts.py` renames PDF receipts to `YYYY-MM-DD Service $0.00 Card-1234.pdf` by extracting date, vendor, amount, and last-4 card details from invoice text. Moved to receipts folder.
