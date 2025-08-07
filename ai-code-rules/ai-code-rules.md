- Write SHORT, CONCISE, READABLE code
- Deduplicate maximally. Use iteration, higher-order functions, vectorization
- Validate early via if-return pattern
- Avoid error handling unless an operation is error-prone
- Use functions, not classes
- Keep config in config files, not code (.env, config.json, config.toml)
- Keep code files under ~500 lines. Split logically
- Follow existing code & comment style
- Include type hints and single-line docstrings
- PRs messages: state problem, changes made, what needs review, and deployment risks & mitigations.

HTML/CSS/JS:

- Use ESM: <script type="module">
- No TypeScript. Only JavaScript
- Use MODERN JavaScript. Minimize libraries
- Use hyphenated HTML class/ID names (id="user-id" not id="userId")
- For single line if / for statements, avoid { blocks }
- Show full errors to the user (beautifully) instead of console.error()
- Show a loading indicator while waiting for fetch()
- Avoid document.createElement. Use .insertAdjacentHTML / .replaceChildren (or lit-html)
- Use Bootstrap classes for CSS. Avoid custom CSS
- Use D3 for data visualization

Linting:

- PY: `uvx ruff --line-length 100`
- JS, MD: `npx -y prettier@3.5 --print-width=120 '**/*.js' '**/*.md'`
- HTML: `npx -y js-beautify@1 '**/*.html' --type html --replace --indent-size 2 --max-preserve-newlines 1 --end-with-newline`


References:

- To [test browser JS apps](test-browser-js-apps.md) read @test-browser-js-apps.md
- For [npm-packages](npm-packages.md) read @npm-packages.md
