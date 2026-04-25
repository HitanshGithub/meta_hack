from __future__ import annotations

import json
from pathlib import Path

from ..models import Action, Observation
from ..reward import compute_reward

_FIXTURE_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "pr_easy.json"

with _FIXTURE_PATH.open("r", encoding="utf-8") as f:
    _RAW_FIXTURE = json.load(f)

if isinstance(_RAW_FIXTURE, list):
    FIXTURES: list[dict[str, object]] = [dict(item) for item in _RAW_FIXTURE]
else:
    FIXTURES = [dict(_RAW_FIXTURE)]

if not FIXTURES:
    raise ValueError("pr_easy.json must contain at least one fixture")

FIXTURE: dict[str, object] = FIXTURES[0]
GOLD: dict[str, object] = dict(FIXTURE["gold"])


def _observation() -> Observation:
    return Observation(
        pr_id=int(FIXTURE["pr_id"]),
        title=str(FIXTURE["title"]),
        description=str(FIXTURE["description"]),
        diff=str(FIXTURE["diff"]),
        comments=[str(c) for c in FIXTURE["comments"]],
        files_changed=[str(p) for p in FIXTURE["files_changed"]],
        author=str(FIXTURE["author"]),
        base_branch=str(FIXTURE["base_branch"]),
        additions=int(FIXTURE["additions"]),
        deletions=int(FIXTURE["deletions"]),
        current_step=1,
        max_steps=4,
        task_name="easy",
    )


def grade(action: Action) -> float:
    return compute_reward(observation=_observation(), action=action, gold=GOLD)
