"""Validate compact records and compare delay trim against the archived campaign."""
import argparse
import cmath
import itertools
import math
from pathlib import Path
import re
import statistics

import comp_plan as plan
from comp_measure import at
from pilot_controller import fit as fit_pilot, score as score_pilot
import olympus_common as common

FREQ = (7e9,14e9,21e9,28e9,35e9,42e9,49e9,56e9)
SCORE = 'ideal7bit_ADC_then_FFE'


def completed(path):
    report = common.read(path/'measurements.json')
    case = common.read(path/'case.json')
    completion = common.read(path/'completion.json')
    status = common.read(path/'run_status.json')
    bench_sha = common.sha(path/'bench.scs')
    common.need(report['measurement_complete'] is True and completion['measurement_complete'] is True and
                completion['measurement_sha256']==common.sha(path/'measurements.json') and
                report['run_status_sha256']==common.sha(path/'run_status.json') and
                status['status']=='spectre_completed' and status['exit_code']==0 and
                report['case_id']==case['case_id']==status['case_id']==path.name and
                report['bench_sha256']==status['input_deck_sha256_after']==bench_sha and
                status['case_sha256']==common.sha(path/'case.json'), 'Incomplete or inconsistent run evidence')
    if case['kind']=='payload':
        common.need(report['held_sample_count']==4096 and report['held_csv_sha256']==common.sha(path/'held_samples.csv') and
                    report['short_waveform']['sha256']==common.sha(path/'short_waveform.csv'),
                    'Held sample SHA differs')
    return case,report


def observations(root, calibration_id):
    common.need(re.fullmatch(r'(?:tt|ss|ff)_[mp]\d+_v\d{3}_[+-]\d{6}',calibration_id) is not None,
                'Invalid calibration identifier')
    found = []
    for k in range(64):
        path = root/('pilot_'+calibration_id+'_c%02d'%k)
        if not path.exists():
            continue
        case, report = completed(path)
        row = report['observation']
        common.need(case['kind']=='pilot' and row['p_code']==k and row['n_code']==63-k,
                    'Pilot calibration code mismatch')
        found.append(row)
    common.need(bool(found), 'No admitted pilot observations')
    return {'format':'pn_comp_blind_observations_v1',
            'calibration_id':calibration_id,'observations':found}


def modes(a, b, node_p, node_n):
    probes = []
    for f in FREQ:
        def get(d,n):
            return at(d['frequency_Hz'],[complex(*x) for x in d['traces'][n]],f)
        p, n = get(a,node_p),get(b,node_n)
        x, y = get(b,node_p),get(a,node_n)
        dd, dc = (p-x-y+n)/2, p+x-y-n
        probes.append({'frequency_Hz':f, 'P_branch':[p.real,p.imag], 'N_branch':[n.real,n.imag],
                       'Hdd_V_per_V':abs(dd), 'Hdc_complex_V_per_V':[dc.real,dc.imag],
                       'cross_P_from_N':[x.real,x.imag], 'cross_N_from_P':[y.real,y.imag]})
    return probes


def fit_delay(probes, key):
    phases = [cmath.phase(complex(*p[key])) for p in probes]
    for i in range(1,len(phases)):
        phases[i] = phases[i-1] + math.remainder(phases[i]-phases[i-1],2*math.pi)
    fs = [f*1e-12 for f in FREQ]
    x,y = statistics.mean(fs),statistics.mean(phases)
    delay = -sum((f-x)*(q-y) for f,q in zip(fs,phases))/sum((f-x)**2 for f in fs)/(2*math.pi)
    return {'fit_delay_ps':delay,'phase_delay_ps':[-p/(2*math.pi*f) for p,f in zip(phases,fs)],
            'local_group_delay_ps':[-(b-a)/(2*math.pi*(g-f)) for a,b,f,g in
                                    zip(phases,phases[1:],fs,fs[1:])]}


def metrics(a,b):
    trim = modes(a,b,'X_ip','X_im')
    afe = modes(a,b,'X_o_p','X_o_m')
    return {'trim':trim,'AFE':afe,
            'P_delay':fit_delay(trim,'P_branch'),'N_delay':fit_delay(trim,'N_branch'),
            'noise':a['noise'],'DC_power_W':sum(a['supply_power_W'].values()),
            'source_driven_admittance_56GHz_S':[a['driven_pin_input_admittance_56GHz_S'],
                                              b['driven_pin_input_admittance_56GHz_S']]}


