#!/usr/bin/env python3
"""Fit-free selector R/C sensitivity around the measured ACNEXT r3 load.

Only the compact ACNEXT archive is read. The active path has a resistor at
each end. The unused path stays present and couples through one capacitor at
each end. Optional shunt capacitance at each terminal of the two active
switches brackets gate/bulk loading. All parameters are lumped sensitivity
values, not extracted transistor parameters. No simulator or PDK is used.
"""
import argparse
import bisect
import cmath
import hashlib
import json
import math
from pathlib import Path
import tarfile


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARCHIVE = ROOT / 'pam4_pnskew_acnext_20261113_results/olympus_compact_acnext_tt0_13.tgz'
PREFIX = 'run/acnext_tt_p25_v090_'
SUFFIX = '_r25_t25_r3_'
RS_OHM, RT_OHM = 25., 25.
UNIT_L_H, UNIT_C_F, UNIT_R_OHM = 13e-12, 20.8e-15, .305
PROBES_HZ = (1e3, 1e9) + tuple(k*7e9 for k in range(1, 9))
RON_OHM = (0., 2., 5., 15., 50., 170.)
COFF_FF = (0., 1., 3., 10., 30.)
ON_SHUNT_FF = (0., 3.)


def multiply(first, second):
    a,b,c,d = first
    e,f,g,h = second
    return a*e+b*g, a*f+b*h, c*e+d*g, c*f+d*h


def inverse(matrix):
    a,b,c,d = matrix
    determinant = a*d-b*c
    if abs(determinant) < 1e-15:
        raise ValueError('Singular admittance/transfer matrix')
    return d/determinant, -b/determinant, -c/determinant, a/determinant


def series(impedance):
    return 1, impedance, 0, 1


def shunt(admittance):
    return 1, 0, admittance, 1


def line(frequency, count):
    jw = 2j*math.pi*frequency
    arm = series((UNIT_R_OHM+jw*UNIT_L_H)/2)
    cell = multiply(multiply(arm, shunt(jw*UNIT_C_F)), arm)
    chain = (1,0,0,1)
    for _ in range(count):
        chain = multiply(chain, cell)
    return chain


def port_admittance(chain):
    # Reciprocal two-port, both external currents defined into the route.
    a,b,_,d = chain
    if abs(b) < 1e-15:
        raise ValueError('Degenerate ideal short in route admittance')
    return d/b, -1/b, -1/b, a/b


def leg(frequency, count, dormant, ron, coff_fF, on_shunt_fF):
    jw = 2j*math.pi*frequency
    local_shunt = shunt(jw*on_shunt_fF*1e-15)
    active_switch = multiply(multiply(local_shunt, series(ron)), local_shunt)
    main = port_admittance(multiply(multiply(active_switch, line(frequency, count)), active_switch))
    if coff_fF == 0:
        return main
    off_switch = series(1/(jw*coff_fF*1e-15))
    leakage = port_admittance(multiply(multiply(off_switch, line(frequency, dormant)), off_switch))
    return tuple(a+b for a,b in zip(main, leakage))


def transfer(frequency, load, lengths, ron, coff, on_shunt):
    diagonals, drives = [], []
    for port, length in enumerate(lengths):
        dormant = 16 if length == 6 else 6
        a,b,c,d = leg(frequency, length, dormant, ron, coff, on_shunt)
        driver_term = 1+RS_OHM*a
        diagonals.append(load[port*3] + d - RS_OHM*c*b/driver_term)
        drives.append(-c/driver_term)
    matrix = inverse((diagonals[0],load[1],load[2],diagonals[1]))
    return tuple(v*drives[j % 2] for j,v in enumerate(matrix))


def at(report, field, frequency):
    grid = report['frequency_Hz']
    trace = report['traces'][field]
    index = bisect.bisect_left(grid,frequency)
    if index < len(grid) and grid[index] == frequency:
        return complex(*trace[index])
    if index == 0 or index == len(grid):
        raise ValueError('Probe lies outside measured bypass frequency grid')
    fraction = math.log(frequency/grid[index-1])/math.log(grid[index]/grid[index-1])
    return (1-fraction)*complex(*trace[index-1])+fraction*complex(*trace[index])


