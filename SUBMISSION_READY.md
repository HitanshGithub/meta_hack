# Submission Ready Checklist

## Environment
- [x] OpenEnv-compatible API implemented
- [x] `openenv.yaml` present
- [x] Docker deployment configured

## Baseline
- [x] `inference.py` available and reproducible

## RL Training (Now Added)
- [x] `train_grpo.py` (TRL GRPO pipeline)
- [x] `requirements-train.txt` (training dependencies)
- [x] Colab notebook: `colab/PR_Review_GRPO_Training.ipynb`
- [x] Artifact generation for reward curves and before/after metrics

## Before Final Submission (External Links)
- [ ] Hugging Face Space URL added to README
- [ ] Mini-blog or <2 min video URL added to README
- [ ] Training run artifacts committed or linked (plots + summary)

## Final Validation Commands
```bash
docker build -t pr-review-env .
docker run --rm -p 7860:7860 pr-review-env
python inference.py
python train_grpo.py --env-base-url http://127.0.0.1:7860 --num-train-epochs 1 --output-dir artifacts/grpo_final
```
