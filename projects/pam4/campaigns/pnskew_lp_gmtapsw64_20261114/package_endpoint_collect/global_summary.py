"""Collect and gate the LP14 global-map AC measurements."""
import argparse
from collections import defaultdict
import math
from pathlib import Path

from comp_measure import at
import drive_summary
import endpoint_summary
import lp_global as design
import lp_summary
import olympus_common as common
from select_global_codes import select
import summarize_acnext as modal
import weighted_delay


NYQUIST_HZ = 56e9
TARGET_PS = weighted_delay.ENDPOINT_PS
MAX_STEP_PS = .50
LOGICAL_CODES = tuple(range(81))
NEUTRAL = 40


def operating_point(case):
    return tuple(case[k] for k in ('process','temperature_C','vdd_V','source_R_ohm'))


def family(case):
    return operating_point(case),case['switch_mode'],case['tg_parallel'],case['match_load']


def controller_state(case):
    taps = tuple(case[k] for k in ('tap_a_p','tap_a_n','tap_b_p','tap_b_n'))
    return operating_point(case),case['count_b'],taps,case['match_load']


def at_56(frequency, rows, incident_skew_ps=0.):
    exact = drive_summary.matrix_at(frequency,rows,NYQUIST_HZ)
    adjusted = modal.cancel_input_skew([NYQUIST_HZ],[exact],incident_skew_ps)[0]
    dm,cm = modal.modes(adjusted)
    return {'Hdd_dB':modal.db(abs(dm)),'Hdc_complex':lp_summary.complex_list([cm])[0],
            'Hdc_over_abs_Hdd':abs(cm)/abs(dm) if abs(dm)>0 else None}


def subtract(a,b):
    return a-b if a is not None and b is not None else None


def same_grid(reference, frequency):
    return reference is not None and reference[1]['p']['frequency_Hz']==frequency


def fit(frequency, matrix, reference, track):
    result = weighted_delay.evaluate(frequency,drive_summary.column_projection(matrix),
                                     drive_summary.column_projection(reference),track)
    band = result['bands']['7_to_56_GHz']
    return {'delay_ps':band['tau_effective_ps'],'status':band['status'],
            'weighted_phase_rms_ps':band['weighted_phase_rms_ps'],
            'worst_phase_error_ps':band['worst_phase_error_ps'],
            'branch_null_frequencies_Hz':band['branch_null_frequencies_Hz'],
            'phase_delay_at_56GHz_ps':result['at_56_GHz']['differential_phase_delay_vs_bypass_ps']}


def tap_ratios(frequency,pair,case):
    result = {}
    for bank in 'AB':
        for leg,port in (('P','p'),('M','n')):
            traces = pair[port]['traces']
            tap = case[f'tap_{bank.lower()}_{port}']
            source,gate = f'GL{leg}T{tap:02d}',f'GMS{bank}{leg}G'
            if source in traces and gate in traces:
                a,b = [at(frequency,[complex(*v) for v in traces[n]],NYQUIST_HZ)
                       for n in (source,gate)]
                result[f'{bank}{leg}'] = drive_summary.ratio(b,a)
    return result


