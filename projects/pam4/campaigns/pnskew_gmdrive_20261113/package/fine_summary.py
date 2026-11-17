"""Summarize the adjacent-route sparse AC with explicit reference planes."""
import argparse
import math
from pathlib import Path

from comp_measure import at
import gm_fine as fine
import gm_summary as previous
import olympus_common as common
import summarize_acnext as modal
import weighted_delay


def key(case):
    return (case['process'],case['temperature_C'],case['vdd_V'],case['mode'],
            case['count_b'],tuple(case['route_a']),tuple(case['route_b']),case['probe'])


def ratio56(fs, numerator, denominator):
    def hdd(rows):
        return modal.modes([at(fs,column,56e9) for column in zip(*rows)])[0]
    a,b=hdd(numerator),hdd(denominator)
    if abs(b)==0:
        return None
    v=a/b
    return {'complex_ratio':[v.real,v.imag],'magnitude':abs(v),'dBc':modal.db(abs(v))}


def summarize(root):
    results,invalid,missing={},{},[]
    for case in fine.build_plan()['cases']:
        try:
            report=previous.read_case(root,case)
        except FileNotFoundError:
            missing.append(case['case_id'])
        except (ValueError,TypeError,KeyError,OSError) as err:
            invalid[case['case_id']]=str(err)
        else:
            results.setdefault(key(case),{})[case['drive']]=report
    controls={k[:3]:p for k,p in results.items() if k[3]=='bypass' and set(p)=={'p','n'}}
    rows={}
    for config,pair in sorted(results.items()):
        if set(pair)!={'p','n'}:
            continue
        proc,temp,vdd,mode,count,a,b,probe=config
        row={'process':proc,'temperature_C':temp,'vdd_V':vdd,'mode':mode,'count_b':count,
             'routes':[a,b],'probe':probe,'DC_current_A':pair['p']['DC_current_A'],
             'DC_voltage_V':pair['p']['DC_voltage_V'],'DC_supply_power_W':pair['p']['DC_supply_power_W'],
             'noise':pair['p']['noise'],'saved_saturation_margins_V':previous.saturation(pair['p']['saved_mos_oppoint'])}
        row['source_input_admittance_56GHz_S']=modal.source_load_at_56(pair)
        base=controls.get(config[:3])
        fs=pair['p']['frequency_Hz']
        if base:
            common.need(fs==base['p']['frequency_Hz'],'Bypass grid differs')
            afe=modal.matrix(pair,('X_o_p','X_o_m'))
            afe0=modal.matrix(base,('X_o_p','X_o_m'))
            track=modal.matrix(base,('X_h0p','X_h0m'))
            pins=modal.matrix(base,('X_ip','X_im'))
            row['AFE_56GHz_vs_matched_bypass']=modal.plane56(fs,afe,afe0)
            short=results.get(config[:3]+('driver',0,(1,1),(8,14),'full'),{})
            if mode=='driver' and probe=='full' and set(short)=={'p','n'}:
                common.need(fs==short['p']['frequency_Hz'],'Physical short-route grid differs')
                row['AFE_56GHz_vs_physical_short_route']=modal.plane56(
                    fs,afe,modal.matrix(short,('X_o_p','X_o_m')))
            row['AFE_known_skew_56GHz']={
                str(d):modal.plane56(fs,modal.cancel_input_skew(fs,afe,d),afe0)
                for d in (-weighted_delay.ENDPOINT_PS,0.,weighted_delay.ENDPOINT_PS)}
            if mode!='bypass' and probe=='full':
                for bank in ('A','B'):
                    row['bank_'+bank+'_gate_delay']=weighted_delay.evaluate(fs,modal.matrix(
                        pair,('GMS'+bank+'PG','GMS'+bank+'MG')),pins,track)
                # Per-leg projected end-to-end delay from the two AFE output
                # columns, separating real driven responses from branch clocks.
                row['AFE_column_delay_diagnostic']=weighted_delay.evaluate(
                    fs,[(pp-np,0,0,nn-pn) for pp,pn,np,nn in afe],
                    [(pp-np,0,0,nn-pn) for pp,pn,np,nn in afe0],track)
            elif probe=='dormant':
                full=results.get(config[:-1]+('full',),{})
                if set(full)=={'p','n'} and fs==full['p']['frequency_Hz']:
                    full_matrix=modal.matrix(full,('X_o_p','X_o_m'))
                    selected=[[x-y for x,y in zip(u,v)] for u,v in zip(full_matrix,afe)]
                    row['dormant_over_selected_56GHz']=ratio56(fs,afe,selected)
                    row['dormant_over_full_56GHz']=ratio56(fs,afe,full_matrix)
        rows[config]=row
    codebooks={}
    for cfg,row in rows.items():
        if row['probe']!='full' or 'AFE_column_delay_diagnostic' not in row:
            continue
        diag=row['AFE_column_delay_diagnostic']['bands']['7_to_56_GHz']
        if diag['tau_effective_ps'] is None:
            continue
        group=cfg[:4]+cfg[5:7]
        codebooks.setdefault(group,[]).append((row['count_b'],diag['tau_effective_ps']))
    metrics=[]
    for group,book in sorted(codebooks.items()):
        book.sort()
        gaps=[(j-i,abs(y-x)) for (i,x),(j,y) in zip(book,book[1:])]
        steps=[y-x for (_,x),(_,y) in zip(book,book[1:])]
        metrics.append({'configuration':group,'code_delay_ps':book,
                        'all_nine_codes':[k for k,_ in book]==list(range(9)),
                        'strict_monotone_on_measured_codes':(
                            all(x>0 for x in steps) or all(x<0 for x in steps)) if steps else None,
                        'measured_adjacent_max_gap_ps':max((y for n,y in gaps if n==1),default=None)})
    return {'format':'pam4_gmfine_summary_v1','paired_rows':list(rows.values()),'codebooks':metrics,
            'missing_cases':missing,'invalid_cases':invalid,'FFE_SER':None,'thresholds_applied':False}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    common.write_new(a.output,summarize(a.run_root.resolve()))
