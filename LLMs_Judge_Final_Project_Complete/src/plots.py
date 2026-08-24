"""
Figure generation for the modeling results: 3-way ablation and frozen-test-set
policy comparison, matching spec section 16 (figures/ablation.png,
figures/policy_vs_oracle.png).
"""

import os

import pandas as pd
import matplotlib.pyplot as plt


def save_ablation_plot(ablation_df: pd.DataFrame, figures_dir: str = "figures"):
    """Bar chart of PR-AUC by feature subset (direction only / critique only / all)."""
    os.makedirs(figures_dir, exist_ok=True)

    pr_auc_values = ablation_df["PR-AUC"].apply(lambda s: float(s.split(" ")[0]))

    plt.figure(figsize=(8, 5))
    plt.bar(
        ablation_df["Feature Subset"], pr_auc_values,
        color=["#4C72B0", "#DD8452", "#55A868"], edgecolor="black",
    )
    plt.ylabel("PR-AUC (mean across folds)")
    plt.title("3-Way Ablation: Direction vs. Critique Features vs. All")
    plt.xticks(rotation=10)
    plt.tight_layout()
    path = os.path.join(figures_dir, "ablation.png")
    plt.savefig(path)
    plt.close()
    print(f"Saved: {path}")


def save_policy_plot(test_policy_accuracies: dict, n: int, figures_dir: str = "figures"):
    """Bar chart of policy accuracy on the frozen test set, against the oracle ceiling."""
    os.makedirs(figures_dir, exist_ok=True)

    policy_series = pd.Series(test_policy_accuracies)

    plt.figure(figsize=(9, 5))
    bars = plt.bar(policy_series.index, policy_series.values, color="skyblue", edgecolor="black")
    plt.ylabel("Overall Accuracy")
    plt.title(f"Frozen Test Set: Policy Comparison vs. Oracle Ceiling (n={n})")
    plt.ylim(0, 1.0)
    for bar in bars:
        yval = bar.get_height()
        plt.text(bar.get_x() + bar.get_width() / 2.0, yval + 0.02, f"{yval:.1%}",
                  ha="center", va="bottom", fontweight="bold")
    plt.xticks(rotation=15)
    plt.tight_layout()
    path = os.path.join(figures_dir, "policy_vs_oracle.png")
    plt.savefig(path)
    plt.close()
    print(f"Saved: {path}")
