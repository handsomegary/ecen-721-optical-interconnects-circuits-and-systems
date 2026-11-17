"""Summarize measured gain, reference, power and selected code spacing."""
import argparse
import cmath
import math
from pathlib import Path

from comp_measure import at
import drive_summary as inherited
import gm_drive_lp as design
import gm_summary
import olympus_common as common
import summarize_acnext as modal
import weighted_delay

RC_S = 100 * 85.26157665637249e-15


def config(case, **overrides):
    row = dict(case, **overrides)
    return (row['process'],row['launch'],row['source_R_ohm'],row['probe'],
            row['count_b'],tuple(map(tuple,row['route_thirds'])))


def complex_list(values):
    return [[value.real,value.imag] for value in values]


def hdd_at(frequencies, rows, hz):
    return modal.modes(inherited.matrix_at(frequencies,rows,hz))[0]


def read_pairs(root, cases):
    pairs, missing, invalid = {}, [], {}
    for case in cases:
        try:
            report = gm_summary.read_case(root, case, design.PLAN)
        except FileNotFoundError:
            missing.append(case['case_id'])
        except (KeyError, ValueError, TypeError, OSError) as error:
            invalid[case['case_id']] = str(error)
        else:
            pairs.setdefault(config(case),{})[case['drive']] = (case,report)
    results = {}
    for key, columns in pairs.items():
        if set(columns) != {'p','n'}:
            continue
        pair = {side:entry[1] for side,entry in columns.items()}
        case = columns['p'][0]
        try:
            bench = (root/case['case_id']/'bench.scs').read_text(encoding='ascii')
            margins = inherited.headroom(case,pair['p'],bench)
            matrix = modal.matrix(pair,('X_o_p','X_o_m'))
            results[key] = (case,pair,matrix,margins)
        except (KeyError, ValueError, TypeError, OSError) as error:
            invalid[case['case_id']] = str(error)
    return results, missing, invalid


def pair_y(pair):
    fs = pair['p']['frequency_Hz']
    return [-at(fs,[complex(*item) for item in pair[side]['traces'][node]],56e9)
            for node in ('XVin:p','PNCVN:p') for side in ('p','n')]


def launch_probes(case, pair):
    if case['topology'] == 'reference':
        return {}
    fs = pair['p']['frequency_Hz']
    names = ['GMS'+b+l+s for b in 'AB' for l in 'PM' for s in ('G','DRV:p','VD:p','FG','FD')]
    names.extend(['GMSH'+l+s for l in 'PM' for s in ('FG','FD')]+['LP2P','LP2N'])
    return {node:complex_list(at(fs,[complex(*z) for z in pair[side]['traces'][node]],56e9)
                             for side in 'pn')
            for node in names if node in pair['p']['traces']}


def excess_group_delay(fs, candidate, reference):
    samples = {}
    for hz in (7e9,14e9,28e9,42e9,55e9):
        points = (hz-.25e9,hz+.25e9)
        ratios = [hdd_at(fs,candidate,f)/z if abs(z)>1e-12 else None
                  for f,z in ((f,hdd_at(fs,reference,f)) for f in points)]
        samples[str(hz/1e9)] = (-cmath.phase(ratios[1]/ratios[0])/(math.tau*.5e9)*1e12
                                if all(r is not None and abs(r)>1e-12 for r in ratios) else None)
    return samples


