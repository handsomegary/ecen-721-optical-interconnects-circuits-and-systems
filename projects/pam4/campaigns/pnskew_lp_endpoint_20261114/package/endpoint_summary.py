"""Measure LP14 endpoint range, local code steps, and coil sensitivity."""
import argparse
from collections import defaultdict
import math
from pathlib import Path

import drive_summary as inherited
import lp_endpoint as design
import lp_summary as lp
import olympus_common as common
import summarize_acnext as modal
import weighted_delay as delay


NYQUIST = 56e9
STEP_PS = .50
COIL_ARMS = {
    'q15_srf150': ('r15_only','c150_only','native'),
    'q8_srf110': ('r8_only','c110_only','q8'),
}


def operating_key(case):
    return (case['process'],case['temperature_C'],case['vdd_V'],case['source_R_ohm'])


def fixture_key(case):
    routes = tuple(tuple(route) for route in case['route_thirds'])
    return (case['group'],operating_key(case),case['count_b'],routes,case['variant_name'])


def find(fixture_index, case, **fields):
    return fixture_index.get(fixture_key(dict(case,**fields)))


def power_mW(record):
    return 1e3*sum(record['DC_supply_power_W'].values())


def launch_gain(frequency,pair,hz):
    traces = [('GMSHPFG','GMSHMFG'),('GMSHPFD','GMSHMFD')]
    if not all(node in pair[side]['traces'] for pair_nodes in traces
               for node in pair_nodes for side in 'pn'):
        return None
    gate,drain = (lp.hdd_at(frequency,modal.matrix(pair,nodes),hz) for nodes in traces)
    return inherited.ratio(drain,gate)


def base_row(case, pair, matrix, op):
    record = pair['p']
    frequency = record['frequency_Hz']
    total = power_mW(record)
    hdd,hdc = modal.modes(inherited.matrix_at(frequency,matrix,NYQUIST))
    row = {'case':case,'Hdd_56GHz_dB':modal.db(abs(hdd)),
           'Hdc_56GHz_complex':lp.complex_list([hdc])[0],
           'Hdd_56_over_7GHz_dB':inherited.ratio(hdd,lp.hdd_at(frequency,matrix,7e9)),
           'launch_Vdrain_over_Vgate_7GHz_dB':launch_gain(frequency,pair,7e9),
           'launch_Vdrain_over_Vgate_56GHz_dB':launch_gain(frequency,pair,NYQUIST),
           'total_mW':total,'rails_mW':{k:v*1e3 for k,v in record['DC_supply_power_W'].items()},
           'XT2':{n:v for n,v in op.items() if n.startswith('XT2')},
           'noise':record['noise']}
    iref = record.get('reference_current',{}).get('recovered_A')
    if iref is not None and case['variant_name'] not in ('r3','ideal_route'):
        devices = record['saved_mos_oppoint']
        legs = [sum(devices[f'GMSH{leg}CS{i}']['ids'] for i in range(14)) for leg in 'PM']
        row.update(iref_uA=iref*1e6,legs_mA=[i*1e3 for i in legs],mean_leg_mA=5e2*sum(legs),
                   servo_error_fraction=max(abs(i/(14*iref)-1) for i in legs) if iref>0 else None,
                   driver_drain_V=[record['DC_voltage_V'][f'GMSH{leg}FD'] for leg in 'PM'],
                   mean_driver_drain_V=.5*sum(record['DC_voltage_V'][f'GMSH{leg}FD'] for leg in 'PM'),
                   driver_total_gm_mS=[1e3*sum(devices[f'GMSH{leg}CS{i}']['gm']
                                             for i in range(14)) for leg in 'PM'])
    return row


def compare(frequency, matrix, reference, *, injected_ps=0., reference_injected_ps=0.):
    def modes(rows,skew):
        exact = inherited.matrix_at(frequency,rows,NYQUIST)
        return modal.modes(modal.cancel_input_skew([NYQUIST],[exact],skew)[0])
    hdd,hdc = modes(matrix,injected_ps)
    hdd_ref,hdc_ref = modes(reference,reference_injected_ps)
    return {'Hdd_absolute_dB':modal.db(abs(hdd)),
            'Hdd_vs_reference_dB':inherited.ratio(hdd,hdd_ref),
            'Hdc_complex':lp.complex_list([hdc])[0],
            'Hdc_over_own_Hdd':abs(hdc)/abs(hdd) if abs(hdd)>0 else None,
            'Hdc_reference_over_reference_Hdd':abs(hdc_ref)/abs(hdd_ref) if abs(hdd_ref)>0 else None,
            'Hdc_increment_over_reference_Hdd':abs(hdc-hdc_ref)/abs(hdd_ref) if abs(hdd_ref)>0 else None}


