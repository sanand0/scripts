---
name: design
description: ALWAYS follow this design guide for any front-end work
metadata:
  source: https://www.claude.com/blog/improving-frontend-design-through-skills https://github.com/anthropics/skills/blob/main/skills/frontend-design/SKILL.md
---

Design principles:

- Dark mode. Enable a dark-mode toggle. Text should contrast background on both modes.
- Responsive. It should be readable on mobile and at any device size.
- Accessible. Allow extensive keyboard navigation. For example, popups on tables should allow keyboard navigation. Arrow keys act as if the popup on the adjacent cell is activated.
- Bookmarkable. Capture state in the URL `#path?key=value`. Sharing the URL reproduces the view, with tabs, filters, slider positions, etc. captured. Prefer replaceState()

Prefer creative, distinctive frontends that surprise and delight, not generic, "on distribution" outputs.
Copying niche styles can be a great idea.

Focus on:

- Typography: beautiful, unique, and interesting fonts, not generic fonts like Arial, Roboto, Inter, system. Opt for distinctive choices that elevate the frontend's aesthetics.
- Color & Theme: Commit to a cohesive aesthetic. Use CSS variables for consistency. Dominant colors with sharp accents outperform timid, evenly-distributed palettes. Draw from IDE themes and cultural aesthetics for inspiration.
- Motion: Use animations for effects and micro-interactions. Prioritize CSS-only solutions for HTML. Focus on high-impact moments: one well-orchestrated page load with staggered reveals (animation-delay) creates more delight than scattered micro-interactions.
- Backgrounds: Create atmosphere and depth rather than defaulting to solid colors. Layer CSS gradients, use geometric patterns, or add contextual effects that match the overall aesthetic.

Use tooltips and popups as informative and engaging aids.

- Use **tooltips** for:
  - Explaining the non-obvious
  - Context for data points on table cells, chart elements, etc. (always)
- Use **popups** for:
  - Quotes / citations with links
  - File links. Render Markdown as HTML (syntax-highlighted), tabular data as sortable tables (with gradient-colored numbers)
  - Context for data points on table cells, chart elements, etc. These popups can be extensive, e.g. narratives, cards, tables, charts, or even entire dashboards if required

Use icon libraries rather than unicode/emoji icons.

Use SVG favicons e.g.

```html
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg%20xmlns ... %3C%2Fsvg%3E"/>
```

You can use Unicode and rich typography in the SVG.

```html
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="128">
  <rect fill="#2563eb" width="64" height="64" rx="10"/>
  <text x="32" y="35" text-anchor="middle" dominant-baseline="middle" font-size="40">🌈</text>
</svg>
```
