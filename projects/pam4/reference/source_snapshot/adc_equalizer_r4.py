#!/usr/bin/env python3
"""Native-PMOS reset-equalizer diagnostic, generate-only unless --run.

Adds one W3um/L30nm native PMOS across P/Q and one across X/Y to the
unmodified direct-sampler StrongARM probe. Gate is cmp and bulk is avdd.
Four bounded cases: precharge 1x, tail 1x/4x, reset 42/70 ps.
No isolation, full ADC, noise, offset-calibration or PVT claim. Python 3.6.
"""
import argparse
import copy
import itertools
import json
from pathlib import Path

import adc_reset_sweep_r4 as r

a = r.a
PROJECT = r.PROJECT
NAME = 'adc_equalizer_r4_20261013'


def make_deck(cfg, tm):
    lines = r.make_deck(cfg, tm)
    addition = [
        '// Two native PMOS equalizers on only during comparator reset.',
        a.b.mos('MEQPQ', 'p', 'cmp', 'q', 'avdd', pmos=True, l=30e-9),
        a.b.mos('MEQXY', 'x', 'cmp', 'y', 'avdd', pmos=True, l=30e-9)]
    insert_at = next(i for i, line in enumerate(lines) if line.startswith('saveOptions '))
    return lines[:insert_at]+addition+lines[insert_at:]


