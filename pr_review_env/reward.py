from __future__ import annotations

import math
from typing import Any

from .models import Action, Observation, Reward

_PRIORITY_ORDER: dict[str, int] = {
    "low": 0,
    "medium": 1,
    "high": 2,
    "critical": 3,
}

# All scores are clamped to [0.01, 0.99] — strictly between 0 and 1
# as required by the OpenEnv validator.
_MIN_SCORE = 0.01
_MAX_SCORE = 0.99
_LATENCY_DISCOUNT_FLOOR = 0.1
_LATENCY_DECAY_ALPHA = 0.35


def _build_task_evidence() -> dict[str, dict[str, list[str]]]:
    """Build evidence terms for all tasks from fixture gold_keywords and files_changed."""
    import json
    from pathlib import Path

    fixtures_dir = Path(__file__).resolve().parents[1] / "fixtures"
    evidence: dict[str, dict[str, list[str]]] = {}

    for difficulty in ["easy", "medium", "hard"]:
        fixture_path = fixtures_dir / f"pr_{difficulty}.json"
        if not fixture_path.exists():
            continue

        with fixture_path.open("r", encoding="utf-8") as f:
            fixtures = json.load(f)

        for i, fixture in enumerate(fixtures):
            pr_id = fixture["pr_id"]
            task_id = difficulty if i == 0 else f"{difficulty}_{pr_id}"

            keywords = [str(k).strip().lower() for k in fixture.get("gold", {}).get("gold_keywords", []) if str(k).strip()]
            files = [str(fp).split("/")[-1].lower() for fp in fixture.get("files_changed", [])]

            evidence[task_id] = {
                "issue_terms": keywords,
                "impact_terms": keywords,
                "remediation_terms": keywords,
                "file_terms": files,
            }

    return evidence


_TASK_EVIDENCE: dict[str, dict[str, list[str]]] = _build_task_evidence()


def _clamp(value: float) -> float:
    """Clamp a score to be strictly between 0 and 1."""
    return max(_MIN_SCORE, min(_MAX_SCORE, value))


def compute_latency_discount(latency_seconds: float, budget_seconds: float) -> float:
    """
    Compute a smooth latency discount in (0, 1].

    We intentionally use an exponential tail after the budget:
    discount = exp(-alpha * max(0, latency - budget)).
    This is easy to interpret, deterministic, and gives smooth penalties.
    The result is floored to keep slow-but-correct agents non-zero.
    """
    safe_latency = max(0.0, float(latency_seconds))
    safe_budget = max(1e-6, float(budget_seconds))
    over_budget = max(0.0, safe_latency - safe_budget)
    if over_budget <= 0.0:
        return 1.0
    discount = math.exp(-_LATENCY_DECAY_ALPHA * over_budget)
    return max(_LATENCY_DISCOUNT_FLOOR, min(1.0, discount))


def compute_latency_adjusted_score(raw_score: float, latency_discount: float) -> float:
    """Multiply raw reward by latency discount with strict score clamping."""
    return _clamp(float(raw_score) * max(0.0, min(1.0, float(latency_discount))))


def _review_stage_weights(observation: Observation) -> tuple[float, float, float, float]:
    if observation.review_stage == "identify_risk":
        return (0.15, 0.15, 0.10, 0.60)
    if observation.review_stage == "assess_impact":
        return (0.20, 0.30, 0.30, 0.20)
    return (0.30, 0.25, 0.20, 0.25)


def _decision_score(action: Action, gold: dict[str, Any]) -> float:
    gold_decision = str(gold.get("decision", ""))
    raw = 0.9 if action.decision == gold_decision else 0.1
    return _clamp(raw)


def _label_score(action: Action, gold: dict[str, Any]) -> float:
    pred: set[str] = set(action.labels)
    expected: set[str] = {str(label) for label in gold.get("labels", [])}

    if not expected:
        # No labels expected — reward neutral score
        raw = 0.5 if not pred else 0.1
        return _clamp(raw)

    true_positive = len(pred & expected)
    precision = true_positive / len(pred) if pred else 0.0
    recall = true_positive / len(expected) if expected else 0.0

    if precision + recall == 0.0:
        return _clamp(0.05)

    f1 = (2.0 * precision * recall) / (precision + recall)
    # Map f1 from [0, 1] to [0.05, 0.95] to never hit exact 0 or 1
    raw = 0.05 + f1 * 0.9
    return _clamp(raw)


