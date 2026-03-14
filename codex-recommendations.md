# Codex Recommendations: Claim-by-Claim Fact Check

## Scope
This fact-check uses `/home/vscode/.codex/sessions/tags.csv` (current run, `tagger_version=2026-03-03.2`) and checks claims made in the two ChatGPT answers you shared.

- Dataset: 897 `.jsonl` sessions (`2025-08-09` to `2026-03-03`)
- Method: direct aggregation from existing tag columns (no manual sampling)
- Verdicts:
  - `Supported`: matches data closely
  - `Partially supported`: directionally true but overstated/incomplete
  - `Contradicted`: data does not support
  - `Not verifiable from sessions`: claim is external/product-opinion and not measurable from `tags.csv`

## Claim Ledger

### A) Usage-shape and distribution claims (first answer)

| ID | ChatGPT claim | Fact-check against sessions | Verdict |
|---|---|---|---|
| C1 | 897 sessions total | 897 sessions | Supported |
| C2 | Window is Aug 9, 2025 → Mar 3, 2026 | `date_min=2025-08-09`, `date_max=2026-03-03` | Supported |
| C3 | 36% sessions have zero tool calls | 36.12% (`324/897`) | Supported |
| C4 | Median tool calls in “do work” sessions is 7 | Median is 20 (`tool_call_count>0`) | Contradicted |
| C5 | 90th percentile tool calls ~70 | P90 is 95.8 | Contradicted |
| C6 | 71% sessions have no `apply_patch`; 28.9% do | 71.13% no edit, 28.87% with `apply_patch` | Supported |

### B) Token concentration / cache claims

| ID | ChatGPT claim | Fact-check | Verdict |
|---|---|---|---|
| C7 | Top 10 sessions account for ~39% of tokens | 39.09% of `token_total` | Supported |
| C8 | Top 50 sessions account for ~70% of tokens | 70.14% of `token_total` | Supported |
| C9 | Median cached/input ratio ~0.89 | Median(`token_cached_input/token_input_total` where input>0)=0.8888 | Supported |

### C) Prompt-style and quality-gate claims

| ID | ChatGPT claim | Fact-check | Verdict |
|---|---|---|---|
| C10 | Minimal prompts have ~2x higher mean tool error (0.265 vs 0.129) | 0.2649 vs 0.1290 on sessions with tool outputs | Supported |
| C11 | Verification rate is lower for minimal prompts (24% vs 47%) | 24.45% vs 47.38% (`verification_command_count>0`) | Supported |
| C12 | Acceptance criteria associated with ~49% lower mean error | 49.22% lower (0.1370 vs 0.2697) | Supported |
| C13 | Constraints associated with ~52% lower mean error | 52.08% lower (0.1378 vs 0.2876) | Supported |
| C14 | `update_plan` associated with ~51% lower mean error | 50.88% lower (0.1160 vs 0.2361) | Supported |

### D) “Finish the job” / handoff claims

| ID | ChatGPT claim | Fact-check | Verdict |
|---|---|---|---|
| C15 | Handoff appears in ~4.8% sessions | 4.79% (`workflow_phase_tags` contains `handoff`) | Supported |
| C16 | Delegation appears in ~1.3% sessions | 1.34% (`workflow_phase_tags` contains `delegate`) | Supported |
| C17 | Git in 22.7%, commits 3.9%, PR 1.0% | 22.74%, 3.90%, 1.00% | Supported |

### E) Environment and failure-mode claims

| ID | ChatGPT claim | Fact-check | Verdict |
|---|---|---|---|
| C18 | Highest-error work clusters in some `/home/vscode/...` dirs | Top median-error dirs include `/home/vscode/Downloads/playwright` (0.9), `/home/vscode/code/pyoppe` (0.4242), `/home/vscode/code/exam` (0.2449) | Supported |
| C19 | March 2026 looks much worse and includes many 1/1 fails | Mar tool-session mean error=0.645 (highest). 5 sessions have exactly 1 output and 1 failure | Supported |

### F) Timeline claims

