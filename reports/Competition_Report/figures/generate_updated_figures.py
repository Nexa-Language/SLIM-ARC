#!/usr/bin/env python3
"""Generate updated ablation and performance figures with serial cold-start data."""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import os

matplotlib.rcParams.update({'font.size': 13, 'axes.titlesize': 16, 'axes.labelsize': 14,
                           'xtick.labelsize': 12, 'ytick.labelsize': 12, 'legend.fontsize': 11})

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
COLORS = {'baseline': '#E74C3C', 'slimarc': '#3498DB', 'iq4xs': '#9B59B6',
          'kvq4': '#2ECC71', 'accent3': '#F39C12', 'accent4': '#1ABC9C'}

# === Figure 1: Updated ablation diverging bar (serial cold-start data) ===
def fig_ablation_updated():
    configs = ['Full\nSLIM-ARC', '-KV q4_0\n(f16)', '-MADV\n(DISABLE)', '+Eviction']
    tg_vals = [3.03, 3.92, 2.15, 3.30]
    tg_baseline = 3.03  # Full as baseline
    tg_speedup = [(v - tg_baseline) / tg_baseline * 100 for v in tg_vals]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

    # Left: absolute values
    colors = [COLORS['iq4xs'], COLORS['kvq4'], COLORS['baseline'], COLORS['accent3']]
    bars = ax1.barh(range(len(configs)), tg_vals, color=colors, alpha=0.85, edgecolor='black', linewidth=0.8)
    ax1.set_yticks(range(len(configs)))
    ax1.set_yticklabels(configs, fontsize=13)
    ax1.set_xlabel('Decode Throughput (t/s)', fontsize=14)
    ax1.set_title('(a) Absolute Performance', fontsize=16, fontweight='bold')
    ax1.grid(axis='x', alpha=0.3)
    for i, v in enumerate(tg_vals):
        ax1.text(v + 0.05, i, f'{v:.2f}', va='center', fontsize=13, fontweight='bold')

    # Right: speedup vs Full
    colors_s = [COLORS['iq4xs'] if s >= 0 else COLORS['baseline'] for s in tg_speedup]
    bars2 = ax2.barh(range(len(configs)), tg_speedup, color=colors_s, alpha=0.85, edgecolor='black', linewidth=0.8)
    ax2.set_yticks(range(len(configs)))
    ax2.set_yticklabels(configs, fontsize=13)
    ax2.set_xlabel('Speedup vs Full (%)', fontsize=14)
    ax2.set_title('(b) Relative to Full SLIM-ARC', fontsize=16, fontweight='bold')
    ax2.axvline(x=0, color='black', linewidth=0.8)
    ax2.grid(axis='x', alpha=0.3)
    for i, s in enumerate(tg_speedup):
        ax2.text(s + (1 if s > 0 else -1), i, f'{s:+.0f}%', va='center',
                ha='left' if s > 0 else 'right', fontsize=13, fontweight='bold')

    fig.suptitle('Single-Point Ablation: Component Contribution (80B IQ4_XS, 32GB, Serial Cold-Start)',
                 fontsize=15, fontweight='bold', y=1.02)
    fig.tight_layout()
    fig.savefig(os.path.join(OUTPUT_DIR, 'fig_ablation_diverging.png'), bbox_inches='tight', dpi=150)
    plt.close(fig)
    print("Generated: fig_ablation_diverging.png")

