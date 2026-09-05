# context.py

## Even more fixes, 05 Sep 2026

<!--
cd ~/code/scripts
codex --model gpt-5.6-luna --config model_reasoning_effort=xhigh
-->

Patch only `context.py` and `tests/test_context.py`. Do not stage or commit.

Fix `unique_query_entities()` performance.

Current problem: it generates every contiguous 2+ word query span and checks each against all aliases, causing ~1.3s latency on realistic long prompts.

Change it to:

- derive candidate 2+ word prefixes from known aliases/canonical names;
- keep only prefixes that resolve to exactly one entity;
- check those known unique prefixes against the normalized query;
- preserve exact alias matching first;
- keep ambiguous prefixes unmatched;
- no fuzzy matching.

Add one regression test with a realistic long research prompt, no `Guardrails:` cutoff, asserting shortened-name entity matching still works and warm search stays comfortably under 200 ms.

Run:

```bash
just test-context
git diff --check
```

Do not change the action-routing or cross-source linking behavior.

<!-- codex resume 01a070ba-364b-7951-8b60-8cec4306c35f -->

## More fixes, 05 Sep 2026

<!--
cd ~/code/scripts
codex --model gpt-5.6-luna --config model_reasoning_effort=xhigh
-->

Patch `context.py` and `tests/test_context.py` only. Keep changes minimal. Do not stage or commit.

Read `agents/code/SKILL.md` and inspect current code/tests first.

Make these two changes:

1. Expand action-intent matching to cover natural variants:

- `action item` / `action items`
- `next step` / `next steps`
- `prepare for meeting`
- `prepare for the meeting`
- `prepare me for meeting`
- `prepare me for the meeting`

Keep `what happened` excluded. Do not broaden generic `action`.

2. Improve deterministic entity linking for profiles whose canonical names contain organization/context suffixes.

Example shape:

```text
Canonical: First Last Organization
Source display name: First Last
```

If exact alias/ID matching fails, allow a source display name to link when:

- it is a human-looking name with at least 2 words;
- it contains no email/ID/path-like syntax;
- it is a strict prefix of a canonical or explicit alias;
- that prefix resolves to exactly one entity.

If multiple entities share the prefix, do not link.

Use the same safe-prefix semantics for:

- cross-source ingestion (`mail`, `gchat`, `whatsapp`, calendar where applicable);
- `entity` / `open-loops` resolution;
- generic `search` entity routing, so a unique shortened name gets an `entity` boost.

Do not add fuzzy matching.

Add regression tests for:

- unique shortened name links cross-source evidence;
- ambiguous shortened name does not link;
- generic search recognizes a unique shortened entity;
- all new action-intent variants trigger action routing;
- generic `action` and `what happened` do not.

Run:

```bash
just test-context
git diff --check
```

Then do a temporary real-data rebuild and spot-check entity-edge counts and representative entity/open-loop searches. Do not modify the live DB unless the temporary verification passes.

Report only changes, tests, real-data verification, and any remaining limitation.

--- <!-- steering -->

Add comments documenting rationale for ACTION_INTENT, HUMAN_NAME and docstring explaining safe_prefix_entities.

<!-- codex resume 01a07082-d0ed-74c1-af97-be837407f552 -->

## Fixes, 05 Sep 2026

<!--
cd ~/code/scripts
codex --model gpt-5.6-sol --config model_reasoning_effort=medium
-->

Review and patch `context.py` and `tests/test_context.py`. Keep changes minimal. Do not redesign the system or touch unrelated files. Do not stage or commit.

Fix these concrete defects:

1. Long-query routing is too slow and noisy.

Current behavior tokenizes up to 30 words from the raw prompt, including boilerplate and stopwords. Real LocalMCP prompts take seconds; some exceed 10s.

Reuse the deterministic ideas from:

- `~/Downloads/localmcp-structure/third-pass/scripts/router_benchmark.py`

Specifically:

