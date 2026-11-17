#!/usr/bin/env python3
"""Four native StrongARM reset variants under ideal comparator-input clamps.

This isolates internal reset/decision behavior from the preceding short-track
acquisition error. It is NOT an ADC, real held-input, input-noise, or kickback
qualification. The disconnected TG/reference fixture is retained unchanged.
Python3.6; default generate-only; native cards and raw waves remain VM-side.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import adc_comparator_burst_r5 as burst

r, a = burst.r, burst.a
NAME = 'adc_reset_clamp_r5_20261013'
SETTLED_GUARD = 2e-12


def candidates():
    base = copy.deepcopy(r.candidates()['in100_tail3'])
    result = {'base_pre05_eq024': base}
    for name, pre, eq in [('pre1_eq05', 1., .5), ('pre2_eq1', 2., 1.)]:
        widths = copy.deepcopy(base)
        widths.update(precharge=pre, equalizer=eq)
        result[name] = widths
    widths = copy.deepcopy(r.candidates()['in100_nregen'])
    widths.update(precharge=1., equalizer=.5)
    result['nregen_pre1_eq05'] = widths
    return result


def clamp_waves(cfg, tm):
    cm, lsb = cfg['common_mode_V'], cfg['fullscale_differential_Vpp']/128
    stop = a.T0+(cfg['cycles']+1)*tm['period_s']
    changes = [(a.T0+q*tm['period_s']+tm['launch_offset_s']-SETTLED_GUARD-a.EDGE/2,
                r.PATTERN[q % len(r.PATTERN)]*lsb) for q in range(cfg['cycles']+1)]
    return (a.pwl(cm+r.PATTERN[-1]*lsb/2, [(t, cm+x/2) for t, x in changes], stop),
            a.pwl(cm-r.PATTERN[-1]*lsb/2, [(t, cm-x/2) for t, x in changes], stop))


def make_deck(cfg, tm, widths, mos):
    lines = burst.make_deck(cfg, tm, 'sa', mos)
    original = r.sized_strongarm(r.candidates()['in100_tail3'], mos)
    blocks = [i for i in range(len(lines)) if lines[i:i+len(original)] == original]
    if len(blocks) != 1:
        raise ValueError('Cannot identify original comparator block uniquely')
    at = blocks[0]
    lines = lines[:at]+r.sized_strongarm(widths, mos)+lines[at+len(original):]
    p, n = clamp_waves(cfg, tm)
    out = ['// IDEAL INPUT CLAMP RESET DIAGNOSTIC; no real hold/load/noise qualification.']
    removed = []
    for line in lines:
        name = line.split()[0] if line else ''
        if name in ('VGIP', 'VGIN'):
            removed.append(name)
            continue
        if line.startswith('save '):
            terms = [x for x in line.split()[1:] if x not in ('VGIP:p', 'VGIN:p')]
            line = 'save '+' '.join(terms+['cg_p', 'cg_n', 'VCGP:p', 'VCGN:p'])
        out.append(line)
    if sorted(removed) != ['VGIN', 'VGIP']:
        raise ValueError('Comparator must be fully disconnected from old TG holds')
    at = next(i for i, line in enumerate(out) if line.startswith('saveOptions '))
    return out[:at]+['VCGP (cg_p 0) vsource type=pwl wave='+a.wave(p),
                    'VCGN (cg_n 0) vsource type=pwl wave='+a.wave(n)]+out[at:]


def analyze(raw, cfg, tm):
    t, v = raw.values[raw.sweep_names[0]], raw.values
    vdd, lsb = cfg['supply_V'], cfg['fullscale_differential_Vpp']/128
    rises = a.crossings(t, v['cmp'], vdd/2, True)
    falls = a.crossings(t, v['cmp'], vdd/2, False)
    differential = [p-n for p, n in zip(v['cg_p'], v['cg_n'])]
    rows = []
    for q in range(cfg['warmup_cycles'], cfg['cycles']):
        start = a.T0+q*tm['period_s']
        launch = a.near(rises, start+tm['launch_offset_s'])
        previous_reset = a.near(falls, start-tm['period_s']+tm['reset_offset_s'])
        reset = a.near(falls, start+tm['reset_offset_s'])
        next_launch = a.near(rises, launch+tm['period_s'])
        end, before = launch+tm['usable_evaluation_s'], launch-r.MARGIN
        if end > reset-a.EDGE/2-.05e-12:
            raise ValueError('Evaluation extends into reset')
        target = r.PATTERN[q % len(r.PATTERN)]
        measured = a.interpolate(t, differential, before)
        if abs(measured-target*lsb) > 1e-9:
            raise ValueError('Ideal comparator input differs from commanded value')
        sign = 1 if target > 0 else -1
        row = dict(cycle=q, source_LSB=target, previous_source_LSB=r.PATTERN[(q-1) % len(r.PATTERN)],
                   direct_input_prelaunch_V=measured, direct_input_error_V=measured-target*lsb,
                   actual_reset_low_midpoint_interval_s=launch-previous_reset,
                   prelaunch_P_minus_Q_V=a.interpolate(t, v['p'], before)-a.interpolate(t, v['q'], before),
                   prelaunch_X_minus_Y_V=a.interpolate(t, v['x'], before)-a.interpolate(t, v['y'], before),
                   prelaunch_internal_min_V=min(a.interpolate(t, v[k], before) for k in ('p', 'q', 'x', 'y')),
                   stable_resolution_s={}, endpoints={})
        for label, hp, lp in [('raw', 'y', 'x'), ('buffered', 'bx', 'by')]:
            hi, lo = (hp, lp) if sign > 0 else (lp, hp)
            valid = [r.classify(h, l, vdd) == 'correct' for h, l in zip(v[hi], v[lo])]
            stable = a.first_stable(t, valid, launch, end)
            if r.classify(a.interpolate(t, v[hi], end), a.interpolate(t, v[lo], end), vdd) != 'correct':
                stable = None
            row['stable_resolution_s'][label] = None if stable is None else stable-launch
            for ps in (25, 40, 48):
                at = launch+ps*1e-12
                h, l = a.interpolate(t, v[hi], at), a.interpolate(t, v[lo], at)
                row['endpoints'].setdefault(str(ps)+'ps', {})[label] = dict(classification=r.classify(h, l, vdd), signed_difference_V=h-l)
        for label, current, voltage in [('comparator', 'VA:p', None), ('buffer', 'VB:p', None), ('compare_clock', 'VCMP:p', 'cmp')]:
            vv = v[voltage] if voltage else [vdd]*len(t)
            power = [-x*y for x, y in zip(vv, v[current])]
            row[label+'_energy_J'] = a.integral(t, power, launch, next_launch)
        rows.append(row)
    summary = dict(decisions=len(rows), endpoints={}, real_held_input_verified=False,
                   complete_ADC_verified=False, stable_resolution_max_s={})
    for point in ('25ps', '40ps', '48ps'):
        summary['endpoints'][point] = {label: {state: sum(x['endpoints'][point][label]['classification'] == state for x in rows)
                                             for state in r.STATES} for label in ('raw', 'buffered')}
    for label in ('raw', 'buffered'):
        times = [x['stable_resolution_s'][label] for x in rows if x['stable_resolution_s'][label] is not None]
        summary['stable_resolution_max_s'][label] = max(times) if times else None
    for key in ('prelaunch_P_minus_Q_V', 'prelaunch_X_minus_Y_V', 'direct_input_error_V'):
        summary['max_abs_'+key] = max(abs(x[key]) for x in rows)
    summary['minimum_prelaunch_internal_V'] = min(x['prelaunch_internal_min_V'] for x in rows)
    for label in ('comparator', 'buffer', 'compare_clock'):
        energy = sum(x[label+'_energy_J'] for x in rows)/len(rows)
        summary[label+'_mean_energy_J'], summary[label+'_mean_power_W'] = energy, energy/tm['period_s']
    summary['all_32_ideal_clamp_decisions_correct_by48ps'] = summary['endpoints']['48ps']['buffered']['correct'] == len(rows) == 32
    return rows, summary


def self_test():
    def fake(n, d, g, s, bulk, **kw):
        return '%s (%s %s %s %s) TEST w=%.15g' % (n, d, g, s, bulk, kw['w'])
    cfg, tm = r.configuration(), burst.timing('e48_r20')
    for widths in candidates().values():
        deck = make_deck(cfg, tm, widths, fake)
        names = [x.split()[0] for x in deck if x and not x.startswith('//') and '(' in x and not x.startswith('save ')]
        assert len(names) == len(set(names))
        assert 'VGIP' not in names and 'VGIN' not in names
        assert 'VCGP' in names and 'VCGN' in names
        cg_connections = [x for x in deck if '(cg_p ' in x or ' cg_p ' in x or '(cg_n ' in x or ' cg_n ' in x]
        assert not any('(dhp cg_p)' in x or '(dhn cg_n)' in x for x in cg_connections)
    stop = a.T0+(cfg['cycles']+1)*tm['period_s']
    t = [i*.2e-12 for i in range(int(stop/.2e-12)+1)]
    v = {'time': t}
    for line in deck:
        if ' vsource type=pwl wave=' in line:
            node = line.split('(')[1].split()[0]
            numbers = [float(x) for x in line.split('wave=')[1].strip(' []').split()]
            xx, yy = numbers[::2], numbers[1::2]
            v[node] = [a.interpolate(xx, yy, at) for at in t]
    for node in ('p', 'q', 'x', 'y', 'bx', 'by', 'VA:p', 'VB:p', 'VCMP:p'):
        v[node] = [0.]*len(t)
    for i, at in enumerate(t):
        q = max(0, int((at-a.T0)/tm['period_s']))
        sign = 1 if r.PATTERN[q % len(r.PATTERN)] > 0 else -1
        v['p'][i] = v['q'][i] = v['x'][i] = v['y'][i] = .9
        # Large inputs decide by25ps; small inputs need35ps. This guards against
        # accidentally declaring all inputs resolved from only the large subset.
        delay = 20e-12 if abs(r.PATTERN[q % len(r.PATTERN)]) == 32 else 35e-12
        if at-(a.T0+q*tm['period_s']+tm['launch_offset_s']) >= delay and v['cmp'][i] > .45:
            hi, lo = (.9, 0.) if sign > 0 else (0., .9)
            v['y'][i], v['x'][i], v['bx'][i], v['by'][i] = hi, lo, hi, lo
    rows, summary = analyze(SimpleNamespace(sweep_names=['time'], values=v), cfg, tm)
    assert summary['endpoints']['25ps']['buffered']['correct'] == 8
    assert summary['endpoints']['40ps']['buffered']['correct'] == 32
    assert summary['all_32_ideal_clamp_decisions_correct_by48ps']
    print(json.dumps({'self_test': 'passed', 'cases': 4, 'simulator_executed': False}))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case', choices=sorted(candidates()))
    p.add_argument('--cards', type=Path, default=r.PROJECT/'configs/native_geometry_cards_r5.json')
    p.add_argument('--run', action='store_true')
    p.add_argument('--self-test', action='store_true')
    p.add_argument('--timeout', type=int, default=180)
    args = p.parse_args()
    if args.self_test:
        return self_test()
    if not args.case or not 10 <= args.timeout <= 600:
        p.error('Case required; timeout10..600')
    import native_geometry_r5 as geometry
    geometry.install(args.cards)
    cfg, tm, widths = r.configuration(), burst.timing('e48_r20'), candidates()[args.case]
    lines = make_deck(cfg, tm, widths, geometry.mos)
    deck = '\n'.join(lines)+'\n'
    directory = r.PROJECT/'runs'/NAME/args.case
    identity = dict(script_sha256=a.digest(__file__), burst_script_sha256=a.digest(burst.__file__),
                    comparator_script_sha256=a.digest(r.__file__), probe_helpers_sha256=a.digest(a.__file__),
                    geometry_helper_sha256=a.digest(geometry.__file__), native_cards_sha256=a.digest(args.cards),
                    deck_sha256=hashlib.sha256(deck.encode('utf-8')).hexdigest(), configuration=cfg, timing=tm,
                    geometry_widths_um=widths, input_pattern_LSB=r.PATTERN, source_finished_before_launch_s=SETTLED_GUARD)
    path = directory/'reset_clamp_r5_summary.json'
    if path.exists():
        prior = json.loads(path.read_text())
        if prior['identity'] != identity:
            raise ValueError('Existing case identity differs')
        if prior.get('status') == 'complete':
            if a.digest(directory/'bench.scs') != identity['deck_sha256'] or a.digest(a._raw_file(directory)) != prior['raw_sha256']:
                raise ValueError('Completed result provenance differs')
            print(json.dumps({'case': args.case, 'status': 'verified_existing_complete', 'summary': prior['summary']}), flush=True)
            return
    if (directory/'raw').exists():
        raise ValueError('Refusing to overwrite existing incomplete/unbound raw')
    if (directory/'bench.scs').exists() and a.digest(directory/'bench.scs') != identity['deck_sha256']:
        raise ValueError('Existing deck differs')
    directory.mkdir(parents=True, exist_ok=True)
    (directory/'bench.scs').write_text(deck)
    record = dict(schema_version=1, case=args.case, identity=identity, status='generated_only',
                  scope='Ideal zero-impedance comparator-input reset diagnostic only',
                  limitations=['Comparator gates disconnected from TG hold nodes and directly driven by idealPWLsources.',
                               'Input changes withinreset and finishes2psbeforecomparison; no finite DAC settling or driver impedance.',
                               'Unloaded prior TG/reference fixtures remain electrically separate and are not ADC evidence.',
                               'No input-noise, actual held-input, kickback, ADC, reference, controller, mismatch or PEX qualification.',
                               'Current histories and power are conditional on ideal source clamps and idealclockdrive.',
                               'A correct result here must subsequently survive a real held/CDAC input interface.',
                               'TT25C0.9V,32deterministicstressdecisions; does not prove BER or ENOB.'])
    if args.run:
        record['run_status'] = a.b.run(directory, lines, timeout=args.timeout)
        if record['run_status']['exit_code'] != 0:
            record['status'] = 'simulation_failed'
            a.atomic_json(path, record)
            raise RuntimeError('Ideal-clamp reset diagnostic failed')
        raw = a.parse_file(a._raw_file(directory))
        rows, summary = analyze(raw, cfg, tm)
        record.update(status='complete', raw_sha256=raw.sha256, cycles=rows, summary=summary)
    a.atomic_json(path, record)
    print(json.dumps({'case': args.case, 'status': record['status'], 'summary': record.get('summary')}), flush=True)


if __name__ == '__main__':
    main()
