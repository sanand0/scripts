#!/usr/bin/env bash

set -euo pipefail

# rofi-prompts.sh: Pick any prompt from Markdown files and paste its code fence.
#
# Expected input (default: ~/code/blog/pages/prompts):
# - Files that have one prompt in the first fenced code block, OR
# - Files with multiple prompts as H2 sections where each section has a fenced block.
#
# Picker behavior:
# - For H2-based files: one entry per "H2 -> first fenced code block".
# - For single-prompt files: one entry per file (first fenced code block).
#
# Usage:
#   rofi-prompts.sh [PROMPTS_DIR_OR_FILE]
#
# Dependencies:
# - Required: awk, rofi
# - Optional Wayland: wl-copy (+ wtype for auto-type)
# - Optional X11: xclip (+ xdotool for Ctrl+V)
#
# Design notes:
# - Keep parsing conservative and predictable (first fenced block only).
# - Support both single-prompt and multi-section prompt files.
# - Never execute prompt content; only copy/type plain text.

TARGET="${1:-$HOME/code/blog/pages/prompts}"

if [[ ! -e "$TARGET" ]]; then
  echo "Path not found: $TARGET" >&2
  exit 1
fi

# ----------------------------------------------------------------------------
# Parsing helpers
# ----------------------------------------------------------------------------
# extract_first_fence FILE
#   Prints the first fenced code block in FILE (without opening/closing fences).
#   Returns empty output if no fenced block exists.
extract_first_fence() {
  local file="$1"
  awk '
    BEGIN { in_fence=0; done=0 }
    /^```/ {
      if (!in_fence) { in_fence=1; next }
      done=1; exit
    }
    in_fence { print }
  ' "$file"
}

# extract_h2_fence FILE HEADING
#   Prints the first fenced block inside the exact H2 section named HEADING.
#   Used for files like fragments.md that contain many prompt snippets.
extract_h2_fence() {
  local file="$1"
  local heading="$2"

  awk -v target="$heading" '
    BEGIN { in_target=0; in_fence=0; done=0 }
    /^##[[:space:]]+/ {
      if (done) exit
      h=$0
      sub(/^##[[:space:]]+/, "", h)
      in_target = (h == target)
      next
    }
    in_target && /^```/ {
      if (!in_fence) { in_fence=1; next }
      done=1; exit
    }
    in_target && in_fence { print }
  ' "$file"
}

# get_doc_title FILE
#   Uses front-matter title when present; otherwise falls back to file basename.
#   This keeps picker labels stable and human-friendly.
get_doc_title() {
  local file="$1"
  local title
  title="$(awk -F': *' '/^title:[[:space:]]*/ {print $2; exit}' "$file" | sed 's/^"//; s/"$//')"
  if [[ -n "$title" ]]; then
    printf '%s\n' "$title"
  else
    basename "$file" .md
  fi
}

# ----------------------------------------------------------------------------
# Discover candidate markdown files
# ----------------------------------------------------------------------------
FILES=()
if [[ -d "$TARGET" ]]; then
  while IFS= read -r -d '' file; do
    FILES+=("$file")
  done < <(find "$TARGET" -maxdepth 1 -type f -name '*.md' ! -name '_index.md' -print0 | sort -z)
else
  FILES+=("$TARGET")
fi

[[ ${#FILES[@]} -eq 0 ]] && { echo "No markdown files found in: $TARGET"; exit 1; }

# ----------------------------------------------------------------------------
# Build picker index
# ----------------------------------------------------------------------------
# LABELS: user-facing lines shown in rofi.
# META:   tab-separated "file<TAB>heading" aligned by array index with LABELS.
#
# Rule:
# - If a file has H2 sections with fenced content, add each section as one entry.
# - Otherwise add one file-level entry from the first fenced block.
LABELS=()
META=()

for file in "${FILES[@]}"; do
  doc_title="$(get_doc_title "$file")"
  mapfile -t headings < <(
    awk '
      /^##[[:space:]]+/ {
        h=$0
        sub(/^##[[:space:]]+/, "", h)
        print h
      }
    ' "$file"
  )

  added_h2=0
  if [[ ${#headings[@]} -gt 0 ]]; then
    for heading in "${headings[@]}"; do
      code="$(extract_h2_fence "$file" "$heading")"
      if [[ -n "${code:-}" ]]; then
        LABELS+=("${doc_title} › ${heading}")
        META+=("${file}"$'\t'"${heading}")
        added_h2=1
      fi
    done
  fi

  if [[ "$added_h2" -eq 0 ]]; then
    code="$(extract_first_fence "$file")"
    if [[ -n "${code:-}" ]]; then
      LABELS+=("${doc_title}")
      META+=("${file}"$'\t')
    fi
  fi
done

[[ ${#LABELS[@]} -eq 0 ]] && { echo "No fenced prompt blocks found."; exit 1; }

# ----------------------------------------------------------------------------
# User selection and prompt resolution
# ----------------------------------------------------------------------------
CHOICE="$(printf '%s\n' "${LABELS[@]}" | rofi -dmenu -i -p 'Prompt')"
[[ -z "${CHOICE:-}" ]] && exit 0

selected_meta=""
for i in "${!LABELS[@]}"; do
  if [[ "${LABELS[$i]}" == "$CHOICE" ]]; then
    selected_meta="${META[$i]}"
    break
  fi
done

[[ -z "$selected_meta" ]] && { echo "Selected prompt not found."; exit 1; }

IFS=$'\t' read -r selected_file selected_heading <<< "$selected_meta"

if [[ -n "${selected_heading:-}" ]]; then
  CODE="$(extract_h2_fence "$selected_file" "$selected_heading")"
else
  CODE="$(extract_first_fence "$selected_file")"
fi

[[ -z "${CODE:-}" ]] && { echo "No fenced code block found for: $CHOICE"; exit 1; }

# ----------------------------------------------------------------------------
# Output: clipboard + optional auto-paste
# ----------------------------------------------------------------------------
# Copy and paste strategy:
# - Prefer Wayland tools first, then X11 tools.
# - If typing helpers are unavailable, still copy to clipboard.
# - If no clipboard tool exists, print to stdout as a safe fallback.
if command -v wl-copy >/dev/null 2>&1; then
  printf '%s' "$CODE" | wl-copy
  if command -v wtype >/dev/null 2>&1; then
    wtype "$CODE"
    exit 0
  fi
fi

if command -v xclip >/dev/null 2>&1; then
  printf '%s' "$CODE" | xclip -selection clipboard
  if command -v xdotool >/dev/null 2>&1; then
    xdotool key --clearmodifiers ctrl+v
    exit 0
  fi
fi

# Last resort for minimal environments (still useful in terminals/SSH).
printf '%s\n' "$CODE"
