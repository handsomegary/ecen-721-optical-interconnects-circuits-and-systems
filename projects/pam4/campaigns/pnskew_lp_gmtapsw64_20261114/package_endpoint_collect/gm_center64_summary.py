"""Score the local 1/64 center step and SS mid-code XT2 operating points."""
import argparse
from collections import defaultdict
from pathlib import Path

import gm_center64_rf
import gm_summary
import gm_tapmid_summary as mid
import gm_taptrim_summary as trim
import olympus_common as common
import summarize_acnext as modal


GROUPS = {'control','pilot','divider'}
MIDBAND_CODES = {sign*magnitude for sign in (-1,1) for magnitude in range(12,53,4)}
CENTER_STEPS = {32: ((-2,0),(0,2)), 64: ((-2,-1),(-1,0),(0,1),(1,2))}


def collect(root,cases,plan):
    columns, missing, invalid = defaultdict(dict), [], {}
    for case in cases:
        key,side = case['fixture_id'],case['drive']
        common.need(side in ('p','n') and side not in columns[key],
                    'Expected distinct P/N columns for '+key)
        try:
            data = gm_summary.read_case(root,case,plan)
        except FileNotFoundError:
            missing.append(case['case_id'])
        except (KeyError,ValueError,TypeError,OSError) as error:
            invalid[case['case_id']] = str(error)
        else:
            columns[key][side] = case,data
    paired = {}
    for key,items in columns.items():
        if set(items)!= {'p','n'}:
            continue
        case,record = items['p']
        try:
            other = items['n'][0]
            common.need(all(case[k]==other[k] for k in case if k not in ('case_id','drive')),
                        'P/N circuit cases differ')
            pair = {side:item[1] for side,item in items.items()}
            bench = (root/case['case_id']/'bench.scs').read_text(encoding='ascii')
            op = gm_center64_rf.headroom(case,record,bench)
            paired[key] = case,pair,modal.matrix(pair,mid.tap.PORTS),op
        except (KeyError,ValueError,TypeError,OSError) as error:
            invalid[key] = str(error)
    return paired,missing,invalid


def measure(fixture,baseline,center,oracle):
    case = fixture[0]
    measured_case = dict(case,group='sweep') if case['group'] in GROUPS else case
    row = mid.measure((measured_case,*fixture[1:]),baseline,center,oracle)
    row['case'] = case
    if case['bias_kind']!='ideal' and row['DC_bias'] is not None:
        common.need(all(mid.numeric(arm[field]) for arm in row['DC_bias'].values()
                        for field in ('Vb2_to_divider_input_A','Vb1_output_sensor_A')),
                    'Missing divider input or output sensor current')
    return row


def center_report(by_code,resolution):
    increments = CENTER_STEPS[resolution]
    needed = {c for pair in increments for c in pair}
    delays = {code:trim.delay(by_code.get(code,{})) for code in sorted(needed)}
    gates = {code:mid.gate(by_code.get(code,{})) for code in sorted(needed)}
    steps = []
    for a,b in increments:
        va,vb = delays[a],delays[b]
        step = vb-va if mid.numeric(va) and mid.numeric(vb) else None
        steps.append({'from':a,'to':b,'step_ps':step,
                      'step_pass':0<step<=mid.MAX_STEP_PS if step is not None else None})
    return {'delay_ps_by_code':delays,'RF_power_XT2_by_code':gates,'steps':steps,
            'missing_codes':sorted(needed-set(by_code)),
            'maximum_measured_step_ps':max((s['step_ps'] for s in steps if s['step_ps'] is not None),
                                          default=None),
            'all_checked_center_steps_and_static_screens_pass':trim.all_measured(
                [s['step_pass'] for s in steps]+list(gates.values()))}


def midband_report(planned,by_code):
    keys = sorted(planned&MIDBAND_CODES)
    xt2 = {code:(by_code.get(code,{}).get('XT2_worst') or {}).get('passes_static_screen')
           for code in keys}
    gates = {code:mid.gate(by_code.get(code,{})) for code in keys}
    margins = {code:(by_code.get(code,{}).get('XT2_worst') or {}).get('margin_V')
               for code in keys}
    rows = [by_code.get(code,{}) for code in keys]
    complete_grid = set(keys)==MIDBAND_CODES
    return {
        'planned_mids':keys,'missing_measured_mids':sorted(set(keys)-set(by_code)),
        'undecked_reference_grid_mids':sorted(MIDBAND_CODES-set(keys)),
        'XT2_native_and_margin_by_code':xt2,'XT2_worst_margin_V_by_code':margins,
        'RF_power_XT2_by_code':gates,'worst_margin_V':min(
            (v for v in margins.values() if v is not None),default=None),
        'all_planned_mids_pass_XT2':trim.all_measured(list(xt2.values())) if keys else None,
        'all_planned_mids_pass_RF_power_XT2':trim.all_measured(list(gates.values())) if keys else None,
        'reference_even_midband_grid_pass':trim.all_measured(list(gates.values()))
        if complete_grid else None,
        'worst_current_target_error_fraction':trim.target_error(rows) if keys else None,
        'peak_to_peak_current_over_min_fraction':trim.current_span(rows) if keys else None,
    }


