#!/usr/bin/env bash
# Hourly Graphene -> Plutonium Documents sync; update changed files, never delete.
set -Eeuo pipefail
umask 077
export LC_ALL=C

cache="$HOME/.cache/sanand-scripts/sync-plutonium"
mkdir -p "$cache"
exec 9>"$cache/run.lock"
if ! flock -n 9; then
  printf '🟠 %s SKIP reason=already-running\n' "$(date -Is)" | tee -a "$cache/run.log"
  exit 0
fi

mode=apply
dry_run=()
case "${1:-}" in
  "") ;;
  --dry-run) mode=dry-run; dry_run=(--dry-run) ;;
  *) printf 'Usage: %s [--dry-run]\n' "$0" >&2; exit 2 ;;
esac

started=$(date +%s)
status=ok
source_files=0
transferred_files=0
transferred_bytes=0
sent_bytes=0
received_bytes=0

log() {
  printf '%s %s %s\n' "$1" "$(date -Is)" "$2" | tee -a "$cache/run.log"
}

human() {
  numfmt --to=iec --suffix=B "$1"
}

work=$(mktemp -d "${XDG_RUNTIME_DIR:-/tmp}/sync-plutonium.XXXXXXXX")
finish() {
  local rc=$1 marker='🟢' label=transferred
  trap - EXIT
  if (( rc != 0 )); then
    marker='🔴'
    status=failed
  elif [[ "$status" == skipped ]]; then
    marker='🟠'
  fi
  [[ "$mode" == dry-run ]] && label=would_transfer
  log "$marker" "END status=$status mode=$mode elapsed=$(($(date +%s)-started))s source_files=$source_files ${label}_files=$transferred_files ${label}_data=$(human "$transferred_bytes") sent=$(human "$sent_bytes") received=$(human "$received_bytes")"
  rm -rf -- "$work"
}
trap 'finish $?' EXIT
trap 'rc=$?; log "🔴" "ERROR line=$LINENO exit=$rc command=$BASH_COMMAND"' ERR

log '🟢' "START mode=$mode from=~/Documents/ to=plutonium:C:/Documents/ policy=update-no-delete"

# Same metered-network safeguard as the other services.
if [[ "${SYNC_DOCUMENTS_ALLOW_METERED:-0}" != 1 ]]; then
  unmetered=0
  if ! command -v nmcli >/dev/null; then
    log '🟠' "SKIP reason=nmcli-unavailable (override: SYNC_DOCUMENTS_ALLOW_METERED=1)"
    status=skipped; exit 0
  fi
  while IFS=: read -r dev kind connection; do
    [[ "$connection" == connected* && ( "$kind" == wifi || "$kind" == ethernet ) ]] || continue
    metered="$(nmcli -g GENERAL.METERED device show "$dev" 2>/dev/null | head -1)"
    [[ "$metered" == no* ]] && unmetered=1
    [[ "$metered" == yes* ]] && { unmetered=0; break; }
  done < <(nmcli -t -f DEVICE,TYPE,STATE device status)
  if [[ "$unmetered" != 1 ]]; then
    log '🟠' "SKIP reason=metered-or-unknown-network (override: SYNC_DOCUMENTS_ALLOW_METERED=1)"
    status=skipped; exit 0
  fi
fi

# Reject unsafe Windows names, case collisions and symlinks outside Documents.
# The two existing Codex node_modules links point to regular files inside the
# tree; --copy-links copies their contents (not Windows symlinks).
if ! python3 - "$HOME/Documents" >"$work/check.log" 2>&1 <<'PY'
import os, re, sys
from collections import Counter
from pathlib import Path

root = Path(sys.argv[1]).resolve()
for base, dirs, files in os.walk(root, followlinks=False):
    names = dirs + files
    folded = Counter(n.casefold() for n in names)
    for name in names:
        path = Path(base, name)
        stem = name.rstrip(" .").split(".")[0].upper()
        reserved = stem in {"CON", "PRN", "AUX", "NUL"} or bool(re.fullmatch(r"(COM|LPT)[1-9]", stem))
        if (any(c in name for c in '<>:"\\|?*') or name.endswith((" ", "."))
            or reserved or folded[name.casefold()] > 1):
            sys.exit(f"Unsafe Windows name or case collision: {path.relative_to(root)}")
        if path.is_symlink():
            target = path.resolve(strict=True)
            if not target.is_relative_to(root) or not target.is_file():
                sys.exit(f"Unsafe symlink target: {path.relative_to(root)} -> {target}")
PY
then
  log '🔴' "ERROR NTFS-compatibility $(head -n 5 "$work/check.log" | tr '\n' ' ')"
  exit 2
fi

if ! ssh-keyscan -4 -T 8 -t ed25519 plutonium >"$work/known_hosts" 2>"$work/ssh.err"; then
  log '🔴' "ERROR SSH host=plutonium reason=key-scan-failed detail=$(head -c 250 "$work/ssh.err")"
  exit 3
fi
fingerprint="$(ssh-keygen -lf "$work/known_hosts" | awk 'NR==1 {print $2}')"
if [[ "$fingerprint" != 'SHA256:cgUJptFBdGsAIuWotxjZk8Y1bZtD+ZjfLdvGqQIrv3Q' ]]; then
  log '🔴' "ERROR SSH host=plutonium reason=host-key-mismatch got=$fingerprint"
  exit 3
fi
ssh_cmd="ssh -F /dev/null -i $HOME/Dropbox/scripts/.ssh/id_rsa -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=$work/known_hosts -o ConnectTimeout=15 -o ServerAliveInterval=30 -o ServerAliveCountMax=3"

stat_value() {
  awk -F ': ' -v label="$1" '$1 == label {
    split($2, fields, /[[:space:]]+/)
    gsub(/,/, "", fields[1])
    print fields[1]
    seen=1
    exit
  } END {if (!seen) print 0}' "$2"
}
details() {
  local text
  text="$(grep -iE 'rsync:|ssh:|permission denied|failed|error|no such file|connection|invalid|vanished' "$work/rsync.log" | tail -n 12 || true)"
  [[ -n "$text" ]] || text="$(tail -n 12 "$work/rsync.log")"
  while IFS= read -r line; do
    [[ -n "$line" ]] && log '🔴' "DETAIL $line"
  done <<<"$text"
}

# One whole-tree sync. No --delete: Plutonium-only files are preserved.
if rsync -rlt --copy-links --partial-dir=.rsync-partial \
     --no-perms --no-owner --no-group --omit-dir-times \
     --exclude='.rsync-partial/' --timeout=300 --stats \
     --rsync-path='C:/cygwin/bin/rsync.exe' -e "$ssh_cmd" \
     "${dry_run[@]}" "$HOME/Documents/" "Anand@plutonium:/cygdrive/c/Documents/" \
     >"$work/rsync.log" 2>&1; then
  :
else
  code=$?
  log '🔴' "ERROR rsync_exit=$code"
  details
  exit "$code"
fi

source_files=$(stat_value 'Number of files' "$work/rsync.log")
transferred_files=$(stat_value 'Number of regular files transferred' "$work/rsync.log")
transferred_bytes=$(stat_value 'Total transferred file size' "$work/rsync.log")
sent_bytes=$(stat_value 'Total bytes sent' "$work/rsync.log")
received_bytes=$(stat_value 'Total bytes received' "$work/rsync.log")
