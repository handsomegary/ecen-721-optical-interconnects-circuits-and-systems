"""Paired gain and power gates, passive sensitivity, and code/seam measurements."""
import argparse
import math
from pathlib import Path

import drive_summary as old
import lp_next as design
import lp_summary as lp
import olympus_common as common
import summarize_acnext as modal
import weighted_delay as delay


def config(case, **changes):
    row = dict(case, **changes)
    return (*lp.config(row),row['coil_Q56'],row['coil_SRF_GHz'],row['coil_scale'])


IDEAL_COIL = dict(coil_Q56=None,coil_SRF_GHz=None,coil_scale=1.)


def branch_current_ratio(probes, count_b):
    if count_b not in (0,8):
        return None
    a,b = ('A','B') if count_b==0 else ('B','A')
    def idm(bank):
        p,n = [probes.get('GMS'+bank+leg+'VD:p') for leg in 'PM']
        if p is None or n is None:
            return None
        pp,pn = map(lambda z:complex(*z),p)
        np,nn = map(lambda z:complex(*z),n)
        return (pp-pn-np+nn)/2
    selected,dormant = idm(a),idm(b)
    if selected is not None and dormant is not None and abs(selected)>0:
        z = dormant/selected
        return {'dBc':modal.db(abs(z)), 'complex':lp.complex_list([z])[0]}
    return None


def db_relative(fs, candidate, reference, hz):
    return old.ratio(lp.hdd_at(fs,candidate,hz),lp.hdd_at(fs,reference,hz))


def book_reports(books):
    rows = []
    for (process,direction),segments in sorted(books.items()):
        segment_rows, seams = [], []
        for segment, entries in sorted(segments.items()):
            steps = {k:entries[k+1]-entries[k] for k in sorted(entries)
                     if entries[k] is not None and entries.get(k+1) is not None}
            # In the + fixture P gets longer and N gets shorter with code,
            # so the fitted P-minus-N delay increases. Check the declared
            # physical orientation below rather than trusting the code order.
            expected = direction
            gap = max((abs(v) for v in steps.values()),default=None)
            segment_rows.append({'segment':segment,'code_tau_ps':entries,'adjacent_steps_ps':steps,
                                 'all_nine_resolved':all(entries.get(i) is not None for i in range(9)),
                                 'monotone_where_measured':all(expected*v>0 for v in steps.values()) if steps else None,
                                 'largest_measured_step_ps':gap,
                                 'within_0p30ps_where_measured':gap<=.30 if gap is not None else None})
            following = segments.get(segment+1,{})
            if entries.get(8) is not None and following.get(0) is not None:
                seams.append({'after_segment':segment,'next_code0_minus_this_code8_ps':following[0]-entries[8]})
        measured = [(segment,code,tau) for segment,entries in segments.items()
                    for code,tau in entries.items() if tau is not None]
        target_tau = -direction*delay.ENDPOINT_PS
        nearest = min(measured,key=lambda item:abs(item[2]-target_tau),default=None)
        rows.append({'process':process,'direction':direction,'segments':segment_rows,'seams':seams,
                     'tau_min_ps':min((item[2] for item in measured),default=None),
                     'tau_max_ps':max((item[2] for item in measured),default=None),
                     'target_tau_ps':target_tau,
                     'closest_measured_code_offline':dict(segment=nearest[0],code=nearest[1],
                         tau_ps=nearest[2],residual_ps=nearest[2]-target_tau) if nearest else None})
    return rows


