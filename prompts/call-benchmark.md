# Call benchmark, 01 Oct 2026

Keep the current model/thinking default, 40-line / 12,000-character continuity
context, and friendly chunk planning with a 30-minute maximum. Cheaper thinking
roughly halved the measured bill but produced more unsupported names, boilerplate,
summaries and omissions. Smaller/no context did not improve fidelity. There is no
evidence here to change the production defaults.

Two confident fixes came from the experiments:

- Absorb at most one second beyond a nominal boundary into the preceding chunk.
  The four-minute Opus clip was 240.0065 seconds long; previously its extra 6.5ms
  triggered a separate paid chunk. All audio is retained by the new plan.
- Preserve valid text before an out-of-window inline timestamp. Previously one
  long paragraph was discarded in full, triggering an unnecessary paid retry.
  Replaying its saved raw response after the fix accepts the valid prefix with
  zero API calls. The raw continuation remains available for diagnosis.

## Thinking comparison

Five complete short recordings (86–136 seconds) were each transcribed once with
the existing default, minimal and low thinking. Same model, audio and system
prompt; no production notes were overwritten. Exact requests, response metadata,
modality usage, costs and elapsed times are retained in the artifacts below.

| Thinking | Requests | Estimated cost | Sum of upload/generation seconds | Thinking tokens |
| --- | ---: | ---: | ---: | ---: |
| Default | 5 | $0.047081 | 70.96 | 7,886 |
| Minimal | 5 | $0.024638 | 39.74 | 0 |
| Low | 5 | $0.023429 | 35.35 | 0 |

The samples were Nutan/Optum, Pyconf, Kamatchi's tax discussion, a PKF school
discussion, and Manju/Aditi. They cover conversation, a talk fragment, technical
and financial terms, mixed-language phrases, different speech densities and one
stereo recording. None were skipped in the final comparison.

Qualitative comparison against existing notes and the default output found:

- Minimal reversed/guessed participants in the tax call and added unsupported
  speaker names elsewhere. It also added unsolicited takeaway sections.
- Low was generally preferable to minimal, but still guessed names, merged turns,
  omitted detail and added summaries or framing absent from the default output.
- Default better preserved substantive discussion across these samples, although
  it also contained uncertain recognitions and imperfect speaker labels.

Existing transcripts are comparison references, not independently verified ground
truth. Text similarity was computed for inspection, not presented as word error
rate. Each setting has one trial per recording; latency and output vary between
runs. These findings support retaining fidelity-oriented defaults, not a universal
claim that more thinking always improves transcription.

## Context and chunk boundaries

The same 240-second JnJ excerpt, beginning 180 seconds into the original recording,
was transcribed whole and in one/two-minute chunks using low thinking. The prompt
named Anand, Rishi and Nutan. Other settings were held constant. The table shows
the corrected chunk plans; the initial padding-affected artifacts are also saved.

| Plan / continuity context | Audio chunks | Paid requests | Estimated cost | Sum of upload/generation seconds |
| --- | ---: | ---: | ---: | ---: |
| Whole excerpt | 1 | 1 | $0.009338 | 10.82 |
| Two minutes / 40 lines | 2 | 2 | $0.010286 | 17.06 |
| Two minutes / 10 lines | 2 | 2 | $0.010534 | 17.29 |
| Two minutes / none | 2 | 2 | $0.011005 | 22.12 |
| One minute / 10 lines | 4 | 5 | $0.032525 | 61.18 |

The one-minute run's fifth request was the inline-timestamp retry described above.
Its bill includes both paid responses. This was repaired using the raw receipt;
the experiment was not repeated again at additional cost.

Forty-line context gave the cleanest boundary flow and most stable speakers.
Ten lines added more explanatory material without a cost advantage. No context
was less reliable for diarization and continuity. One-minute chunks fragmented
utterances and added more framing and invented setup. The whole-excerpt output
is another model output, not ground truth.

This short excerpt tests boundary behavior, not whether 15, 20 or 30-minute
production chunks are optimal. Existing friendly 15/20/25/30-minute planning and
the context cap remain unchanged. A longer, independently reviewed benchmark
would be needed to justify changing them.

## Artifacts and reproduction

All experiment files are local under `../.cache/call-benchmark/` (Git-ignored):

- `runner.py`: resumable five-recording thinking comparison; run with
  `uv run .cache/call-benchmark/runner.py 5` from the repository root.
- `boundaries.py`: same-excerpt context/chunk experiment; skips completed outputs.
- `metrics.py` and `boundary_metrics.py`: regenerate the measured tables.
- `results/`, `boundaries/`, `references/`, `audio/`: generated transcripts,
  read-only reference copies and local input copies/excerpt.
- `cache/`, `boundary-cache/`: per-request state and per-run diagnostic logs.
- `boundaries-before/`, `boundary-cache-before/`: padding-affected trials retained
  for comparison; `jobs.jsonl` and `boundary-jobs.jsonl` retain process timings.
- `metrics.json` and `boundary-metrics.json`: structured measurements.

Total experimental responses: **41**, estimated cost **$0.220738** including the
padding-affected trials, their corrected reruns and the paid inline-timestamp
retry. No full-length production recordings were retranscribed. Original audio
and transcript notes were preserved. No artifacts were deleted or published.

Operational logging now captures one private folder per invocation under
`~/.cache/sanand-scripts/transcribe_calls/runs/` (or the configured cache). Help
does not create logs; dry runs and list/skip/error operations do. Summaries contain
arguments, versions, code hash, elapsed time, exit status, request/cache counts
and new cost. Events include source/chunk identity, processing/upload timing,
generation settings, raw response receipts, response IDs/finish reasons and
token/pricing breakdowns. Console errors and unexpected tracebacks are retained.
API keys are excluded. Hard termination leaves a running summary and the last
flushed events rather than falsely claiming completion.

## Design simplification

Fish usage and history still justify multiple audio arguments, substring lookup,
prompt metadata, force, patch, change listing and legacy timestamp repair. These
features were retained. `prompts/call.md` now explicitly separates the active
contract from historical requests for glob filtering, no-argument batch mode,
expiring caches, five-line validation and inaccurate timestamps.

For thinking experiments, Google documents the level control in its
[thinking guide](https://ai.google.dev/gemini-api/docs/thinking); measurements here
use the installed SDK's `GenerateContentConfig.thinking_config` against the
existing `gemini-3-flash-preview`, with returned usage recorded per response.