def codebook(rows):
    numbered = sorted(k for k in rows if k >= 0)
    if numbered != list(range(64)):
        return {'measured_codes': numbered, 'status':'PARTIAL'}
    curves = [rows[k]['P_delay']['fit_delay_ps']-rows[k]['N_delay']['fit_delay_ps'] for k in numbered]
    band = [[p-n for p,n in zip(rows[k]['P_delay']['phase_delay_ps'],
                               rows[k]['N_delay']['phase_delay_ps'])] for k in numbered]
    probes = {}
    for target in (-.5*plan.UI_PS,0.,.5*plan.UI_PS):
        error, code = min((max(abs(x-target) for x in delays),k) for k,delays in enumerate(band))
        probes[str(target)] = {'p_code':code,'n_code':63-code,'worst_band_residual_ps':error}
    steps = [b-a for a,b in zip(curves,curves[1:])]
    ideal = (curves[-1]-curves[0])/63
    return {'status':'MEASURED_AC_ESTIMATE','signed_differential_delay_ps':curves,
            'min_max_ps':[min(curves),max(curves)],'monotone_increasing':min(steps)>0,
            'largest_sorted_gap_ps':max(b-a for a,b in zip(sorted(curves),sorted(curves)[1:])),
            'DNL_LSB':[s/ideal-1 for s in steps] if ideal>0 else None,
            'endpoint_INL_LSB':[(x-curves[0])/ideal-k for k,x in enumerate(curves)] if ideal>0 else None,
            'per_code_differential_phase_delay_ps':band,
            'model_fit_endpoint_range_observed':min(curves)<=-.5*plan.UI_PS and max(curves)>=.5*plan.UI_PS,
            'known_target_design_diagnostic_only':probes,
            'scope':'Complementary pairs measured with the loaded r3 input; selected-code time-domain check remains required.'}


def errors(report):
    result = {}
    for point in ('primary','secondary'):
        m = report['results'][point]['metrics'][SCORE]
        common.need(m['sample_count']==2032, 'Wrong FFE sample count')
        result[point] = m['symbol_errors']
    return result


