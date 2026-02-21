#!/bin/bash

# https://gemini.google.com/share/7e78b6083091

# Bullets should not have empty lines inside them
#
# ```markdown
# - Bullets should not have empty lines INSIDE them
#
#   - This bullet has an extra line (maybe with white spaces) before this sub-bullet
#   - Next sub-bullet
#
#     - This sub-sub-bullet has an extra line above it
#     - Next sub-sub-bullet
#
# - There's an extra line above this bullet
# ```
#
# But if there are multiple paragraphs inside a bullet, those empty lines INSIDE a list should be preserved:
#
# ```markdown
# - This bullet has multiple paragraphs.
#
#   This is the second paragraph of the same bullet.
#   - This is a second-level bullet inside the first bullet.
#
#     This is a paragraph inside the second-level bullet.
# ```

# CAPTURE TEXT content
text=$(xclip -selection clipboard -t text/plain -o 2>/dev/null)

echo $text | uv run python -c '
import sys
import re

# Regex Breakdown:
# 1. Look behind for either a List Item OR Indented Text (Capture Group 1)
# 2. Match one or more empty lines (newlines with optional whitespace)
# 3. Look ahead for a List Item
pattern = re.compile(
    r"(?m)"                          # Multiline mode (^ matches start of line)
    r"(^"                            # Start of Group 1 (Previous Line)
      r"(?:"                         # Non-capturing group for line types:
        r"\s*(?:[-*+]|\d+\.)"        # A. List Item (bullet or number)
        r"|"                         # OR
        r"[ \t]+"                    # B. Indented text (continuation)
      r")"
      r".*"                          # Rest of the line content
    r")"                             # End of Group 1
    r"(\n\s*)+"                      # The Blank Lines to remove
    r"^(?=\s*(?:[-*+]|\d+\.)\s)"     # Lookahead: Must be followed by a List Item
)

# Replace with the previous line + single newline (removing the gap)
print(pattern.sub(r"\1\n", sys.stdin.read()))
'
