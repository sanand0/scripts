---
name: anand-laptops
description: Locate and use Anand's files, projects, notes, archives and agent history on his laptops - graphene (Linux) and Plutonium (Windows, usually online) - which share one ~/ layout. Use before reading or searching his files via LocalMCP2, Remote Desktop Commander or a local shell.
---

# Machines

- **Prefer graphene** (Linux) when it's online. It's the primary machine, and its scheduled jobs keep the snapshots and the context index fresh.
- **Use Plutonium** (Windows) when graphene is offline, e.g. while Anand travels.
  - It has the same `~/...` layout, but its `~/Documents` and `~/r2` may be missing or older.
  - Name the sources you couldn't reach. Unreachable is not the same as absent.
- Prefer **LocalMCP2** - which reaches only the graphene folders it was started with. Its `~` is `/home/vscode`, aliased to `/home/sanand`. A missing path there may just be unmounted.
- **Remote Desktop Commander** reaches both machines, so pick the device explicitly.
- **Paths:**
  - When passing a path to a program, write `"$HOME/..."`. That works in bash and in PowerShell; Windows PowerShell 5.1 doesn't expand `~` for programs.
  - Desktop Commander's file tools accept `~/...` on both machines.
  - On Plutonium, avoid Cygwin bash: Windows programs can't open its `/home/...` paths.
- **Sync:**
  - `~/Dropbox` syncs live. On Plutonium only `C:\Dropbox` is live, so ignore dated or backup copies.
  - `~/code` holds separate git checkouts on each machine. Check branch and status; push from one machine and fetch on the other.
  - `~/Documents`, `~/r2`, agent sessions and browser state are per machine.

# Starting points

Read `~/code/scripts/agents/AGENTS.md` for coding, shell, or filesystem-modification tasks: it sets tool preferences and working rules, and remote sessions don't load it.

- **Unclear or cross-source:** `uv run "$HOME/code/scripts/context.py" search '…'`, if `~/Documents/data/context/` exists.
  - Other subcommands: `entity`, `recent`, `open-loops`, `thread`, `style`, `assets`.
  - Hits are candidates, so deep-read the `~/...` locator.
  - `status` shows each source's latest item. The index can be fresh while a source is weeks old.
- **Code, projects:** `~/code/README.md` (repo index; if absent, list `~/code`), then the repo's `README.md` and `AGENTS.md`.
- **Blog, talks, demos, evals, data stories:**
  - `~/code/blog/description.md` (one line per post)
  - `~/code/talks/README.md`
  - `~/code/llmdemos/config.json`
  - `~/code/datastories/config.json`
  - `~/code/llmevals/README.md`
  - `~/code/til/README.md`
- **Notes, people, meetings, tasks:** `~/Dropbox/notes/`, especially `about/<person>.md`, `transcripts/` (date-named), `weekly-tasks.md` and `daily-*.md`.
- **Mail, chat, calendar, Drive:**
  - Live: `gws`. The default account is s.anand@straive.com.
  - For root.node@gmail.com or anand@study.iitm.ac.in, set `GOOGLE_WORKSPACE_CLI_CONFIG_DIR` to `~/.config/gws-<account>`.
  - Confirm the account before any write. Setup: `~/Dropbox/notes/gws-cli.md`.
  - History: `~/Documents/data/<account>/` covers mail, chat and calendar. For Drive, use `gws`.
  - Older mail: `~/Documents/Mail/` (its README explains the index).
- **WhatsApp, browsing, LinkedIn:** `~/Documents/data/README.md` lists each archive and the script that builds it.
- **ChatGPT and Claude conversations:** `~/Documents/chatgpt/`, `~/Documents/claude/`.
- **Coding-agent sessions:** `uv run "$HOME/code/scripts/agentlog.py" {codex,claude,copilot}`, on each machine.
- **Daily activity:** `~/Documents/activities/`.
- **Large files, media:** `~/r2/{files,media,private}/`.
- **Setup, personal CLIs:** `~/code/scripts/README.md`, `~/code/scripts/setup/{linux,windows}.md`, `~/Dropbox/scripts/`.
- **Browser control (graphene):** the `devtools` skill.

# Answering

Label each source as one of:

- **live** (`gws`)
- **snapshot**, with its date
- **index hit**, not yet deep-read
- **inference**
