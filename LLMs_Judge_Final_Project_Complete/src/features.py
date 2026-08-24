"""Feature engineering for the LLM-as-judge revision dataset.

Given the parsed interaction dataset (dataset.csv) and, optionally, the raw
pipeline records it was derived from (pipeline_outputs.jsonl or
checkpoint.json), this module recovers the raw critique text that dataset.csv
doesn't carry, builds the modeling features (answer-distance family,
hedging/error-description features, direction one-hot encoding), enforces
the two feature-selection boundaries (no label leakage, no post-decision
fields), and runs a variance check to decide which candidate features are
stable enough to model on the disagreement-only population.

Public API
----------
attach_critique_raw(df, path)   Recover the raw critique text from the
                                 pipeline records and join it onto a
                                 dataset.csv-shaped frame as `critique_raw`.
build_features(df)              Add all feature/characterization columns to
                                 a copy of the input frame. Non-destructive:
                                 nothing is dropped, so excluded columns
                                 remain available for inspection.
feature_columns(...)            The candidate feature set passed to the
                                 classifier by default.
audit_features(...)             Check a feature set against the leakage and
                                 post-decision boundaries.
variance_check(...)             Report which candidate features are stable
                                 enough to keep on the disagreement-only
                                 population.

Command line
------------
    python features.py --input dataset.csv --output dataset_with_features.csv \\
        [--checkpoint pipeline_outputs.jsonl_or_checkpoint.json]

--checkpoint is optional; include it whenever critique_raw isn't already
in --input, which is the normal case for a fresh dataset.csv.
"""

from __future__ import annotations

import json
import math
import re
import sys
import warnings
from typing import Dict, Iterable, List, Optional, Sequence

import numpy as np
import pandas as pd


def answers_match(a: float, b: float, tol: float = 1e-6) -> bool:
    """Check whether two already-parsed numeric answers are equal within tolerance.

    Args:
        a: First numeric value.
        b: Second numeric value.
        tol: Absolute tolerance for equality.

    Returns:
        True if abs(a - b) <= tol.
    """
    return abs(a - b) <= tol


# --------------------------------------------------------------------------- #
# Feature definitions
# --------------------------------------------------------------------------- #

# Hedging terms used by hedging_count(). Matched case-insensitively with word
# boundaries, so e.g. "unlikely" does not match "likely" and "seemed" does not
# match "seems". Vocabulary is tuned to the critique model actually in use;
# re-derive it from a fresh critique corpus if the critic model or prompt
# changes.
HEDGING_TERMS: Sequence[str] = (
    "maybe",
    "perhaps",
    "might",
    "possibly",
    "i think",
    "seems",
    "seem to",
    "likely",
    "probably",
    "may",
    "could be",
    "appears",
    "appear to",
    "presumably",
    "i believe",
    "i suspect",
    "unclear",
    "uncertain",
    "not certain",
    "unsure",
    "should be",
    "potentially",
    "arguably",
)
_HEDGING_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(t) for t in HEDGING_TERMS) + r")\b",
    re.IGNORECASE,
)


def _to_number(x) -> Optional[float]:
    """Coerce a value to float, tolerating missing or unparseable input.

    Args:
        x: Raw cell value (may be None, NaN, a string, or a number).

    Returns:
        The value as a float, or None if it is missing or cannot be parsed.
    """
    if x is None:
        return None
    if isinstance(x, float) and math.isnan(x):
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def answer_distance(solver_answer, critic_independent_answer) -> Optional[float]:
    """Compute the absolute numeric gap between the solver's and critic's answers.

    Args:
        solver_answer: The solver model's final answer.
        critic_independent_answer: The critic's answer from its own independent
            (blind) solve of the same problem.

    Returns:
        abs(solver_answer - critic_independent_answer), or None if either
        value is missing.
    """
    a_s, a_c = _to_number(solver_answer), _to_number(critic_independent_answer)
    if a_s is None or a_c is None:
        return None
    return abs(a_s - a_c)


def answer_distance_norm(solver_answer, critic_independent_answer) -> Optional[float]:
    """Compute the scale-normalized distance between the solver's and critic's answers.

    Args:
        solver_answer: The solver model's final answer.
        critic_independent_answer: The critic's independently derived answer.

    Returns:
        abs(a_s - a_c) / max(abs(a_s), abs(a_c), 1), or None if either value
        is missing.
    """
    a_s, a_c = _to_number(solver_answer), _to_number(critic_independent_answer)
    if a_s is None or a_c is None:
        return None
    return abs(a_s - a_c) / max(abs(a_s), abs(a_c), 1.0)


