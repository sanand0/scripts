---
name: interactive-storytelling
description: Use interactivity purposefully in data visualizations and narrative content. Trigger for scrollytelling, explorable explanations, simulations, guess-then-reveal patterns, or any data story where user action shapes understanding. NOT for dashboard drill-downs or generic UI interactivity.
---

Interactivity is choosing WHICH cognitive work the reader does, not avoiding it. Good interactivity replaces passive reading with active engagement that creates deeper learning.

## When Interactivity Wins

**The litmus test:** If removing interactivity collapses the story, you're using it right. If it's decoration, cut it.

Use interactivity when:
- System behavior matters more than static snapshots (simulations, explorable explanations)
- Personal context changes meaning (personalization: "in your city, at your income")
- Testing prediction improves retention (guess-then-reveal: testing effect proven superior to passive reading)
- Narrative pacing controls comprehension (scrollytelling for complex systems)
- Overwhelming info needs progressive reveal (cognitive load management)

Skip interactivity when:
- Message is simple and unambiguous
- Interaction cost exceeds insight gain
- Critical info would be hidden from non-interactive users (accessibility failure)

## Core Patterns

### Scrollytelling — Author-Paced Narrative
Reader controls speed, author controls sequence. Best for complex systems requiring step-by-step reveal.

**Pinned narrative** (NYT/Pudding style): text changes, visual stays fixed — efficient for data-heavy stories
**Progressive reveal**: content fades in on scroll — spatial metaphor for temporal/causal sequences
**Step sequence**: discrete sections with transitions — clearest for educational content

**Critical rules:**
- Must work on mobile (50%+ traffic) — test touch, reduce complexity for small screens
- Lazy-load media (images/video load only when scrolled into view)
- Provide static fallback for `prefers-reduced-motion` users
- Don't bury the lede — most important insight must be visible without scrolling

**Tech:** Intersection Observer API (native, performant) or GSAP ScrollTrigger (cross-browser, powerful)

### Explorable Explanations — Reader as Scientist
Manipulate variables, observe system response. Teaches causal relationships through experimentation.

**Pattern:** Overview → sandbox mode where reader explores their own questions
**Key insight:** Quality doesn't matter (hand-drawn sketch = polished viz for learning)
**Hook requirement:** Must work with zero prior knowledge; complexity revealed progressively
**Ending:** Open sandbox — reader goes beyond teacher's original question

**Works best for:** Systems thinking, policy tradeoffs, algorithm behavior, game theory
**Nicky Case principle:** Start with my question, end with their questions

### Guess-Then-Reveal — Testing Effect
Reader predicts/draws trend, then sees reality. The gap between guess and truth IS the story.

**Why it works:** Active prediction >> passive observation for retention (cognitive science proven)
**Drawing benefit:** Motor + visual + semantic encoding = 3x memory vs. reading alone
**Pattern:** Prompt → user input → reveal → comparison
**Variants:** Draw line (NYT), estimate value, rank order, predict next

**Critical:** User must commit BEFORE seeing answer (no peeking) or testing effect fails

### Simulations — Systems in Motion
Watch emergent behavior under different conditions. Shows what equations cannot.

**Author controls:** System rules, parameter ranges
**Reader observes:** Emergent patterns, second-order effects, tipping points
**Classic wins:** Disease spread (WashPost flatten curve), segregation (Parable of Polygons), ecosystem dynamics

**Design rule:** Animation speed must match comprehension speed (too fast = missed insight)

### Progressive Disclosure — Manage Cognitive Load
High-level overview first, details on demand. "Overview first, zoom and filter, then details-on-demand" (Shneiderman)

**Prevents:** Information overload (human brain: ~7 items working memory)
**How:** Tooltips, expandable sections, drill-down paths, tabs, accordions
**Golden rule:** If data shows users regularly access "hidden" feature, it shouldn't be hidden
**Anti-pattern:** Hiding frequently-used info to look minimal (form over function)

**Mobile-first principle:** Design for most constrained screen first, enhance for larger screens — forces prioritization

### Personalization — Make It About Them
Same design, reader's data. Abstract → concrete via personal context.

**Powerful variants:**
- Location-based (climate in YOUR city, pollution at YOUR address)
- Time-based (change since YOU were born)
- Scale-based (spending as % of YOUR income)

