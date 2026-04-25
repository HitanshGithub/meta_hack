# Judges Guide

## 1) What This Submission Is
`pr-review-env` is an OpenEnv-compatible professional-task environment for PR triage and risk review.

Theme alignment:
- **Theme #3.1 (World Modeling - Professional Tasks)**.

## 2) Fast Validation
```bash
git clone <repo-url>
cd pr-review-env
docker build -t pr-review-env .
docker run --rm -p 7860:7860 pr-review-env
```

In another terminal:
```bash
curl http://127.0.0.1:7860/health
python inference.py
```

## 3) RL Training Evidence Pipeline

Colab-first path:
- Open [`colab/PR_Review_GRPO_Training.ipynb`](colab/PR_Review_GRPO_Training.ipynb)
- Run all cells (install deps, start env, run GRPO, inspect plots)

Local path:
```bash
pip install -r requirements-train.txt
python -m uvicorn server.app:app --host 0.0.0.0 --port 7860
python train_grpo.py --env-base-url http://127.0.0.1:7860 --num-train-epochs 1 --output-dir artifacts/grpo_run
```

Produced artifacts:
- `artifacts/grpo_run/logs/reward_history.csv`
- `artifacts/grpo_run/logs/training_summary.json`
- `artifacts/grpo_run/logs/before_after.md`
- `artifacts/grpo_run/plots/reward_curve.png`

## 4) What to Look At
- Reward trend over training steps (`reward_curve.png`)
- Baseline vs trained scores per task (`before_after.md`)
- Deterministic verifier components (`reward_components.csv`)

## 5) Environment API
- `POST /reset`
- `POST /step`
- `GET /state`
- `GET /tasks`
- `GET /health`
- `POST /validate` (debug/analysis helper)

## 6) Submission Links (to fill before final submit)
- HF Space URL: `TODO`
- Mini-blog or <2 min video URL: `TODO`
