# AI Usage — Claude Code + Codex GNOME panel indicator

Show your **Claude Code** and **Codex (ChatGPT subscription)** usage in the Ubuntu GNOME panel. The compact readout looks like:

`[Claude logo] 17% | 21%    [OpenAI logo] 0% | 1%`

Each pair is **5-hour | 7-day quota used** (not tokens spent, money spent, or general ChatGPT chat quota). Claude uses its terracotta logo, OpenAI is monochrome, and panel numbers are regular-weight and colored by **time until reset** (not percentage used).

Click the indicator to see one line per quota window, with independently colored **usage** and **time remaining**:

`5h: 25% - 0:17 m - Mon 12 Oct 5:10 pm +08`

`7d: 22% - 3d 1h - Thu 15 Oct 6:00 pm +08`

Popup usage percentages are green below 70%, amber from 70% to below 90%, red at 90%+. Only the remaining-time portion of the popup is colored; the reset date/time stays neutral. The bottom bar percentages use the same reset-time colors. Reset time is green except: for 5h, amber at ≤1 hour and red at ≤30 minutes; for 7d, amber at ≤1 day and red at ≤12 hours. The popup also shows a larger last-successful-reading age, per-provider errors, **Refresh now**, and **Auto-refresh** (Off / 1 / 5 / 10 / 30 / 60 minutes; default 5). Time-remaining labels update every 30 seconds without making additional HTTP requests. A missing quota shows `—`, never a misleading 0%.

## Install (Ubuntu GNOME)

Requirements: GNOME Shell 45+; Bash, `curl`, `jq`, `flock` (`util-linux`), `glib-compile-schemas` (`libglib2.0-bin`), and `gnome-extensions`. Install **Claude Code** and **Codex CLI**, and log into the subscriptions you want monitored. The GNOME extension uses their local authentication, not an Anthropic/OpenAI API key.

With this repository checked out at `~/code/scripts` (including the two top-level CLI scripts):

```bash
cd ~/code/scripts/ai-usage
./install.sh
ccusage --json && codexusage --json
```

**Log out of the Ubuntu desktop and log back in** to load the extension's JavaScript. Logging out of Ubuntu is different from logging out of Claude/ChatGPT. If necessary, run `gnome-extensions enable ai-usage@sanand.net`. Look for the indicator in the GNOME top panel or wherever Dash-to-Panel places the system status area. Click it to change refresh settings.

**Claude automatic authentication:** `ccusage` can read your existing `~/.claude/.credentials.json` without modifying it, but that token expires. For unattended refreshing, run **once**:

```bash
ccusage --setup
```

Complete the browser sign-in. This creates a **separate** private Claude monitor profile under `~/.config/dock-stats/claude` and automatically rotates its own refresh token. Your main Claude Code login is untouched. If you already completed this setup, **do not repeat it**: updates and reinstallations reuse the existing profile. The monitor cannot guarantee indefinite authentication if Anthropic revokes an OAuth session; rerun setup only if the widget asks you to.

**Codex authentication:** Uses your existing `~/.codex/auth.json` as read-only input to a fast HTTP call, then falls back to Codex's app-server for authentication refresh/schema changes. Run `codex login` only if your session has expired or been revoked.

## Usage / maintenance

```bash
ccusage                # Human-readable Claude usage and resets
codexusage             # Human-readable Codex usage and resets
ccusage --json         # Machine-readable quota values
codexusage --json
./test.sh                # Offline tests; no real credentials/network
./install.sh             # Reinstall after updating this checkout
```

The indicator calls `~/code/scripts/ccusage` and `~/code/scripts/codexusage` directly. They remain on your PATH for interactive use. It uses two short-lived shell processes per refresh and no always-running daemon. Claude subscription usage and Codex's direct HTTP endpoint are undocumented and may change; the Codex app-server fallback uses its published interface. Credentials are not stored in extension settings or logs. No history logging is included.

To disable: `gnome-extensions disable ai-usage@sanand.net`. Re-enabling or reinstalling may require logging out and back in; avoid resetting **all** GNOME extensions, particularly with Vitals/Dash-to-Panel installed. To diagnose a failure, use `gnome-extensions info ai-usage@sanand.net` and `journalctl -b --no-pager | grep -A 10 'Extension ai-usage@sanand.net:' | tail -40`.

The extension source is flat in `ai-usage/`: `extension.js`, `format.js`, `metadata.json`, `stylesheet.css`, `icons/`, and `schemas/`. The SVG icons are from Simple Icons (CC0). `format.js` holds testable countdown and color thresholds. `ccusage` and `codexusage` emit `{provider,checked_at,windows:{"5h":{used_percent,resets_at},"7d":...}}`; unavailable windows are null. Claude resets use ISO 8601, Codex Unix seconds. Both are displayed in your local timezone.
