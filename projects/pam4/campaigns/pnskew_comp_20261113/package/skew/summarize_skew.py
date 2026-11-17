#!/usr/bin/env python3
"""Analyze compact r5 readbacks and report predeclared PN-skew effect sizes."""
import argparse
import cmath
import math
from pathlib import Path
import statistics

if __package__:
    from . import prepare_skew as S
else:
    import prepare_skew as S
import admit
import readback_guard as guard

POINTS = ('primary', 'secondary')
SCORE = 'ideal7bit_ADC_then_FFE'
# r5_original/frozen.json, SHA verified by admission and verify_delivery.py.
# These are the original raw_three_threshold polarities, fixed across all cases.
FROZEN_HELD_POLARITY = {'primary': 1, 'secondary': -1}


def db(ratio):
    return 20. * math.log10(ratio) if ratio > 0 else None


def model_56(delta_ui):
    # Vd = Vp - Vn and Vcm = (Vp + Vn)/2. Normalized to the unskewed
    # synthetic channel gain. This reference precedes the native AFE.
    angle = math.pi * S.F_TONE * delta_ui * S.UI_S
    c, s = math.cos(angle), math.sin(angle)
    return dict(delta_UI=delta_ui, delta_ps=delta_ui * S.UI_S * 1e12,
                Hdd=phasor(c), Hdc=phasor(-2j*s), Hcd=phasor(-.5j*s), Hcc=phasor(c),
                Nyquist_DM_gain_change_dB=db(abs(c)), scope='Ideal matched channel and pure PN delay only')


def phasor(value):
    return dict(real=value.real, imag=value.imag, magnitude=abs(value), phase_rad=cmath.phase(value))


def percentile(values, p):
    ordered = sorted(values)
    if not ordered:
        raise ValueError('Missing original PAM4 symbol class')
    index = p * (len(ordered) - 1)
    lo, hi = int(index), math.ceil(index)
    return ordered[lo] + (index - lo) * (ordered[hi] - ordered[lo])


def measured_points(path, result):
    if result['provenance']['frozen_r5_sha256'] != admit.FROZEN_SHA256:
        raise ValueError('Held eye statistics require original r5 frozen polarity')
    _, rows = guard.csv_readback(path, result['held_sample_csv'], guard.C.CSV_FIELDS)
    groups = {point: [[] for _ in range(4)] for point in POINTS}
    for row in rows:
        point = row[0]
        groups[point][int(row[8])].append(FROZEN_HELD_POLARITY[point] * float(row[7]))
    scored = {}
    for point, levels in groups.items():
        gaps = [percentile(levels[i+1], .05) - percentile(levels[i], .95) for i in range(3)]
        metrics = result['results'][point]['metrics']
        ffe = metrics[SCORE]
        raw_ffe = metrics['raw_held_FFE_before_ADC']
        scored[point] = dict(held_adjacent_p05_minus_p95_V=gaps, held_min_gap_V=min(gaps),
                             held_frozen_polarity=FROZEN_HELD_POLARITY[point],
                             scored_symbols=ffe['sample_count'], symbol_errors=ffe['symbol_errors'], SER=ffe['SER'],
                             gray_bit_errors=ffe['gray_bit_errors'], scored_bits=ffe['bit_count'], gray_BER=ffe['gray_BER'],
                             raw_FFE_symbol_errors=raw_ffe['symbol_errors'],
                             FFE_MSE_target_units_squared=ffe['prediction_RMSE_in_target_symbol_units']**2,
                             FFE_adjacent_p05_minus_p95_target_units=ffe['p05_p95_eye_gaps_in_target_symbol_units'],
                             quantizer_clipping_count=metrics['ADC_validation_input_clipped_count'],
                             quantizer_input_symbols=metrics['ADC_validation_input_count'])
    return scored


def effect(scored, baseline):
    ser_delta = (scored['symbol_errors'] - baseline['symbol_errors']) / baseline['scored_symbols']
    gap, reference = scored['held_min_gap_V'], baseline['held_min_gap_V']
    fraction = (reference - gap) / reference if reference > 0 else None
    gap_loss = fraction is not None and fraction >= .10
    return dict(delta_SER=ser_delta, delta_symbol_errors=scored['symbol_errors'] - baseline['symbol_errors'],
                delta_held_min_gap_V=gap-reference, held_min_gap_fraction_loss=fraction,
                held_margin_relative_evaluable=reference > 0,
                conspicuous_degradation=ser_delta >= .01 or gap_loss,
                delta_FFE_MSE_target_units_squared=scored['FFE_MSE_target_units_squared'] - baseline['FFE_MSE_target_units_squared'])


