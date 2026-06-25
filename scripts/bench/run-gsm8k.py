#!/usr/bin/env python3
"""
SLIM-ARC GSM8K Few-shot Benchmark

Following the survey's ALEM protocol:
- 8-shot prompting
- temperature=0.2, top_p=0.95 (deterministic-ish)
- exact match scoring on final numerical answer

Usage:
    python3 run-gsm8k.py --model ../../data/models/Qwen3-4B-Q4_K_M.gguf \
        --binary ../../src/llama-upstream/build/bin/llama-cli \
        --n-questions 20 --n-shot 8
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

# Standard 8-shot examples from GSM8K paper (train set)
FEW_SHOT_EXAMPLES = [
    {
        "question": "A robe takes 2 bolts of blue fiber and half that much white fiber. How many bolts in total?",
        "answer": "It takes 2 * 1/2 = 1 bolt of white fiber. So the total is 2 + 1 = 3 bolts. The answer is 3."
    },
    {
        "question": "Josh has 18 marbles. He loses 5 and buys 7 more. How many does he have?",
        "answer": "He starts with 18. After losing 5: 18 - 5 = 13. After buying 7: 13 + 7 = 20. The answer is 20."
    },
    {
        "question": "A bakery sells 4 loaves at $3 each. How much total?",
        "answer": "4 loaves * $3 = $12 total. The answer is 12."
    },
    {
        "question": "If a train travels 60 mph for 2.5 hours, how far?",
        "answer": "Distance = 60 * 2.5 = 150 miles. The answer is 150."
    },
    {
        "question": "A store has 50 apples. 12 are sold, 8 go bad. How many left?",
        "answer": "Start with 50. After selling 12: 50 - 12 = 38. After 8 go bad: 38 - 8 = 30. The answer is 30."
    },
    {
        "question": "Lisa reads 30 pages/day for 4 days. Total pages?",
        "answer": "30 * 4 = 120 pages. The answer is 120."
    },
    {
        "question": "A box has 24 chocolates. 1/4 are dark. How many dark?",
        "answer": "24 * 1/4 = 6 dark chocolates. The answer is 6."
    },
    {
        "question": "Tom has $50. He buys a book for $15 and a pen for $3. How much left?",
        "answer": "He spends 15 + 3 = 18. He has 50 - 18 = 32 left. The answer is 32."
    },
]

def build_prompt(n_shot, test_question):
    """Build 8-shot prompt following survey protocol."""
    prompt = ""
    for ex in FEW_SHOT_EXAMPLES[:n_shot]:
        prompt += f"Question: {ex['question']}\nAnswer: {ex['answer']}\n\n"
    prompt += f"Question: {test_question}\nAnswer:"
    return prompt

def extract_answer(text):
    """Extract final numerical answer from model output."""
    # Look for "The answer is X" pattern
    match = re.search(r'[Tt]he answer is[:\s]*\$?([\d,]+\.?\d*)', text)
    if match:
        return match.group(1).replace(',', '').rstrip('.')
    # Fallback: last number in text
    numbers = re.findall(r'[\d,]+\.?\d*', text)
    if numbers:
        return numbers[-1].replace(',', '').rstrip('.')
    return None

def extract_gold(answer_text):
    """Extract gold answer from GSM8K format (ends with '#### N')."""
    match = re.search(r'####\s*(\$?[\d,]+\.?\d*)', answer_text)
    if match:
        return match.group(1).replace(',', '').replace('$', '').rstrip('.')
    # Fallback: last number
    numbers = re.findall(r'[\d,]+\.?\d*', answer_text)
    if numbers:
        return numbers[-1].replace(',', '').rstrip('.')
    return None

def run_model(binary, model, prompt, threads, temp, top_p, n_predict, env_vars=None):
    """Run llama-cli with the given prompt and return output."""
    env = os.environ.copy()
    env['LD_LIBRARY_PATH'] = os.path.dirname(os.path.abspath(binary)) or '.'
    if env_vars:
        env.update(env_vars)

    cmd = [
        binary, '-m', model, '-t', str(threads),
        '-c', '4096', '-n', str(n_predict),
        '--temp', str(temp), '--top-p', str(top_p),
        '-no-cnv', '-p', prompt
    ]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300,
            env=env
        )
        return result.stdout
    except subprocess.TimeoutExpired:
        return ""
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return ""

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', required=True)
    parser.add_argument('--binary', required=True)
    parser.add_argument('--data', default='data/benchmarks/gsm8k/gsm8k_test.jsonl')
    parser.add_argument('--n-questions', type=int, default=20)
    parser.add_argument('--n-shot', type=int, default=8)
    parser.add_argument('--threads', type=int, default=8)
    parser.add_argument('--temp', type=float, default=0.2)
    parser.add_argument('--top-p', type=float, default=0.95)
    parser.add_argument('--n-predict', type=int, default=256)
    parser.add_argument('--output', default='logs/gsm8k_results.jsonl')
    parser.add_argument('--env', help='extra env vars (KEY=VAL,KEY=VAL)')
    args = parser.parse_args()

    # Load GSM8K questions
    questions = []
    with open(args.data) as f:
        for line in f:
            d = json.loads(line)
            questions.append(d)

    questions = questions[:args.n_questions]
    print(f"Testing {len(questions)} questions with {args.n_shot}-shot", file=sys.stderr)

    env_vars = {}
    if args.env:
        for kv in args.env.split(','):
            k, v = kv.split('=', 1)
            env_vars[k] = v

    results = []
    correct = 0
    total = 0

    for i, q in enumerate(questions):
        gold = extract_gold(q['answer'])
        prompt = build_prompt(args.n_shot, q['question'])

        t0 = time.time()
        output = run_model(
            args.binary, args.model, prompt,
            args.threads, args.temp, args.top_p, args.n_predict,
            env_vars
        )
        elapsed = time.time() - t0

        # Extract model's answer
        # Find the part after the last "Answer:" in prompt
        gen_text = output
        # Try to isolate just the model's continuation
        marker = "Answer:"
        parts = gen_text.rsplit(marker, 1)
        if len(parts) == 2 and parts[0].endswith(q['question'][-20:]):
            gen_continuation = parts[1].strip()
        else:
            gen_continuation = gen_text[-500:]

        pred = extract_answer(gen_continuation)
        is_correct = pred is not None and gold is not None and pred == gold
        if is_correct:
            correct += 1
        total += 1

        result = {
            'idx': i,
            'question': q['question'][:100],
            'gold': gold,
            'pred': pred,
            'correct': is_correct,
            'elapsed_s': round(elapsed, 1),
        }
        results.append(result)
        print(f"[{i+1}/{len(questions)}] gold={gold} pred={pred} {'✓' if is_correct else '✗'} ({elapsed:.1f}s)", file=sys.stderr)

    acc = correct / total if total > 0 else 0
    print(f"\nGSM8K Accuracy: {correct}/{total} = {acc:.1%}", file=sys.stderr)

    # Save results
    with open(args.output, 'w') as f:
        for r in results:
            f.write(json.dumps(r) + '\n')
    print(f"Results saved to {args.output}", file=sys.stderr)
    print(f"ACCURACY={acc}")

if __name__ == '__main__':
    main()
