"""Collect completed diagnostic results while preserving unresolved status."""
import argparse
import math
from pathlib import Path

import gm_summary
import lp_diagnostics as design
import olympus_common as common
import recover_diag


def summarize(root,recovery_root=None):
    rows,missing,invalid = [],[],{}
    cases = common.read(design.PLAN)['cases']
    for i,case in enumerate(cases):
        try:
            if recovery_root is not None and i in recover_diag.COHORT:
                report = recover_diag.read_recovered(recovery_root/case['case_id'],case)
            else:
                report = gm_summary.read_case(root,case,design.PLAN)
        except FileNotFoundError:
            missing.append(case['case_id'])
        except (KeyError,ValueError,TypeError,OSError) as err:
            invalid[case['case_id']] = str(err)
        else:
            rows.append({'case_id':case['case_id'],'stage':case['stage'],'profile':case['profile'],
                         'process':case['process'],'count_b':case['count_b'],'result':report})
    def gate(stage):
        found = [r['result'].get('passed') for r in rows if r['stage']==stage]
        if any(p is False for p in found):
            return False
        expected = sum(c['stage']==stage for c in cases)
        return True if len(found)==expected and all(p is True for p in found) else None
    swing = {r['profile']:r['result']['finite_swing_planes'] for r in rows if
             r['stage']=='xt2' and 'finite_swing_planes' in r['result']}
    compression = None
    if set(swing)=={'vppd400','vppd200'}:
        full,half = swing['vppd400'],swing['vppd200']
        a = full['PNC_PREP__PNC_PREN']['difference_Vpp']
        b = half['PNC_PREP__PNC_PREN']['difference_Vpp']
        compression = {}
        for plane in ('X_c_p__X_c_m','X_o_p__X_o_m','held_at_clock_fall'):
            num = full[plane]['difference_Vpp']*b
            den = half[plane]['difference_Vpp']*a
            compression[plane] = 20*math.log10(num/den) if min(num,den)>0 else None
    return {'format':'lp14_diagnostics_summary_v1','rows':rows,
            'missing_cases':missing,'invalid_cases':invalid,'startup_pass':gate('startup'),
            'both_STB_loops_pass':gate('stb'),'full_vs_half_Vpp_gain_change_dB':compression,
            'XT2_bias_change_approved':False,'FFE_SER':None}


if __name__=='__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--recovery-root',type=Path)
    a = p.parse_args()
    common.write_new(a.output,summarize(a.run_root.resolve(),
        a.recovery_root.resolve() if a.recovery_root else None))
