"""Read completed GLOBAL SS pilot measurements to locate a differential minimum."""
import argparse
import math
from pathlib import Path

from drive_summary import matrix_at
import gm_summary
import lp_global
import olympus_common as common
import summarize_acnext as modes
from weighted_delay import ENDPOINT_PS


def band_minimum(samples):
    if len(samples)<3:
        raise ValueError('Expected dense AC points from 45 to 80 GHz')
    local = [row for left,row,right in zip(samples,samples[1:],samples[2:])
             if row['Hdd_V_per_V']<left['Hdd_V_per_V'] and row['Hdd_V_per_V']<right['Hdd_V_per_V']]
    minimum = min(samples,key=lambda p:p['Hdd_V_per_V'])
    return {'minimum':minimum,'interior_minima':local}


def analyze(frequency,matrix,skew):
    grid = sorted({45e9,56e9,80e9,*[f for f in frequency if 45e9<=f<=80e9]})
    rows = [matrix_at(frequency,matrix,f) for f in grid]
    rows = modes.cancel_input_skew(grid,rows,skew)
    compact = []
    for f,(pp,pn,np,nn) in zip(grid,rows):
        p,n = pp-np,nn-pn
        hdd,hdc = modes.modes((pp,pn,np,nn))
        compact.append({'frequency_Hz':f,'Hdd_V_per_V':abs(hdd),'Hdd_dB':modes.db(abs(hdd)),
                        'Hdc_V_per_V':abs(hdc),'branch_p_abs':abs(p),'branch_n_abs':abs(n),
                        'branch_angle_difference_deg':math.degrees(math.atan2((p*n.conjugate()).imag,
                                                                             (p*n.conjugate()).real))
                        if p and n else None})
    return {'injected_skew_ps':skew,'at_56GHz':next(p for p in compact if p['frequency_Hz']==56e9),
            **band_minimum(compact),'trace_45_80_GHz':compact}


def read(root):
    cases = common.read(lp_global.PLAN)['cases']
    output = []
    for i in (6,8,12,38,40,44,70,72,76):
        c,n = cases[i:i+2]
        p_record = gm_summary.read_case(root,c,lp_global.PLAN)
        n_record = gm_summary.read_case(root,n,lp_global.PLAN)
        pair = {'p':p_record,'n':n_record}
        frequency = p_record['frequency_Hz']
        common.need(frequency[0]<=45e9 and frequency[-1]>=80e9,'AC band is incomplete')
        matrix = modes.matrix(pair,('X_o_p','X_o_m'))
        skew = (40-c['logical_code'])/40*ENDPOINT_PS
        output.append({'fixture_id':c['fixture_id'],'zero_input_skew':analyze(frequency,matrix,0.),
                       'target_input_skew':analyze(frequency,matrix,skew)})
    return {'format':'pam4_old_tg_ac_notch_v1','trace_source':'verified compact GLOBAL pilot AC',
            'source_plan_sha256':common.sha(lp_global.PLAN),'rows':output}


if __name__=='__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--old-run-root',type=Path,required=True)
    cli.add_argument('--output',type=Path,required=True)
    args = cli.parse_args()
    root,out = args.old_run_root.resolve(),args.output.resolve()
    common.need(not out.is_relative_to(root),'Write the report outside the earlier run root')
    common.write_new(out,read(root))
