---
name: code
description: ALWAYS follow this style when writing Python / JavaScript / HTML / CSS code
---

- Inspect relevant code, tests, config, sample input/output before editing. Don't assume structure or behavior you can check directly
- Minimize new code and changes. Prefer the first working option:
  1. Skip if unnecessary
  2. Reuse existing code
  3. Use native platform features
  4. Write it one line if that is clear and correct
  5. Use standard library
  6. Use existing library
  7. Use popular, modern, minimal, fast library
  8. Write the minimum code that works
- Prefer deletion over addition, boring over clever, 1 file over many. Minimize abstractions, scaffolding, or dependencies
- Prefer data over code: structures beat conditionals. Prefer config.{json|yaml|toml|...} if >= 30 lines
- DRY: Use helpers for logic repeated 3+ times, precompute shared intermediates
- Keep happy path linear and obvious. Write flow first, then fill in code
- Early returns fail fast and reduce nesting. Skip defensive fallbacks, existence checks, ... unless essential
- Change existing code minimally. Retain existing comments. Follow existing style.
  Preserve behavior outside requested changes. Ask before materially expanding scope or touching unrelated files/config
- Make scripts re-startable if interrupted. Inspect state first for unexpected changes

Docs:

- Use type hints and docstrings (document contracts and surprises, not mechanics)
- Comment non-obvious stuff that'll trip future maintainers: why, why not alternatives, pitfalls, invariants, input/output shape, ...

Tests:

- When tests exist, or writing new code, add and run tests first
- Use existing commands and environment - don't reconstruct dependencies ad hoc
- Run minimal existing tests for changed behavior. Extend relevant existing tests before creating new test/file
- Lint/format only files you changed. Don't auto-format legacy code unless asked
- Test final outputs, not just the source / intermediates
- Test user-visible front-end changes with:
  - DOM/source checks for behavior: interactions, navigation, overlaps, cut-off elements, readability, colour/font size count, ...
  - Screenshots for appearance changes: responsive layout, overlaps, contrast & visibility, visual impact, ...
  - Lighthouse audit via Chrome DevTools MCP else `npx -y lighthouse@latest`: when semantics, controls, colors, performance changes
- Keep tests fast
- Never say "verified" without evidence. List changes, validations with results, and remaining risks/unknowns

Ops:

- Log status & progress for long tasks (>5s). Log _before_ action. Flush logs

Bug fixes:

- Fix the root cause, not just the reported symptom. Check callers before patching

## Python

Avoid `python` or `python3`. Prefer `uv run script.py` for PEP 723 scripts and `uv run --with pkg ...` for ad-hoc code/tests.
Tests importing a PEP 723 script must use the repo test environment or explicitly include its dependencies.

Avoid `requirements.txt`. Unless `pyproject.toml` is present, add dependencies as PEP 723 metadata:

```py
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["scipy>=1.10", "httpx"]
# ///
```

Prefer when really needed:

- typer|click > argparse
- httpx2 > httpx > requests
- lxml > xml
- duckdb > pandas > csv
- tenacity for retries

## Web

Prefer modern HTML/CSS/platform features over custom JavaScript or libraries.

- Images: responsive `srcset`/`sizes`; `loading="lazy"` for offscreen images, but never likely LCP images; use `fetchpriority="high"` for important/LCP images
- Forms: semantic input types, `autocomplete=`, `inputmode=`, `enterkeyhint=`, `list=`, `autocapitalize=`, `spellcheck=`, `form=`
- UI: `<dialog>`, `popover`, `popovertarget=`, `commandfor=`/`command=`, `inert`, `<details name="">`, `closedby=`
- Semantics: prefer native elements such as `<search>`, `<meter>`, `<progress>`, `<output>`, `<data>`, `<time>` over custom equivalents
- Media: `<picture>`, `srcset=`, `preload=`, `poster=`, `playsinline`, `<track>`
- CSS: prefer container queries for component responsiveness; logical properties, `clamp()`, `text-wrap: balance|pretty`, `color-scheme`, `light-dark()`, `color-mix()`, `oklch()` where useful
- Motion: prefer CSS transitions/animations over JavaScript; respect `prefers-reduced-motion`
- Accessibility: preserve native keyboard/focus behavior; use `:focus-visible`; prefer native HTML semantics over ARIA/custom JavaScript
- Validation: prefer native constraint validation and `:user-valid`/`:user-invalid`
- Prefer Baseline Widely Available features. For newer features, feature-detect / use `@supports` and degrade gracefully; avoid polyfills/dependencies unless required.
- For unfamiliar/new web-platform features or uncertain browser support, consult `npx -y modern-web-guidance@latest search "<task>"` and retrieve only the relevant guide.

## JavaScript

Preferred JS style:

- Hyphenated HTML class/ID names (`id="user-id"` not `id="userId"`)
- Use modern JavaScript and ES modules: `?.`, `??`, destructuring, spread, implicit returns (`=>` over `=> { return }`)
- No TypeScript, but `// @ts-check`. `.d.ts` is OK for packages
- With `fetch()`, check `response.ok` before consuming the response unless non-2xx responses are intentionally handled
- Show loading/pending state for user-visible async operations
- Handle expected/recoverable errors where they occur; let unexpected errors propagate to a top-level handler
- Prefer `textContent`/DOM APIs for untrusted content; never interpolate untrusted data into `innerHTML`

Debug front-end apps with agent-browser, Playwright via CDP on localhost:9222.
For single-page HTML, prefer `file://` when a server isn't required.
