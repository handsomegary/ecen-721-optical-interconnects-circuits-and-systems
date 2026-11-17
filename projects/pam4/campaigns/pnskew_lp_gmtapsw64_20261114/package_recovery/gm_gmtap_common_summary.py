"""Score the same Split64 divider hardware at SS, TT and FF."""

import argparse
from collections import defaultdict
import math
from pathlib import Path

import gm_center64_summary as center
import gm_tapmid_summary as mid
import gm_taptrim_summary as trim
import olympus_common as common
from weighted_delay import ENDPOINT_PS


CORNERS = ('ss', 'tt', 'ff')
GROUPS = {'ideal', 'divider', 'codes', 'extra'}
PRIMARY_GROUPS = {'divider', 'codes'}
COMMON_BIAS = 'divider_lowz'
BLOCK_SIZE = 16


def process_bias(case):
    return case['process'], case['bias_kind']


def same_physical_split64(case):
    return (case['tail_variant']=='split64' and case['resolution']==64 and case['vb1_V']==.565
            and tuple(case['anchors'])==(6,11,16) and case['match_load'] is False)


def endpoint(row, sign):
    """Require both a matched population control and Hdd improvement at ±0.5 UI."""
    stress = row.get('known_endpoint_skew') or {}
    oracle = row.get('same_route_population_oracle') or {}
    skew = stress.get('injected_p_minus_n_ps')
    improvement = stress.get('Hdd_gain_vs_uncorrected_dB')
    sense = oracle.get('injected_skew_ps')
    oracle_pass = oracle.get('within_2dB_population_screen')
    inputs_present = all(mid.numeric(x) for x in (skew, sense, improvement)) and oracle_pass is not None
    ok = None
    if inputs_present:
        ok = (math.isclose(skew,-sign*ENDPOINT_PS,rel_tol=0,abs_tol=1e-8)
              and math.isclose(sense,skew,rel_tol=0,abs_tol=1e-8)
              and improvement>0 and oracle_pass is True)
    return {'endpoint_RF_pass':ok,'injected_skew_ps':skew,
            'Hdd_gain_vs_uncorrected_dB':improvement,
            'Hdd_vs_same_route_oracle_dB':oracle.get('Hdd_drop_or_gain_dB'),
            'weighted_residual_ps':stress.get('incremental_residual_ps'),
            'phase_residual_56GHz_ps':(row.get('residual_diagnostics') or {}).get('phase_residual_56GHz_ps'),
            'corrected':stress.get('corrected'),'uncorrected_same_hardware':stress.get('uncorrected_same_hardware')}


def family_report(cases, by_code):
    required = {case['code'] for case in cases if case['group']!='extra'}
    optional = {case['code'] for case in cases if case['group']=='extra'}
    missing = sorted(code for code in required if not mid.numeric(trim.delay(by_code.get(code,{})))
                     or mid.gate(by_code.get(code,{})) is None)
    optional_missing = sorted(code for code in optional if not mid.numeric(trim.delay(by_code.get(code,{})))
                              or mid.gate(by_code.get(code,{})) is None)
    delays = {code:trim.delay(row) for code,row in by_code.items() if mid.numeric(trim.delay(row))}
    observed = sorted(delays)
    steps = [{'from':a,'to':b,'step_ps':delays[b]-delays[a],
              'optional_codes_between':[code for code in optional_missing if a<code<b]}
             for a,b in zip(observed,observed[1:])]
    corners = {}
    for sign in (-1,1):
        reachable = [(delay*sign,code) for code,delay in delays.items() if code*sign>0
                     and mid.gate(by_code[code]) is True]
        outward,code = max(reachable,default=(None,None))
        extremes = [c for c in required if c*sign>0]
        nearest = min(extremes,key=lambda c:abs(delays[c]*sign-ENDPOINT_PS),default=None) \
            if all(c in delays for c in extremes) else None
        corners['negative' if sign<0 else 'positive'] = {
            'largest_measured_static_qualified_range_ps':outward,
            'largest_measured_static_qualified_range_code':code,
            'largest_measured_static_qualified_code_endpoint_RF':endpoint(by_code[code],sign)
            if code is not None else None,
            'closest_required_code':nearest,
            'closest_required_code_endpoint_RF':endpoint(by_code[nearest],sign)
            if nearest is not None else None,
        }
    required_measured = [by_code.get(code,{}) for code in sorted(required)]
    return {
        'planned_required_codes':sorted(required),
        'missing_required_metrics':missing,
        'optional_unmeasured_codes':optional_missing,
        'measured_weighted_delay_ps_by_code':delays,
        'measured_neighbor_steps':steps,
        'measured_neighbor_step_violations':[s for s in steps if not 0<s['step_ps']<=mid.MAX_STEP_PS],
        'per_code_RF_power_XT2':{code:mid.gate(row) for code,row in sorted(by_code.items())},
        'per_sign_measured_extremes':corners,
        'worst_current_target_error_fraction':trim.target_error(required_measured) if required else None,
        'peak_to_peak_current_over_min_fraction':trim.current_span(required_measured) if required else None,
    }


