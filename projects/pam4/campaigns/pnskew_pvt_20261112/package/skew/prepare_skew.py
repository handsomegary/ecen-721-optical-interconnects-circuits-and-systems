#!/usr/bin/env python3
"""Prepare fixed-mean PN-skew cases with the original r5 stager. No simulation."""
import argparse
from difflib import unified_diff
import hashlib
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'native'))
import admit
import pn_stage

UI_S = 1.0 / 112e9
SKW = tuple(i / 8.0 for i in range(-4, 5))
SEEDS = tuple(range(1001, 1021))
NOISY_DELTAS = (-.5, 0., .5)
F_TONE = 56e9
TONE_LO = 0.8e-9
TONE_HI = TONE_LO + 21.0 / F_TONE


def signed_id(delta):
    return ('m' if delta < 0 else 'p' if delta > 0 else 'z') + '%03d' % round(abs(delta) * 1000)


def cases():
    rows = []
    for delta in SKW:
        rows.append(dict(case_id='quiet_' + signed_id(delta), kind='pam4_noiseless', phase='quiet_grid',
                         delta_ui=delta, noise_seed=None, runtime_budget='quiet'))
    for seed in SEEDS:
        for delta in NOISY_DELTAS:
            rows.append(dict(case_id='noise_' + signed_id(delta) + '_' + str(seed), kind='pam4_noise',
                             phase='paired_noise_endpoints', delta_ui=delta, noise_seed=seed,
                             runtime_budget='noise'))
    for mode in ('dm', 'cm'):
        for delta in NOISY_DELTAS:
            rows.append(dict(case_id='tone56_' + mode + '_' + signed_id(delta), kind='tone_' + mode,
                             phase='modal_probe_56GHz', delta_ui=delta, noise_seed=None,
                             frequency_Hz=F_TONE, tone_peak_V=.001, pwl_samples_per_tone_cycle=128,
                             measurement_window_s=[TONE_LO, TONE_HI], runtime_budget='tone'))
        rows.append(dict(case_id='tone56_' + mode + '_z000_half', kind='tone_' + mode,
                         phase='modal_probe_56GHz_linearity', delta_ui=0., noise_seed=None,
                         frequency_Hz=F_TONE, tone_peak_V=.0005, pwl_samples_per_tone_cycle=128,
                         measurement_window_s=[TONE_LO, TONE_HI], runtime_budget='tone'))
    return rows


def plan():
    rows = cases()
    return dict(format='pam4_pnskew_quantification_v1', case_count=len(rows), cases=rows,
                data_seed=2026101302, nominal_symbol_rate_Baud=112e9, UI_s=UI_S,
                phase_order=['quiet_grid','modal_probe_56GHz','paired_noise_endpoints'],
                injection=dict(reference='X_ip/X_im after synthetic two independent buffered RC channels',
                               implementation='Shift original TX PWL time axes only; exact time-shift commutation in admitted LTI channel',
                               noise_scope='Commutation is for the driven deterministic signal; source shifting does not delay resistor noise. Seed IDs pair conditions, not adaptive noise waveforms.',
                               P_delay='delta/2', N_delay='-delta/2', mean_delay_s=0., clock_shift_s=0.),
                ideal_oracle=dict(delta_ui=[-.5,.5], inverse='P=-delta/2 and N=+delta/2; apply net shifts algebraically before render',
                                  execution='Reuse exact same zero-skew deck and matched seed as mathematical upper-bound controls',
                                  mean_delay_s=0., additional_native_runs=0,
                                  physical_scope='Ideal noncausal inverse reference. Delay-only hardware introduces mean latency and must establish timing separately.'),
                source=dict(lineage='genuine r5_late1/cml2_late1 using r3 focus55 CTLE',
                            original_vm_deck_sha256=admit.DECK_SHA256,
                            frozen_detector_sha256=admit.FROZEN_SHA256,
                            scorer='Original r5 frozen primary and secondary detectors, no fitting, 2048 held symbols and 2032 FFE decisions'),
                resource_budgets={
                    'quiet':dict(historical_reference_minutes=55, planning_range_minutes=[45,90], requested_memory_GiB=6, requested_wall_minutes=180),
                    'noise':dict(historical_reference_minutes=70, planning_range_minutes=[55,110], requested_memory_GiB=6, requested_wall_minutes=180),
                    'tone':dict(historical_reference_minutes=None, planning_range_minutes=[45,110], requested_memory_GiB=6, requested_wall_minutes=180),
                },
                resource_scope='Provisional classic envelopes, not measured per-case RAM or a guarantee. The original transient stop is 29.414285714 ns for quiet, noise and tone. Recheck after the first new case of each class.',
                planned_execution=dict(solver='classic', requested_threads=1, CPUs_per_case=1, raw_max_bytes=512*1024**2),
                decisions=dict(ser_delta_absolute_min=.01, held_min_gap_fraction_loss=.10,
                               held_quantiles=[.05,.95], tone_linearity_complex_relative_max=.05,
                               noise_scope='Complete 20 matched seed IDs separately for each sign and point. Report range, mean, and all paired differences.'),
                scope='Development impact characterization of the unmodified frontend and numerical ADC/FFE; course and physical compensation qualification remain unmeasured.')


