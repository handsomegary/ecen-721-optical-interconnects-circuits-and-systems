#!/usr/bin/env python3
"""Analytic lumped LC delay-cell seed. Python standard library only.

Per leg: four identical series L/2, shunt C, series L/2 sections. Each
center C is (12+5*code) fF for unary code 0..15. The load is an ideal shunt
capacitor and the input has the declared Thevenin source resistance. This
does not model MOS switches, PDK passives, parasitic couplings, or a real RX.
"""
import argparse
import cmath
import json
import math
from pathlib import Path


UI_S = 1 / 112e9
TARGET_PS = UI_S * 0.5e12
SECTION_L_H = 65e-12
SECTIONS = 4
STEP_GHZ = 0.25
FREQUENCIES_GHZ = [k * STEP_GHZ for k in range(241)]
PROBES_GHZ = (1., 7., 14., 28., 42., 56.)
COMPARISON_BAND_GHZ = (14., 56.)
DEMO_CODES = (0, 7, 15)


def multiply(m1, m2):
    a, b, c, d = m1
    e, f, g, h = m2
    return a*e+b*g, a*f+b*h, c*e+d*g, c*f+d*h


def transfer(freq_hz, code, source_ohm, load_f, series_ohm_per_section=0.):
    """Return Vout/Vopen-circuit-source, Vout/Vin and loaded input admittance."""
    if type(code) is not int or not 0 <= code <= 15:
        raise ValueError('code must be a unary count in 0..15')
    values = (freq_hz, source_ohm, load_f, series_ohm_per_section)
    if not all(math.isfinite(v) and v >= 0 for v in values):
        raise ValueError('nonnegative finite frequency, impedances and load required')
    jw = 2j * math.pi * freq_hz
    z_half = (series_ohm_per_section + jw * SECTION_L_H) / 2
    y_center = jw * (12 + 5*code) * 1e-15
    half = (1, z_half, 0, 1)
    section = multiply(multiply(half, (1, 0, y_center, 1)), half)
    chain = (1, 0, 0, 1)
    for _ in range(SECTIONS):
        chain = multiply(chain, section)
    a, b, c, d = chain
    yl = jw * load_f
    vi_per_vo = a+b*yl
    ii_per_vo = c+d*yl
    return 1/(vi_per_vo+source_ohm*ii_per_vo), 1/vi_per_vo, ii_per_vo/vi_per_vo


def unwrap(values):
    out = []
    for value in values:
        phase = cmath.phase(value)
        if out:
            phase = out[-1] + (phase-out[-1]+math.pi) % (2*math.pi) - math.pi
        out.append(phase)
    return out


def phase_delay_ps(phase, frequency_ghz):
    return -phase / (2*math.pi*frequency_ghz) * 1e3


def group_delay_ps(phase, index):
    return -(phase[index+1]-phase[index-1]) / (2*math.pi*2*STEP_GHZ) * 1e3


def db(value):
    return 20*math.log10(abs(value))


def vector(value):
    return {'real': value.real, 'imag': value.imag, 'magnitude': abs(value)}


def fit_delay_ps(phases, indices):
    """Uniform frequency least-squares pure-delay fit, zero phase intercept."""
    frequencies = [FREQUENCIES_GHZ[i] for i in indices]
    slope = sum(f*phases[i] for f,i in zip(frequencies,indices)) / sum(f*f for f in frequencies)
    return -slope * 1e3 / (2*math.pi)


def maximum_error_ps(phases, indices, desired_delay_ps):
    return max(abs(phase_delay_ps(phases[i], FREQUENCIES_GHZ[i])-desired_delay_ps) for i in indices)