def common_path(by_corner, candidates, sign):
    """Find one sequence of codes whose every transition passes in all corners."""
    steps = {}
    paths = {0:(0,)}
    for code in sorted((c for c in candidates if sign*c>0), key=abs):
        options = []
        for previous,path in paths.items():
            increments = {p:sign*(trim.delay(by_corner[p][code])-trim.delay(by_corner[p][previous]))
                          for p in CORNERS}
            if all(0<d<=mid.MAX_STEP_PS for d in increments.values()):
                steps[previous,code] = increments
                options.append((*path,code))
        if options:
            paths[code] = min(options,key=lambda seq:(-len(seq),tuple(map(abs,seq))))
    reachable = []
    for code,path in paths.items():
        if not code:
            continue
        delay = {p:sign*trim.delay(by_corner[p][code]) for p in CORNERS}
        if not all(value>=ENDPOINT_PS for value in delay.values()):
            continue
        closure = {p:endpoint(by_corner[p][code],sign) for p in CORNERS}
        if all(metrics['endpoint_RF_pass'] is True for metrics in closure.values()):
            reachable.append((delay,path,closure))
    if not reachable:
        return None
    delay,path,closure = min(reachable,key=lambda x:(max(x[0].values()),abs(x[1][-1])))
    return {
        'codes_center_out':list(path),'outward_range_ps_by_corner':delay,
        'step_ps_by_corner':[
            {'from':a,'to':b,'positive_outward_step_ps':steps[a,b]} for a,b in zip(path,path[1:])],
        'endpoint_0p5_UI_RF_by_corner':closure,
    }


def common_static_map(planned, measured):
    physical = {p:[c for c in planned.get((p,COMMON_BIAS),[]) if c['group'] in PRIMARY_GROUPS] for p in CORNERS}
    required = {p:{c['code'] for c in physical[p]} for p in CORNERS}
    by_corner = {p:measured.get((p,COMMON_BIAS),{}) for p in CORNERS}
    missing = {p:sorted(c for c in required[p] if not mid.numeric(trim.delay(by_corner[p].get(c,{})))
                        or mid.gate(by_corner[p].get(c,{})) is None) for p in CORNERS}
    same_plan = (required[CORNERS[0]] and 0 in required[CORNERS[0]]
                 and all(required[p]==required[CORNERS[0]] for p in CORNERS)
                 and all(same_physical_split64(c) for plan in physical.values() for c in plan))
    row_codes = [{c for c,row in by_corner[p].items()
                  if mid.numeric(trim.delay(row)) and mid.gate(row) is True
                  and same_physical_split64(row['case'])} for p in CORNERS]
    candidates = set.intersection(*row_codes)
    result = {'bias_kind':COMMON_BIAS,'max_code_step_ps':mid.MAX_STEP_PS,
              'required_span_each_sign_ps':ENDPOINT_PS,'planned_required_codes_by_corner':
                  {p:sorted(codes) for p,codes in required.items()},
              'missing_required_metrics_by_corner':missing,'qualified_common_codes':sorted(candidates),
              'ordered_codes':None,'negative':None,'positive':None,'verified':False}
    if not same_plan:
        result['status'] = 'incomplete_or_different_primary_plan'
    elif any(missing.values()):
        result['status'] = 'incomplete_primary_measurements'
    elif 0 not in candidates:
        result['status'] = 'center_static_screen_failed'
    else:
        negative,positive = (common_path(by_corner,candidates,sign) for sign in (-1,1))
        result.update(negative=negative,positive=positive)
        if negative and positive:
            result['verified'] = True
            result['status'] = 'verified_static_screen'
            result['ordered_codes'] = negative['codes_center_out'][:0:-1]+positive['codes_center_out']
        else:
            result['status'] = 'no_common_static_path_in_measured_codes'
    return result


