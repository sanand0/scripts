---
name: expert-lens
description: Use this for non-trivial analysis, design, diagnosis, review, strategy, or judgment. Skip it for simple lookups, mechanical rewrites, and pure tone tasks.
---

Apply experts' procedure. Do not just "act as an expert." Think like the expert but keep the reasoning internal.

1. Reframe the task first.
   Infer the user's real decision, success metric, audience, and constraints. Improve the question before answering. If the literal request is weaker than the likely intent, state and answer the improved version while preserving the user's constraints.
   Name the 2-3 tempting false victories: outputs that would look like success but miss the objective - the special case for the general claim, the mock for working code, the framework instead of a decision, etc. Treat them as named failure modes for step 6.
2. Abstract first.
   State the 1–3 governing principles, base rates, trade-offs, or constraints the problem reduces to.
3. Check what expertise matters.
   - High-validity domains: stable patterns, fast clear feedback, objective checks. Trust expert pattern recognition but verify.
   - Low-validity domains: strategy, novel markets, long-horizon prediction, governance. Use expert process, taxonomies, base rates, falsifiers, and leading indicators. Do not trust expert confidence or gut feel.
4. Pick 1–3 lenses that could significantly change the answer. For each, list:
   - What they'd notice
   - The mental model they'd apply
   - The question they'd ask
   - The failure mode they'd fear
   - The evidence that would change their mind
5. Solve against the user's constraints.
   Treat explicit and inferred constraints as a checklist: deliverable, format, scope, evidence standard, exclusions, and reviewability.
6. Verify with the strongest available check.
   Deterministic test > source lookup > corpus evidence > independent model/judge > adversarial counterexample > uncertainty note.
   Check each named failure mode.
   Fact-check like an untrusted solution, not defending your own.
7. Output only what helps.
   Don't show the expert-lens process unnecessarily. Share the conclusion. Only if required, share the decisive lens shifts and evidence/checks that significantly changed the answer.

Hard rules:

- Prefer procedures over identities.
- Prefer domain-specific failure taxonomies over generic advice.
- Prefer external checks over self-critique.
- Prefer one sharp lens over three decorative ones.
- In low-validity domains, output assumptions, scenarios, falsifiers, and leading indicators. Don't trust "what the expert would feel".
- If a lens yields nothing specific to this task, delete it.
- If deterministic verification is possible, do it before relying on judgment.
