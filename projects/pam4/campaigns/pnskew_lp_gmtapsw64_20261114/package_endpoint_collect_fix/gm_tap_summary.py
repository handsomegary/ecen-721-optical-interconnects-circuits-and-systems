"""Pair real P/N AC measurements and score the switch-free tap pilot."""
import argparse
from collections import defaultdict
from pathlib import Path

from comp_measure import at
import drive_summary
import endpoint_summary
import gm_summary
import gm_tap as design
import gm_tap_rf
from global_summary import at_56, fit, same_grid, subtract
import olympus_common as common
import summarize_acnext as modal
from weighted_delay import ENDPOINT_PS


PORTS = ('X_o_p','X_o_m')
TRACK = ('X_h0p','X_h0m')
LOSS_LIMIT_DB = 2.


def pvt(case):
    return tuple(case[k] for k in ('process','temperature_C','vdd_V','source_R_ohm'))


def family(case):
    return pvt(case),case['anchor_set'],tuple(case['anchors']),case['match_load']


def active_distribution(case):
    return tuple((a,w) for a,w in zip(case['anchors'],case['weights']) if w)


def collect(root, cases, plan):
    columns,missing,invalid = defaultdict(dict),[],{}
    for case in cases:
        fixture,side = case['fixture_id'],case['drive']
        common.need(side in ('p','n'),'Expected P/N drive column')
        try:
            record = gm_summary.read_case(root,case,plan)
        except FileNotFoundError:
            missing.append(case['case_id'])
        except (KeyError,ValueError,TypeError,OSError) as error:
            invalid[case['case_id']] = str(error)
        else:
            common.need(side not in columns[fixture],'Duplicate drive column for '+fixture)
            columns[fixture][side] = (case,record)

    paired = {}
    for key,items in columns.items():
        if set(items) != {'p','n'}:
            continue
        case,record = items['p']
        pair = {side:item[1] for side,item in items.items()}
        try:
            other = items['n'][0]
            common.need(all(case[k]==other[k] for k in case if k not in ('case_id','drive')),
                        'P/N circuit cases differ')
            bench = (root/case['case_id']/'bench.scs').read_text(encoding='ascii')
            margins = gm_tap_rf.headroom(case,record,bench)
            paired[key] = case,pair,modal.matrix(pair,PORTS),margins
        except (KeyError,ValueError,TypeError,OSError) as error:
            invalid[key] = str(error)
    return paired, missing, invalid


def stress(case):
    if 'injected_skew_ps' in case:
        return case['injected_skew_ps']
    point = case['point']
    return ENDPOINT_PS if point.startswith('neg_') else -ENDPOINT_PS if point.startswith('pos_') else (
        ENDPOINT_PS if point.endswith('_neg') else -ENDPOINT_PS if point.endswith('_pos') else 0.)


def band_minimum(fs, matrix, low=45e9, high=80e9):
    grid = sorted({f for f in fs if low<=f<=high} | ({low,high} if fs[0]<=low<high<=fs[-1] else set()))
    samples = [(abs(modal.modes(drive_summary.matrix_at(fs,matrix,f))[0]),f) for f in grid]
    if not samples:
        return None
    gain,frequency = min(samples)
    return {'frequency_Hz':frequency,'Hdd_dB':modal.db(gain)}


def read_at(fs, record, node):
    if node not in record['traces']:
        return None
    vals = [complex(*v) for v in record['traces'][node]]
    return at(fs,vals,56e9)


def vector(value):
    return [value.real,value.imag] if value is not None else None


def admittance(voltage, current):
    return vector(current/voltage) if current is not None and voltage is not None and abs(voltage)>1e-12 else None


