"""
Metric summarization and results-artifact saving for the predictor.
"""

import json
import os

import numpy as np
import pandas as pd


def format_cv_summary(raw_metrics: dict) -> dict:
    """Mean +/- std across folds for each metric, formatted as a display string."""
    return {
        k: f"{np.mean(v):.3f} \u00b1 {np.std(v):.3f}"
        for k, v in raw_metrics.items()
    }


def save_results(cv_summary: dict, ablation_df: pd.DataFrame,
                  test_policy_accuracies: dict, test_eval: pd.DataFrame,
                  results_dir: str = "results"):
    """
    Save the ablation table, policy comparison table, and a summary metrics JSON,
    matching the file layout in spec section 16 (results/metrics.json,
    results/policy_comparison.csv).
    """
    os.makedirs(results_dir, exist_ok=True)

    ablation_df.to_csv(os.path.join(results_dir, "ablation_3way.csv"), index=False)

    pd.DataFrame(
        list(test_policy_accuracies.items()), columns=["Policy", "Accuracy"]
    ).to_csv(os.path.join(results_dir, "policy_comparison.csv"), index=False)

    summary_artifact = {
        "dev_cv_metrics_all_features": cv_summary,
        "test_policy_accuracies": test_policy_accuracies,
        "test_set_n": len(test_eval),
    }
    with open(os.path.join(results_dir, "modeling_metrics.json"), "w") as f:
        json.dump(summary_artifact, f, indent=2)

    print(f"Saved: {results_dir}/ablation_3way.csv, "
          f"{results_dir}/policy_comparison.csv, "
          f"{results_dir}/modeling_metrics.json")
