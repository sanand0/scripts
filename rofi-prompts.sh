#!/usr/bin/env bash

set -euo pipefail

# rofi-prompts.sh: pick a prompt fragment from Markdown files and paste it.
#
# Input model (default target: ~/code/blog/pages/prompts):
# - single-prompt files: first fenced code block in the file
# - multi-prompt files: per-H2 first fenced code block (e.g. fragments.md)
#
# Usage:
#   rofi-prompts.sh [PROMPTS_DIR_OR_FILE]
#   rofi-prompts.sh --benchmark [PROMPTS_DIR_OR_FILE]
#   rofi-prompts.sh --no-cache [PROMPTS_DIR_OR_FILE]
#
# Design principles:
# - Fast hot path: serve picker entries from cache whenever safely possible.
# - Predictable behavior: always extract only the first fenced block per scope.
# - Simple invalidation: mtime-based freshness checks, no expensive hashing passes.
# - Low surprise maintenance: clear function boundaries, one responsibility each.
#
# Cache strategy (optimized for low overhead):
# - cache file stores prebuilt picker entries (label, file, heading)
# - cache invalidates if target dir/file or any candidate file is newer
# - no hashes, no per-file metadata files, no deep checks

DEFAULT_TARGET="$HOME/code/blog/pages/prompts"
CACHE_DIR="$HOME/.cache/sanand-scripts/rofi-prompts"
CACHE_VERSION="v1"

TARGET="$DEFAULT_TARGET"
BENCHMARK=0
USE_CACHE=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --benchmark)
      BENCHMARK=1
      shift
      ;;
    --no-cache)
      USE_CACHE=0
      shift
      ;;
    --help|-h)
      # Keep help concise; this script is usually launched via keybinding.
      echo "Usage: rofi-prompts.sh [--benchmark] [--no-cache] [PROMPTS_DIR_OR_FILE]"
      exit 0
      ;;
    *)
      TARGET="$1"
      shift
      ;;
  esac
done

if [[ ! -e "$TARGET" ]]; then
  echo "Path not found: $TARGET" >&2
  exit 1
fi

# Extracts first fenced code block from an entire file.
# Intentionally stops at the first closed fence to keep semantics deterministic.
extract_first_fence() {
  local file="$1"
  awk '
    BEGIN { in_fence=0 }
    /^```/ {
      if (!in_fence) { in_fence=1; next }
      exit
    }
    in_fence { print }
  ' "$file"
}

# Extracts first fenced code block under a specific H2 heading.
# Matching is exact on heading text after stripping leading "## ".
extract_h2_fence() {
  local file="$1" heading="$2"
  awk -v target="$heading" '
    BEGIN { in_target=0; in_fence=0 }
    /^##[[:space:]]+/ {
      h=$0
      sub(/^##[[:space:]]+/, "", h)
      in_target = (h == target)
      in_fence=0
      next
    }
    in_target && /^```/ {
      if (!in_fence) { in_fence=1; next }
      exit
    }
    in_target && in_fence { print }
  ' "$file"
}

# Prefers front-matter title because it is user-facing and human-curated.
# Falls back to basename for files that do not use front matter.
get_doc_title() {
  local file="$1" title
  title="$(awk -F': *' '/^title:[[:space:]]*/ {print $2; exit}' "$file" | sed 's/^"//; s/"$//')"
  if [[ -n "$title" ]]; then
    printf '%s\n' "$title"
  else
    basename "$file" .md
  fi
}

# Single-pass scanner to identify only H2 sections that actually contain code.
# This avoids N rescans (one per heading), which was the main pre-cache hotspot.
list_h2_with_fence() {
  local file="$1"
  awk '
    BEGIN { in_h2=0; in_fence=0; heading=""; heading_has_code=0 }
    /^##[[:space:]]+/ {
      if (in_h2 && heading_has_code) print heading
      heading=$0
      sub(/^##[[:space:]]+/, "", heading)
      in_h2=1
      in_fence=0
      heading_has_code=0
      next
    }
    /^```/ {
      if (!in_fence) {
        in_fence=1
        if (in_h2) heading_has_code=1
        next
      }
      in_fence=0
      next
    }
    END {
      if (in_h2 && heading_has_code) print heading
    }
  ' "$file"
}

# Fast boolean check used for single-prompt files (no qualifying H2 sections).
has_any_fence() {
  local file="$1"
  awk '/^```/ { found=1; exit } END { exit found ? 0 : 1 }' "$file"
}

