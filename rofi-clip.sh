#!/bin/bash
# rofi-clip.sh — Clipboard transformation menu via rofi
# Dependencies: rofi, xclip (X11) or wl-clipboard (Wayland), pandoc, uv, curl, jq

set -Eeuo pipefail

DEBUG_LOG="${ROFI_CLIP_DEBUG_LOG:-/tmp/rofi-clip.log}"
RUN_ID="$(date '+%Y%m%dT%H%M%S%z')-$$"
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
LOG_ENABLED=0

prepend_path_if_dir() {
    local dir="$1"
    [[ -d "$dir" ]] || return 0
    case ":$PATH:" in
        *":$dir:"*) ;;
        *) PATH="$dir:$PATH" ;;
    esac
}

bootstrap_tool_paths() {
    prepend_path_if_dir "$HOME/.local/bin"
    prepend_path_if_dir "$HOME/bin"
    prepend_path_if_dir "$HOME/.local/share/mise/shims"
    prepend_path_if_dir "$HOME/.local/share/mise/bin"
    prepend_path_if_dir "$HOME/.cargo/sharebin"
}

with_input_file() {
    local tmp_file status
    tmp_file=$(mktemp)
    printf '%s' "$INPUT" > "$tmp_file"
    "$@" "$tmp_file"
    status=$?
    rm -f "$tmp_file"
    return $status
}

uri_encode_stdin() {
    jq -sRr @uri
}

cmd_status() {
    local cmd="$1"
    if command -v "$cmd" >/dev/null 2>&1; then
        printf '%s=yes %s_path=%s' "$cmd" "$cmd" "$(command -v "$cmd")"
    else
        printf '%s=no %s_path=missing' "$cmd" "$cmd"
    fi
}

log_runtime_deps() {
    [[ "$LOG_ENABLED" -eq 1 ]] || return 0
    log_debug "deps $(cmd_status rofi) $(cmd_status pandoc) $(cmd_status dprint) $(cmd_status uv) $(cmd_status notify-send) $(cmd_status xclip) $(cmd_status wl-copy)"
}

log_debug() {
    [[ "$LOG_ENABLED" -eq 1 ]] || return 0
    printf '[%s] [run:%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S%z')" "$RUN_ID" "$1" >> "$DEBUG_LOG"
}

log_data() {
    [[ "$LOG_ENABLED" -eq 1 ]] || return 0
    local label="$1"
    local value="${2:-}"
    local bytes
    bytes=$(printf '%s' "$value" | wc -c | tr -d ' ')
    log_debug "$label bytes=$bytes"
    printf '%s\n' "$value" | sed 's/^/| /' >> "$DEBUG_LOG"
}

