#!/usr/bin/env python3
# Copyright © SixtyFPS GmbH <info@slint.dev>
# SPDX-License-Identifier: MIT
import argparse
import csv
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

parser = argparse.ArgumentParser()
parser.add_argument('evidence', type=Path)
parser.add_argument('output', type=Path)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
rows = []
series = {}
for stage in ['before', 'after', 'delivery']:
    root = args.evidence / stage / 'raw'
    for f in sorted(root.glob('regression-*.json')):
        scenario = f.stem[len('regression-'):]
        case = scenario[len('timing-' + stage + '-'):-len('-trial1')]
        result = json.loads(f.read_text())
        inputs = list(csv.DictReader((root / f'input-{scenario}.csv').open()))
        release = next(r for r in inputs if r['event_type'] == 'touch_callback' and r['touch_phase'] == '3')
        release_time = float(release['callback_time'])
        frames = list(csv.DictReader((root / f'scroll-{scenario}.csv').open()))
        packets = [json.loads(line) for line in (root / f'hid-{scenario}.jsonl').read_text().splitlines()]
        delegate = next((r for r in packets if r['kind'] == 'will_end_dragging'), {})
        measured = delegate.get('velocity_pt_per_ms')
        row = {'stage': stage, 'case': case, 'release_gap_pt': result['release_gap_pt'],
            'uikit_travel_pt': result['uikit_post_travel_pt'], 'slint_travel_pt': result['slint_post_travel_pt'],
            'travel_error_pt': result['slint_post_travel_pt'] - result['uikit_post_travel_pt'],
            'uikit_measured_launch_pt_per_s': None if measured is None else measured * 1000,
            'max_frame_gap_ms': result['max_frame_gap_ms'], 'max_touches': result['max_simultaneous_touches'],
            'hid_errors': result['hid_serialization_errors']}
        assert row['max_frame_gap_ms'] <= 30 and row['max_touches'] == 1 and row['hid_errors'] == 0
        if stage == 'after':
            assert abs(row['travel_error_pt']) < .5, row
        rows.append(row)
        selected = []; last = -1e9
        for frame in frames:
            t = float(frame['callback_time']) - release_time
            if -.1 <= t <= 3 and t - last >= .045:
                selected.append((t, float(frame['uikit_offset']), float(frame['slint_offset'])))
                last = t
        series[stage, case] = selected
        with (args.output / f'{stage}-{case}.positions.csv').open('w') as out:
            writer = csv.writer(out, lineterminator="\n"); writer.writerow(['time_since_delivered_release_s','uikit_offset_pt','slint_offset_pt']);writer.writerows(selected)
for group, cases in [('flicks', ['fast','short']), ('holds', ['hold','jitter']), ('reversals', ['reversal','near-zero'])]:
    fig, axes = plt.subplots(2, 2, figsize=(11, 7))
    for i, case in enumerate(cases):
        for j, stage in enumerate(['before', 'after']):
            data = series[stage, case]; ax = axes[i,j]
            ax.plot([r[0] for r in data], [r[1] for r in data], color='#c72d32', label='UIKit')
            ax.plot([r[0] for r in data], [r[2] for r in data], color='#176aab', label='Slint')
            ax.axvline(0, color='#888', linewidth=.7, linestyle=':')
            ax.set_title(f'{case} · '+('Before' if stage=='before' else 'Native capture timestamps'))
            ax.set_xlabel('Actual seconds after delivered release'); ax.set_ylabel('Absolute content offset (pt)')
            ax.grid(alpha=.2); ax.legend()
        limits=[value for stage in ['before','after'] for r in series[stage,case] for value in r[1:]]
        pad=max(1,(max(limits)-min(limits))*.05)
        for ax in axes[i]:ax.set_ylim(min(limits)-pad,max(limits)+pad)
    fig.tight_layout();fig.savefig(args.output/f'{group}.png',dpi=170);plt.close(fig)
with (args.output/'results.csv').open('w') as f:
    writer=csv.DictWriter(f,fieldnames=list(rows[0]), lineterminator="\n");writer.writeheader();writer.writerows(rows)
(args.output/'results.json').write_text(json.dumps(rows,indent=2)+'\n')
print(json.dumps(rows,indent=2))