def read_fixture_rows(root, cases, plan):
    """Keep the baselines but discard full AC traces after processing each block."""
    columns = defaultdict(list)
    for case in cases:
        columns[case['fixture_id']].append(case)
    native = {name:items[0] for name,items in columns.items() if items[0]['group']!='oracle'}
    anchors = [name for name,c in native.items() if c['group']=='baseline' or
               (c['code']==0 and c['group'] in GROUPS|{'legacy'})]
    referenced = {c['oracle_fixture_id'] for c in native.values() if c.get('oracle_fixture_id')}
    pending = [name for name in columns if name not in referenced and name not in anchors]
    missing = set()
    invalid,fixtures = {},{}

    def read_block(names):
        requested = dict.fromkeys([*names, *(native[n]['oracle_fixture_id'] for n in names
                                         if n in native and native[n].get('oracle_fixture_id'))])
        checks = [case for name in requested for case in columns[name]]
        paired,absent,unreadable = center.collect(root,checks,plan)
        missing.update(absent)
        invalid.update(unreadable)
        return paired

    def measure_block(paired):
        for name,fixture in paired.items():
            case = fixture[0]
            wrapped = dict(case,group='pilot') if case['group'] in GROUPS else case
            try:
                row = center.measure((wrapped,*fixture[1:]),baselines.get(mid.tap.pvt(case)),
                                     centers.get(mid.family(case)),paired.get(case.get('oracle_fixture_id')))
                row['case'] = case
                fixtures[name] = row
            except (ValueError,KeyError,TypeError,OverflowError) as error:
                invalid[name] = str(error)

    first = read_block(anchors)
    baselines = {mid.tap.pvt(f[0]):f for f in first.values() if f[0]['group']=='baseline'}
    centers = {mid.family(f[0]):f for f in first.values()
               if f[0]['code']==0 and f[0]['group'] in GROUPS|{'legacy'}}
    measure_block(first)
    del first
    for start in range(0,len(pending),BLOCK_SIZE):
        measure_block(read_block(pending[start:start+BLOCK_SIZE]))
    return fixtures,[c['case_id'] for c in cases if c['case_id'] in missing],invalid


def summarize(root, plan=None):
    from gm_gmtap_common import PLAN, control_word
    if plan is None:
        plan = PLAN
    cases = common.read(plan)['cases']
    fixtures,missing,invalid = read_fixture_rows(root,cases,plan)
    planned,measured = defaultdict(list),defaultdict(dict)
    for case in cases:
        if case['group'] in GROUPS and case['drive']=='p':
            planned[process_bias(case)].append(case)
    for name,row in fixtures.items():
        case = row['case']
        if case['group'] not in GROUPS:
            continue
        try:
            row['constant_current_target'] = trim.current_comparison(
                row,fixtures.get(case.get('target_current_fixture_id')))
            if case['bias_kind']!='ideal':
                row['same_code_ideal_bias_comparison'] = mid.compare_divider(
                    row,fixtures.get(case.get('ideal_reference_fixture_id')))
            family = measured[process_bias(case)]
            common.need(case['code'] not in family,'Duplicate measured common hardware code')
            family[case['code']] = row
        except (ValueError,KeyError,TypeError,OverflowError) as error:
            invalid[name] = str(error)
    common_map = common_static_map(planned,measured)
    if common_map['verified']:
        common_map['ordered_control_words'] = [control_word(q) for q in common_map['ordered_codes']]
    resolved = set(fixtures)-set(invalid)
    return {
        'format':'pam4_lp14_gm_tap_common64_summary_v1',
        'code_unit':'signed 1/64 of nominal tail width',
        'rows':[r for name,r in fixtures.items() if name in resolved],
        'family_reports':[dict(family_report(group,measured[key]),process=key[0],bias_kind=key[1])
                          for key,group in sorted(planned.items())],
        'common_static_map':common_map,'global_code_map_verified':common_map['verified'],
        'dynamic_switching_verified':False,'FFE_SER':None,
        'missing_cases':missing,'invalid_cases':invalid,
        'unresolved_fixtures':sorted({c['fixture_id'] for c in cases}-resolved),
    }


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    common.write_new(args.output,summarize(args.run_root.resolve()))
