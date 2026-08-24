# V6 Final Test Revision Re-parse

No model generation was run. The original archive and V6 code were not modified.

## Deterministic rule

Allow arbitrary preamble before one exact REASONING marker; require exactly one DECISION line containing KEEP or CHANGE; use the last FINAL_ANSWER marker and strictly parse the first non-empty line after it as one signed integer or decimal. Process attempts in original order and select the earliest parseable attempt.

The attempts are checked in original order and the earliest parseable attempt is selected. Gold answers are not available to the parser.

## Before and after

| Metric | Before | After |
|---|---:|---:|
| Valid | 293 | 298 |
| Invalid | 7 | 2 |
| HELPED | 3 | 5 |
| HURT | 5 | 5 |
| STABLE-CORRECT | 264 | 265 |
| STABLE-WRONG | 21 | 23 |

## After re-parsing by direction

| Direction | HELPED | HURT | STABLE-CORRECT | STABLE-WRONG |
|---|---:|---:|---:|---:|
| qwen_solver_llama_critic | 2 | 3 | 133 | 10 |
| llama_solver_qwen_critic | 3 | 2 | 132 | 13 |

Recovered revisions: 5/5.
Remaining invalid interactions: 2 (both are non-revision failures).
