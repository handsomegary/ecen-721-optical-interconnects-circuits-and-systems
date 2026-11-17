#!/usr/bin/env python3
"""Constant-sum TTD interpolation and coherent echo sizing diagnostics."""

import argparse
import cmath
import hashlib
import json
import math
from pathlib import Path


OUTPUTS = Path(__file__).resolve().parents[1]
DEFAULT_REFERENCE = OUTPUTS / 'pam4_pnskew_gmselect_20261113_results/gmselect_summary.json'
ANCHORS = (6, 8, 10, 11, 12, 14, 16)
SUM_SECTIONS = 22
FREQUENCIES_GHZ = tuple(range(7, 57))
HALF_UI_PS = 500 / 112
UNIT_L_H = 13e-12
UNIT_C_F = 20.8e-15
UNIT_R_OHM = 0.305
NOMINAL_SECTION_PS = 0.5246


def routes(section_count):
    return section_count, SUM_SECTIONS - section_count


def blend(f_ghz, route_a, route_b, alpha, section_ps):
    omega = math.tau * f_ghz * 1e-3
    return ((1-alpha)*cmath.exp(-1j*omega*section_ps*route_a)
            + alpha*cmath.exp(-1j*omega*section_ps*route_b))


def entry(anchor_a, anchor_b, alpha, section_ps):
    p_a,n_a = routes(anchor_a)
    p_b,n_b = routes(anchor_b)
    differential = []
    common = []
    magnitude_db = []
    for f in FREQUENCIES_GHZ:
        p = blend(f,p_a,p_b,alpha,section_ps)
        n = blend(f,n_a,n_b,alpha,section_ps)
        omega = math.tau*f*1e-3
        expected_p = -omega*section_ps*((1-alpha)*p_a+alpha*p_b)
        expected_n = -omega*section_ps*((1-alpha)*n_a+alpha*n_b)
        phase_p = expected_p+math.remainder(cmath.phase(p)-expected_p,math.tau)
        phase_n = expected_n+math.remainder(cmath.phase(n)-expected_n,math.tau)
        differential.append((phase_n-phase_p)/omega)
        common.append(-(phase_p+phase_n)/(2*omega))
        magnitude_db.append(20*math.log10(min(abs(p),abs(n))))
    ideal = section_ps*((1-alpha)*(p_a-n_a)+alpha*(p_b-n_b))
    return {'route_a_PN': [p_a,n_a], 'route_b_PN': [p_b,n_b], 'alpha': alpha,
            'nominal_differential_delay_ps': ideal, 'differential_delay_56GHz_ps': differential[-1],
            'differential_phase_delay_span_ps': [min(differential),max(differential)],
            'worst_differential_deviation_from_linear_ps': max(abs(x-ideal) for x in differential),
            'common_phase_delay_span_ps': [min(common),max(common)],
            'minimum_normalized_leg_gain_dB': min(magnitude_db),
            'per_frequency_differential_phase_delay_ps': differential}


def codebook(section_ps, intervals):
    codes = []
    for a,b in zip(ANCHORS,ANCHORS[1:]):
        codes.extend(entry(a,b,k/intervals,section_ps) for k in range(intervals))
    codes.append(entry(ANCHORS[-2],ANCHORS[-1],1,section_ps))
    ideal_steps = [b['nominal_differential_delay_ps']-a['nominal_differential_delay_ps']
                   for a,b in zip(codes,codes[1:])]
    at56_steps = [b['differential_delay_56GHz_ps']-a['differential_delay_56GHz_ps']
                  for a,b in zip(codes,codes[1:])]
    dnl = [actual/ideal-1 for actual,ideal in zip(at56_steps,ideal_steps)]
    target_rows = []
    for target in (-HALF_UI_PS,0.0,HALF_UI_PS):
        selected = min(codes,key=lambda row:max(abs(x-target) for x in row['per_frequency_differential_phase_delay_ps']))
        target_rows.append({'known_correction_target_ps': target,
                            'route_a_PN': selected['route_a_PN'], 'route_b_PN': selected['route_b_PN'],
                            'alpha': selected['alpha'],
                            'worst_7_to_56_GHz_abs_error_ps': max(abs(x-target) for x in selected['per_frequency_differential_phase_delay_ps']),
                            'signed_error_56GHz_ps': selected['differential_delay_56GHz_ps']-target})
    return {'section_delay_ps': section_ps, 'weight_intervals_per_anchor_pair': intervals,
            'total_distinct_nominal_codes': len(codes),
            'phase_delay_range_56GHz_ps': [codes[0]['differential_delay_56GHz_ps'],codes[-1]['differential_delay_56GHz_ps']],
            'nominal_common_delay_ps': SUM_SECTIONS*section_ps/2,
            'nominal_step_range_ps': [min(ideal_steps),max(ideal_steps)],
            'actual_phase_step_56GHz_range_ps': [min(at56_steps),max(at56_steps)],
            'largest_ideal_nearest_code_quantization_ps': max(ideal_steps)/2,
            'largest_56GHz_nearest_code_quantization_ps': max(at56_steps)/2,
            'local_DNL_56GHz_range_LSB': [min(dnl),max(dnl)],
            'local_DNL_reference': 'Actual adjacent phase step over that interval nominal step minus one. Anchors with unequal segment lengths deliberately have different nominal steps.',
            'worst_interpolation_delay_dispersion_ps': max(max(c['per_frequency_differential_phase_delay_ps'])-min(c['per_frequency_differential_phase_delay_ps']) for c in codes),
            'worst_interpolation_non_linearity_ps': max(c['worst_differential_deviation_from_linear_ps'] for c in codes),
            'worst_normalized_leg_gain_dB': min(c['minimum_normalized_leg_gain_dB'] for c in codes),
            'known_target_offline_design_diagnostics': target_rows,
            'codebook': [{k:v for k,v in row.items() if k!='per_frequency_differential_phase_delay_ps'} for row in codes]}


