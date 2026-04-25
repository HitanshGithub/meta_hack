# PR Review Environment - Full Project Documentation

## 1) Project Identity

This repository implements a deterministic pull-request review environment for training and evaluating agents.  
It is built around a Python domain package (`pr_review_env`) with a FastAPI wrapper (`server`) and optional training/inference tooling.

Primary goals:
- Simulate PR triage tasks with realistic code diffs and review comments.
- Score reviewer actions deterministically with interpretable reward components.
- Provide an HTTP interface compatible with OpenEnv-style workflows.
- Support baseline inference and GRPO-based fine-tuning workflows.

---

## 2) Repository Inventory

Top-level layout:

```text
Meta_3_1/
  pr_review_env/                # Core environment package
  server/                       # FastAPI application
  fixtures/                     # Task fixtures + gold annotations
  tests/                        # Unit tests
  colab/                        # Notebook training workflow
  README.md
  ARCHITECTURE.md
  DEPLOYMENT.md
  JUDGES_GUIDE.md
  VALIDATION_CHECKLIST.md
  SCORING_ANALYSIS.md
  COMPETITIVE_ANALYSIS.md
  HF_MINI_BLOG_DRAFT.md
  SUBMISSION_READY.md
  openenv.yaml
  inference.py
  train_grpo.py
  pyproject.toml
  requirements.txt
  requirements-train.txt
  Dockerfile
  conftest.py
  test_output_format.py
  .env.example
  .gitignore
  .dockerignore
  .gitattributes
  uv.lock
```

---

## 3) Architecture Overview

### 3.1 Core Components

1. **Environment Engine (`pr_review_env/env.py`)**
   - Owns episode state, task selection, staged workflow prompts, step transitions, and terminal conditions.

2. **Reward Engine (`pr_review_env/reward.py`)**
   - Computes reward breakdown (`decision`, `labels`, `priority`, `summary`, penalties) and final scalar reward.

3. **Schema Layer (`pr_review_env/models.py`)**
   - Defines strict Pydantic models used across engine and API.

4. **Task Providers (`pr_review_env/tasks/*.py`)**
   - Load fixture JSON data and expose task-specific `FIXTURE`, `GOLD`, and `grade()`.

5. **HTTP Interface (`server/app.py`)**
   - Exposes environment operations over REST (`/reset`, `/step`, `/state`, `/tasks`, `/validate`, etc.).

6. **Client Tooling**
   - `inference.py`: baseline rollout script using OpenAI-compatible APIs.
   - `train_grpo.py`: TRL/GRPO training script with reward callbacks from env validation.

### 3.2 Runtime Topology

- API process hosts a global in-memory session store: `SESSION_STORE: dict[str, PRReviewEnv]`.
- Each `session_id` corresponds to one `PRReviewEnv` instance.
- Task fixtures are static JSON files and loaded by task modules.
- No persistent DB layer is used.

---

## 4) Domain Models and Contracts

Defined in `pr_review_env/models.py`.

### 4.1 `Observation`

Fields:
- `pr_id`, `title`, `description`, `diff`, `comments`
- `files_changed`, `author`, `base_branch`
- `additions`, `deletions`
- `current_step`, `max_steps`, `task_name`
- `review_stage`, `stage_prompt`

Used as:
- Response from `/reset`
- Included in `StepResult` returned by `/step`

### 4.2 `Action`

Fields:
- `decision`: one of `approve | request_changes | close`
- `labels`: list of allowed labels (no duplicates)
- `priority`: one of `low | medium | high | critical`
- `review_summary`: non-empty string

Validation:
- Unknown labels rejected.
- Duplicate labels rejected.
- Empty/whitespace summary rejected.
- Extra fields forbidden.

### 4.3 `Reward`

Fields:
- `decision_score`
- `label_score`
- `priority_score`
- `summary_score`
- `step_penalty`
- `total`

All score fields constrained to `[0.0, 1.0]`.

### 4.4 `StepResult`

Fields:
- `observation: Observation`
- `reward: float`
- `done: bool`
- `info: dict`

---

## 5) Task System and Fixtures

### 5.1 Task Catalog

Configured in `pr_review_env/env.py` via `TASK_CONFIGS`:
- `easy`
- `medium`
- `hard`

