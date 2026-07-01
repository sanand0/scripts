---
name: code
description: ALWAYS follow this style when writing Python / JavaScript code
---

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
- Change existing code minimally. Retain existing comments. Follow existing style
- Make scripts re-startable if interrupted

Docs:

- Use type hints and docstrings (document contracts and surprises, not mechanics)
- Comment non-obvious stuff that'll trip future maintainers: why, why not alternatives, pitfalls, invariants, input/output shape, ...

Tests:

- When tests exist, or writing new code, add and run tests first (including edge cases). Keep tests fast
- Test final outputs, not just the source / intermediates
- Test visual artifacts (web pages, docs, slides, PDFs, ...) with screenshots (for responsive layout, overlaps, contrast & visibility) _AND_ DOM (for interactions, navigation, accessibility) before finalizing
- Never say "verified" without evidence. List changes, validations with results, and remaining risks/unknowns

Ops:

- Log status & progress for long tasks (>5s). Log _before_ action. Flush logs

Bug fixes:

- Fix the root cause, not just the reported symptom. Check callers before patching

## Python

Prefer `uv run --with pkg1 --with pkg2 script.py`, `uvx --from pkg cmd` over `python` or `python3`

Avoid `requirements.txt`. Unless `pyproject.toml` is present, add dependencies as PEP 723 metadata:

```py
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["scipy>=1.10", "httpx"]
# ///
```

Prefer:

- typer / click not argparse
- httpx not requests
- lxml not xml
- duckdb / pandas not csv
- tenacity for retries

## HTML

Prefer modern HTML:

- Loading: loading="lazy", fetchpriority="low", <link rel="preload" as="image">
- Forms: inputmode=, enterkeyhint=, autocomplete=, list=, autocapitalize=, spellcheck=, form=
- UI: popover, popovertarget=, formmethod="dialog", inert, <details name=""> for accordions, <dialog>, <meter>, <progress>, <track>, <data>
- Media: picture srcset=, video preload=, crossorigin=, playsinline=, muted=, autoplay=, loop=, controls=, poster=

## JavaScript

Preferred JS style:

- Hyphenated HTML class/ID names (id="user-id" not id="userId")
- Modern browser APIs and ESM2022+: Use `?.`, `??`, destructuring, spread, implicit returns (`=>` over `=> { return }`)
- No TypeScript, but `// @ts-check`. `.d.ts` is OK for packages
- Loading indicator while awaiting fetch()
- Error handling only at top level. Render errors for user

Debug front-end apps with agent-browser, rodney, Playwright via CDP on localhost:9222.
For single-page HTML files try `file://` if a server may not be needed.
