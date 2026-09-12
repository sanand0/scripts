# Available tools

ug -il -Z1 --bool --files '"phrase" (x|y|z) -deprecated' "$DIR"
rga, sd
sg (ast-grep: code search), dprint
git, gh (check repo first; `git log --follow` only one path)
curl, w3m, lynx, websocat, wscat
uvx ruff, uvx yt-dlp, uvx docling (pdf to Markdown with OCR)
agent-browser (use stable tab IDs like t45; inspect visible DOM before clicking), uvx browser-use, uvx --from playwright python -c 'import playwright' (no npm playwright)
npx -y @firecrawl/anydoc (pdf, word, ppt to Markdown, no OCR)
pdfcpu, qpdf, pdftoppm, pdfplumber, pandoc
magick (~/.local/overrides/magick), cwebp, ffmpeg, melt (avoid imgcat, prefer view_image / read tool)

See other files in this directory for usage examples.