def path_diagnostics(case, pair, fs):
    if case['variant_name'] != 'gmtap':
        return None
    arms = {}
    for leg,side in (('P','p'),('M','n')):
        record = pair[side]
        launch = read_at(fs,record,'GL'+leg+'I')
        launch_i = read_at(fs,record,'GL'+leg+'DRV:p')
        taps = {}
        for anchor,weight in zip(case['anchors'],case['weights']):
            loc = anchor if leg=='P' else 22-anchor
            tap = read_at(fs,record,f'GL{leg}T{loc:02d}')
            stem = f'GMSK{anchor:02d}{leg}'
            gate = read_at(fs,record,stem+'G')
            gate_current = read_at(fs,record,stem+'DRV:p')
            bank_rail = record.get('DC_current_A',{}).get(stem+'VT:p')
            taps[str(anchor)] = {'physical_tap':loc,'tail_units':weight,'tail_current_A':bank_rail,
                                 'tap_over_launch_dB':drive_summary.ratio(tap,launch)
                                 if tap is not None and launch is not None else None,
                                 'gate_over_tap_dB':drive_summary.ratio(gate,tap)
                                 if gate is not None and tap is not None else None,
                                 'gate_admittance_re_im_S':admittance(gate,gate_current),
                                 'drain_current_re_im_A_per_Vsource':vector(
                                     read_at(fs,record,stem+'VD:p'))}
        amps = [row['tail_current_A'] for row in taps.values()]
        arms[leg] = {'launch_admittance_re_im_S':admittance(launch,launch_i),
                     'total_tail_current_A':sum(amps) if None not in amps else None,
                     'banks':taps}
    return arms


def comparable_oracle(case, oracle):
    if oracle is None:
        return False
    ref = oracle[0]
    return (ref['group']=='oracle' and case['match_load']==ref['match_load']
            and pvt(case)==pvt(ref) and active_distribution(case)==active_distribution(ref)
            and set(ref['anchors']) <= set(case['anchors']))


def measure(fixture, baseline, center, oracle, fixed):
    case,pair,matrix,op = fixture
    fs = pair['p']['frequency_Hz']
    raw = at_56(fs,matrix)
    h7 = modal.db(abs(modal.modes(drive_summary.matrix_at(fs,matrix,7e9))[0]))
    total = endpoint_summary.power_mW(pair['p'])
    pilot = case['group']=='pilot'
    active = len(active_distribution(case)) if case['variant_name']=='gmtap' else None
    budget = (10 if active==1 else 14) if pilot else None
    added = total-endpoint_summary.power_mW(baseline[1]['p']) if baseline and pilot else None
    worst = min(((n,row['margin_V']) for n,row in op.items()),key=lambda item:item[1],default=None)
    row = {'case':case,'output_56GHz':raw,'tilt_56_over_7GHz_dB':subtract(raw['Hdd_dB'],h7),
           'minimum_Hdd_45_to_80GHz':band_minimum(fs,matrix),
           'total_mW':total,'active_bank_count':active,'added_mW_vs_r3':added,'budget_mW':budget,
           'within_power_budget':added<=budget if None not in (added,budget) else None,
           'noise':pair['p'].get('noise'),'r3_output_56GHz':None,'Hdd_vs_r3_56GHz_dB':None,
           'AFE_delay_vs_r3':None,'AFE_delay_vs_family_center':None,
           'same_route_population_oracle':None,'fixed_legacy_context':None,'known_endpoint_skew':None,
           'AC_path_diagnostics_56GHz':path_diagnostics(case,pair,fs),'worst_active_margin':worst,
           'XT2':{n:v for n,v in op.items() if n.startswith('XT2')}}
    if same_grid(baseline,fs):
        reference = at_56(fs,baseline[2])
        row.update(r3_output_56GHz=reference,Hdd_vs_r3_56GHz_dB=subtract(raw['Hdd_dB'],reference['Hdd_dB']))
        if case['group']!='baseline':
            track = modal.matrix(baseline[1],TRACK)
            row['AFE_delay_vs_r3'] = fit(fs,matrix,baseline[2],track)
            if same_grid(center,fs):
                row['AFE_delay_vs_family_center'] = fit(fs,matrix,center[2],track)
    p = pair['p']
    ref = p.get('reference_current')
    if ref is not None:
        iref = ref['recovered_A']
        devices = p['saved_mos_oppoint']
        legs = [sum(devices[f'GMSH{leg}CS{i}']['ids'] for i in range(14)) for leg in 'PM']
        row.update(iref_uA=iref*1e6,driver_leg_current_mA=[i*1e3 for i in legs],
                   driver_servo_error_fraction=max(abs(leg/(14*iref)-1) for leg in legs) if iref>0 else None)
    injected = stress(case)
    corrected = at_56(fs,matrix,injected)
    if comparable_oracle(case,oracle) and same_grid(oracle,fs):
        ideal = at_56(fs,oracle[2],injected)
        loss = subtract(corrected['Hdd_dB'],ideal['Hdd_dB'])
        row['same_route_population_oracle'] = {
            'reference_fixture_id':oracle[0]['fixture_id'],
            'injected_skew_ps':injected,'Hdd_drop_or_gain_dB':loss,
            'Hdd_drop_or_gain_zero_input_skew_dB':subtract(raw['Hdd_dB'],at_56(fs,oracle[2])['Hdd_dB']),
            'within_2dB_population_screen':loss>=-LOSS_LIMIT_DB if loss is not None else None,
            'reference_output_56GHz':ideal}
    if same_grid(fixed,fs):
        old = at_56(fs,fixed[2],injected)
        row['fixed_legacy_context'] = {
            'reference_fixture_id':fixed[0]['fixture_id'],'injected_skew_ps':injected,
            'Hdd_drop_or_gain_dB':subtract(corrected['Hdd_dB'],old['Hdd_dB']),
            'reference_output_56GHz':old}
    if injected and same_grid(center,fs):
        uncorrected = at_56(fs,center[2],injected)
        tau = (row['AFE_delay_vs_family_center'] or {}).get('delay_ps')
        row['known_endpoint_skew'] = {
            'injected_p_minus_n_ps':injected,'incremental_residual_ps':injected+tau if tau is not None else None,
            'corrected':corrected,'uncorrected_same_hardware':uncorrected,
            'Hdd_gain_vs_uncorrected_dB':subtract(corrected['Hdd_dB'],uncorrected['Hdd_dB'])}
    return row