def answer_distance_log1p(solver_answer, critic_independent_answer) -> Optional[float]:
    """Compute a log-compressed version of the answer distance.

    Reduces the influence of large-magnitude problems on the raw distance
    scale, which otherwise skews heavily toward a small number of outliers.

    Args:
        solver_answer: The solver model's final answer.
        critic_independent_answer: The critic's independently derived answer.

    Returns:
        log1p(abs(a_s - a_c)), or None if either value is missing.
    """
    a_s, a_c = _to_number(solver_answer), _to_number(critic_independent_answer)
    if a_s is None or a_c is None:
        return None
    return math.log1p(abs(a_s - a_c))


def answer_distance_signed(solver_answer, critic_independent_answer) -> Optional[float]:
    """Compute the signed gap between the solver's and critic's answers.

    Positive values mean the solver answered higher than the critic's
    independent solve; negative values mean lower. This feature is
    heavy-tailed on its raw scale — large-magnitude problems can produce
    outliers well outside the typical range — so it is treated as a
    characterization feature rather than a classifier default. See
    `answer_distance_signed_log1p` for the modeling-friendly version.

    Args:
        solver_answer: The solver model's final answer.
        critic_independent_answer: The critic's independently derived answer.

    Returns:
        solver_answer - critic_independent_answer, or None if either value
        is missing.
    """
    a_s, a_c = _to_number(solver_answer), _to_number(critic_independent_answer)
    if a_s is None or a_c is None:
        return None
    return a_s - a_c


def answer_distance_signed_log1p(solver_answer, critic_independent_answer) -> Optional[float]:
    """Compute a sign-preserving, log-compressed version of the signed gap.

    Carries the same directional information as `answer_distance_signed`
    on a scale that is not dominated by a handful of large outliers, which
    makes it the classifier-default variant of the two.

    Args:
        solver_answer: The solver model's final answer.
        critic_independent_answer: The critic's independently derived answer.

    Returns:
        sign(d) * log1p(abs(d)), where d = solver_answer -
        critic_independent_answer, or None if either value is missing.
    """
    a_s, a_c = _to_number(solver_answer), _to_number(critic_independent_answer)
    if a_s is None or a_c is None:
        return None
    d = a_s - a_c
    sign = -1.0 if d < 0 else 1.0
    return sign * math.log1p(abs(d))


def proposed_answer_differs(critic_proposed_answer, solver_answer, tol: float = 1e-6) -> int:
    """Flag whether the critic's proposed answer differs from the solver's answer.

    On the disagreement population this tends to be near-constant, since a
    critic proposing an error correction usually differs from the solver's
    answer almost by definition. See `critic_answer_differs_from_own_solve`
    for a feature that captures a rarer, less redundant signal.

    Args:
        critic_proposed_answer: The answer proposed during the critique stage.
        solver_answer: The solver model's final answer.
        tol: Absolute tolerance for numeric equality.

    Returns:
        1 if the two answers differ, 0 if they match or either is missing.
    """
    a_p, a_s = _to_number(critic_proposed_answer), _to_number(solver_answer)
    if a_p is None or a_s is None:
        return 0
    return 0 if answers_match(a_p, a_s, tol) else 1


def critic_answer_differs_from_own_solve(
    critic_proposed_answer, critic_independent_answer, tol: float = 1e-6
) -> int:
    """Flag whether the critic revised its own answer during the critique stage.

    Captures whether the critic's proposed answer changed between its
    independent-solve stage and its critique stage — a different, rarer
    signal than `proposed_answer_differs`, which mostly reduces to comparing
    against the solver's answer.

    Args:
        critic_proposed_answer: The answer proposed during the critique stage.
        critic_independent_answer: The critic's answer from its own
            independent (blind) solve.
        tol: Absolute tolerance for numeric equality.

    Returns:
        1 if the two answers differ, 0 if they match or either is missing.
    """
    a_p = _to_number(critic_proposed_answer)
    a_c = _to_number(critic_independent_answer)
    if a_p is None or a_c is None:
        return 0
    return 0 if answers_match(a_p, a_c, tol) else 1


