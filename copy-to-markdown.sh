#!/bin/bash

# Usage: Press Ctrl+C to copy rich text (e.g. web page). Then press Ctrl+Alt+C to run this script.
# Clipboard now has a Markdown version of the HTML.
# See setup/media-keys.dconf for keybinding setup.

# Dependencies: xclip, deno

# CAPTURE HTML content
html=$(xclip -selection clipboard -t text/html -o 2>/dev/null)

# CONVERT to Markdown
markdown=$(echo "$html" | mise x -- deno eval '
import { NodeHtmlMarkdown } from "npm:node-html-markdown";
const html = await new Response(Deno.stdin.readable).text();
const options = { bulletMarker: "-", useLinkReferenceDefinitions: false };
await Deno.stdout.write(new TextEncoder().encode(NodeHtmlMarkdown.translate(html, options)));
')

# COPY
echo "$markdown" | xclip -selection clipboard
echo "$markdown" | xclip -selection primary
