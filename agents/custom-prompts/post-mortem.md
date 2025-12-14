---
description: Run a post-mortem analysis
---

Review our entire conversation and extract lessons learned. This is blameless: focus on system, process, and instruction improvements.

STYLE:

- No vague improvements ("be more careful", "check thoroughly")
- Every prevention must be a concrete system change
- Prefer preventative fixes over mitigative ones
- If uncertain, say so and propose how to validate

## 1. CONTEXT GATHERING

Check:

- Terminal output - what commands failed or behaved unexpectedly?
- What actually changed vs. what we discussed? E.g. via git status/diff/log
- Test/lint/typecheck results - what's currently broken?

If any source is unavailable, note it and proceed with what you have.

## 2. HYPOTHESES TIMELINE

List every non-obvious hypothesis / choice / guess / choice you made, both right or wrong. For each:

- **Hypothesis**: What you assumed and why
- **Action**: What you tried
- **Outcome**: What actually happened

Hypotheses that failed are usually where the learning lives.

## 3. FAILURE MODE CATALOG

For each failure mode, document:

- **Symptom**: What happened
- **Frequency**: How often this session
- **Root Cause (5 Whys)**: Why (dig deep)
- **Detection Gap**: What should have caught this earlier?
- **Prevention Rule**: Specific system change

"Detection Gap" is critical: what test, lint rule, type check, or verification step _should_ have caught this before it became a problem?

## 4. HIDDEN MOTIVATIONS

Be brutally honest about choices that seemed reasonable but weren't:

- Did you add complexity to appear thorough rather than to solve the problem?
- Did you default to familiar patterns instead of reading the actual code?
- Did you make assumptions to avoid the "cost" of checking?
- Were you optimizing for appearing competent vs. being effective?

## 5. WHAT ACTUALLY WORKED

Capture successful patterns worth repeating:

- Approaches that succeeded on first try
- Commands/tools that were particularly effective
- Prompting or communication patterns that helped
- Moments where checking something first saved time

## 6. ACTIONABLE RULES

Transform insights into specific, copy-paste-ready rules for AGENTS.md / CLAUDE.md:

Each rule must trace back to a failure mode from Section 3.

## 7. FUTURE SELF WARNING

One paragraph: If you could send a message back to yourself at the start of this session, what would it say?

---

Save this as `post-mortem.md`.
