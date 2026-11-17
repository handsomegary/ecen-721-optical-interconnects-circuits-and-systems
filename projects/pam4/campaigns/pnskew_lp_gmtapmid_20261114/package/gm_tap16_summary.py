"""Score coarse3 half-tail AC evidence with the weighted-delay convention."""
import argparse
from collections import defaultdict
import math
from pathlib import Path

import gm_summary
import gm_tap_rf
import gm_tap_summary as prior
import olympus_common as common
import summarize_acnext as modal
from weighted_delay import ENDPOINT_PS


CODES = tuple(range(-16,17))
CORNERS = {'ss','tt','ff'}
MAX_STEP_PS = .50
MAP_GROUPS = {'pilot','map'}


def resolution(case):
    return case.get('resolution',8)


def family(case):
    return prior.family(case), resolution(case)


def is_map_case(case):
    return resolution(case)==16 and case['group'] in MAP_GROUPS


def collect(root, cases, plan):
    from gm_tap16_rf import headroom as half_headroom

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
            columns[fixture][side] = case,record

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
            headroom = half_headroom if resolution(case)==16 else gm_tap_rf.headroom
            paired[key] = case,pair,modal.matrix(pair,prior.PORTS),headroom(case,record,bench)
        except (KeyError,ValueError,TypeError,OSError) as error:
            invalid[key] = str(error)
    return paired,missing,invalid


def tail_currents(row):
    arms = row.get('AC_path_diagnostics_56GHz')
    if arms is None:
        return None
    return {leg:arm['total_tail_current_A'] for leg,arm in arms.items()}


def compare_even_state(row, legacy):
    if legacy is None:
        return None
    case,old = row['case'],legacy['case']
    if not (resolution(case)==16 and resolution(old)==8 and case['code']%2==0 and
            prior.pvt(case)==prior.pvt(old) and case['match_load']==old['match_load'] and
            tuple(case['anchors'])==tuple(old['anchors']) and
            [2*w for w in old['weights']]==list(case['weights'])):
        return None
    new_arms,old_arms = tail_currents(row),tail_currents(legacy)
    totals = {}
    for leg in ('P','M'):
        current = (new_arms or {}).get(leg)
        reference = (old_arms or {}).get(leg)
        change = current/reference-1 if current is not None and reference else None
        totals[leg] = {'fine_total_A':current,'legacy_total_A':reference,
                       'fine_vs_legacy_fraction':change}
    new_fit = row['AFE_delay_vs_family_center'] or {}
    old_fit = legacy['AFE_delay_vs_family_center'] or {}
    return {'reference_fixture_id':old['fixture_id'],'per_leg_total_tail_current':totals,
            'Hdd_zero_skew_change_dB':prior.subtract(row['output_56GHz']['Hdd_dB'],
                            legacy['output_56GHz']['Hdd_dB']),
            'weighted_delay_change_ps':prior.subtract(new_fit.get('delay_ps'),old_fit.get('delay_ps')),
            'phase_delay_56GHz_change_ps':prior.subtract(new_fit.get('phase_delay_at_56GHz_ps'),
                                                       old_fit.get('phase_delay_at_56GHz_ps')),
            'total_power_change_mW':row['total_mW']-legacy['total_mW']}


def measure(fixture, baseline, center, oracle, fixed):
    case = fixture[0]
    if oracle is not None and resolution(oracle[0])!=resolution(case):
        oracle = None
    # The inherited measurement treats 'pilot' as the population with an RF
    # and power budget. A full-map state is the same circuit and same screen.
    measured_case = dict(case,group='pilot') if case['group']=='map' else case
    row = prior.measure((measured_case,*fixture[1:]),baseline,center,oracle,fixed)
    row['case'] = case
    row['tail_current_A'] = tail_currents(row)
    fit = row['AFE_delay_vs_family_center'] or {}
    stress = prior.stress(case)
    phase = fit.get('phase_delay_at_56GHz_ps')
    tau = fit.get('delay_ps')
    row['residual_diagnostics'] = {
        'injected_skew_ps':stress,
        'weighted_residual_ps':stress+tau if tau is not None else None,
        'phase_residual_56GHz_ps':stress+phase if phase is not None else None,
        'weighted_phase_rms_ps':fit.get('weighted_phase_rms_ps'),
        'worst_phase_error_ps':fit.get('worst_phase_error_ps'),
    }
    row['RF_at_fitted_cancellation'] = None
    frequency = fixture[1]['p']['frequency_Hz']
    if tau is not None and prior.comparable_oracle(measured_case,oracle) and prior.same_grid(oracle,frequency):
        cancellation = -tau
        actual = prior.at_56(frequency,fixture[2],cancellation)
        reference = prior.at_56(frequency,oracle[2],cancellation)
        gain = prior.subtract(actual['Hdd_dB'],reference['Hdd_dB'])
        row['RF_at_fitted_cancellation'] = {
            'injected_skew_ps':cancellation,'output_56GHz':actual,'reference_output_56GHz':reference,
            'Hdd_drop_or_gain_dB':gain,'within_2dB_population_screen':gain>=-prior.LOSS_LIMIT_DB
            if gain is not None else None,
        }
    return row