def onset(quiet):
    result = {}
    if 0. not in quiet:
        return {'status':'NO_ZERO_SKEW_CLASSIC_REFERENCE'}
    for sign in (-1,1):
        clear = 0.
        observed = None
        unevaluable_margin = set()
        for k in range(1,5):
            delta = sign*k/8.
            if delta not in quiet:
                status = 'MISSING_GRID_COVERAGE'
                break
            comparison = quiet[delta]['effect']
            unevaluable_margin.update(point for point in POINTS if not comparison[point]['held_margin_relative_evaluable'])
            if any(row['conspicuous_degradation'] for row in comparison.values()):
                observed = delta
                status = 'FIRST_OBSERVED_GRID_DEGRADATION'
                break
            clear = delta
        else:
            status = 'DEGRADATION_LABEL_NOT_OBSERVED_ON_THIS_GRID'
        result['negative' if sign < 0 else 'positive'] = dict(status=status, last_contiguous_clear_test_UI=clear,
            first_flagged_test_UI=observed, last_contiguous_clear_test_ps=clear*S.UI_S*1e12,
            first_flagged_test_ps=observed*S.UI_S*1e12 if observed is not None else None,
            sampled_grid_only=True, unavailable_relative_held_margin_points=sorted(unevaluable_margin),
            clear_scope='Below threshold among evaluable metrics on contiguous grid, no between-point guarantee')
    return result


def noise_summary(noise):
    summary = {}
    for delta in S.NOISY_DELTAS:
        row = {}
        for point in POINTS:
            paired = []
            for seed in S.SEEDS:
                if (delta, seed) not in noise or (0., seed) not in noise:
                    continue
                a, b = noise[(delta,seed)][point], noise[(0.,seed)][point]
                paired.append(dict(seed=seed, current=a, reference=b, effect=effect(a,b)))
            complete = len(paired) == len(S.SEEDS)
            out = dict(paired_count=len(paired), complete_20_seed_set=complete, per_seed=paired)
            if paired:
                symbol_errors = [p['current']['symbol_errors'] for p in paired]
                held_margins = [p['current']['held_min_gap_V'] for p in paired]
                out.update(observed_symbol_errors_range=[min(symbol_errors),max(symbol_errors)],
                           observed_held_min_gap_V_range=[min(held_margins),max(held_margins)],
                           mean_paired_delta_SER=statistics.mean(p['effect']['delta_SER'] for p in paired),
                           mean_paired_delta_held_min_gap_V=statistics.mean(p['effect']['delta_held_min_gap_V'] for p in paired),
                           seed_count_with_degradation_label=sum(p['effect']['conspicuous_degradation'] for p in paired))
            out['complete_mean_degradation_label'] = (out['mean_paired_delta_SER'] >= .01 or
                statistics.mean(p['current']['held_min_gap_V'] for p in paired) <=
                .9*statistics.mean(p['reference']['held_min_gap_V'] for p in paired) and
                statistics.mean(p['reference']['held_min_gap_V'] for p in paired)>0) if complete else None
            row[point] = out
        summary[str(delta)] = row
    return summary


def complex_field(row):
    return complex(row['real'],row['imag'])


def modal_report(results):
    # Fits normalized to the unskewed launched modal peak, not 50-ohm S-parameters.
    # Keep native input plane as a separate observation from output.
    modes = {}
    for mode, meaning in (('dm','Hdd'),('cm','Hdc')):
        zero = 'tone56_'+mode+'_z000'
        half = zero+'_half'
        linearity = {}
        if zero in results and half in results and 'tone56_dm_z000' in results:
            dd = results['tone56_dm_z000']['normalized_to_TX_modal_peak']
            for plane in ('input','output'):
                for modal in ('differential','common'):
                    key = 'AFE_'+plane+'_'+modal
                    a,b = (complex_field(results[i]['normalized_to_TX_modal_peak'][key]) for i in (zero,half))
                    floor = abs(complex_field(dd['AFE_'+plane+'_differential']))
                    norm = max(abs(a),floor)
                    error = abs(b-a)/norm if norm > 0 else None
                    linearity[key] = dict(normalized_complex_difference=error,
                                           diagnostic_within_5pct=error is not None and error <= .05,
                                           normalizer='max(magnitude of full-amplitude transfer, magnitude of zero-skew DM transfer at same plane)')
        qualified = bool(linearity) and all(entry['diagnostic_within_5pct'] for entry in linearity.values())
        cases = {}
        for delta in S.NOISY_DELTAS:
            cid = 'tone56_'+mode+'_'+S.signed_id(delta)
            if cid not in results:
                continue
            row = results[cid]
            pair = row['normalized_to_TX_modal_peak']
            aft = complex_field(pair['AFE_output_differential'])
            ref = complex_field(results[zero]['normalized_to_TX_modal_peak']['AFE_output_differential']) if zero in results else None
            dd0 = (complex_field(results['tone56_dm_z000']['normalized_to_TX_modal_peak']['AFE_output_differential'])
                   if 'tone56_dm_z000' in results else None)
            cases[str(delta)] = dict(modal_transfer=pair, fitted_residual_RMS_V={name:fit['residual_rms_V'] for name,fit in row['fits'].items()},
                Hdd_Nyquist_gain_change_vs_zero_dB=db(abs(aft)/abs(ref)) if mode=='dm' and ref else None,
                added_Hdc_complex_vs_zero=phasor(aft-ref) if mode=='cm' and ref is not None else None,
                added_Hdc_relative_to_zero_Hdd=abs(aft-ref)/abs(dd0) if mode=='cm' and ref is not None and dd0 else None)
        modes[meaning] = dict(zero_half_linearity=linearity, linearity_check_complete=bool(linearity),
                              linearity_diagnostic_within_5pct=qualified if linearity else None,
                              reported_as='56 GHz fundamental voltage transfer including synthetic channel and switched native loading',
                              cases=cases)
    return modes