# Builds file list once, in deterministic order.
# Deterministic ordering keeps picker order stable and cache diffs predictable.
discover_files() {
  FILES=()
  if [[ -d "$TARGET" ]]; then
    while IFS= read -r -d '' file; do
      FILES+=("$file")
    done < <(find "$TARGET" -maxdepth 1 -type f -name '*.md' ! -name '_index.md' -print0 | sort -z)
  else
    FILES+=("$TARGET")
  fi

  if [[ ${#FILES[@]} -eq 0 ]]; then
    echo "No markdown files found in: $TARGET"
    exit 1
  fi
}

# Cache key is derived from canonicalized target path.
# One cache file per target keeps logic simple and avoids namespace collisions.
cache_key() {
  local target_key
  target_key="$(readlink -f "$TARGET" 2>/dev/null || printf '%s' "$TARGET")"
  printf '%s' "$target_key" | sha1sum | awk '{print $1}'
}

cache_file_path() {
  local key
  key="$(cache_key)"
  printf '%s/index-%s.tsv\n' "$CACHE_DIR" "$key"
}

# Freshness policy:
# 1) cache file exists and has current schema version
# 2) target container (dir/file) is not newer than cache
# 3) none of the candidate files are newer than cache
#
# This is O(number_of_files) on mtimes only (cheap), with no content reads.
cache_is_fresh() {
  local cache_file="$1"
  local header
  [[ -s "$cache_file" ]] || return 1

  header="$(head -n 1 "$cache_file" 2>/dev/null || true)"
  [[ "$header" == "#cache-version=${CACHE_VERSION}" ]] || return 1

  # Top-level target timestamp catches add/remove/rename in directories.
  [[ "$TARGET" -nt "$cache_file" ]] && return 1

  # File timestamp check catches content edits in tracked files.
  local file
  for file in "${FILES[@]}"; do
    [[ "$file" -nt "$cache_file" ]] && return 1
  done

  return 0
}

# Loads index rows into memory arrays consumed by rofi picker and resolver.
# TSV format: label<TAB>file<TAB>heading
load_index_from_cache() {
  local cache_file="$1"
  LABELS=()
  META=()

  while IFS=$'\t' read -r label file heading; do
    [[ -z "$label" ]] && continue
    [[ "$label" == "#cache-version=${CACHE_VERSION}" ]] && continue
    LABELS+=("$label")
    META+=("${file}"$'\t'"${heading}")
  done < "$cache_file"
}

# Writes cache atomically (tmp + mv) to avoid torn writes on interruptions.
save_index_to_cache() {
  local cache_file="$1"
  local tmp_file
  tmp_file="${cache_file}.tmp.$$"

  mkdir -p "$CACHE_DIR"

  {
    printf '#cache-version=%s\n' "$CACHE_VERSION"
    local i file heading
    for i in "${!LABELS[@]}"; do
      IFS=$'\t' read -r file heading <<< "${META[$i]}"
      printf '%s\t%s\t%s\n' "${LABELS[$i]}" "$file" "$heading"
    done
  } > "$tmp_file"

  mv "$tmp_file" "$cache_file"
}

# Builds picker index directly from markdown files.
# Output arrays are index-aligned:
# - LABELS[i] shown to user
# - META[i] has file<TAB>heading for resolution
build_index_from_files() {
  LABELS=()
  META=()

  local file doc_title
  for file in "${FILES[@]}"; do
    doc_title="$(get_doc_title "$file")"
    mapfile -t headings < <(list_h2_with_fence "$file")

    if [[ ${#headings[@]} -gt 0 ]]; then
      local heading
      for heading in "${headings[@]}"; do
        LABELS+=("${doc_title} › ${heading}")
        META+=("${file}"$'\t'"${heading}")
      done
    elif has_any_fence "$file"; then
      LABELS+=("${doc_title}")
      META+=("${file}"$'\t')
    fi
  done
}

# Output strategy:
# - Wayland: wl-copy + optional wtype
# - X11: xclip + optional xdotool
# - fallback: stdout (still useful in terminals or remote sessions)
copy_or_type() {
  local text="$1"

  if command -v wl-copy >/dev/null 2>&1; then
    printf '%s' "$text" | wl-copy
    if command -v wtype >/dev/null 2>&1; then
      wtype "$text"
      return
    fi
  fi

  if command -v xclip >/dev/null 2>&1; then
    printf '%s' "$text" | xclip -selection clipboard
    if command -v xdotool >/dev/null 2>&1; then
      xdotool key --clearmodifiers ctrl+v
      return
    fi
  fi

  printf '%s\n' "$text"
}

discover_files

# Benchmark measures index preparation only, not interactive rofi time.
INDEX_START_NS=$(date +%s%N)
INDEX_SOURCE="build"

CACHE_FILE="$(cache_file_path)"
if [[ "$USE_CACHE" -eq 1 ]] && cache_is_fresh "$CACHE_FILE"; then
  load_index_from_cache "$CACHE_FILE"
  INDEX_SOURCE="cache"
else
  build_index_from_files
  if [[ "$USE_CACHE" -eq 1 ]]; then
    save_index_to_cache "$CACHE_FILE"
  fi
fi

INDEX_END_NS=$(date +%s%N)
INDEX_MS=$(awk -v start="$INDEX_START_NS" -v end="$INDEX_END_NS" 'BEGIN { printf "%.2f", (end-start)/1000000 }')

if [[ ${#LABELS[@]} -eq 0 ]]; then
  echo "No fenced prompt blocks found."
  exit 1
fi

if [[ "$BENCHMARK" -eq 1 ]]; then
  printf 'index_entries=%d index_ms=%s index_source=%s\n' "${#LABELS[@]}" "$INDEX_MS" "$INDEX_SOURCE"
  exit 0
fi

# Selection is by label text; then resolved back to file+heading metadata.
CHOICE="$(printf '%s\n' "${LABELS[@]}" | rofi --normal-window -dmenu -i -p 'Prompt')"
[[ -z "${CHOICE:-}" ]] && exit 0

SELECTED_META=""
for i in "${!LABELS[@]}"; do
  if [[ "${LABELS[$i]}" == "$CHOICE" ]]; then
    SELECTED_META="${META[$i]}"
    break
  fi
done

if [[ -z "$SELECTED_META" ]]; then
  echo "Selected prompt not found."
  exit 1
fi

# heading may be empty for single-prompt files.
IFS=$'\t' read -r SELECTED_FILE SELECTED_HEADING <<< "$SELECTED_META"

if [[ -n "${SELECTED_HEADING:-}" ]]; then
  CODE="$(extract_h2_fence "$SELECTED_FILE" "$SELECTED_HEADING")"
else
  CODE="$(extract_first_fence "$SELECTED_FILE")"
fi

if [[ -z "${CODE:-}" ]]; then
  echo "No fenced code block found for: $CHOICE"
  exit 1
fi

copy_or_type "$CODE"
