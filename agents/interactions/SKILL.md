---
name: interactions
description: Use to create tooltips, popups, interactions, and animations as informative and engaging aids.
metadata:
  sources:
    - https://claude.ai/chat/8cd1018b-c25a-4845-8083-0be478444b34
    - https://chatgpt.com/c/6a3482d0-af78-83e8-a266-a0aefca8fe41
    - https://claude.ai/chat/e4f902f8-97fd-4ffb-b5c8-babf296920b1
    - https://chatgpt.com/c/6a420e03-7dd4-83ec-9e89-1d360cb8c576
---

**Tooltips** are for:

- Context about non-obvious terms or phrases (only if relevant and useful)
- Additional context about references (where possible)
- Metadata and context about data points, table cells, chart elements, etc. (always)
- Guidelines:
  - On mobile, use tap-to-reveal with clear dismiss affordance (tap elsewhere or an × icon); auto-reposition to stay within the viewport.
  - Debounce on hover. Only 1 tooltip at a time.
  - Do not show tooltips where the tooltips add no meaningful value or additional information beyond the text.

**Popups** are for:

- Citations. Search for and include references. Cite the key point from the reference and link to it.
- Files. Link liberally to files as supporting evidence.
  - Clicking on file links should open the files in a popup, with a link to open the original in a new tab.
  - Syntax-highlighted if code
  - Show sortable for tabular data, gradient-coloring important numeric / categorical columns if that will help understand the context
- Data points. Provide extensive context for data points.
  - Wherever useful, clicking on data points, table cells, chart elements, etc. should open a popup that provides full context about that element.
  - Include narratives, cards, tables, charts, or even entire dashboards that answer what the user is likely to be curious about or wants to dig in for more details. E.g. context, examples, related metrics, trends over time, breakdown by relevant dimensions, etc.
  - Standardize the format of these popups so users know what to expect. Reuse popups by archetype.
- Guidelines: Trap keyboard focus inside. Contain scrolling. Show loading state when required. Use a consistent anatomy.

**Interactions** can include:

- Scrollytelling. As the user scrolls, trigger changes in charts, illustrations, narratives, etc. to guide them through the story.
- Sliders that allow users to adjust assumptions, scenarios, etc. and see the impact in real time. Keep input & output close - without scrolling.
- Interactive explainers that let the user step through a process, pause, play, speed up, slow down, step forward/backward, or jump to any point in the timeline via a slider (like a video player), with clear explanation of each step and visual cues to highlight relevant parts and metadata/tags for the current step.
- Transition on value change. Animate chart values between states (e.g., bar heights morphing) rather than jump-cutting.
- Streaming text to simulate LLM responses. Stream word-by-word, at ~4 words per second, with a controllable rate, using a blinking cursor at the end to show that it's still generating.
- Progressive reveal quiz. Ask user a question, reveal answer against their guess. Related to scenario forking: choose your own adventure style branching based on user choices.
- Comparisons. Pairwise comparisons, pinnable for comparison, swipe to compare, etc.
- Brushing and linking. Select a region in one chart to highlight related data nearby.
- Small multiples. Show a grid of small charts, letting user expand any SMOOTHLY into a full view - with more details.
- Filters & search.
- Also: Trails. Cursor morphing. Magnetic snapping. Intertial scrolling/panning. Contextual axis transitions.

**Animated SVGs** are for:

- Explaining processes, mechanisms, workflows, etc. The aim is to make users FEEL the process. One glance should give them an intuitive understanding of how it works, even before they read the accompanying text. Show how things are connected, what data flows from where to where, how elements, interact, etc.
- Guidelines: Use GPU-friendly rendering (transform, opacity). Sequence multiple animations deliverately. Respect `prefers-reducted-motion`.

**Principles** to follow:

- Meaningfulness: think carefully about what will be meaningful and useful for the audience to see, based on their objective. The goal is to help them understand and act.
- Visual quality: is critical. Use consistency, bold typography, contrast, visual hierarchy, progressive disclosure, repetition, alignment, information density calibration, and other principles of visual design - while also evaluating relevant visual format innovation.
- Responsive design: all interactions, tooltips, and popups work well on different screen sizes and devices.
- Accessibility: keyboard navigation, minimum contrast ratios, etc.
- URL-driven state: Slider positions, toggle states, and selected scenarios should be reflected in bookmarkable URL parameters.

**Errors to avoid**:

- Visibility: ensure nothing overlaps, get cut off, or becomes inaccessible because we can't scroll to it, etc.
- Performance: ensure loading is fast, latency < 100ms, even with large datasets or complex visualizations.
- Common bugs: tooltip/popup positioning during scroll / resize, z-index warefare, orphaned event listeners, etc.

Plan the design and layout carefully before coding. Sketch the information architecture, interaction inventory, design tokens, performance sensitive paths, responsive breakpoints, etc.