| ID | ChatGPT claim | Fact-check | Verdict |
|---|---|---|---|
| C20 | Sep 2025: tools used, almost no `apply_patch` | Sep tool-share=49.1%, apply-share=0% | Supported |
| C21 | Oct 2025: very structured (high acceptance/planning/verification) | Oct acceptance=97.3% (peak), update-plan share=48.4%, verification=41.8% | Supported |
| C22 | Nov–Jan: shift to minimal prompts with verification drop | Minimal share rises to 64.4% (Nov), 51.1% (Dec), 68.0% (Jan); verification drops vs Oct | Supported |
| C23 | Feb: heavier tool use and more verification | Tool-share=91.0%, verification=43.8% | Supported |
| C24 | Mar: many execute sessions, high error, lowest acceptance criteria | Tool-share=100%, mean tool error=0.645, acceptance=15.4% (lowest) | Supported |

### G) Heroes/villains claims

| ID | ChatGPT claim | Fact-check | Verdict |
|---|---|---|---|
| C25 | `update_plan` sessions are more complex yet lower-error and more verified | Mean tool calls 66.27 vs 30.11, mean tokens 3.71M vs 1.54M, mean error 0.116 vs 0.236, verification 46.4% vs 31.8% | Supported |
| C26 | Subagent sessions are 12 | 12 sessions (`feature_subagents=1` or `subagent_spawn_count>0`) | Supported |
| C27 | Subagent sessions have median ~231 tool calls | Median tool calls in subagent sessions = 231 | Supported |
| C28 | Subagent sessions are not higher error | Subagent mean error=0.1833 vs non-subagent 0.1162 | Contradicted |
| C29 | ~75% sessions run zero verification commands | 75.59% with `verification_command_count=0` | Supported |
| C30 | ~16% sessions invoke skills | 16.05% with `skill_count>0` | Supported |

### H) Instrumentation-quality claims from ChatGPT

| ID | ChatGPT claim | Fact-check | Verdict |
|---|---|---|---|
| C31 | `prompt_has_plans_md` undercounts because it misses `PLAN.md` | Historical claim was valid for older script. Current script now detects `PLAN.md`, `PLANS.md`, `ExecPlan`; 36 sessions flagged | Supported (fixed) |
| C32 | `feature_web` undercounts browser/devtools activity | Historical claim was valid for older script. Current script now counts prefixed browser/devtools tools and web shell activity; `feature_web` now true in 20.07% sessions | Supported (fixed) |
| C33 | Objective preview still contains AGENTS/tool boilerplate | Still present in 47 sessions (`objective_preview` contains “available tools”) | Supported |

### I) Claims from the second ChatGPT answer (tool-install answer)

| ID | ChatGPT claim | Fact-check | Verdict |
|---|---|---|---|
| C34 | Your usage is interactive shell-heavy | 54.96% sessions have shell commands; top presence tools include `shell`, `exec_command`, `shell_command` | Supported |
| C35 | You under-leverage verify+ship automation | 75.59% sessions have zero verification; handoff only 4.79%; PR only 1.00% | Supported |
| C36 | “You already have `gh`” | Session logs show `gh` in 3 sessions (0.33%), but install status is not directly provable from tags | Partially supported |
| C37 | Product capability claims (pre-commit/ruff/biome/just/direnv/mise/etc. behavior) | External tool claims are not inferable from `tags.csv` alone | Not verifiable from sessions |

### J) Tool-by-tool adoption claims implied by second answer

These are factual checks for each named tool recommendation (not endorsement).

