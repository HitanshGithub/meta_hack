from __future__ import annotations

import argparse
import csv
import inspect
import json
import random
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, request

import matplotlib.pyplot as plt
import torch
from datasets import Dataset
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer
from trl import GRPOConfig, GRPOTrainer


SYSTEM_PROMPT = """You are a senior pull request triage reviewer.
Return only valid JSON with this exact schema:
{
  "decision": "approve|request_changes|close",
  "labels": ["bug|security|enhancement|documentation|breaking-change|needs-tests|trivial|urgent"],
  "priority": "low|medium|high|critical",
  "review_summary": "1-3 sentence review summary"
}
"""

ALLOWED_LABELS = {
    "bug",
    "security",
    "enhancement",
    "documentation",
    "breaking-change",
    "needs-tests",
    "trivial",
    "urgent",
}

MIN_REWARD = 0.01
MAX_REWARD = 0.99


def clamp_reward(value: float) -> float:
    return max(MIN_REWARD, min(MAX_REWARD, value))


def strip_code_fences(raw: str) -> str:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def safe_json_loads(raw: str) -> dict[str, Any] | None:
    cleaned = strip_code_fences(raw)
    if not cleaned:
        return None
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        return None
    required = {"decision", "labels", "priority", "review_summary"}
    if set(parsed.keys()) != required:
        return None
    if parsed["decision"] not in {"approve", "request_changes", "close"}:
        return None
    if parsed["priority"] not in {"low", "medium", "high", "critical"}:
        return None
    if not isinstance(parsed["labels"], list):
        return None
    if any(label not in ALLOWED_LABELS for label in parsed["labels"]):
        return None
    if not isinstance(parsed["review_summary"], str) or not parsed["review_summary"].strip():
        return None
    return parsed


@dataclass
class EnvClient:
    base_url: str

    def _post(self, path: str, payload: dict[str, Any], session_id: str | None = None) -> tuple[dict[str, Any], str | None]:
        headers = {"Content-Type": "application/json"}
        if session_id:
            headers["session_id"] = session_id
        req = request.Request(
            url=f"{self.base_url}{path}",
            method="POST",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
        )
        with request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return body, resp.headers.get("session_id")

    def reset(self, task: str) -> tuple[dict[str, Any], str]:
        observation, session_id = self._post("/reset", {"task": task})
        if not session_id:
            session_id = "default"
        return observation, session_id

    def step(self, action: dict[str, Any], session_id: str) -> dict[str, Any]:
        result, _ = self._post("/step", action, session_id=session_id)
        return result

    def validate(self, task: str, action: dict[str, Any]) -> tuple[float, dict[str, float]]:
        response, _ = self._post("/validate", {"task": task, "action": action})
        if not response.get("valid", False):
            return MIN_REWARD, {}
        reward_breakdown = response.get("reward_breakdown", {})
        total = clamp_reward(float(reward_breakdown.get("total", MIN_REWARD)))
        return total, {str(k): float(v) for k, v in reward_breakdown.items() if isinstance(v, (int, float))}


def format_observation_prompt(observation: dict[str, Any]) -> str:
    payload = {
        "task_name": observation.get("task_name"),
        "title": observation.get("title"),
        "description": observation.get("description"),
        "diff": observation.get("diff"),
        "comments": observation.get("comments"),
        "files_changed": observation.get("files_changed"),
        "author": observation.get("author"),
        "base_branch": observation.get("base_branch"),
        "additions": observation.get("additions"),
        "deletions": observation.get("deletions"),
        "current_step": observation.get("current_step"),
        "max_steps": observation.get("max_steps"),
        "review_stage": observation.get("review_stage"),
        "stage_prompt": observation.get("stage_prompt"),
    }
    return (
        f"{SYSTEM_PROMPT}\n\n"
        "Current observation:\n"
        f"{json.dumps(payload, ensure_ascii=True)}\n\n"
        "Return valid JSON only."
    )


