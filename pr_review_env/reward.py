from __future__ import annotations

import re
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
    if action.decision == gold_decision:
        return 1.0
    
    # Partial credit: approve vs request_changes are closer than either vs close
    if action.decision == "close" or gold_decision == "close":
        return 0.0  # Close is a completely different category
    
    # approve vs request_changes - partial credit for being in the same review category
    return 0.3


def _label_score(action: Action, gold: dict[str, Any]) -> float:
    pred = set(action.labels)
    expected = {str(label) for label in gold.get("labels", [])}
    if not pred and not expected:
        return 1.0

    true_positive = len(pred & expected)
    precision = true_positive / len(pred) if pred else 0.0
    recall = true_positive / len(expected) if expected else 0.0

    if precision + recall == 0:
        return 0.0
    f1 = (2 * precision * recall) / (precision + recall)
    
    # Bonus for getting critical labels right (security, breaking-change)
    critical_labels = {"security", "breaking-change"}
    pred_critical = pred & critical_labels
    expected_critical = expected & critical_labels
    
    if expected_critical:
        critical_precision = len(pred_critical & expected_critical) / len(pred_critical) if pred_critical else 0.0
        critical_recall = len(pred_critical & expected_critical) / len(expected_critical)
        critical_f1 = (2 * critical_precision * critical_recall) / (critical_precision + critical_recall) if (critical_precision + critical_recall) > 0 else 0.0
        # Weight critical labels more heavily
        f1 = 0.7 * f1 + 0.3 * critical_f1
    
    return f1


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
    
    # Length penalties
    if len(summary) < 20:
        return 0.0  # Too short to be meaningful
    if len(summary) > 500:
        return 0.3  # Too long, but some credit
    
    # Ideal length bonus
    length_score = 1.0
    if 50 <= len(summary) <= 200:
        length_score = 1.0  # Ideal length
    elif 20 <= len(summary) < 50 or 200 < len(summary) <= 300:
        length_score = 0.9  # Good length
    elif 300 < len(summary) <= 500:
        length_score = 0.8  # Acceptable but verbose
    
    keywords = [str(k).lower() for k in gold.get("gold_keywords", []) if str(k).strip()]
    if not keywords:
        return length_score

    lowered_summary = summary.lower()
    
    # Exact keyword matches
    exact_matches = sum(1 for term in keywords if term in lowered_summary)
    
    # Partial matches and semantic variants
    partial_matches = 0
    for term in keywords:
        # Check for word parts and common variations
        words = term.split()
        if len(words) > 1:
            # Multi-word terms - check if all parts are present
            present_words = sum(1 for word in words if word in lowered_summary)
            if present_words > 0:
                partial_matches += 0.8 * (present_words / len(words))
        else:
            # Single word - check for partial matches
            for word in lowered_summary.split():
                if term in word or word in term:
                    partial_matches += 0.8  # Full credit for single word partial
                    break
    
    # Normalize matches - partial matches get full weight
    keyword_score = min(1.0, (exact_matches + partial_matches) / len(keywords))
    
    # Quality indicators
    quality_bonus = 0.0
    if any(phrase in lowered_summary for phrase in ["please", "recommend", "suggest", "should", "consider"]):
        quality_bonus += 0.1  # Polite/constructive language
    if any(phrase in lowered_summary for phrase in ["test", "verify", "validate", "regression"]):
        quality_bonus += 0.1  # Mentions testing
    
    return min(1.0, length_score * 0.4 + keyword_score * 0.5 + quality_bonus)


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
