#!/usr/bin/env python3
"""
SLIM-ARC Phase 1: Memory Access Behavior Profiler

Analyzes GGUF model tensor distribution, size by layer, and memory access
patterns to guide prefetch scheduling decisions.

Usage:
    python3 scripts/profile/analyze_gguf.py <model.gguf> [--output report.md]
"""

import argparse
import os
import sys
import struct
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class TensorInfo:
    name: str
    dtype: int
    dims: tuple
    offset: int
    size: int  # bytes


# GGML quantization type names
GGML_TYPE_NAMES = {
    0: "F32", 1: "F16", 2: "Q4_0", 3: "Q4_1", 6: "Q5_0", 7: "Q5_1",
    8: "Q8_0", 9: "Q8_1", 10: "Q2_K", 11: "Q3_K", 12: "Q4_K",
    13: "Q5_K", 14: "Q6_K", 15: "Q8_K", 16: "IQ2_XXS", 17: "IQ2_XS",
    18: "IQ3_XXS", 19: "IQ1_S", 20: "IQ4_NL", 21: "IQ3_S", 22: "IQ2_S",
    23: "IQ4_XS", 24: "I8", 25: "I16", 26: "I32", 27: "I64", 28: "F64",
    29: "IQ1_M", 30: "BF16", 31: "Q4_0_4_4", 32: "Q4_0_4_8",
    33: "Q4_0_8_8", 34: "TQ1_0", 35: "TQ2_0",
}


def _read_value(f, vtype):
    """Read a single value of the given GGUF type."""
    if vtype == 8:  # string
        vlen = struct.unpack("<Q", f.read(8))[0]
        return f.read(vlen).decode("utf-8", errors="replace")
    elif vtype == 4:  # uint32
        return struct.unpack("<I", f.read(4))[0]
    elif vtype == 5:  # uint64
        return struct.unpack("<Q", f.read(8))[0]
    elif vtype == 6:  # float32
        return struct.unpack("<f", f.read(4))[0]
    elif vtype == 7:  # float64
        return struct.unpack("<d", f.read(8))[0]
    elif vtype == 2:  # int8
        return struct.unpack("<b", f.read(1))[0]
    elif vtype == 0:  # uint8
        return f.read(1)[0]
    elif vtype == 10:  # array: subtype + count + values
        sub_type = struct.unpack("<I", f.read(4))[0]
        n = struct.unpack("<Q", f.read(8))[0]
        return [_read_value(f, sub_type) for _ in range(n)]
    elif vtype == 3:  # int32
        return struct.unpack("<i", f.read(4))[0]
    elif vtype == 1:  # int8 (same as 2)
        return struct.unpack("<b", f.read(1))[0]
    elif vtype == 9:  # bool
        return f.read(1)[0] != 0
    else:
        raise ValueError(f"Unknown GGUF value type: {vtype}")


def parse_gguf_header(filepath: str) -> tuple:
    """Parse GGUF header using upstream gguf library."""
    import sys as _sys
    _sys.path.insert(1, str(Path(__file__).parent.parent.parent / "src" / "llama-upstream" / "gguf-py"))
    from gguf import GGUFReader

    reader = GGUFReader(filepath)
    kv = {}
    for field in reader.fields.values():
        # field.parts[-1] is the value, but for strings it's bytes
        if len(field.parts) == 0:
            continue
        val = field.parts[-1]
        if field.types and field.types[0] == 8:  # string
            try:
                val = bytes(val).decode("utf-8")
            except (UnicodeDecodeError, TypeError):
                val = str(val)
        elif hasattr(val, "tolist"):
            val = val.tolist()
            if len(val) == 1:
                val = val[0]
        kv[field.name] = val

    tensors = []
    for t in reader.tensors:
        tensors.append(TensorInfo(
            name=t.name,
            dtype=t.tensor_type,
            dims=tuple(t.shape),
            offset=t.data_offset,
            size=t.n_bytes,
        ))

    version = reader.version if hasattr(reader, "version") else 3
    return kv, tensors, version


