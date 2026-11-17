"""Pair completed P/N probes, retain circuit diagnostics and flag missing cases."""
import argparse
from pathlib import Path
import math

import ac_next as bench
import olympus_common as common
import weighted_delay


def read_case(root, case):
    path = root/case['case_id']
    result = common.read(path/'measurements.json')
    receipt = common.read(path/'completion.json')
    status = common.read(path/'run_status.json')
    stored = common.read(path/'case.json')
    common.need(all(stored[k]==v for k,v in case.items()) and
                status['case_sha256']==common.sha(path/'case.json') and
                status['plan_sha256']==common.sha(bench.ROOT/'case_plan.json') and
                status['status']=='spectre_completed' and status['exit_code']==0 and
                status['case_id']==result['case_id']==case['case_id'] and
                receipt['measurement_complete'] is True and result['measurement_complete'] is True and
                result['run_status_sha256']==common.sha(path/'run_status.json') and
                receipt['measurement_sha256']==common.sha(path/'measurements.json') and
                result['bench_sha256']==status['input_deck_sha256_after']==common.sha(path/'bench.scs'),
                'Case evidence differs')
    return result


def matrix(pair, nodes):
    p,n = pair['p'],pair['n']
    fs = p['frequency_Hz']
    common.need(fs==n['frequency_Hz'],'P/N probe grids differ')
    a,b=nodes
    return [[complex(*x) for x in row] for row in zip(p['traces'][a],n['traces'][a],
                                                    p['traces'][b],n['traces'][b])]


def key(case):
    return (case['process'],case['temperature_C'],case['vdd_V'],case['source_ohm'],case['termination_ohm'],
            case['load'],case['variant'],case['p_code'],case['n_code'])


def modes(m):
    pp,pn,np,nn=m
    return (pp-pn-np+nn)/2, pp+pn-np-nn


def source_load_at_56(pair):
    from comp_measure import at
    values = []
    for side, trace in (('p','XVin:p'),('n','PNCVN:p')):
        rec=pair[side]
        ys=[-complex(*z) for z in rec['traces'][trace]]
        y=at(rec['frequency_Hz'],ys,56e9)
        values.append([y.real,y.imag])
    return values


def db(x):
    return 20*math.log10(x) if x>0 else None


def plane56(fs, candidate, reference):
    from comp_measure import at
    def point(rows):
        return [at(fs,v,56e9) for v in zip(*rows)]
    d,c=modes(point(candidate))
    d0,c0=modes(point(reference))
    return {'Hdd_absolute_dB':db(abs(d)),'Hdd_vs_bypass_dB':db(abs(d)/abs(d0)) if abs(d0) else None,
            'Hdc_increment_over_abs_Hdd_bypass':abs(c-c0)/abs(d0) if abs(d0) else None}


def cancel_input_skew(fs, rows, injected_ps):
    import cmath
    result=[]
    for f,(pp,pn,np,nn) in zip(fs,rows):
        shift=cmath.exp(-1j*math.pi*f*injected_ps*1e-12)
        result.append((pp*shift,pn*shift.conjugate(),np*shift,nn*shift.conjugate()))
    return result


def summarize(root):
    found,missing,invalid={},[],{}
    for case in bench.build_plan()['cases']:
        try:
            rec=read_case(root,case)
        except FileNotFoundError:
            missing.append(case['case_id'])
            continue
        except (ValueError,KeyError,TypeError,OSError) as error:
            invalid[case['case_id']]=str(error)
            continue
        found.setdefault(key(case),{})[case['drive']]=rec
    reports=[]
    for config,pair in sorted(found.items()):
        if set(pair)!={'p','n'}:
            continue
        process,temp,vdd,rs,rt,load,variant,p,n=config
        bypass=found.get(config[:6]+('bypass',0,0),{})
        row={'config':dict(zip(('process','temperature_C','vdd_V','source_ohm','termination_ohm','load',
                                'variant','p_code','n_code'),config)),
             'noise':pair['p']['noise'],'DC_supply_power_W':pair['p']['DC_supply_power_W'],
             'DC_voltage_V':pair['p']['DC_voltage_V'],
             'single_leg_driven_source_admittance_56GHz_S':source_load_at_56(pair)}
        fs=pair['p']['frequency_Hz']
        native=matrix(pair,('X_ip','X_im'))
        twin=found.get(config[:-2]+(n,p),{})
        if p!=n and set(twin)=={'p','n'}:
            twin_m=matrix(twin,('X_ip','X_im'))
            common.need(fs==twin['p']['frequency_Hz'],'Swapped grids differ')
            row['PN_swap_max_absolute_error_VV']=max(abs(a-b) for row_a,row_b in zip(native,twin_m)
                for a,b in zip(row_a,reversed(row_b)))
        if set(bypass)=={'p','n'} and load=='r3':
            common.need(fs==bypass['p']['frequency_Hz'],'Bypass grid differs')
            trim_bypass=matrix(bypass,('X_ip','X_im'))
            track_bypass=matrix(bypass,('X_h0p','X_h0m'))
            afe=matrix(pair,('X_o_p','X_o_m'))
            afe_bypass=matrix(bypass,('X_o_p','X_o_m'))
            row['delay']=weighted_delay.evaluate(fs,native,trim_bypass,track_bypass)
            row['unskewed_AFE_56GHz']=plane56(fs,afe,afe_bypass)
            row['known_input_skew_AFE_56GHz']={
                str(delta):plane56(fs,cancel_input_skew(fs,afe,delta),afe_bypass)
                for delta in (-weighted_delay.ENDPOINT_PS,0.,weighted_delay.ENDPOINT_PS)}
            row['known_input_skew_trim_56GHz']={
                str(delta):plane56(fs,cancel_input_skew(fs,native,delta),trim_bypass)
                for delta in (-weighted_delay.ENDPOINT_PS,0.,weighted_delay.ENDPOINT_PS)}
            row['AFE_56GHz_vs_original_0ohm_bypass_dB']=None
            original=found.get((process,temp,vdd,0,0,'r3','bypass',0,0),{})
            if set(original)=={'p','n'} and fs==original['p']['frequency_Hz']:
                original_afe=matrix(original,('X_o_p','X_o_m'))
                row['AFE_56GHz_vs_original_0ohm_bypass_dB']=plane56(
                    fs,afe,original_afe)['Hdd_vs_bypass_dB']
                row['known_input_skew_AFE_56GHz_vs_original_0ohm_bypass_dB']={
                    str(d):plane56(fs,cancel_input_skew(fs,afe,d),original_afe)['Hdd_vs_bypass_dB']
                    for d in (-weighted_delay.ENDPOINT_PS,0.,weighted_delay.ENDPOINT_PS)}
        elif load=='cap':
            identity=[(1,0,0,1)]*len(fs)
            if set(bypass)=={'p','n'}:
                reference=matrix(bypass,('X_ip','X_im'))
                row['cap_only_56GHz']=weighted_delay.evaluate(fs,native,reference,identity)['at_56_GHz']
            else:
                row['delay_status']='AWAITING_CAP_ONLY_BYPASS'
        else:
            row['delay_status']='AWAITING_SAME_FIXTURE_BYPASS'
        reports.append(row)
    return {'format':'pam4_acnext_sparse_summary_v1','missing_cases':missing,'invalid_cases':invalid,
            'paired_rows':reports,'scope':'AC diagnostics only','thresholds_applied':False,'FFE_SER':None}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    common.write_new(a.output,summarize(a.run_root.resolve()))
