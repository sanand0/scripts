#!/bin/bash
# rofi-clip.sh — Clipboard transformation menu via rofi
# Dependencies: rofi, xclip (X11) or wl-clipboard (Wayland), pandoc, uv, python3, curl

set -euo pipefail

# ─────────────────────────────────────────────
# 0. CLIPBOARD ABSTRACTION
# ─────────────────────────────────────────────

clipboard_get() {
    if [[ -n "${WAYLAND_DISPLAY:-}" ]]; then
        wl-paste --no-newline 2>/dev/null || wl-paste 2>/dev/null
    elif [[ -n "${DISPLAY:-}" ]]; then
        xclip -selection clipboard -o 2>/dev/null
    elif [[ "$(uname)" == "Darwin" ]]; then
        pbpaste
    else
        echo "ERROR: No clipboard tool found" >&2; exit 1
    fi
}

clipboard_set() {
    # $1 = mime type (optional, default text/plain)
    local mime="${1:-text/plain}"
    if [[ -n "${WAYLAND_DISPLAY:-}" ]]; then
        wl-copy --type "$mime"
    elif [[ -n "${DISPLAY:-}" ]]; then
        xclip -selection clipboard -t "$mime" -i
    elif [[ "$(uname)" == "Darwin" ]]; then
        pbcopy
    else
        echo "ERROR: No clipboard tool found" >&2; exit 1
    fi
}

notify() {
    # Show a brief notification (requires libnotify; gracefully skips if absent)
    if command -v notify-send &>/dev/null; then
        notify-send -t 2000 -i edit-paste "Clipboard transformed" "$1"
    fi
}

die() { notify-send -t 4000 -i error "clip-transform error" "$1" 2>/dev/null || true; exit 1; }

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

# ── IMPLEMENTED ──────────────────────────────

transform_unicode_to_ascii() {
    # anyascii handles a huge range: Cyrillic, CJK, emoji, typographic chars, etc.
    # Falls back to manual map for the most common typographic substitutions first
    # so we preserve intent (em-dash → hyphen, not empty string).
    echo "$INPUT" | uv run --quiet --with anyascii python3 - <<'PYEOF'
import sys, anyascii

MANUAL = {
    '\u2014': '--',   # em dash
    '\u2013': '-',    # en dash
    '\u2018': "'",    # left single quote
    '\u2019': "'",    # right single quote / apostrophe
    '\u201c': '"',    # left double quote
    '\u201d': '"',    # right double quote
    '\u2026': '...',  # ellipsis
    '\u00b7': '.',    # middle dot
    '\u2022': '-',    # bullet
    '\u00a0': ' ',    # non-breaking space
    '\u00ad': '',     # soft hyphen (invisible, just drop it)
    '\u200b': '',     # zero-width space
    '\u200c': '',     # zero-width non-joiner
    '\u200d': '',     # zero-width joiner
    '\ufeff': '',     # BOM
}

text = sys.stdin.read()
for src, dst in MANUAL.items():
    text = text.replace(src, dst)
# anyascii for everything else
sys.stdout.write(anyascii.anyascii(text))
PYEOF
}

transform_md_to_richtext() {
    # Produces HTML and puts it in the text/html clipboard slot.
    # Google Docs, Notion, etc. will accept this as rich text on paste.
    # NOTE: This transform writes directly to clipboard (different MIME type).
    echo "$INPUT" \
        | pandoc -f "$PANDOC_FROM" -t html $PANDOC_HTML_FLAGS \
        | clipboard_set "text/html"
    SKIP_WRITE=1  # signal to main loop: clipboard already set
    notify "Markdown → Rich text (text/html)"
}

transform_md_to_html() {
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
    echo "$INPUT" | python3 - <<'PYEOF'
import sys
from urllib.parse import urlparse, urlencode, parse_qsl

STRIP_PREFIXES = ('utm_', 'gclid', 'fbclid', 'mc_', 'igshid', 'msclkid')
STRIP_EXACT    = {'ref', 'source', 'yclid', 's_kwcid', 'dclid'}

url = sys.stdin.read().strip()
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
    echo "$INPUT" | python3 -c "
import sys
from urllib.parse import unquote_plus
sys.stdout.write(unquote_plus(sys.stdin.read().strip()))
"
}

transform_url_encode() {
    echo "$INPUT" | python3 -c "
import sys
from urllib.parse import quote_plus
sys.stdout.write(quote_plus(sys.stdin.read().strip()))
"
}

