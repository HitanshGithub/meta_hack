from __future__ import annotations

from typing import Any

from .models import Action, Observation, Reward

_PRIORITY_ORDER: dict[str, int] = {
    "low": 0,
    "medium": 1,
    "high": 2,
    "critical": 3,
}


def _decision_score(action: Action, gold: dict[str, Any]) -> float:
    gold_decision = str(gold.get("decision", ""))
    return 1.0 if action.decision == gold_decision else 0.0


def _label_score(action: Action, gold: dict[str, Any]) -> float:
    pred: set[str] = set(action.labels)
    expected: set[str] = {str(label) for label in gold.get("labels", [])}
    if not pred and not expected:
        return 1.0

    true_positive = len(pred & expected)
    precision = true_positive / len(pred) if pred else 0.0
    recall = true_positive / len(expected) if expected else 0.0
    if precision + recall == 0.0:
        return 0.0
    return (2.0 * precision * recall) / (precision + recall)


def _priority_score(action: Action, gold: dict[str, Any]) -> float:
    gold_priority = str(gold.get("priority", ""))
    if action.priority not in _PRIORITY_ORDER or gold_priority not in _PRIORITY_ORDER:
        return 0.0

    distance = abs(_PRIORITY_ORDER[action.priority] - _PRIORITY_ORDER[gold_priority])
    if distance == 0:
        return 1.0
    if distance == 1:
        return 0.5
    if distance == 2:
        return 0.25
    return 0.0


def _summary_score(action: Action, gold: dict[str, Any]) -> float:
    summary = action.review_summary.strip()
    # Hard length penalties (as specified).
    if len(summary) < 20 or len(summary) > 500:
        return 0.0

    keywords = [str(k).strip().lower() for k in gold.get("gold_keywords", []) if str(k).strip()]
    if not keywords:
        return 0.0

    lowered_summary = summary.lower()

    # Dense keyword credit: exact substring hits score 1.0; otherwise credit
    # is proportional to how many keyword tokens appear in the summary.
    term_scores: list[float] = []
    for keyword in keywords:
        if keyword in lowered_summary:
            term_scores.append(1.0)
            continue

        parts = [p for p in keyword.split() if p]
        if not parts:
            term_scores.append(0.0)
            continue

        matched = sum(1 for part in parts if part in lowered_summary)
        term_scores.append(matched / len(parts))

    return sum(term_scores) / len(term_scores)


def compute_reward_breakdown(observation: Observation, action: Action, gold: dict[str, Any]) -> Reward:
    decision = _decision_score(action=action, gold=gold)
    labels = _label_score(action=action, gold=gold)
    priority = _priority_score(action=action, gold=gold)
    summary = _summary_score(action=action, gold=gold)

    base = (decision + labels + priority + summary) / 4.0
    step_penalty = max(observation.current_step - 1, 0) * 0.02
    total = max(0.0, min(1.0, base - step_penalty))

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
