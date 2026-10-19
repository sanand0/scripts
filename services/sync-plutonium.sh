#!/usr/bin/env bash
# Hourly additive Graphene -> Plutonium sync of NTFS-safe Documents directories.
# Existing destination files are never changed; no files are deleted or renamed.
set -Eeuo pipefail
umask 077

cache="$HOME/.cache/sanand-scripts/sync-plutonium"
mkdir -p "$cache"
exec 9>"$cache/run.lock"
flock -n 9 || { echo "sync-plutonium: already running"; exit 0; }
exec > >(tee -a "$cache/run.log") 2>&1

dry_run=()
case "${1:-}" in
  "") ;;
  --dry-run) dry_run=(--dry-run) ;;
  *) echo "Usage: $0 [--dry-run]" >&2; exit 2 ;;
esac

echo "=== $(date -Is) sync-plutonium start ${dry_run[*]:-apply} ==="

# Consistent with daily-activities: don't silently use mobile/metered data.
if [[ "${SYNC_DOCUMENTS_ALLOW_METERED:-0}" != 1 ]]; then
  unmetered=0
  while IFS=: read -r dev kind status; do
    [[ "$status" == connected* && ( "$kind" == wifi || "$kind" == ethernet ) ]] || continue
    metered="$(nmcli -g GENERAL.METERED device show "$dev" 2>/dev/null | head -1)"
    [[ "$metered" == no* ]] && unmetered=1
    [[ "$metered" == yes* ]] && { unmetered=0; break; }
  done < <(nmcli -t -f DEVICE,TYPE,STATE device status)
  if [[ "$unmetered" != 1 ]]; then
    echo "SKIP: metered or unknown network (override: SYNC_DOCUMENTS_ALLOW_METERED=1)"
    exit 0
  fi
fi

# Confirm the server key against its independently verified fingerprint.
known_hosts="$(mktemp "$cache/known_hosts.XXXXXX")"
trap 'rm -f "$known_hosts"' EXIT
ssh-keyscan -4 -T 8 -t ed25519 plutonium 2>/dev/null >"$known_hosts"
fingerprint="$(ssh-keygen -lf "$known_hosts" | awk 'NR==1 {print $2}')"
[[ "$fingerprint" == "SHA256:cgUJptFBdGsAIuWotxjZk8Y1bZtD+ZjfLdvGqQIrv3Q" ]] || {
  echo "FAIL: unrecognized Plutonium SSH host key $fingerprint"; exit 3;
}
ssh_cmd="ssh -F /dev/null -i $HOME/Dropbox/scripts/.ssh/id_rsa -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=$known_hosts -o ConnectTimeout=15 -o ServerAliveInterval=30 -o ServerAliveCountMax=3"

# Initial large-copy whitelist. Excluded folders require NTFS/conflict reconciliation.
folders=(
  Mail site books docs talks gitlab infy comics bcg audio archive
  Takeout chatgpt-images claude claude-gramener screenplays sutd
  llmfoundry twitter newsboat whatsapp activities gramener Zoom
)

errors=0
for folder in "${folders[@]}"; do
  src="$HOME/Documents/$folder"
  [[ -d "$src" ]] || { echo "SKIP missing: $folder"; errors=1; continue; }

  # Fail closed if a previously safe folder gains an NTFS-invalid name,
  # case collision, Windows-reserved name, or symlink.
  if ! python3 - "$src" <<'PY'
import os, re, sys
from collections import Counter
from pathlib import Path
root = Path(sys.argv[1])
bad = []
for base, dirs, files in os.walk(root, followlinks=False):
    names = dirs + files
    folded = Counter(name.casefold() for name in names)
    for name in names:
        path = Path(base, name)
        stem = name.rstrip(" .").split(".")[0].upper()
        reserved = stem in {"CON", "PRN", "AUX", "NUL"} or bool(re.fullmatch(r"(COM|LPT)[1-9]", stem))
        if (any(c in name for c in '<>:"\\|?*') or name.endswith((" ", "."))
            or reserved or path.is_symlink() or folded[name.casefold()] > 1):
            bad.append(str(path.relative_to(root)))
            if len(bad) == 3:
                break
    if bad:
        break
if bad:
    print(f"NTFS-incompatible entries in {root.name}: {bad}", file=sys.stderr)
    sys.exit(1)
PY
  then
    echo "SKIP $folder: incompatible filenames (fix source before sync)"
    errors=1
    continue
  fi

  echo "--- $(date -Is) $folder start ---"
  if rsync -rlt --ignore-existing --partial-dir=.rsync-partial \
      --no-perms --no-owner --no-group --omit-dir-times \
      --exclude='.rsync-partial/' --timeout=300 \
      --itemize-changes --stats \
      --rsync-path='C:/cygwin/bin/rsync.exe' -e "$ssh_cmd" \
      "${dry_run[@]}" "$src/" "Anand@plutonium:/cygdrive/c/Documents/$folder/"; then
    echo "--- $(date -Is) $folder ok ---"
  else
    code=$?
    echo "--- $(date -Is) $folder FAILED exit=$code ---"
    errors=1
  fi
done

echo "=== $(date -Is) sync-plutonium end errors=$errors ==="
exit "$errors"
