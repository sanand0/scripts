#!/usr/bin/env bash
# Hourly Graphene -> Plutonium sync; update changed files, never delete.
set -Eeuo pipefail
umask 077
export LC_ALL=C

# Archive Graphene's agent data under C:\graphene\, separate from live agent state.
GRAPHENE_DIRS=(
  .codex/sessions
  .codex/archived_sessions
  .codex/memories
  .claude/projects
  .claude/todos
  .copilot/session-state
)
GRAPHENE_FILES=(
  .codex/history.jsonl
  .codex/config.toml
  .claude/history.jsonl
  .claude/settings.json
  .claude/CLAUDE.md
)
# The Copilot session-store.db gets a consistent SQLite snapshot.

# Mirror these home-relative paths as-is into C:\ on Plutonium.
SYNC_DIRS=(
  r2
  code/tds-network-games/.private
  code/exam/dumps
  code/exam/.private
)
SYNC_FILES=(
  code/exam/.env
  code/exam/.dev.vars
  code/tds-network-games/.dev.vars
  code/scripts/.env
)

# Re-creatable Linux dependencies and tool caches. Match directory names at
# any depth in both the preflight validator and every rsync transfer.
SKIP_DIRS=(
  '.venv*'
  venv
  node_modules
  __pycache__
  .pytest_cache
  .ruff_cache
  .mypy_cache
  .wrangler
  .cloudflare
  .rsync-partial
)

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

log '🟢' "START mode=$mode targets=C:/Documents/,C:/graphene/,C:/code/,C:/r2/ policy=update-no-delete"

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

# All listed sources must exist; avoid silently incomplete backups.
validate_sources=("$HOME/Documents")
for relative in "${GRAPHENE_DIRS[@]}" "${SYNC_DIRS[@]}"; do
  if [[ ! -d "$HOME/$relative" ]]; then
    log '🔴' "ERROR missing-directory=~/$relative"
    exit 2
  fi
  validate_sources+=("$HOME/$relative")
done
for relative in "${GRAPHENE_FILES[@]}" "${SYNC_FILES[@]}"; do
  if [[ ! -f "$HOME/$relative" ]]; then
    log '🔴' "ERROR missing-file=~/$relative"
    exit 2
  fi
  validate_sources+=("$HOME/$relative")
done
if [[ ! -f "$HOME/.copilot/session-store.db" ]]; then
  log '🔴' "ERROR missing-file=~/.copilot/session-store.db"
  exit 2
fi

# Preserve Documents filenames containing ':' with Windows-safe '%3A' names.
# Other invalid names, case collisions and unsafe symlinks still fail the sync.
if ! python3 - "$work" "${SKIP_DIRS[@]}" -- "${validate_sources[@]}" >"$work/check.log" 2>&1 <<'PY_VALIDATE'
import fnmatch, os, re, sys
from collections import Counter
from pathlib import Path

work = Path(sys.argv[1])
split = sys.argv.index("--")
skip_dirs = sys.argv[2:split]
roots = [Path(arg).resolve() for arg in sys.argv[split + 1:]]
documents = roots[0]
renames = []
for root in roots:
    if root.is_file():
        if any(c in root.name for c in '<>:"\\|?*'):
            sys.exit(f"Unsafe Windows filename: {root}")
        continue
    for base, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs
                   if not any(fnmatch.fnmatchcase(d, pattern) for pattern in skip_dirs)]
        names = dirs + files
        folded = Counter(n.casefold() for n in names)
        for name in names:
            path = Path(base, name)
            stem = name.rstrip(" .").split(".")[0].upper()
            reserved = stem in {"CON", "PRN", "AUX", "NUL"} or bool(re.fullmatch(r"(COM|LPT)[1-9]", stem))
            forbidden = any(c in name for c in '<>:"\\|?*')
            trailing = name.endswith((" ", "."))
            collision = folded[name.casefold()] > 1
            if (forbidden or trailing or reserved or collision):
                # Only rename ordinary Documents files with colons, not directories.
                safe = name.replace(":", "%3A")
                if (root == documents and name in files and ":" in name
                    and not any(c in name for c in '<>"\\|?*')
                    and not trailing and not reserved and not collision
                    and "\n" not in name and "\r" not in name
                    and safe.casefold() not in folded):
                    rel = path.relative_to(documents)
                    renames.append((rel, rel.with_name(safe), path))
                else:
                    sys.exit(f"Unsafe Windows name or case collision: {path}")
            if path.is_symlink():
                target = path.resolve(strict=True)
                if not target.is_relative_to(root) or not target.is_file():
                    sys.exit(f"Unsafe symlink target: {path} -> {target}")