log_stack_trace() {
    [[ "$LOG_ENABLED" -eq 1 ]] || return 0
    local i
    log_debug "stack_trace_begin"
    for ((i = 1; i < ${#FUNCNAME[@]}; i++)); do
        log_debug "stack[$i] func=${FUNCNAME[$i]} source=${BASH_SOURCE[$i]} line=${BASH_LINENO[$((i - 1))]}"
    done
    log_debug "stack_trace_end"
}

on_error() {
    local exit_code=$?
    LOG_ENABLED=1
    touch "$DEBUG_LOG" 2>/dev/null || true
    log_debug "ERROR exit=$exit_code line=$1 cmd=$2"
    log_stack_trace
    exit "$exit_code"
}

trap 'on_error "$LINENO" "$BASH_COMMAND"' ERR

# ─────────────────────────────────────────────
# 0. CLIPBOARD ABSTRACTION
# ─────────────────────────────────────────────

clipboard_get() {
    local data
    if [[ -n "${WAYLAND_DISPLAY:-}" ]]; then
        log_debug "clipboard_get backend=wayland"
        data=$(wl-paste --no-newline 2>/dev/null || wl-paste 2>/dev/null)
    elif [[ -n "${DISPLAY:-}" ]]; then
        log_debug "clipboard_get backend=x11"
        data=$(xclip -selection clipboard -o 2>/dev/null)
    elif [[ "$(uname)" == "Darwin" ]]; then
        log_debug "clipboard_get backend=darwin"
        data=$(pbpaste)
    else
        log_debug "clipboard_get backend=none"
        echo "ERROR: No clipboard tool found" >&2; exit 1
    fi
    printf '%s' "$data"
}

clipboard_set() {
    # $1 = mime type (optional, default text/plain)
    local mime="${1:-text/plain}"
    local payload
    payload=$(cat)
    log_debug "clipboard_set mime=$mime"
    log_data "clipboard_set_payload" "$payload"
    if [[ -n "${WAYLAND_DISPLAY:-}" ]]; then
        printf '%s' "$payload" | wl-copy --type "$mime"
    elif [[ -n "${DISPLAY:-}" ]]; then
        printf '%s' "$payload" | xclip -selection clipboard -t "$mime" -i
    elif [[ "$(uname)" == "Darwin" ]]; then
        printf '%s' "$payload" | pbcopy
    else
        echo "ERROR: No clipboard tool found" >&2; exit 1
    fi
}

die() {
    LOG_ENABLED=1
    touch "$DEBUG_LOG" 2>/dev/null || true
    log_debug "die message=$1"
    notify-send -t 4000 -i error "clip-transform error" "$1" 2>/dev/null || true
    exit 1
}

# ─────────────────────────────────────────────
# 1. TRANSFORMATION MENU (ordered display list)
# ─────────────────────────────────────────────
# Format: "Display label" → function name
# Add new entries here; implement the function below.

declare -a MENU_LABELS=(
    "Unicode → ASCII                (curly quotes, em-dash, …)"
    "Markdown → Unicode             (bold/italic for LinkedIn)"
    "Markdown → Rich text           (paste into Docs, Notion)"
    "Markdown → HTML                (paste into WordPress)"
    "Markdown → Plain text          (strip all formatting)"
    "Markdown: Strip links          ([text](url) → text)"
    "Markdown: Strip <details>      (keep summary only)"
    "Markdown: Clean & reformat     (dprint)"
    "Rich text → Markdown           (from clipboard HTML)"
    "Rich text → HTML               (from clipboard HTML)"
    "URL: Decode                    (%20 → space, etc.)"
    "URL: Encode                    (space → %20, etc.)"
    "URL: Strip tracking params     (utm_, gclid, ref, …)"
    "URL: Open in ChatGPT           (ask AI)"
    "URL: Open in Claude            (ask AI)"
    "URL: Open in Google AI Mode    (ask AI)"
    "URL: Fetch page title          (url → [Title](url))"
    "Date → ISO 8601                (2026-02-28)"
    "Date → Long                    (Sat 28 Feb 2026)"
    "Date → Short US                (02/28/2026)"
)

declare -A MENU_FNS=(
    ["Unicode → ASCII                (curly quotes, em-dash, …)"]="transform_unicode_to_ascii"
    ["Markdown → Unicode             (bold/italic for LinkedIn)"]="transform_md_to_unicode"
    ["Markdown → Rich text           (paste into Docs, Notion)"]="transform_md_to_richtext"
    ["Markdown → HTML                (paste into WordPress)"]="transform_md_to_html"
    ["Markdown → Plain text          (strip all formatting)"]="transform_md_to_text"
    ["Markdown: Strip links          ([text](url) → text)"]="transform_strip_links"
    ["Markdown: Strip <details>      (keep summary only)"]="transform_strip_details"
    ["Markdown: Clean & reformat     (dprint)"]="transform_md_clean"
    ["Rich text → Markdown           (from clipboard HTML)"]="transform_richtext_to_md"
    ["Rich text → HTML               (from clipboard HTML)"]="transform_richtext_to_html"
    ["URL: Decode                    (%20 → space, etc.)"]="transform_url_decode"
    ["URL: Encode                    (space → %20, etc.)"]="transform_url_encode"
    ["URL: Strip tracking params     (utm_, gclid, ref, …)"]="transform_strip_tracking"
    ["URL: Open in ChatGPT           (ask AI)"]="transform_ask_chatgpt"
    ["URL: Open in Claude            (ask AI)"]="transform_ask_claude"
    ["URL: Open in Google AI Mode    (ask AI)"]="transform_ask_google_ai"
    ["URL: Fetch page title          (url → [Title](url))"]="transform_fetch_title"
    ["Date → ISO 8601                (2026-02-28)"]="transform_date_iso"
    ["Date → Long                    (Sat 28 Feb 2026)"]="transform_date_long"
    ["Date → Short US                (02/28/2026)"]="transform_date_us"
)

# ─────────────────────────────────────────────
# 2. PANDOC MARKDOWN FLAVOR
# Shared flags for all pandoc calls reading Markdown
# ─────────────────────────────────────────────
PANDOC_FROM="gfm-gfm_auto_identifiers+bracketed_spans+fenced_divs+subscript+superscript+hard_line_breaks"
PANDOC_HTML_FLAGS="--syntax-highlighting=none --wrap=none"

# ─────────────────────────────────────────────
# 3. TRANSFORMATIONS
# Each function reads INPUT (set globally below) and prints result to stdout.
# Special cases (rich-text clipboard target, browser open) are handled internally.
# ─────────────────────────────────────────────

transform_unicode_to_ascii() {
    # anyascii handles a huge range: Cyrillic, CJK, emoji, typographic chars, etc.
    # Falls back to manual map for the most common typographic substitutions first
    # so we preserve intent (em-dash → hyphen with spaces, bullet -> hyphen, not asterisk).
    with_input_file uvx --quiet --with anyascii python - <<'PYEOF'
import sys, anyascii
from pathlib import Path

MANUAL = {
    '\u2014': ' -- ', # em dash
    '\u2022': '-',    # bullet
}

text = Path(sys.argv[1]).read_text(encoding='utf-8')
for src, dst in MANUAL.items():
    text = text.replace(src, dst)
# anyascii for everything else
sys.stdout.write(anyascii.anyascii(text))
PYEOF
}

transform_md_to_richtext() {
    # Converts **bold** etc into rich text in the text/html clipboard slot.
    # Google Docs, Notion, etc. will accept this as rich text on paste.
    # NOTE: This transform writes directly to clipboard (different MIME type).
    echo "$INPUT" | pandoc -f "$PANDOC_FROM" -t html $PANDOC_HTML_FLAGS | clipboard_set "text/html"
    SKIP_WRITE=1  # signal to main loop: clipboard already set
}

transform_md_to_html() {
    # Converts **bold** etc into <strong>bold</strong> HTML
    echo "$INPUT" | pandoc -f "$PANDOC_FROM" -t html $PANDOC_HTML_FLAGS
}

transform_md_to_text() {
    # pandoc's plain output is close but keeps some punctuation; pipe through
    # a quick sed to clean up remaining artifacts.
    echo "$INPUT" \
        | pandoc -f "$PANDOC_FROM" -t plain --wrap=none \
        | sed 's/\[\([^]]*\)\]([^)]*)/\1/g'  # catch any residual links
}

transform_strip_tracking() {
    with_input_file uvx python - <<'PYEOF'
import sys
from pathlib import Path
from urllib.parse import urlparse, urlencode, parse_qsl

STRIP_PREFIXES = ('utm_', 'gclid', 'fbclid', 'mc_', 'igshid', 'msclkid')
STRIP_EXACT    = {'ref', 'source', 'yclid', 's_kwcid', 'dclid'}

url = Path(sys.argv[1]).read_text(encoding='utf-8').strip()
parsed = urlparse(url)
kept = [
    (k, v) for k, v in parse_qsl(parsed.query)
    if not any(k.startswith(p) for p in STRIP_PREFIXES)
    and k not in STRIP_EXACT
]
clean = parsed._replace(query=urlencode(kept))
# remove trailing ? if no params remain
result = clean.geturl().rstrip('?')
sys.stdout.write(result)
PYEOF
}

transform_url_decode() {
    echo "$INPUT" | uvx python -c "
import sys
from urllib.parse import unquote_plus
sys.stdout.write(unquote_plus(sys.stdin.read().strip()))
"
}

transform_url_encode() {
    printf '%s' "$INPUT" | uri_encode_stdin
}

transform_fetch_title() {
    local encoded title
    encoded=$(printf '%s' "$INPUT" | uri_encode_stdin)
    title=$(curl -s "https://api.microlink.io/?url=${encoded}" | jq -r '.data.title')
    echo "[$title]($INPUT)"
    notify-send -t 4000 -i dialog-information "Fetched title" "$title" 2>/dev/null || true
}

transform_date_iso() {
    date -d "$INPUT" +"%Y-%m-%dT%H:%M:%S%z"
}

transform_date_long() {
    date -d "$INPUT" +"%a %d %b %Y"
}

transform_date_us() {
    date -d "$INPUT" +"%m/%d/%Y"
}

# ── STUBS — replace body with real implementation ─────────────────

transform_md_to_unicode() {
    # LinkedIn bold: map ASCII letters/digits to Mathematical Sans-Serif Bold block.
    # Italic: Mathematical Sans-Serif Italic block.
    # This is a pure Python char-map; no external deps.
    echo "$INPUT" | unidown -i -
}

transform_strip_links() {
    # Inline striplinks.py behavior: strip Markdown/HTML links and images.
    with_input_file uvx --quiet --with beautifulsoup4 python - <<'PYEOF'
import re
import sys
from pathlib import Path
from bs4 import BeautifulSoup

content = Path(sys.argv[1]).read_text(encoding='utf-8')

# 1. Strip Markdown Images: ![alt](url) -> alt. Allow empty alt text with * instead of +
content = re.sub(r"!\[([^\]]*)\]\([^\)]+\)", r"\1", content)

# 2. Strip Markdown Links: [text](url) -> text
content = re.sub(r"\[([^\]]*)\]\([^\)]+\)", r"\1", content)

# 3. Parse HTML
soup = BeautifulSoup(content, "html.parser")

# 4. Strip HTML Images: <img src="..." alt="text"> -> text. Replace the tag with 'alt' attribute
for img in soup.find_all("img"):
    alt_text = img.get("alt", "")
    alt_text = "" if alt_text is None or not isinstance(alt_text, str) else alt_text
    img.replace_with(alt_text)

# 5. Strip HTML Links: <a href="...">text</a> -> text. unwrap() removes tag, keeps inner text/formatting
for anchor in soup.find_all("a"):
    anchor.unwrap()

print(soup.decode(formatter=None), end="")
PYEOF
}

transform_strip_details() {
    # Remove full <details> blocks.
    with_input_file uvx python - <<'PYEOF'
import re
import sys
from pathlib import Path

content = Path(sys.argv[1]).read_text(encoding='utf-8')
tag = 'details'
escaped_tag = re.escape(tag)
open_tag = rf"<{escaped_tag}\b(?:\"[^\"]*\"|'[^']*'|[^'\">])*?>"
close_tag = rf"</{escaped_tag}\s*>"
pair_pattern = re.compile(rf"{open_tag}.*?{close_tag}", re.IGNORECASE | re.DOTALL)
self_closing_pattern = re.compile(
    rf"<{escaped_tag}\b(?:\"[^\"]*\"|'[^']*'|[^'\">])*?/>", re.IGNORECASE
)

content = pair_pattern.sub("", content)
content = self_closing_pattern.sub("", content)

print(content, end="")
PYEOF
}

transform_md_clean() {
    # Clean Markdown only (no dprint, no temp files).
    printf '%s' "$INPUT" | uv run "$SCRIPT_DIR/clean_markdown.py" /dev/stdin
}

transform_richtext_to_md() {
    # Reuse copy-to-markdown.sh approach: read HTML from clipboard, convert via deno.
    local html_content
    html_content=$(xclip -selection clipboard -t text/html -o 2>/dev/null)
    [[ -z "$html_content" ]] && die "No HTML content in clipboard. Copy rich text first."
    printf '%s' "$html_content" | mise x -- deno eval '
import { NodeHtmlMarkdown } from "npm:node-html-markdown";
const html = await new Response(Deno.stdin.readable).text();
const options = { bulletMarker: "-", useLinkReferenceDefinitions: false };
await Deno.stdout.write(new TextEncoder().encode(NodeHtmlMarkdown.translate(html, options)));
'
}

transform_richtext_to_html() {
    # Reuse copy-to-markdown.sh capture logic: read HTML from clipboard and return it.
    local html_content
    html_content=$(xclip -selection clipboard -t text/html -o 2>/dev/null)
    [[ -z "$html_content" ]] && die "No HTML content in clipboard. Copy rich text first."
    printf '%s' "$html_content"
}

transform_ask_chatgpt() {
    local encoded url
    encoded=$(printf '%s' "$INPUT" | uri_encode_stdin)
    url="https://chatgpt.com/?q=${encoded}"
    echo "$url"
    xdg-open "$url" 2>/dev/null || open "$url" 2>/dev/null
}

transform_ask_claude() {
    local encoded url
    encoded=$(printf '%s' "$INPUT" | uri_encode_stdin)
    url="https://claude.ai/new?q=${encoded}"
    echo "$url"
    xdg-open "$url" 2>/dev/null || open "$url" 2>/dev/null
}

transform_ask_google_ai() {
    local encoded url
    encoded=$(printf '%s' "$INPUT" | uri_encode_stdin)
    url="https://www.google.com/search?udm=50&q=${encoded}"
    echo "$url"
    xdg-open "$url" 2>/dev/null || open "$url" 2>/dev/null
}

# ─────────────────────────────────────────────
# 4. MAIN
# ─────────────────────────────────────────────

bootstrap_tool_paths
log_debug "run_start cwd=$(pwd) user=${USER:-unknown} shell=${SHELL:-unknown} display=${DISPLAY:-} wayland=${WAYLAND_DISPLAY:-}"
log_runtime_deps

INPUT=$(clipboard_get)
[[ -z "$INPUT" ]] && die "Clipboard is empty."
log_data "clipboard_input" "$INPUT"

# Present menu
CHOICE=$(printf '%s\n' "${MENU_LABELS[@]}" \
    | rofi -normal-window -dmenu \
           -p "Transform clipboard" \
           -i \
           -theme-str 'window {width: 60%;} listview {lines: 20;}' \
    )
if [[ -z "$CHOICE" ]]; then
    log_debug "menu_dismissed"
    exit 0
fi
log_debug "choice=$CHOICE"

FN="${MENU_FNS[$CHOICE]:-}"
[[ -z "$FN" ]] && die "No handler for: $CHOICE"
log_debug "handler=$FN"

SKIP_WRITE=0

# Run transform in current shell; capture output while preserving side effects
# (e.g., SKIP_WRITE=1 inside handlers like transform_md_to_richtext).
RESULT_FILE=$(mktemp)
STDERR_FILE=$(mktemp)
if "$FN" > "$RESULT_FILE" 2> "$STDERR_FILE"; then
    TRANSFORM_STATUS=0
else
    TRANSFORM_STATUS=$?
fi
RESULT=$(<"$RESULT_FILE")
TRANSFORM_STDERR=$(<"$STDERR_FILE")
log_debug "transform_status=$TRANSFORM_STATUS skip_write=$SKIP_WRITE"
log_data "transform_stdout" "$RESULT"
if [[ -n "$TRANSFORM_STDERR" ]]; then
    log_data "transform_stderr" "$TRANSFORM_STDERR"
fi
rm -f "$RESULT_FILE"
rm -f "$STDERR_FILE"

if [[ "$TRANSFORM_STATUS" -ne 0 ]]; then
    LOG_ENABLED=1
    touch "$DEBUG_LOG" 2>/dev/null || true
    log_debug "transform_error choice=$CHOICE handler=$FN status=$TRANSFORM_STATUS"
    log_data "transform_stdout" "$RESULT"
    log_data "transform_stderr" "$TRANSFORM_STDERR"
    log_stack_trace
    die "Transform failed ($FN), see $DEBUG_LOG"
fi

# Write result back to clipboard (unless transform did it directly)
if [[ "$SKIP_WRITE" -eq 0 ]]; then
    log_debug "clipboard_write mode=text/plain"
    echo -n "$RESULT" | clipboard_set "text/plain"
else
    log_debug "clipboard_write skipped_by_handler=1"
fi

log_debug "run_end success=1"
