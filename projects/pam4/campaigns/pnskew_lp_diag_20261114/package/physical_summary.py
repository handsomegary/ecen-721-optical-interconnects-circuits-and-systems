"""Measure physical bias closure against matched ideal and original r3 cases."""
import argparse
from pathlib import Path

import drive_summary as old
import lp_summary as lp
import olympus_common as common
import physical_bias as design
import summarize_acnext as modal


def key(case, **updates):
    c = dict(case,**updates)
    return (*lp.config(c),c['hardware'],c['ref_R_ohm'],c['miller_pF'])


def summarize(root):
    results,missing,invalid = lp.read_pairs(root,common.read(design.PLAN)['cases'],design.PLAN,key)
    controls = {c['process']:pair['p'] for c,pair,_,_ in results.values() if c['launch']=='bypass'}
    rows = []
    for case,pair,matrix,op in results.values():
        p = pair['p']
        fs = p['frequency_Hz']
        vdd = case['vdd_V']
        power = 1e3*sum(p['DC_supply_power_W'].values())
        z = lp.hdd_at(fs,matrix,56e9)
        row = {k:v for k,v in case.items() if k!='drive'}
        row.update(total_mW=power,rail_mW={k:1e3*v for k,v in p['DC_supply_power_W'].items()},
                   Hdd_56GHz_dB=modal.db(abs(z)),Hmatrix_56GHz=lp.complex_list(old.matrix_at(fs,matrix,56e9)),
                   Hdd_56_over_7GHz_dB=old.ratio(z,lp.hdd_at(fs,matrix,7e9)),
                   DC_voltage_V=p['DC_voltage_V'],noise=p['noise'],
                   r3_stage2={n:op[n] for n in ('XT2p0','XT2m0') if n in op})
        base = controls.get(case['process'])
        if base:
            row['added_mW_vs_r3']=power-1e3*sum(base['DC_supply_power_W'].values())
        if case['hardware']!='reference':
            ref = results.get(key(case,launch='idealz50',hardware='reference',ref_R_ohm=1800,miller_pF=2.))
            ideal = results.get(key(case,hardware='ideal',ref_R_ohm=1800,miller_pF=2.))
            if ref and fs==ref[1]['p']['frequency_Hz']:
                row['Hdd_56GHz_vs_ideal_dB'] = old.ratio(z,lp.hdd_at(fs,ref[2],56e9))
                row['excess_group_delay_ps'] = lp.excess_group_delay(fs,matrix,ref[2])
            devices = p['saved_mos_oppoint']
            legs = [1e3*sum(devices[f'GMSH{leg}CS{i}']['ids'] for i in range(14)) for leg in 'PM']
            row['legs_mA']=legs
            row['max_tracking_error_fraction']=max(abs(i/design.TARGET-1) for i in legs)
            row['iref_A']=p['reference_current']['recovered_A']
            row['bias_devices_OP']={n:fields for n,fields in devices.items()
                                    if n.startswith('GMSQ') or n=='GMSRCS0'}
            row['non_main_driver_rail_mW']=row['rail_mW']['GFVDD:p']-vdd*sum(legs)
            if ideal:
                row['total_mW_delta_vs_ideal_servo'] = power-1e3*sum(ideal[1]['p']['DC_supply_power_W'].values())
            if case['hardware'] in ('native_ref','native_both'):
                row['startup_kick_current_uA']=(p['DC_voltage_V']['GMSQBP']-p['DC_voltage_V']['GMSQK'])/50e3*1e6
            if case['hardware']=='native_both' and 'Hdd_56GHz_vs_ideal_dB' in row and 'added_mW_vs_r3' in row:
                row['gain_power_tracking_pass'] = (
                    row['Hdd_56GHz_vs_ideal_dB'] is not None and row['Hdd_56GHz_vs_ideal_dB']>=-2
                    and row['added_mW_vs_r3']<=(10 if case['count_b']==0 else 14)
                    and row['max_tracking_error_fraction']<=.02)
        rows.append(row)
    integrated = [r for r in rows if r['stage']=='core' and r['hardware']=='native_both']
    complete = len(integrated)==6 and all('gain_power_tracking_pass' in r for r in integrated)
    return {'format':'pam4_lp_physical_summary_v1','rows':rows,'missing_cases':missing,'invalid_cases':invalid,
            'integrated_all_six_static_pass':all(r['gain_power_tracking_pass'] for r in integrated)
            if complete else None,'startup_verified':False,'loop_stability_verified':False,'FFE_SER':None}


if __name__=='__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a = p.parse_args()
    common.write_new(a.output,summarize(a.run_root.resolve()))
