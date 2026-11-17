#!/usr/bin/env python3
"""Analytic fixed-length LC true-time-delay candidate with measured r3 AC load.

Only the existing AC60 bypass summary is read. The passive path selector is
ideal. Constant series ESR, optional AC termination, and linearized r3
admittance are fixture assumptions. No PDK data or simulator is used.
"""
import argparse
import cmath
import hashlib
import json
import math
from pathlib import Path


UI_PS = 1e12 / 112e9
TARGET_PS = UI_PS / 2
UNIT_DELAY_PS = .52
LENGTHS = (6, 16)
CORNER_R25 = ('tt_p25_v090_r25', 'ss_p85_v081_r25', 'ff_m40_v099_r25')
DEFAULT_INPUT = Path(__file__).resolve().parents[1] / 'pam4_pnskew_comp_20261113_results' / 'ac60_summary.json'


def mul(a, b):
    return (a[0]*b[0]+a[1]*b[2], a[0]*b[1]+a[1]*b[3],
            a[2]*b[0]+a[3]*b[2], a[2]*b[1]+a[3]*b[3])


def inv(a):
    det = a[0]*a[3]-a[1]*a[2]
    if abs(det) < 1e-15:
        raise ValueError('singular AC matrix')
    return (a[3]/det, -a[1]/det, -a[2]/det, a[0]/det)


def abcd(f, z0, n, r, *, delay_ps=UNIT_DELAY_PS):
    delay = delay_ps*1e-12
    w = 2*math.pi*f
    z = (r + 1j*w*z0*delay)/2
    y = 1j*w*delay/z0
    arm = (1, z, 0, 1)
    cell = mul(mul(arm, (1, 0, y, 1)), arm)
    result = (1, 0, 0, 1)
    for _ in range(n):
        result = mul(result, cell)
    return result


def modal(h):
    p, x, y, n = h
    return (p-x-y+n)/2, p+x-y-n, (p-x+y-n)/4, (p+x+y+n)/2


def bypass_matrix(row):
    keys = ('P_branch', 'cross_P_from_N', 'cross_N_from_P', 'N_branch')
    return tuple(complex(*row[k]) for k in keys)


def recover_admittance(h, source_resistance):
    """Vsource=(I+Rs*Y)*Vpin for identical known real series Rs."""
    return tuple((x - (1 if i in (0, 3) else 0))/source_resistance for i,x in enumerate(inv(h)))


def load_with_termination(y, resistance):
    g = 0 if resistance is None else 1/resistance
    return y[0]+g,y[1],y[2],y[3]+g


def through(f, z0, lengths, r, rs, load):
    rows = []
    for i,n in enumerate(lengths):
        a,b,c,d = abcd(f,z0,n,r)
        rows.extend((b+rs*d)*load[2*i+j]+((a+rs*c) if i==j else 0) for j in range(2))
    return inv(tuple(rows))


def unwrap(complex_values):
    phases = []
    for value in complex_values:
        phi = cmath.phase(value)
        if phases:
            phi = phases[-1]+math.remainder(phi-phases[-1], 2*math.pi)
        phases.append(phi)
    return phases


def db(a):
    return 20*math.log10(abs(a))


def cjson(z):
    return [z.real,z.imag]


