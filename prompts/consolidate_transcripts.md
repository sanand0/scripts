# consolidate_transcripts.py

Read `consolidate.py` which extracts from transcripts into try-out.md, insights.md, etc.

Create a `consolidate_transcripts.py` that's similar, but instead creates a single `transcripts.md` that looks like this:

```
## What I missed

- 2025-10-02 Kamal.md
  * **Kamal’s execution hierarchy**: he explicitly wants base-layer reliability (OCR→retries→alerts) before strategy—signal that “predictability first” is the bar; risk: I leaned into portfolio strategy early.
  * **His quality concern is about *thinking developers***: he wants “people who anticipate failure modes” (e.g., auto-retrigger on OCR fail), not just ticket-takers—this implies hiring/mentoring for “proactive edges,” not only skills.
  * **He affirmed Anand Patel as “best placed”** but fears he’s dragged into code reviews; I didn’t immediately propose how to firewall Patel’s time.
- 2025-10-01 PG Alpha Quality Issues.md
  - **Root cause on page-26 omission**: You verified the absence but didn’t dig into _why_ 26 wasn’t recalled (chunking policy, page metadata lost, filter logic, or index timing). Cognitive bias: _stop-when-proved_ (satisficing once the bug reproduces).
  - **First-turn rewrite gap**: You noted it but didn’t immediately prioritize enabling rewrite on Q1; that likely fixes recall for “budget.” Bias: _solution aversion_ toward pipeline changes vs a quicker model swap.
  - **Terminology mismatch (“BUD” vs “budget”)**: You observed it but didn’t turn it into a norm-expansion rule. Bias: _expert blindness_—assuming models will infer obvious synonyms.
  - **Citation faithfulness**: You accepted that references were “off” without installing a hard guard (“reject if cited page lacks the claimed token/number”). Bias: _halo effect_ from seeing correct “forecast” and forgiving missing “budget.”
- ...

## Try out

- 2025-10-02 Kamal.md
  * **Spec-by-Example kit (1 page per feature)**: inputs, outputs, counter-examples, and “don’t do this” cases—designed for Adriano’s precision and Hendra’s clarity. High-impact because it shortens debate cycles.
  * ⭐ **Golden-Question Bench + Prompt-Diffs**: freeze 50 canonical Qs; run nightly on (current model, candidate model) with `temperature≈0` and seed (where supported); flag regressions with side-by-side diffs. Novel because it treats prompts like code with CI. ([OpenAI Platform][2])
  * ...
- 2025-10-01 PG Alpha Quality Issues.md
  - ⭐ **Dual-key coverage guard**: Add a lightweight checker: “Do not answer unless both _forecast_ and _budget_ are present; else return ‘budget not found on cited pages’ with page IDs.” High-impact because it kills partial answers; novel because it inverts the usual “answer anyway” bias.
  - **Abbreviation & label normalizer**: Map `DE→Germany`, `BUD→budget`, etc., via a tiny YAML and a regex pre-pass before embedding. Cheap, OSS-friendly, and immediately boosts recall.
  - ...
```

Use the following pre-defined section headings (in order):

- Try out
- What I missed
- Insights
- Corrections
- Persona
- What they missed

For each section:

- The first-level bullets contain the file name (no path).
- The second-level bullets are lines directly copied from the sub-bullets in that section.

Use `consolidate.py` as the reference implementation.
