# Frozen Evaluation Pipeline

This source runs the Solver-Critic Pipeline on the question IDs stored in `frozen_test_question_ids.csv`. It loads the matching questions from the GSM8K `test` split without resampling.

The validation command checks the split, ID count, duplicates, missing IDs, expected interaction count, and both model directions without loading the language models:

```bash
python -m src.interact \
  --config configs/config_final_test.yaml \
  --validate-frozen-test
```

Run the evaluation with a new writable output directory:

```bash
python -m src.interact \
  --config configs/config_final_test.yaml \
  --output-root /kaggle/working/final_test_150
```

Reusing that output directory resumes from its checkpoint and skips completed question-direction pairs.

Generated outputs must remain outside `/kaggle/input/`.