def row_for(fixture,controls,index):
    case,pair,matrix,op = fixture
    frequency = pair['p']['frequency_Hz']
    row = base_row(case,pair,matrix,op)
    r3 = controls.get(operating_key(case))
    ideal = find(index,case,variant_name='ideal_route')
    if case['group'] in ('coil_split','tolerance'):
        ideal = find(index,case,group='coverage',variant_name='ideal_route')
    zero = find(index,case,group='coverage',variant_name='native',count_b=0,route_thirds=design.ZERO)
    same_grid = lambda fix: fix is not None and fix[1]['p']['frequency_Hz']==frequency
    real_driver = case['variant_name'] not in ('r3','ideal_route')
    budget = 10 if case['count_b'] in (0,8) else 14
    row.update(added_mW_vs_r3=None,budget_mW=budget if real_driver else None,
               within_power_budget=None,within_2dB=None,gain_and_power_pass=None)
    if real_driver and r3:
        added = row['total_mW']-power_mW(r3[1]['p'])
        row.update(added_mW_vs_r3=added,within_power_budget=added<=budget)
    if real_driver and same_grid(ideal):
        driver = compare(frequency,matrix,ideal[2])
        gain = driver['Hdd_vs_reference_dB']
        row.update(vs_same_route_ideal_zero_skew=driver,
                   excess_group_delay_ps=lp.excess_group_delay(frequency,matrix,ideal[2]),
                   within_2dB=gain>=-2 if gain is not None else None)
    if real_driver and same_grid(r3) and case['group'] in ('coverage','endpoint','fine'):
        r3_matrix = r3[2]
        track = modal.matrix(r3[1],('X_h0p','X_h0m'))
        row['vs_r3_zero_skew'] = compare(frequency,matrix,r3_matrix)
        row['AFE_column_delay'] = delay.evaluate(frequency,inherited.column_projection(matrix),
                                                  inherited.column_projection(r3_matrix),track)
        if same_grid(zero):
            row['incremental_delay_vs_native_zero'] = delay.evaluate(
                frequency,inherited.column_projection(matrix),inherited.column_projection(zero[2]),track)
        if case['group'] in ('endpoint','fine'):
            injected = case['direction']*delay.ENDPOINT_PS
            row['known_skew_offline_only'] = {
                'injected_skew_ps':injected,
                'vs_r3_zero_skew':compare(frequency,matrix,r3_matrix,injected_ps=injected),
            }
            skewed = row['known_skew_offline_only']
            if same_grid(zero):
                skewed['uncorrected_same_native_vs_r3_zero_skew'] = compare(
                    frequency,zero[2],r3_matrix,injected_ps=injected)
                skewed['compensated_vs_uncorrected_same_native'] = compare(
                    frequency,matrix,zero[2],injected_ps=injected,reference_injected_ps=injected)
            if same_grid(ideal):
                skewed['vs_same_route_ideal_with_same_skew'] = compare(
                    frequency,matrix,ideal[2],injected_ps=injected,reference_injected_ps=injected)
                gain = skewed['vs_same_route_ideal_with_same_skew']['Hdd_vs_reference_dB']
                skewed['within_2dB'] = gain>=-2 if gain is not None else None
                skew_gates = (row['within_power_budget'],skewed['within_2dB'])
                skewed['gain_and_power_pass'] = all(skew_gates) if None not in skew_gates else None
    gates = (row['within_power_budget'],row['within_2dB'])
    row['gain_and_power_pass'] = all(gates) if None not in gates else None
    return row