def measurement(fixture, r3, neutral, oracle):
    case,pair,matrix,op = fixture
    p = pair['p']
    fs = p['frequency_Hz']
    score = at_56(fs,matrix)
    h7 = modal.db(abs(lp_summary.hdd_at(fs,matrix,7e9)))
    power = endpoint_summary.power_mW(p)
    is_native = case['switch_mode']=='native'
    is_r3 = case['switch_mode']=='r3'
    budget = (10 if case['count_b'] in (0,8) else 14) if is_native else None
    r3_score = at_56(fs,r3[2]) if same_grid(r3,fs) else None
    added = power-endpoint_summary.power_mW(r3[1]['p']) if r3 and not is_r3 else None
    row = {'case':case,'output_56GHz':score,'tilt_56_over_7GHz_dB':subtract(score['Hdd_dB'],h7),
           'Hdd_vs_r3_56GHz_dB':subtract(score['Hdd_dB'],r3_score['Hdd_dB']) if r3_score else None,
           'Hdd_vs_same_state_oracle_56GHz_dB':None,'oracle_fixture_id':None,
           'within_2dB':None,'total_mW':power,'added_mW_vs_r3':added,'budget_mW':budget,
           'within_power_budget':added<=budget if None not in (added,budget) else None,
           'AFE_delay_vs_r3':None,'AFE_delay_vs_neutral':None,
           'known_endpoint_skew':None,'noise':p.get('noise'),
           'selected_tap_to_gate_56GHz_dB':tap_ratios(fs,pair,case) if not is_r3 else None,
           'XT2':{n:v for n,v in op.items() if n.startswith('XT2')}}
    if same_grid(oracle,fs):
        oracle_score = at_56(fs,oracle[2])
        gain = subtract(score['Hdd_dB'],oracle_score['Hdd_dB'])
        row.update(Hdd_vs_same_state_oracle_56GHz_dB=gain,
                   oracle_fixture_id=oracle[0]['fixture_id'],within_2dB=gain>=-2 if gain is not None else None)
    if not is_r3 and same_grid(r3,fs):
        track = modal.matrix(r3[1],('X_h0p','X_h0m'))
        row['AFE_delay_vs_r3'] = fit(fs,matrix,r3[2],track)
        if same_grid(neutral,fs):
            row['AFE_delay_vs_neutral'] = fit(fs,matrix,neutral[2],track)
    fitted = (row['AFE_delay_vs_neutral'] or {}).get('delay_ps')
    if fitted:
        incident = -math.copysign(TARGET_PS,fitted)
        corrected = at_56(fs,matrix,incident)
        uncorrected = at_56(fs,neutral[2],incident)
        ideal = at_56(fs,oracle[2],incident) if same_grid(oracle,fs) else None
        gain = subtract(corrected['Hdd_dB'],ideal['Hdd_dB']) if ideal else None
        row['known_endpoint_skew'] = {
            'injected_p_minus_n_ps':incident,'incremental_residual_ps':incident+fitted,
            'corrected':corrected,'uncorrected_same_hardware':uncorrected,
            'same_state_oracle':ideal,
            'Hdd_gain_vs_uncorrected_dB':subtract(corrected['Hdd_dB'],uncorrected['Hdd_dB']),
            'Hdd_vs_same_state_oracle_dB':gain,
            'within_2dB_vs_same_state_oracle':gain>=-2 if gain is not None else None,
            'Hdd_vs_zero_skew_r3_dB':subtract(corrected['Hdd_dB'],r3_score['Hdd_dB']) if r3_score else None,
        }
    if is_native and p.get('reference_current'):
        iref = p['reference_current']['recovered_A']
        legs = [sum(p['saved_mos_oppoint'][f'GMSH{leg}CS{i}']['ids'] for i in range(14)) for leg in 'PM']
        row.update(iref_uA=iref*1e6,leg_current_mA=[i*1e3 for i in legs],
                   servo_error_fraction=max(abs(i/(14*iref)-1) for i in legs) if iref>0 else None)
    return row


def status_counts(values):
    return {'pass':sum(v is True for v in values),'fail':sum(v is False for v in values),
            'unmeasured':sum(v is None for v in values)}


