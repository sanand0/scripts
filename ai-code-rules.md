- Write SHORT, CONCISE, READABLE code
- Write modular code (iteration, functions, vectorization). No duplication
- Follow existing style. Retain existing comments.
- Use functions, not classes
- Add type hints
- Write single-line docstrings
- Validate early. Use the if-return pattern. Avoid unnecessary else statements
- Avoid try blocks unless the operation is error-prone

HTML/CSS/JS:
- Use ESM: <script type="module">
- Use MODERN JavaScript. Minimize libraries
- Use hyphenated HTML class/ID names (id="user-id" not id="userId")
- For single line if / for statements, avoid { blocks }
- Use .insertAdjacentHTML / .replaceChildren (or lit-html). Avoid document.createElement
- Use Bootstrap for CSS. Avoid custom CSS
- Use D3 for data visualization
- Show errors to the user (beautifully). Avoid console.error()