- strip obvious task boilerplate / guardrails / skill instructions before lexical search;
- remove common stopwords;
- retain salient names, emails, subjects, project terms, etc.;
- run separate narrow FTS searches for `Subject:` and `From:` cues instead of merely boosting broad-search survivors;
- combine broad/subject/sender/entity/action searches deterministically, preferably using RRF or similarly bounded scoring;
- keep `why` explanations and stable tie-breaking.

Do not add embeddings, LLM query expansion, or fuzzy retrieval.

Add a realistic long-prompt performance regression test. Warm search on a fixture or representative synthetic corpus should stay comfortably below ~200 ms rather than seconds.

2. Fix entity aliases and cross-source entity linkage.

Current alias extraction incorrectly treats any email, Google ID, or WhatsApp ID mentioned anywhere in an About note as belonging to that profile. This creates widespread false aliases.

Change this so strong IDs are aliases only when explicitly presented as that profile's identity/contact metadata. Do not infer identity from source citations, paths, quoted messages, unrelated mentions, or group IDs.

Also improve entity resolution:

- exact alias/canonical match first;
- allow a unique canonical-name prefix or similarly strict deterministic shortened-name match;
- if multiple profiles match, return an explicit ambiguity result rather than silently guessing;
- no fuzzy matching.

Then add deterministic entity edges from other sources where identity is strong enough:

- mail sender/recipient addresses where an address is an explicit alias;
- Google Chat sender IDs where explicitly mapped;
- WhatsApp sender IDs where explicitly mapped;
- exact unambiguous display-name matching may be used only when safe;
- Calendar attendees/organizers where explicit IDs map cleanly.

Do not infer weak person matches.

The goal is for `entity` and `open-loops --entity` to include later mail/chat/calendar/WhatsApp evidence, not just About/transcript records.

Add tests for:

- source-path email addresses do not become aliases;
- unrelated IDs in note text do not become aliases;
- explicit contact IDs do;
- shortened unique canonical name resolves;
- ambiguous shortened name does not;
- cross-source entity results include deterministic mail/chat/etc. evidence.

3. Fix transcript filename detection.

Valid transcript files exist in both forms:

```text
YYYY-MM-DD Name.md
YYYY-MM-DD-Name.md
```

The current regex misses the hyphen form.

Accept both separators while still excluding non-date transcript files. Add a regression test and verify the real-data transcript count against the source directory independently.

4. Fix historical-mail source filtering.

Historical mbox federation should behave as part of logical source `mail`.

For example, a search constrained with:

```text
--source mail --since 2020-01-01 --until 2021-01-01
```

should search historical mail when the date/query requires federation.

Result provenance may still report `source: historical_mail`, but `--source mail` must not suppress those results.

Keep explicit `--source historical_mail` working if already supported.

Add tests for both cases.

Also make these small cleanups:

- remove the new exact `BAD_PEOPLE` blacklist from `context.py`; transcript metadata should rely on the generalized upstream cleaning already implemented in `summarize.py`;
- change the default query log to:
  `~/Documents/data/context/query-log.jsonl`
- rename the accidental `just text-context` target to `context-rebuild`.

Verification:

- run `just test-context`;
- run relevant neighboring tests;
- run `git diff --check`;
- rebuild a temporary real-data DB;
- independently compare source counts;
- verify SQLite integrity and FTS/item counts;
- test representative short, subject/sender, entity, historical-mail, and realistic long LocalMCP queries;
- report warm query timings for several long prompts.

Do not modify the live production DB until tests and temporary real-data verification pass. Then rebuild it once and run smoke queries.

In the final report, give only:

- files changed;
- defects fixed;
- tests/results;
- real-data counts;
- representative query timings;
- any remaining known limitation.

<!-- codex resume 01a06fa0-b7b0-74a3-b1cd-ec2e10b688a7 -->

## Initial version, 05 Sep 2026

<!--
cd ~/code/scripts
codex --model gpt-5.6-sol --config model_reasoning_effort=medium
-->