def map_report(cases, rows, selected_family):
    selected = [c for c in cases if c['group']=='map' and c['switch_mode']=='native'
                and family(c)==selected_family and c['drive']=='p']
    expected = {c['logical_code']:c for c in selected}
    common.need(sorted(expected)==list(LOGICAL_CODES) and len(selected)==len(expected),
                'Expected one native case pair for each decoder code')
    members = {row['case']['logical_code']:row for row in rows if row['case']['group']=='map'
               and family(row['case'])==selected_family}
    lengths = {k:row['AFE_delay_vs_neutral']['delay_ps'] for k,row in members.items()
               if row['AFE_delay_vs_neutral'] and row['AFE_delay_vs_neutral']['delay_ps'] is not None}
    steps = [{'from':i,'to':i+1,'step_ps':lengths[i+1]-lengths[i]}
             for i in LOGICAL_CODES[:-1] if i in lengths and i+1 in lengths]
    bad = [step for step in steps if not 0<step['step_ps']<=MAX_STEP_PS]
    complete = set(lengths)==set(LOGICAL_CODES)
    maximum_step = max((s['step_ps'] for s in steps),default=None)
    span = {str(i):lengths.get(i) for i in (LOGICAL_CODES[0],LOGICAL_CODES[-1])}
    range_pass = span['0']<=-TARGET_PS and span['80']>=TARGET_PS if None not in span.values() else None
    records = [members.get(k,{}) for k in LOGICAL_CODES]
    power = status_counts([r.get('within_power_budget') for r in records])
    gain = status_counts([r.get('within_2dB') for r in records])
    known = []
    for incident in (-TARGET_PS,TARGET_PS):
        sign = -1 if incident>0 else 1
        options = [i for i in lengths if lengths[i]*sign>0]
        nearest = min(options,key=lambda i:(abs(incident+lengths[i]),i),default=None)
        known.append({'injected_p_minus_n_ps':incident,'closest_measured_code':nearest,
                      'ac_known_target_only':True,'scores':members[nearest]['known_endpoint_skew']
                      if nearest is not None else None})

    center = members.get(NEUTRAL,{})
    return {'process':selected_family[0][0],'tg_parallel':selected_family[2],'match_load':selected_family[3],
            'complete':complete,'missing_codes':sorted(set(expected)-set(members)),
            'unresolved_delays':sorted(set(members)-set(lengths)),
            'code_delay_vs_neutral_ps':lengths,'adjacent_steps_ps':steps,'violating_steps':bad,
            'maximum_measured_positive_step_ps':maximum_step,
            'all_steps_strictly_increasing_and_within_0p50ps':not bad if complete else None,
            'endpoints_vs_neutral_ps':span,'covers_both_0p5_UI':range_pass,
            'neutral_delay_vs_r3':center.get('AFE_delay_vs_r3'),
            'neutral_output_56GHz':center.get('output_56GHz'),
            'power':power,'gain_vs_same_state_oracle':gain,'known_endpoint_candidates':known,
            'ac_map_pass':(not bad and range_pass is True and power['pass']==gain['pass']==len(LOGICAL_CODES))
            if complete and not power['unmeasured'] and not gain['unmeasured'] else None}


def selector_candidates(cases,rows,parallel,matched):
    candidates = {}
    selected = {(c['hardware_word'],c['process']):c for c in cases if c['group'] in ('map','alias')
                and c['switch_mode']=='native' and c['tg_parallel']==parallel and c['match_load']==matched
                and c['drive']=='p'}
    for (word,_),c in selected.items():
        candidates[word] = {'logical_code':c['logical_code'],'hardware_word':word,'metrics_per_corner':{}}
    for row in rows:
        case = row['case']
        if case['group'] not in ('map','alias') or case['switch_mode']!='native':
            continue
        word,corner = case['hardware_word'],case['process']
        source = selected.get((word,corner))
        if source is None or source['fixture_id']!=case['fixture_id']:
            continue
        gain,power = row['within_2dB'],row['within_power_budget']
        candidates[word]['metrics_per_corner'][corner] = {
            'delay_ps':(row['AFE_delay_vs_neutral'] or {}).get('delay_ps'),
            'neutral_relative_fit_ps':(row['AFE_delay_vs_neutral'] or {}).get('delay_ps'),
            'r3_relative_fit_ps':(row['AFE_delay_vs_r3'] or {}).get('delay_ps'),
            'gain_power_pass':gain and power if None not in (gain,power) else None,
        }
    return [candidates[k] for k in sorted(candidates)]


