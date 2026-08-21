"""
Feature selection and dataset-splitting utilities for the critique-acceptance predictor.

Filters the dev/test datasets down to the disagreement population the predictor trains
and evaluates on, and runs the variance/near-constancy check that determines the active
feature set.
"""

import pandas as pd

# Confirmed active feature set (near-constancy-checked; see select_active_features).
ACTIVE_FEATURES = [
    "answer_distance_log1p",
    "answer_distance_norm",
    "answer_distance_signed_log1p",
    "hedging_count",
    "error_desc_length",
    "direction_llama_solver_qwen_critic",
    "direction_qwen_solver_llama_critic",
]

DIRECTION_COLS = [
    "direction_llama_solver_qwen_critic",
    "direction_qwen_solver_llama_critic",
]

CRITIQUE_COLS = [c for c in ACTIVE_FEATURES if c not in DIRECTION_COLS]


def load_predictor_population(csv_path: str) -> pd.DataFrame:
    """
    Load a dataset CSV and filter to the predictor population: valid interactions where
    the Critic disagreed and a revision was generated (revision_called == 1).

    Agreement cases are excluded, since the predictor's decision only applies when there
    is a disagreement to act on.
    """
    df = pd.read_csv(csv_path)
    valid_df = df[df["valid"] == 1].copy() if "valid" in df.columns else df.copy()
    predictor_df = valid_df[valid_df["revision_called"] == 1].copy()
    return valid_df, predictor_df


def select_active_features(predictor_df: pd.DataFrame) -> list:
    """
    Reproduce the variance / near-constancy check used to arrive at ACTIVE_FEATURES.

    A feature is dropped if it is constant (var == 0) or near-constant (majority-class
    share >= 95%), even if its raw variance is nonzero -- this is what excludes
    `proposed_answer_differs`, which is nonzero-variance but 98.3% one value.
    """
    candidate_features = [
        col for col in predictor_df.columns
        if col.startswith((
            "answer_distance", "hedging_count", "error_desc_length",
            "critique_tokens", "solver_tokens", "critic_independent_tokens",
            "direction_", "proposed_answer_differs",
        ))
    ]

    feature_variances = predictor_df[candidate_features].var(numeric_only=True)
    nonzero_var = feature_variances[feature_variances > 0].index.tolist()

    near_constant_cols = [
        c for c in nonzero_var
        if predictor_df[c].value_counts(normalize=True).iloc[0] >= 0.95
    ]

    assert set(near_constant_cols).isdisjoint(ACTIVE_FEATURES), (
        "a near-constant feature leaked into ACTIVE_FEATURES"
    )
    return ACTIVE_FEATURES, near_constant_cols
