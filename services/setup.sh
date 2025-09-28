#!/usr/bin/env bash
# Usage: ./setup.sh -- sets up systemd services (if required) and report status
#
#  1. Loop through all .service/.timer files in the current directory
#  2. Link them to $HOME/.config/systemd/user if not already linked
#  3. Enable & start all .timer files (safe to re-run)
#  4. Print status of all .service/.timer files

set -euo pipefail
# Expand only if files exist
shopt -s nullglob

DEST="$HOME/.config/systemd/user"
mkdir -p "$DEST"

# Link .service/.timer files only if needed
for f in *.service *.timer; do
  base="${f##*/}"; target="$DEST/$base"; src="$PWD/$f"
  if [[ -L "$target" ]]; then
    [[ "$(readlink -f "$target")" == "$src" ]] || { rm -f "$target"; systemctl --user link "$src" >/dev/null; }
  elif [[ ! -e "$target" ]]; then
    systemctl --user link "$src" >/dev/null
  fi
done

# Reload user manager to pick up changes
systemctl --user daemon-reload

# Enable & start timers (safe to re-run)
for t in *.timer; do
  [[ -e "$t" ]] || continue
  systemctl --user enable --now "${t##*/}" >/dev/null || true
done

# Print status of timers
for t in *.timer; do
  systemctl --user status "${t##*/}"
done

# Print logs of services
for t in *.service; do
  journalctl --user -u "${t##*/}" -n 5
done
