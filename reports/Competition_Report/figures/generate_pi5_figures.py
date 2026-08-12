#!/usr/bin/env python3
"""
SLIM-ARC: Generate Raspberry Pi 5 (4GB) edge test charts for the academic report.
All data transcribed from native raw records under docs/pi5_4GB_test_notes/
(raw-41~47, smoke-*, llama-bench).
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
    'xtick.labelsize': 9,
    'ytick.labelsize': 10,
    'legend.fontsize': 9,
    'axes.grid': True,
    'grid.alpha': 0.3,
    'axes.spines.top': False,
    'axes.spines.right': False,
})

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
C = {'pp': '#2980B9', 'tg': '#E74C3C', 'acc': '#27AE60', 'gray': '#7F8C8D', 'warn': '#F39C12'}


def _save(fig, name):
    p = os.path.join(OUTPUT_DIR, name)
    fig.savefig(p, bbox_inches='tight')
    plt.close(fig)
    print('saved', p)


def fig_pi5_matrix():
    """llama-cli test matrix: Prompt vs Generation across cases."""
    labels = ['Cold', 'Hot', 'KV\nq4_0', 'FA\nauto', 'FA\noff', 'ctx\n512', 'ctx\n1024', 'KV\nevict', 'No\nMADV']
    pp = [9.6, 11.8, 7.8, 6.7, 6.3, 7.6, 7.8, 8.1, 6.7]
    tg = [4.1, 4.3, 3.3, 3.1, 3.1, 3.0, 2.6, 3.4, 3.2]
    x = np.arange(len(labels)); w = 0.34
    fig, ax = plt.subplots(figsize=(11, 6))
    b1 = ax.bar(x - w/2, pp, w, label='Prompt (t/s)', color=C['pp'], alpha=0.9, edgecolor='white', linewidth=0.5)
    b2 = ax.bar(x + w/2, tg, w, label='Generation (t/s)', color=C['tg'], alpha=0.9, edgecolor='white', linewidth=0.5)
    ax.set_ylabel('Throughput (tokens/s)')
    ax.set_title('Pi5 4GB: Qwen3-4B full test matrix (llama-cli, --single-turn, hot cache)\nAll cases EXIT=0, no OOM')
    ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=9)
    ax.legend(loc='upper left')
    ax.set_ylim(0, 13.5)
    for bars in (b1, b2):
        for bar in bars:
            h = bar.get_height()
            ax.text(bar.get_x()+bar.get_width()/2, h+0.15, f'{h:.1f}', ha='center', fontsize=7.5)
    _save(fig, 'fig_pi5_matrix.png')


def fig_pi5_bench():
    """llama-bench steady-state throughput."""
    labels = ['pp64', 'tg32', 'pp128', 'tg64']
    vals = [10.16, 3.48, 6.88, 2.93]
    cols = [C['pp'], C['tg'], C['pp'], C['tg']]
    fig, ax = plt.subplots(figsize=(8, 6))
    bars = ax.bar(range(4), vals, 0.5, color=cols, alpha=0.9, edgecolor='white', linewidth=0.5)
    ax.set_xticks(range(4)); ax.set_xticklabels(labels)
    ax.set_ylabel('Throughput (tokens/s)')
    ax.set_title('Pi5 4GB: llama-bench steady state (Qwen3-4B Q4_K_M, -t 4)\npp64 10.16 / tg32 3.48 | pp128 6.88 / tg64 2.93')
    ax.set_ylim(0, 12)
    for bar in bars:
        h = bar.get_height()
        ax.text(bar.get_x()+bar.get_width()/2, h+0.15, f'{h:.2f}', ha='center', fontsize=10)
    _save(fig, 'fig_pi5_bench.png')


def fig_pi5_memory():
    """Memory footprint + microSD bottleneck."""
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))
    # (a) RSS peak vs 4GB budget
    ax = axes[0]
    bars = ax.bar([0], [2.42], 0.45, color=C['acc'], alpha=0.9, edgecolor='white', linewidth=0.5, label='RSS peak')
    ax.axhline(4, color=C['tg'], ls='--', lw=1.5)
    ax.text(0.55, 4.06, '4GB total RAM', ha='right', fontsize=9, color='#C0392B')
    ax.set_xticks([0]); ax.set_xticklabels(['Qwen3-4B\n(2.33GB model)'])
    ax.set_ylabel('Memory (GiB)'); ax.set_ylim(0, 5)
    for bar in bars:
        ax.text(bar.get_x()+bar.get_width()/2, bar.get_height()+0.06, '2.42', ha='center', fontsize=10)
    ax.set_title('(a) RSS peak 2.42 GiB < 4GB (no OOM)')
    # (b) cold vs hot prefill (microSD bottleneck)
    ax = axes[1]
    bars = ax.bar(['Cold\n(microSD read)', 'Hot\n(page cache)'], [0.3, 3.96], 0.5,
                  color=[C['gray'], C['pp']], alpha=0.9, edgecolor='white', linewidth=0.5)
    ax.set_ylabel('Prefill (tokens/s)')
    ax.set_ylim(0, 4.6)
    for bar in bars:
        h = bar.get_height()
        ax.text(bar.get_x()+bar.get_width()/2, h+0.06, f'{h:.2f}', ha='center', fontsize=10)
    ax.annotate('13x', xy=(1, 3.96), xytext=(0.45, 3.0), fontsize=12, color='#C0392B',
                arrowprops=dict(arrowstyle='->', color='#C0392B'))
    ax.set_title('(b) microSD is the cold-start bottleneck (13x)')
    fig.suptitle('Pi5 4GB: memory footprint & storage bottleneck (Qwen3-4B)', fontsize=14, fontweight='bold')
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    _save(fig, 'fig_pi5_memory.png')


if __name__ == '__main__':
    fig_pi5_matrix()
    fig_pi5_bench()
    fig_pi5_memory()
    print('ALL PI5 FIGURES DONE')