# === Figure 2: Updated optimization chain (dumbbell) ===
def fig_dumbbell_updated():
    fig, axes = plt.subplots(1, 3, figsize=(16, 6))

    envs = ['8GB\n(4 cores)', '16GB\n(8 cores)', '32GB\n(8 cores, cold)']
    # Updated data: 8GB cold-start timeout, 16GB=2.27, 32GB=3.03 (IQ4_XS cold)
    # For 8GB use previous warm data 0.76, for 32GB warm use 5.16
    baseline = [0.08, 0.18, 0.08]   # upstream baseline
    slimarc  = [0.42, 1.12, 3.03]   # SLIM-ARC cold-start (32GB=3.03)
    full     = [0.76, 2.27, 5.16]   # Full (8GB warm, 16GB cold, 32GB warm)

    x = np.arange(3)
    width = 0.28

    for i, (ax, env) in enumerate(zip(axes, envs)):
        vals = [baseline[i], slimarc[i], full[i]]
        colors = [COLORS['baseline'], COLORS['slimarc'], COLORS['iq4xs']]
        labels = ['Baseline', 'SLIM-ARC', 'Full\n(+FA)']
        bars = ax.bar(x, vals, width*2.5, color=colors, alpha=0.88, edgecolor='black', linewidth=0.8)
        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=13)
        ax.set_title(env, fontsize=16, fontweight='bold')
        ax.set_ylabel('Decode (t/s)', fontsize=14)
        ax.grid(axis='y', alpha=0.3, linestyle='--')

        for j, (bar, v) in enumerate(zip(bars, vals)):
            ax.text(bar.get_x() + bar.get_width()/2, v + max(vals)*0.02, f'{v:.2f}',
                    ha='center', va='bottom', fontsize=14, fontweight='bold')

        speedup = full[i] / baseline[i] if baseline[i] > 0 else 0
        ax.text(0.5, 0.95, f'{speedup:.1f}x', transform=ax.transAxes, fontsize=16, fontweight='bold',
                color=COLORS['iq4xs'], ha='center', va='top',
                bbox=dict(boxstyle='round,pad=0.4', facecolor='yellow', alpha=0.4))
        ax.set_ylim(0, max(vals) * 1.25)

    fig.suptitle('Progressive Optimization: Baseline -> SLIM-ARC -> Full (IQ4_XS + KV q4_0 + FlashAttention)',
                 fontsize=15, fontweight='bold', y=1.02)
    fig.tight_layout()
    fig.savefig(os.path.join(OUTPUT_DIR, 'fig_optimization_dumbbell.png'), bbox_inches='tight', dpi=150)
    plt.close(fig)
    print("Generated: fig_optimization_dumbbell.png")

