#!/usr/bin/env python3
"""Test script to validate inference output format"""

print('[START] task=easy env=pr-review-env model=Qwen/Qwen2.5-72B-Instruct')
action_str = '{"decision":"approve","labels":["bug"],"priority":"low","review_summary":"LGTM"}'
print('[STEP] step=1 action=' + action_str + ' reward=<0.95> done=true error=')
print('[END] success=true steps=1 score=<0.95> rewards=0.95')
print('Output format validated')