def gate_value(row):
    oracle = row.get('RF_at_fitted_cancellation') or {}
    rf = oracle.get('within_2dB_population_screen')
    power = row.get('within_power_budget')
    if False in (rf,power):
        return False
    return True if rf is True and power is True else None


def map_report(cases, rows):
    expected, measured = defaultdict(set),defaultdict(dict)
    for case in cases:
        if is_map_case(case):
            expected[family(case)].add(case['code'])
    for row in rows:
        case = row['case']
        if is_map_case(case):
            states = measured[family(case)]
            common.need(case['code'] not in states,'Duplicate measured fine16 code')
            states[case['code']] = row
    reports = []
    for key,planned in sorted(expected.items()):
        states = measured[key]
        fits = {code:(row['AFE_delay_vs_family_center'] or {}).get('delay_ps')
                for code,row in states.items()}
        delays = {code:tau for code,tau in fits.items() if tau is not None and math.isfinite(tau)}
        steps = [{'from':a,'to':a+1,'step_ps':delays[a+1]-delays[a]}
                 for a in CODES[:-1] if a in delays and a+1 in delays]
        violations = [step for step in steps if not 0<step['step_ps']<=MAX_STEP_PS]
        gates = {code:gate_value(row) for code,row in states.items()}
        complete = set(delays)==set(CODES)
        lo,hi = delays.get(CODES[0]),delays.get(CODES[-1])
        span = lo<=-ENDPOINT_PS and hi>=ENDPOINT_PS if None not in (lo,hi) else None
        verdict = complete and span is True and not violations and all(gates[c] is True for c in CODES) \
            if complete and all(gates.get(c) is not None for c in CODES) else None
        reports.append({
            'process':key[0][0][0],'match_load':key[0][3],
            'planned_codes':sorted(planned),'missing_measured_codes':sorted(set(CODES)-set(delays)),
            'weighted_delay_ps_by_code':delays,'adjacent_weighted_steps':steps,
            'largest_measured_step_ps':max((s['step_ps'] for s in steps),default=None),
            'step_violations':violations,'full_codebook_measured':complete,
            'largest_step_within_0p50ps_and_strictly_monotone':not violations if complete else None,
            'extremes_cover_both_0p5_UI':span,'RF_and_power_gate_by_code':gates,
            'endpoint_diagnostics':endpoints(states),'outer_code_step_diagnostics':outer_steps(delays),
            'static_all_codes_pass':verdict,
        })
    return reports


def outer_steps(delays):
    diagnostics = {}
    for side,sign in (('negative',-1),('positive',1)):
        result = []
        for inward,outward in ((13,14),(14,15),(15,16)):
            a,b = sign*inward,sign*outward
            lo,hi = delays.get(a),delays.get(b)
            step = sign*(hi-lo) if None not in (lo,hi) else None
            result.append({'inner_code':a,'outer_code':b,'outward_step_ps':step,
                           'straddles_target':sign*lo <= ENDPOINT_PS <= sign*hi
                           if step is not None else None,
                           'step_pass':0<step<=MAX_STEP_PS if step is not None else None})
        diagnostics[side] = result
    return diagnostics


def endpoints(states):
    report = {}
    for label,sign in (('negative',-1),('positive',1)):
        candidates = [row for code,row in states.items() if code*sign>0 and
                      math.isclose(row['residual_diagnostics']['injected_skew_ps'],-sign*ENDPOINT_PS,
                                   rel_tol=0,abs_tol=1e-6)]
        comparison = {}
        for metric in ('weighted_residual_ps','phase_residual_56GHz_ps'):
            usable = [r for r in candidates if r['residual_diagnostics'][metric] is not None]
            best = min(usable,key=lambda r:(abs(r['residual_diagnostics'][metric]),r['case']['code']),
                       default=None)
            comparison[metric] = {'code':best['case']['code'],'residual_ps':best['residual_diagnostics'][metric],
                                  'Hdd_after_injection':(best['known_endpoint_skew'] or {}).get('corrected'),
                                  'RF_and_power_at_fitted_cancellation_pass':gate_value(best),
                                  'RF_at_endpoint_within_2dB':(best['same_route_population_oracle'] or {})
                                  .get('within_2dB_population_screen')} if best else None
        report[label] = comparison
    return report