<!-- Source: https://chatgpt.com/c/6a97cdc6-1dc8-83ec-89e9-a523cafe7258 -->

Implement `context.py`, a deterministic, no-embeddings cross-source context index/retrieval CLI for LocalMCP (mcpserver.py).

Inspect current repo conventions, `backupgoogle.py`, `summarize.py`, `mailindex.py`, source schemas, and:

- `~/Downloads/localmcp-structure/third-pass/REPORT.md`
- `~/Downloads/localmcp-structure/third-pass/scripts/context.py`
- `~/Downloads/localmcp-structure/third-pass/scripts/router_benchmark.py`

The prototype is a reference, not production code to copy blindly.

Goal: build a thin source-preserving candidate-discovery layer. Results must retain provenance so agents can deep-read original sources before making claims.

Create:

- `context.py`
- `tests/test_context.py`

Update minimally: `justfile text-context`, `README.md`, and `daily-activities` to run `context.py rebuild` after transcript summarization.

Do not modify `mcpserver.py`, implement `backupdrive.py`, use embeddings/LLMs, or commit.

Use SQLite FTS5. Default DB: `~/Documents/data/context/context.sqlite`

`rebuild` must build `context.sqlite.tmp`, validate it, then atomically `os.replace()` the live DB. A failed rebuild must leave the old DB untouched. Full rebuild only; no incremental indexing.

Use roughly this schema:

```
items:
  id, source, native_id, timestamp, title, body, summary, locator,
  thread_id, conversation_id, account, author, role, extra

item_fts(title, body, summary, author)

actions:
  item_id, action_text, owner, due_date, fingerprint

entities:
  entity_id, canonical_name, profile_path

aliases:
  entity_id, alias

item_entities:
  item_id, entity_id, role
  UNIQUE(item_id, entity_id, role)

source_status:
  source, latest_item_time, source_mtime, row_count, built_at, warning
```

Index these sources:

- `~/Dropbox/notes/transcripts/*.md`
  - date-named individual transcripts only
  - body, summary, people, actions, keywords
- `~/Dropbox/notes/about/*.md`
  - one canonical entity per profile
  - aliases from H1/filename/strong IDs
  - only proven About→transcript links explicitly cited in the profile
  - no fuzzy entity merging
- work/personal `{mail,calendar,chat}.jsonl`
  - preserve native Gmail `thread_id`
  - preserve Google Chat `thread_id`, `space_id`, `sender_id`
  - preserve Calendar recurrence/status/RSVP fields
- `~/Documents/data/whatsapp/*.jsonl`
  - preserve native message/conversation/author IDs
- `~/Documents/{chatgpt,claude}/*.md`
  - one indexed item per turn
  - preserve `role=user|assistant`
- Drive manifest, only if a production `drive.jsonl` exists; otherwise skip cleanly
- asset registries:
  - `~/code/README.md`
  - `~/code/talks/README.md`
  - `~/code/datastories/config.json`
  - `~/code/llmdemos/config.json`
  - `~/code/llmevals/README.md`
  - `~/code/blog/description.md`
  - `~/code/til/README.md`
  - JSON configs should index one logical asset per entry

Do not duplicate the historical mbox corpus. For pre-2026/historical email searches, federate to `~/Documents/Mail/mail-index.sqlite` and normalize results into the same result shape. Never invent Gmail thread IDs for historical mbox mail.

CLI, JSON output by default:

```text
context.py rebuild
context.py search QUERY [--source ...] [--since ...] [--until ...] [--as-of ...] [--limit N]
context.py entity PERSON [--since ...]
context.py recent QUERY --days N
context.py open-loops [--entity PERSON]
context.py thread THREAD_ID
context.py style QUERY
context.py assets QUERY
context.py status [--identities]
context.py --describe
```

Every search hit should include at least:

```json
{
  "source": "...",
  "timestamp": "...",
  "title": "...",
  "author": "...",
  "role": "...",
  "native_id": "...",
  "thread_id": "...",
  "conversation_id": "...",
  "locator": "...",
  "snippet": "...",
  "score": 0,
  "why": ["broad", "entity", "recent"]
}
```