def configuration(source_ohm, load_fF, loss_ohm):
    sweeps = [[transfer(f*1e9,k,source_ohm,load_fF*1e-15,loss_ohm)
               for f in FREQUENCIES_GHZ] for k in range(16)]
    h = [[x[0] for x in sweep] for sweep in sweeps]
    phases = [unwrap(row) for row in h]
    indices = [i for i,f in enumerate(FREQUENCIES_GHZ) if COMPARISON_BAND_GHZ[0] <= f <= COMPARISON_BAND_GHZ[1]]
    i56 = int(56/STEP_GHZ)
    codes = {}
    for code in DEMO_CODES:
        samples = []
        for f in PROBES_GHZ:
            i = int(f/STEP_GHZ)
            h_src, h_pin, yin = sweeps[code][i]
            samples.append({'frequency_GHz': f, 'H_Vout_per_Vsource': vector(h_src),
                            'gain_Vout_per_Vsource_dB': db(h_src), 'H_Vout_per_Vin': vector(h_pin),
                            'input_admittance_S': vector(yin), 'phase_delay_ps': phase_delay_ps(phases[code][i], f),
                            'group_delay_ps': group_delay_ps(phases[code],i)})
        codes[str(code)] = {'center_C_fF': 12+5*code, 'frequency_samples': samples,
                            'band_gain_min_dB': min(db(h[code][i]) for i in indices),
                            'band_gain_max_dB': max(db(h[code][i]) for i in indices)}

    matched_center = h[7]
    center_phase = phases[7]
    reference_common_ps = fit_delay_ps(center_phase,indices)
    pairs = []
    for code_p in range(16):
        code_n = 15-code_p
        relative_phase = [a-b for a,b in zip(phases[code_p], phases[code_n])]
        mean_phase_error = [(a+b)/2-c for a,b,c in zip(phases[code_p],phases[code_n],center_phase)]
        effective = fit_delay_ps(relative_phase,indices)
        residual = [phase_delay_ps(relative_phase[i],FREQUENCIES_GHZ[i]) for i in indices]
        hp, hn = h[code_p][i56], h[code_n][i56]
        hdd = (hp+hn)/2
        hdc = hp-hn
        pairs.append({'code_p': code_p, 'code_n': code_n,
                      'differential_delay_ps_at_56GHz': phase_delay_ps(relative_phase[i56],56),
                      'differential_group_delay_ps_at_56GHz': group_delay_ps(relative_phase,i56),
                      'effective_broadband_differential_delay_ps': effective,
                      'broadband_differential_phase_delay_minmax_ps': [min(residual),max(residual)],
                      'broadband_delay_ripple_about_fit_max_ps': maximum_error_ps(relative_phase,indices,effective),
                      'max_band_mean_delay_change_vs_equal_code_7_ps': maximum_error_ps(mean_phase_error,indices,0),
                      'mean_delay_change_vs_equal_code_7_ps_at_56GHz': phase_delay_ps(mean_phase_error[i56],56),
                      'Hdd_56GHz': vector(hdd), 'Hdc_56GHz': vector(hdc),
                      'Hdd_56GHz_vs_equal_code_7_dB': db(hdd/matched_center[i56]),
                      'Hdc_56GHz_magnitude_over_equal_code_7_Hdd': abs(hdc/matched_center[i56]),
                      'branch_gain_mismatch_56GHz_dB_P_minus_N': db(hp/hn),
                      'P_phase_delay_ps_at_56GHz': phase_delay_ps(phases[code_p][i56],56),
                      'N_phase_delay_ps_at_56GHz': phase_delay_ps(phases[code_n][i56],56)})

    # Independently selectable two-leg codes can represent zero exactly. All
    # 16x16 pairs are compared solely as known-target design references.
    matched_target = {}
    for target in (-TARGET_PS, 0., TARGET_PS):
        all_pairs = []
        for p in range(16):
            for n in range(16):
                relative_phase = [a-b for a,b in zip(phases[p],phases[n])]
                error = maximum_error_ps(relative_phase,indices,target)
                common_error = [(a+b)/2-c for a,b,c in zip(phases[p],phases[n],center_phase)]
                all_pairs.append((error,maximum_error_ps(common_error,indices,0),p,n,fit_delay_ps(relative_phase,indices)))
        error, common_error, p, n, delay = min(all_pairs)
        ideal_factor = math.cos(math.pi*56e9*target*1e-12)
        matched_target[str(target)] = {'ideal_known_target_ps': target, 'minimax_pair_P_N': [p,n],
            'pair_effective_broadband_delay_ps': delay, 'worst_band_residual_from_ideal_ps': error,
            'pair_worst_band_mean_delay_change_vs_equal_code_7_ps': common_error,
            'ideal_Hdd_56GHz_relative_to_zero_skew_dB': db(ideal_factor),
            'ideal_Hdc_56GHz_magnitude_relative_to_zero_skew': 2*abs(math.sin(math.pi*56e9*target*1e-12)),
            'ideal_equal_common_delay_reference_ps': reference_common_ps,
            'ideal_common_delay_change_for_any_target_ps': 0.}
    assert abs(pairs[0]['effective_broadband_differential_delay_ps']+pairs[-1]['effective_broadband_differential_delay_ps']) < 1e-10
    fitted = [pair['effective_broadband_differential_delay_ps'] for pair in pairs]
    return {'source_ohm': source_ohm, 'load_fF_per_leg': load_fF, 'series_loss_ohm_per_section': loss_ohm,
            'series_loss_at_56GHz_nominal_Q': (2*math.pi*56e9*SECTION_L_H/loss_ohm) if loss_ohm else None,
            'demo_codes': codes, 'complementary_pairs': pairs,
            'complementary_effective_broadband_differential_delay_minmax_ps': [min(fitted),max(fitted)],
            'complementary_endpoint_pair_effective_delay_ps': [fitted[0],fitted[-1]],
            'complementary_effective_delay_steps_ps': [b-a for a,b in zip(fitted,fitted[1:])],
            'ideal_target_comparison': matched_target}