def self_test():
    r.self_test()
    captured, previous = [], a.b.mos
    def capture(name, drain, gate, source, bulk, **kwargs):
        captured.append((name, drain, gate, source, bulk, kwargs))
        return '%s (%s %s %s %s) native_test_placeholder' % (name, drain, gate, source, bulk)
    cfg = dict(supply_V=.9, common_mode_V=.75686, fullscale_differential_Vpp=.1,
               temperature_C=25., cycles=20, warmup_cycles=4, maxstep_s=.1e-12,
               source_resistance_per_side_ohm=50., buffer_output_capacitance_F=1e-15,
               copies=dict(input=1, regen_n=1, regen_p=1, tail=1, precharge=1, buffer=1))
    try:
        a.b.mos = capture
        for tail, reset_ps in itertools.product((1, 4), (42, 70)):
            captured[:] = []
            cfg['copies']['tail'] = tail
            tm = r.timing(reset_ps)
            deck = make_deck(cfg, tm)
            ids = [line.split()[0] for line in deck if line and not line.startswith('//') and
                   '(' in line and not line.startswith('save ')]
            assert len(ids) == len(set(ids))
            equalizers = [device for device in captured if device[0] in ('MEQPQ', 'MEQXY')]
            assert len(equalizers) == 2
            assert equalizers[0][1:5] == ('p', 'cmp', 'q', 'avdd')
            assert equalizers[1][1:5] == ('x', 'cmp', 'y', 'avdd')
            assert all(x[5] == {'pmos': True, 'l': 30e-9} for x in equalizers)
            # Original voltage-source topology is unchanged: adding equalizers
            # does not add ideal sources or introduce an ideal-source loop.
            original = r.make_deck(cfg, tm)
            assert [x for x in deck if ' vsource ' in x] == [x for x in original if ' vsource ' in x]
            assert tm['track_overlaps_previous_evaluation_s'] == 0.
    finally:
        a.b.mos = previous
    print(json.dumps({'equalizer_self_test': 'passed', 'cases': 4, 'simulator_executed': False}))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', action='store_true')
    p.add_argument('--self-test', action='store_true')
    p.add_argument('--timeout', type=int, default=180)
    p.add_argument('--output-dir', type=Path, default=PROJECT/'runs'/NAME)
    p.add_argument('--baseline-summary', type=Path, default=PROJECT/'runs/adc_comparator_r3_tt/comparator_probe_summary.json')
    p.add_argument('--cards', type=Path, default=PROJECT/'configs/native_device_cards.json')
    args = p.parse_args()
    if args.self_test:
        return self_test()
    if args.timeout < 10 or args.timeout > 600:
        p.error('Timeout must be 10..600 seconds per case')
    output, allowed = args.output_dir.resolve(), (PROJECT/'runs').resolve()
    if allowed not in output.parents or output.name != NAME:
        p.error('Output must be the new '+NAME+' directory under project runs')
    original = json.loads(args.baseline_summary.read_text())
    cfg = copy.deepcopy(original['configuration'])
    cfg.update(cycles=20, warmup_cycles=4, noise_seed=None)
    cfg['copies']['precharge'] = 1
    a.validate_card_identity(args.cards)
    native = a.install_native_cards(args.cards)
    if original['native_cards']['native_cards_sha256'] != native['native_cards_sha256']:
        raise ValueError('Native cards differ from the original comparator probe')
    excursion = max(abs(x) for x in r.PATTERN)*cfg['fullscale_differential_Vpp']/256
    if not 0 < cfg['common_mode_V']-excursion < cfg['common_mode_V']+excursion < cfg['supply_V']:
        raise ValueError('Diagnostic input exceeds supplies')
    identity = {'script_sha256': a.digest(__file__), 'reset_sweep_script_sha256': a.digest(r.__file__),
                'probe_script_sha256': a.digest(a.__file__),
                'baseline_summary_sha256': a.digest(args.baseline_summary),
                'native_cards_sha256': native['native_cards_sha256'],
                'base_configuration': cfg, 'input_pattern_LSB': r.PATTERN,
                'evaluation_s': r.EVALUATION,
                'compare_high_midpoint_interval_s': r.HIGH_MIDPOINT,
                'equalizers': [{'name': 'MEQPQ', 'drain': 'p', 'gate': 'cmp', 'source': 'q', 'bulk': 'avdd'},
                               {'name': 'MEQXY', 'drain': 'x', 'gate': 'cmp', 'source': 'y', 'bulk': 'avdd'}],
                'equalizer_geometry': 'One native W3um/L30nm PMOS per pair, nf=multi=1'}
    output.mkdir(parents=True, exist_ok=True)
    identity_path = output/'equalizer_identity.json'
    if identity_path.exists():
        if json.loads(identity_path.read_text()) != identity:
            raise ValueError('Existing experiment identity differs; refusing mutation')
    else:
        a.atomic_json(identity_path, identity)
    result = {'schema_version': 1, 'scope': 'Two-PMOS StrongARM reset-equalizer diagnostic; direct sampler, not ADC',
              'status': 'running' if args.run else 'generating', 'identity': identity,
              'endpoint_note': 'Compare rising midpoint +80/+100/+120 ps; reset falling midpoint is +120.6 ps.',
              'assumptions': ['Native direct TG sampler has 5fF per side; no added input isolation.',
                              'Equalizer gate low during reset; body at avdd, source/drain connect internal pairs.',
                              '42/70ps reset intervals avoid overlap with the 35.714ps track and 2ps launch guard.',
                              'TT baseline, 1ps ideal-clock edges, deterministic inputs; noise/mismatch/PVT/PEX excluded.',
                              'Internal reset-residual threshold is diagnostic and not input-referred offset proof.',
                              'Capacitance and charge injection of both equalizers are included by native MOS cards.'],
              'cases': []}
    for tail, reset_ps in itertools.product((1, 4), (42, 70)):
        case = 'pre1_tail%d_reset%dps_eq1' % (tail, reset_ps)
        cc = copy.deepcopy(cfg)
        cc['copies'].update(precharge=1, tail=tail)
        tm = r.timing(reset_ps)
        lines = make_deck(cc, tm)
        deck = '\n'.join(lines)+'\n'
        deck_sha = r.sha(deck)
        directory = output/case
        directory.mkdir(exist_ok=True)
        deck_path, record_path = directory/'bench.scs', directory/'equalizer_case_summary.json'
        if deck_path.exists() and a.digest(deck_path) != deck_sha:
            raise ValueError('Existing case deck differs: '+case)
        if record_path.exists():
            prior = json.loads(record_path.read_text())
            if prior.get('raw_sha256') is not None:
                if prior['deck_sha256'] != deck_sha or prior['raw_sha256'] != a.digest(a._raw_file(directory)):
                    raise ValueError('Completed case provenance differs: '+case)
                result['cases'].append(prior)
                a.atomic_json(output/'equalizer_sweep_summary.json', result)
                print(json.dumps({'case': case, 'status': 'verified_existing_complete'}), flush=True)
                continue
        if (directory/'raw').exists():
            raise ValueError('Unbound raw results exist; refusing overwrite: '+case)
        deck_path.write_text(deck)
        record = {'case': case, 'precharge_copies': 1, 'tail_copies': tail,
                  'equalizer_PMOS_copies_per_pair': 1, 'timing': tm,
                  'deck_sha256': deck_sha, 'status': 'generated_only'}
        if args.run:
            record['run_status'] = a.b.run(directory, lines, timeout=args.timeout)
            if record['run_status']['exit_code'] != 0:
                record['status'] = 'simulation_failed'
                a.atomic_json(record_path, record)
                result['cases'].append(record)
                result['status'] = 'failed'
                a.atomic_json(output/'equalizer_sweep_summary.json', result)
                raise RuntimeError('Equalizer case failed: '+case)
            raw = a.parse_file(a._raw_file(directory))
            rows = r.analyze_values(raw.values[raw.sweep_names[0]], raw.values, cc, tm)
            record.update(status='complete', raw_sha256=raw.sha256, cycles=rows, summary=r.summarize(rows, tm))
        a.atomic_json(record_path, record)
        result['cases'].append(record)
        a.atomic_json(output/'equalizer_sweep_summary.json', result)
        print(json.dumps({'case': case, 'status': record['status'], 'summary': record.get('summary')}), flush=True)
    result['status'] = 'complete' if all(x['status'] == 'complete' for x in result['cases']) else 'generated_only'
    a.atomic_json(output/'equalizer_sweep_summary.json', result)


if __name__ == '__main__':
    main()
