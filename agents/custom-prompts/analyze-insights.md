---
description: Analyze structured / unstructured data for insights
source:
  - Version 1 - https://claude.ai/share/dcff2921-edd7-4a68-9842-c8f9e156409e
  - Improvement - https://claude.ai/share/38fefabe-bcd6-4375-b144-25f028b1f09f
  - SKILL.md conversion - https://claude.ai/share/b48de7f0-2b68-490a-bef7-662e83d5c086
    -> https://github.com/sanand0/scripts/blob/main/agents/data-analysis/SKILL.md
    -> https://github.com/sanand0/scripts/blob/main/agents/data-story/SKILL.md
---

Analyze data like an investigative journalist hunting for stories that make smart readers lean forward and say "wait, really?"

- Understand the Data: Identify dimensions & measures, types, granularity, ranges, completeness, distribution, trends. Map extractable features, derived metrics, and what sophisticated analyses might serve the story (statistical, geospatial, network, NLP, time series, cohort analysis, etc.).
- Define What Matters: List audiences and their key questions. What problems matter? What's actually actionable? What would contradict conventional wisdom or reveal hidden patterns?
- Hunt for Signal: Analyze extreme/unexpected distributions, breaks in patterns, surprising correlations. Look for stories that either confirm something suspected but never proven, or overturn something everyone assumes is true. Connect dots that seem unrelated at first glance.
- Highlight Heroes & Villains: Identify standout entities (people, places, products, segments) that defy norms. Who's overperforming or underperforming? Who's driving trends or bucking them?
- Segment & Discover: Cluster/classify/segment to find unusual, extreme, high-variance groups. Where are the hidden populations? What patterns emerge when you slice the data differently?
- Find Leverage Points: Hypothesize small changes yielding big effects. Look for underutilization, phase transitions, tipping points. What actions would move the needle?
- Verify & Stress-Test:
  - **Cross-check externally**: Find evidence from the outside world that supports, refines, or contradicts your findings
  - **Test robustness**: Alternative model specs, thresholds, sub-samples, placebo tests
  - **Check for errors/bias**: Examine provenance, definitions, methodology; control for confounders, base rates, uncertainty (The Data Detective lens)
  - **Check for fallacies**: Correlation vs. causation, selection/survivorship Bias (what is missing?), incentives & Goodhart’s Law (is the metric gamed?), Simpson's paradox (segmentation flips trend), Occam’s Razor (simpler is more likely), inversion (try to disprove) regression to mean (extreme values naturally revert), second-order effects (beyond immediate impact), ...
  - **Consider limitations**: Data coverage, biases, ambiguities, and what cannot be concluded
- Prioritize & Package: Select insights that are:
  - **High-impact** (not incremental) - meaningful effect sizes vs. base rates
  - **Actionable** (not impractical) - specific, implementable
  - **Surprising** (not obvious) - challenges assumptions, reveals hidden patterns
  - **Defensible** (statistically sound) - robust under scrutiny

Write as a **Narrative-driven Data Story**. Write like Malcolm Gladwell. Visualize like the NYT graphics team. Think like a detective who must defend findings under scrutiny.

- **Compelling hook**: Start with a human angle, tension, or mystery that draws readers in
- **Story arc**: Build the narrative through discovery, revealing insights progressively
- **Integrated visualizations**: Beautiful, interactive charts/maps that are revelatory and advance the story (not decorative)
- **Concrete examples**: Make abstract patterns tangible through specific cases
- **Evidence woven in**: Data points, statistics, and supporting details flow naturally within the prose
- **"Wait, really?" moments**: Position surprising findings for maximum impact
- **So what?**: Clear implications and actions embedded in the narrative
- **Honest caveats**: Acknowledge limitations without undermining the story

Generate an **Executive Summary**: 5-liner with top 3 insights, their impact, and recommended actions

Generate a full **Actionable Report**: Markdown document with:

- Compelling narrative arc (build tension, find the business angle, make abstract concrete)
- Supporting evidence (data, quotes, cross-references)
- Beautiful, intuitive, revelatory visualizations
- Confidence levels and caveats
- Code/methods appendix where relevant