def extract_pair(archive, variant):
    result = []
    for drive in 'pn':
        name = PREFIX+variant+SUFFIX+drive+'/measurements.json'
        member = archive.getmember(name)
        if not member.isfile() or not 0 < member.size < 10*1024**2:
            raise ValueError('Expected compact admitted measurements, not a raw file')
        with archive.extractfile(member) as stream:
            content = stream.read()
        report = json.loads(content)
        if report.get('measurement_complete') is not True or report['case_id'] != name.split('/')[1]:
            raise ValueError('Missing completed expected measurement')
        result.append((report, hashlib.sha256(content).hexdigest()))
    return result


def from_measurement(pair, frequency):
    p,n = pair[0][0],pair[1][0]
    return (at(p,'X_ip',frequency),at(n,'X_ip',frequency),
            at(p,'X_im',frequency),at(n,'X_im',frequency))


def hdd(h):
    return (h[0]-h[1]-h[2]+h[3])/2


def hdc(h):
    return h[0]+h[1]-h[2]-h[3]


def db(value):
    return 20*math.log10(abs(value))


def cpair(value):
    return [value.real,value.imag]


def metric(h, reference, ideal):
    return {'Hdd_vs_same_fixture_bypass_dB':db(hdd(h)/hdd(reference)),
            'Hdd_vs_ideal_selector_same_route_dB':db(hdd(h)/hdd(ideal)),
            'Hdc_magnitude_over_bypass_Hdd':abs(hdc(h)/hdd(reference)),
            'H_PP_PN_NP_NN':list(map(cpair,h))}


def delay_metrics(rows):
    frequency,phase = [],[]
    for f,h in rows:
        if f < 7e9:
            continue
        angle = cmath.phase(h[0]/h[3])
        if phase:
            angle = phase[-1]+math.remainder(angle-phase[-1],2*math.pi)
        phase.append(angle);frequency.append(f)
    delays = [-theta/(2*math.pi*f)*1e12 for f,theta in zip(frequency,phase)]
    fit = -sum(f*theta for f,theta in zip(frequency,phase))/sum(f*f for f in frequency)*1e12/(2*math.pi)
    return {'phase_delay_7_to_56GHz_minmax_ps':[min(delays),max(delays)],
            'uniform_probe_phase_fit_through_origin_ps':fit,
            'worst_probe_residual_to_signed_half_UI_ps':max(abs(delay-(1e12/224e9 if fit>=0 else -1e12/224e9))for delay in delays)}


