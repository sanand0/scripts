# Setup

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

See [`ai-code-rules/`](ai-code-rules/README.md) for setting up AI code editors.

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

- [ask](ask) records a short voice note, sends it to `llm` for custom action (transcribe, bash code, fish code, ...), copies to clipboard
- [askwin](askwin) calls [ask](ask) and pastes on window we called it from. Triggered by Ctrl + Alt + 0
- [chars](chars) lists non-ASCII characters in files.
- [copy-to-markdown.sh](copy-to-markdown.sh) converts clipboard rich text (HTML) to Markdown in clipboard. Usage: Ctrl + C, then Ctrl + Alt + C
- [dev.sh](dev.sh) runs a development container for safer experimentation.
  - [dev.dockerfile](dev.dockerfile) contains the image spec.
  - [dev.test.sh](dev.test.sh) tests the environment for tools.
- [consolidate_transcripts.py](consolidate_transcripts.py) aggregates lessons from my call transcript into a unified transcripts.md.
- [daydream](daydream) fuses recalled concepts into radical ideas. Example: `daydream -c llm -c oblique-strategies "web app"`
- [discourse.py](discourse.py) extracts recent posts from a Discourse category or topic.
- [gitget](gitget) clones a git repository and copies specific paths to local directories.
- [git-uncommitted](git-uncommitted) lists directories not git-synced with remote
- [githubscore.py](githubscore.py) evaluates GitHub developer quality
- [gmail](gmail.py): Gmail search CLI. Uses OAuth tokens from [google_oauth.py](google_oauth.py)
- [histfreq](histfreq) ranks the most common commands from a NUL-delimited shell history stream. `history --null | uv run histfreq.py -n 40`
- [q](q) is a terminal AI chat interface. `q 'What is 2 + 2?' --llm chatgpt` opens Google AI mode, asks the question, and prints the answer. `q --m chatgpt 'What is 2 + 2?'` does the same with ChatGPT.
- [recall](recall) shows a random note bullet. Example: `recall` or `recall talks`
- [rgb](rgb) converts RGB to hex and vice versa.
- [rofi-files.sh](rofi-files.sh) and [rofi-chrome-tabs.sh](rofi-chrome-tabs.sh) are used by rofi to get recent files.
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
- [update-files](update-files) caches directory listings so `rofi-files.sh` can stay fast even on large mounts.
- [viz.py](viz.py) embeds CSV files a HTML templates. This is the script that started [Gramener](http://gramener.com/) in 2011.

## AI coding agent scripts

- [codexlog.jq](codexlog.jq) converts Codex CLI session logs to Markdown (from ~/.codex/sessions/yyyy/mm/dd/session.jsonl)
  - [codexlist](codexlist) lists all sessions
  - [codextools.py](codextools.py) lists tools used by Codex
  - [codexerrors.py](codexerrors.py) lists tool errors by Codex
- [claudelog.jq](claudelog.jq) converts Claude Code session logs to Markdown (from ~/.claude/projects/$path/\*.jsonl)
  - [claudelist](claudelist) lists all sessions
- [copilotlog.jq](copilotlog.jq) converts GitHub session logs to Markdown (from ~/.copilot/session-state/*.jsonl)
  - [copilotlist](copilotlist) lists all sessions
- [opencodelog.jq](opencodelog.jq) converts OpenCode session logs to Markdown (from `opencode export sessionID`)

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
- `rclone-hetzner.service`: Mount Hetzner cloud storage at `/mnt/hetzner/` on boot
- `trending-repo-weekly.*`: Update trending GitHub repos
- `update-files-daily.*`: Update local files
- `update-files-weekly.*`: Update mounted files
