- Write SHORT, CONCISE, READABLE code
- Deduplicate maximally. Use iteration, higher-order functions, vectorization
- Minimize code changes. NEVER remove existing comments
- Validate early via if-return pattern
- Skip error handling. No try/catch unless an operation is error-prone
- For single line if / for statements, avoid { blocks }
- Use functions, not classes
- Keep large config in config files, not code (.env, config.json, config.toml)
- Keep code files under ~500 lines. Split logically
- Follow existing code & comment style
- Include type hints and single-line docstrings
- On completion, suggest further improvements

Python:

- Use `uv run` instead of `python` or `python3`.
- Add dependencies as inline script metadata like this:
  ```
  #!/usr/bin/env -S uv run --script
  # /// script
  # requires-python = ">=3.12"
  # dependencies = dependencies = ["scipy>=1.10", "httpx"]`
  # ///
  ```

HTML/CSS/JS:

- Use ESM: <script type="module">
- No TypeScript. Only MODERN JavaScript
- Use hyphenated HTML class/ID names (id="user-id" not id="userId")
- Show full errors to the user (beautifully) instead of console.error()
- Show a loading indicator while awaiting fetch()
- Avoid document.createElement. Use .insertAdjacentHTML / .replaceChildren (or lit-html)
- Use Bootstrap classes for CSS. Avoid custom CSS
- Use D3 for data visualization

Lint with `npm run lint` if available, else:

- PY: `uvx ruff --line-length 100`
- JS, MD: `npx -y prettier@3.5 --print-width=120 '**/*.js' '**/*.md'`
- HTML: `npx -y js-beautify@1 '**/*.html' --type html --replace --indent-size 2 --max-preserve-newlines 1 --end-with-newline`

References:

- To [test browser JS apps](test-browser-js-apps.md) read @test-browser-js-apps.md
- For [npm-packages](npm-packages.md) read @npm-packages.md