def read_reference(path):
    payload = path.read_bytes()
    rows = json.loads(payload)['paired_rows']
    endpoints = {}
    for row in rows:
        if row['variant']=='dual_end' and row['active']=='a' and not row['dormant_only_probe']:
            delay = row['gate_delay']['bands']['7_to_56_GHz']['tau_effective_ps']
            endpoints[row['process']] = abs(delay)
    if set(endpoints)!= {'tt','ss','ff'}:
        raise ValueError('Expected measured TT, SS and FF ideal-launch dual endpoint rows')
    return {'file': path.name, 'sha256': hashlib.sha256(payload).hexdigest(),
            'measured_ideal_launch_dual_endpoint_effective_delay_ps': endpoints,
            'derived_per_section_delay_ps': {k:v/10 for k,v in endpoints.items()}}


def leakage_budget(differential_error_ps, separation_ps):
    per_leg = differential_error_ps/2
    upper56 = math.sin(math.tau*56e-3*per_leg)
    upper_low = per_leg/(separation_ps+per_leg)
    return {'allocated_differential_timing_error_ps': differential_error_ps,
            'assumed_echo_separation_ps': separation_ps,
            'max_coherent_echo_per_leg_at_56GHz': upper56,
            'max_coherent_echo_per_leg_at_56GHz_dBc': 20*math.log10(upper56),
            'max_coherent_echo_per_leg_for_low_frequency_group_delay': upper_low,
            'max_coherent_echo_per_leg_for_low_frequency_group_delay_dBc': 20*math.log10(upper_low)}


def generate(reference_path=None):
    reference = read_reference(reference_path) if reference_path is not None else None
    section_ps = reference['derived_per_section_delay_ps']['tt'] if reference else NOMINAL_SECTION_PS
    separate = (ANCHORS[-1]-ANCHORS[0])*section_ps
    adjacent = max(b-a for a,b in zip(ANCHORS,ANCHORS[1:]))*section_ps
    def center(separation_ps):
        x = math.pi*56e-3*separation_ps
        return {'path_delay_separation_ps': separation_ps, 'midweight_normalized_56GHz_gain_dB': 20*math.log10(math.cos(x)),
                'local_phase_to_weight_slope_vs_linear_at_midweight': math.tan(x)/x}
    return {'format': 'pam4_gm_fine_delay_model_v1', 'status': 'ANALYTIC_DESIGN_DIAGNOSTIC',
            'reference': reference, 'original_ladder': {'unit_L_H': UNIT_L_H,'unit_C_F': UNIT_C_F,'unit_R_ohm': UNIT_R_OHM,
                'low_frequency_nominal_Z_ohm': math.sqrt(UNIT_L_H/UNIT_C_F),
                'quarter_unit_L_H': UNIT_L_H/4,'quarter_unit_C_F': UNIT_C_F/4,'quarter_unit_R_ohm': UNIT_R_OHM/4,
                'quarter_unit_caveat': 'Scaled ideal element control only. Physical parasitics and Q need extraction.'},
            'constant_sum_section_count': SUM_SECTIONS, 'complementary_anchors_PN': [list(routes(k)) for k in ANCHORS],
            'half_UI_ps': HALF_UI_PS, 'frequency_grid_GHz': list(FREQUENCIES_GHZ),
            'interpolation_comparison': {'adjacent_anchor': center(adjacent), 'extreme_endpoints': center(separate)},
            '8_intervals': codebook(section_ps,8), '16_intervals': codebook(section_ps,16),
            'corner_endpoint_scaled_model': {k: {name:v for name,v in codebook(delay,8).items() if name!='codebook'}
                                           for k,delay in (reference['derived_per_section_delay_ps'].items() if reference else [])},
            'coherent_echo_budget_examples': {'long_dormant_route': [leakage_budget(e,separate) for e in (0.05,0.1,0.25)],
                                              'adjacent_dormant_route': [leakage_budget(e,adjacent) for e in (0.05,0.1,0.25)],
                                              'assumption': 'One echo per leg with fixed complex relative coefficient and pure excess delay. The bounds are sufficient worst-case across two legs. Frequency-dependent leakage requires measured complex reconstruction.'},
            'limitations': ['These are proposed engineering comparisons without native fine-code, device, driver, switch or SER results.',
                            'Each local adjacent fixture uses two gm banks. A global coarse tap selector must preserve inactive terminations and drain capacitance before a global codebook is claimed.',
                            'The calculation uses normalized complementary linear gm weights and equal path amplitudes. Physical gm allocation, leakage, cap loading, noise and bias startup need separate verification.',
                            'Known correction targets are offline diagnostics. Pilot code selection cannot read the injected skew.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference',type=Path,default=DEFAULT_REFERENCE if DEFAULT_REFERENCE.is_file() else None)
    parser.add_argument('--output',type=Path)
    args = parser.parse_args()
    rendered = json.dumps(generate(args.reference),indent=2,allow_nan=False)+'\n'
    if args.output:
        with args.output.open('x',encoding='utf-8') as stream:
            stream.write(rendered)
    else:
        print(rendered,end='')


if __name__=='__main__':
    main()
