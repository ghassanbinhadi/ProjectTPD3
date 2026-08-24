"""
Policy definitions and scoring for the critique-acceptance decision.

Five policies (spec section 13): never-accept, adopt-critic, always-accept, the learned
policy (classifier-gated), and the oracle upper bound.
"""

import pandas as pd


def get_policy_final_answer(row, policy_name: str) -> str:
    """
    Return the final answer a given policy would produce for one interaction row.
    On agreement (revision_called == 0), every policy keeps the original answer.
    """
    if row["revision_called"] == 0:
        return str(row["solver_answer"]).strip()

    if policy_name == "1_never_accept":
        return str(row["solver_answer"]).strip()
    elif policy_name == "2_adopt_critic":
        return str(row["critic_proposed_answer"]).strip()
    elif policy_name == "3_always_accept":
        return str(row["revised_answer"]).strip()
    elif policy_name == "4_learned_policy":
        return (str(row["revised_answer"]).strip()
                if row["predicted_beneficial"] == 1
                else str(row["solver_answer"]).strip())
    elif policy_name == "5_oracle":
        return (str(row["revised_answer"]).strip()
                if row["transition"] == "HELPED"
                else str(row["solver_answer"]).strip())
    raise ValueError(f"Unknown policy: {policy_name}")


def check_correctness(final_ans, gold_ans) -> bool:
    """Numeric-first comparison, falling back to string equality if not parseable."""
    try:
        return float(final_ans) == float(gold_ans)
    except (TypeError, ValueError):
        return str(final_ans).strip() == str(gold_ans).strip()


POLICIES = ["1_never_accept", "2_adopt_critic", "3_always_accept", "4_learned_policy", "5_oracle"]


def score_all_policies(test_valid: pd.DataFrame, test_predictor: pd.DataFrame,
                        final_model, final_scaler, active_features: list):
    """
    Score all 5 policies against a test set. `test_predictor` gets classifier predictions
    from `final_model` (already fit on dev data -- not refit here). Returns
    (policy_accuracies dict, the full evaluation dataframe with predictions attached).
    """
    test_predictor = test_predictor.copy()
    X_scaled = final_scaler.transform(test_predictor[active_features])
    test_predictor["predicted_beneficial"] = final_model.predict(X_scaled)

    test_eval = test_valid.copy()
    test_eval["predicted_beneficial"] = 0
    test_eval.loc[test_predictor.index, "predicted_beneficial"] = test_predictor["predicted_beneficial"]

    policy_accuracies = {}
    for pol in POLICIES:
        correct = test_eval.apply(
            lambda r: check_correctness(get_policy_final_answer(r, pol), r["gold_answer"]),
            axis=1,
        ).sum()
        policy_accuracies[pol] = correct / len(test_eval)

    return policy_accuracies, test_eval