def _priority_score(action: Action, gold: dict[str, Any]) -> float:
    gold_priority = str(gold.get("priority", ""))
    if action.priority not in _PRIORITY_ORDER or gold_priority not in _PRIORITY_ORDER:
        return _clamp(0.05)

    distance = abs(_PRIORITY_ORDER[action.priority] - _PRIORITY_ORDER[gold_priority])
    if distance == 0:
        raw = 0.95
    elif distance == 1:
        raw = 0.6
    elif distance == 2:
        raw = 0.3
    else:
        raw = 0.05
    return _clamp(raw)


def _summary_score(action: Action, gold: dict[str, Any]) -> float:
    summary = action.review_summary.strip()
    # Hard length penalties (as specified).
    if len(summary) < 20 or len(summary) > 500:
        return _clamp(0.05)

    keywords = [str(k).strip().lower() for k in gold.get("gold_keywords", []) if str(k).strip()]
    if not keywords:
        return _clamp(0.3)

    lowered_summary = summary.lower()

    # Dense keyword credit: exact substring hits score 0.95; otherwise credit
    # is proportional to how many keyword tokens appear in the summary.
    term_scores: list[float] = []
    for keyword in keywords:
        if keyword in lowered_summary:
            term_scores.append(0.95)
            continue

        parts = [p for p in keyword.split() if p]
        if not parts:
            term_scores.append(0.05)
            continue

        matched = sum(1 for part in parts if part in lowered_summary)
        partial = 0.05 + (matched / len(parts)) * 0.9
        term_scores.append(partial)

    raw = sum(term_scores) / len(term_scores)
    return _clamp(raw)


def _evidence_score(observation: Observation, action: Action) -> float:
    summary = action.review_summary.strip().lower()
    task_terms = _TASK_EVIDENCE.get(observation.task_name, {})
    stage_key = {
        "identify_risk": "issue_terms",
        "assess_impact": "impact_terms",
        "final_triage": "remediation_terms",
    }.get(observation.review_stage, "issue_terms")

    stage_terms = task_terms.get(stage_key, [])
    file_terms = task_terms.get("file_terms", [])

    term_hits = sum(1 for term in stage_terms if term in summary)
    file_hits = sum(1 for term in file_terms if term in summary)

    stage_score = term_hits / len(stage_terms) if stage_terms else 0.0
    file_score = file_hits / len(file_terms) if file_terms else 0.0
    raw = 0.05 + min(0.9, stage_score * 0.7 + file_score * 0.2)

    if observation.review_stage == "final_triage" and len(summary.split()) < 8:
        raw -= 0.1

    return _clamp(raw)


def _consistency_penalty(action: Action, gold: dict[str, Any]) -> float:
    penalty = 0.0
    labels = set(action.labels)
    expected_labels = set(str(label) for label in gold.get("labels", []))

    severe_labels = {"security", "urgent", "breaking-change"}
    if action.decision == "approve" and labels & severe_labels:
        penalty += 0.2
    if action.priority == "low" and labels & {"security", "urgent"}:
        penalty += 0.12
    if action.decision == "close" and expected_labels:
        penalty += 0.15
    if len(labels - expected_labels) >= 3:
        penalty += 0.08

    return penalty


def compute_reward_breakdown(observation: Observation, action: Action, gold: dict[str, Any]) -> Reward:
    decision = _decision_score(action=action, gold=gold)
    labels = _label_score(action=action, gold=gold)
    priority = _priority_score(action=action, gold=gold)
    summary = _clamp((_summary_score(action=action, gold=gold) * 0.6) + (_evidence_score(observation, action) * 0.4))

    w_decision, w_labels, w_priority, w_summary = _review_stage_weights(observation)
    base = (
        decision * w_decision
        + labels * w_labels
        + priority * w_priority
        + summary * w_summary
    )
    base -= _consistency_penalty(action, gold)
    step_penalty = max(observation.current_step - 1, 0) * 0.02
    total = _clamp(base - step_penalty)

    return Reward(
        decision_score=decision,
        label_score=labels,
        priority_score=priority,
        summary_score=summary,
        step_penalty=step_penalty,
        total=total,
    )


def compute_reward(observation: Observation, action: Action, gold: dict[str, Any]) -> float:
    return compute_reward_breakdown(observation=observation, action=action, gold=gold).total
