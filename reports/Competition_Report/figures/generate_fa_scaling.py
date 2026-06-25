#!/usr/bin/env python3
"""Generate FlashAttention scaling + optimization chain figure for SLIM-ARC report."""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import os

fig_dir = os.path.dirname(os.path.abspath(__file__))

# === Figure 1: FlashAttention scaling with prompt length ===
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

# FA scaling data (80B IQ4_XS, 32GB, 8 threads)
pp_lens = [64, 128, 256]
pp_tps = [12.99, 10.55, 17.82]  # t/s for pp64, pp128, pp256
pp_tts = [l / t for l, t in zip(pp_lens, pp_tps)]  # time to process prompt

ax1_twin = ax1.twinx()
bars = ax1.bar(range(len(pp_lens)), pp_tps, 0.5, color='#2196F3', alpha=0.8, label='Throughput (t/s)')
line = ax1_twin.plot(range(len(pp_lens)), pp_tts, 'ro-', linewidth=2, markersize=8, label='TTFT (s)')
ax1.set_xlabel('Prompt Length (tokens)')
ax1.set_ylabel('Prefill Throughput (t/s)', color='#2196F3')
ax1_twin.set_ylabel('Time-to-First-Token (s)', color='red')
ax1.set_xticks(range(len(pp_lens)))
ax1.set_xticklabels([f'{l}' for l in pp_lens])
ax1.set_title('(a) FlashAttention: Prefill Scaling with Prompt Length')
ax1.grid(axis='y', alpha=0.3)
for i, (t, tt) in enumerate(zip(pp_tps, pp_tts)):
    ax1.text(i, t + 0.5, f'{t:.1f}', ha='center', fontsize=9, color='#1565C0')
    ax1_twin.text(i, tt + 0.3, f'{tt:.1f}s', ha='center', fontsize=8, color='red')

# === Figure 2: Optimization chain (cumulative improvement) ===
configs = ['Baseline\n(no opt)', '+MADV\nRANDOM', '+KV\nq4_0', '+IQ4_XS\nquant', '+FlashAttn\n(fa auto)']
# 80B 8GB baseline → optimized progression (tg1/tg8 values from our experiments)
# Using 32GB IQ4_XS data for the chain
tg_values = [0.08, 0.42, 0.76, 2.45, 5.16]  # cumulative improvements
colors = ['#f44336', '#FF9800', '#FFC107', '#4CAF50', '#2196F3']

bars2 = ax2.bar(range(len(configs)), tg_values, 0.6, color=colors, alpha=0.85, edgecolor='black', linewidth=0.5)
ax2.set_xlabel('Optimization Stage')
ax2.set_ylabel('Decode Throughput (t/s)')
ax2.set_title('(b) Optimization Chain: 80B Cumulative Improvement')
ax2.set_xticks(range(len(configs)))
ax2.set_xticklabels(configs, fontsize=8)
ax2.grid(axis='y', alpha=0.3)

for i, v in enumerate(tg_values):
    ax2.text(i, v + 0.15, f'{v:.2f}', ha='center', fontsize=9, fontweight='bold')

# Add improvement annotations
for i in range(1, len(tg_values)):
    improvement = (tg_values[i] / tg_values[i-1] - 1) * 100 if tg_values[i-1] > 0 else 0
    if improvement > 0:
        ax2.annotate(f'+{improvement:.0f}%', 
                    xy=(i, tg_values[i] + 0.5), fontsize=7, color='green',
                    ha='center')

ax2.set_ylim(0, max(tg_values) * 1.2)

plt.tight_layout()
plt.savefig(os.path.join(fig_dir, 'fig_flashattn_scaling.png'), dpi=150, bbox_inches='tight')
print("Saved fig_flashattn_scaling.png")
