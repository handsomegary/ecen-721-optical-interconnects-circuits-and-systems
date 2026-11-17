#!/usr/bin/env python3
"""Bounded deterministic timing/sizing diagnostic; raw/native cards stay on VM.

Keeps the original 35.714 ps track interval and 2 ps post-track launch delay.
An extended period and optional reset lead move reset/next acquisition;
track duration and post-track launch delay are unchanged.
This is not a 14 GHz pass if the selected period exceeds 8 UI.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import adc_comparator_probe as a

ORIGINAL_PERIOD = 8.0 / 112e9
TRACK = ORIGINAL_PERIOD / 2
RESET_LEAD = 4e-12


def clock_changes(cycles, vdd):
    track, compare = [], []
    for q in range(cycles + 1):
        start = a.T0 + q * a.PERIOD
        track += [(start, vdd), (start + TRACK, 0.)]
        compare += [(start + TRACK + a.EDGE / 2 + 2e-12, vdd),
                    (start + a.PERIOD - RESET_LEAD, 0.)]
    return track, compare


def analyze(raw, cfg, magnitude):
    t, v = raw.values[raw.sweep_names[0]], raw.values
    vdd = cfg['supply_V']
    launch_edges = a.crossings(t, v['cmp'], vdd / 2, True)
    reset_edges = a.crossings(t, v['cmp'], vdd / 2, False)
    track_edges = a.crossings(t, v['dck'], vdd / 2, False)
    diff = [p-n for p, n in zip(v['dhp'], v['dhn'])]
    extra_diff = [p-n-rp+rn for p,n,rp,rn in zip(v['dhp'],v['dhn'],v['rhp'],v['rhn'])]
    extra_cm = [(p+n-rp-rn)/2 for p,n,rp,rn in zip(v['dhp'],v['dhn'],v['rhp'],v['rhn'])]
    rows = []
    for q in range(cfg['warmup_cycles'], cfg['cycles']):
        start = a.T0 + q * a.PERIOD
        launch = a.near(launch_edges, start + TRACK + a.EDGE/2 + 2e-12)
        reset = a.near(reset_edges, start + a.PERIOD - RESET_LEAD)
        track_fall = a.near(track_edges, start + TRACK)
        end = reset - a.EDGE/2 - .1e-12
        sign = 1 if q % 2 == 0 else -1
        row = {'cycle': q, 'input_LSB': sign*magnitude,
               'evaluation_usable_s': end-launch,
               'loaded_input_at_launch_V': a.interpolate(t, diff, launch),
               'loaded_input_at_capture_V': a.interpolate(t, diff, track_fall+a.EDGE/2+1e-12),
               'nodes': {}}
        before = launch-a.EDGE/2-.1e-12
        row['prelaunch_internal_min_V'] = min(a.interpolate(t,v[n],before) for n in ('p','q','x','y'))
        row['prelaunch_raw_imbalance_V'] = a.interpolate(t,v['y'],before)-a.interpolate(t,v['x'],before)
        for node in ('p','q','x','y','tail','bx','by'):
            unused, z = a.window(t, v[node], launch, end)
            row['nodes'][node] = {'min_V': min(z), 'max_V': max(z), 'end_V': z[-1]}
        for label, hp, lp in [('raw','y','x'), ('buffered','bx','by')]:
            hi, lo = (hp,lp) if sign > 0 else (lp,hp)
            correct = [h >= .8*vdd and l <= .2*vdd for h,l in zip(v[hi],v[lo])]
            wrong = [l >= .8*vdd and h <= .2*vdd for h,l in zip(v[hi],v[lo])]
            ct, wt = a.first_stable(t,correct,launch,end), a.first_stable(t,wrong,launch,end)
            end_hi, end_lo = a.interpolate(t,v[hi],end), a.interpolate(t,v[lo],end)
            if not (end_hi >= .8*vdd and end_lo <= .2*vdd):
                ct = None
            if not (end_lo >= .8*vdd and end_hi <= .2*vdd):
                wt = None
            row[label+'_resolution_s'] = None if ct is None else ct-launch
            row[label+'_classification'] = 'correct' if ct is not None else ('wrong' if wt is not None else 'unresolved')
            row[label+'_signed_end_difference_V'] = a.interpolate(t,v[hi],end)-a.interpolate(t,v[lo],end)
        for name,trace in [('differential',extra_diff), ('common_mode',extra_cm)]:
            baseline = a.interpolate(t,trace,launch-a.EDGE/2-.1e-12)
            unused,z = a.window(t,trace,launch-a.EDGE/2,end)
            row['compare_kickback_'+name+'_peak_V'] = max(abs(x-baseline) for x in z)
        for name,source in [('comparator','VA:p'), ('buffer','VB:p')]:
            row[name+'_energy_J'] = -vdd*a.integral(t,v[source],launch,launch+a.PERIOD)
        rows.append(row)
    summary = {'decisions': len(rows)}
    for label in ('raw','buffered'):
        times = [r[label+'_resolution_s'] for r in rows if r[label+'_resolution_s'] is not None]
        summary[label+'_counts'] = {c: sum(r[label+'_classification']==c for r in rows) for c in ('correct','wrong','unresolved')}
        summary[label+'_resolution_min_s'] = min(times) if times else None
        summary[label+'_resolution_max_s'] = max(times) if times else None
        summary[label+'_signed_end_difference_min_V'] = min(r[label+'_signed_end_difference_V'] for r in rows)
    for label in ('differential','common_mode'):
        summary['max_'+label+'_kickback_V'] = max(r['compare_kickback_'+label+'_peak_V'] for r in rows)
    for label in ('comparator','buffer'):
        summary[label+'_mean_energy_J'] = sum(r[label+'_energy_J'] for r in rows)/len(rows)
    summary['max_abs_prelaunch_raw_imbalance_V'] = max(abs(r['prelaunch_raw_imbalance_V']) for r in rows)
    summary['minimum_prelaunch_internal_V'] = min(r['prelaunch_internal_min_V'] for r in rows)
    summary['node_end_ranges_V'] = {n: [min(r['nodes'][n]['end_V'] for r in rows), max(r['nodes'][n]['end_V'] for r in rows)] for n in ('p','q','x','y','tail','bx','by')}
    return rows, summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case', required=True)
    p.add_argument('--period-ps', type=float, default=ORIGINAL_PERIOD*1e12)
    p.add_argument('--reset-lead-ps', type=float, default=4.)
    p.add_argument('--magnitude-lsb', type=float, default=1.)
    p.add_argument('--tail-copies', type=int, default=1)
    p.add_argument('--input-copies', type=int, default=1)
    p.add_argument('--regen-n-copies', type=int, default=1)
    p.add_argument('--run', action='store_true')
    args = p.parse_args()
    if not args.case.replace('_','').isalnum() or not math.isfinite(args.period_ps) or args.period_ps < ORIGINAL_PERIOD*1e12:
        p.error('Safe case name and non-shortened period required')
    if not math.isfinite(args.magnitude_lsb) or args.magnitude_lsb <= 0:
        p.error('Positive finite LSB magnitude required')
    if not math.isfinite(args.reset_lead_ps) or args.reset_lead_ps < 4. or args.period_ps-args.reset_lead_ps < TRACK*1e12+28.:
        p.error('Reset lead must preserve at least 25 ps evaluation and the original reset lead')
    project = a.PROJECT
    original = json.loads((project/'runs/adc_comparator_r3_tt/comparator_probe_summary.json').read_text())
    cfg = original['configuration']
    cfg.update(cycles=8, warmup_cycles=2, noise_seed=None)
    cfg['copies'].update(tail=args.tail_copies,input=args.input_copies,regen_n=args.regen_n_copies)
    a.validate_card_identity(project/'configs/native_device_cards.json')
    native = a.install_native_cards(project/'configs/native_device_cards.json')
    if original['native_cards']['native_cards_sha256'] != native['native_cards_sha256']:
        raise ValueError('Native cards differ from the original comparator probe')
    a.PERIOD = args.period_ps*1e-12
    global RESET_LEAD
    RESET_LEAD = args.reset_lead_ps*1e-12
    a.clock_changes = clock_changes
    lines = a.make_deck(cfg,args.magnitude_lsb)
    directory = project/'runs/adc_comparator_r3_diag'/args.case
    deck_hash = hashlib.sha256(('\n'.join(lines)+'\n').encode()).hexdigest()
    if directory.exists():
        raise ValueError('Diagnostic case already exists; refuse overwrite')
    directory.mkdir(parents=True)
    (directory/'bench.scs').write_text('\n'.join(lines)+'\n')
    result = {'case':args.case,'configuration':cfg,'period_s':a.PERIOD,
              'track_duration_s':TRACK,'magnitude_LSB':args.magnitude_lsb,
              'reset_lead_s':RESET_LEAD,
              'native_cards_sha256':native['native_cards_sha256'],'deck_sha256':deck_hash,
              'extended_period_not_a_14GHz_pass':abs(a.PERIOD-ORIGINAL_PERIOD)>1e-18,
              'scope':'Deterministic comparator timing diagnostic; no ADC, noise or PVT qualification'}
    if args.run:
        result['run_status'] = a.b.run(directory,lines,timeout=90)
        if result['run_status']['exit_code'] != 0:
            a.atomic_json(directory/'diagnostic_summary.json',result)
            raise RuntimeError('Diagnostic simulation failed')
        raw = a.parse_file(a._raw_file(directory))
        result['raw_sha256'] = raw.sha256
        result['cycles'],result['summary'] = analyze(raw,cfg,args.magnitude_lsb)
    a.atomic_json(directory/'diagnostic_summary.json',result)
    print(json.dumps({k:result[k] for k in ('case','period_s','magnitude_LSB','extended_period_not_a_14GHz_pass','summary') if k in result}),flush=True)


if __name__ == '__main__':
    main()