transform_fetch_title() {
    echo "$INPUT" | python3 - <<'PYEOF'
import sys, urllib.request, html.parser, re

class TitleParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self._in_title = False
        self.title = ''
    def handle_starttag(self, tag, attrs):
        if tag == 'title': self._in_title = True
    def handle_endtag(self, tag):
        if tag == 'title': self._in_title = False
    def handle_data(self, data):
        if self._in_title: self.title += data

url = sys.stdin.read().strip()
try:
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=5) as resp:
        content = resp.read(65536).decode('utf-8', errors='replace')
    p = TitleParser()
    p.feed(content)
    title = p.title.strip() or url
    # clean up whitespace inside title
    title = re.sub(r'\s+', ' ', title)
    sys.stdout.write(f'[{title}]({url})')
except Exception as e:
    sys.stdout.write(url)  # fail gracefully: return bare URL
PYEOF
}

transform_date_iso() {
    echo "$INPUT" | python3 - <<'PYEOF'
import sys
from dateutil import parser as dp
text = sys.stdin.read().strip()
try:
    dt = dp.parse(text, fuzzy=True)
    sys.stdout.write(dt.strftime('%Y-%m-%d'))
except Exception:
    sys.stdout.write(text)  # pass through if unparseable
PYEOF
}

transform_date_long() {
    echo "$INPUT" | python3 - <<'PYEOF'
import sys
from dateutil import parser as dp
text = sys.stdin.read().strip()
try:
    dt = dp.parse(text, fuzzy=True)
    sys.stdout.write(dt.strftime('%a %d %b %Y'))
except Exception:
    sys.stdout.write(text)
PYEOF
}

transform_date_us() {
    echo "$INPUT" | python3 - <<'PYEOF'
import sys
from dateutil import parser as dp
text = sys.stdin.read().strip()
try:
    dt = dp.parse(text, fuzzy=True)
    sys.stdout.write(dt.strftime('%m/%d/%Y'))
except Exception:
    sys.stdout.write(text)
PYEOF
}

# ── STUBS — replace body with real implementation ─────────────────

transform_md_to_unicode() {
    # LinkedIn bold: map ASCII letters/digits to Mathematical Sans-Serif Bold block.
    # Italic: Mathematical Sans-Serif Italic block.
    # This is a pure Python char-map; no external deps.
    echo "$INPUT" | python3 - <<'PYEOF'
import sys, re

BOLD_OFFSET_UPPER = 0x1D5D4 - ord('A')
BOLD_OFFSET_LOWER = 0x1D5EE - ord('a')
BOLD_OFFSET_DIGIT = 0x1D7EC - ord('0')
ITAL_OFFSET_UPPER = 0x1D608 - ord('A')
ITAL_OFFSET_LOWER = 0x1D622 - ord('a')

def to_bold(s):
    out = []
    for c in s:
        if 'A' <= c <= 'Z': out.append(chr(ord(c) + BOLD_OFFSET_UPPER))
        elif 'a' <= c <= 'z': out.append(chr(ord(c) + BOLD_OFFSET_LOWER))
        elif '0' <= c <= '9': out.append(chr(ord(c) + BOLD_OFFSET_DIGIT))
        else: out.append(c)
    return ''.join(out)

def to_italic(s):
    out = []
    for c in s:
        if 'A' <= c <= 'Z': out.append(chr(ord(c) + ITAL_OFFSET_UPPER))
        elif 'a' <= c <= 'z': out.append(chr(ord(c) + ITAL_OFFSET_LOWER))
        else: out.append(c)
    return ''.join(out)

text = sys.stdin.read()

# Order matters: bold-italic before bold before italic
# Strip headings (# → just the text, uppercased bold)
text = re.sub(r'^#{1,6}\s+(.+)$', lambda m: to_bold(m.group(1)), text, flags=re.MULTILINE)
# Bold: **text** or __text__
text = re.sub(r'\*\*(.+?)\*\*|__(.+?)__', lambda m: to_bold(m.group(1) or m.group(2)), text)
# Italic: *text* or _text_
text = re.sub(r'\*(.+?)\*|_(.+?)_', lambda m: to_italic(m.group(1) or m.group(2)), text)
# Strip links: [text](url) → text
text = re.sub(r'\[(.+?)\]\([^)]+\)', r'\1', text)
# Strip inline code backticks
text = re.sub(r'`(.+?)`', r'\1', text)

sys.stdout.write(text)
PYEOF
}

transform_strip_links() {
    # [text](url) → text; also handles reference-style [text][ref]
    echo "$INPUT" | python3 -c "
import sys, re
text = sys.stdin.read()
text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)   # inline links
text = re.sub(r'\[([^\]]+)\]\[[^\]]*\]', r'\1', text)   # reference links
sys.stdout.write(text)
"
}