def coil_reports(rows,cases):
    reports = []
    members = {fixture_key(row['case']):row for row in rows}
    for case in cases:
        if case['group']!='coil_split' or case['drive']!='p':
            continue
        for label,(series,parallel,full) in COIL_ARMS.items():
            if case['variant_name']!=series:
                continue
            effects = {}
            for variant in ('ideal_coil',series,parallel,full):
                effects[variant] = find(members,case,variant_name=variant)

            def factorial(field):
                values = [r.get(field) if r else None for r in effects.values()]
                if None in values:
                    return None
                ref,r,c,both = values
                return {'R_only_minus_ideal':r-ref,'Cp_only_minus_ideal':c-ref,
                        'R_and_Cp_minus_ideal':both-ref,'interaction':both-r-c+ref}

            reports.append({'case':case,'factorial':label,'status':'complete' if all(effects.values()) else 'partial',
                            'missing_arms':[variant for variant,arm in effects.items() if arm is None],
                            'Hdd_56GHz_dB':factorial('Hdd_56GHz_dB'),
                            'Hdd_56_over_7GHz_dB':factorial('Hdd_56_over_7GHz_dB'),
                            'launch_Vdrain_over_Vgate_7GHz_dB':factorial('launch_Vdrain_over_Vgate_7GHz_dB'),
                            'launch_Vdrain_over_Vgate_56GHz_dB':factorial('launch_Vdrain_over_Vgate_56GHz_dB'),
                            'power_mW':factorial('total_mW'),'servo_error_fraction':factorial('servo_error_fraction'),
                            'mean_leg_mA':factorial('mean_leg_mA'),'mean_driver_drain_V':factorial('mean_driver_drain_V')})
    return reports


def fitted_delay(row, field='incremental_delay_vs_native_zero'):
    return row.get(field,{}).get('bands',{}).get('7_to_56_GHz',{}).get('tau_effective_ps')


def fine_reports(rows,cases):
    expected,measured = defaultdict(set),defaultdict(dict)
    for c in cases:
        if c['group']=='fine':
            expected[(c['process'],c['direction'],c['segment'])].add(c['count_b'])
    for row in rows:
        c = row['case']
        if c['group']=='fine':
            measured[(c['process'],c['direction'],c['segment'])][c['count_b']] = row
    reports = {}
    for key,codes in sorted(expected.items()):
        corner,direction,segment = key
        values = {k:fitted_delay(row) for k,row in measured.get(key,{}).items()}
        resolved = {k:v for k,v in values.items() if v is not None}
        pairs = [{'from_code':k,'to_code':k+1,'step_ps':resolved[k+1]-resolved[k]}
                 for k in sorted(resolved) if k+1 in resolved]
        peak = max((abs(p['step_ps']) for p in pairs),default=None)
        complete = set(resolved)==set(range(9))
        monotone = all(p['step_ps']*direction>0 for p in pairs) if pairs else None
        reports[key] = {'process':corner,'direction':direction,'segment':segment,
                        'status':('complete' if complete else 'sparse' if set(resolved)==codes else 'partial'),
                        'planned_codes':sorted(codes),'measured_code_delay_ps':values,
                        'adjacent_steps':pairs,'largest_measured_step_ps':peak,
                        'monotone_where_measured':monotone,
                        'within_0p50ps_where_measured':peak<=STEP_PS if peak is not None else None,
                        'all_steps_pass':complete and monotone and peak<=STEP_PS if complete else None}
    seams = []
    for (corner,direction,segment),segment_report in reports.items():
        next_report = reports.get((corner,direction,segment+1))
        if next_report is None:
            continue
        current = segment_report['measured_code_delay_ps'].get(8)
        following = next_report['measured_code_delay_ps'].get(0)
        seam = following-current if current is not None and following is not None else None
        before = measured.get((corner,direction,segment),{}).get(8,{})
        after = measured.get((corner,direction,segment+1),{}).get(0,{})
        hdd_before,hdd_after = before.get('Hdd_56GHz_dB'),after.get('Hdd_56GHz_dB')
        cm_before,cm_after = before.get('Hdc_56GHz_complex'),after.get('Hdc_56GHz_complex')
        power_before,power_after = before.get('total_mW'),after.get('total_mW')
        seams.append({'process':corner,'direction':direction,'after_segment':segment,
                      'next_code0_minus_this_code8_ps':seam,
                      'along_increasing_code_ps':seam*direction if seam is not None else None,
                      'within_0p50ps_magnitude':abs(seam)<=STEP_PS if seam is not None else None,
                      'Hdd_56GHz_change_dB':hdd_after-hdd_before if None not in (hdd_before,hdd_after) else None,
                      'Hdc_56GHz_change_V_per_V':lp.complex_list([complex(*cm_after)-complex(*cm_before)])[0]
                      if cm_before is not None and cm_after is not None else None,
                      'total_mW_change':power_after-power_before if None not in (power_before,power_after) else None})
    return list(reports.values()),seams