def calculate():
    cases = [configuration(rs,cl,loss) for loss in (0.,1.5) for rs in (5.,25.,50.) for cl in (20.,50.,100.)]
    return {'format': 'pam4_pnskew_four_section_lc_ladder_v1',
            'scope': 'Synthetic lumped analytical screening seed. No PDK, Spectre, circuit performance or acceptance result.',
            'units': {'frequency': 'GHz', 'delay': 'ps', 'inductance': 'pH', 'capacitance': 'fF', 'resistance': 'ohm'},
            'input': {'sections_per_leg': SECTIONS, 'L_per_section_pH': 65., 'C_fixed_per_section_fF': 12.,
                      'C_per_unary_unit_per_section_fF': 5., 'code_range_inclusive': [0,15],
                      'source_resistances_ohm': [5,25,50], 'load_capacitances_fF_per_leg': [20,50,100],
                      'series_loss_ohm_per_section': [0,1.5], 'UI_ps': UI_S*1e12, 'target_magnitude_ps': TARGET_PS,
                      'comparison_band_GHz': list(COMPARISON_BAND_GHZ), 'phase_unwrap_grid_step_GHz': STEP_GHZ},
            'definitions': {'transfer': 'Vout/Vopen-circuit-Thevenin-source and Vout/Vin actual ladder input pin. No terminating resistor at output.',
                'damping': 'Rs is Thevenin source series damping. Optional 1.5ohm constant ESR per full inductor split equally over L/2 arms. Ideal shunt caps and pure capacitive load; no implicit 50ohm shunt termination.',
                'delay': 'Phase delay = -unwrapped_phase/(2pi*f). Group delay = -dphase/domega, central difference. Effective broadband delay fits phase slope through origin over the declared 14–56GHz grid. Min/max and ripple retain dispersion.',
                'modal': 'P/N independent legs, Vd=Vp-Vn, Vcm=(Vp+Vn)/2. Hdd=(Hp+Hn)/2; Hdc=Hp-Hn. Equal-code 7/7 is reference. Complementary 0..15 pairs have fixed nominal total capacitance, which does not guarantee fixed common delay.',
                'ideal_comparison': 'Pure opposite delay offsets ±delta/2 about one constant reference mean; this comparison uses known design targets, not a physical detector or trim-code algorithm.',
                'power_noise': 'Passive synthetic response does not estimate physical power, switching/control/driver overhead, or noise.'},
            'cases': cases}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,help='New JSON file, otherwise print JSON to stdout')
    args = parser.parse_args()
    payload = json.dumps(calculate(),indent=2,allow_nan=False)+'\n'
    if args.output is None:
        print(payload,end='')
    else:
        with args.output.open('x',encoding='utf-8') as stream:
            stream.write(payload)


if __name__ == '__main__':
    main()
