"""Pytest configuration"""

import pytest
import sys
from pathlib import Path

# Add the project root to Python path for imports
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

@pytest.fixture
def sample_action():
    """Sample valid action for testing"""
    from pr_review_env.models import Action
    return Action(
        decision="approve",
        labels=["bug"],
        priority="low",
        review_summary="LGTM - looks good to me."
    )

@pytest.fixture
def sample_observation():
    """Sample valid observation for testing"""
    from pr_review_env.models import Observation
    return Observation(
        pr_id=123,
        title="Test PR",
        description="Test description",
        diff="+ print('hello')",
        comments=["alice: LGTM"],
        files_changed=["test.py"],
        author="test_user",
        base_branch="main",
        additions=5,
        deletions=2,
        current_step=1,
        max_steps=4,
        task_name="easy"
    )
