#!/usr/bin/env bash
# Usage:
#   ./setup.sh       -- sets up systemd services (if required) and reports status
#   ./setup.sh check -- reports timer health without changing systemd state
#
#  1. Loop through all .service/.timer files next to this script
#  2. Link them to $HOME/.config/systemd/user if not already linked
#  3. Enable & start all .timer files (safe to re-run)
#  4. Print status of all .service/.timer files

set -euo pipefail
# Expand only if files exist
shopt -s nullglob

SCRIPT_DIR="$(dirname "$(realpath "$0")")"
cd "$SCRIPT_DIR"

DEST="$HOME/.config/systemd/user"

check_units() {
  local units=()
  local journal_args=()
  for f in *.service *.timer; do
    [[ -e "$f" ]] || continue
    [[ "$f" == *@.service ]] && continue
    units+=("${f##*/}")
    journal_args+=(-u "${f##*/}")
  done

  echo "== User timers =="
  systemctl --user list-timers --all || true
  echo

  echo "== Failed user units =="
  systemctl --user --failed || true
  echo

  if ((${#units[@]})); then
    echo "== Unit status =="
    systemctl --user status "${units[@]}" || true
    echo

    echo "== Recent warnings/errors =="
    journalctl --user --since "1 week ago" --no-pager \
      -g "Failed|FAILURE|failed|error|Error|warning|Warning|Input/output|Cannot" \
      "${journal_args[@]}" || true
  fi

  echo
  echo "== daily-activities prerequisites =="
  command -v nmcli >/dev/null && echo "nmcli: ok" || echo "nmcli: missing; bandwidth-heavy jobs will be skipped"
  command -v rsync >/dev/null && echo "rsync: ok" || echo "rsync: missing"
  command -v rclone >/dev/null && echo "rclone: ok" || echo "rclone: missing"
  [[ -r "$HOME/.config/rclone/rclone.conf" ]] && echo "rclone config: ok" || echo "rclone config: missing at $HOME/.config/rclone/rclone.conf"
  if [[ -n "${SSH_AUTH_SOCK:-}" && -S "${SSH_AUTH_SOCK:-}" ]]; then
    echo "ssh agent: $SSH_AUTH_SOCK"
  else
    echo "ssh agent: not imported; daily-activities will try common user-session sockets"
  fi
}

if [[ "${1-}" == "check" ]]; then
  check_units
  exit 0
elif [[ $# -gt 0 ]]; then
  echo "Usage: $0 [check]" >&2
  exit 2
fi

mkdir -p "$DEST"

# Link .service/.timer files only if needed
for f in *.service *.timer; do
  base="${f##*/}"; target="$DEST/$base"; src="$SCRIPT_DIR/$f"
  if [[ -L "$target" ]]; then
    if [[ "$(readlink -f "$target")" != "$src" ]]; then
      rm -f "$target"
      systemctl --user link "$src" >/dev/null
    fi
  elif [[ ! -e "$target" ]]; then
    systemctl --user link "$src" >/dev/null
  else
    echo "Refusing to overwrite existing non-symlink unit: $target" >&2
    echo "Move it aside or replace it with a symlink to: $src" >&2
    exit 1
  fi
done

# Reload user manager to pick up changes
systemctl --user daemon-reload

# Enable & start timers (safe to re-run)
for t in *.timer; do
  [[ -e "$t" ]] || continue
  systemctl --user enable --now "${t##*/}" >/dev/null
done

# Enable & start stand-alone services (no matching timer)
standalone_services=()
for s in *.service; do
  [[ -e "$s" ]] || continue
  [[ -e "${s%.service}.timer" ]] && continue
  [[ "$s" == *@.service ]] && continue
  standalone_services+=("${s##*/}")
  systemctl --user enable --now "${s##*/}" >/dev/null
done

check_units

# Log:
# journalctl --user --since $(date -I  --date="1 week ago") -u $SERVICE

# Failures
# systemctl --user --failed

# Disable services by masking them
# systemctl --user stop $SERVICE
# systemctl --user disable $SERVICE