def pilot_reports(cases, rows):
    pilot_cases = defaultdict(set)
    for c in cases:
        if c['group']=='pilot' and c['switch_mode']=='native':
            pilot_cases[family(c)].add(c['logical_code'])
    pilot_rows = defaultdict(dict)
    for row in rows:
        c = row['case']
        if c['group']=='pilot' and c['switch_mode']=='native':
            pilot_rows[family(c)][c['logical_code']] = row
    reports = []
    for key,codes in sorted(pilot_cases.items()):
        measured = pilot_rows[key]
        values = [measured.get(k,{}) for k in sorted(codes)]
        center = measured.get(NEUTRAL,{})
        fitted = {k:r['AFE_delay_vs_neutral']['delay_ps'] for k,r in measured.items()
                  if r['AFE_delay_vs_neutral'] and r['AFE_delay_vs_neutral']['delay_ps'] is not None}
        gain = status_counts([r.get('within_2dB') for r in values])
        power = status_counts([r.get('within_power_budget') for r in values])
        span = fitted.get(0),fitted.get(80)
        reports.append({'process':key[0][0],'tg_parallel':key[2],'match_load':key[3],
                        'planned_codes':sorted(codes),'unmeasured_codes':sorted(codes-set(measured)),
                        'unresolved_delays':sorted(set(measured)-set(fitted)),
                        'gain_vs_same_state_oracle':gain,'power':power,'endpoint_span_vs_neutral_ps':span,
                        'covers_both_0p5_UI':span[0]<=-TARGET_PS and span[1]>=TARGET_PS if None not in span else None,
                        'neutral_delay_vs_r3':center.get('AFE_delay_vs_r3'),
                        'neutral_output_56GHz':center.get('output_56GHz')})
    return reports


def summarize(root):
    plan = common.read(design.PLAN)
    cases = plan['cases']
    evidence,missing,invalid = lp_summary.read_pairs(root,cases,design.PLAN,lambda c:c['fixture_id'])
    reference,neutral,oracle = {},{},{}
    for fixture in evidence.values():
        c = fixture[0]
        switch = c['switch_mode']
        if switch=='r3':
            reference[operating_point(c)] = fixture
            continue
        if c.get('logical_code')==NEUTRAL and c['group']!='alias':
            key = family(c)
            neutral[c['group'],key] = fixture
        if switch=='ideal':
            key = controller_state(c)
            if key not in oracle or c['group']=='map':
                oracle[key] = fixture

    rows = []
    for fixture in evidence.values():
        c = fixture[0]
        try:
            category = 'map' if c['group']=='alias' else c['group']
            center = neutral.get((category,family(c)))
            key = controller_state(c)
            rows.append(measurement(fixture,reference.get(operating_point(c)),center,
                                    oracle.get(key) if c['switch_mode']=='native' else None))
        except (KeyError,ValueError,TypeError,OverflowError) as error:
            invalid[c['fixture_id']] = str(error)

    families = {family(c) for c in cases if c['group']=='map' and c['switch_mode']=='native'}
    reports = [map_report(cases,rows,key) for key in sorted(families)]
    parallel,matched = plan['candidate_tg_parallel'],plan['candidate_match_load']
    selector_input = selector_candidates(cases,rows,parallel,matched)
    selection = select(selector_input)
    passed = [r['ac_map_pass'] for r in reports]
    unresolved = sorted({c['fixture_id'] for c in cases}-set(evidence))
    return {'format':'lp14_global_map_ac_summary_v1','map_reports':reports,'pilot_reports':pilot_reports(cases,rows),
            'rows':rows,
            'missing_cases':missing,'invalid_cases':invalid,'unresolved_fixtures':unresolved,
            'canonical_all_corners_ac_map_pass':all(p is True for p in passed) if passed and None not in passed else None,
            'selector_candidates':selector_input,'selector_result':selection,
            'selected_global_ac_map_verified':selection['status']=='verified_map',
            'dynamic_switching_verified':False,'FFE_SER':None}


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    common.write_new(args.output,summarize(args.run_root.resolve()))
