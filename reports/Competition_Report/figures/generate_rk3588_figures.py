#!/usr/bin/env python3
"""
SLIM-ARC: Generate RK3588 edge-side experiment charts for the academic report.
All data are transcribed from native raw records under docs/rk3588_test_notes/
and docs/rk3588_improvement/测试数据.md (source: llama-bench / llama-cli runs).
"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import os

plt.rcParams.update({
    'font.family': 'serif',
    'font.size': 11,
    'figure.dpi': 200,
    'axes.titlesize': 14,
    'axes.labelsize': 12,
    'xtick.labelsize': 10,
    'ytick.labelsize': 10,
    'legend.fontsize': 9,
    'axes.grid': True,
    'grid.alpha': 0.3,
    'axes.spines.top': False,
    'axes.spines.right': False,
})

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

C = {
    'pp':    '#2980B9',   # blue  prefill
    'tg':    '#E74C3C',   # red   decode
    'disable': '#7F8C8D', # gray
    'win':   '#27AE60',   # green
    'lose':  '#8E44AD',   # purple
    'accent': '#F39C12',
}

def _save(fig, name):
    path = os.path.join(OUTPUT_DIR, name)
    fig.savefig(path, bbox_inches='tight')
    plt.close(fig)
    print('saved', path)


def fig_edge_dynmadv():
    """Dynamic MADV fix: negative optimization -> parity with disable."""
    labels = ['Static\nRANDOM\n(before)', 'Disabled\n(upstream)', 'Dyn MADV\nprefill=SEQ\ndecode=RAND', 'Dyn MADV\nall SEQUEN\n(final)']
    pp = [0.44, 2.74, 2.82, 2.84]
    tg = [0.26, 1.41, 0.25, 1.40]
    x = np.arange(len(labels)); w = 0.34
    fig, ax = plt.subplots(figsize=(10, 6))
    b1 = ax.bar(x - w/2, pp, w, label='Prefill (pp32)', color=C['pp'], alpha=0.9, edgecolor='white', linewidth=0.5)
    b2 = ax.bar(x + w/2, tg, w, label='Decode (tg16)', color=C['tg'], alpha=0.9, edgecolor='white', linewidth=0.5)
    ax.axhline(1.41, color=C['disable'], ls='--', lw=1, label='Disable tg (reference)')
    ax.set_ylabel('Throughput (tokens/s)')
    ax.set_title('RK3588: Dynamic MADV eliminates 4-6x negative optimization\n(Qwen3-Next-80B Q4_K_M, 8GB, -t 4)')
    ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=9)
    ax.legend(loc='upper left')
    ax.set_ylim(0, 3.4)
    for bars in (b1, b2):
        for bar in bars:
            h = bar.get_height()
            ax.text(bar.get_x()+bar.get_width()/2, h+0.04, f'{h:.2f}', ha='center', fontsize=8)
    _save(fig, 'fig_edge_dynmadv.png')


def fig_edge_ablation():
    """Edge-side switch ablation: locate MADV_RANDOM as main overhead."""
    labels = ['B1 Full\nSLIM-ARC', 'B2 Disabled', 'B3 No\nMADV_RANDOM', 'B4 No\nprefetch']
    pp = [0.39, 2.02, 1.41, 0.37]
    tg = [0.23, 0.89, 0.65, 0.24]
    x = np.arange(len(labels)); w = 0.34
    fig, ax = plt.subplots(figsize=(10, 6))
    b1 = ax.bar(x - w/2, pp, w, label='Prefill (pp32)', color=C['pp'], alpha=0.9, edgecolor='white', linewidth=0.5)
    b2 = ax.bar(x + w/2, tg, w, label='Decode (tg16)', color=C['tg'], alpha=0.9, edgecolor='white', linewidth=0.5)
    ax.set_ylabel('Throughput (tokens/s)')
    ax.set_title('RK3588: switch ablation - MADV_RANDOM is the main overhead\n(Qwen3-Next-80B Q4_K_M, 8GB, -t 4)')
    ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=9)
    ax.legend(loc='upper left')
    ax.set_ylim(0, 2.4)
    for bars in (b1, b2):
        for bar in bars:
            h = bar.get_height()
            ax.text(bar.get_x()+bar.get_width()/2, h+0.03, f'{h:.2f}', ha='center', fontsize=8)
    _save(fig, 'fig_edge_ablation.png')


def fig_edge_expert():
    """Expert prefetch improvements: confidence gating wins."""
    labels = ['baseline\n(temporal)', 'CONF=1\n(confidence)', 'BUDGET=1\n(IO budget)', 'POP=16\n(top-K union)']
    issued = [27.8, 12.1, 25.8, 72.6]   # GB prefetched
    hit    = [31.1, 55.4, 28.8, 19.3]   # %
    x = np.arange(len(labels)); w = 0.5
    fig, ax = plt.subplots(figsize=(10, 6))
    bars = ax.bar(x, issued, w, color=[C['disable'], C['win'], C['pp'], C['lose']], alpha=0.9, edgecolor='white', linewidth=0.5, label='Prefetched bytes (GB)')
    ax.set_ylabel('Prefetched bytes (GB)')
    ax.set_xlabel('Expert-prefetch policy')
    ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylim(0, 85)
    for bar in bars:
        h = bar.get_height()
        ax.text(bar.get_x()+bar.get_width()/2, h+1, f'{h:.1f}', ha='center', fontsize=9, color='#333333')
    ax2 = ax.twinx()
    ax2.plot(x, hit, 'o-', color=C['accent'], lw=2, markersize=8, label='Hit rate (%)')
    for xi, hi in zip(x, hit):
        ax2.annotate(f'{hi:.1f}%', (xi, hi), textcoords='offset points', xytext=(0, 8), ha='center', fontsize=9, color='#B9770E')
    ax2.set_ylabel('Hit rate (%)', color='#B9770E'); ax2.tick_params(axis='y', labelcolor='#B9770E')
    ax2.set_ylim(0, 70)
    h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1+h2, l1+l2, loc='upper right', fontsize=9)
    ax.set_title('RK3588: expert-prefetch improvements (n=64)\nCONF=1: -56% bytes, +24pp hit rate, no speed loss')
    _save(fig, 'fig_edge_expert.png')


def fig_edge_longctx():
    """Long-context capability: bounded RSS + KV eviction works at 45GB/8GB."""
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))
    # (a) tg across context: default vs disabled
    ctx = [4096, 8192, 16384]
    tg_def = [0.53, 0.53, 0.53]
    tg_dis = [2.13, 2.15, 1.64]
    x = np.arange(len(ctx)); w = 0.3
    ax = axes[0]
    ax.bar(x - w/2, tg_def, w, label='SLIM-ARC (default)', color=C['pp'], alpha=0.9, edgecolor='white', linewidth=0.5)
    ax.bar(x + w/2, tg_dis, w, label='Disabled', color=C['disable'], alpha=0.9, edgecolor='white', linewidth=0.5)
    ax.set_xticks(x); ax.set_xticklabels([f'{c}' for c in ctx])
    ax.set_xlabel('Context length (-c)'); ax.set_ylabel('Decode (tokens/s)')
    ax.set_title('(a) Decode across context (default vs disabled)')
    ax.legend(fontsize=9); ax.set_ylim(0, 2.6)
    # (b) RSS for KV eviction variants
    ax = axes[1]
    ev = ['KV_EVICT\nW=256', 'KV_EVICT\nW=1024', 'No\neviction']
    rss = [6.34, 6.44, 6.49]
    bars = ax.bar(range(3), rss, 0.5, color=[C['win'], C['pp'], C['disable']], alpha=0.9, edgecolor='white', linewidth=0.5)
    ax.set_xticks(range(3)); ax.set_xticklabels(ev, fontsize=9)
    ax.set_ylabel('RSS peak (GiB)'); ax.set_ylim(6.0, 6.8)
    ax.axhline(8, color='#E74C3C', ls='--', lw=1)
    ax.text(2.45, 8.03, '8GB RAM', ha='right', fontsize=8, color='#C0392B')
    for bar in bars:
        h = bar.get_height()
        ax.text(bar.get_x()+bar.get_width()/2, h+0.01, f'{h:.2f}', ha='center', fontsize=9)
    ax.set_title('(b) RSS bounded ~6.5GB at 45GB/8GB (KV eviction)')
    fig.suptitle('RK3588: long-context capability (Qwen3-Next-80B Q4_K_M, 8GB)', fontsize=14, fontweight='bold')
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    _save(fig, 'fig_edge_longctx.png')


if __name__ == '__main__':
    fig_edge_dynmadv()
    fig_edge_ablation()
    fig_edge_expert()
    fig_edge_longctx()
    print('ALL RK3588 FIGURES DONE')