def check_channel(deck):
    """Prove the two visible channel paths are the admitted matched buffered RCs."""
    lines = deck.decode('utf-8').splitlines()
    statements = {tokens[0]: tokens for line in lines for tokens in [line.split()]
                  if tokens and not line[0].isspace() and not line.startswith('\\')}
    for suffix, rx_node in (('p','X_ip'), ('m','X_im')):
        table = {
            'CHR1': (['(PAM4_src_' + suffix, 'CH1_' + suffix + ')', 'resistor'], 'r='),
            'CHC1': (['(CH1_' + suffix, 'X_cm)', 'capacitor'], 'c='),
            'CHB1': (['(CHB_' + suffix, 'X_cm', 'CH1_' + suffix, 'X_cm)', 'vcvs'], 'gain='),
            'CHR2': (['(CHB_' + suffix, 'CH2_' + suffix + ')', 'resistor'], 'r='),
            'CHC2': (['(CH2_' + suffix, 'X_cm)', 'capacitor'], 'c='),
            'CHB2': (['(' + rx_node, 'X_cm', 'CH2_' + suffix, 'X_cm)', 'vcvs'], 'gain='),
        }
        for element, (ports, parameter) in table.items():
            name = element + suffix
            row = statements.get(name, [])
            if row[1:-1] != ports or not row[-1].startswith(parameter):
                raise ValueError('Original isolated buffered channel topology absent: ' + name)
            value = pn_stage.number(row[-1].split('=', 1)[1])
            pvalue = pn_stage.number(statements[element + 'p'][-1].split('=', 1)[1])
            if not value == pvalue or (parameter == 'gain=' and value != 1.) or value <= 0:
                raise ValueError('Channel must be matched and LTI: ' + name)


def deployment_baseline(source, admission, case):
    quiet = case['kind'] != 'pam4_noise'
    baseline_case = dict(case, delta_ui=0., kind='pam4_noiseless' if quiet else 'pam4_noise',
                         noise_seed=None if quiet else 173)
    baseline_case.pop('pvt_corner', None)
    data, _ = pn_stage.render_deck(source, admission, baseline_case)
    check_channel(data)
    return data


def write_diff(admission_path, run_dir):
    """Add a reviewable patch relative to the exact path-only parent deck."""
    admission = admit.read_admission(admission_path, verify=True)
    root = Path(run_dir).resolve()
    profile = pn_stage.verify_stage(admission_path, root)
    original = Path(admission['source_decks'][profile['source_kind']]['path']).read_bytes()
    baseline = deployment_baseline(original, admission, profile['case'])
    actual = (root / 'bench.scs').read_bytes()
    patch = ''.join(unified_diff(baseline.decode('utf-8').splitlines(keepends=True),
                                 actual.decode('utf-8').splitlines(keepends=True),
                                 'path_only_original.scs', 'bench.scs'))
    with (root/'stimulus_overlay.diff').open('x', encoding='utf-8', newline='') as f:
        f.write(patch)
    proof = dict(parent_baseline_sha256=hashlib.sha256(baseline).hexdigest(),
                 staged_deck_sha256=hashlib.sha256(actual).hexdigest(),
                 diff_sha256=admit.sha256_file(root/'stimulus_overlay.diff'),
                 literal_matched_independent_buffered_RC_topology_checked=True)
    admit.write_new_json(root/'stimulus_overlay.json', proof)
    return proof


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write-plan', type=Path)
    parser.add_argument('--admission', type=Path)
    parser.add_argument('--plan', type=Path, default=HERE/'skew_plan.json')
    parser.add_argument('--case-index', type=int)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.write_plan is not None:
        admit.write_new_json(args.write_plan, plan())
        return
    if args.admission is None or args.output is None or args.case_index is None:
        parser.error('require --admission, --case-index and --output')
    if admit.read_json(args.plan) != plan():
        raise ValueError('Plan differs from frozen original experiment')
    profile = pn_stage.prepare(args.admission, args.plan, args.case_index, args.output)
    print(json.dumps(dict(case=profile['case'], overlay=write_diff(args.admission,args.output)),indent=2))


if __name__ == '__main__':
    main()
