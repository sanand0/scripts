# /// script
# requires-python = ">=3.12"
# ///
#
# striptags.py -- reads from stdin, strips specified HTML tags, writes to stdout.
#
# Clipboard usage: xclip -selection clipboard -o | uv run striptags.py details | xclip -selection clipboard

import sys
import re


def main():
    content = sys.stdin.read()
    tags = sys.argv[1:] if len(sys.argv) > 1 else []

    for tag in tags:
        escaped_tag = re.escape(tag)
        open_tag = rf"<{escaped_tag}\b(?:\"[^\"]*\"|'[^']*'|[^'\">])*?>"
        close_tag = rf"</{escaped_tag}\s*>"
        pair_pattern = re.compile(rf"{open_tag}.*?{close_tag}", re.IGNORECASE | re.DOTALL)
        self_closing_pattern = re.compile(
            rf"<{escaped_tag}\b(?:\"[^\"]*\"|'[^']*'|[^'\">])*?/>", re.IGNORECASE
        )

        content = pair_pattern.sub("", content)
        content = self_closing_pattern.sub("", content)

    print(content)


if __name__ == "__main__":
    main()
