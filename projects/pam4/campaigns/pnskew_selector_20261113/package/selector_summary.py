"""Combine independent P and N probes and preserve measurement provenance."""
import argparse
import math
from pathlib import Path

import olympus_common as common
import selector
import summarize_acnext as prior
import weighted_delay
from comp_measure import at

KEY = ('process', 'temperature_C', 'vdd_V', 'variant', 'bias', 'fingers',
       'p_code', 'n_code', 'state')


def read_case(root, case):
    path=root/case['case_id']
    stored=common.read(path/'case.json')
    status=common.read(path/'run_status.json')
    result=common.read(path/'measurements.json')
    done=common.read(path/'completion.json')
    common.need(all(stored[k]==v for k,v in case.items()) and
                status['case_sha256']==common.sha(path/'case.json') and
                status['plan_sha256']==common.sha(selector.ROOT/'case_plan.json') and
                status['status']=='spectre_completed' and status['exit_code']==0 and
                status['case_id']==result['case_id']==case['case_id'] and
                status['spectre_log_sha256']==common.sha(path/'spectre.log') and
                done['measurement_complete'] is True and result['measurement_complete'] is True and
                result['run_status_sha256']==common.sha(path/'run_status.json') and
                done['measurement_sha256']==common.sha(path/'measurements.json') and
                result['bench_sha256']==status['input_deck_sha256_before']==
                    status['input_deck_sha256_after']==common.sha(path/'bench.scs'),
                'Case provenance differs')
    return result


def device_metrics(pair):
    fs=pair['p']['frequency_Hz']
    # Current flowing from the driven source into the DUT is -I(source:p).
    y=[[-x for x in row] for row in prior.matrix(pair,('XVin:p','PNCVN:p'))]
    result={}
    for f in (1000., 7e9, 14e9, 28e9, 42e9, 56e9):
        row=[at(fs,column,f) for column in zip(*y)]
        conductance=-(row[1]+row[2])/2
        apparent=1/conductance if abs(conductance)>1e-18 else None
        result[str(int(f))]={
            'Y_pp_pn_np_nn_S':[[v.real,v.imag] for v in row],
            'apparent_transfer_impedance_ohm':[apparent.real,apparent.imag] if apparent is not None else None,
            'signed_mutual_capacitance_equivalent_fF':conductance.imag/(2*math.pi*f)*1e15,
            'input_ground_admittance_equivalent_S':[[(row[0]+row[1]).real,(row[0]+row[1]).imag],
                                                  [(row[3]+row[2]).real,(row[3]+row[2]).imag]]}
    return result


def loaded_metrics(pair,bypass,mid_reference):
    fs=pair['p']['frequency_Hz']
    common.need(fs==bypass['p']['frequency_Hz'],'Bypass probe grid differs')
    trim=prior.matrix(pair,('X_ip','X_im'))
    ref=prior.matrix(bypass,('X_ip','X_im'))
    tracks=prior.matrix(bypass,('X_h0p','X_h0m'))
    afe=prior.matrix(pair,('X_o_p','X_o_m'))
    afe_ref=prior.matrix(bypass,('X_o_p','X_o_m'))
    report={'delay':weighted_delay.evaluate(fs,trim,ref,tracks),
            'AFE_56GHz_vs_bypass':prior.plane56(fs,afe,afe_ref),
            'AFE_56GHz_known_input_skew_diagnostic':{
                str(d):prior.plane56(fs,prior.cancel_input_skew(fs,afe,d),afe_ref)
                for d in (-weighted_delay.ENDPOINT_PS,0.,weighted_delay.ENDPOINT_PS)},
            'noise':pair['p']['noise'],'noise_bypass':bypass['p']['noise'],
            'DC_supply_power_W':pair['p']['DC_supply_power_W'],
            'DC_voltage_V':pair['p']['DC_voltage_V'],
            'saved_mos_oppoint':pair['p'].get('saved_mos_oppoint',{}),
            'source_admittance_56GHz_S':prior.source_load_at_56(pair)}
    for label, transfer, reference in (('trim',trim,ref),('AFE',afe,afe_ref)):
        report[label+'_1kHz_vs_bypass_dB']=prior.db(abs(prior.modes(transfer[0])[0])/
                                                   abs(prior.modes(reference[0])[0]))
    if mid_reference:
        common.need(fs==mid_reference['p']['frequency_Hz'],'Same-length midrail probe grid differs')
        report['AFE_56GHz_vs_same_code_midrail_direct']=prior.plane56(
            fs,afe,prior.matrix(mid_reference,('X_o_p','X_o_m')))
    report['DM_output_relative_to_selector_rails_DC_V']={
        n:v for n,v in pair['p']['DC_voltage_V'].items() if n in ('X_ip','X_im','SELPOUT','SELNOUT')}
    return report


def summarize(root):
    found,missing,invalid={},[],{}
    for case in selector.build_plan()['cases']:
        try:
            result=read_case(root,case)
        except FileNotFoundError:
            missing.append(case['case_id'])
            continue
        except (ValueError,KeyError,TypeError,OSError) as error:
            invalid[case['case_id']]=str(error)
            continue
        found.setdefault(tuple(case[k] for k in KEY),{})[case['drive']]=result
    rows=[]
    for key,pair in found.items():
        if set(pair)!={'p','n'}:
            continue
        config=dict(zip(KEY,key))
        row={'config':config}
        if config['variant']=='device':
            row.update(Y_probes=device_metrics(pair),DC_terminal_V=pair['p']['DC_terminal_V'],
                       saved_mos_oppoint=pair['p'].get('saved_mos_oppoint',{}),
                       DC_source_currents_A=pair['p']['DC_source_currents_A'])
        else:
            bypass=found.get(key[:3]+('bypass','native',0,0,0,'na'),{})
            mid=found.get(key[:3]+('ttd_mid_direct','mid',0)+key[6:],{})
            if set(bypass)=={'p','n'}:
                row.update(loaded_metrics(pair,bypass,mid if set(mid)=={'p','n'} else None))
            else:
                row['status']='AWAITING_SAME_CORNER_BYPASS'
            swapped=found.get(key[:6]+(key[7],key[6])+key[8:],{})
            if key[6]!=key[7] and set(swapped)=={'p','n'}:
                pair_m=prior.matrix(pair,('X_ip','X_im'))
                swapped_m=prior.matrix(swapped,('X_ip','X_im'))
                common.need(pair['p']['frequency_Hz']==swapped['p']['frequency_Hz'],'Mirrored probe grid differs')
                row['PN_swap_max_absolute_error_VV']=max(abs(a-b) for x,y in zip(pair_m,swapped_m)
                                                        for a,b in zip(x,reversed(y)))
        rows.append(row)
    return {'format':'pam4_selector_summary_v1','paired_rows':rows,
            'missing_cases':missing,'invalid_cases':invalid,'thresholds_applied':False,
            'FFE_SER':None,'scope':'Isolated device Y and fixed-track AC only'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    common.write_new(args.output,summarize(args.run_root.resolve()))
