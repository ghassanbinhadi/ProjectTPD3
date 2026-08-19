# LLMs Judge

This project studies whether a solver should revise a numeric answer after an independent critic disagrees. It runs Qwen2.5-3B-Instruct and Llama-3.2-3B-Instruct in both solver-critic directions on GSM8K.

## Pipeline

1. The Solver produces a numeric answer.
2. The Critic solves the question independently.
3. The Critic compares both answers and returns a verdict.
4. The Solver revises only when the verdict is `INCORRECT`.
5. Every interaction is appended to JSONL and tracked by checkpoint files.
6. `src/verify.py` builds `dataset.csv` and `metrics.json` from saved interactions.

Models are loaded one at a time with 4-bit NF4 quantization. The first generation attempt is greedy. A single parse retry uses sampling with temperature `0.7` while keeping the prompt unchanged.

## Run on Kaggle

Add an enabled Kaggle secret named `HF_TOKEN`, attach the project as an input dataset, and open `notebooks/pilot.ipynb`. Generated files are written under `/kaggle/working/`.

The main configuration is `configs/config.yaml`. Keep the same output directory when resuming an interrupted run.

## Evaluation

Build processed outputs from existing interaction files without rerunning the models:

```bash
python -m src.verify \
  --config configs/config.yaml \
  --raw-dir data/raw \
  --output-root .
```

Generated raw records, checkpoints, logs, model weights, tokens, and local environment files are excluded from Git.

## Frozen Evaluation

The exact source used for the frozen 150-question GSM8K test evaluation is preserved under `evaluation_snapshot/`. It remains separate because its `interact.py` contains frozen-ID selection and validation logic that is not present in the Development runner.

Validate the published test IDs without loading either model:

```bash
cd evaluation_snapshot
python -m src.interact \
  --config configs/config_final_test.yaml \
  --validate-frozen-test
python -m unittest discover -s tests -p 'test_frozen_test.py' -v
python -m unittest discover -s tools -p 'test_reparse_final_test.py' -v
```

Published evaluation artifacts:

- `data/processed/frozen_test_question_ids.csv`
- `data/processed/dataset_final_test.csv`
- `results/metrics_final_test.json`
- `results/revision_reparse_audit.csv`
- `results/demo_cases.md`

The corrected evaluation dataset was rebuilt from saved outputs with a deterministic, gold-blind parser. No model generation was rerun. Raw interaction JSONL files remain in the external experiment archive rather than the Git repository.