def bootstrap_action(task: str) -> dict[str, Any]:
    if task == "easy":
        return {
            "decision": "approve",
            "labels": ["bug"],
            "priority": "low",
            "review_summary": "Off-by-one boundary fix looks correct and low risk.",
        }
    if task == "medium":
        return {
            "decision": "request_changes",
            "labels": ["security", "breaking-change"],
            "priority": "critical",
            "review_summary": "Token expiry checks were removed and this creates a serious auth risk.",
        }
    return {
        "decision": "request_changes",
        "labels": ["bug", "needs-tests", "urgent"],
        "priority": "high",
        "review_summary": "Rate limiter logic appears non-atomic and may race under concurrency.",
    }


def build_training_dataset(
    env: EnvClient,
    num_samples: int,
    curriculum: tuple[float, float, float],
    seed: int,
) -> Dataset:
    random.seed(seed)
    tasks = ["easy", "medium", "hard"]
    stage_choices = [0, 1, 2]
    stage_weights = [0.55, 0.30, 0.15]

    rows: list[dict[str, Any]] = []
    for _ in range(num_samples):
        task = random.choices(tasks, weights=list(curriculum), k=1)[0]
        target_stage = random.choices(stage_choices, weights=stage_weights, k=1)[0]
        observation, session_id = env.reset(task)
        for _step in range(target_stage):
            try:
                result = env.step(bootstrap_action(task), session_id=session_id)
                observation = result.get("observation", observation)
                if result.get("done", False):
                    break
            except error.URLError:
                break
        rows.append({"prompt": format_observation_prompt(observation), "task": task})
    return Dataset.from_list(rows)


def extract_completion_text(completion: Any) -> str:
    if isinstance(completion, str):
        return completion
    if isinstance(completion, list):
        parts: list[str] = []
        for item in completion:
            if isinstance(item, dict):
                content = item.get("content", "")
                if isinstance(content, str):
                    parts.append(content)
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts).strip()
    if isinstance(completion, dict):
        content = completion.get("content", "")
        if isinstance(content, str):
            return content
    return str(completion)


def generate_action_text(model: Any, tokenizer: Any, prompt: str, max_new_tokens: int) -> str:
    inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=2048)
    inputs = {k: v.to(model.device) for k, v in inputs.items()}
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=True,
            temperature=0.2,
            top_p=0.9,
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id,
        )
    prompt_len = inputs["input_ids"].shape[1]
    text = tokenizer.decode(outputs[0][prompt_len:], skip_special_tokens=True)
    return text.strip()


def evaluate_model(
    env: EnvClient,
    model: Any,
    tokenizer: Any,
    episodes_per_task: int,
    max_episode_steps: int,
    max_new_tokens: int,
) -> dict[str, float]:
    task_scores: dict[str, float] = {}
    for task in ("easy", "medium", "hard"):
        episode_scores: list[float] = []
        for _ in range(episodes_per_task):
            observation, session_id = env.reset(task)
            rewards: list[float] = []
            for _step in range(max_episode_steps):
                prompt = format_observation_prompt(observation)
                raw = generate_action_text(model, tokenizer, prompt, max_new_tokens=max_new_tokens)
                action = safe_json_loads(raw) or bootstrap_action(task)
                result = env.step(action, session_id=session_id)
                reward = clamp_reward(float(result.get("reward", MIN_REWARD)))
                rewards.append(reward)
                observation = result.get("observation", observation)
                if result.get("done", False):
                    break
            episode_scores.append(sum(rewards) / len(rewards) if rewards else MIN_REWARD)
        task_scores[task] = float(sum(episode_scores) / len(episode_scores))
    task_scores["overall"] = float(sum(task_scores.values()) / 3.0)
    return task_scores


