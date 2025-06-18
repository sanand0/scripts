- Write SHORT, CONCISE, READABLE code
- Deduplicate maximally. Use iteration, higher-order functions, vectorization
- Validate early. Use the if-return pattern. Avoid unnecessary else statements
- Avoid try blocks unless the operation is error-prone
- Use functions, not classes
- Keep configurations in separate config files, not code (.env, config.json, config.toml)
- Keep files under ~500 lines, split logically
- When modifying code, follow existing style. Retain existing comments.
- In Python, add type hints and write single-line docstrings

HTML/CSS/JS:
- Use ESM: <script type="module">
- No TypeScript. Only JavaScript
- Use MODERN JavaScript. Minimize libraries
- Use hyphenated HTML class/ID names (id="user-id" not id="userId")
- For single line if / for statements, avoid { blocks }
- Show errors to the user (beautifully). Avoid console.error()
- Show a loading indicator while waiting for fetch()
- Use .insertAdjacentHTML / .replaceChildren (or lit-html). Avoid document.createElement
- Use Bootstrap classes for CSS. Avoid custom CSS
- Use D3 for data visualization

Linting:
- PY: `uvx ruff --line-length 100`
- JS, MD: `npx -y prettier@3.5 --print-width=120 '**/*.js' '**/*.md'` -- do not format HTML files
- HTML: `npx -y js-beautify@1 '**/*.html' --type html --replace --indent-size 2 --max-preserve-newlines 1 --end-with-newline`

In pull request descriptions, include well-formatted Markdown covering:
- The problem this PR solves (1 sentence)
- What code / config / doc changes were made in which files.
- What to review, what's safe vs. what needs extra scrutiny.
- Exact steps to verify locally.
- Deployment risks and mitigations
- What can developers learn from this PR?
