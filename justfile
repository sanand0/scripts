python := "3.14"
pytest := "uv run --isolated --no-project --python " + python + " --with pytest"
playwright := "1.62.0"
playwright_revision := "1234"
fastmcp := "3.4.7"

# Run the complete test suite, failing on the first test module with an error.
test: test-agentlog test-backup-observability test-browsing-history test-chatgpt test-codextags test-edge test-htmlemail test-linkedin test-mcpserver test-musictag test-podcast test-rofi-clip test-run-at test-skilluse test-summarize-blog-tags test-summarize-transcript test-transcribe-calls

# Run the agentlog tests.
test-agentlog:
    {{ pytest }} --with typer pytest -q tests/test_agentlog.py

# Run the backup observability tests.
test-backup-observability:
    {{ pytest }} pytest -q tests/test_backup_observability.py

# Run the browsing history tests.
test-browsing-history:
    {{ pytest }} --with typer pytest -q tests/test_browsing_history.py

[private]
playwright-install:
    test -x "$HOME/.cache/ms-playwright/chromium_headless_shell-{{ playwright_revision }}/chrome-headless-shell-linux64/chrome-headless-shell" || uv run --isolated --no-project --python {{ python }} --with 'playwright=={{ playwright }}' playwright install chromium

# Run the ChatGPT CLI tests, installing their matching Chromium build if needed.
test-chatgpt: playwright-install
    {{ pytest }} --with typer --with 'playwright=={{ playwright }}' pytest -q tests/test_chatgpt_cli.py

# Run the Codex tag-index tests.
test-codextags:
    {{ pytest }} --with bashlex --with orjson --with typer pytest -q tests/test_codextags.py

# Run the Edge CLI tests.
test-edge:
    {{ pytest }} --with beautifulsoup4 --with httpx --with markdownify --with websocket-client pytest -q tests/test_edge.py

# Run the HTML email tests using their PEP 723 environment.
test-htmlemail:
    uv run --python {{ python }} tests/test_htmlemail.py -q

# Run the LinkedIn CLI tests using their PEP 723 environment.
test-linkedin:
    uv run --python {{ python }} tests/test_linkedin.py -q

# Run the MCP server tests against the ToolResult contract they require.
test-mcpserver:
    {{ pytest }} --with 'fastmcp=={{ fastmcp }}' pytest -q tests/test_mcpserver.py

# Run the music tag tests.
test-musictag:
    {{ pytest }} --with mutagen --with typer pytest -q tests/test_musictag.py

# Run the podcast tests.
test-podcast:
    {{ pytest }} --with httpx --with python-dotenv --with pyyaml --with tenacity --with typer pytest -q tests/test_podcast.py

# Run the Rofi clipboard tests.
test-rofi-clip:
    {{ pytest }} pytest -q tests/test_rofi_clip.py

# Run the delayed-command tests.
test-run-at:
    {{ pytest }} pytest -q tests/test_run_at.py

# Run the skill-use scanner tests.
test-skilluse:
    {{ pytest }} --with typer pytest -q tests/test_skilluse.py

# Run the blog metadata summarizer tests without contacting paid APIs.
test-summarize-blog-tags:
    OPENAI_BASE_URL=http://127.0.0.1:9/v1 OPENAI_API_KEY=test {{ pytest }} --with typer --with google-genai --with openai --with python-dotenv --with ruamel.yaml --with rich --with pydantic --with tenacity pytest -q tests/test_summarize_blog_tags.py

# Run the transcript metadata summarizer tests.
test-summarize-transcript:
    OPENAI_BASE_URL=http://127.0.0.1:9/v1 OPENAI_API_KEY=test {{ pytest }} --with typer --with google-genai --with openai --with python-dotenv --with ruamel.yaml --with rich --with pydantic --with tenacity pytest -q tests/test_summarize_transcript.py

# Run the call transcription tests.
test-transcribe-calls:
    {{ pytest }} --with google-genai --with python-dotenv --with pyyaml --with typer pytest -q tests/test_transcribe_calls.py