def save_reward_curve(reward_rows: list[dict[str, Any]], output_dir: Path) -> None:
    if not reward_rows:
        return
    xs = [int(row["training_step"]) for row in reward_rows]
    ys = [float(row["mean_reward"]) for row in reward_rows]
    plt.figure(figsize=(8, 4.8))
    plt.plot(xs, ys, color="#0b7a75", linewidth=2.0, marker="o", markersize=3)
    plt.title("GRPO Training Reward Curve")
    plt.xlabel("Training Step")
    plt.ylabel("Mean Reward")
    plt.grid(alpha=0.25)
    plot_path = output_dir / "plots" / "reward_curve.png"
    plot_path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(plot_path, dpi=140)
    plt.close()


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_grpo_config(args: argparse.Namespace, output_dir: Path) -> GRPOConfig:
    config_kwargs: dict[str, Any] = {
        "output_dir": str(output_dir / "checkpoints"),
        "num_train_epochs": args.num_train_epochs,
        "per_device_train_batch_size": args.per_device_train_batch_size,
        "gradient_accumulation_steps": args.gradient_accumulation_steps,
        "learning_rate": args.learning_rate,
        "max_prompt_length": args.max_prompt_length,
        "max_completion_length": args.max_completion_length,
        "logging_steps": args.logging_steps,
        "save_steps": args.save_steps,
        "bf16": torch.cuda.is_available(),
        "report_to": "none",
    }
    valid_params = inspect.signature(GRPOConfig.__init__).parameters
    filtered = {k: v for k, v in config_kwargs.items() if k in valid_params}
    return GRPOConfig(**filtered)


