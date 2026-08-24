# Predicting Beneficial LLM Critiques

This project studies whether a language model should revise its answer after an
independent model disagrees. It uses GSM8K with two directions:

- Qwen2.5-3B-Instruct Solver -> Llama-3.2-3B-Instruct Critic
- Llama-3.2-3B-Instruct Solver -> Qwen2.5-3B-Instruct Critic

The Critic solves each problem independently before comparing answers. Revision is
called only when the Critic returns `INCORRECT`.

## Labels

- `HELPED`: wrong answer becomes correct.
- `HURT`: correct answer becomes wrong.
- `STABLE-CORRECT`: correct answer stays correct.
- `STABLE-WRONG`: wrong answer stays wrong.

The classifier target `beneficial` is `1` only for `HELPED`.

## Experimental Setup

- Development: 1,000 fixed questions from the GSM8K train split.
- Evaluation: 150 frozen questions from the GSM8K test split.
- Each question runs in both model directions.
- Models are loaded one at a time in 4-bit NF4.
- The first generation attempt is greedy.
- One parsing retry is allowed with `do_sample=True` and `temperature=0.7`.
- Every interaction is saved immediately, and checkpoint/resume prevents duplication.

## Run on Kaggle

1. Enable a GPU and Internet access.
2. Add a Kaggle secret named `HF_TOKEN` with Hugging Face read access.
3. Upload the project as a Kaggle Dataset.
4. Open `notebooks/pilot.ipynb` and run the cells in order.
5. Store every generated artifact under `/kaggle/working/`; `/kaggle/input/` is read-only.

Use the same development output directory for the 50-question pilot and the later
1,000-question continuation.

### Command-Line Alternative

Run a separate five-question debug:

```bash
python -m src.interact \
  --config configs/config.yaml \
  --output-root /kaggle/working/debug_5 \
  --debug-sample-size 5
```

Run the first 50 development questions:

```bash
python -m src.interact \
  --config configs/config.yaml \
  --output-root /kaggle/working/project_v7_1000 \
  --question-limit 50
```

Resume the same cohort and complete all 1,000 questions:

```bash
python -m src.interact \
  --config configs/config.yaml \
  --output-root /kaggle/working/project_v7_1000 \
  --question-limit 1000
```

## Build the Dataset and Features

After generation, build the verified dataset from the saved interaction JSONL files:

```bash
python -m src.verify \
  --config configs/config.yaml \
  --raw-dir /kaggle/working/project_v7_1000/data/raw \
  --output-root /kaggle/working/project_v7_1000
```

Then extract pre-revision features:

```bash
python -m src.features \
  --input /kaggle/working/project_v7_1000/data/processed/dataset.csv \
  --output /kaggle/working/project_v7_1000/data/processed/dataset_with_features.csv \
  --checkpoint /kaggle/working/project_v7_1000/pipeline_outputs.jsonl
```

## Run Modeling

The repository already contains the prepared development and evaluation feature
datasets used by the training script. From the project root, run:

```bash
python src/train.py
```

The script performs grouped 5-fold `StratifiedGroupKFold` cross-validation, fits the
final Logistic Regression model on development disagreements, and scores the frozen
evaluation set once.

## Frozen Evaluation

Validate the frozen 150-question set without generating model outputs:

```bash
cd evaluation/source
python -m src.interact \
  --config configs/config_final_test.yaml \
  --validate-frozen-test
```

The evaluation set must not be resampled or used to tune features, models, or the
classification threshold.

## Key Outputs

- Verified datasets and features are under `data/processed/`.
- Metrics and policy comparisons are under `results/`.
- Generated charts are under `figures/`.
- Frozen evaluation records, audits, and demo cases are under `evaluation/`.
