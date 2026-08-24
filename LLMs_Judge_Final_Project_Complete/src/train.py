"""
Training entry point for the critique-acceptance predictor.

Runs 5-fold StratifiedGroupKFold cross-validation (grouped by question_id) on the dev-set
disagreement population, fits one final model on the full dev set, and scores it once
against the frozen test set. Run as a script:

    python src/train.py
"""

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (
    precision_score, recall_score, f1_score,
    average_precision_score, roc_auc_score, confusion_matrix,
)

from split import load_predictor_population, select_active_features, ACTIVE_FEATURES
from baselines import score_all_policies
from metrics import format_cv_summary
from plots import save_ablation_plot, save_policy_plot

DEV_CSV = "data/processed/dataset_with_features.csv"
TEST_CSV = "data/processed/test_dataset_with_features.csv"


def evaluate_logistic_cv(X, y, groups, n_splits=5, seed=42):
    """
    5-fold StratifiedGroupKFold cross-validation with a balanced logistic regression classifier.
    Groups by question_id so no question's interactions cross a fold boundary while
    preserving class balance across folds.
    Returns (metric_summary, out-of-fold predictions, out-of-fold probabilities).
    """
    sgkf = StratifiedGroupKFold(n_splits=n_splits)
    raw_metrics = {"precision": [], "recall": [], "f1": [], "pr_auc": [], "roc_auc": [],
                    "tn": [], "fp": [], "fn": [], "tp": []}
    oof_preds = np.zeros(len(X))
    oof_probs = np.zeros(len(X))

    for train_idx, val_idx in sgkf.split(X, y, groups):
        X_tr, y_tr = X.iloc[train_idx], y.iloc[train_idx]
        X_va, y_va = X.iloc[val_idx], y.iloc[val_idx]

        scaler = StandardScaler()
        X_tr_s = scaler.fit_transform(X_tr)
        X_va_s = scaler.transform(X_va)

        model = LogisticRegression(class_weight="balanced", max_iter=1000, random_state=seed)
        model.fit(X_tr_s, y_tr)

        probs = model.predict_proba(X_va_s)[:, 1]
        preds = (probs >= 0.5).astype(int)
        oof_probs[val_idx] = probs
        oof_preds[val_idx] = preds

        raw_metrics["precision"].append(precision_score(y_va, preds, zero_division=0))
        raw_metrics["recall"].append(recall_score(y_va, preds, zero_division=0))
        raw_metrics["f1"].append(f1_score(y_va, preds, zero_division=0))
        tn, fp, fn, tp = confusion_matrix(y_va, preds, labels=[0, 1]).ravel()
        raw_metrics["tn"].append(tn); raw_metrics["fp"].append(fp)
        raw_metrics["fn"].append(fn); raw_metrics["tp"].append(tp)
        if len(np.unique(y_va)) > 1:
            raw_metrics["pr_auc"].append(average_precision_score(y_va, probs))
            raw_metrics["roc_auc"].append(roc_auc_score(y_va, probs))

    summary = format_cv_summary(raw_metrics)
    return summary, oof_preds, oof_probs


def run_ablation(predictor_df, y, groups):
    """Direction only / critique features only / all combined, under identical CV."""
    from split import DIRECTION_COLS, CRITIQUE_COLS

    ablation_sets = {
        "Direction Only": DIRECTION_COLS,
        "Critique Features Only": CRITIQUE_COLS,
        "All (Combined)": ACTIVE_FEATURES,
    }
    results = []
    for name, cols in ablation_sets.items():
        res, _, _ = evaluate_logistic_cv(predictor_df[cols], y, groups, n_splits=5)
        results.append({
            "Feature Subset": name, "Num Features": len(cols),
            "Precision": res["precision"], "Recall": res["recall"],
            "F1 Score": res["f1"], "PR-AUC": res["pr_auc"], "ROC-AUC": res["roc_auc"],
        })
    return pd.DataFrame(results)


def fit_final_model(predictor_df, y):
    """Fit one model on the full dev-set disagreement population (not a CV-fold ensemble)."""
    scaler = StandardScaler().fit(predictor_df[ACTIVE_FEATURES])
    X_scaled = scaler.transform(predictor_df[ACTIVE_FEATURES])
    model = LogisticRegression(class_weight="balanced", max_iter=1000, random_state=42)
    model.fit(X_scaled, y)
    return model, scaler


def main():
    # --- Dev set: CV, ablation, final model fit ---
    valid_df, predictor_df = load_predictor_population(DEV_CSV)
    active_features, dropped = select_active_features(predictor_df)
    print("Dropped (near-constant):", dropped)

    y = predictor_df["beneficial"].astype(int)
    groups = predictor_df["question_id"]

    cv_summary, oof_preds, oof_probs = evaluate_logistic_cv(predictor_df[active_features], y, groups)
    print("\n--- Dev-Set CV Predictor Performance (All Features) ---")
    for metric in ["precision", "recall", "f1", "pr_auc", "roc_auc"]:
        print(f"{metric.upper():<10}: {cv_summary[metric]}")

    ablation_df = run_ablation(predictor_df, y, groups)
    print("\n--- 3-Way Feature Ablation ---")
    print(ablation_df)
    save_ablation_plot(ablation_df)

    final_model, final_scaler = fit_final_model(predictor_df, y)
    print(f"\nFinal model fit on {len(predictor_df)} dev disagreement rows.")

    # --- Frozen test set: score once ---
    test_valid, test_predictor = load_predictor_population(TEST_CSV)
    test_policy_accuracies, test_eval = score_all_policies(
        test_valid, test_predictor, final_model, final_scaler, active_features
    )
    print(f"\n--- FROZEN TEST SET Policy Accuracy (n = {len(test_eval)}) ---")
    for pol, acc in test_policy_accuracies.items():
        print(f"{pol:<20}: {acc:.2%}")
    save_policy_plot(test_policy_accuracies, n=len(test_eval))


if __name__ == "__main__":
    main()
