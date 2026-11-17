"""Measure the ideal mid-code sweep and Vb2-fed Vb1 divider cases."""

import argparse
from collections import defaultdict
import math
from pathlib import Path

import gm_tap16_summary as fine
import gm_tap_summary as tap
import gm_taptrim_summary as trim
import olympus_common as common
from weighted_delay import ENDPOINT_PS


MAX_STEP_PS = .5
NEAR_BIAS_V = .002
PRIMARY_GROUPS = {'sweep', 'pvt', 'divider', 'extra'}


def family(case):
    return trim.family(case),case['bias_kind']


def numeric(value):
    return type(value) in (float,int) and math.isfinite(value)


def measure(fixture, baseline, center, oracle):
    case,pair,*_ = fixture
    if oracle is not None:
        other = oracle[0]
        common.need(all(case[key]==other[key] for key in ('tail_variant','vb1_V','resolution','code','bias_kind'))
                    and tap.comparable_oracle(case,oracle),'Minimal-load circuit differs from its candidate')
    pilot = dict(case,group='pilot') if case['group'] in PRIMARY_GROUPS else case
    row = fine.measure((pilot,*fixture[1:]),baseline,center,oracle,None)
    row['case'] = case
    row['XT2_worst'] = trim.xt2_minimum(pair)
    row['DC_bias'] = bias_evidence(case,pair) if case['group'] in PRIMARY_GROUPS|{'oracle'} else None
    return row


def bias_evidence(case,pair):
    results = {}
    for side,record in pair.items():
        voltage = record['DC_voltage_V']
        current = record.get('DC_current_A',{})
        power = record['DC_supply_power_W']
        vb1 = voltage.get('GMSKVBIAS')
        vb2 = voltage.get('X_vb')
        common.need(numeric(vb1) and numeric(vb2) and abs(vb2-.580)<=2e-6,
                    'Missing DC bias measurement or Vb2 differs from 0.580 V')
        delta = vb1-case['vb1_V']
        if case['bias_kind']=='ideal':
            common.need(abs(delta)<=2e-6,'Ideal Vb1 differs from case setpoint')
        else:
            common.need('GMSKV1:p' not in power,'Divider Vb1 must not be counted as a second supply')
        results[side] = {
            'Vb1_V':vb1,'Vb2_V':vb2,'Vb1_minus_nominal_V':delta,
            'within_2mV_diagnostic':abs(delta)<=NEAR_BIAS_V,
            'Vb2_to_divider_input_A':current.get('GMSKVDIV:p'),
            'Vb1_output_sensor_A':current.get('GMSKV1:p'),
            'Vb2_supply_power_W':power.get('XVb:p'),
            'ideal_Vb1_supply_power_W':power.get('GMSKV1:p'),
        }
    return results


def noise(row):
    return (row.get('noise') or {}).get('Vrms_1MHz_to_56GHz')


def compare_divider(row, ideal):
    if ideal is None:
        return None
    c,d = row['case'],ideal['case']
    common.need(tap.pvt(c)==tap.pvt(d) and c['code']==d['code'] and
                c['resolution']==d['resolution'] and c['tail_variant']==d['tail_variant'] and
                c['weights']==d['weights'] and c['anchors']==d['anchors'] and
                c['match_load']==d['match_load'] and c['vb1_V']==d['vb1_V'] and d['bias_kind']=='ideal',
                'Divider to ideal reference does not preserve the same circuit state')
    comparisons = {}
    for side in 'pn':
        dc,reference = row['DC_bias'][side],ideal['DC_bias'][side]
        expected = dc['Vb2_supply_power_W']
        comparisons[side] = {
            'measured_Vb1_change_V':dc['Vb1_V']-reference['Vb1_V'],
            'Vb2_supply_power_change_W':tap.subtract(expected,reference['Vb2_supply_power_W']),
            'Vb2_and_ideal_Vb1_supply_power_change_W':tap.subtract(expected,
                reference['Vb2_supply_power_W']+reference['ideal_Vb1_supply_power_W']
                if None not in (reference['Vb2_supply_power_W'],reference['ideal_Vb1_supply_power_W'])
                else None),
        }
    corrected = lambda r: ((r.get('known_endpoint_skew') or {}).get('corrected') or {}).get('Hdd_dB')
    return {'ideal_fixture_id':d['fixture_id'],'bias_delta_by_drive':comparisons,
            'weighted_delay_change_ps':tap.subtract(trim.delay(row),trim.delay(ideal)),
            'Hdd_zero_skew_change_dB':tap.subtract(row['output_56GHz']['Hdd_dB'],ideal['output_56GHz']['Hdd_dB']),
            'Hdd_at_endpoint_stress_change_dB':tap.subtract(corrected(row),corrected(ideal)),
            'XT2_margin_change_V':tap.subtract(row['XT2_worst']['margin_V'],ideal['XT2_worst']['margin_V']),
            'output_noise_change_Vrms_1MHz_to_56GHz':tap.subtract(noise(row),noise(ideal)),
            'total_power_change_mW':tap.subtract(row['total_mW'],ideal['total_mW']),
            'actual_ideal_relative_tail_current':trim.current_comparison(row,ideal)}