def evaluate(points, z0, rs, termination, r, lengths):
    frequencies = [f for f,_ in points]
    hp, hn, transfer = [], [], []
    for f,y in points:
        load = load_with_termination(y, termination)
        h = through(f,z0,lengths,r,rs,load)
        # Evaluate equal paths and bypass with the identical source, termination and r3 load.
        equal = through(f,z0,(sum(lengths)//2,)*2,r,rs,load)
        bypass = through(f,z0,(0,0),r,rs,load)
        dd,dc,cd,cc = modal(h)
        dd_bypass,_,_,_ = modal(bypass)
        dd_equal,_,_,_ = modal(equal)
        # Ideal known input-skew control cancels the requested half-UI. It is
        # applied at the source plane, before the coupled physical-load model.
        target = TARGET_PS if lengths[0] > lengths[1] else -TARGET_PS
        tilt = cmath.exp(1j*math.pi*f*target*1e-12)
        corrected = (h[0]*tilt,h[1]/tilt,h[2]*tilt,h[3]/tilt)
        corrected_dd,corrected_dc,_,_ = modal(corrected)
        hp.append(h[0]);hn.append(h[3])
        transfer.append({'frequency_GHz':f*1e-9,'H_full_PP_PN_NP_NN':list(map(cjson,h)),
            'Hdd_absolute_dB':db(dd),'Hdd_vs_identical_termination_bypass_dB':db(dd/dd_bypass),
            'Hdd_vs_equal_length_dB':db(dd/dd_equal),'Hdc_over_equal_length_Hdd':abs(dc/dd_equal),
            'branch_gain_mismatch_P_minus_N_dB':db(h[0]/h[3]),
            'after_known_halfUI_input_skew_Hdd_vs_equal_length_dB':db(corrected_dd/dd_equal),
            'after_known_halfUI_input_skew_Hdc_over_equal_length_Hdd':abs(corrected_dc/dd_equal),
            'Hcd':cjson(cd),'Hcc':cjson(cc)})
    phase_p, phase_n = unwrap(hp), unwrap(hn)
    diff = [a-b for a,b in zip(phase_p,phase_n)]
    mean = [(a+b)/2 for a,b in zip(phase_p,phase_n)]
    for row,f,dp,mp in zip(transfer,frequencies,diff,mean):
        row['signed_differential_phase_delay_ps'] = -dp/(2*math.pi*f)*1e12
        row['mean_phase_delay_ps'] = -mp/(2*math.pi*f)*1e12
    local_group_delays = [-1e12*(b-a)/(2*math.pi*(g-f)) for a,b,f,g in zip(diff,diff[1:],frequencies,frequencies[1:])]
    phase_delay = [t['signed_differential_phase_delay_ps'] for t in transfer]
    fit = -sum(f*p for f,p in zip(frequencies,diff))/sum(f*f for f in frequencies)*1e12/(2*math.pi)
    return {'Z0_ohm':z0, 'source_ohm_per_leg':rs,'AC_termination_ohm_per_leg':termination,
            'series_ESR_per_T_cell_ohm':r,'cells_P_N':lengths,'transfer':transfer,
            'differential_phase_delay_minmax_ps':[min(phase_delay),max(phase_delay)],
            'differential_phase_slope_fit_through_origin_ps':fit,
            'differential_group_delay_midband_minmax_ps':[min(local_group_delays),max(local_group_delays)],
            'worst_probe_residual_to_ideal_halfUI_ps':max(abs(t-TARGET_PS) for t in phase_delay)}


def generate(raw):
    source = json.loads(raw)
    cases = {}
    for name in CORNER_R25:
        rows = source['AC'][name]['cases']['-1']['trim']
        if [r['frequency_Hz'] for r in rows] != [k*7e9 for k in range(1,9)]:
            raise ValueError('expected complete 7–56 GHz AC60 bypass phasors')
        points = [(row['frequency_Hz'],recover_admittance(bypass_matrix(row),25)) for row in rows]
        evaluations = []
        for z0 in (25.,50.):
            for rs in (0.,25.,z0) if z0 == 50 else (0.,25.):
                for termination in (None,z0):
                    for resistance in (0.,2*math.pi*56e9*z0*UNIT_DELAY_PS*1e-12/15.):
                        evaluations.append(evaluate(points,z0,rs,termination,resistance,LENGTHS[::-1]))
        cases[name] = {'recovered_r3_input_admittance_S':[{'frequency_GHz':f*1e-9,'Y_PP_PN_NP_NN':list(map(cjson,y))} for f,y in points],
                       'evaluations':evaluations}
    verify_r50 = []
    for row25,row50 in zip(source['AC'][CORNER_R25[0]]['cases']['-1']['trim'], source['AC']['tt_p25_v090_r50']['cases']['-1']['trim']):
        y25 = recover_admittance(bypass_matrix(row25),25)
        y50 = recover_admittance(bypass_matrix(row50),50)
        verify_r50.append(max(abs(a-b) for a,b in zip(y25,y50)))
    return {'format':'pn_trim_equal_impedance_TTD_reference_v1',
            'source_AC60_summary_sha256':hashlib.sha256(raw).hexdigest(),
            'scope':'Analytic T-section route reference with inferred r3 linear load. Selector, matching, RF passives, PDK, power and native performance remain unmeasured.',
            'units':{'frequency':'GHz','L':'pH','C':'fF','delay':'ps','resistance':'ohm','Y':'S'},
            'candidate':{'unit_delay_ps':UNIT_DELAY_PS,'fast_slow_cell_counts':list(LENGTHS),
                'fast_slow_nominal_delay_ps':[n*UNIT_DELAY_PS for n in LENGTHS],
                'nominal_difference_ps':(LENGTHS[1]-LENGTHS[0])*UNIT_DELAY_PS,
                'ideal_symmetric_mean_delay_ps':sum(LENGTHS)*UNIT_DELAY_PS/2,
                'ideal_halfUI_target_ps':TARGET_PS,'ideal_cell_cutoff_GHz':1/(math.pi*UNIT_DELAY_PS*1e-3),
                'unit_cells':[{'Z0_ohm':z,'section_L_pH':z*UNIT_DELAY_PS,'L_half_pH':z*UNIT_DELAY_PS/2,
                    'section_C_fF':1000*UNIT_DELAY_PS/z,'ESR_ohm_for_Q15_at_56GHz':2*math.pi*56e9*z*UNIT_DELAY_PS*1e-12/15} for z in (25.,50.)]},
            'assumptions':{'r3_load':'Y=(inv(H_bypass)-I)/25 from AC60 complex source-to-Xip/Xim matrices. Coupled, corner-specific r3 load at original DC point.',
                'r3_load_TT_recovery_crosscheck_vs_50ohm_max_complex_admittance_error_S':max(verify_r50),
                'termination':'Independent parallel AC-only termination at each ladder output. This ideal AC fixture omits bias isolation, termination noise, and drive/buffer power.',
                'selector':'Only one route per leg, with no disabled route loading and no switch loss, on resistance, charge injection or routing parasitics.',
                'ESR':'Uniform constant series resistance, either zero or equivalent inductor Q=15 at 56 GHz. Capacitors ideal.',
                'comparison':'P uses 16 cells, N uses 6. Swapping restores opposite differential delay for symmetric loads. Known half-UI input skew is an ideal sign-opposite control only.',
                'delay':'Quoted fitted delay uses unwrapped diagonal phase ratio with equal weights over measured 7,14,...,56GHz. Group delay is finite difference between adjacent probes. These are voltage-plane diagnostics; PAM4 decisions need end-to-end transient confirmation.',
                'baseline':'Hdd ratios compare same source resistance and termination. Absolute Hdd includes that fixture loss.'},
            'cases':cases}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ac60-summary',type=Path,default=DEFAULT_INPUT)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    content=json.dumps(generate(args.ac60_summary.read_bytes()),indent=2,allow_nan=False)+'\n'
    if args.output is None:
        print(content,end='')
    else:
        with args.output.open('x',encoding='utf-8') as handle:
            handle.write(content)


if __name__ == '__main__':
    main()