Implement the deterministic routing ideas from the prior benchmark, not just raw BM25:

- broad lexical FTS
- `Subject:` cue
- `From:` cue
- canonical About-person matching
- proven About→transcript links
- action-intent boost
- recency boost
- `--as-of` for historical recency
- stable deterministic ranking, preferably RRF/bounded boosts

Every hit must explain `why`.

Important behavior:

- Gmail `thread` uses native `thread_id`, never normalized subject.
- Google Chat `thread` uses native Chat `thread_id`.
- `style` should default to evidence actually authored by me:
  - ChatGPT/Claude `role=user`
  - sent email
  - exclude assistant turns.

- `open-loops` indexes transcript actions, groups similar actions with a deterministic fingerprint, and shows later evidence. Never infer `pending` or `done` merely from elapsed time; use `completion_evidence: null` when unsupported.
- `status` reports counts, latest timestamps, mtimes, build time, DB size, missing/stale sources, and with `--identities`, ambiguous aliases/duplicate-profile candidates.
- Add lightweight query logging under `~/.cache/sanand-scripts/context/`, recording query/filter/result metadata and latency, not full bodies.

Tests first. At minimum cover:

- atomic rebuild failure leaves old DB untouched
- deterministic rebuild / FTS counts
- exact source/date filters
- Gmail same-subject/different-thread separation
- native Gmail and GChat thread reconstruction
- Calendar native metadata preservation
- WhatsApp native IDs
- transcript actions/people
- unique About entity edges
- ambiguous aliases are not guessed
- ChatGPT/Claude turn roles
- `style` excludes assistant prose
- subject/sender/entity/action/recency routing
- `--as-of`
- historical mail federation
- asset-per-entry indexing
- provenance/locator on every hit
- status and query logging

After fixture tests pass, build a temporary DB from real data and independently verify source counts, DB size, rebuild time, integrity, several locators, and representative searches. Then run the production rebuild.

Run at the end:

```bash
just test-context
git diff --check
```

Also run relevant neighboring tests.

Use sub-agents with appropriate models as required.

Report: files changed, source counts, DB size/rebuild time, representative queries/results, test results, and anything deliberately deferred.

---

Patch `~/code/scripts/context.py` minimally. Do not redesign, stage, or commit.

Read `agents/code/SKILL.md`, inspect `git status`, and preserve unrelated changes.

Fix the remaining query-latency issue:

1. In `search_database()`, compute once:

```python
intent = intent_text(query)
```

Use `intent`, not the full raw prompt, for:

```python
unique_query_entities(connection, intent)
ACTION_INTENT.search(intent)
RECENT_INTENT.search(intent)
```

Keep raw `query` only where source-native structure matters, e.g. extracting `Subject:` / `From:`.

2. Narrow action intent. Do not trigger action mode on generic `action`. Use explicit phrases such as:

- `pending`
- `open loop`
- `follow-up` / `follow up`
- `commit`
- `action item`
- `next step`
- `meeting prep`
- `prepare for meeting`
- `briefing`
- `what happened`
- `last meeting`

The goal is to avoid expensive false-positive action scans from long email/research prompts.

3. Add regression tests:

- boilerplate after `Guardrails:` cannot trigger entity/action/recency behavior;
- long realistic prompt stays fast;
- genuine action/open-loop queries still trigger action routing.

Verify with:

```bash
just test-context
git diff --check
```

Then run the existing 112-task retrieval benchmark or equivalent replay and report:

- Hit@20
- Recall@20
- median / p95 / max latency

Expected direction from prior measurement: roughly 58% Hit@20, ~40% Recall@20, median around 60 ms, with no regression in retrieval quality.

Do not optimize the action table further unless this patch still leaves ordinary non-action queries slow.

<!-- codex resume 01a06f66-bf90-7923-a5d5-24ab30b033aa -->