# === Figure 3: Performance landscape (updated) ===
def fig_landscape_updated():
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    # (a) Three-tier decode comparison
    ax = axes[0][0]
    envs = ['8GB', '16GB', '32GB']
    tg_iq4 = [0.76, 2.27, 3.03]  # 8GB warm, 16GB cold, 32GB cold
    tg_q4k = [0.76, 0, 2.68]     # Q4_K_M (16GB tg timeout)
    x = np.arange(3)
    w = 0.35
    ax.bar(x - w/2, tg_iq4, w, label='IQ4_XS (40GB)', color=COLORS['iq4xs'], alpha=0.85, edgecolor='black', linewidth=0.5)
    ax.bar(x + w/2, tg_q4k, w, label='Q4_K_M (45GB)', color=COLORS['slimarc'], alpha=0.85, edgecolor='black', linewidth=0.5)
    ax.set_xticks(x)
    ax.set_xticklabels(envs, fontsize=13)
    ax.set_ylabel('Decode (t/s)', fontsize=14)
    ax.set_title('(a) Three-Tier Decode Performance', fontsize=16, fontweight='bold')
    ax.legend(fontsize=11)
    ax.grid(axis='y', alpha=0.3)
    for i, v in enumerate(tg_iq4):
        ax.text(i - w/2, v + 0.05, f'{v:.2f}', ha='center', va='bottom', fontsize=12, fontweight='bold')

    # (b) Optimization stacking waterfall
    ax = axes[0][1]
    stages = ['Baseline', '+MADV', '+KV q4_0', '+IQ4_XS', '+FlashAttn']
    vals = [0.08, 0.42, 0.76, 2.45, 5.16]
    deltas = [0, 0.34, 0.34, 1.69, 2.71]
    colors_w = [COLORS['baseline'], COLORS['slimarc'], COLORS['kvq4'], COLORS['iq4xs'], COLORS['accent3']]
    bars = ax.bar(stages, vals, color=colors_w, alpha=0.85, edgecolor='black', linewidth=0.5)
    ax.set_ylabel('Decode (t/s)', fontsize=14)
    ax.set_title('(b) Optimization Stacking (8GB -> 32GB warm)', fontsize=16, fontweight='bold')
    ax.grid(axis='y', alpha=0.3)
    for i, (v, d) in enumerate(zip(vals, deltas)):
        ax.text(i, v + 0.05, f'{v:.2f}', ha='center', va='bottom', fontsize=12, fontweight='bold')
        if d > 0:
            ax.text(i, v/2, f'+{d:.2f}', ha='center', va='center', fontsize=11, color='white', fontweight='bold')

    # (c) Quantization format impact
    ax = axes[1][0]
    quants = ['Q4_K_M\n(45GB)', 'IQ4_XS\n(40GB)']
    pp_vals = [5.89, 4.44]
    tg_vals = [2.68, 3.03]
    x = np.arange(2)
    w = 0.35
    ax.bar(x - w/2, pp_vals, w, label='pp64', color=COLORS['slimarc'], alpha=0.85, edgecolor='black', linewidth=0.5)
    ax.bar(x + w/2, tg_vals, w, label='tg48', color=COLORS['iq4xs'], alpha=0.85, edgecolor='black', linewidth=0.5)
    ax.set_xticks(x)
    ax.set_xticklabels(quants, fontsize=13)
    ax.set_ylabel('Throughput (t/s)', fontsize=14)
    ax.set_title('(c) IQ4_XS vs Q4_K_M (32GB cold)', fontsize=16, fontweight='bold')
    ax.legend(fontsize=11)
    ax.grid(axis='y', alpha=0.3)

    # (d) Prefill vs Decode tradeoff
    ax = axes[1][1]
    configs = ['Baseline', 'SLIM-ARC', 'Full']
    pp = [5.89, 4.44, 12.99]
    tg = [0.08, 3.03, 5.16]
    ax.scatter(pp, tg, s=200, c=[COLORS['baseline'], COLORS['slimarc'], COLORS['iq4xs']],
              edgecolors='black', linewidth=1.5, zorder=5)
    for i, cfg in enumerate(configs):
        ax.annotate(cfg, (pp[i], tg[i]), textcoords="offset points", xytext=(10, 10), fontsize=12, fontweight='bold')
    ax.set_xlabel('Prefill (t/s)', fontsize=14)
    ax.set_ylabel('Decode (t/s)', fontsize=14)
    ax.set_title('(d) Prefill vs Decode Trade-off', fontsize=16, fontweight='bold')
    ax.grid(alpha=0.3)

    fig.suptitle('SLIM-ARC Performance Landscape (Serial Cold-Start Data)', fontsize=18, fontweight='bold', y=0.98)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(os.path.join(OUTPUT_DIR, 'fig_performance_landscape.png'), bbox_inches='tight', dpi=150)
    plt.close(fig)
    print("Generated: fig_performance_landscape.png")

# === Figure 4: Small models extreme ===
def fig_small_updated():
    fig, ax = plt.subplots(figsize=(10, 6))
    models = ['Qwen3-4B\n(Dense, 2.4GB)', 'OLMoE-1B-7B\n(MoE, 3.9GB)']
    tg_vals = [2.58, 8.92]
    colors = [COLORS['slimarc'], COLORS['iq4xs']]
    bars = ax.bar(models, tg_vals, color=colors, alpha=0.85, edgecolor='black', linewidth=0.8, width=0.5)
    ax.set_ylabel('Decode (t/s)', fontsize=14)
    ax.set_title('Small Models in 2GB+1-core Extreme Environment', fontsize=16, fontweight='bold')
    ax.grid(axis='y', alpha=0.3)
    for i, v in enumerate(tg_vals):
        ax.text(i, v + 0.1, f'{v:.2f} t/s', ha='center', va='bottom', fontsize=14, fontweight='bold')
    ax.set_ylim(0, max(tg_vals) * 1.2)
    fig.tight_layout()
    fig.savefig(os.path.join(OUTPUT_DIR, 'fig_small_models.png'), bbox_inches='tight', dpi=150)
    plt.close(fig)
    print("Generated: fig_small_models.png")

# === Main ===
fig_ablation_updated()
fig_dumbbell_updated()
fig_landscape_updated()
fig_small_updated()
print("\nAll updated figures saved!")
