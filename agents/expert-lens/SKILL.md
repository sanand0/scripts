---
name: expert-lens
description: Use this for non-trivial analysis, design, diagnosis, review, strategy, or judgment. Skip it for simple lookups, mechanical rewrites, and pure tone tasks.
metadata:
  sources:
    - https://claude.ai/chat/8cd1018b-c25a-4845-8083-0be478444b34
    - https://chatgpt.com/c/6a3482d0-af78-83e8-a266-a0aefca8fe41
---

Apply experts' procedure. Do not just "act as an expert." THINK like the expert:

1. Abstract first.
   State the 1–3 governing principles, base rates, trade-offs, or constraints the problem reduces to.
2. Check what expertise matters in this domain.
   - In high-validity domains - stable patterns, fast clear feedback (code review, diagnosis, instrumented analysis): trust expert *pattern recognition*; "what they'd notice" is signal.
   - In low-validity domains - strategy, novel markets, long-horizon prediction, governance: expert intuition is near-chance and overconfident. Import *process and falsification only*; distrust the expert gut read and confidence.
3. Pick 1–4 lenses that could materially change the answer. For each, list:
   - What they'd notice
   - The mental model they'd apply
   - The question they'd ask
   - The failure mode they'd fear
   - The evidence that would change their mind
4. Solve, then verify as a fresh reviewer.
   Check output *against* external anchors - run code/tests, look up sources, check each named failure mode, evaluate counterexamples and "what would have to be true?" assumptions. Prefer a deterministic check over judgment. Fact-check like an untrusted solution, not defending your own.

Hard rules:

- Prefer procedures over identities.
- Prefer domain-specific failure taxonomies over generic advice.
- Prefer external checks over self-critique.
- Prefer one sharp lens over four decorative ones.
- In low-validity domains, don't trust "what the expert would feel" - only the structure.
- If a step yields nothing specific to this task, delete it.
- Think silently, internally - don't mention the thinking in the output.
