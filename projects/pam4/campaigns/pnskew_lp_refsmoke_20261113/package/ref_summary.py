"""Summarize reference-only DC and native OTA-only P/N smoke results."""
import argparse
from pathlib import Path

import gm_summary
import lp_summary as lp
import olympus_common as common
import ref_smoke as design
import summarize_acnext as modal

REFERENCE_DB = {'ss':-22.966,'ff':-18.915}
BYPASS_MW = {'ss':7.785,'ff':13.23}


def summarize(root):
    plan = common.read(design.PLAN)
    dc,ac,missing,invalid = [],[],[],{}
    paired = {}
    for case in plan['cases']:
        try:
            report = gm_summary.read_case(root,case,design.PLAN)
        except FileNotFoundError:
            missing.append(case['case_id'])
            continue
        except (ValueError,KeyError,OSError,TypeError) as error:
            invalid[case['case_id']] = str(error)
            continue
        if case['kind']=='dc':
            dc.append(dict(case,measurement=report,
                           within_5_percent=abs(report['reference_error_fraction'])<=.05,
                           within_2_percent=abs(report['reference_error_fraction'])<=.02))
        else:
            paired.setdefault(case['process'],{})[case['drive']] = (case,report)
    for corner,entries in paired.items():
        if set(entries)!={'p','n'}:
            continue
        case,p = entries['p']
        data = {side:val[1] for side,val in entries.items()}
        fs = p['frequency_Hz']
        matrix = modal.matrix(data,('X_o_p','X_o_m'))
        hdd = modal.db(abs(lp.hdd_at(fs,matrix,56e9)))
        v = p['DC_voltage_V']
        legs = [1000*sum(p['saved_mos_oppoint'][f'GMSH{leg}CS{i}']['ids']
                        for i in range(14)) for leg in 'PM']
        total = 1000*sum(p['DC_supply_power_W'].values())
        ac.append({'process':corner,'case_ids':[x[0]['case_id'] for x in entries.values()],
                   'reference_current':p['reference_current'],'leg_currents_mA':legs,
                   'max_tracking_error_fraction':max(abs(i/design.phy.TARGET-1) for i in legs),
                   'replica_minus_ref_mV':1000*(v['GMSR_D']-v['GMSR_REF']),
                   'OTA_gate_bias_V':v['GMSR_BIAS'],'total_mW':total,
                   'added_mW_vs_first12_r3_rounded':total-BYPASS_MW[corner],
                   'non_main_GF_rail_mW':1000*p['DC_supply_power_W']['GFVDD:p']-sum(legs)*case['vdd_V'],
                   'Hdd_56GHz_dB':hdd,'Hdd_vs_first12_ideal_rounded_dB':
                   hdd-REFERENCE_DB[corner] if hdd is not None else None,
                   'noise':p['noise'],'XT2p0':p['saved_mos_oppoint'].get('XT2p0'),
                   'OTA_OP':{n:f for n,f in p['saved_mos_oppoint'].items() if n.startswith('GMSQ')}})
    return {'format':'pam4_lp_refsmoke_summary_v1','dc':dc,'ota':ac,'missing_cases':missing,
            'invalid_cases':invalid,'integrated_design_signoff':False}


if __name__=='__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a = p.parse_args()
    common.write_new(a.output,summarize(a.run_root.resolve()))
