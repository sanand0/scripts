#!/usr/bin/bash

# Restore Dash-to-Panel after locking/unlocking the screen.
#
# Symptom and usage:
# - After screen lock/blank, Gnome extensions are disabled (grey, not orange)
#   even though they show they're enabled.
# - Run this script (bound to Ctrl+Alt+U) after unlocking when that happens.
#
# Why this is not a simple "restart every extension":
# - Dash-to-Panel owns panel actors also used by extensions such as
#   AppIndicators and Vitals. Tearing down all extensions at once caused those
#   extensions to access already-disposed actors. On 2026-06-06 that race
#   repeatedly segfaulted GNOME Shell and displayed the "Oh no!" screen.
# - Dependencies must stop before Dash-to-Panel and start after it. The sleeps
#   let asynchronous callbacks settle before the next panel teardown/rebuild.
# - I added some sleep commands (guessing required timings) to reduce race risk.
# - flock drops overlapping invocations, which previously made the race easier
#   to trigger when the shortcut was pressed more than once.
#
# Incident evidence: /home/sanand/code/infra/gnome-crash/incident-20260606-154057
# Original context: https://claude.ai/chat/9f993bc0-ba50-46e0-b0d5-38a77c0b8621

# Use a stable per-user lock path so only one panel rebuild runs at a time.
exec 9>/tmp/dock-sh.lock
/usr/bin/flock -n 9 || exit 0

# Disable extensions
/usr/bin/gnome-extensions disable "Vitals@CoreCoding.com"
sleep 0.2
/usr/bin/gnome-extensions disable "ubuntu-appindicators@ubuntu.com"
sleep 0.2
/usr/bin/gnome-extensions disable "emoji-copy@felipeftn"
sleep 0.2
/usr/bin/gnome-extensions disable "clipboard-history@alexsaveau.dev"
sleep 0.2
/usr/bin/gnome-extensions disable "dash-to-panel@jderose9.github.com"
sleep 1

# Enable extensions
/usr/bin/gnome-extensions enable "dash-to-panel@jderose9.github.com"
sleep 1
/usr/bin/gnome-extensions enable "clipboard-history@alexsaveau.dev"
sleep 0.2
/usr/bin/gnome-extensions enable "emoji-copy@felipeftn"
sleep 0.2
/usr/bin/gnome-extensions enable "ubuntu-appindicators@ubuntu.com"
sleep 0.2
/usr/bin/gnome-extensions enable "Vitals@CoreCoding.com"