def report_families(cases, rows):
    expected = defaultdict(set)
    actual = defaultdict(dict)
    for case in cases:
        if case['group']=='pilot':
            expected[family(case)].add(case['point'])
    for row in rows:
        case = row['case']
        if case['group']=='pilot':
            actual[family(case)][case['point']] = row
    reports = []
    for k,points in sorted(expected.items()):
        states = actual[k]
        fits = {name:(row['AFE_delay_vs_family_center'] or {}).get('delay_ps') for name,row in states.items()}
        neg,pos = fits.get('neg_end'),fits.get('pos_end')
        reports.append({'process':k[0][0],'anchor_set':k[1],'anchors':k[2],'match_load':k[3],
                        'planned_points':sorted(points),'missing_points':sorted(points-set(states)),
                        'delay_ps_by_point':fits,
                        'measured_extremes_cover_both_0p5_UI':neg<=-ENDPOINT_PS and pos>=ENDPOINT_PS
                        if None not in (neg,pos) else None,
                        'full_codebook_measured':False})
    return reports


def summarize(root):
    cases = common.read(design.PLAN)['cases']
    pairs,missing,invalid = collect(root,cases,design.PLAN)
    baselines = {pvt(x[0]):x for x in pairs.values() if x[0]['group']=='baseline'}
    centers = {family(x[0]):x for x in pairs.values() if x[0]['group']=='pilot' and x[0]['point']=='center'}
    fixed = {(pvt(x[0]),x[0]['point']):x for x in pairs.values() if x[0]['group']=='fixed'}
    rows = []
    for fixture in pairs.values():
        case = fixture[0]
        pilot = case['group']=='pilot'
        center = centers.get(family(case)) if pilot else None
        prior = (pairs.get(case['fixed_fixture_id']) if 'fixed_fixture_id' in case else
                 fixed.get((pvt(case),case['point']))) if pilot else None
        try:
            rows.append(measure(fixture,baselines.get(pvt(case)),center,
                                pairs.get(case.get('oracle_fixture_id')),prior))
        except (KeyError,ValueError,TypeError,OverflowError) as error:
            invalid[case['fixture_id']] = str(error)
    resolved = {row['case']['fixture_id'] for row in rows}
    return {'format':'pam4_lp14_gm_tap_pilot_summary_v1','rows':rows,'families':report_families(cases,rows),
            'missing_cases':missing,'invalid_cases':invalid,
            'unresolved_fixtures':sorted({c['fixture_id'] for c in cases}-resolved),
            'global_code_map_verified':False,'dynamic_switching_verified':False,'FFE_SER':None}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    common.write_new(args.output,summarize(args.run_root.resolve()))
