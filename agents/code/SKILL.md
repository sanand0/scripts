---
name: code
description: ALWAYS follow this style when writing Python / JavaScript code
---

- Ask if the success criteria is unclear
- Prefer libraries to writing code. Prefer popular, modern, minimal, fast libraries
- Write readable code. Keep happy path linear and obvious. Write flow first, then fill in code. Name intuitively
- Keep code short
  - Data over code: Structures beat conditionals. Prefer config.{json|yaml|toml|...} if >= 30 lines
  - DRY: Helpers for repeated logic, precompute shared intermediates
  - Early returns fail fast and reduce nesting. Skip defensive fallbacks, existence checks, ... unless essential
  - YAGNI: Skip unused imports, variables, and code
- Change existing code minimally. Retain existing comments. Follow existing style
- Use type hints and docstrings (document contracts and surprises, not mechanics)
- Only comment non-obvious stuff that'll trip future maintainers: why, why not alternatives, pitfalls, invariants, input/output shape, ...
- When tests exist, or writing new code, add new failing tests first (including edge cases). Keep tests fast
- Test web pages with screenshots (for layout, overlaps, contrast) _AND_ DOM (for interactions, navigation) before finalizing
- Log status & progress for long tasks (>5s)
- Make scripts re-startable if interrupted
- Check latest docs for fast moving packages

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

Preferred libs:

- typer / click not argparse
- httpx not requests
- lxml not xml
- pandas not csv
- tenacity for retries

## HTML

Prefer modern HTML:

- Loading: loading="lazy", fetchpriority="low", <link rel="preload" as="image">
- Forms: inputmode=, enterkeyhint=, autocomplete=, list=, autocapitalize=, spellcheck=, form=
- UI: popover, popovertarget=, formmethod="dialog", inert, <details name=""> for accordions, <dialog>, <meter>, <progress>, <track>, <data>
- Media: picture srcset=, video preload=, crossorigin=, playsinline=, muted=, autoplay=, loop=, controls=, poster=

## JavaScript

Preferred JS style:

- Use CSS libraries. Minimize custom CSS
- Hyphenated HTML class/ID names (id="user-id" not id="userId")
- Use modern browser APIs and ESM2022+: Use `?.`, `??`, destructuring, spread, implicit returns (`=>` over `=> { return }`)
- Avoid TypeScript, but enable `// @ts-check`. `.d.ts` is OK for packages
- Loading indicator while awaiting fetch()
- Error handling only at top level. Render errors for user

Preferred libs: d3, hljs, lit-html, marked, partial-json

Debug front-end apps with agent-browser or Playwright via CDP on localhost:9222.
For single-page HTML files try `file://` before spinning up a server.