def _is_placeholder_error_desc(text) -> bool:
    """Check whether an error-description value is empty or a placeholder.

    Args:
        text: The raw critic_error_desc cell value.

    Returns:
        True if the value is missing, or a placeholder such as "none"/"n/a"
        that the critique model writes when there is no error to report.
    """
    if text is None or (isinstance(text, float) and math.isnan(text)):
        return True
    return str(text).strip().lower() in ("", "none", "n/a", "na")


def error_desc_length(critic_error_desc) -> int:
    """Compute the word count of the critic's error description.

    Args:
        critic_error_desc: The critic's stated error description.

    Returns:
        The word count, or 0 if the value is missing or a placeholder.
    """
    if _is_placeholder_error_desc(critic_error_desc):
        return 0
    return len(str(critic_error_desc).split())


def hedging_count(critique_text) -> int:
    """Count hedging-language occurrences in the critique text.

    Args:
        critique_text: The full critique text to scan.

    Returns:
        The number of hedging-term matches, or 0 if the text is missing.
    """
    if critique_text is None or (isinstance(critique_text, float) and math.isnan(critique_text)):
        return 0
    return len(_HEDGING_RE.findall(str(critique_text)))


def critique_length(critique_text) -> int:
    """Compute the word count of the full critique text.

    Distinct from `critique_tokens`, the model-generated token count
    supplied upstream by the generation pipeline.

    Args:
        critique_text: The full critique text.

    Returns:
        The word count, or 0 if the text is missing.
    """
    if critique_text is None or (isinstance(critique_text, float) and math.isnan(critique_text)):
        return 0
    return len(str(critique_text).split())


def critic_disagrees(critic_verdict) -> int:
    """Flag whether the critic's verdict was INCORRECT.

    Constant on the disagreement population by construction, so this column
    is characterization-only there.

    Args:
        critic_verdict: The critic's stated verdict.

    Returns:
        1 if the verdict is "INCORRECT" (case-insensitive), else 0.
    """
    if critic_verdict is None:
        return 0
    return 1 if str(critic_verdict).strip().upper() == "INCORRECT" else 0


def explicit_error_flag(critic_error_desc) -> int:
    """Flag whether the critique names an actual error.

    Also constant on the disagreement population by construction.

    Args:
        critic_error_desc: The critic's stated error description.

    Returns:
        1 if an error description is present and not a placeholder, else 0.
    """
    return 0 if _is_placeholder_error_desc(critic_error_desc) else 1


# --------------------------------------------------------------------------- #
# Feature families (for metadata vs. structured ablations)
# --------------------------------------------------------------------------- #

_METADATA_FEATURES = {"error_desc_length", "critique_tokens"}
_STRUCTURED_FEATURES = {
    "answer_distance",
    "answer_distance_norm",
    "answer_distance_log1p",
    "answer_distance_signed",
    "answer_distance_signed_log1p",
    "hedging_count",
    "proposed_answer_differs",
    "critic_answer_differs_from_own_solve",
}
_METADATA_EXTRA = {"solver_tokens", "critic_independent_tokens"}


def assign_family(feature_name: str) -> str:
    """Classify a feature name into its ablation family.

    Args:
        feature_name: The feature column name to classify.

    Returns:
        "metadata", "structured", or "other". Direction one-hot columns are
        classified as structured.
    """
    if feature_name in _METADATA_FEATURES or feature_name in _METADATA_EXTRA:
        return "metadata"
    if feature_name in _STRUCTURED_FEATURES or feature_name.startswith("direction"):
        return "structured"
    return "other"


def feature_families(feature_names: Iterable[str]) -> Dict[str, List[str]]:
    """Group a list of feature names by ablation family.

    Args:
        feature_names: Feature column names to group.

    Returns:
        A dict with keys "metadata", "structured", and "other", each mapping
        to the list of feature names in that family.
    """
    out: Dict[str, List[str]] = {"metadata": [], "structured": [], "other": []}
    for name in feature_names:
        out[assign_family(name)].append(name)
    return out


_COMPUTED_FEATURES = [
    "answer_distance",
    "answer_distance_norm",
    "answer_distance_log1p",
    "answer_distance_signed",
    "answer_distance_signed_log1p",
    "proposed_answer_differs",
    "critic_answer_differs_from_own_solve",
    "error_desc_length",
    "hedging_count",
]
_CHARACTERIZATION_COLUMNS = ["critic_disagrees", "explicit_error_flag", "critique_length"]