transform_strip_details() {
    # <details><summary>X</summary>...body...</details> → X
    echo "$INPUT" | python3 -c "
import sys, re
text = sys.stdin.read()
text = re.sub(
    r'<details[^>]*>\s*<summary>(.*?)</summary>.*?</details>',
    r'\1', text, flags=re.DOTALL | re.IGNORECASE
)
sys.stdout.write(text)
"
}

transform_md_clean() {
    # Requires dprint with markdown plugin: https://dprint.dev
    # Install: curl -fsSL https://dprint.dev/install.sh | sh
    if ! command -v dprint &>/dev/null; then
        die "dprint not found. Install: curl -fsSL https://dprint.dev/install.sh | sh"
    fi
    # dprint reads/writes files, so use a temp file
    local tmp
    tmp=$(mktemp --suffix=.md)
    echo "$INPUT" > "$tmp"
    dprint fmt "$tmp" 2>/dev/null
    cat "$tmp"
    rm -f "$tmp"
}

transform_richtext_to_md() {
    # Read the text/html clipboard slot and convert via pandoc
    # NOTE: reads HTML mime type, writes plain text back
    local html_content
    if [[ -n "${WAYLAND_DISPLAY:-}" ]]; then
        html_content=$(wl-paste --type text/html 2>/dev/null)
    else
        html_content=$(xclip -selection clipboard -t text/html -o 2>/dev/null)
    fi
    [[ -z "$html_content" ]] && die "No HTML content in clipboard. Copy rich text first."
    echo "$html_content" | pandoc -f html -t "$PANDOC_FROM" --wrap=none
}

transform_richtext_to_html() {
    # Same as above but output raw HTML (clean, not Word-dirty HTML)
    local html_content
    if [[ -n "${WAYLAND_DISPLAY:-}" ]]; then
        html_content=$(wl-paste --type text/html 2>/dev/null)
    else
        html_content=$(xclip -selection clipboard -t text/html -o 2>/dev/null)
    fi
    [[ -z "$html_content" ]] && die "No HTML content in clipboard. Copy rich text first."
    # Round-trip through pandoc to clean up Word/Docs dirty HTML
    echo "$html_content" | pandoc -f html -t html $PANDOC_HTML_FLAGS
}

transform_ask_chatgpt() {
    local url="https://chatgpt.com/?q=$(python3 -c "import sys,urllib.parse; sys.stdout.write(urllib.parse.quote_plus('$INPUT'))")"
    xdg-open "$url" 2>/dev/null || open "$url" 2>/dev/null
    SKIP_WRITE=1
    notify "Opened in ChatGPT"
}

transform_ask_claude() {
    # Claude.ai doesn't have a ?q= param yet; open new chat and pre-fill isn't
    # supported via URL. Best we can do: keep original clipboard, open new chat.
    # The user pastes manually. We notify them.
    xdg-open "https://claude.ai/new" 2>/dev/null || open "https://claude.ai/new" 2>/dev/null
    SKIP_WRITE=1
    notify "Opened Claude — paste your clipboard to ask"
}

transform_ask_google_ai() {
    local encoded
    encoded=$(python3 -c "import sys,urllib.parse; sys.stdout.write(urllib.parse.quote_plus('''$INPUT'''))")
    xdg-open "https://www.google.com/search?udm=50&q=${encoded}" 2>/dev/null \
        || open "https://www.google.com/search?udm=50&q=${encoded}" 2>/dev/null
    SKIP_WRITE=1
    notify "Opened in Google AI Mode"
}

# ─────────────────────────────────────────────
# 4. MAIN
# ─────────────────────────────────────────────

INPUT=$(clipboard_get)
[[ -z "$INPUT" ]] && die "Clipboard is empty."

# Present menu
CHOICE=$(printf '%s\n' "${MENU_LABELS[@]}" \
    | rofi -dmenu \
           -p "Transform clipboard" \
           -i \
           -theme-str 'window {width: 60%;} listview {lines: 20;}' \
    )
[[ -z "$CHOICE" ]] && exit 0  # user dismissed

FN="${MENU_FNS[$CHOICE]:-}"
[[ -z "$FN" ]] && die "No handler for: $CHOICE"

SKIP_WRITE=0

# Run transform; capture output
RESULT=$("$FN")

# Write result back to clipboard (unless transform did it directly)
if [[ "$SKIP_WRITE" -eq 0 ]]; then
    echo -n "$RESULT" | clipboard_set "text/plain"
    notify "$CHOICE"
fi