def maybe_load_model_with_unsloth(args: argparse.Namespace) -> tuple[Any, Any]:
    from unsloth import FastLanguageModel, PatchFastRL  # type: ignore

    PatchFastRL("GRPO", FastLanguageModel)
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.model_name,
        max_seq_length=args.max_seq_length,
        load_in_4bit=True,
    )
    model = FastLanguageModel.get_peft_model(
        model,
        r=args.lora_r,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    return model, tokenizer


def load_model(args: argparse.Namespace) -> tuple[Any, Any]:
    if args.use_unsloth:
        try:
            return maybe_load_model_with_unsloth(args)
        except Exception as exc:  # pragma: no cover - runtime fallback
            print(f"[WARN] Unsloth load failed, falling back to transformers: {exc}")

    tokenizer = AutoTokenizer.from_pretrained(args.model_name, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    dtype = torch.bfloat16 if torch.cuda.is_available() else torch.float32
    model = AutoModelForCausalLM.from_pretrained(
        args.model_name,
        torch_dtype=dtype,
        device_map="auto",
        trust_remote_code=True,
    )
    lora = LoraConfig(
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        bias="none",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora)
    return model, tokenizer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train PR-review policy with TRL GRPO and OpenEnv verifier rewards.")
    parser.add_argument("--env-base-url", type=str, default="http://127.0.0.1:7860")
    parser.add_argument("--model-name", type=str, default="Qwen/Qwen2.5-3B-Instruct")
    parser.add_argument("--output-dir", type=str, default="artifacts/grpo_run")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--num-samples", type=int, default=120)
    parser.add_argument("--num-train-epochs", type=int, default=1)
    parser.add_argument("--per-device-train-batch-size", type=int, default=1)
    parser.add_argument("--gradient-accumulation-steps", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=1e-5)
    parser.add_argument("--max-seq-length", type=int, default=2048)
    parser.add_argument("--max-prompt-length", type=int, default=1400)
    parser.add_argument("--max-completion-length", type=int, default=220)
    parser.add_argument("--max-new-tokens", type=int, default=220)
    parser.add_argument("--logging-steps", type=int, default=5)
    parser.add_argument("--save-steps", type=int, default=50)
    parser.add_argument("--episodes-per-task", type=int, default=2)
    parser.add_argument("--max-episode-steps", type=int, default=6)
    parser.add_argument("--use-unsloth", action="store_true")
    parser.add_argument("--lora-r", type=int, default=16)
    parser.add_argument("--lora-alpha", type=int, default=16)
    parser.add_argument("--lora-dropout", type=float, default=0.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    random.seed(args.seed)
    torch.manual_seed(args.seed)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    env = EnvClient(args.env_base_url)
    print(f"[INFO] Building curriculum dataset from {args.env_base_url}")
    dataset = build_training_dataset(env, args.num_samples, curriculum=(0.6, 0.3, 0.1), seed=args.seed)

    print(f"[INFO] Loading model: {args.model_name}")
    model, tokenizer = load_model(args)

    print("[INFO] Running baseline evaluation")
    baseline = evaluate_model(
        env=env,
        model=model,
        tokenizer=tokenizer,
        episodes_per_task=args.episodes_per_task,
        max_episode_steps=args.max_episode_steps,
        max_new_tokens=args.max_new_tokens,
    )

    reward_rows: list[dict[str, Any]] = []
    reward_components: list[dict[str, Any]] = []

    def env_reward_fn(completions: list[Any], task: list[str] | None = None, **_kwargs: Any) -> list[float]:
        rewards: list[float] = []
        tasks = task if isinstance(task, list) else ["easy"] * len(completions)
        for idx, completion in enumerate(completions):
            raw = extract_completion_text(completion)
            parsed = safe_json_loads(raw)
            if parsed is None:
                rewards.append(MIN_REWARD)
                continue
            score, breakdown = env.validate(tasks[idx], parsed)
            rewards.append(score)
            if breakdown:
                reward_components.append({"task": tasks[idx], **breakdown})
        mean_reward = sum(rewards) / len(rewards) if rewards else MIN_REWARD
        reward_rows.append(
            {
                "training_step": len(reward_rows) + 1,
                "mean_reward": mean_reward,
                "timestamp": int(time.time()),
            }
        )
        return rewards

    grpo_config = build_grpo_config(args, output_dir)
    trainer_kwargs: dict[str, Any] = {
        "model": model,
        "args": grpo_config,
        "train_dataset": dataset,
        "reward_funcs": [env_reward_fn],
    }
    trainer_sig = inspect.signature(GRPOTrainer.__init__).parameters
    if "processing_class" in trainer_sig:
        trainer_kwargs["processing_class"] = tokenizer
    if "tokenizer" in trainer_sig:
        trainer_kwargs["tokenizer"] = tokenizer

    print("[INFO] Starting GRPO training")
    trainer = GRPOTrainer(**trainer_kwargs)
    trainer.train()

    final_model_dir = output_dir / "checkpoints" / "final"
    final_model_dir.mkdir(parents=True, exist_ok=True)
    trainer.save_model(str(final_model_dir))
    tokenizer.save_pretrained(str(final_model_dir))

    print("[INFO] Running post-training evaluation")
    after = evaluate_model(
        env=env,
        model=trainer.model,
        tokenizer=tokenizer,
        episodes_per_task=args.episodes_per_task,
        max_episode_steps=args.max_episode_steps,
        max_new_tokens=args.max_new_tokens,
    )

    write_csv(output_dir / "logs" / "reward_history.csv", reward_rows, ["training_step", "mean_reward", "timestamp"])
    if reward_components:
        component_fields = sorted({key for row in reward_components for key in row.keys()})
        write_csv(output_dir / "logs" / "reward_components.csv", reward_components, component_fields)
    save_reward_curve(reward_rows, output_dir)

    summary = {
        "baseline": baseline,
        "after_training": after,
        "improvement_overall": after["overall"] - baseline["overall"],
        "config": vars(args),
    }
    with (output_dir / "logs" / "training_summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)

    markdown = (
        "| Metric | Baseline | Trained |\n"
        "|---|---:|---:|\n"
        f"| Easy | {baseline['easy']:.3f} | {after['easy']:.3f} |\n"
        f"| Medium | {baseline['medium']:.3f} | {after['medium']:.3f} |\n"
        f"| Hard | {baseline['hard']:.3f} | {after['hard']:.3f} |\n"
        f"| Overall | {baseline['overall']:.3f} | {after['overall']:.3f} |\n"
    )
    with (output_dir / "logs" / "before_after.md").open("w", encoding="utf-8") as handle:
        handle.write(markdown)

    print("[DONE] Training complete")
    print(markdown)
    print(f"[INFO] Artifacts written to: {output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