# CLASSIFIER_DEFAULT_FEATURES is what feature_columns() hands to the model by
# default. CHARACTERIZATION_ONLY_FEATURES are computed and kept in the
# dataset for inspection/reporting but excluded from the model by default —
# each is either redundant with a classifier-default feature or too close to
# constant on the disagreement population (see the corresponding function's
# docstring). Pass force_include=[...] to feature_columns() to opt one back
# in explicitly.
CLASSIFIER_DEFAULT_FEATURES = [
    "answer_distance_log1p",
    "answer_distance_norm",
    "answer_distance_signed_log1p",
    "hedging_count",
    "error_desc_length",
]
CHARACTERIZATION_ONLY_FEATURES = [
    "answer_distance",
    "answer_distance_signed",
    "proposed_answer_differs",
    "critic_answer_differs_from_own_solve",
    "critic_disagrees",
    "explicit_error_flag",
    "critique_length",
]


def feature_columns(
    direction_dummies: Optional[Sequence[str]] = None,
    *,
    force_include: Optional[Sequence[str]] = None,
) -> List[str]:
    """Build the candidate feature list passed to the classifier by default.

    This is a candidate list, not a final one — always run it through
    `variance_check()` before training. `force_include` makes a
    normally-excluded characterization column eligible for consideration; it
    does not bypass the variance check.

    Args:
        direction_dummies: Resolved direction one-hot column names to
            append, typically from `direction_dummy_columns()`.
        force_include: Characterization-only column names to add to the
            candidate list explicitly.

    Returns:
        The candidate feature column names.
    """
    cols = list(CLASSIFIER_DEFAULT_FEATURES)
    if force_include:
        for name in force_include:
            if name not in cols:
                cols.append(name)
    if direction_dummies:
        cols.extend(direction_dummies)
    return cols


# --------------------------------------------------------------------------- #
# Critique-text recovery
# --------------------------------------------------------------------------- #
#
# dataset.csv (the upstream join output) carries only the parsed critique
# fields (critic_verdict, critic_error_desc, critic_proposed_answer) — the
# full raw critique text isn't in it. That text still exists one level up,
# in the pipeline's raw interaction records, so these functions recover it
# and join it onto a dataset.csv-shaped frame as `critique_raw`, which
# build_features() then uses for hedging_count and critique_length.


def load_critique_raw_map(pipeline_outputs_path: str) -> Dict[str, str]:
    """Build an interaction_id -> raw critique text lookup from pipeline records.

    Accepts two input shapes:
      - pipeline_outputs.jsonl: one JSON record per line.
      - checkpoint.json: a single JSON object with a top-level "states" dict
        mapping interaction_id -> record (the pipeline runner's resume cache).
    Both shapes hold the same per-interaction record structure; only the
    container differs. Detected by attempting to parse the whole file as one
    JSON document first (checkpoint.json), falling back to line-delimited
    parsing if that fails (pipeline_outputs.jsonl) — both shapes start with
    "{", so the format can't be told from the first character alone.

    Args:
        pipeline_outputs_path: Path to pipeline_outputs.jsonl or
            checkpoint.json.

    Returns:
        A dict mapping interaction_id to the raw critique-stage completion
        text (stages.critique.raw_response).
    """
    mapping: Dict[str, str] = {}
    missing_stage = 0

    with open(pipeline_outputs_path, "r", encoding="utf-8") as f:
        raw_text = f.read()

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        data = None

    if isinstance(data, dict) and "states" in data:
        records = data["states"].values()
    elif isinstance(data, dict):
        raise ValueError(
            f"{pipeline_outputs_path} parsed as a single JSON object but has no "
            f"top-level 'states' key — unrecognized checkpoint shape."
        )
    else:
        # Not a single valid JSON document -> treat as pipeline_outputs.jsonl
        # (one JSON record per line).
        records = (json.loads(line) for line in raw_text.splitlines() if line.strip())

    for rec in records:
        interaction_id = rec.get("interaction_id")
        critique_stage = rec.get("stages", {}).get("critique")
        if not critique_stage:
            missing_stage += 1
            continue
        raw = critique_stage.get("raw_response")
        if interaction_id is not None and raw is not None:
            mapping[interaction_id] = raw

    if missing_stage:
        print(
            f"[features] NOTE: {missing_stage} records had no 'critique' stage "
            f"at all (critique never ran for them).",
            file=sys.stderr,
        )
    return mapping


