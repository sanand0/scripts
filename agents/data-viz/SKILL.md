---
name: data-viz
description: To select, design, annotate, and verify a data visualization (chart, map, or table).
---

A good chart makes **one** comparison clear, honest, and easy to remember.

**Start with the brief.** Before you draw, fix:

- The one claim the chart should prove.
- The comparison the reader must make: change, rank, size, spread, relationship, part-of-whole, flow, place, or how sure we are.
- The denominator and unit, and any change made to the data (like smoothing or indexing).
- The one caveat that could change how it reads.
- What it's for: to **make one point**, or to **let people find and watch numbers** (like a dashboard).
  A chart that makes a point needs one clear takeaway.
  A dashboard doesn't - it needs the right numbers to be easy to find.
  Don't force one story onto a dashboard.

**Build a trustworthy chart.**

- Compare fairly: use a rate, not a raw count, with a fair denominator. Treat dates as dates, not categories.
- Match the number to the claim: right measure, right total or average.
- Keep the scale honest: bars start at zero; no second y-axis (it fakes a link); crop a line's axis only if you label it and it doesn't exaggerate.
- Show gaps in the data - never join a line across missing points as if they were there. Say when you smooth or index.
- Order is not cause. Color alone is not meaning - add a label or shape so colorblind readers can read it too.

**Pick the best form.** Anchor on the **FT Visual Vocabulary**.

- Tables often beats a charts when people need exact numbers.
- Use shading in maps for **rates** and sized dots for **totals**.
- Use a scatter plot only for two number columns.
- Use a treemap only when the nesting matters.
- Use **position, not area or angle**, for anything people must compare closely (Cleveland-McGill) - so skip pie charts for fine comparisons.

**Focus.** Prefer these defaults unless you have a good reason.

- Use black & white, coloring the one or few things that matter. Avoid a full rainbow. Max 7 colors.
- Keep labels right next to the lines or bars, instead of in a separate legend.
- Write a headline that says the **finding**, not the topic - but let the data speak; don't oversell.
- Add a short note on the chart, with an arrow, pointing at the thing you want seen.
- Cut anything that isn't data or a label (Tufte's data-ink idea).
  But dense doesn't imply messy - when there's a lot to show, group or layer it instead of deleting it.
- If the chart makes a point, give it one clear focal point that reads in about five seconds.
  If it's for looking things up, just make the right comparison easy to find.

**Novelty.** Keep it plain by default, unusual on purpose.

An eye-catching, unusual chart is easier to remember but slower to read.
That trade is worth it when you want people to remember it - a talk, a poster, the big chart at the top of a story.
It's not worth it when people need to read fast, like a dashboard or a quick decision.

**Check the finished image.** From the code **AND** the rendered output:

- Does the point land in about five seconds?
- Is anything cut off or overlapping?
- Does it still work at phone width?
- Is it still clear in gray?

Fix and redraw until yes.
