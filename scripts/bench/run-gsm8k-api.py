#!/usr/bin/env python3
"""
SLIM-ARC GSM8K Benchmark via llama-server API

Uses a running llama-server instance to avoid model reload per question.
Following survey ALEM protocol: 8-shot, temp=0.2, top_p=0.95, exact match.

Usage:
    # Start server first:
    #   llama-server -m model.gguf -t 8 -c 4096 --port 8082
    # Then:
    #   python3 run-gsm8k-api.py --port 8082 --n-questions 20
"""
import argparse
import json
import re
import sys
import time
import urllib.request
import urllib.error

FEW_SHOT_EXAMPLES = [
    {"q": "A robe takes 2 bolts of blue fiber and half that much white fiber. How many bolts in total?",
     "a": "It takes 2 * 1/2 = 1 bolt of white fiber. So the total is 2 + 1 = 3 bolts. The answer is 3."},
    {"q": "Josh has 18 marbles. He loses 5 and buys 7 more. How many does he have?",
     "a": "He starts with 18. After losing 5: 18 - 5 = 13. After buying 7: 13 + 7 = 20. The answer is 20."},
    {"q": "A bakery sells 4 loaves at $3 each. How much total?",
     "a": "4 loaves * $3 = $12 total. The answer is 12."},
    {"q": "If a train travels 60 mph for 2.5 hours, how far?",
     "a": "Distance = 60 * 2.5 = 150 miles. The answer is 150."},
    {"q": "A store has 50 apples. 12 are sold, 8 go bad. How many left?",
     "a": "Start with 50. After selling 12: 50 - 12 = 38. After 8 go bad: 38 - 8 = 30. The answer is 30."},
    {"q": "Lisa reads 30 pages/day for 4 days. Total pages?",
     "a": "30 * 4 = 120 pages. The answer is 120."},
    {"q": "A box has 24 chocolates. 1/4 are dark. How many dark?",
     "a": "24 * 1/4 = 6 dark chocolates. The answer is 6."},
    {"q": "Tom has $50. He buys a book for $15 and a pen for $3. How much left?",
     "a": "He spends 15 + 3 = 18. He has 50 - 18 = 32 left. The answer is 32."},
]

def build_prompt(n_shot, test_question):
    prompt = ""
    for ex in FEW_SHOT_EXAMPLES[:n_shot]:
        prompt += f"Question: {ex['q']}\nAnswer: {ex['a']}\n\n"
    prompt += f"Question: {test_question}\nAnswer:"
    return prompt

def extract_answer(text):
    match = re.search(r'[Tt]he answer is[:\s]*\$?([\d,]+\.?\d*)', text)
    if match:
        return match.group(1).replace(',', '').rstrip('.')
    numbers = re.findall(r'[\d,]+\.?\d*', text)
    if numbers:
        return numbers[-1].replace(',', '').rstrip('.')
    return None

def extract_gold(answer_text):
    match = re.search(r'####\s*(\$?[\d,]+\.?\d*)', answer_text)
    if match:
        return match.group(1).replace(',', '').replace('$', '').rstrip('.')
    numbers = re.findall(r'[\d,]+\.?\d*', answer_text)
    if numbers:
        return numbers[-1].replace(',', '').rstrip('.')
    return None

def call_api(host, port, prompt, temp, top_p, n_predict):
    url = f"http://{host}:{port}/completion"
    data = json.dumps({
        "prompt": prompt,
        "n_predict": n_predict,
        "temperature": temp,
        "top_p": top_p,
        "stream": False,
    }).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read())
            return result.get("content", "")
    except Exception as e:
        print(f"API error: {e}", file=sys.stderr)
        return ""

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8082)
    parser.add_argument('--data', default='data/benchmarks/gsm8k/gsm8k_test.jsonl')
    parser.add_argument('--n-questions', type=int, default=20)
    parser.add_argument('--n-shot', type=int, default=8)
    parser.add_argument('--temp', type=float, default=0.2)
    parser.add_argument('--top-p', type=float, default=0.95)
    parser.add_argument('--n-predict', type=int, default=256)
    parser.add_argument('--output', default='logs/gsm8k_api_results.jsonl')
    args = parser.parse_args()

    questions = []
    with open(args.data) as f:
        for line in f:
            questions.append(json.loads(line))
    questions = questions[:args.n_questions]

    print(f"Testing {len(questions)} questions, {args.n_shot}-shot, temp={args.temp}", file=sys.stderr)

    results = []
    correct = 0
    total_tps = 0.0
    total_tokens = 0
    total_time = 0.0

    for i, q in enumerate(questions):
        gold = extract_gold(q['answer'])
        prompt = build_prompt(args.n_shot, q['question'])

        t0 = time.time()
        gen = call_api(args.host, args.port, prompt, args.temp, args.top_p, args.n_predict)
        elapsed = time.time() - t0

        pred = extract_answer(gen)
        is_correct = pred is not None and gold is not None and pred == gold
        if is_correct:
            correct += 1

        # Estimate tokens generated (rough: 1 token ~ 4 chars)
        gen_tokens = max(1, len(gen) // 4)
        total_tokens += gen_tokens
        total_time += elapsed

        result = {
            'idx': i,
            'question': q['question'][:80],
            'gold': gold,
            'pred': pred,
            'correct': is_correct,
            'gen_preview': gen[:120].replace('\n', ' '),
            'elapsed_s': round(elapsed, 1),
            'est_tokens': gen_tokens,
        }
        results.append(result)
        print(f"[{i+1}/{len(questions)}] gold={gold} pred={pred} {'✓' if is_correct else '✗'} ({elapsed:.1f}s, ~{gen_tokens}tok)", file=sys.stderr)

    acc = correct / len(questions) if questions else 0
    avg_tps = total_tokens / total_time if total_time > 0 else 0

    print(f"\n=== GSM8K Results ===", file=sys.stderr)
    print(f"Accuracy: {correct}/{len(questions)} = {acc:.1%}", file=sys.stderr)
    print(f"Avg throughput: ~{avg_tps:.1f} tok/s (estimated)", file=sys.stderr)
    print(f"Total time: {total_time:.1f}s", file=sys.stderr)

    with open(args.output, 'w') as f:
        for r in results:
            f.write(json.dumps(r) + '\n')
    # Summary
    summary = {'accuracy': acc, 'correct': correct, 'total': len(questions),
               'avg_tps': avg_tps, 'total_time_s': total_time}
    with open(args.output.replace('.jsonl', '_summary.json'), 'w') as f:
        json.dump(summary, f, indent=2)
    print(f"Saved to {args.output}", file=sys.stderr)
    print(f"ACCURACY={acc:.4f}")
    print(f"THROUGHPUT={avg_tps:.2f}")

if __name__ == '__main__':
    main()
