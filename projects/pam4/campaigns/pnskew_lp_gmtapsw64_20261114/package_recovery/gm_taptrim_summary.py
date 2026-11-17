"""Compare coarse3 Vb1 current trim and the single 1/32 endpoint step."""

import argparse
from collections import defaultdict
import math
from pathlib import Path

import gm_summary
import gm_tap16_summary as fine
import gm_tap_summary as tap
import olympus_common as common
import summarize_acnext as modal
from weighted_delay import ENDPOINT_PS


EDGE_CODES = (-30,-29,-28,0,28,29,30)
MAX_STEP_PS = .50
CURRENT_DIAGNOSTIC_LIMIT = .02
UNTRIMMED_V = .580
XT2_INSTANCES = tuple(f'XT2{side}{i}' for side in 'pm' for i in range(8))


def hardware_family(case):
    return (tap.pvt(case),case['tail_variant'],case['resolution'],tuple(case['anchors']),
            case['match_load'])


def family(case):
    return hardware_family(case),case['vb1_V']


def collect(root, cases, plan):
    from gm_taptrim_rf import headroom

    columns,missing,invalid = defaultdict(dict),[],{}
    for case in cases:
        fixture,side = case['fixture_id'],case['drive']
        common.need(side in ('p','n') and side not in columns[fixture],
                    'Expected distinct P/N columns for '+fixture)
        try:
            record = gm_summary.read_case(root,case,plan)
        except FileNotFoundError:
            missing.append(case['case_id'])
        except (KeyError,ValueError,TypeError,OSError) as error:
            invalid[case['case_id']] = str(error)
        else:
            columns[fixture][side] = case,record
    paired = {}
    for key,items in columns.items():
        if set(items) != {'p','n'}:
            continue
        case,record = items['p']
        try:
            other = items['n'][0]
            common.need(all(case[k]==other[k] for k in case if k not in ('case_id','drive')),
                        'P/N circuit cases differ')
            pair = {side:item[1] for side,item in items.items()}
            bench = (root/case['case_id']/'bench.scs').read_text(encoding='ascii')
            paired[key] = case,pair,modal.matrix(pair,tap.PORTS),headroom(case,record,bench)
        except (KeyError,ValueError,TypeError,OSError) as error:
            invalid[key] = str(error)
    return paired,missing,invalid


def xt2_minimum(pair):
    arms = {}
    candidates = []
    for drive in 'pn':
        ops = pair[drive]['saved_mos_oppoint']
        devices = {}
        for tag in XT2_INSTANCES:
            op = ops.get(tag,{})
            vds, vdsat = (op.get(key) for key in ('vds','vdsat'))
            region = op.get('region')
            numeric = all(type(v) in (int,float) and math.isfinite(v) for v in (vds,vdsat))
            margin = vds-abs(vdsat) if numeric else None
            saturated = region in (2, '2', '2.0') if region is not None else None
            status = all_measured([margin>0 if numeric else None,saturated])
            devices[tag] = {'vds_V':vds,'vdsat_V':vdsat,'margin_V':margin,
                            'native_region':region,'passes_static_screen':status}
            if numeric:
                candidates.append((margin,drive,tag))
        arms[drive] = devices
    worst,drive,tag = min(candidates,default=(None,None,None))
    return {'instance':tag,'drive':drive,'margin_V':worst,
            'passes_static_screen':all_measured([op['passes_static_screen']
                                                 for arm in arms.values() for op in arm.values()]),
            'per_drive':arms}


def measured_current(row):
    currents = row.get('tail_current_A') or {}
    return {leg:currents.get(leg) for leg in 'PM'}


def current_comparison(row, reference):
    if not reference or tap.pvt(row['case'])!=tap.pvt(reference['case']):
        return None
    case,old = row['case'],reference['case']
    arms = measured_current(row)
    target = measured_current(reference)
    errors = {leg:arms[leg]/target[leg]-1 if arms[leg] is not None and target[leg] else None
              for leg in 'PM'}
    width = lambda c: {tap_id:weight/c['resolution'] for tap_id,weight in tap.active_distribution(c)}
    return {'reference_fixture_id':old['fixture_id'],'matched_weight_distribution':width(case)==width(old),
            'current_A':arms,'reference_A':target,'fraction_vs_reference':errors}


