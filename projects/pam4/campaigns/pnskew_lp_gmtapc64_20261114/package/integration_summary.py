"""Score native LP14 separately for RF performance and bias accuracy."""
import argparse
from pathlib import Path

import drive_summary as old
import lp_integrate as design
import lp_summary as lp
import olympus_common as common
import summarize_acnext as modal


def key(case, **updates):
    row = dict(case,**updates)
    return (*lp.config(row),row['integration'])


def tracking(legs_mA, iref_A, target_mA=4.35):
    nominal_ref = target_mA*1e-3/14
    error = {'iref_error_fraction':iref_A/nominal_ref-1,
             'nominal_leg_error_fraction':[i/target_mA-1 for i in legs_mA]}
    measured_target = 14*iref_A*1000
    servo = [i/measured_target-1 for i in legs_mA] if measured_target>0 else None
    error.update(servo_leg_error_fraction=servo,
                 servo_within_2_percent=max(map(abs,servo))<=.02 if servo else False,
                 nominal_within_2_percent=max(map(abs,error['nominal_leg_error_fraction']))<=.02)
    return error


def summarize(root):
    cases = common.read(design.PLAN)['cases']
    results,missing,invalid = lp.read_pairs(root,cases,design.PLAN,key)
    bypass = {c['process']:p['p'] for c,p,_,_ in results.values() if c['launch']=='bypass'}
    rows = []
    for case,pair,matrix,op in results.values():
        p = pair['p']
        fs = p['frequency_Hz']
        proc = case['process']
        total = 1000*sum(p['DC_supply_power_W'].values())
        matrix56 = old.matrix_at(fs,matrix,56e9)
        z,hdc = modal.modes(matrix56)
        row = {k:v for k,v in case.items() if k!='drive'}
        row.update(total_mW=total,rail_mW={k:1000*v for k,v in p['DC_supply_power_W'].items()},
                   Hdd_56GHz_dB=modal.db(abs(z)),Hmatrix_56GHz=lp.complex_list(matrix56),
                   Hdc_56GHz_complex=lp.complex_list([hdc])[0],
                   Hdd_56_over_7GHz_dB=old.ratio(z,lp.hdd_at(fs,matrix,7e9)),
                   input_Y_56GHz_S=lp.complex_list(lp.pair_y(pair)),noise=p['noise'],
                   r3_stage2_tail={n:m for n,m in op.items() if n in ('XT2p0','XT2m0')})
        base = bypass.get(proc)
        if base:
            row['added_mW_vs_r3'] = total-1000*sum(base['DC_supply_power_W'].values())
        if case['integration']!='reference':
            dc = p['DC_voltage_V']
            devices = p['saved_mos_oppoint']
            legs = [1000*sum(devices[f'GMSH{leg}CS{i}']['ids'] for i in range(14)) for leg in 'PM']
            iref = p['reference_current']['recovered_A']
            offset = dc['GMSR_D']-dc['GMSR_REF']
            row.update(legs_mA=legs,iref_uA=iref*1e6,replica_minus_ref_mV=offset*1000,
                       replica_resistor_error_fraction=-offset/(462*iref) if iref>0 else None,
                       replica_voltage_within_2_percent=abs(offset)<=.02*462*iref if iref>0 else False,
                       non_main_mW=row['rail_mW']['GFVDD:p']-case['vdd_V']*sum(legs),
                       OTA_input_drain_diff_mV=(dc['GMSQO1']-dc['GMSQOM'])*1000,
                       bias_OP={n:v for n,v in devices.items() if n.startswith('GMSQ') or n=='GMSRCS0'})
            row.update(tracking(legs,iref))
            ref = results.get(key(case,launch='idealz50',integration='reference'))
            if ref and fs==ref[1]['p']['frequency_Hz']:
                gain = old.ratio(z,lp.hdd_at(fs,ref[2],56e9))
                gain7 = old.ratio(lp.hdd_at(fs,matrix,7e9),lp.hdd_at(fs,ref[2],7e9))
                limit = 10 if case['count_b']==0 else 14
                row.update(same_route_ideal_gain_delta_dB=gain,budget_mW=limit,
                           within_2dB=gain>=-2 if gain is not None else None,
                           excess_group_delay_ps=lp.excess_group_delay(fs,matrix,ref[2]),
                           excess_tilt_dB=gain-gain7 if gain is not None and gain7 is not None else None)
                if 'added_mW_vs_r3' in row:
                    row['power_margin_mW']=limit-row['added_mW_vs_r3']
                    row['gain_and_power_pass']=row['within_2dB'] and row['power_margin_mW']>=0
        rows.append(row)
    native = [r for r in rows if r['integration']=='native_direct']
    complete = len(native)==6 and all(r.get('gain_and_power_pass') is not None for r in native)
    return {'format':'lp14_native_integration_summary_v1','rows':rows,'missing_cases':missing,
            'invalid_cases':invalid,'all_six_gain_and_power_pass':all(r['gain_and_power_pass'] for r in native)
            if complete else None,'all_six_nominal_current_within_2_percent':all(
                r['nominal_within_2_percent'] for r in native) if len(native)==6 else None,
            'all_six_servo_within_2_percent':all(r['servo_within_2_percent'] for r in native)
            if len(native)==6 else None,'all_six_replica_voltage_within_2_percent':all(
                r['replica_voltage_within_2_percent'] for r in native) if len(native)==6 else None,
            'startup_verified':False,'stability_verified':False,'FFE_SER':None}


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    common.write_new(args.output,summarize(args.run_root.resolve()))
