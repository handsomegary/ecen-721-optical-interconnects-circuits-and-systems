#!/usr/bin/env python3
"""Bounded native CTLE second pass; never overwrites the main AC summary.

Run serially beside the PAM4 jobs. Sixty owned focusXX cases explore the
20--100 fF degeneration-capacitance gap and stage asymmetry at fixed geometry.
Only a separate ctle_ac_focus.json derived report is checkpointed.
"""

import argparse
import json
import time
from pathlib import Path

import optimize_ac as optimization
import pam4_integration as integration


PROJECT = Path('/path/to/local/cadence-home/Desktop/cadence_projects/project6_28nm')


def configs(project):
    baseline = integration.base_config(project)
    cases = []
    geometries = [(8, 8, 50, 50), (16, 16, 25, 25)]
    for nc, nv, rc, rv in geometries:
        for capacitance in [30e-15, 40e-15, 60e-15, 80e-15, 100e-15]:
            for resistance in [500, 2000, 8000, 64000]:
                config = dict(baseline, nc=nc, nv=nv, rc=rc, rv=rv,
                              cm=.7, vb=.58, rdeg=resistance, rdeg2=resistance,
                              cdeg=capacitance, cdeg2=capacitance)
                cases.append(('symmetric capacitance-gap screen', config))
    for nc, nv, rc, rv in geometries:
        for resistance, capacitance in [(64000, 100e-15), (2000, 40e-15)]:
            config = dict(baseline, nc=nc, nv=nv, rc=rc, rv=rv,
                          cm=.6, vb=.58, rdeg=resistance, rdeg2=resistance,
                          cdeg=capacitance, cdeg2=capacitance)
            cases.append(('old input-common-mode control', config))
    for nc, nv, rc, rv in geometries:
        for c1, c2 in [(20e-15, 40e-15), (40e-15, 20e-15)]:
            for resistance in [2000, 8000]:
                config = dict(baseline, nc=nc, nv=nv, rc=rc, rv=rv,
                              cm=.7, vb=.58, rdeg=resistance, rdeg2=resistance,
                              cdeg=c1, cdeg2=c2)
                cases.append(('unequal stage capacitance screen', config))
    for nc, nv, rc, rv in geometries:
        for capacitance in [30e-15, 40e-15, 60e-15, 100e-15]:
            config = dict(baseline, nc=nc, nv=nv, rc=rc, rv=rv,
                          cm=.7, vb=.58, rdeg=250, rdeg2=250,
                          cdeg=capacitance, cdeg2=capacitance)
            cases.append(('lower degeneration resistance with higher capacitance', config))
    assert len(cases) == 60
    assert len({json.dumps(config, sort_keys=True) for unused, config in cases}) == 60
    return [('focus%02d' % index, reason, config)
            for index, (reason, config) in enumerate(cases)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, default=PROJECT)
    parser.add_argument('--limit', type=int, help='optional bounded smoke subset')
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error('--limit must be positive')
    project = args.project
    native = integration.install_native_cards(project / 'configs/native_device_cards.json')
    cases = configs(project)
    if args.limit is not None:
        cases = cases[:args.limit]
    source = project / 'results/ctle_ac_optimization.json'
    previous = json.loads(source.read_text())
    references = [record for record in previous['results']
                  if record['id'] in ['baseline_native_r2', 'ac189']]
    destination = project / 'results/ctle_ac_focus.json'
    summary = {'schema_version': 1, 'status': 'running',
               'scope': 'serial native AC/DC/frozen-track-noise focused follow-up; not PAM4 selection',
               'conditions': previous['conditions'], 'native_metadata': native,
               'configuration_count': len(cases), 'worker_count': 1,
               'references': references, 'results': [], 'shortlist': [], 'errors': [],
               'main_summary_sha256_before': integration.file_hash(source),
               'native_cards_sha256_before': integration.file_hash(project / 'configs/native_device_cards.json')}
    started = time.time()
    for index, (identifier, reason, config) in enumerate(cases):
        try:
            record = optimization.run_case(project, identifier, config)
            record['focus_reason'] = reason
        except Exception as error:
            record = {'id': identifier, 'config': config, 'focus_reason': reason,
                      'error': repr(error)}
        summary['results'].append(record)
        if record.get('error') or record.get('analysis_error') or record.get('run_status', {}).get('exit_code') != 0:
            summary['errors'].append({'id': identifier, 'error': record.get('error', record.get('analysis_error', record.get('run_status')))})
        summary['shortlist'] = optimization.select_shortlist(summary['results'], 10)
        summary['preferred_top4_ids'] = [item['id'] for item in summary['shortlist'][:4]]
        summary['elapsed_s'] = time.time() - started
        optimization.atomic_json(destination, summary)
        if (index + 1) % 10 == 0 or index + 1 == len(cases):
            best = summary['shortlist'][0] if summary['shortlist'] else None
            print(json.dumps({'event': 'focused_AC_progress', 'completed': index + 1,
                              'total': len(cases), 'elapsed_s': summary['elapsed_s'],
                              'shortlist_ids': summary['preferred_top4_ids'],
                              'best_metrics': {key: best['metrics'][key] for key in [
                                  'combined_gain_56GHz_VV', 'combined_passband_ripple_dB',
                                  'sinusoidal_SNR_56GHz_proxy_dB', 'power_W']}
                              if best else None}), flush=True)
    summary['status'] = 'complete' if not summary['errors'] else 'complete_with_errors'
    summary['main_summary_sha256_after'] = integration.file_hash(source)
    summary['native_cards_sha256_after'] = integration.file_hash(project / 'configs/native_device_cards.json')
    summary['main_summary_unchanged'] = summary['main_summary_sha256_before'] == summary['main_summary_sha256_after']
    summary['native_cards_unchanged'] = summary['native_cards_sha256_before'] == summary['native_cards_sha256_after']
    summary['script_sha256'] = integration.file_hash(Path(__file__))
    summary['elapsed_s'] = time.time() - started
    optimization.atomic_json(destination, summary)
    print(json.dumps({'event': 'focused_AC_finished', 'status': summary['status'],
                      'completed': len(summary['results']), 'shortlist_ids': summary['preferred_top4_ids'],
                      'main_summary_unchanged': summary['main_summary_unchanged'],
                      'native_cards_unchanged': summary['native_cards_unchanged']}), flush=True)
    return 0 if summary['status'] == 'complete' else 1


if __name__ == '__main__':
    raise SystemExit(main())