def summarize(root):
    results, missing, invalid = read_pairs(root, common.read(design.PLAN)['cases'])
    bypass = {(c['process'],c['source_R_ohm']):(c,pair,matrix)
              for c,pair,matrix,_ in results.values() if c['launch']=='bypass'}
    rows, codes = [], {}
    for case, pair, matrix, margins in results.values():
        fs = pair['p']['frequency_Hz']
        matrix56 = inherited.matrix_at(fs,matrix,56e9)
        z, cm_dm = modal.modes(matrix56)
        hdd7 = hdd_at(fs,matrix,7e9)
        rails = pair['p']['DC_supply_power_W']
        driver = 1000*rails.get('GFVDD:p',0.) if case['topology'] in ('branch','shared') else 0.
        op_worst = min(margins,key=lambda name:margins[name]['margin_V'])
        row = {field:value for field,value in case.items() if field!='drive'}
        row.update(Hdd_56GHz_complex=complex_list([z])[0], Hdd_56GHz_dB=modal.db(abs(z)),
                   Hdc_56GHz_complex=complex_list([cm_dm])[0], Hmatrix_56GHz=complex_list(matrix56),
                   Hdd_56_over_7GHz_dB=inherited.ratio(z,hdd7), input_Y_56GHz_S=complex_list(pair_y(pair)),
                   power_mW=1000*sum(rails.values()), driver_rail_mW=driver, rails_W=rails,
                   active_MOS=margins, worst_active_MOS=op_worst,
                   noise=pair['p']['noise'], DC_nodes_V=pair['p']['DC_voltage_V'],
                   launch_probes_56GHz=launch_probes(case,pair))
        if case['probe']=='full':
            ref = results.get(config(case,launch='ideal'))
            if ref and case['launch']!='ideal' and fs==ref[1]['p']['frequency_Hz']:
                zref = hdd_at(fs,ref[2],56e9)
                row['extra_dB_vs_same_route_independent_ideal'] = inherited.ratio(z,zref)
                zref7 = hdd_at(fs,ref[2],7e9)
                row['excess_56_over_7GHz_tilt_dB'] = inherited.ratio(z*zref7,zref*hdd7)
                row['comparison_Z0_ohm'] = [case['Z0_ohm'],ref[0]['Z0_ohm']]
                row['excess_Hdd_group_delay_ps_at_GHz'] = excess_group_delay(fs,matrix,ref[2])
                row['added_total_mW_vs_same_route_ideal'] = (
                    row['power_mW']-1000*sum(ref[1]['p']['DC_supply_power_W'].values()))
                if case['topology']=='branch' and abs(zref)>0:
                    row['loss_under_2dB'] = abs(z/zref) > 10**(-2/20)
            if case['launch'] in ('direct','directz50'):
                name = 'direct_ideal' if case['launch']=='direct' else 'direct_idealz50'
                ref = results.get(config(case, launch=name))
                if ref and fs==ref[1]['p']['frequency_Hz']:
                    unloaded = 1/(1+math.tau*56e9*RC_S*1j)
                    row['extra_dB_vs_same_Z0_unloaded_channel'] = inherited.ratio(
                        z,hdd_at(fs,ref[2],56e9)*unloaded)
                row['unloaded_last_pole_H56_complex'] = complex_list([1/(1+math.tau*56e9*RC_S*1j)])[0]
        else:
            full = results.get(config(case,probe='full'))
            if full and fs==full[1]['p']['frequency_Hz']:
                selected = hdd_at(fs,full[2],56e9)-z
                if abs(selected)>0:
                    row['OFF_over_selected_56GHz_complex'] = complex_list([z/selected])[0]
                    row['OFF_over_selected_56GHz_dBc'] = modal.db(abs(z/selected))
        control = bypass.get((case['process'],case['source_R_ohm']))
        if control and fs==control[1]['p']['frequency_Hz'] and case['topology']!='direct':
            row['same_external_R_bypass'] = modal.plane56(fs,matrix,control[2])
            if case['probe']=='full':
                row['known_skew_scores_56GHz'] = {
                    str(ps):modal.plane56(fs,modal.cancel_input_skew(fs,matrix,ps),control[2])
                    for ps in (-weighted_delay.ENDPOINT_PS,0.,weighted_delay.ENDPOINT_PS)}
                if case['stage']=='fallback_fine':
                    ref_track = modal.matrix(control[1],('X_h0p','X_h0m'))
                    row['AFE_column_delay'] = weighted_delay.evaluate(
                        fs,inherited.column_projection(matrix),inherited.column_projection(control[2]),ref_track)
                    tau = row['AFE_column_delay']['bands']['7_to_56_GHz']['tau_effective_ps']
                    codes.setdefault((case['process'],case['segment']),{})[case['count_b']] = tau
        rows.append(row)
    spacing = []
    for (corner,segment),book in sorted(codes.items()):
        steps = {str(k):book[k+1]-book[k] for k in sorted(book)
                 if book[k] is not None and book.get(k+1) is not None}
        following = codes.get((corner,segment+1),{})
        seam = following[0]-book[8] if book.get(8) is not None and following.get(0) is not None else None
        spacing.append({'corner':corner,'segment':segment,'tau_by_code_ps':book,
                        'measured_adjacent_steps_ps':steps,'next_seam_ps':seam})
    return {'format':'pam4_gmdrive_lp_summary_v1','rows':rows,'fine_spacing':spacing,
            'missing_cases':missing,'invalid_cases':invalid,'FFE_SER':None}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    common.write_new(args.output,summarize(args.run_root.resolve()))
