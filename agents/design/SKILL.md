---
name: design
description: ALWAYS follow this design guide for any front-end work
---

Design principles:

- Dark mode. Add a toggle. Text should contrast background on both modes in ALL elements / states.
- Responsive. Be mobile-friendly at any device size.
- Accessible. Allow extensive keyboard navigation, e.g. for popups on tables, shortcuts for selections, etc.
- Bookmarkable. Capture state in the URL `#path?key=value`. Sharing the URL reproduces the view, with tabs, filters, slider positions, etc. captured. Prefer replaceState()

Prefer creative, distinctive frontends that surprise and delight, not generic, "on distribution" outputs.
A good way is to copy the design of a niche site highly related to the topic. If you do so, mention the site, reason, and what's copied.

Focus on:

- Typography: beautiful, unique, and interesting fonts, not generic fonts like Arial, Roboto, Inter, system. Opt for distinctive choices that elevate the frontend's aesthetics.
- Color & Theme: Commit to a cohesive aesthetic. Use CSS variables for consistency. Dominant colors with sharp accents outperform timid, evenly-distributed palettes. Draw from IDE themes and cultural aesthetics for inspiration.
- Motion: Use animations for effects and micro-interactions. Prioritize CSS-only solutions for HTML. Focus on high-impact moments: one well-orchestrated page load with staggered reveals (animation-delay) creates more delight than scattered micro-interactions.

Use tooltips and popups as informative and engaging aids.

- Use **tooltips** for:
  - Explaining the non-obvious
  - Context for data points on table cells, chart elements, etc. (always)
- Use **popups** for:
  - Quotes / citations with links
  - File links. Render Markdown as HTML (syntax-highlighted), tabular data as sortable tables (with gradient-colored numbers)
  - Rich context on table cells, chart elements, etc. with narratives, cards, tables, charts, or even entire dashboards if required
  - Always allow arrow keys to navigate between popups on adjacent table cells, chart elements, etc.

Use icon libraries. Use SVG favicons e.g.

```html
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg%20xmlns ... %3C%2Fsvg%3E"/>
```

Build interactions with the platform, not JS. Syntax/fallbacks: `npx -y modern-web-guidance@latest retrieve <id>`.

- Tooltip: `popover="hint"` + `interestfor` + `position-area`, `position-try-fallbacks: flip-block` → interest-triggered-tooltips, position-aware-tooltips
- Hover preview (citation, file link): `interestfor` → `popover` card → hovercard
- Drill-down popup: `<dialog closedby="any">` via `commandfor`/`command="show-modal"`; `@starting-style` + `allow-discrete` → dialog, animate-to-from-top-layer
- State change (filter, sort, tab, expand small multiple): `document.startViewTransition(render)`; `view-transition-name: match-element` → same-document-transitions, group-element-transitions
- Scroll-linked visuals: `animation-timeline: view()|scroll()`; play-once via `timeline-trigger`; JS only to swap chart data per step → scrollytelling, scroll-entry-exit-effects
- Expand/collapse: `<details name>` + `::details-content` + `interpolate-size: allow-keywords` → animate-to-intrinsic-sizes
- Sticky header stuck / scroll-edge shade: `@container scroll-state(...)` → state-aware-sticky-headers, scrollability-affordance-hints
- Stagger: `animation-delay: calc(sibling-index() * 40ms)`
- Text on coloured cells: `color: contrast-color(var(--bg))`
- Dark mode: one token set with `light-dark()`; the toggle sets `color-scheme`

Chromium-only bits (interestfor, timeline-trigger, scroll-state, interpolate-size) are enhancements; the fallback is the plain, unanimated state.
JS that positions, shows/hides, dismisses, traps focus or animates on scroll needs a one-line comment saying why the native route fails.
