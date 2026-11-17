"""Report shared LP14 fixed-current gain, replica tracking, and budget closure."""
import argparse
from pathlib import Path

import drive_summary as inherited
import lp_bias as design
import lp_summary as lp
import olympus_common as common
import summarize_acnext as modal


def key(case, **updates):
    c = dict(case,**updates)
    return (*lp.config(c),c['bias_mode'],c['target_mA_per_leg'])


def summed_ids(report, prefix):
    op = report['saved_mos_oppoint']
    return 1000*sum(op[f'{prefix}{k}']['ids'] for k in range(design.N))


def tested_targets(rows):
    table = []
    for target in (*design.MAIN_TARGETS,*design.UPPER_TARGETS):
        group = [r for r in rows if r['target_mA_per_leg']==target]
        if not group:
            continue
        conditions = {(r['process'],r['count_b']):r for r in group}
        required = {(corner,count) for corner in ('ss','tt','ff') for count in (0,2)}
        complete = set(conditions)==required and all(r.get('provisional_gate_pass') is not None for r in group)
        gain_complete = set(conditions)==required and all(
            r.get('within_2dB_loss') is not None and 'increment_with_extra_reserve_mW' in r
            for r in group)
        table.append({'target_mA_per_leg':target,'matched_condition_count':sum(
            r.get('provisional_gate_pass') is not None for r in group),
            'complete_three_corner_single_and_dual':complete,
            'all_six_provisionally_pass':all(r['provisional_gate_pass'] for r in group) if complete else None,
            'all_six_meet_gain_and_tracking':all(
                r['within_2dB_loss'] and r['within_2percent_tracking'] for r in group) if gain_complete else None,
            'observed_worst_single_mW_with_reserve':max(
                r['increment_with_extra_reserve_mW'] for r in group if r['count_b']==0) if gain_complete else None,
            'observed_worst_dual_mW_with_reserve':max(
                r['increment_with_extra_reserve_mW'] for r in group if r['count_b']==2) if gain_complete else None})
    return table


def summarize(root):
    results, missing, invalid = lp.read_pairs(root,common.read(design.PLAN)['cases'],design.PLAN,key)
    base = {c['process']:(p,m) for c,p,m,_ in results.values() if c['launch']=='bypass'}
    rows = []
    for case,pair,matrix,margins in results.values():
        p = pair['p']
        fs = p['frequency_Hz']
        proc = case['process']
        z56 = inherited.matrix_at(fs,matrix,56e9)
        z,cm_dm = modal.modes(z56)
        power = 1000*sum(p['DC_supply_power_W'].values())
        worst = min(margins,key=lambda name:margins[name]['margin_V'])
        row = {k:v for k,v in case.items() if k!='drive'}
        row.update(total_mW=power,rail_mW={k:1000*v for k,v in p['DC_supply_power_W'].items()},
                   Hmatrix_56GHz=lp.complex_list(z56), Hdd_56GHz_dB=modal.db(abs(z)),
                   Hdc_56GHz_complex=lp.complex_list([cm_dm])[0],
                   Hdd_56_over_7GHz_dB=inherited.ratio(z,lp.hdd_at(fs,matrix,7e9)),
                   input_Y_56GHz_S=lp.complex_list(lp.pair_y(pair)),noise=p['noise'],
                   worst_active_MOS=worst,worst_active_headroom=margins[worst],
                   r3_stage2_tail={name:m for name,m in margins.items() if name in ('XT2p0','XT2m0')},
                   first_stage_CM_V=[p['DC_voltage_V'].get(n) for n in ('X_c_p','X_c_m')])
        if proc in base:
            ref_p, ref_m = base[proc]
            row['increment_vs_r3_mW'] = power-1000*sum(ref_p['p']['DC_supply_power_W'].values())
            if fs==ref_p['p']['frequency_Hz']:
                row['vs_r3_matched_bypass'] = modal.plane56(fs,matrix,ref_m)
        if case['launch']==design.SHARED:
            legs = [summed_ids(p,stem+'CS') for stem in ('GMSHP','GMSHM')]
            driver = sum(legs)*case['vdd_V']
            bias_rail = row['rail_mW']['GFVDD:p']
            row.update(main_leg_current_mA=legs,main_CS_ids_power_mW=driver,
                       GFVDD_non_main_difference_mW=bias_rail-driver,
                       bias_gate_DC_V=[p['DC_voltage_V'][name] for name in ('GMSHPFG','GMSHMFG')])
            limit = 10 if case['count_b']==0 else 14
            row['approved_increment_limit_mW'] = limit
            ref = results.get(key(case,launch='idealz50',bias_mode='reference',target_mA_per_leg=None))
            if ref and fs==ref[1]['p']['frequency_Hz']:
                ref_h = lp.hdd_at(fs,ref[2],56e9)
                gain = inherited.ratio(z,ref_h)
                d7 = inherited.ratio(lp.hdd_at(fs,matrix,7e9),lp.hdd_at(fs,ref[2],7e9))
                row['same_route_ideal_gain_delta_dB'] = gain
                row['within_2dB_loss'] = gain>=-2 if gain is not None else None
                row['extra_tilt_56_over_7GHz_dB'] = gain-d7 if gain is not None and d7 is not None else None
                row['excess_group_delay_ps'] = lp.excess_group_delay(fs,matrix,ref[2])
            if case['bias_mode']=='replica':
                target = case['target_mA_per_leg']
                tracking = max(abs(i/target-1) for i in legs)
                row.update(replica_bias_V=p['DC_voltage_V']['GMSR_BIAS'],
                           replica_drain_V=p['DC_voltage_V']['GMSR_D'],
                           replica_reference_V=p['DC_voltage_V']['GMSR_REF'],
                           replica_current_mA=1000*p['saved_mos_oppoint']['GMSRCS0']['ids'],
                           reference_sink_current_mA=1000*abs(p['DC_current_A']['GMSRIREF:p']),
                           largest_leg_tracking_error_fraction=tracking,
                           within_2percent_tracking=tracking<=.02)
                if 'increment_vs_r3_mW' in row:
                    estimate = row['increment_vs_r3_mW']+design.OVERHEAD_MW
                    row['increment_with_extra_reserve_mW'] = estimate
                    row['remaining_budget_after_reserve_mW'] = limit-estimate
                    row['within_budget_with_extra_reserve'] = estimate<=limit
                    if row.get('within_2dB_loss') is not None:
                        row['provisional_gate_pass'] = (
                            row['within_2dB_loss'] and tracking<=.02 and estimate<=limit)
        rows.append(row)
    return {'format':'lp_bias_summary_v1','rows':rows,'tested_targets':tested_targets(rows),
            'missing_cases':missing,'invalid_cases':invalid,
            'actual_bias_OTA_verified':False,'FFE_SER':None}


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    common.write_new(args.output,summarize(args.run_root.resolve()))
