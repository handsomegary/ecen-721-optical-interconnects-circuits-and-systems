"""Summarize full and dormant-only transfer with paired compact evidence."""
import argparse
from pathlib import Path

import gm_select as design
import olympus_common as common
import summarize_acnext as modal
import weighted_delay
from comp_measure import at


def read_case(root, case, plan_path=design.ROOT/'case_plan.json'):
    path=root/case['case_id']
    stored=common.read(path/'case.json')
    status=common.read(path/'run_status.json')
    result=common.read(path/'measurements.json')
    done=common.read(path/'completion.json')
    common.need(all(stored[k]==v for k,v in case.items()) and
                status['case_sha256']==common.sha(path/'case.json') and
                status['plan_sha256']==common.sha(plan_path) and
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


def group_key(c):
    return (c['process'],c['temperature_C'],c['vdd_V'],c['variant'],tuple(c['route_a']),
            tuple(c['route_b']),c['active'],c['off_probe'])


def saturation(op):
    return {n:d['vds']-d['vdsat'] for n,d in op.items() if
            isinstance(d.get('vds'),(int,float)) and isinstance(d.get('vdsat'),(int,float))}


def drive_plane(pair, names):
    fs=pair['p']['frequency_Hz']
    output={}
    for name in names:
        rec=pair['p' if name[4]=='P' else 'n']
        v=[complex(*z) for z in rec['traces'][name+'L']]
        currents=[-complex(*z) for z in rec['traces'][name+'DRV:p']]
        drive=at(fs,v,56e9)
        admittance=at(fs,currents,56e9)/drive if abs(drive)>1e-12 else None
        output[name]=[admittance.real,admittance.imag] if admittance is not None else None
    return output


def summarize(root):
    found,missing,invalid={},[],{}
    for c in design.build_plan()['cases']:
        try:
            r=read_case(root,c)
        except FileNotFoundError:
            missing.append(c['case_id'])
            continue
        except (ValueError,KeyError,TypeError,OSError) as error:
            invalid[c['case_id']]=str(error)
            continue
        found.setdefault(group_key(c),{})[c['drive']]=r
    rows=[]
    for key,pair in found.items():
        if set(pair)!={'p','n'}:
            continue
        process,temp,vdd,variant,a,b,active,off=key
        r=pair['p']
        fs=r['frequency_Hz']
        row={'process':process,'temperature_C':temp,'vdd_V':vdd,'variant':variant,
             'route_a':a,'route_b':b,'active':active,'dormant_only_probe':off,
             'DC_voltage_V':r['DC_voltage_V'],'DC_current_A':r['DC_current_A'],
             'DC_supply_power_W':r['DC_supply_power_W'],'stationary_noise':r['noise'],
             'saved_saturation_margins_V':saturation(r['saved_mos_oppoint'])}
        bypass=found.get(key[:3]+('bypass',(0,0),(0,0),'a',False),{})
        if set(bypass)=={'p','n'}:
            common.need(fs==bypass['p']['frequency_Hz'],'Reference grid differs')
            afe=modal.matrix(pair,('X_o_p','X_o_m'))
            afe0=modal.matrix(bypass,('X_o_p','X_o_m'))
            if off:
                full=found.get(key[:-1]+(False,),{})
                if set(full)=={'p','n'}:
                    common.need(fs==full['p']['frequency_Hz'],'Enabled probe grid differs')
                    full_afe=modal.matrix(full,('X_o_p','X_o_m'))
                    selected=[[total-dormant for total,dormant in zip(total_row,off_row)]
                              for total_row,off_row in zip(full_afe,afe)]
                    row['dormant_to_full_AFE_DM_at_56']=modal.plane56(
                        fs,afe,full_afe)
                    row['selected_only_AFE_56GHz_by_linear_subtraction']=modal.plane56(
                        fs,selected,afe0)
            else:
                row['AFE_56GHz_vs_same_termination_bypass']=modal.plane56(fs,afe,afe0)
                row['AFE_known_input_skew_56GHz_diagnostic']={
                    str(d):modal.plane56(fs,modal.cancel_input_skew(fs,afe,d),afe0)
                    for d in (-weighted_delay.ENDPOINT_PS,0.,weighted_delay.ENDPOINT_PS)}
                d,r0=modal.modes(afe[0])[0],modal.modes(afe0[0])[0]
                row['AFE_1kHz_vs_same_termination_bypass_dB']=modal.db(abs(d/r0)) if r0 else None
                track0=modal.matrix(bypass,('X_h0p','X_h0m'))
                if variant.startswith('bypass'):
                    active_gates=('X_ip','X_im')
                else:
                    active_gates=('GMS'+active.upper()+'PG','GMS'+active.upper()+'MG')
                    prefixes=[x[:5] for x in r['traces'] if x.startswith('GMS') and x.endswith('DRV:p')]
                    row['loaded_launch_input_admittance_at_56GHz_S']=drive_plane(pair,prefixes)
                row['gate_delay']=weighted_delay.evaluate(fs,modal.matrix(pair,active_gates),
                                                         modal.matrix(bypass,('X_ip','X_im')),track0)
                row['reference_noise']=bypass['p']['noise']
                row['rail_power_delta_W']={
                    k:v-bypass['p']['DC_supply_power_W'][k] if k in bypass['p']['DC_supply_power_W'] else None
                    for k,v in r['DC_supply_power_W'].items()}
                native=found.get(key[:3]+('bypass_original',(0,0),(0,0),'a',False),{})
                if set(native)=={'p','n'}:
                    row['AFE_56GHz_vs_original_unterminated']=modal.plane56(
                        fs,afe,modal.matrix(native,('X_o_p','X_o_m')))
        rows.append(row)
    return {'format':'pam4_gmselect_summary_v1','paired_rows':rows,'missing_cases':missing,
            'invalid_cases':invalid,'FFE_SER':None,'course_pass':None,'thresholds_applied':False,
            'scope':'Static bank bias and ideal isolated launch buffers. Driver power is outside this result.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    common.write_new(args.output,summarize(args.run_root.resolve()))