def common_usable_window(reports):
    by_corner = {r['process']:r for r in reports}
    complete = (set(by_corner)==CORNERS and len(by_corner)==len(reports) and
                all(r['full_codebook_measured'] for r in reports))
    result = {'status':'incomplete','global_code_map_verified':False,'usable_codes':None,
              'max_step_limit_ps':MAX_STEP_PS,'required_span_each_sign_ps':ENDPOINT_PS}
    if not complete:
        return result
    for side in (-1,1):
        if not any(all(side*r['weighted_delay_ps_by_code'][code]>=ENDPOINT_PS for r in reports)
                   for code in CODES if code*side>0):
            return dict(result,status='insufficient_range')
    lo = max(c for c in CODES if c<0 and all(
        r['weighted_delay_ps_by_code'][c]<=-ENDPOINT_PS for r in reports))
    hi = min(c for c in CODES if c>0 and all(
        r['weighted_delay_ps_by_code'][c]>=ENDPOINT_PS for r in reports))
    used = list(range(lo,hi+1))
    coverage = {}
    for r in reports:
        delays, gates = r['weighted_delay_ps_by_code'],r['RF_and_power_gate_by_code']
        coverage[r['process']] = {
            'span_ps':[delays[lo],delays[hi]],
            'invalid_steps':[s for s in r['step_violations'] if lo<=s['from']<s['to']<=hi],
            'measured_RF_or_power_fail_codes':[c for c in used if gates.get(c) is False],
            'missing_RF_or_power_codes':[c for c in used if gates.get(c) is None],
        }
    if any(r['missing_RF_or_power_codes'] for r in coverage.values()):
        status = 'incomplete_RF_or_power'
    elif any(r['invalid_steps'] or r['measured_RF_or_power_fail_codes'] for r in coverage.values()):
        status = 'required_window_failed'
    else:
        status = 'verified_static_window'
    valid = status=='verified_static_window'
    return dict(result,status=status,global_code_map_verified=valid,
                usable_codes=used if valid else None,candidate_codes=used,by_corner=coverage)


def summarize(root, plan=None):
    if plan is None:
        from gm_tap16 import PLAN
        plan = PLAN
    cases = common.read(plan)['cases']
    pairs,missing,invalid = collect(root,cases,plan)
    baseline = {prior.pvt(x[0]):x for x in pairs.values() if x[0]['group']=='baseline'}
    centers = {family(x[0]):x for x in pairs.values() if x[0]['group'] in MAP_GROUPS|{'legacy'}
               and x[0]['code']==0}
    rows,by_fixture = [],{}
    for fixture in pairs.values():
        case = fixture[0]
        try:
            row = measure(fixture,baseline.get(prior.pvt(case)),centers.get(family(case)),
                          pairs.get(case.get('oracle_fixture_id')),pairs.get(case.get('fixed_fixture_id')))
        except (KeyError,ValueError,TypeError,OverflowError) as error:
            invalid[case['fixture_id']] = str(error)
        else:
            rows.append(row)
            by_fixture[case['fixture_id']] = row
    for row in rows:
        case = row['case']
        if is_map_case(case):
            matched = by_fixture.get(case.get('legacy_fixture_id'))
            row['matched_8_unit_even_code'] = compare_even_state(row,matched)
    reports = map_report(cases,rows)
    usable = common_usable_window(reports)
    return {'format':'pam4_lp14_gm_tap_fine16_summary_v1',
            'code_order_metric':'7–56 GHz fixed-weight fit relative to same-resolution code zero',
            'rows':rows,'map_reports':reports,'common_usable_window':usable,
            'missing_cases':missing,'invalid_cases':invalid,
            'unresolved_fixtures':sorted({c['fixture_id'] for c in cases}-set(by_fixture)),
            'global_code_map_verified':usable['global_code_map_verified'],
            'dynamic_switching_verified':False,'FFE_SER':None}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    common.write_new(args.output,summarize(args.run_root.resolve()))
