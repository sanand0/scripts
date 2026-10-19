#!/usr/bin/env bash
# Hourly additive Graphene -> Plutonium sync. No destination deletes or overwrites.
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

folders=(
  Mail site books docs talks gitlab infy comics bcg audio archive
  Takeout chatgpt-images claude claude-gramener screenplays sutd
  llmfoundry twitter newsboat whatsapp activities gramener Zoom
)
started=$(date +%s)
total=${#folders[@]}
ok=0
failed=0
skipped=0
new_files=0
new_bytes=0
sent_bytes=0
received_bytes=0
status=ok

log() {
  printf '%s %s %s\n' "$1" "$(date -Is)" "$2" | tee -a "$cache/run.log"
}

human() {
  numfmt --to=iec --suffix=B "$1"
}

# All normal output goes through log(); rsync diagnostics are captured separately.
work=$(mktemp -d "${XDG_RUNTIME_DIR:-/tmp}/sync-plutonium.XXXXXXXX")
finish() {
  local rc=$1 marker label
  trap - EXIT
  if (( rc != 0 || failed > 0 )); then
    status=failed; marker='🔴'
  elif [[ "$status" == skipped ]]; then
    marker='🟠'
  else
    marker='🟢'
  fi
  label=new
  [[ "$mode" == dry-run ]] && label=would_add
  log "$marker" "END status=$status mode=$mode elapsed=$(($(date +%s)-started))s folders=$ok/$total failed=$failed skipped=$skipped ${label}_files=$new_files ${label}_data=$(human "$new_bytes") sent=$(human "$sent_bytes") received=$(human "$received_bytes")"
  rm -rf -- "$work"
}
trap 'finish $?' EXIT
unexpected() {
  local code="$1" line="$2" command="$3"
  ((failed+=1))
  log '🔴' "ERROR unexpected_exit=$code line=$line command=$command"
}
trap 'unexpected "$?" "$LINENO" "$BASH_COMMAND"' ERR

log '🟢' "START mode=$mode from=~/Documents/ to=plutonium:C:/Documents/ folders=$total policy=add-only"

# Avoid using mobile/metered bandwidth, matching daily-activities.
if [[ "${SYNC_DOCUMENTS_ALLOW_METERED:-0}" != 1 ]]; then
  unmetered=0
  if ! command -v nmcli >/dev/null; then
    log '🟠' "SKIP reason=nmcli-unavailable (set SYNC_DOCUMENTS_ALLOW_METERED=1 to override)"
    skipped=$total; status=skipped; exit 0
  fi
  while IFS=: read -r dev kind connection; do
    [[ "$connection" == connected* && ( "$kind" == wifi || "$kind" == ethernet ) ]] || continue
    metered="$(nmcli -g GENERAL.METERED device show "$dev" 2>/dev/null | head -1)"
    [[ "$metered" == no* ]] && unmetered=1
    [[ "$metered" == yes* ]] && { unmetered=0; break; }
  done < <(nmcli -t -f DEVICE,TYPE,STATE device status)
  if [[ "$unmetered" != 1 ]]; then
    log '🟠' "SKIP reason=metered-or-unknown-network (set SYNC_DOCUMENTS_ALLOW_METERED=1 to override)"
    skipped=$total; status=skipped; exit 0
  fi
fi

if ! ssh-keyscan -4 -T 8 -t ed25519 plutonium >"$work/known_hosts" 2>"$work/ssh.err"; then
  ((failed+=1))
  log '🔴' "ERROR SSH host=plutonium reason=key-scan-failed detail=$(head -c 250 "$work/ssh.err")"
  exit 3
fi
fingerprint="$(ssh-keygen -lf "$work/known_hosts" | awk 'NR==1 {print $2}')"
if [[ "$fingerprint" != 'SHA256:cgUJptFBdGsAIuWotxjZk8Y1bZtD+ZjfLdvGqQIrv3Q' ]]; then
  ((failed+=1))
  log '🔴' "ERROR SSH host=plutonium reason=host-key-mismatch got=$fingerprint"
  exit 3
fi
ssh_cmd="ssh -F /dev/null -i $HOME/Dropbox/scripts/.ssh/id_rsa -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=$work/known_hosts -o ConnectTimeout=15 -o ServerAliveInterval=30 -o ServerAliveCountMax=3"

stat_value() {
  awk -F ': ' -v label="$1" '$1 == label {
    split($2, fields, /[[:space:]]+/)
    value = fields[1]
    gsub(/,/, "", value)
    print value
    seen=1
    exit
  } END {if (!seen) print 0}' "$2"
}
details() {
  # Capture enough context to diagnose the failure without flooding the log.
  local file="$1" text
  text="$(grep -iE 'rsync:|ssh:|permission denied|failed|error|no such file|connection|invalid|vanished' "$file" | tail -n 12 || true)"
  [[ -n "$text" ]] || text="$(tail -n 12 "$file")"
  while IFS= read -r line; do
    [[ -n "$line" ]] && log '🔴' "DETAIL $line"
  done <<<"$text"
}