def score_case(fixture, baseline, center, oracle):
    case = fixture[0]
    if oracle is not None:
        other = oracle[0]
        common.need(all(case[key]==other[key] for key in ('tail_variant','vb1_V','resolution','code')) and
                    tap.comparable_oracle(case,oracle),
                    'Minimal-load oracle does not match hardware, Vb1 or active weights')
    measured_case = dict(case,group='pilot') if case['group']=='control' else case
    row = fine.measure((measured_case,*fixture[1:]),baseline,center,oracle,None)
    row['case'] = case
    if case['group'] in ('control','oracle','pilot'):
        arms = {}
        for drive,record in fixture[1].items():
            values = record['DC_voltage_V']
            vb1,vb2 = values['GMSKVBIAS'],values['X_vb']
            common.need(math.isclose(vb1,case['vb1_V'],rel_tol=0,abs_tol=2e-6) and
                        math.isclose(vb2,.580,rel_tol=0,abs_tol=2e-6),
                        'Native DC bias does not match commanded Vb1 and fixed Vb2')
            arms[drive] = {'Vb1_V':vb1,'Vb2_V':vb2}
        row['measured_DC_bias_by_drive'] = arms
    row['XT2_worst'] = xt2_minimum(fixture[1])
    return row


def summarize_bias_effect(row, untrimmed):
    if untrimmed is None:
        return None
    actual,base = measured_current(row),measured_current(untrimmed)
    x1,x0 = row['XT2_worst'],untrimmed['XT2_worst']
    d1,d0 = row['residual_diagnostics'],untrimmed['residual_diagnostics']
    return {'untrimmed_fixture_id':untrimmed['case']['fixture_id'],
            'tail_current_change_A':{leg:tap.subtract(actual[leg],base[leg]) for leg in 'PM'},
            'XT2_margin_change_V':tap.subtract(x1['margin_V'],x0['margin_V']) if x1 and x0 else None,
            'Hdd_zero_input_change_dB':tap.subtract(row['output_56GHz']['Hdd_dB'],
                                                  untrimmed['output_56GHz']['Hdd_dB']),
            'weighted_residual_change_ps':tap.subtract(d1['weighted_residual_ps'],d0['weighted_residual_ps'])}


def delay(row):
    return (row.get('AFE_delay_vs_family_center') or {}).get('delay_ps')


def endpoint_steps(by_code):
    result = {}
    for sign in (-1,1):
        codes = [sign*mag for mag in (28,29,30)]
        inner,middle,outer = (delay(by_code.get(code,{})) for code in codes)
        records = []
        for low,high,a,b in ((inner,middle,*codes[:2]),(middle,outer,*codes[1:])):
            value = sign*(high-low) if low is not None and high is not None else None
            records.append({'inner_code':a,'outer_code':b,'outward_step_ps':value,
                            'steps_within_0p50':0<value<=MAX_STEP_PS if value is not None else None})
        result['negative' if sign==-1 else 'positive'] = {
            'correction_ps':dict(zip(codes,(inner,middle,outer))),
            'steps':records,
            'covers_0p5_UI':sign*outer>=ENDPOINT_PS if outer is not None else None,
            'closest_measured_code':min(((abs(ENDPOINT_PS-sign*d),k) for k,d in
                                         zip(codes,(inner,middle,outer)) if d is not None),
                                        default=(None,None))[1]}
    return result


def all_measured(values):
    if any(v is False for v in values):
        return False
    return True if all(v is True for v in values) else None


def target_error(rows):
    compared = [r.get('constant_current_target') or {} for r in rows]
    errors = [(r.get('fraction_vs_reference') or {}).get(leg) for r in compared for leg in 'PM']
    if not errors or any(e is None for e in errors):
        return None
    return max(map(abs,errors))


def current_span(rows):
    current_maps = [measured_current(row) for row in rows]
    if not current_maps or any(not current[leg] for current in current_maps for leg in 'PM'):
        return None
    result = {}
    for leg in 'PM':
        values = [current[leg] for current in current_maps]
        result[leg] = max(values)/min(values)-1
    return result


def prepare_report(cases, rows):
    settings = defaultdict(set)
    measured = defaultdict(dict)
    for case in cases:
        if case['group']=='pilot' and case['tail_variant']=='split32':
            settings[family(case)].add(case['code'])
    for row in rows:
        case = row['case']
        if case['group']=='pilot' and case['tail_variant']=='split32':
            by_code = measured[family(case)]
            common.need(case['code'] not in by_code,'Duplicate measured local code')
            by_code[case['code']] = row
    reports = []
    for key, planned in sorted(settings.items()):
        pvt,tail_variant,_,anchors,match_load = key[0]
        by_code = measured[key]
        steps = endpoint_steps(by_code)
        required = [by_code.get(code,{}) for code in EDGE_CODES]
        missing = [code for code in EDGE_CODES if code not in by_code]
        current_error = target_error(required)
        spread = current_span(required)
        step_pass = all_measured([r['steps_within_0p50'] for side in steps.values() for r in side['steps']])
        coverage = all_measured([side['covers_0p5_UI'] for side in steps.values()])
        xt2 = all_measured([(row.get('XT2_worst') or {}).get('passes_static_screen') for row in required])
        rf_power = all_measured([fine.gate_value(row) for row in required])
        stress_gain = all_measured([(row.get('same_route_population_oracle') or {})
                                    .get('within_2dB_population_screen') for row in required])
        current_pass = (current_error<=CURRENT_DIAGNOSTIC_LIMIT and
                        max(spread.values())<=CURRENT_DIAGNOSTIC_LIMIT
                        if current_error is not None and spread is not None else None)
        reports.append({
            'process':pvt[0],'tail_variant':tail_variant,'anchors':anchors,'match_load':match_load,
            'vb1_V':key[1],'planned_codes':sorted(planned),'missing_required_codes':missing,
            'signed_endpoint_steps':steps,'local_step_pass':step_pass,'coverage_pass':coverage,
            'XT2_all_native_region_2_and_positive_margin':xt2,
            'RF_and_power_at_fitted_cancellation':rf_power,
            'RF_at_fixed_endpoint_stress_or_center':stress_gain,
            'worst_absolute_current_target_error_fraction':current_error,
            'peak_to_peak_current_over_min_fraction':spread,
            'within_diagnostic_current_target_and_span':current_pass,
            'local_trim_pass':all_measured([step_pass,coverage,xt2,rf_power,stress_gain]) if not missing else None,
        })
    return reports