exclude = work / "documents-excludes"
rename_log = work / "documents-renames.tsv"
with exclude.open("w") as exclusions, rename_log.open("w") as log:
    for rel, safe_rel, source in renames:
        # rsync exclude-from patterns are rooted at the Documents transfer root.
        pattern = "/" + str(rel).replace("[", r"\[").replace("]", r"\]")
        exclusions.write(pattern + "\n")
        target = work / "windows-renamed" / "Documents" / safe_rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(source)
        log.write(f"{rel}\t{safe_rel}\n")
PY_VALIDATE
then
  log '🔴' "ERROR NTFS-compatibility $(head -n 5 "$work/check.log" | tr '\n' ' ')"
  exit 2
fi
while IFS=$'\t' read -r src dst; do
  log '🟠' "NTFS-safe-name from=~/Documents/$src to=C:/Documents/$dst"
done <"$work/documents-renames.tsv"

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

# Apply the same directory exclusions in rsync and the preflight scanner.
exclude_args=()
for dir in "${SKIP_DIRS[@]}"; do
  exclude_args+=(--exclude="$dir/")
done

# Run one group at a time, preserving existing no-delete and logging behavior.
run_sync() {
  local label="$1" code
  shift
  if rsync -rlt --copy-links --partial-dir=.rsync-partial \
       --no-perms --no-owner --no-group --omit-dir-times \
       "${exclude_args[@]}" --timeout=300 --stats \
       --rsync-path='C:/cygwin/bin/rsync.exe' -e "$ssh_cmd" \
       "${dry_run[@]}" "$@" >"$work/rsync.log" 2>&1; then
    :
  else
    code=$?
    log '🔴' "ERROR group=$label rsync_exit=$code"
    details
    exit "$code"
  fi
  source_files=$((source_files + $(stat_value 'Number of files' "$work/rsync.log")))
  transferred_files=$((transferred_files + $(stat_value 'Number of regular files transferred' "$work/rsync.log")))
  transferred_bytes=$((transferred_bytes + $(stat_value 'Total transferred file size' "$work/rsync.log")))
  sent_bytes=$((sent_bytes + $(stat_value 'Total bytes sent' "$work/rsync.log")))
  received_bytes=$((received_bytes + $(stat_value 'Total bytes received' "$work/rsync.log")))
  log '🟢' "SYNC group=$label status=ok"
}

# Keep the original Documents mirror unchanged.
run_sync documents --exclude-from="$work/documents-excludes" \
  "$HOME/Documents/" "Anand@plutonium:/cygdrive/c/Documents/"
if [[ -s "$work/documents-renames.tsv" ]]; then
  run_sync documents-renamed --relative \
    "$work/windows-renamed/./Documents/" "Anand@plutonium:/cygdrive/c/"
fi

# Stage only links under a temporary 'graphene/' directory so rsync --relative
# creates C:\graphene\ on its own. Do not touch Plutonium's live agent directories.
mkdir -p "$work/graphene"
for relative in "${GRAPHENE_DIRS[@]}" "${GRAPHENE_FILES[@]}"; do
  mkdir -p "$work/graphene/$(dirname "$relative")"
  ln -s "$HOME/$relative" "$work/graphene/$relative"
done

# Copy the Copilot SQLite database through its backup API, not as a live DB/WAL.
mkdir -p "$work/graphene/.copilot"
if ! python3 - "$HOME/.copilot/session-store.db" "$work/graphene/.copilot/session-store.db" \
  >"$work/sqlite.log" 2>&1 <<'PY_SQLITE'
import sqlite3, sys
from pathlib import Path

source, destination = map(Path, sys.argv[1:])
with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=30) as src:
    with sqlite3.connect(destination) as dst:
        src.backup(dst)
PY_SQLITE
then
  log '🔴' "ERROR Copilot SQLite snapshot failed: $(head -n 3 "$work/sqlite.log" | tr '\n' ' ')"
  exit 2
fi

# The staged path includes 'graphene/' and all source subpaths.
run_sync graphene --relative \
  "$work/./graphene/" "Anand@plutonium:/cygdrive/c/"

# Preserve home-relative destination paths for both dirs and individual files.
sync_paths=()
for relative in "${SYNC_DIRS[@]}"; do
  sync_paths+=("$HOME/./$relative/")
done
for relative in "${SYNC_FILES[@]}"; do
  sync_paths+=("$HOME/./$relative")
done
run_sync paths --relative "${sync_paths[@]}" "Anand@plutonium:/cygdrive/c/"