Each task has:
- `id`, `description`, `difficulty`
- `fixture` (full PR artifact)
- `gold` (expected action target)
- `max_steps`
- `expected_score_range`

### 5.2 Fixture Structure

JSON files:
- `fixtures/pr_easy.json`
- `fixtures/pr_medium.json`
- `fixtures/pr_hard.json`

Top-level fields:
- `pr_id`, `title`, `description`, `diff`, `comments`
- `files_changed`, `author`, `base_branch`
- `additions`, `deletions`
- `gold`

`gold` fields:
- `decision`
- `labels`
- `priority`
- `gold_keywords`

### 5.3 Task Modules

Files:
- `pr_review_env/tasks/easy.py`
- `pr_review_env/tasks/medium.py`
- `pr_review_env/tasks/hard.py`

Each module:
- Loads a fixture JSON.
- Exposes `FIXTURE` and `GOLD`.
- Implements `grade(action)` via `compute_reward()`.

---

## 6) Environment Lifecycle

Implemented in `pr_review_env/env.py`.

### 6.1 Reset

`PRReviewEnv.reset(task_name)`
- Validates task key.
- Initializes:
  - `_task_name`
  - `_current_step = 1`
  - `_done = False`
  - `_last_reward = None`
  - `_history = []`
  - `_gold = selected_task.gold`
- Returns first `Observation`.

### 6.2 Review Stages

Stages are tied to step number:
- Step 1 -> `identify_risk`
- Step 2 -> `assess_impact`
- Step >=3 -> `final_triage`

Observation includes stage-aware prompt text (`stage_prompt`) to shape behavior.

### 6.3 Step

`PRReviewEnv.step(action)`
- Requires initialized task and non-terminal episode.
- Builds current observation.
- Computes reward via `compute_reward_breakdown(...)`.
- Terminal condition:
  - done if step reaches `max_steps`, OR
  - done early if `current_step >= min(3, max_steps)` and `reward >= 0.85`.
- Appends step record to `_history`.
- Increments step if not done.
- Returns `StepResult`.

### 6.4 State Inspection

`PRReviewEnv.get_state()` returns a dict with:
- task id
- current step
- max steps
- done flag
- last reward
- step history
- current observation (if initialized)

---

## 7) Reward System

Implemented in `pr_review_env/reward.py`.

## 7.1 Component Scores

1. **Decision score**
   - exact match with gold decision -> `0.9`
   - mismatch -> `0.1`

2. **Label score**
   - F1-based score from predicted vs gold labels.
   - mapped to bounded range `[0.05, 0.95]`.

3. **Priority score**
   - exact match -> `0.95`
   - distance 1 -> `0.6`
   - distance 2 -> `0.3`
   - distance 3 -> `0.05`

4. **Summary score**
   - combines:
     - keyword relevance to `gold_keywords`
     - evidence quality (references to diff, comments, files, patterns)
   - final summary score uses weighted blend: `0.6 * keyword + 0.4 * evidence`.

All components are clamped to avoid exact 0/1 extremes.

## 7.2 Stage-Dependent Weights

- `identify_risk`: `(decision=0.15, labels=0.15, priority=0.10, summary=0.60)`
- `assess_impact`: `(0.20, 0.30, 0.30, 0.20)`
- `final_triage`: `(0.30, 0.25, 0.20, 0.25)`

## 7.3 Penalties

1. **Consistency penalty**
   - Penalizes contradictory decisions/labels/priority combinations.
   - Examples:
     - `approve` with severe labels
     - `low` with `security`
     - `close` despite meaningful expected issue labels
     - broad severe-label spam on weak evidence

2. **Step penalty**
   - `0.02 * (current_step - 1)` (non-negative).

## 7.4 Final Reward

`total = clamp(weighted_component_sum - consistency_penalty - step_penalty)`

Returns `Reward` object with component breakdown and total.

---

## 8) API Reference

Implemented in `server/app.py`.

### 8.1 `POST /reset`

Request:
- body optional: `{"task": "easy|medium|hard"}`
- header optional: `session_id`

Behavior:
- Creates/reuses session environment.
- Resets selected task.
- Returns initial `Observation`.
- Adds generated `session_id` header when absent.

### 8.2 `POST /step`

Request:
- body: `Action`
- header: `session_id` (default fallback used if omitted)