def rank_common_bias(reports):
    passed = [r for r in reports if r['local_trim_pass'] is True]
    if not passed:
        return None
    return min(passed,key=lambda r:(r['within_diagnostic_current_target_and_span'] is not True,
                                   r['worst_absolute_current_target_error_fraction']
                                   if r['worst_absolute_current_target_error_fraction'] is not None else float('inf'),
                                   abs(r['vb1_V']-UNTRIMMED_V),r['vb1_V']))


def summarize(root, plan=None):
    if plan is None:
        from gm_taptrim import PLAN
        plan = PLAN
    cases = common.read(plan)['cases']
    pairs,missing,invalid = collect(root,cases,plan)
    baselines = {tap.pvt(x[0]):x for x in pairs.values() if x[0]['group']=='baseline'}
    centers = {family(x[0]):x for x in pairs.values()
               if x[0]['code']==0 and x[0]['group'] in ('legacy','control','pilot')}
    rows,by_fixture = [],{}
    for fixture in pairs.values():
        case = fixture[0]
        try:
            row = score_case(fixture,baselines.get(tap.pvt(case)),centers.get(family(case)),
                             pairs.get(case.get('oracle_fixture_id')))
        except (KeyError,ValueError,TypeError,OverflowError) as error:
            invalid[case['fixture_id']] = str(error)
        else:
            rows.append(row)
            by_fixture[case['fixture_id']] = row
    untrimmed = {(hardware_family(r['case']),r['case']['code'],r['case']['group']):r
                 for r in rows if r['case']['vb1_V']==UNTRIMMED_V}
    old_center = {tap.pvt(r['case']):r for r in rows if r['case']['tail_variant']=='old8' and
                  r['case']['group']=='legacy' and r['case']['code']==0}
    old_halves = {(tap.pvt(r['case']),r['case']['code']):r for r in rows
                  if r['case']['tail_variant']=='half16' and r['case']['group']=='control'
                  and r['case']['vb1_V']==UNTRIMMED_V}
    for row in rows:
        case = row['case']
        comparison = current_comparison(row,by_fixture.get(case.get('reference_current_fixture_id')))
        if comparison is not None and 'reference_current_exact' in case:
            common.need(comparison['matched_weight_distribution']==case['reference_current_exact'],
                        'Legacy current reference weight annotation differs')
        row['legacy_current_comparison'] = comparison
        target_id = case.get('target_current_fixture_id')
        target = by_fixture.get(target_id) if target_id else old_center.get(tap.pvt(case))
        row['constant_current_target'] = current_comparison(row,target)
        row['change_from_same_untrimmed_hardware_and_code'] = summarize_bias_effect(row,untrimmed.get(
            (hardware_family(case),case['code'],case['group']))) if case['vb1_V']!=UNTRIMMED_V else None
        if case['tail_variant']=='split32' and case['group']=='pilot' and case['vb1_V']==UNTRIMMED_V:
            row['change_from_same_bias_half16'] = summarize_bias_effect(
                row,old_halves.get((tap.pvt(case),case['code'])))
    reports = prepare_report(cases,rows)
    return {'format':'pam4_lp14_gm_tap_trim32_summary_v1','rows':rows,'local_common_bias_reports':reports,
            'best_measured_common_bias_local_only':rank_common_bias(reports),
            'current_diagnostic_limit_fraction':CURRENT_DIAGNOSTIC_LIMIT,
            'global_code_map_verified':False,'dynamic_switching_verified':False,'FFE_SER':None,
            'missing_cases':missing,'invalid_cases':invalid,
            'unresolved_fixtures':sorted({c['fixture_id'] for c in cases}-set(by_fixture))}


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    common.write_new(args.output,summarize(args.run_root.resolve()))