def summary(plan_path, run_root, admission_path):
    run_root = Path(run_root).resolve()
    supplied = admit.read_json(plan_path)
    if supplied != S.plan():
        raise ValueError('Plan differs from predeclared skew campaign')
    digest = admit.sha256_file(plan_path)
    quiet, noise, tones, invalid, missing = {}, {}, {}, {}, []
    for case in supplied['cases']:
        cid = case['case_id']
        run = run_root/cid
        if not (run/'measurements.json').is_file():
            missing.append(cid)
            continue
        try:
            result = guard.verify_run(run, expected_case=case, expected_plan_sha256=digest, admission_path=admission_path)
            status = admit.read_json(run/'run_status.json')
            argv = status['actual_argv']
            options = {x.lower() for x in argv[1:]}
            if status['cpus_allocated'] != 1 or argv.count('+mt=1') != 1 or any(
                x.startswith(('+aps','++aps','+preset','+xps')) for x in options):
                raise ValueError('Expected the campaign classic one-CPU Spectre execution')
            delta = case['delta_ui']
            if case['kind'] == 'pam4_noiseless':
                quiet[delta] = dict(points=measured_points(run, result))
            elif case['kind'] == 'pam4_noise':
                noise[(delta,case['noise_seed'])] = measured_points(run,result)
            else:
                tones[cid] = result
        except (ValueError, KeyError, TypeError, OSError, OverflowError) as error:
            invalid[cid] = str(error)
    if 0. in quiet:
        baseline = quiet[0.]['points']
        for row in quiet.values():
            row['effect'] = {p: effect(row['points'][p],baseline[p]) for p in POINTS}
    bounds = onset(quiet)
    budget = dict(required_signed_differential_range_ps=[-.5*S.UI_S*1e12,.5*S.UI_S*1e12],
                  two_leg_complementary_excursion_ps=.25*S.UI_S*1e12,
                  grid_step_ps=.125*S.UI_S*1e12,
                  illustrative_CM_conversion_budget_ratio=.1,
                  model_CM_limited_residual_ps=math.asin(.05)/(math.pi*S.F_TONE)*1e12,
                  original_draft_target_residual_ps=.25, conditional_ideal_quantization_only_LSB_upper_ps=.5,
                  scope='Prior architecture proposal, independent matched-delay model only. Extra detector, PVT and nonuniform code error need separate margin. The measured grid cannot resolve 0.25 ps.')
    return dict(status='COMPLETE_DEVELOPMENT_CHARACTERIZATION' if not missing and not invalid else 'INCOMPLETE',
                plan_sha256=digest, missing_cases=missing, invalid_cases=invalid,
                quiet_grid={str(k):v for k,v in sorted(quiet.items())}, quiet_degradation_onset=bounds,
                noise_seed_pairs=noise_summary(noise), modal_56GHz=modal_report(tones),
                ideal_matched_56GHz_model=[model_56(x) for x in S.SKW],
                compensation_range_resolution=budget,
                ideal_corrected_endpoint_reference=dict(available=0. in quiet, quiet_zero_reference=quiet.get(0.),
                  noise_zero_reference='Same-seed baseline in noise_seed_pairs[0.0].',
                  scope='Exact mathematical inverse cancels both source offsets before render, so the original zero-skew deck is the identity control.'),
                finite_development_results_only=True, physical_PN_compensation_pass=None, course_pass=None)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan', type=Path, required=True)
    p.add_argument('--run-root', type=Path, required=True)
    p.add_argument('--admission', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    admit.write_new_json(a.output, summary(a.plan,a.run_root,a.admission))


if __name__ == '__main__':
    main()