**Why it works:** People care deeply about relative position; self-relevance drives engagement

## Implementation Principles

**Accessibility is not optional:**
- Keyboard navigation for every interaction (tab, enter, arrow keys)
- Focus indicators (visible outline showing current element)
- Screen reader announcements for state changes (`aria-live` regions)
- Static content fallback OR text alternative describing key findings
- Respect `prefers-reduced-motion` (CSS media query) — swap animation for instant state change

**Performance hierarchy:**
1. CSS-only animations (fastest, smoothest)
2. Canvas for data-heavy rendering (thousands of points)
3. SVG for accessibility + moderate complexity (semantic elements, screenreader friendly)
4. Libraries only when native methods fail

**Mobile constraints drive better design:**
- Touch targets minimum 44×44px (Apple HIG) / 48×48px (Material)
- No hover-dependent info (hover doesn't exist on touch)
- Thumb-zone optimization (bottom third of screen easiest to reach)
- Reduce complexity 50% for mobile vs desktop (attention, screen size, bandwidth)

**Clear affordances prevent confusion:**
- Interactive elements look interactive (color, cursor, underline, button treatment)
- Obvious next action (scroll down arrow, "drag to explore", labeled buttons)
- Immediate feedback on interaction (visual/haptic response within 100ms)
- Undo/reset always available ("back to start" button)

**Default state tells a story:**
- Initial view must communicate insight without ANY interaction
- Interactivity adds depth, not basic comprehension
- If nothing makes sense until user clicks, you've failed

## Anti-Patterns to Avoid

**Interaction that obscures meaning:**
- Critical data hidden behind clicks (accessibility violation)
- Confusing affordances (is this interactive? what happens when I click?)
- Breaking standard patterns without clear benefit (unexpected scroll behavior, weird navigation)

**Performance sins:**
- Janky animation (user sees stutter, loses flow state — 60fps minimum)
- Blocking main thread (UI freezes during computation — use Web Workers)
- Loading everything upfront (bloated initial load — lazy-load offscreen content)

**Mobile hostility:**
- Tiny click targets (fingers are not mouse pointers)
- Hover-required info (doesn't exist on touch devices)
- Horizontal scroll without clear signaling (users won't discover)
- Complex multi-touch gestures without tutorials

## AI-Era Opportunities (Growing in Importance)

These patterns were HARD pre-AI, now trivially generateable at scale:

**Narrative data stories** (scrollytelling, annotated visualizations):
- AI can draft narrative arc from data automatically
- Human judgment: is the story true? does pacing work? is it worth telling?

**Personalized variations** (1000s of custom views):
- Generate location/demographic-specific versions at scale
- Human judgment: does personalization add insight or just novelty?

**Explorable explanations** (interactive simulations):
- AI can write simulation code from conceptual description
- Human judgment: does model capture real dynamics? is simplification appropriate?

**Multi-modal explanations** (voice + visual + interaction):
- Voice interfaces for accessibility (screen reader + verbal explanation)
- Human judgment: does this help understanding or add distraction?

**The shift:** Production is free. Judgment and taste are scarce. Use AI to generate variations, human discernment to pick what works.

## Declining in Importance (Easy Pre-AI, Weak Impact)

Dashboard interactivity (filters, drill-downs): Tools like Tableau made this commodified. Low narrative power, high cognitive cost for casual users. Use only for analyst/expert audiences with specific exploration needs.

## Technical Notes

**Scrollytelling:** Intersection Observer API (native, 0 dependencies) or GSAP ScrollTrigger (most powerful, cross-browser)
**Animations:** CSS animations >> JS libraries for simple transitions (performance + no dependencies)
**Simulations:** Canvas for 1000+ objects (performance), SVG for <500 (accessibility via semantic elements)
**Reactive updates:** Observable Plot, D3, or vanilla JS for data-bound interactions

**Testing checklist before launch:**
- Keyboard navigation works (tab through, activate with enter/space)
- Screen reader announces state changes (test with VoiceOver/NVDA)
- Works on mobile (test real device, not just responsive mode)
- Handles slow connections gracefully (loading states, progressive enhancement)
- Degrades when JS disabled (static fallback or clear message)