Behavior:
- Runs one environment step and returns `StepResult`.

### 8.3 `GET /state`

Behavior:
- Returns state snapshot from current session env.

### 8.4 `GET /tasks`

Behavior:
- Returns metadata for all configured tasks and environment version info.

### 8.5 `GET /health`

Behavior:
- Returns status, active sessions count, available tasks, and timestamp.

### 8.6 `POST /validate`

Request:
- `{"task": "<task>", "action": <Action>}`

Behavior:
- Runs stateless one-step validation in a temporary env.
- Returns validity + reward breakdown.

### 8.7 `GET /examples`

Behavior:
- Returns predefined action examples by difficulty.

### 8.8 `GET /metrics`

Behavior:
- Returns aggregate session metrics and per-session stats.

---

## 9) Inference Pipeline (`inference.py`)

Purpose:
- Baseline benchmark script that calls env endpoints and an LLM API.

Flow:
1. Build prompts from observation.
2. Call chat-completions endpoint.
3. Parse/normalize model output into valid `Action`.
4. Send action to `/step`.
5. Log standardized trace for each task and per-step score.

Key env vars:
- `ENV_BASE_URL`
- `API_BASE_URL`
- `MODEL_NAME`
- `HF_TOKEN` or `OPENAI_API_KEY` / `API_KEY`
- `MAX_STEPS`

Output format:
- `[START]`, `[STEP]`, `[END]` line-oriented logs.

---

## 10) Training Pipeline (`train_grpo.py`)

Purpose:
- Run GRPO fine-tuning loop using environment-derived rewards.

Main pieces:
- `EnvClient`: talks to env API (`/reset`, `/step`, `/validate`).
- `build_training_dataset(...)`: creates prompt dataset from task episodes.
- `env_reward_fn(...)`: calls validator and returns scalar reward for GRPO.
- `evaluate_model(...)`: compares model behavior before/after training.
- `load_model(...)`: supports standard + optional Unsloth paths.

Outputs (in `output-dir`):
- model checkpoint(s)
- `reward_history.csv`
- optional `reward_components.csv`
- `training_summary.json`
- `before_after.md`
- `reward_curve.png`

Training deps:
- from `requirements-train.txt` (PyTorch, TRL, Transformers, PEFT, etc.)

---

## 11) Testing and Validation

### 11.1 Test Modules

- `tests/test_models.py`
  - schema validation, enum constraints, bounds, strictness.

- `tests/test_reward.py`
  - component scoring behavior, penalties, stage effects.

- `tests/test_env.py`
  - reset/step progression, done behavior, history integrity.

- `tests/test_tasks.py`
  - fixture/gold structure, task exports, grade range, realism checks.

### 11.2 Additional Validation Assets

- `VALIDATION_CHECKLIST.md`:
  - checklist for endpoints, inference output, and training artifacts.
- `test_output_format.py`:
  - manual format sanity for expected run output.

---

## 12) Configuration and Build System

### 12.1 `pyproject.toml`

- Build backend: setuptools.
- Defines package metadata and dependencies.
- Exposes script entry point: `server = "server.app:main"`.
- Configures pytest discovery.

### 12.2 Requirements

- `requirements.txt`: runtime server/inference dependencies.
- `requirements-train.txt`: superset for training.
- `uv.lock`: fully pinned resolution for reproducible installs.

### 12.3 Docker

`Dockerfile`:
- Python 3.11 slim base.
- Installs runtime dependencies.
- Copies project.
- Runs as non-root user.
- Starts `uvicorn server.app:app --port 7860`.

---

## 13) Documentation Set (What Each Doc Covers)

- `README.md` - complete quickstart and project narrative.
- `ARCHITECTURE.md` - conceptual architecture write-up.
- `DEPLOYMENT.md` - deployment recipes for multiple targets.
- `JUDGES_GUIDE.md` - short evaluator-focused runbook.
- `VALIDATION_CHECKLIST.md` - proof/readiness checklist.
- `SCORING_ANALYSIS.md` - reward rationale (contains some drift vs code).
- `COMPETITIVE_ANALYSIS.md` - positioning analysis.
- `HF_MINI_BLOG_DRAFT.md` - draft external-facing write-up.
- `SUBMISSION_READY.md` - final readiness checklist.

---

## 14) Operational Notes

