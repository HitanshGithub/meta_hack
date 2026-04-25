from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..models import Action, Observation
from ..reward import compute_reward

_FIXTURE_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "pr_hard.json"

with _FIXTURE_PATH.open("r", encoding="utf-8") as f:
    _RAW_FIXTURE = json.load(f)

if isinstance(_RAW_FIXTURE, list):
    FIXTURES: list[dict[str, object]] = [dict(item) for item in _RAW_FIXTURE]
else:
    FIXTURES = [dict(_RAW_FIXTURE)]

if not FIXTURES:
    raise ValueError("pr_hard.json must contain at least one fixture")

# Alias for backward compatibility with env.py imports
ALL_FIXTURES = FIXTURES

FIXTURE: dict[str, object] = FIXTURES[0]
GOLD: dict[str, object] = dict(FIXTURE["gold"])


def _observation_for(fixture: dict[str, Any], task_name: str = "hard") -> Observation:
    return Observation(
        pr_id=int(fixture["pr_id"]),
        title=str(fixture["title"]),
        description=str(fixture["description"]),
        diff=str(fixture["diff"]),
        comments=[str(c) for c in fixture["comments"]],
        files_changed=[str(p) for p in fixture["files_changed"]],
        author=str(fixture["author"]),
        base_branch=str(fixture["base_branch"]),
        additions=int(fixture["additions"]),
        deletions=int(fixture["deletions"]),
        current_step=1,
        max_steps=8,
        task_name=task_name,
    )


def _observation() -> Observation:
    return _observation_for(FIXTURE, "hard")


def grade(action: Action) -> float:
    return compute_reward(observation=_observation(), action=action, gold=GOLD)