def gate(row):
    return trim.all_measured([fine.gate_value(row),
                              (row.get('XT2_worst') or {}).get('passes_static_screen')])


def local_report(cases,by_code):
    expected = {c['code'] for c in cases if c['group'] in ('sweep','pvt','divider')}
    missing = sorted(expected-set(by_code))
    tested = [by_code.get(code,{}) for code in sorted(expected)]
    steps = trim.endpoint_steps(by_code)
    edge = {0,-30,-29,-28,28,29,30}
    planned_full_edge = edge<=expected
    gains = [(r.get('same_route_population_oracle') or {}).get('within_2dB_population_screen') for r in tested]
    current_errors = trim.target_error(tested) if tested else None
    current_span = trim.current_span(tested) if tested else None
    screens = [gate(r) for r in tested]
    edge_check = trim.all_measured([gate(by_code.get(code,{})) for code in sorted(edge)]+
        [(by_code.get(code,{}).get('same_route_population_oracle') or {}).get('within_2dB_population_screen')
         for code in sorted(edge)]+[r['steps_within_0p50'] for detail in steps.values() for r in detail['steps']]+
        [detail['covers_0p5_UI'] for detail in steps.values()])
    parts = [arm.get('within_2mV_diagnostic') for row in tested for arm in (row.get('DC_bias') or {}).values()]
    return {'planned_codes':sorted(expected),'missing_codes':missing,'codes_with_measured_metrics':sorted(by_code),
            'per_code_RF_power_XT2':dict(zip(sorted(expected),screens)),
            'per_code_RF_at_fixed_endpoint_or_center':dict(zip(sorted(expected),gains)),
            'covers_and_resolves_all_local_endpoint_codes':edge_check if planned_full_edge else None,
            'endpoint_checks':steps,'planned_complete_edge':planned_full_edge,
            'complete_scheduled_measurements':not missing and all(x is not None for x in screens),
            'worst_current_target_error_fraction':current_errors,
            'peak_to_peak_current_over_min_fraction':current_span,
            'satisfies_2percent_current_diagnostic':max(current_span.values())<=.02 and current_errors<=.02
            if current_errors is not None and current_span is not None else None,
            'all_measured_bias_within_2mV_diagnostic':trim.all_measured(parts) if parts else None}


def side_path(by_code,sign):
    """Return the closest outer code connected to zero by qualified steps."""
    center = trim.delay(by_code.get(0,{}))
    if not numeric(center) or gate(by_code[0]) is not True:
        return None
    reachable = [(0,sign*center,[(0,sign*center)])]
    outward = sorted((code for code in by_code if code*sign>0),key=abs)
    for code in outward:
        row = by_code[code]
        value = trim.delay(row)
        if gate(row) is not True or not numeric(value):
            continue
        value *= sign
        predecessors = [[*path,(code,value)] for _,delay,path in reachable
                        if 0<value-delay<=MAX_STEP_PS]
        if predecessors:
            chosen = min(predecessors,key=lambda path:(-len(path),max(
                b[1]-a[1] for a,b in zip(path,path[1:])),tuple(abs(x[0]) for x in path)))
            reachable.append((code,value,chosen))
    candidates = [(val,path) for code,val,path in reachable if code and val>=ENDPOINT_PS
                  and (by_code[code].get('same_route_population_oracle') or {}).get(
                      'within_2dB_population_screen') is True]
    if not candidates:
        return None
    out,path = min(candidates,key=lambda x:(x[0],-len(x[1])))
    steps = [{'outward_from':a[0],'outward_to':b[0],'positive_step_ps':b[1]-a[1]}
             for a,b in zip(path,path[1:])]
    return {'codes_center_out':[p[0] for p in path],'outward_range_ps':out,'steps':steps}


