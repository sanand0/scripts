- Treat me as an expert
- Consider new technologies and contrarian ideas, not just the conventional wisdom
- Write the shortest, most concise, readable code possible
- Follow my formatting preferences
- Retain all code comments. They're there for a reason. Do NOT remove them
- Use functional, declarative programming; avoid classes
- Avoid code duplication (iteration, functions, vectorization)
- Use descriptive variable names with auxiliary verbs

Python:
- Use snake_case variables for Python (is_active, has_permission)
- Prefer type hinting your function signatures
- Write one-line docstrings
- Minimize blocking I/O operations. Use async operations
- Use FastAPI for API development

JavaScript:
- Use only ESM. Target modern browsers
- Use camelCase for variables (isActive, hasPermission) and hyphenated class/ID names
- Avoid redundant braces, e.g. in single-line blocks.
- Avoid document.createElement. Prefer .insertAdjacentHTML / .replaceChildren
- Use vanilla JS. Use lit-html only if templates are INCREMENTALLY updated
- D3 for data visualization, Bootstrap for CSS, Pandas and DuckDB for data analysis

Error Handling and Validation
- Validate preconditions and errors early - avoid nested if statements
- Avoid unnecessary else statements; use the if-return pattern instead
- Avoid try blocks unless the operation is error-prone
- Log errors with friendly error messages on the frontend
