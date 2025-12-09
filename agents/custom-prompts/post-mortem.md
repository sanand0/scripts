---
description: Run a post-mortem analysis
---

Review our entire conversation and extract lessons learned. This is blameless: focus on system, process, and instruction improvements.

## CONTEXT GATHERING (do this first)

Before analyzing, actively check:

- `git status` and `git diff` — what actually changed vs. what we discussed?
- Recent terminal output — what commands failed or behaved unexpectedly?
- Test/lint/typecheck results — what's currently broken?
  If any source is unavailable, note it and proceed with what you have.

---

## 1. EXECUTIVE SUMMARY

In 5-8 bullets:

- What we set out to do
- Top 3 things that went wrong
- Top 3 interventions that fixed things
- Current state (working / partially working / technical debt)

## 2. TURNING POINTS TIMELINE

List the 5-8 key moments where direction changed. For each:

- **Signal**: What we observed
- **Hypothesis**: What you assumed was happening
- **Action**: What you tried
- **Outcome**: What actually happened

Mark which hypothesis was _wrong_ — that's usually where the lesson lives.

## 3. FAILURE MODE CATALOG

| Symptom       | Root Cause (5 Whys) | Detection Gap                         | Prevention Rule        | Frequency              |
| ------------- | ------------------- | ------------------------------------- | ---------------------- | ---------------------- |
| What happened | Why (dig deep)      | What should have caught this earlier? | Specific system change | How often this session |

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

## 6. ACTIONABLE RULES FOR CLAUDE.md

Transform insights into specific, copy-paste-ready rules:

```
# Learned from session [date/topic]

## When [specific situation]
DO: [exact action]
BECAUSE: [what went wrong when we didn't]

## NEVER
- [anti-pattern] — causes [consequence we experienced]

## Commands that work in this repo
- [exact syntax that worked]
```

Each rule must trace back to a failure mode from Section 3.

## 7. NEXT SESSION PLAYBOOK

A compact checklist to paste at the start of the next session:

**Before coding:**

- [ ] [specific thing to investigate first]
- [ ] [context to gather]

**During:**

- [ ] [verification step after doing X]
- [ ] [check to run before committing]

**Stop conditions** (pause and ask me when):

- [situation that went badly when you proceeded autonomously]

## 8. FUTURE SELF WARNING

One paragraph: If you could send a message back to yourself at the start of this session, what would it say?

---

## STYLE CONSTRAINTS

- No vague improvements ("be more careful", "check thoroughly")
- Every prevention must be a concrete system change
- Prefer preventative fixes over mitigative ones
- If uncertain, say so and propose how to validate