def summary(root, baseline, pvt_baseline):
    ac, tran, missing = {},{},{}
    for path in sorted(root.iterdir()):
        if not path.is_dir() or path.name.startswith('pilot_'):
            continue
        try:
            case,result = completed(path)
            if case['kind']=='ac':
                key = (plan.tag((case['process'],case['temperature_C'],case['vdd_V'])),
                       case['source_ohm'],-1 if case['bypass'] else case['p_code'])
                ac.setdefault(key,{})[case['drive']] = result
            else:
                row = {'case':case,'symbol_errors':errors(result),
                       'held_voltage_statistics':result['held_voltage_statistics'],
                       'trim_validation_mean_rail_W':result['trim_validation_mean_rail_W'],
                       'FFE_by_point':{k:v['metrics'][SCORE] for k,v in result['results'].items()}}
                try:
                    fit = fit_pilot(result['early_validation_pilot']['verify'])
                    row['residual_diagnostic'] = dict(fit,worst_phase_residual_ps=score_pilot(fit))
                except ValueError as error:
                    row['residual_diagnostic'] = {'status':'UNRESOLVED','reason':str(error)}
                tran[path.name] = row
        except (KeyError, ValueError, TypeError, OSError) as error:
            missing[path.name] = str(error)
    corners = {}
    for (corner,rs,code),rows in ac.items():
        if set(rows)!={'p','n'}:
            continue
        corners.setdefault((corner,rs),{})[code] = metrics(rows['p'],rows['n'])
    ac_out = {}
    for (corner,rs), rows in corners.items():
        if -1 in rows:
            base = rows[-1]
            for code, row in rows.items():
                a,b = row['AFE'][-1]['Hdd_V_per_V'], base['AFE'][-1]['Hdd_V_per_V']
                row['Hdd_56_change_vs_bypass_dB'] = 20*math.log10(a/b) if a>0 and b>0 else None
                row['DC_power_increment_vs_bypass_W'] = row['DC_power_W']-base['DC_power_W']
                row['differential_phase_delay_56GHz_ps'] = (
                    row['P_delay']['phase_delay_ps'][-1]-row['N_delay']['phase_delay_ps'][-1])
                now = complex(*row['AFE'][-1]['Hdc_complex_V_per_V'])
                ref = complex(*base['AFE'][-1]['Hdc_complex_V_per_V'])
                row['CM_to_DM_delta_ratio_at_56GHz'] = abs(now-ref)/b if b>0 else None
                if row['noise'] and base['noise']:
                    row['input_noise_variance_change_V2'] = row['noise']['Vrms']**2-base['noise']['Vrms']**2
        ac_out['%s_r%d'%(corner,rs)]={'cases':rows,'codebook':codebook(rows)}
    expected = {(plan.tag((c['process'],c['temperature_C'],c['vdd_V'])),c['source_ohm'],
                 -1 if c['bypass'] else c['p_code'],c['drive']):c['case_id'] for c in plan.build()['cases']}
    missing_ac = sorted(case_id for (corner,rs,code,drive),case_id in expected.items()
                        if drive not in ac.get((corner,rs,code),{}))
    zero = {(x['case']['study'],x['case']['process'],x['case']['seed']):x['symbol_errors']
            for x in tran.values() if x['case']['injected_skew_UI']==0}
    for row in tran.values():
        case = row['case']
        delta = str(case['injected_skew_UI'])
        if delta in ('-0.0','0.0'): delta='0.0'
        no_cell, oracle = {}, {}
        for point in ('primary','secondary'):
            if case['study']=='noise':
                pairs = baseline['noise_seed_pairs'][delta][point]['per_seed']
                a = next((v for v in pairs if v['seed']==case['seed']),None)
                if a:
                    no_cell[point]=a['current']['symbol_errors']
                    oracle[point]=a['reference']['symbol_errors']
            elif case['study']=='pvt':
                zcase = 'r3_pvt_tran_ss_t85_v081' if case['process']=='ss' else 'r3_pvt_tran_ff_tm40_v099'
                oracle[point]=pvt_baseline['fixed_FFE_endpoint_transient'][zcase]['points'][point]['symbol_errors']
                if delta=='0.0':
                    no_cell[point]=oracle[point]
            else:
                oracle[point]=baseline['quiet_grid']['0.0']['points'][point]['symbol_errors']
                if delta in baseline['quiet_grid'] and case['study']!='stress':
                    no_cell[point]=baseline['quiet_grid'][delta]['points'][point]['symbol_errors']
        row.update(archived_no_cell=no_cell,archived_zero_skew_oracle=oracle,
                   same_hardware_zero_skew=zero.get((case['study'],case['process'],case['seed']),
                       zero.get(('quiet',case['process'],case['seed']))))
    paired = {}
    for delta in (-.5,0.,.5):
        matched = [r for r in tran.values() if r['case']['study']=='noise' and
                   r['case']['injected_skew_UI']==delta and r['same_hardware_zero_skew'] and
                   set(r['archived_no_cell'])=={'primary','secondary'}]
        points = {}
        for point in ('primary','secondary'):
            seeds = sorted(
                ({'seed':r['case']['seed'], 'new_symbol_errors':r['symbol_errors'][point],
                  'change_vs_no_cell_errors':r['symbol_errors'][point]-r['archived_no_cell'][point],
                  'change_vs_new_zero_errors':r['symbol_errors'][point]-r['same_hardware_zero_skew'][point]}
                 for r in matched),key=lambda r:r['seed'])
            point_result = {'pairs':seeds,'all_20':{r['seed'] for r in seeds}==set(range(1001,1021))}
            if seeds:
                for key in ('new_symbol_errors','change_vs_no_cell_errors','change_vs_new_zero_errors'):
                    values = [r[key] for r in seeds]
                    point_result[key] = {'min':min(values),'max':max(values),'mean':statistics.mean(values)}
            points[point] = point_result
        paired[str(delta)] = points
    return {'format':'pn_comp_summary_v1','AC':ac_out,'transient':tran,'invalid':missing,
            'missing_AC_ids':missing_ac,
            'paired_noise':paired,
            'expected_integrated_count':len(plan.build()['integrated_plan']),
            'measured_integrated_count':len(tran),'course_pass':None,
            'missing_integrated_ids':sorted({c['case_id'] for c in plan.build()['integrated_plan']}-set(tran)),
            'qualifier':'No gate approval or final holdout inferred from compact data.'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--calibration-id',help='Emit blind pilot observations only')
    a=p.parse_args()
    root=a.run_root.resolve()
    if a.calibration_id:
        report=observations(root,a.calibration_id)
    else:
        archived=Path(__file__).resolve().parent/'reference'
        report=summary(root,common.read(archived/'skew_summary.json'),common.read(archived/'pvt_summary.json'))
    common.write_new(a.output,report)