def attach_critique_raw(
    df: pd.DataFrame,
    pipeline_outputs_path: str,
    *,
    direction_col: str = "direction",
    question_id_col: str = "question_id",
) -> pd.DataFrame:
    """Join recovered critique text onto a dataset.csv-shaped frame.

    Join key: interaction_id in the pipeline records equals
    f"{direction}::{question_id}" in the dataset. Prints a join-quality
    summary and flags any row that has a critic_verdict but no critique_raw,
    which would indicate a real join miss rather than a stage that simply
    never ran.

    Args:
        df: A dataset.csv-shaped frame with direction_col and
            question_id_col present.
        pipeline_outputs_path: Path to pipeline_outputs.jsonl or
            checkpoint.json.
        direction_col: Column holding the solver/critic direction label.
        question_id_col: Column holding the question identifier.

    Returns:
        A copy of df with a new `critique_raw` column added.
    """
    out = df.copy()
    critique_map = load_critique_raw_map(pipeline_outputs_path)

    keys = out[direction_col].astype(str) + "::" + out[question_id_col].astype(str)
    dup = int(keys.duplicated().sum())
    if dup:
        print(
            f"[features] WARNING: {dup} duplicate join keys — join may not be "
            f"1:1 on this data. Verify before trusting the result.",
            file=sys.stderr,
        )

    out["critique_raw"] = keys.map(critique_map)

    n_total = len(out)
    n_filled = int(out["critique_raw"].notna().sum())
    n_missing = n_total - n_filled
    print(f"[features] Joined critique_raw for {n_filled}/{n_total} rows ({n_missing} unmatched).")

    if n_missing and "critic_verdict" in out.columns:
        missing_with_verdict = int((out["critique_raw"].isna() & out["critic_verdict"].notna()).sum())
        if missing_with_verdict:
            print(
                f"[features] WARNING: {missing_with_verdict} rows have a critic_verdict "
                f"but no critique_raw — that combination shouldn't happen and suggests "
                f"a real join miss, not a missing stage. Inspect before proceeding.",
                file=sys.stderr,
            )

    return out


# --------------------------------------------------------------------------- #
# Frame builder
# --------------------------------------------------------------------------- #


def build_features(
    df: pd.DataFrame,
    *,
    solver_answer_col: str = "solver_answer",
    critic_independent_answer_col: str = "critic_independent_answer",
    critic_proposed_answer_col: str = "critic_proposed_answer",
    error_desc_col: str = "critic_error_desc",
    verdict_col: str = "critic_verdict",
    direction_col: str = "direction",
    critique_text_col: str = "critique_raw",
    tol: float = 1e-6,
) -> pd.DataFrame:
    """Add all feature and characterization columns to a copy of the dataset.

    Non-destructive: no columns are dropped, so `variance_check()` can later
    report which columns to exclude from the model while keeping everything
    available in the returned dataset.

    Args:
        df: The input dataset.
        solver_answer_col: Column holding the solver's final answer.
        critic_independent_answer_col: Column holding the critic's
            independent (blind) answer.
        critic_proposed_answer_col: Column holding the critic's proposed
            answer from the critique stage.
        error_desc_col: Column holding the critic's error description.
        verdict_col: Column holding the critic's verdict.
        direction_col: Column holding the solver/critic direction label,
            one-hot encoded into `direction_*` columns.
        critique_text_col: Column holding the full raw critique text, used
            for hedging_count/critique_length. Falls back to error_desc_col
            with a warning if absent.
        tol: Absolute tolerance used for numeric answer comparisons.

    Returns:
        A copy of `df` with all feature and characterization columns added.
    """
    out = df.copy()

    # Normalize placeholder error-description text ("none"/"n/a"/"", any
    # casing) to real NaN, so anything built directly off critic_error_desc
    # elsewhere inherits the fix too, not just the features computed below.
    if error_desc_col in out:
        out[error_desc_col] = out[error_desc_col].where(
            ~out[error_desc_col].apply(_is_placeholder_error_desc)
        )

    a_s = out[solver_answer_col] if solver_answer_col in out else pd.Series([None] * len(out))
    a_c = (
        out[critic_independent_answer_col]
        if critic_independent_answer_col in out
        else pd.Series([None] * len(out))
    )
    a_p = (
        out[critic_proposed_answer_col]
        if critic_proposed_answer_col in out
        else pd.Series([None] * len(out))
    )
    err = out[error_desc_col] if error_desc_col in out else pd.Series([None] * len(out))
    verdict = out[verdict_col] if verdict_col in out else pd.Series([None] * len(out))

    # Resolve the critique-text source, falling back to the (much shorter)
    # error description if the raw critique text isn't available.
    if critique_text_col in out:
        critique_text = out[critique_text_col]
    elif error_desc_col in out:
        warnings.warn(
            f"build_features: '{critique_text_col}' not found; falling back to "
            f"'{error_desc_col}' for hedging_count/critique_length. Persist the raw "
            f"critique text for meaningful hedging counts.",
            stacklevel=2,
        )
        critique_text = err
    else:
        critique_text = pd.Series([None] * len(out))

    # Answer-distance family.
    out["answer_distance"] = [answer_distance(s, c) for s, c in zip(a_s, a_c)]
    out["answer_distance_norm"] = [answer_distance_norm(s, c) for s, c in zip(a_s, a_c)]
    out["answer_distance_log1p"] = [answer_distance_log1p(s, c) for s, c in zip(a_s, a_c)]
    out["answer_distance_signed"] = [answer_distance_signed(s, c) for s, c in zip(a_s, a_c)]
    out["answer_distance_signed_log1p"] = [
        answer_distance_signed_log1p(s, c) for s, c in zip(a_s, a_c)
    ]

    # Structured / metadata scalar features.
    out["proposed_answer_differs"] = [proposed_answer_differs(p, s, tol) for p, s in zip(a_p, a_s)]
    out["critic_answer_differs_from_own_solve"] = [
        critic_answer_differs_from_own_solve(p, c, tol) for p, c in zip(a_p, a_c)
    ]
    out["error_desc_length"] = [error_desc_length(e) for e in err]
    out["hedging_count"] = [hedging_count(t) for t in critique_text]

    # Characterization columns (kept in the dataset; often near-constant on
    # the disagreement population).
    out["critic_disagrees"] = [critic_disagrees(v) for v in verdict]
    out["explicit_error_flag"] = [explicit_error_flag(e) for e in err]
    out["critique_length"] = [critique_length(t) for t in critique_text]

    # Direction one-hot encoding. Category labels come from the data.
    if direction_col in out:
        dummies = pd.get_dummies(out[direction_col], prefix="direction")
        for col in dummies.columns:
            out[col] = dummies[col].astype(int)

    return out


