# Frozen Evaluation Pipeline

This source runs the Solver-Critic Pipeline on the question IDs stored in `frozen_test_question_ids.csv`. It loads the matching questions from the GSM8K `test` split without resampling.

The validation command checks the split, ID count, duplicates, missing IDs, expected interaction count, and both model directions without loading the language models:

```bash
python -m src.interact \
  --config configs/config_final_test.yaml \
  --validate-frozen-test
```

Run all 150 frozen questions in both directions with:

```bash
python -m src.interact \
  --config configs/config_final_test.yaml \
  --output-root /kaggle/working/runs/v6_final_test_150 \
  --question-limit 150
```

Use a new writable output directory for the evaluation run. Reusing that directory resumes from its checkpoint and skips completed question-direction pairs.

Generated outputs must remain outside `/kaggle/input/`.