def compare_split32(row,old):
    if old is None:
        return None
    case,reference = row['case'],old['case']
    common.need(case['code']==reference['code'] and case['resolution']==64 and
                reference['resolution']==32 and
                mid.tap.pvt(case)==mid.tap.pvt(reference) and
                case['anchors']==reference['anchors'] and case['match_load']==reference['match_load'] and
                case['bias_kind']==reference['bias_kind']=='ideal' and case['vb1_V']==reference['vb1_V'],
                'Split32 geometry comparison must preserve corner, code and Vb1')
    current = trim.current_comparison(row,old)
    common.need(current and current['matched_weight_distribution'],
                'Different nominal weights in same-code Split32 comparison')
    return {'fixture_id':reference['fixture_id'],'tail_current_comparison':current,
            'weighted_delay_delta_ps':mid.tap.subtract(trim.delay(row),trim.delay(old)),
            'zero_input_Hdd_delta_dB':mid.tap.subtract(row['output_56GHz']['Hdd_dB'],
                                                       old['output_56GHz']['Hdd_dB']),
            'XT2_worst_margin_delta_V':mid.tap.subtract(row['XT2_worst']['margin_V'],
                                                       old['XT2_worst']['margin_V'])}


def family_reports(cases,rows):
    plan, measured = defaultdict(dict),defaultdict(dict)
    for case in cases:
        if case['group'] in GROUPS and case['drive']=='p':
            family = plan[mid.family(case)]
            common.need(case['code'] not in family,'Duplicate planned family code')
            family[case['code']] = case
    for row in rows:
        case = row['case']
        if case['group'] in GROUPS:
            family = measured[mid.family(case)]
            common.need(case['code'] not in family,'Duplicate measured family code')
            family[case['code']] = row
    reports = []
    for key,family in sorted(plan.items()):
        case = next(iter(family.values()))
        by_code = measured[key]
        planned = set(family)
        reports.append({'process':case['process'],'group':case['group'],'bias_kind':case['bias_kind'],
                        'nominal_Vb1_V':case['vb1_V'],'resolution':case['resolution'],
                        'planned_codes':sorted(planned),'missing_codes':sorted(planned-set(by_code)),
                        'center':center_report(by_code,case['resolution']),
                        'midband':midband_report(planned,by_code),
                        'measured_negative_path_diagnostic':mid.side_path(by_code,-1),
                        'measured_positive_path_diagnostic':mid.side_path(by_code,1)})
    return reports


def summarize(root,plan=None):
    if plan is None:
        from gm_center64 import PLAN
        plan = PLAN
    cases = common.read(plan)['cases']
    paired,missing,invalid = collect(root,cases,plan)
    baselines,centers = {},{}
    for fixture in paired.values():
        case = fixture[0]
        if case['group']=='baseline':
            baselines[mid.tap.pvt(case)] = fixture
        elif case['group'] in GROUPS|{'legacy'} and case['code']==0:
            centers[mid.family(case)] = fixture
    fixtures = {}
    for key,fixture in paired.items():
        case = fixture[0]
        try:
            fixtures[key] = measure(fixture,baselines.get(mid.tap.pvt(case)),centers.get(mid.family(case)),
                                    paired.get(case.get('oracle_fixture_id')))
        except (ValueError,KeyError,TypeError,OverflowError) as error:
            invalid[key] = str(error)
    for key,row in fixtures.items():
        case = row['case']
        if case['group'] not in GROUPS:
            continue
        current = fixtures.get(case.get('target_current_fixture_id') or case.get('reference_current_fixture_id'))
        row['constant_current_target'] = trim.current_comparison(row,current)
        try:
            row['same_weight_split32_comparison'] = compare_split32(
                row,fixtures.get(case.get('same_weight_32_fixture_id')))
            if case['bias_kind']!='ideal':
                row['same_code_ideal_bias_comparison'] = mid.compare_divider(
                    row,fixtures.get(case.get('ideal_reference_fixture_id')))
        except (ValueError,KeyError,TypeError,OverflowError) as error:
            invalid[key] = str(error)
    rows = [row for key,row in fixtures.items() if key not in invalid]
    resolved = {r['case']['fixture_id'] for r in rows}
    reports = family_reports(cases,rows)
    ideal_ss = {r['resolution']:r for r in reports if r['process']=='ss' and
                r['bias_kind']=='ideal' and r['nominal_Vb1_V']==.565}
    split32_mids = (ideal_ss.get(32,{}).get('midband') or {}).get('reference_even_midband_grid_pass')
    split64_center = (ideal_ss.get(64,{}).get('center') or {}).get(
        'all_checked_center_steps_and_static_screens_pass')
    return {'format':'pam4_lp14_gm_center64_summary_v1',
            'code_unit':'signed 1/64 of nominal tail width for every resolution',
            'rows':rows,'family_reports':reports,
            'SS_565_separate_repair_checks':{'split32_even_midband_grid_pass':split32_mids,
                                             'split64_center_pass':split64_center,
                                             'both_local_repairs_pass':trim.all_measured(
                                                 [split32_mids,split64_center])},
            'missing_cases':missing,'invalid_cases':invalid,
            'unresolved_fixtures':sorted({c['fixture_id'] for c in cases}-resolved),
            'global_code_map_verified':False,'dynamic_switching_verified':False,'FFE_SER':None}


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    common.write_new(args.output,summarize(args.run_root.resolve()))