def direction_dummy_columns(df: pd.DataFrame, direction_col: str = "direction") -> List[str]:
    """List the one-hot direction column names present in a built frame.

    Args:
        df: A dataset that has already been through `build_features()`.
        direction_col: Unused; kept for interface symmetry with
            `build_features()`. Column names are discovered by prefix.

    Returns:
        The names of all columns prefixed with "direction_".
    """
    return [c for c in df.columns if c.startswith("direction_")]


# --------------------------------------------------------------------------- #
# Feature-selection boundaries: no label leakage, no post-decision features
# --------------------------------------------------------------------------- #

# Fields derived from the gold answer; any feature built from these leaks
# the label.
GOLD_DERIVED_FIELDS = frozenset(
    {
        "gold_answer",
        "solver_correct",
        "critic_independent_correct",
        "revised_correct",
        "beneficial",
        "transition",
        "label",
    }
)
_LEAKAGE_SUBSTRINGS = ("gold", "_correct", "beneficial", "transition")

# Fields produced at or after the revision decision, so unavailable at
# prediction time.
POST_DECISION_FIELDS = frozenset(
    {
        "revision_tokens",
        "latency_s",
        "revised_answer",
        "revised_correct",
        "revise_decision",
        "revision_reasoning",
        "changed_answer",
        "transition",
        "beneficial",
    }
)
_POST_DECISION_SUBSTRINGS = ("revision", "revised", "revise", "latency")


def scan_label_leakage(feature_names: Iterable[str]) -> List[str]:
    """Find feature names that derive from, or name, a gold-derived field.

    Args:
        feature_names: Candidate feature column names to check.

    Returns:
        The subset of names that would leak the label.
    """
    flagged = []
    for name in feature_names:
        low = name.lower()
        if name in GOLD_DERIVED_FIELDS or any(sub in low for sub in _LEAKAGE_SUBSTRINGS):
            flagged.append(name)
    return flagged


