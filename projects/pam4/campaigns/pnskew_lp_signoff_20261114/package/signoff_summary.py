"""Report the replica extension and native peaking-coil sensitivity."""
import argparse
import math
from pathlib import Path

import drive_summary as old
import gm_summary
import lp_next as coil
import lp_signoff as design
import lp_summary as lp
import olympus_common as common
import summarize_acnext as modal


def key(case):
    return (case['process'],case['count_b'],case['variant_name'])


def summarize(root):
    cases = common.read(design.PLAN)['cases']
    ac = [c for c in cases if c['stage']=='passive']
    pairs,missing,invalid = lp.read_pairs(root,ac,design.PLAN,key)
    stb = []
    for c in cases[:4]:
        try:
            result = gm_summary.read_case(root,c,design.PLAN)
        except FileNotFoundError:
            missing.append(c['case_id'])
        except (ValueError,KeyError,TypeError,OSError) as err:
            invalid[c['case_id']] = str(err)
        else:
            stb.append(dict(case=c,result=result))
    rows = []
    for c,pair,matrix,op in pairs.values():
        proc,cb,variant = key(c)
        if variant in ('r3','ideal_route'):
            continue
        p = pair['p']
        fs = p['frequency_Hz']
        power = 1e3*sum(p['DC_supply_power_W'].values())
        matrix56 = old.matrix_at(fs,matrix,56e9)
        z,cm_to_dm = modal.modes(matrix56)
        row = dict(case=c,Hdd_56GHz_dB=modal.db(abs(z)),total_mW=power,noise=p['noise'],
                   rails_mW={k:v*1000 for k,v in p['DC_supply_power_W'].items()},
                   XT2={n:v for n,v in op.items() if n.startswith('XT2')},
                   Hmatrix_56GHz=lp.complex_list(matrix56),
                   Hdc_56GHz_re_im=lp.complex_list([cm_to_dm])[0])
        l,r,cp = coil.nonideal_values(c)
        series = complex(r,math.tau*56e9*l)
        zcoil = 1/(1/series+1j*math.tau*56e9*cp)
        row['coil'] = {'L_pH':l*1e12,'R_DCR_ohm':r,'Cp_fF':cp*1e15,
                       'Z56_re_im_ohm':[zcoil.real,zcoil.imag],
                       'effective_Q56':zcoil.imag/zcoil.real if zcoil.real>0 else None}
        devices = p['saved_mos_oppoint']
        legs = [1e3*sum(devices[f'GMSH{leg}CS{i}']['ids'] for i in range(14)) for leg in 'PM']
        iref = p['reference_current']['recovered_A']
        row.update(iref_uA=iref*1e6,legs_mA=legs,
                   max_leg_servo_error_fraction=max(abs(i/(14e3*iref)-1) for i in legs) if iref>0 else None,
                   drains_V=[p['DC_voltage_V'][f'GMSH{leg}FD'] for leg in 'PM'])
        ref = pairs.get((proc,cb,'ideal_route'))
        if ref and fs==ref[1]['p']['frequency_Hz']:
            loss = old.ratio(z,lp.hdd_at(fs,ref[2],56e9))
            low = old.ratio(lp.hdd_at(fs,matrix,7e9),lp.hdd_at(fs,ref[2],7e9))
            row.update(vs_ideal_route_dB=loss,within_2dB=loss>=-2 if loss is not None else None,
                       excess_tilt_dB=loss-low if loss is not None and low is not None else None,
                       excess_group_delay_ps=lp.excess_group_delay(fs,matrix,ref[2]))
        ideal = pairs.get((proc,cb,'ideal_coil'))
        if ideal and fs==ideal[1]['p']['frequency_Hz']:
            row['vs_ideal_coil_dB'] = old.ratio(z,lp.hdd_at(fs,ideal[2],56e9))
        baseline = pairs.get((proc,0,'r3'))
        if baseline:
            added = power-1e3*sum(baseline[1]['p']['DC_supply_power_W'].values())
            row.update(added_mW=added,within_power_budget=added<=(10 if cb==0 else 14))
        gates = (row.get('within_2dB'),row.get('within_power_budget'))
        row['gain_and_power_pass'] = all(gates) if None not in gates else None
        servo = row['max_leg_servo_error_fraction']
        row['servo_within_2_percent'] = servo<=.02 if servo is not None else None
        rows.append(row)
    return {'format':'lp14_signoff_ac_summary_v1','replica':stb,'passive':rows,
            'missing_cases':missing,'invalid_cases':invalid,'FFE_SER':None}


if __name__=='__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a = p.parse_args()
    common.write_new(a.output,summarize(a.run_root.resolve()))
