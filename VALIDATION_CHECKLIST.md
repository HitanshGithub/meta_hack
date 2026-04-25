# Validation Checklist

## Mandatory Hackathon Checks

### OpenEnv Environment
- [ ] `openenv.yaml` is valid
- [ ] Environment starts via Docker
- [ ] Required endpoints work: `/reset`, `/step`, `/state`, `/tasks`, `/health`

### Inference Reproducibility
- [ ] `python inference.py` runs end-to-end
- [ ] Output format uses `[START]`, `[STEP]`, `[END]`

### RL Training Pipeline (TRL/Unsloth)
- [ ] Colab notebook runs: `colab/PR_Review_GRPO_Training.ipynb`
- [ ] `python train_grpo.py ...` runs without API errors
- [ ] Reward logs are produced
- [ ] Reward curve image is produced
- [ ] Before/after score table is produced

### Training Artifacts
- [ ] `artifacts/<run>/logs/reward_history.csv`
- [ ] `artifacts/<run>/logs/training_summary.json`
- [ ] `artifacts/<run>/logs/before_after.md`
- [ ] `artifacts/<run>/plots/reward_curve.png`

### Storytelling Requirements
- [ ] README explains problem, environment, rewards, and results
- [ ] README links to HF Space
- [ ] README links to mini-blog or <2 min video

## Quick Command Flow
```bash
docker build -t pr-review-env .
docker run --rm -p 7860:7860 pr-review-env
python inference.py
python train_grpo.py --env-base-url http://127.0.0.1:7860 --num-train-epochs 1 --output-dir artifacts/grpo_run
```