def scan_post_decision(feature_names: Iterable[str]) -> List[str]:
    """Find feature names that are only available after the revision decision.

    Args:
        feature_names: Candidate feature column names to check.

    Returns:
        The subset of names that are post-decision fields.
    """
    flagged = []
    for name in feature_names:
        low = name.lower()
        if name in POST_DECISION_FIELDS or any(sub in low for sub in _POST_DECISION_SUBSTRINGS):
            flagged.append(name)
    return flagged


def audit_features(feature_names: Iterable[str]) -> Dict[str, object]:
    """Audit a proposed feature set against both selection boundaries.

    Args:
        feature_names: Candidate feature column names to audit.

    Returns:
        A dict with keys "ok" (bool, True only if both lists below are
        empty), "leakage" (label-leaking column names), and
        "post_decision" (post-decision column names).
    """
    names = list(feature_names)
    leakage = scan_label_leakage(names)
    post = scan_post_decision(names)
    return {"ok": not leakage and not post, "leakage": leakage, "post_decision": post}


def assert_features_clean(feature_names: Iterable[str]) -> None:
    """Raise if a feature set violates either selection boundary.

    Args:
        feature_names: Candidate feature column names to validate.

    Raises:
        AssertionError: If the feature set contains a label-leaking or
            post-decision column.
    """
    report = audit_features(feature_names)
    if not report["ok"]:
        raise AssertionError(
            "Feature boundary violation — "
            f"label leakage: {report['leakage']}; "
            f"post-decision: {report['post_decision']}"
        )


# --------------------------------------------------------------------------- #
# Variance check on the disagreement-only predictor population
# --------------------------------------------------------------------------- #

# Minority-value fraction below which a feature is treated as near-constant
# and dropped from the model (never from the dataset). Pass
# near_constant_frac= to variance_check() to override.
DEFAULT_NEAR_CONSTANT_FRAC = 0.05


def disagreement_population_mask(
    df: pd.DataFrame,
    *,
    revision_called_col: str = "revision_called",
    valid_col: str = "valid",
) -> pd.Series:
    """Build a boolean mask for the disagreement-only predictor population.

    Args:
        df: The dataset to mask.
        revision_called_col: Column indicating whether a revision was
            generated for the row.
        valid_col: Column indicating whether the row parsed successfully.

    Returns:
        A boolean Series, True for valid interactions where the critic
        disagreed and a revision was generated (revision_called == 1,
        valid == 1).
    """
    rc = df[revision_called_col].astype(float) == 1 if revision_called_col in df else pd.Series(False, index=df.index)
    vd = df[valid_col].astype(float) == 1 if valid_col in df else pd.Series(False, index=df.index)
    return rc & vd


def _minority_fraction(series: pd.Series) -> float:
    """Compute the fraction of non-null values not equal to the modal value.

    Args:
        series: The column to evaluate.

    Returns:
        1 - (count of the most common value / total non-null count), or 0.0
        if the series has no non-null values. A constant column returns 0.0.
    """
    s = series.dropna()
    if len(s) == 0:
        return 0.0
    counts = s.value_counts()
    modal = counts.iloc[0]
    return 1.0 - (modal / len(s))


def variance_check(
    df: pd.DataFrame,
    feature_cols: Sequence[str],
    population_mask: Optional[pd.Series] = None,
    *,
    near_constant_frac: float = DEFAULT_NEAR_CONSTANT_FRAC,
) -> Dict[str, object]:
    """Determine which candidate features are stable enough to model on.

    Non-destructive: returns lists and per-feature stats without modifying
    `df`. The caller keeps all columns in the dataset and passes only
    `kept` to the model.

    Args:
        df: The dataset to evaluate.
        feature_cols: Candidate feature column names to check.
        population_mask: Boolean mask selecting the evaluation population.
            Defaults to `disagreement_population_mask(df)`.
        near_constant_frac: Minority-value fraction below which a feature is
            treated as near-constant.

    Returns:
        A dict with keys "near_constant_frac", "n_population", "kept"
        (list of retained feature names), "dropped" (list of excluded
        feature names), and "details" (per-feature stats). A feature is
        dropped if it is constant (<=1 unique non-null value) or
        near-constant (minority fraction below `near_constant_frac`).
    """
    if population_mask is None:
        population_mask = disagreement_population_mask(df)
    sub = df.loc[population_mask]

    details: Dict[str, dict] = {}
    kept: List[str] = []
    dropped: List[str] = []
    for col in feature_cols:
        if col not in sub:
            details[col] = {"present": False, "kept": False, "reason": "absent"}
            dropped.append(col)
            continue
        series = sub[col]
        nunique = int(series.nunique(dropna=True))
        minority = _minority_fraction(series)
        if nunique <= 1:
            keep, reason = False, "constant"
        elif minority < near_constant_frac:
            keep, reason = False, f"near_constant(minority={minority:.4f}<{near_constant_frac})"
        else:
            keep, reason = True, "ok"
        details[col] = {
            "present": True,
            "nunique": nunique,
            "minority_fraction": round(minority, 4),
            "kept": keep,
            "reason": reason,
        }
        (kept if keep else dropped).append(col)

    return {
        "near_constant_frac": near_constant_frac,
        "n_population": int(population_mask.sum()),
        "kept": kept,
        "dropped": dropped,
        "details": details,
    }


