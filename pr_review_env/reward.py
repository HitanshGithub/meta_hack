from __future__ import annotations

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


def _clamp(value: float) -> float:
    """Clamp a score to be strictly between 0 and 1."""
    return max(_MIN_SCORE, min(_MAX_SCORE, value))


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


def compute_reward_breakdown(observation: Observation, action: Action, gold: dict[str, Any]) -> Reward:
    decision = _decision_score(action=action, gold=gold)
    labels = _label_score(action=action, gold=gold)
    priority = _priority_score(action=action, gold=gold)
    summary = _summary_score(action=action, gold=gold)

    base = (decision + labels + priority + summary) / 4.0
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