| ID | Suggested tool claim context | Session evidence (`executables_used`) | Verdict |
|---|---|---|---|
| C38 | Pre-commit would be newly useful | `pre-commit`: 0 sessions observed | Supported (as “not currently used”) |
| C39 | Ruff would be newly useful | `ruff`: 0 sessions observed | Supported (as “not currently used”) |
| C40 | Biome would be newly useful | `biome`: 0 sessions observed | Supported (as “not currently used”) |
| C41 | Just/Task runner is likely underused | `just`: 0, `task`: 1 session | Supported |
| C42 | Direnv is not currently part of workflow | `direnv`: 0 sessions | Supported |
| C43 | Mise is part of workflow | `mise`: 4 sessions | Partially supported (present, but low use) |
| C44 | GH CLI should be leveraged more | `gh`: 3 sessions; PR sessions only 1.00% | Supported |
| C45 | Delta/difftastic could improve diff review | `delta`: 0, `difftastic`: 0 sessions | Supported (as “not currently used”) |
| C46 | Watchexec could improve continuous verify loops | `watchexec`: 0 sessions | Supported (as “not currently used”) |
| C47 | Playwright is relevant in your workflow | `playwright`: 24 sessions | Supported |
| C48 | yq is not currently used | `yq`: 0 sessions | Supported |
| C49 | VisiData/sqlite-utils are not currently used | `visidata`: 0, `sqlite-utils`: 0 sessions | Supported |
| C50 | zoxide is not currently used | `zoxide`: 0 sessions | Supported |
| C51 | codex-1up is in current workflow | `codex-1up`: 0 sessions | Contradicted |

## Supported Recommendations (Data-Backed)

Only recommendations justified by supported claims are included.

1. **Make `update_plan` default for non-trivial tasks (`>10` expected tool calls).**
   - Why: lower mean error (0.116 vs 0.236) despite higher complexity.
   - Action: add a hard rule in your AGENTS prompt: “create/update plan before first edit unless task is trivial.”

2. **Enforce an edit-gate: every code edit must trigger at least one verification command.**
   - Why: 75.59% of sessions have zero verification; only 12.36% of edit sessions verify after edit.
   - Action: add a post-edit checklist step (`test` or `lint` or `build`) and fail session completion if skipped.

3. **Keep prompts concise, but always include constraints + done criteria.**
   - Why: minimal prompts correlate with higher errors; constraints and acceptance each cut mean error ~50%.
   - Action: standard 3-line template: Goal / Constraints / Done-when.

4. **Optimize mega-sessions first (top 10 = 39% of token load).**
   - Why: biggest leverage comes from reducing retries and context bloat in a small number of sessions.
   - Action: add mandatory decomposition for high-token runs (subtasks + checkpoints + context pruning).

5. **Increase end-to-end completion inside Codex (handoff discipline).**
   - Why: handoff only 4.79%; commit 3.90%; PR 1.00%.
   - Action: for non-trivial changes, require branch+commit and optionally draft PR text before exit.

6. **Target environment reliability in high-error working directories.**
   - Why: failure clustering in specific `/home/vscode/...` paths; Mar spike consistent with env mismatch.
   - Action: add per-repo bootstrap/check command and require running it before feature work.

7. **Increase skill usage in complex sessions.**
   - Why: only 16.05% sessions invoke skills despite high complexity in many runs.
   - Action: auto-inject skill references when intent matches (plan/code/data-analysis/webapp-testing).

8. **Use subagents selectively for scale, but add verification safeguards.**
   - Why: subagent sessions are much larger (median 231 tool calls), but currently have higher error rate than non-subagent sessions.
   - Action: require explicit verification agent or mandatory final validation phase for delegated flows.

9. **Finish objective-preview cleanup in tagger.**
   - Why: 47 sessions still show boilerplate in `objective_preview`.
   - Action: strengthen scaffolding stripping to drop AGENTS/INSTRUCTIONS blocks even when no explicit user objective follows.

10. **Install priorities tied to your measured gaps (if you want tooling changes now).**
   - Why: verify+handoff gaps are clear; most suggested tools are currently unused.
   - Action order:
     1. `pre-commit` + (`ruff` or repo-appropriate linter) for hard verification gates
     2. `just`/`task` for one-command workflows (`check`, `ship`)
     3. `direnv` for env consistency in high-error repos
     4. optional: `delta` for review ergonomics

## Notes on contradicted claims

- Strongest contradictions:
  - Work-session tool-call distribution (`median=20`, `p90=95.8`, not `7/70`)
  - Subagent error parity (subagent sessions are currently higher error on average)
  - `codex-1up` adoption (not seen in sessions)
- Recommendations depending on contradicted claims were not propagated.