def format_variance_report(report: Dict[str, object]) -> str:
    """Render a `variance_check()` result as a readable table.

    Args:
        report: The dict returned by `variance_check()`.

    Returns:
        A formatted multi-line string summarizing the kept/dropped decision
        for each candidate feature.
    """
    lines = [
        f"Variance check on disagreement population "
        f"(n={report['n_population']}, near_constant_frac={report['near_constant_frac']})",
        f"{'feature':<26}{'nuniq':>7}{'minority':>10}  {'decision':<8} reason",
        "-" * 72,
    ]
    for col, d in report["details"].items():
        if not d.get("present", False):
            lines.append(f"{col:<26}{'-':>7}{'-':>10}  {'DROP':<8} absent")
            continue
        decision = "keep" if d["kept"] else "DROP"
        lines.append(
            f"{col:<26}{d['nunique']:>7}{d['minority_fraction']:>10.4f}  "
            f"{decision:<8} {d['reason']}"
        )
    lines.append("-" * 72)
    lines.append(f"kept:    {report['kept']}")
    lines.append(f"dropped: {report['dropped']}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Command-line interface
# --------------------------------------------------------------------------- #


def _cli() -> None:
    """Command-line entry point: add feature columns to a dataset CSV.

    Reads a dataset CSV, runs it through `build_features()`, audits the
    default candidate feature set against the selection boundaries, runs
    the variance check, and writes the augmented dataset back out.
    """
    import argparse

    ap = argparse.ArgumentParser(
        description="Add feature columns to a dataset CSV."
    )
    ap.add_argument("--input", required=True, help="Path to input dataset CSV")
    ap.add_argument("--output", required=True, help="Path to write the feature-augmented CSV")
    ap.add_argument(
        "--checkpoint",
        default=None,
        help="Optional path to pipeline_outputs.jsonl or checkpoint.json — if given, "
        "critique_raw is recovered and joined onto --input before features are built.",
    )
    ap.add_argument(
        "--critique-text-col",
        default="critique_raw",
        help="Column holding raw critique text (default: critique_raw). "
        "Falls back to critic_error_desc with a logged warning if absent.",
    )
    ap.add_argument(
        "--near-constant-frac",
        type=float,
        default=DEFAULT_NEAR_CONSTANT_FRAC,
        help=f"Variance-check threshold (default: {DEFAULT_NEAR_CONSTANT_FRAC}).",
    )
    args = ap.parse_args()

    df = pd.read_csv(args.input)
    print(f"[features] Loaded {args.input}: {df.shape[0]} rows, {df.shape[1]} cols")

    if args.checkpoint:
        df = attach_critique_raw(df, args.checkpoint)

    out = build_features(df, critique_text_col=args.critique_text_col)

    dummies = direction_dummy_columns(out)
    candidate_cols = feature_columns(direction_dummies=dummies)
    audit = audit_features(candidate_cols)
    if not audit["ok"]:
        raise AssertionError(
            "Feature boundary violation on the default candidate set — "
            f"leakage: {audit['leakage']}; post_decision: {audit['post_decision']}"
        )

    mask = disagreement_population_mask(out)
    report = variance_check(out, candidate_cols, mask, near_constant_frac=args.near_constant_frac)
    print(format_variance_report(report))

    out.to_csv(args.output, index=False)
    print(f"[features] Wrote {args.output}: {out.shape[0]} rows, {out.shape[1]} cols")
    print(
        f"[features] Classifier-default candidates: {candidate_cols}\n"
        f"[features] Characterization-only (in CSV, excluded by default): "
        f"{CHARACTERIZATION_ONLY_FEATURES}"
    )


if __name__ == "__main__":
    _cli()