def summarize(root):
    plan = common.read(design.PLAN)
    results, missing, invalid = lp.read_pairs(root,plan['cases'],design.PLAN,config)
    bypass = {c['process']:(p,m) for c,p,m,_ in results.values() if c['launch']=='bypass'}
    rows, books = [], {}
    for case,pair,matrix,margins in results.values():
        fs = pair['p']['frequency_Hz']
        proc, launch = case['process'],case['launch']
        rails = pair['p']['DC_supply_power_W']
        z = lp.hdd_at(fs,matrix,56e9)
        mixed = old.matrix_at(fs,matrix,56e9)
        _, hdc = modal.modes(mixed)
        worst = min(margins,key=lambda n:margins[n]['margin_V'])
        power = 1000*sum(rails.values())
        row = {k:v for k,v in case.items() if k!='drive'}
        row.update(total_mW=power,rail_mW={k:1000*v for k,v in rails.items()},
                   driver_rail_mW=1000*rails.get('GFVDD:p',0.) if launch in (design.BRANCH,design.SHARED) else 0.,
                   Hdd_56GHz_dB=modal.db(abs(z)), Hdd_56_over_7GHz_dB=old.ratio(z,lp.hdd_at(fs,matrix,7e9)),
                   Hdc_56GHz_complex=lp.complex_list([hdc])[0],Hmatrix_56GHz=lp.complex_list(mixed),
                   input_Y_56GHz_S=lp.complex_list(lp.pair_y(pair)),noise=pair['p']['noise'],
                   DC_nodes_V=pair['p']['DC_voltage_V'],worst_active_MOS=worst,
                   worst_active_headroom_V=margins[worst]['margin_V'],active_MOS_OP=margins,
                   launch_probes_56GHz=lp.launch_probes(case,pair))
        if launch in (design.BRANCH,design.SHARED):
            row['dormant_over_active_differential_bank_drain_current_56GHz'] = (
                branch_current_ratio(row['launch_probes_56GHz'],case['count_b']))
            ref_name = 'idealz50' if launch==design.SHARED else 'ideal'
            ref = results.get(config(case,launch=ref_name,**IDEAL_COIL))
            if ref and fs==ref[1]['p']['frequency_Hz']:
                penalty = db_relative(fs,matrix,ref[2],56e9)
                db7 = db_relative(fs,matrix,ref[2],7e9)
                row['same_Z0_ideal_gain_delta_56GHz_dB'] = penalty
                row['within_2dB_loss'] = penalty>=-2 if penalty is not None else None
                row['additional_tilt_dB'] = penalty-db7 if penalty is not None and db7 is not None else None
                row['excess_Hdd_group_delay_ps_at_GHz'] = lp.excess_group_delay(fs,matrix,ref[2])
            limit = 10 if case['count_b'] in (0,8) else 14
            row['budget_increment_mW'] = limit
            # Shared keeps one driver pair active; the cap is selected by
            # how many r3 transconductor banks the code enables.
            if proc in bypass:
                added = power-1000*sum(bypass[proc][0]['p']['DC_supply_power_W'].values())
                row['added_mW_vs_r3'] = added
                row['within_increment_budget'] = added<=limit
                if row.get('within_2dB_loss') is not None:
                    row['gain_and_power_pass'] = row['within_2dB_loss'] and row['within_increment_budget']
            if case['stage']=='passive' and any(case[k]!=v for k,v in IDEAL_COIL.items()):
                l,r,c = design.nonideal_values(case)
                omega = math.tau*56e9
                series = complex(r,omega*l)
                port = 1/(1/series+1j*omega*c)
                resonance_squared = 1/(l*c)-(r/l)**2 if c else 0.
                row['coil_model'] = {'L_pH':l*1e12,'series_R_DC_and_RF_ohm':r,'parallel_C_fF':c*1e15,
                                     'Z_56GHz_ohm':lp.complex_list([port])[0],
                                     'terminal_Q_56GHz':port.imag/port.real if port.real>0 else None,
                                     'terminal_SRF_GHz':math.sqrt(resonance_squared)/math.tau/1e9
                                     if resonance_squared>0 else None}
                prior = results.get(config(case,**IDEAL_COIL))
                if prior and fs==prior[1]['p']['frequency_Hz']:
                    row['delta_vs_ideal_coil_56GHz_dB'] = db_relative(fs,matrix,prior[2],56e9)
        if proc in bypass and fs==bypass[proc][0]['p']['frequency_Hz']:
            p,ref = bypass[proc]
            track = modal.matrix(p,('X_h0p','X_h0m'))
            row['vs_r3_matched_bypass'] = modal.plane56(fs,matrix,ref)
            if launch in (design.BRANCH,design.SHARED):
                fit = delay.evaluate(fs,old.column_projection(matrix),old.column_projection(ref),track)
                row['AFE_column_delay'] = fit
                row['known_skew_offline_only'] = {
                    str(ps):modal.plane56(fs,modal.cancel_input_skew(fs,matrix,ps),ref)
                    for ps in (-delay.ENDPOINT_PS,0.,delay.ENDPOINT_PS)}
                if case['stage']=='fine':
                    book = books.setdefault((proc,case['direction']),{}).setdefault(case['segment'],{})
                    book[case['count_b']] = fit['bands']['7_to_56_GHz']['tau_effective_ps']
        rows.append(row)
    return {'format':'lp_next_summary_v1','rows':rows,'codebooks':book_reports(books),
            'missing_cases':missing,'invalid_cases':invalid,'FFE_SER':None}


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    common.write_new(args.output,summarize(args.run_root.resolve()))