def compute_tensor_sizes(tensors: list, kv: dict) -> list:
    """Compute byte sizes for each tensor based on dtype and dims."""
    # GGML block sizes: (block_elements, block_bytes)
    GGML_BLCK_SIZES = {
        0: (1, 4),    # F32
        1: (1, 2),    # F16
        2: (32, 18),  # Q4_0
        3: (32, 20),  # Q4_1
        6: (32, 22),  # Q5_0
        7: (32, 24),  # Q5_1
        8: (32, 34),  # Q8_0
        9: (32, 36),  # Q8_1
        10: (256, 84), # Q2_K
        11: (256, 110), # Q3_K
        12: (256, 144), # Q4_K
        13: (256, 176), # Q5_K
        14: (256, 210), # Q6_K
        15: (256, 292), # Q8_K
        30: (1, 2),   # BF16
    }
    alignment = kv.get("general.alignment", 32)
    result = []
    for t in tensors:
        blck_elems, blck_bytes = GGML_BLCK_SIZES.get(t.dtype, (1, 4))
        n_elems = 1
        for d in t.dims:
            n_elems *= d
        raw_size = (n_elems // blck_elems) * blck_bytes
        # Align
        aligned = (raw_size + alignment - 1) // alignment * alignment
        result.append(TensorInfo(t.name, t.dtype, t.dims, t.offset, aligned))
    return result


def extract_layer(name: str) -> int:
    """Extract layer index from tensor name like 'blk.0.attn_q.weight'."""
    if name.startswith("blk."):
        parts = name[4:].split(".")
        if parts[0].isdigit():
            return int(parts[0])
    return -1


def analyze_model(filepath: str) -> dict:
    """Analyze a GGUF model and return profiling data."""
    kv, tensors, version = parse_gguf_header(filepath)
    tensors = compute_tensor_sizes(tensors, kv)

    arch = kv.get("general.architecture", "unknown")
    n_layers = kv.get(f"{arch}.block_count", 0)
    n_embd = kv.get(f"{arch}.embedding_length", 0)
    n_ff = kv.get(f"{arch}.feed_forward_length", 0)
    n_heads = kv.get(f"{arch}.attention.head_count", 0)
    n_kv_heads = kv.get(f"{arch}.attention.head_count_kv", 0)
    n_experts = kv.get(f"{arch}.expert_count", 0)

    total_size = sum(t.size for t in tensors)
    file_size = os.path.getsize(filepath)

    # Group by layer
    by_layer = defaultdict(list)
    non_layer = []
    for t in tensors:
        layer = extract_layer(t.name)
        if layer >= 0:
            by_layer[layer].append(t)
        else:
            non_layer.append(t)

    # Group by tensor type
    by_type = defaultdict(int)
    for t in tensors:
        by_type[GGML_TYPE_NAMES.get(t.dtype, f"UNK{t.dtype}")] += t.size

    # Per-layer size breakdown
    layer_sizes = {}
    for layer, ts in sorted(by_layer.items()):
        layer_sizes[layer] = sum(t.size for t in ts)

    # Categorize tensors in each layer
    layer_categories = {}
    for layer, ts in sorted(by_layer.items()):
        cats = defaultdict(int)
        for t in ts:
            if "attn_q" in t.name or "attn_k" in t.name or "attn_v" in t.name:
                cats["attention_qkv"] += t.size
            elif "attn" in t.name:
                cats["attention_other"] += t.size
            elif "ffn_gate" in t.name or "ffn_up" in t.name:
                cats["ffn_gate_up"] += t.size
            elif "ffn_down" in t.name:
                cats["ffn_down"] += t.size
            elif "ffn" in t.name:
                cats["ffn_other"] += t.size
            else:
                cats["other"] += t.size
        layer_categories[layer] = dict(cats)

    return {
        "arch": arch,
        "n_layers": n_layers,
        "n_embd": n_embd,
        "n_ff": n_ff,
        "n_heads": n_heads,
        "n_kv_heads": n_kv_heads,
        "n_experts": n_experts,
        "total_tensor_size": total_size,
        "file_size": file_size,
        "n_tensors": len(tensors),
        "by_type": dict(by_type),
        "layer_sizes": layer_sizes,
        "layer_categories": layer_categories,
        "non_layer_size": sum(t.size for t in non_layer),
        "non_layer_tensors": [t.name for t in non_layer],
    }


def generate_report(data: dict, filepath: str) -> str:
    """Generate a markdown profiling report."""
    lines = []
    lines.append(f"# Memory Access Profile: {os.path.basename(filepath)}\n")
    lines.append(f"## Model Architecture\n")
    lines.append(f"- Architecture: `{data['arch']}`")
    lines.append(f"- Layers: {data['n_layers']}")
    lines.append(f"- Embedding dim: {data['n_embd']}")
    lines.append(f"- FFN dim: {data['n_ff']}")
    lines.append(f"- Attention heads: {data['n_heads']} (KV: {data['n_kv_heads']})")
    if data["n_experts"]:
        lines.append(f"- Experts: {data['n_experts']} (MoE)")
    lines.append(f"- Total tensors: {data['n_tensors']}")
    lines.append(f"- Total tensor size: {data['total_tensor_size'] / 1024**3:.2f} GiB")
    lines.append(f"- File size: {data['file_size'] / 1024**3:.2f} GiB")
    lines.append("")

    lines.append("## Tensor Size by Quantization Type\n")
    lines.append("| Type | Size (MiB) | % |")
    lines.append("|------|-----------|---|")
    for dtype, size in sorted(data["by_type"].items(), key=lambda x: -x[1]):
        pct = 100.0 * size / data["total_tensor_size"]
        lines.append(f"| {dtype} | {size / 1024**2:.1f} | {pct:.1f}% |")
    lines.append("")

    lines.append("## Per-Layer Tensor Size Breakdown\n")
    lines.append("| Layer | Total (MiB) | Attn QKV (MiB) | FFN Gate/Up (MiB) | FFN Down (MiB) |")
    lines.append("|-------|------------|----------------|-------------------|----------------|")
    for layer, cats in list(data["layer_categories"].items())[:10]:
        total = data["layer_sizes"][layer]
        qkv = cats.get("attention_qkv", 0)
        gate_up = cats.get("ffn_gate_up", 0)
        ffn_down = cats.get("ffn_down", 0)
        lines.append(f"| {layer} | {total/1024**2:.1f} | {qkv/1024**2:.1f} | {gate_up/1024**2:.1f} | {ffn_down/1024**2:.1f} |")
    if len(data["layer_categories"]) > 10:
        lines.append(f"| ... | ... | ... | ... | ... |")
    lines.append("")

    avg_layer = sum(data["layer_sizes"].values()) / max(len(data["layer_sizes"]), 1)
    lines.append(f"- Average layer size: {avg_layer / 1024**2:.1f} MiB")
    lines.append(f"- Non-layer tensors: {data['non_layer_size'] / 1024**2:.1f} MiB")
    lines.append("")

    lines.append("## Prefetch Scheduling Insights\n")
    lines.append(f"- Each layer is ~{avg_layer / 1024**2:.0f} MiB")
    lines.append(f"- With window=3, prefetch budget: ~{3 * avg_layer / 1024**2:.0f} MiB")
    lines.append(f"- FFN dominates: {sum(c.get('ffn_gate_up',0)+c.get('ffn_down',0) for c in data['layer_categories'].values())/1024**2:.1f} MiB total")
    if data["n_experts"]:
        lines.append(f"- MoE model: expert prediction can reduce I/O by ~(1-1/{data['n_experts']:.0f})*100%")
    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="SLIM-ARC GGUF memory profiler")
    parser.add_argument("model", help="Path to GGUF model file")
    parser.add_argument("--output", "-o", default=None, help="Output report file")
    args = parser.parse_args()

    if not os.path.exists(args.model):
        print(f"Error: {args.model} not found", file=sys.stderr)
        sys.exit(1)

    print(f"Analyzing {args.model}...")
    data = analyze_model(args.model)
    report = generate_report(data, args.model)

    if args.output:
        Path(args.output).write_text(report)
        print(f"Report saved to {args.output}")
    else:
        print(report)


if __name__ == "__main__":
    main()
