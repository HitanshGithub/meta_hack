from __future__ import annotations

import json
from pathlib import Path

from ..models import Action, Observation
from ..reward import compute_reward

_FIXTURE_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "pr_medium.json"

with _FIXTURE_PATH.open("r", encoding="utf-8") as f:
    FIXTURE: dict[str, object] = json.load(f)

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
        max_steps=6,
        task_name="medium",
    )


def grade(action: Action) -> float:
    return compute_reward(observation=_observation(), action=action, gold=GOLD)
