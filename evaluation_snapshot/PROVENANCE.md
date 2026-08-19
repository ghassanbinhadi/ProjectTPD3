# Evaluation Source Provenance

The executable source used for the 150-question evaluation is preserved in this directory. Its comments and documentation were cleaned for publication; executable AST checks confirmed that the logic did not change.

Original source hashes recorded by the run:

| File | SHA-256 |
|---|---|
| `configs/prompts.py` | `87e13b8fad95500bfe81e24e144c43b1194d0b68d6b816c09f4c028212fb14b1` |
| `src/interact.py` | `efbc9309ece2a7002f145ac936ce120aa310e50f934950a6bac8a66d20bc91b9` |
| `src/models.py` | `fa124b235795be42876e08698c36989defab099701f942b16689ce60e0b4fd7c` |
| `frozen_test_question_ids.csv` | `b36b02e590402e552edce1227e1919725919e3d4c1883c5fb3044ecd0770e747` |

Runtime model revisions:

- `Qwen/Qwen2.5-3B-Instruct@aa8e72537993ba99e69dfaafa59ed015b17504d1`
- `meta-llama/Llama-3.2-3B-Instruct@0cb88a4f764b7a12671c53f0838cd831a0843b95`
- `transformers==5.0.0`

The corrected dataset uses the saved raw outputs. Five revision responses were recovered by one deterministic, gold-blind parsing rule; no model generation was rerun.
