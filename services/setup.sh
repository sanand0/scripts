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

# Enable & start stand-alone services (no matching timer)
standalone_services=()
for s in *.service; do
  [[ -e "$s" ]] || continue
  [[ -e "${s%.service}.timer" ]] && continue
  standalone_services+=("${s##*/}")
  systemctl --user enable --now "${s##*/}" >/dev/null || true
done

# Print status of timers
systemctl list-timers --user --all

# Print status of stand-alone services (if any)
if ((${#standalone_services[@]})); then
  systemctl --user status "${standalone_services[@]}" || true
fi

# Log:
# journalctl --user --since $(date -I  --date="1 week ago") -u $SERVICE

# Disable services by masking them
# systemctl --user stop $SERVICE
# systemctl --user disable $SERVICE
