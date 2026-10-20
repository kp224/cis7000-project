#!/usr/bin/env python3
"""Plot validated contention results; requires Matplotlib."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import ScalarFormatter

COUNTS = (1, 2, 4, 8)
COLORS = {'cfs': '#2563B8', 'eevdf': '#D66B29'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path, help='Directory containing summary.json')
    args = parser.parse_args()
    data = json.loads((args.root / 'summary.json').read_text())
    groups = {(g['variant'], g['workers']): g for g in data['groups']}
    if len(groups) != 8 or set(groups) != {(v, n) for v in COLORS for n in COUNTS}:
        parser.error('Expected both kernels at 1, 2, 4 and 8 competing workers.')
    if any(g['repeats'] != data['repeats'] for g in groups.values()):
        parser.error('Inconsistent repeat counts.')
    plt.rcParams.update({
        'font.family': 'DejaVu Sans', 'font.size': 10.5,
        'axes.labelcolor': '#374151', 'xtick.color': '#596579',
        'ytick.color': '#596579', 'axes.edgecolor': '#C9D1DC',
        'axes.spines.top': False, 'axes.spines.right': False, 'svg.fonttype': 'none',
    })
    fig, axes = plt.subplots(1, 3, figsize=(14.5, 6.8), facecolor='white')
    fig.subplots_adjust(left=.065, right=.97, bottom=.27, top=.70, wspace=.34)
    fig.text(.065, .93, 'CFS vs EEVDF under CPU contention', fontsize=23,
             fontweight='bold', color='#142438')
    fig.text(.065, .875, 'One periodic task + 1, 2, 4 or 8 busy workers on CPU 2',
             fontsize=13, color='#596579')
    fig.text(.065, .825, '1,000 periodic jobs per run · about 1 ms of calibrated work every 10 ms',
             fontsize=11, color='#596579')
    panels = [
        ('p99_us', .001, 'Tail latency', 'p99 completion latency (ms)'),
        ('background_chunks_per_s', 1, 'Background throughput', 'Completed fixed-work chunks / second'),
        ('missed_deadlines', .1, 'Missed deadlines', 'Jobs missing their 10 ms deadline (%)'),
    ]
    for ax, (metric, scale, title, ylabel) in zip(axes, panels):
        for variant in COLORS:
            values = [groups[variant, n]['metrics'][metric] for n in COUNTS]
            middle = [v['median'] * scale for v in values]
            errors = [[(v['median'] - v['min']) * scale for v in values],
                      [(v['max'] - v['median']) * scale for v in values]]
            ax.errorbar(COUNTS, middle, yerr=errors, color=COLORS[variant],
                        label=variant.upper(), marker='o' if variant == 'cfs' else 's',
                        markersize=6, markerfacecolor='white', capsize=4,
                        linewidth=2, linestyle='-' if variant == 'cfs' else '--',
                        clip_on=False)
        ax.set_title(title, loc='left', fontsize=14, fontweight='bold', color='#142438', pad=16)
        ax.set_xscale('log', base=2)
        ax.set_xticks(COUNTS, labels=[str(n) for n in COUNTS])
        ax.set_xlim(.85, 9.4)
        ax.set_xlabel('Competing workers', labelpad=9)
        ax.set_ylabel(ylabel, labelpad=8)
        ax.grid(color='#E9EDF2', linewidth=.8)
        ax.set_axisbelow(True)
        ax.set_ylim(bottom=0)
    latency = [g['metrics']['p99_us'][k] * .001 for g in groups.values() for k in ('min', 'max')]
    log_latency = min(latency) > 0 and max(latency) / min(latency) >= 50
    if log_latency:
        axes[0].set_yscale('log')
        axes[0].set_ylim(min(latency) / 1.3, max(latency) * 1.3)
        axes[0].set_ylabel('p99 completion latency (ms, log scale)')
        axes[0].yaxis.set_major_formatter(ScalarFormatter())
    axes[2].set_ylim(0, 100)
    axes[2].set_yticks([0, 25, 50, 75, 100])
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='upper right', bbox_to_anchor=(.965, .82),
               frameon=False, ncol=2, fontsize=11)
    repeats = data['repeats']
    calibration = data['calibration_ns_per_loop']
    fig.text(.065, .165, f'{repeats} measured runs per kernel/load · Points: median across runs · Bars: observed min–max, not confidence intervals',
             fontsize=10.5, color='#374151')
    fig.text(.065, .115, f'Normal policy, nice 0, calibration {calibration} ns/loop. Background throughput excludes work outside the periodic interval.',
             fontsize=9.5, color='#6B7280')
    note = 'Exploratory matrix; kernel order was not alternated. Warm-up excluded.'
    if log_latency:
        note += ' Tail-latency axis is logarithmic.'
    fig.text(.065, .07, note, fontsize=9.5, color='#6B7280')
    for extension in ('png', 'svg'):
        target = args.root / f'contention.{extension}'
        fig.savefig(target, dpi=180, facecolor='white')
        print(target)
    plt.close(fig)


if __name__ == '__main__':
    main()