### 14.1 Session Management

- Sessions are process-memory only.
- Restarting server clears all sessions.
- Multi-worker/distributed deployments require external session strategy to preserve state.

### 14.2 Security/Posture

- API endpoints are open by default (no auth in code path).
- Suitable for controlled/internal evaluation setup unless protected by external network/auth layers.

### 14.3 Determinism

- Core reward behavior is deterministic for fixed observation/action/gold.
- Inference/training loops can be non-deterministic due to model sampling unless configured.

---

## 15) Known Gaps and Drift (Important)

1. **Doc vs code reward mismatch**
   - Some scoring docs describe behavior not identical to current `reward.py` implementation.

2. **Deployment snippet mismatch**
   - Some docs/snippets reference `app:app`; runtime module is `server.app:app`.

3. **Exception handler caveat**
   - Global exception handling in API should be verified for proper FastAPI response semantics.

4. **Feature overclaims in narratives**
   - Some docs mention production controls (rate limits/session cleanup/access controls) that are not explicitly implemented in server code.

Treat this file and source code (`pr_review_env/*`, `server/app.py`) as the canonical technical reference.

---

## 16) End-to-End Local Runbook

### 16.1 API Server

```bash
python -m uvicorn server.app:app --host 0.0.0.0 --port 7860
```

### 16.2 Health Check

```bash
curl http://127.0.0.1:7860/health
```

### 16.3 Inference

```bash
python inference.py
```

### 16.4 Training

```bash
python train_grpo.py --env-base-url http://127.0.0.1:7860 --model-name Qwen/Qwen2.5-0.5B-Instruct
```

### 16.5 Tests

```bash
pytest
```

---

## 17) File-by-File Index (Condensed)

### Root
- `.dockerignore` - Docker build excludes.
- `.env.example` - environment variable template.
- `.gitattributes` - Git attributes/LFS patterns.
- `.gitignore` - git ignores.
- `ARCHITECTURE.md` - architecture narrative.
- `COMPETITIVE_ANALYSIS.md` - comparative framing.
- `DEPLOYMENT.md` - deployment playbook.
- `Dockerfile` - container image build/run.
- `HF_MINI_BLOG_DRAFT.md` - external comms draft.
- `JUDGES_GUIDE.md` - evaluator runbook.
- `README.md` - primary project docs.
- `SCORING_ANALYSIS.md` - reward explanation doc.
- `SUBMISSION_READY.md` - submission checklist.
- `VALIDATION_CHECKLIST.md` - validation checklist.
- `conftest.py` - pytest shared fixtures/path bootstrap.
- `inference.py` - baseline rollout client.
- `openenv.yaml` - environment spec.
- `pyproject.toml` - package/project config.
- `requirements-train.txt` - training deps.
- `requirements.txt` - runtime deps.
- `test_output_format.py` - output-format test utility.
- `train_grpo.py` - RL training script.
- `uv.lock` - lockfile.

### `pr_review_env/`
- `__init__.py` - package exports.
- `env.py` - state machine and task orchestration.
- `models.py` - strict schemas.
- `reward.py` - deterministic reward logic.

### `pr_review_env/tasks/`
- `__init__.py` - task exports.
- `easy.py` - easy task loader + grader.
- `medium.py` - medium task loader + grader.
- `hard.py` - hard task loader + grader.

### `server/`
- `__init__.py` - package marker.
- `app.py` - FastAPI routes/session handling.

### `fixtures/`
- `pr_easy.json` - easy scenario and gold.
- `pr_medium.json` - medium scenario and gold.
- `pr_hard.json` - hard scenario and gold.

### `tests/`
- `__init__.py` - marker.
- `test_env.py` - env lifecycle tests.
- `test_models.py` - schema validation tests.
- `test_reward.py` - reward engine tests.
- `test_tasks.py` - fixture/task tests.

### `colab/`
- `PR_Review_GRPO_Training.ipynb` - notebook workflow.

---

## 18) Canonical Truth Priority

When docs conflict, trust in this order:

1. `pr_review_env/models.py`
2. `pr_review_env/reward.py`
3. `pr_review_env/env.py`
4. `server/app.py`
5. `tests/*`
6. `openenv.yaml`
7. markdown narrative docs

This ordering reflects executable behavior over prose.

