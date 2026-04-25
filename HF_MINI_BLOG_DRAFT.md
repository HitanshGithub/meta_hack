# Mini Blog Draft (Hackathon)

## Title
Training LLMs for Real PR Triage with OpenEnv, TRL GRPO, and Verifiable Rewards

## Problem
LLMs can summarize code diffs, but real engineering teams need more than summaries. They need consistent triage decisions, risk prioritization, and review comments grounded in evidence from code and reviewer discussion.

## Environment
We built `pr-review-env`, an OpenEnv environment with three realistic PR tasks:
- Easy: off-by-one bugfix
- Medium: auth token expiry regression
- Hard: Redis TOCTOU race condition

The agent acts in stages:
1. identify risk
2. assess impact
3. final triage

## Reward Design
The reward is deterministic and verifiable:
- Decision correctness
- Label F1
- Priority alignment
- Summary quality and evidence terms
- Consistency penalties
- Step penalty for efficiency

This keeps rewards objective while reducing reward hacking.

## Training
We trained with TRL GRPO using environment-verifiable rewards through `/validate`, with a Colab-first pipeline and optional Unsloth acceleration.

Artifacts generated:
- Reward curve (`reward_curve.png`)
- Reward logs (`reward_history.csv`)
- Baseline vs trained table (`before_after.md`)

## Results
Training increased average reward and improved consistency on medium/hard risk tasks. The pipeline is fully reproducible from notebook and script.

## Why It Matters
This work targets a real professional capability gap: reliable PR risk triage under noisy signals and partial observability. It aligns with OpenEnv Theme #3.1 (World Modeling - Professional Tasks).

## Links
- Repo: `TODO`
- HF Space: `TODO`
- Colab notebook: `colab/PR_Review_GRPO_Training.ipynb`