def endpoint_reports(rows,cases):
    endpoints = []
    for row in rows:
        case = row['case']
        if case['group']!='endpoint' or case['variant_name']!='native':
            continue
        skew = case['direction']*delay.ENDPOINT_PS
        estimate = fitted_delay(row)
        endpoints.append({'process':case['process'],'direction':case['direction'],'count_b':case['count_b'],
                          'fixture_id':case['fixture_id'],'estimated_p_minus_n_delay_ps':estimate,
                          'r3_referenced_p_minus_n_delay_ps':fitted_delay(row,'AFE_column_delay'),
                          'injected_skew_ps':skew,'signed_residual_ps':estimate+skew if estimate is not None else None,
                          'reaches_required_correction':-estimate*case['direction']>=delay.ENDPOINT_PS
                          if estimate is not None else None,
                          'ac_only':True})
    grouped = defaultdict(list)
    expected = defaultdict(set)
    for c in cases:
        if c['group'] in ('endpoint','fine') and c['variant_name']=='native':
            expected[(c['process'],c['direction'])].add(c['fixture_id'])
    for row in rows:
        c = row['case']
        if c['group'] not in ('endpoint','fine') or c['variant_name']!='native':
            continue
        estimate = fitted_delay(row)
        if estimate is None:
            continue
        direction = c['direction']
        grouped[(c['process'],direction)].append({
            'fixture_id':c['fixture_id'],'group':c['group'],'segment':c['segment'],'count_b':c['count_b'],
            'delay_ps':estimate,'signed_residual_ps':estimate+direction*delay.ENDPOINT_PS,
            'Hdd_corrected_vs_r3_56GHz_dB':row.get('known_skew_offline_only',{}).get(
                'vs_r3_zero_skew',{}).get('Hdd_vs_reference_dB'),
            'within_power_budget':row.get('within_power_budget')})
    coverage = []
    for (corner,direction),planned in sorted(expected.items()):
        candidates = grouped[(corner,direction)]
        nearest = min(candidates,key=lambda c:(abs(c['signed_residual_ps']),c['fixture_id']),default=None)
        maximum = max((-c['delay_ps']*direction for c in candidates),default=None)
        coverage.append({'process':corner,'direction':direction,'injected_skew_ps':direction*delay.ENDPOINT_PS,
                         'measured_fixtures':len(candidates),'planned_fixtures':len(planned),
                         'status':'planned_fixtures_resolved' if len(candidates)==len(planned) else 'partial',
                         'maximum_measured_corrective_delay_ps':maximum,
                         'reaches_required_correction_where_measured':maximum>=delay.ENDPOINT_PS
                         if maximum is not None else None,
                         'closest_measured_fixture_known_target_only':nearest})
    return endpoints,coverage


def summarize(root):
    cases = common.read(design.PLAN)['cases']
    results,missing,invalid = lp.read_pairs(root,cases,design.PLAN,lambda c:c['fixture_id'])
    partial = sorted({c['fixture_id'] for c in cases if c['case_id'] in missing or c['case_id'] in invalid}
                     -set(results))
    controls = {operating_key(c):item for item in results.values()
                for c in (item[0],) if c['variant_name']=='r3'}
    index = {fixture_key(item[0]):item for item in results.values()}
    rows = []
    for fixture in results.values():
        try:
            rows.append(row_for(fixture,controls,index))
        except (ValueError,KeyError,TypeError,OverflowError) as error:
            invalid[fixture[0]['fixture_id']] = str(error)
    fine,seams = fine_reports(rows,cases)
    endpoints,coverage = endpoint_reports(rows,cases)
    return {'format':'lp14_endpoint_fine_summary_v1','rows':rows,'endpoints':endpoints,
            'endpoint_coverage_known_target_only':coverage,
            'local_fine_codebooks':fine,'seams':seams,'coil_factorial':coil_reports(rows,cases),
            'missing_cases':missing,'invalid_cases':invalid,'fixtures_with_missing_or_invalid_cases':partial,
            'global_code_map_verified':False,'FFE_SER':None}


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    common.write_new(args.output,summarize(args.run_root.resolve()))