for folder in "${folders[@]}"; do
  src="$HOME/Documents/$folder"
  if [[ ! -d "$src" ]]; then
    log '🔴' "ERROR folder=$folder reason=source-directory-missing"
    ((failed+=1))
    continue
  fi

  # Fail closed if the source has an NTFS-invalid name, collision, or symlink.
  if ! python3 - "$src" >"$work/check.log" 2>&1 <<'PY'
import os, re, sys
from collections import Counter
from pathlib import Path
root = Path(sys.argv[1])
for base, dirs, files in os.walk(root, followlinks=False):
    names = dirs + files
    folded = Counter(n.casefold() for n in names)
    for name in names:
        path = Path(base, name)
        stem = name.rstrip(" .").split(".")[0].upper()
        reserved = stem in {"CON", "PRN", "AUX", "NUL"} or bool(re.fullmatch(r"(COM|LPT)[1-9]", stem))
        if (any(c in name for c in '<>:"\\|?*') or name.endswith((" ", "."))
            or reserved or path.is_symlink() or folded[name.casefold()] > 1):
            print(f"{path.relative_to(root)}: incompatible name, symlink, or case collision", file=sys.stderr)
            sys.exit(1)
PY
  then
    log '🟠' "SKIP folder=$folder reason=NTFS-name-check-failed"
    ((skipped+=1))
    while IFS= read -r line; do
      [[ -n "$line" ]] && log '🔴' "DETAIL folder=$folder $line"
    done < <(head -n 12 "$work/check.log")
    ((failed+=1))
    continue
  fi

  if rsync -rlt --ignore-existing --partial-dir=.rsync-partial \
       --no-perms --no-owner --no-group --omit-dir-times \
       --exclude='.rsync-partial/' --timeout=300 --stats \
       --rsync-path='C:/cygwin/bin/rsync.exe' -e "$ssh_cmd" \
       "${dry_run[@]}" "$src/" "Anand@plutonium:/cygdrive/c/Documents/$folder/" \
       >"$work/rsync.log" 2>&1; then
    ((ok+=1))
  else
    code=$?
    log '🔴' "ERROR folder=$folder rsync_exit=$code"
    details "$work/rsync.log"
    ((failed+=1))
    continue
  fi
  new_files=$((new_files + $(stat_value 'Number of regular files transferred' "$work/rsync.log")))
  new_bytes=$((new_bytes + $(stat_value 'Total transferred file size' "$work/rsync.log")))
  sent_bytes=$((sent_bytes + $(stat_value 'Total bytes sent' "$work/rsync.log")))
  received_bytes=$((received_bytes + $(stat_value 'Total bytes received' "$work/rsync.log")))
done

if (( failed > 0 )); then
  exit 1
fi
