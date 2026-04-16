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

Focus on:

- Typography: beautiful, unique, and interesting fonts, not generic fonts like Arial, Roboto, Inter, system. Opt for distinctive choices that elevate the frontend's aesthetics.
- Color & Theme: Commit to a cohesive aesthetic. Use CSS variables for consistency. Dominant colors with sharp accents outperform timid, evenly-distributed palettes. Draw from IDE themes and cultural aesthetics for inspiration.
- Motion: Use animations for effects and micro-interactions. Prioritize CSS-only solutions for HTML. Focus on high-impact moments: one well-orchestrated page load with staggered reveals (animation-delay) creates more delight than scattered micro-interactions.
- Backgrounds: Create atmosphere and depth rather than defaulting to solid colors. Layer CSS gradients, use geometric patterns, or add contextual effects that match the overall aesthetic.

Override framework / browser defaults to avoid generic AI-generated aesthetics:

- Overused font families (Inter, Roboto, Arial, system fonts)
- Clichéd color schemes (particularly purple gradients on white backgrounds)
- Predictable layouts and component patterns
- Cookie-cutter design that lacks context-specific character

Interpret creatively and make unexpected choices that feel genuinely designed for the context. Vary between light and dark themes, different fonts, different aesthetics. You still tend to converge on common choices (Space Grotesk, for example) across generations. Avoid this: it is critical that you think outside the box!

Use tooltips and popups as informative and engaging aids.

- **Tooltips** are for:
  - Context about non-obvious terms or phrases (only if relevant and useful)
  - Additional context about references (where possible)
  - Metadata and context about data points, table cells, chart elements, etc. (always)
- **Popups** are for:
  - Citations. Quote from citations and link to references from the popup.
  - Files as supporting evidence in popups. Render Markdown as HTML (syntax-highlighted if it has code), tabular data as sortable tables (gradient-coloring numbers if that'll help)
  - Full context for data points, table cells, chart elements, etc. These popups can be extensive, e.g. narratives, cards, tables, charts, or even entire dashboards if required
