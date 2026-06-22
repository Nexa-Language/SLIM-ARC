#!/usr/bin/env python3
"""
SLIM-ARC Phase 2a: MoE Expert Activation Profiler

Analyzes MoE expert tensor distribution in GGUF models and estimates
bandwidth savings from expert prediction prefetch.

Usage:
    python3 scripts/profile/analyze_moe.py <model.gguf>
"""

import argparse
import os
import sys
from collections import defaultdict
from pathlib import Path


def analyze_moe_experts(filepath: str):
    """Analyze MoE expert tensor distribution."""
    sys.path.insert(1, str(Path(__file__).parent.parent.parent / "src" / "llama-upstream" / "gguf-py"))
    from gguf import GGUFReader

    reader = GGUFReader(filepath)
    arch_field = reader.get_field("general.architecture")
    arch = bytes(arch_field.parts[-1]).decode() if arch_field else "unknown"

    n_experts = 0
    n_experts_used = 0
    expert_field = reader.get_field(f"{arch}.expert_count")
    if expert_field:
        n_experts = expert_field.parts[-1].tolist()[0] if hasattr(expert_field.parts[-1], "tolist") else int(expert_field.parts[-1])
    used_field = reader.get_field(f"{arch}.expert_used_count")
    if used_field:
        n_experts_used = used_field.parts[-1].tolist()[0] if hasattr(used_field.parts[-1], "tolist") else int(used_field.parts[-1])

    # Categorize expert tensors
    expert_tensors = defaultdict(lambda: {"count": 0, "total_size": 0})
    non_expert_tensors = {"count": 0, "total_size": 0}

    for t in reader.tensors:
        # Match expert tensor patterns: experts, exp_, _exps, ffn_*_exps
        is_expert = any(kw in t.name.lower() for kw in ["experts", "exp_", "_exps", "ffn_.*_exp"])
        if not is_expert and "_exps" in t.name:
            is_expert = True

        size = t.n_bytes
        if is_expert:
            expert_tensors["all_experts"]["count"] += 1
            expert_tensors["all_experts"]["total_size"] += size
        else:
            non_expert_tensors["count"] += 1
            non_expert_tensors["total_size"] += size

    total_expert_size = expert_tensors["all_experts"]["total_size"]
    total_size = sum(t.n_bytes for t in reader.tensors)

    # Per-layer expert analysis (match _exps, experts, exp patterns)
    layer_experts = defaultdict(int)
    for t in reader.tensors:
        if "_exps" in t.name or "experts" in t.name:
            parts = t.name.split(".")
            for p in parts:
                if p.isdigit():
                    layer = int(p)
                    layer_experts[layer] += t.n_bytes
                    break

    print(f"\n{'='*60}")
    print(f"MoE Expert Analysis: {os.path.basename(filepath)}")
    print(f"{'='*60}")
    print(f"\nArchitecture: {arch}")
    print(f"Total experts: {n_experts}")
    print(f"Experts used per token: {n_experts_used}")
    if n_experts > 0:
        sparsity = (1 - n_experts_used / n_experts) * 100
        print(f"Sparsity: {sparsity:.1f}% ({n_experts - n_experts_used}/{n_experts} experts inactive)")

    print(f"\n--- Tensor Size Breakdown ---")
    print(f"Expert tensors:     {total_expert_size / 1024**3:.2f} GiB ({expert_tensors['all_experts']['count']} tensors)")
    print(f"Non-expert tensors: {non_expert_tensors['total_size'] / 1024**3:.2f} GiB ({non_expert_tensors['count']} tensors)")
    print(f"Total:              {total_size / 1024**3:.2f} GiB")

    if n_experts > 0 and n_experts_used > 0:
        print(f"\n--- Bandwidth Savings Analysis ---")
        # OLMoE stores all experts in merged tensors (e.g. ffn_gate_exps contains all 64 experts)
        # Per-expert size = total_expert_size / n_layers / n_experts / 3 (gate, up, down)
        n_layers_with_experts = len(layer_experts)
        per_expert_size = total_expert_size / (n_layers_with_experts * n_experts) if n_layers_with_experts else 0
        print(f"Per-expert size (avg): {per_expert_size / 1024**2:.1f} MiB")

        # Without prediction: load all experts per layer
        bandwidth_full = total_expert_size  # all layers

        # With perfect prediction: load only n_experts_used experts per layer
        bandwidth_predicted = per_expert_size * n_experts_used * n_layers_with_experts

        reduction = (1 - bandwidth_predicted / bandwidth_full) * 100 if bandwidth_full > 0 else 0
        print(f"\nFull prefetch (all {n_experts} experts):    {bandwidth_full / 1024**3:.2f} GiB/forward")
        print(f"Predicted prefetch (top-{n_experts_used}): {bandwidth_predicted / 1024**3:.2f} GiB/forward")
        print(f"Bandwidth reduction:           {reduction:.1f}%")

        # Per-layer breakdown
        if layer_experts:
            print(f"\n--- Per-Layer Expert Size ---")
            print(f"{'Layer':>6} | {'Expert Size (MiB)':>18} | {'Per Expert (MiB)':>18}")
            print(f"{'-'*6} | {'-'*18} | {'-'*18}")
            for layer in sorted(layer_experts.keys())[:5]:
                size = layer_experts[layer]
                pe = size / n_experts
                print(f"{layer:6d} | {size/1024**2:18.1f} | {pe/1024**2:18.1f}")
            if len(layer_experts) > 5:
                print(f"  ... ({len(layer_experts)} layers total)")

    print(f"\n--- Prefetch Scheduling Implications ---")
    if n_experts > 0:
        print(f"1. Expert prediction can reduce I/O by ~{reduction:.0f}%")
        print(f"2. With window=3, prefetch budget per layer: {per_expert_size * n_experts_used * 3 / 1024**2:.0f} MiB")
        print(f"3. Without prediction, prefetch budget: {per_expert_size * n_experts * 3 / 1024**2:.0f} MiB")
        print(f"4. Prediction accuracy of 80% saves ~{0.8 * reduction:.0f}% bandwidth")

    return {
        "arch": arch,
        "n_experts": n_experts,
        "n_experts_used": n_experts_used,
        "expert_size": total_expert_size,
        "total_size": total_size,
    }


def main():
    parser = argparse.ArgumentParser(description="SLIM-ARC MoE Expert Profiler")
    parser.add_argument("model", help="Path to GGUF model file")
    args = parser.parse_args()

    if not os.path.exists(args.model):
        print(f"Error: {args.model} not found", file=sys.stderr)
        sys.exit(1)

    analyze_moe_experts(args.model)


if __name__ == "__main__":
    main()