def sweep_report(cases,by_code):
    primary = {c['code'] for c in cases if c['group']=='sweep'}
    optional = {c['code'] for c in cases if c['group']=='extra'}
    missing_primary = sorted(code for code in primary if not numeric(trim.delay(by_code.get(code,{})))
                             or gate(by_code.get(code,{})) is None)
    missing_optional = sorted(code for code in optional if not numeric(trim.delay(by_code.get(code,{})))
                              or gate(by_code.get(code,{})) is None)
    known = {code:trim.delay(row) for code,row in by_code.items() if numeric(trim.delay(row))}
    ordered = sorted(known)
    steps = [{'from':a,'to':b,'step_ps':known[b]-known[a],
              'optional_codes_between':sorted(c for c in missing_optional if a<c<b)}
             for a,b in zip(ordered,ordered[1:])]
    negative,positive = side_path(by_code,-1),side_path(by_code,1)
    usable = bool(primary and not missing_primary and negative and positive)
    return {'planned_primary_codes':sorted(primary),'missing_primary_metrics':missing_primary,
            'optional_unmeasured_codes':missing_optional,'weighted_delay_ps_by_measured_code':known,
            'measured_neighbor_steps':steps,'measured_neighbor_step_violations':
            [s for s in steps if not 0<s['step_ps']<=MAX_STEP_PS],
            'negative_candidate':negative,'positive_candidate':positive,
            'SS_ideal_usable_static_window':usable if primary and not missing_primary else None,
            'ordered_codes':list(reversed(negative['codes_center_out'][1:]))+positive['codes_center_out']
            if usable else None}


def summarize(root,plan=None):
    if plan is None:
        from gm_tapmid import PLAN
        plan = PLAN
    cases = common.read(plan)['cases']
    paired,missing,invalid = trim.collect(root,cases,plan)
    baselines = {tap.pvt(f[0]):f for f in paired.values() if f[0]['group']=='baseline'}
    centers = {family(f[0]):f for f in paired.values() if f[0]['code']==0 and
               f[0]['group'] in PRIMARY_GROUPS|{'legacy'}}
    rows,fixtures = [],{}
    for f in paired.values():
        case = f[0]
        try:
            row = measure(f,baselines.get(tap.pvt(case)),centers.get(family(case)),
                          paired.get(case.get('oracle_fixture_id')))
        except (ValueError,KeyError,TypeError,OverflowError) as error:
            invalid[case['fixture_id']]=str(error)
            continue
        rows.append(row)
        fixtures[case['fixture_id']]=row
    members,planned = defaultdict(dict),defaultdict(list)
    for c in cases:
        if c['group'] in PRIMARY_GROUPS and c['drive']=='p':
            planned[family(c)].append(c)
    for row in rows:
        c = row['case']
        if c['group'] not in PRIMARY_GROUPS:
            continue
        row['constant_current_target'] = trim.current_comparison(row,fixtures.get(c.get('target_current_fixture_id')))
        if c['bias_kind']!='ideal':
            try:
                row['same_code_ideal_bias_comparison'] = compare_divider(
                    row,fixtures.get(c.get('ideal_reference_fixture_id')))
            except (ValueError,KeyError,TypeError,OverflowError) as error:
                invalid[c['fixture_id']]=str(error)
                continue
        group = members[family(c)]
        common.need(c['code'] not in group,'Duplicate measured family code')
        group[c['code']] = row
    endpoint_families,sweeps = [],[]
    for key,group in sorted(planned.items()):
        report = local_report(group,members[key])
        c = group[0]
        report.update(process=c['process'],bias_kind=c['bias_kind'],nominal_Vb1_V=c['vb1_V'])
        endpoint_families.append(report)
        if any(g['group']=='sweep' for g in group):
            sweeps.append(sweep_report(group,members[key]))
    invalid_fixtures = {c['fixture_id'] for c in cases if c['case_id'] in invalid or c['fixture_id'] in invalid}
    return {'format':'pam4_lp14_gm_tap_midbias_summary_v1','rows':rows,
            'family_endpoint_reports':endpoint_families,'SS_ideal_sweep_reports':sweeps,
            'missing_cases':missing,'invalid_cases':invalid,
            'unresolved_fixtures':sorted({c['fixture_id'] for c in cases}-set(fixtures)|invalid_fixtures),
            'global_code_map_verified':False,'physical_independent_Vb1_reference_verified':False,
            'dynamic_switching_verified':False,'FFE_SER':None}


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    common.write_new(args.output,summarize(args.run_root.resolve()))
