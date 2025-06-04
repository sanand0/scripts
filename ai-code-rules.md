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
- Use .insertAdjacentHTML / .replaceChildren (or lit-html). Avoid document.createElement
- Use Bootstrap classes for CSS. Avoid custom CSS
- Use D3 for data visualization
