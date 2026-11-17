"""Summarize the new diagnostic batch with independent evidence states."""
import argparse
import math
from pathlib import Path

import diag_next as design
import gm_summary
import olympus_common as common


def summarize(root):
    rows,missing,invalid = [],[],{}
    for case in common.read(design.PLAN)['cases']:
        try:
            report = gm_summary.read_case(root,case,design.PLAN)
        except FileNotFoundError:
            missing.append(case['case_id'])
        except (ValueError,KeyError,TypeError,OSError) as err:
            invalid[case['case_id']] = str(err)
        else:
            rows.append({**case,'result':report})
    swing = {r['profile']:r['result']['finite_swing_planes'] for r in rows
             if r['stage']=='xt2' and 'finite_swing_planes' in r['result']}
    gain_change = None
    if set(swing)=={'vppd400','vppd200'}:
        a,b = swing['vppd400'],swing['vppd200']
        x,y = [r['PNC_PREP__PNC_PREN']['difference_Vpp'] for r in (a,b)]
        gain_change = {}
        for plane in ('X_c_p__X_c_m','X_o_p__X_o_m','held_at_clock_fall'):
            u = a[plane]['difference_Vpp']*y
            v = b[plane]['difference_Vpp']*x
            gain_change[plane] = 20*math.log10(u/v) if min(u,v)>0 else None
    return {'format':'lp14_diag_next_summary_v1','rows':rows,'missing_cases':missing,
            'invalid_cases':invalid,'full_vs_half_Vpp_gain_change_dB':gain_change,
            'historical_results_reclassified':False,'beta_formal_stability_verified':False}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    common.write_new(a.output,summarize(a.run_root.resolve()))