def generate(archive_path):
    variants = {(6,6):'06_06',(16,6):'16_06'}
    with tarfile.open(archive_path,'r:gz') as archive:
        bypass = extract_pair(archive,'bypass_00_00')
        native = {lengths:extract_pair(archive,'ttd_switch_'+code) for lengths,code in variants.items()}
        direct = {lengths:extract_pair(archive,'ttd_selected_'+code) for lengths,code in variants.items()}
    references = {f:from_measurement(bypass,f) for f in PROBES_HZ}
    loads = {f:tuple((x-(i in (0,3)))/RS_OHM for i,x in enumerate(inverse(h))) for f,h in references.items()}
    sweep = []
    observed = []
    for lengths in variants:
        ideal = {f:transfer(f,loads[f],lengths,0,0,0) for f in PROBES_HZ}
        measured = []
        for f in PROBES_HZ:
            actual, control = from_measurement(native[lengths],f),from_measurement(direct[lengths],f)
            measured.append({'frequency_Hz':f,'native':metric(actual,references[f],control),
                             'native_ideal_selected':metric(control,references[f],control),
                             'analytic_ideal_selected':metric(ideal[f],references[f],control)})
        observed.append({'lengths_P_N':lengths,'measured':measured})
        for ron in RON_OHM:
            for coff in COFF_FF:
                for csh in ON_SHUNT_FF:
                    rows = [(f,transfer(f,loads[f],lengths,ron,coff,csh)) for f in PROBES_HZ]
                    by_frequency = {f:h for f,h in rows}
                    sweep.append({'lengths_P_N':lengths,'Ron_per_selected_switch_ohm':ron,
                        'Coff_between_terminals_per_off_switch_fF':coff,'selected_switch_shunt_fF_per_terminal':csh,
                        'at_1kHz':metric(by_frequency[1e3],references[1e3],ideal[1e3]),
                        'at_56GHz':metric(by_frequency[56e9],references[56e9],ideal[56e9]),
                        'delay':delay_metrics(rows) if lengths[0] != lengths[1] else None})
    entry = native[6,6][0][0]
    source_current = -at(entry,'XVin:p',1e3)
    vpin,vin,vline,vout = (at(entry,k,1e3) for k in ('ACNPI','ACNPFI','ACNPFO','X_ip'))
    series_budget = RS_OHM+RT_OHM+6*UNIT_R_OHM
    return {'format':'pam4_ttd_selector_fit_free_rc_sensitivity_v1',
        'source_archive_sha256':hashlib.sha256(archive_path.read_bytes()).hexdigest(),
        'source_bypass_measurement_sha256_P_N':[x[1] for x in bypass],
        'source_case_measurement_sha256_P_N':{f'{a}_{b}':{'native':[x[1] for x in native[a,b]],'ideal':[x[1] for x in direct[a,b]]} for a,b in variants},
        'fixture':{'source_ohm':RS_OHM,'output_termination_ohm':RT_OHM,'per_unit_L_pH':UNIT_L_H*1e12,
            'per_unit_C_fF':UNIT_C_F*1e15,'per_unit_ESR_ohm':UNIT_R_OHM,
            'load':'Full coupled ACNEXT TT direct bypass at each frequency. Y=(inverse(H_bypass)-I)/Rs already includes the 25ohm termination; no second Rt added.',
            'voltage_reference':'AC input is the open-circuit Thevenin source. Extra switch loss referenced to the same modeled selected route; fixture insertion also reported against native bypass.'},
        'measured_equal_length_LF_Ron_estimate':{'frequency_Hz':1e3,'entry_DeltaV_over_source_I_ohm':cpair((vpin-vin)/source_current),
            'exit_DeltaV_over_Rt_I_ohm':cpair((vline-vout)/(vout/RT_OHM)),
            'approximation':'At 1kHz shunt current is negligible; gate/body DC leakage is neglected. This is a small-signal local estimate, not an RF switch compact model.'},
        'series_loss_budget':{'extra_allowed_loss_dB':.67,'ideal_selected_06_06_56GHz_insertion_reported_dB':-.33,
            'approximate_total_loss_if_budget_met_dB':1.,
            'matched_low_frequency_formula':'Ron_each=(Rs+Rt+6*R_ESR)/2*(10^(extra_dB/20)-1)',
            'Ron_each_max_ohm':series_budget/2*(10**(.67/20)-1),
            'scope':'First-order analytical sizing check, proposed screening budget, pending user approval. RF parasitics further consume headroom.'},
        'limitations':['Scalar Ron, off feedthrough and shunts are independent synthetic sensitivities. No mapping from arbitrary width or bias to actual R/C is claimed.',
            'The model lacks bias variation, transistor transit time, gate rail impedance, distributed MOS parasitics, junction nonlinearity, passives EM, device noise and control power.',
            'Input source and termination match the native TT fixture; SS/FF, active buffer headroom and different termination are unmeasured here.',
            'Weighted pilot fit and frozen FFE are outside this model. Reported phase fit is uniformly weighted at eight probe frequencies.'],
        'measured_comparisons':observed,'sweep':sweep}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--acnext-archive',type=Path,default=DEFAULT_ARCHIVE)
    parser.add_argument('--output',type=Path)
    args = parser.parse_args()
    payload = json.dumps(generate(args.acnext_archive),indent=2,allow_nan=False)+'\n'
    if args.output is None:
        print(payload,end='')
    else:
        with args.output.open('x',encoding='utf-8') as output:
            output.write(payload)


if __name__ == '__main__':
    main()
