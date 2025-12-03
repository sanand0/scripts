---
name: demos
description: Use when creating demos or POCs
---

Scaffold files from ./assets/:

- index.html: For all static content
- script.js: For all dynamic content
- config.json: optional configs for demos, dataset, prompt, model, schema, ...
  - Use config.js instead when template literals and minimal JS expressions are needed
- README.md: Explains what the app does (functionally), how to run locally/deploy

Guidelines:

- Prefer pure-front-end apps that can be deployed on GitHub pages.
- Make it easy to demo.
  - Include cards from config.json to run a demo with one click
  - Include synthetic sample datasets as CSV/JSON each <= 1MB, total <= 5MB
- Make it self-serve
  - Allow users to upload their own data
  - Include a collapsible settings form to edit prompts, models, schema, ... with defaults from config.json.
  - Persist settings with https://www.npmjs.com/package/saveform allowing reset
- Provide a responsive UX
  - Use lit-html for DOM updates
  - Always show a spinner while awaiting network call
  - Always stream LLM responses. Stream JSON with partial-json. Render LLM output with marked. Highlight code blocks

Code style:

- Prefer CDNs over `npm install` (less build steps).
- Lint with dprint and oxlint
  - dprint fmt -c https://raw.githubusercontent.com/sanand0/scripts/refs/heads/main/dprint.jsonc
  - npx -y oxlint --fix
- #TODO Pyodide / DuckDB WASM to run code / analysis

GitHub:

- Add a brief description. Tags: optional
- Deploy on GitHub Pages #TODO
- Ensure that the "About" section is linked to the GitHub Pages URL
