"""Report matched launch loss, headroom, and static code spacing from paired AC."""
import argparse
import math
import re
from pathlib import Path

from audit_gmfine_op import ANALOG, classify
from comp_measure import at
import gm_drive as drive
import gm_summary
import olympus_common as common
import summarize_acnext as modal
import weighted_delay

PLAN = drive.plan_path()
FIELDS = ('process', 'launch', 'source_R_ohm', 'gate_offset_mV', 'direction',
          'route_thirds', 'segment', 'count_b', 'probe')


def key(case, **updates):
    values = dict(case, **updates)
    return tuple(tuple(map(tuple, values[name])) if name == 'route_thirds' else values[name]
                 for name in FIELDS)


def hdd(frequency, matrix):
    return modal.modes(matrix_at(frequency, matrix, 56e9))[0]


def matrix_at(frequency, matrix, point):
    return [at(frequency, column, point) for column in zip(*matrix)]


def ratio(a, b):
    return modal.db(abs(a / b)) if abs(b) > 0 else None


def column_projection(matrix):
    return [(pp-np, 0, 0, nn-pn) for pp, pn, np, nn in matrix]


def headroom(case, record, deck):
    nodes = {name: pins.split() for name, pins in
             re.findall(r'^(\w+) \(([^\n)]+)\) [np]mos_lvt ', deck, re.M)}
    result = {}
    for name, pins in nodes.items():
        if not name.startswith(('GMS', 'XM1', 'XT1', 'XM2', 'XT2')):
            continue
        if re.fullmatch(r'GMSH[PM]CS\d+', name):
            role = 'CS_enabled'
        elif re.fullmatch(r'GMS[AB][PM]CS\d+', name):
            on = case['count_b'] != (8 if name[3] == 'A' else 0)
            role = 'CS_enabled' if on else 'CS_disabled'
        else:
            role = classify(name, pins, case)
        if role in ANALOG or role == 'CS_enabled':
            data = record['saved_mos_oppoint'].get(name, {})
            common.need(all(isinstance(data.get(f), (int, float)) and math.isfinite(data[f])
                            for f in ('vds', 'vdsat', 'ids', 'gm')), 'Incomplete active MOS OP: '+name)
            value = data['vds']-abs(data['vdsat'])  # enabled analog devices here are NMOS
            result[name] = {'role': role, 'margin_V': value, 'region': data.get('region'),
                            'ids_A': data.get('ids'), 'gm_S': data.get('gm')}
    common.need(bool(result), 'No saved active MOS with headroom fields')
    return result


def gate_row(case, pair, fs):
    stages = {}
    for bank in 'AB':
        for leg, side in (('P', 'p'), ('M', 'n')):
            prefix = 'GMS' + bank + leg
            record = pair[side]
            def z(node):
                return at(fs, [complex(*x) for x in record['traces'][node]], 56e9)
            stages[prefix] = {
                'drain_DC_V': record['DC_voltage_V'][prefix+'FD'],
                'bias_DC_V': record['DC_voltage_V'][prefix+'FG'],
                'line_pin_over_source_dB': ratio(z(prefix+'I'),
                    z('PNC_PREP' if leg == 'P' else 'PNC_PREN')),
                'drain_over_gate_dB': ratio(z(prefix+'FD'), z(prefix+'FG')),
            }
    return stages


def paired_rows(root, cases):
    pairs, missing, invalid = {}, [], {}
    for case in cases:
        try:
            report = gm_summary.read_case(root, case, PLAN)
        except FileNotFoundError:
            missing.append(case['case_id'])
        except (ValueError, KeyError, TypeError, OSError) as exc:
            invalid[case['case_id']] = str(exc)
        else:
            pairs.setdefault(key(case), {})[case['drive']] = (case, report)
    results = {}
    for config, values in pairs.items():
        if set(values) != {'p', 'n'}:
            continue
        pair = {side: value[1] for side, value in values.items()}
        case, p = values['p']
        path = root / case['case_id'] / 'bench.scs'
        try:
            results[config] = (case, pair, modal.matrix(pair, ('X_o_p', 'X_o_m')),
                               headroom(case, p, path.read_text(encoding='ascii')))
        except (ValueError, KeyError, TypeError, OSError) as exc:
            invalid[case['case_id']] = str(exc)
    return results, missing, invalid


def summarize(root):
    cases = common.read(PLAN)['cases']
    results, missing, invalid = paired_rows(root, cases)
    controls = {c['process']: (p, matrix) for c, p, matrix, _ in results.values()
                if c['launch'] == 'bypass'}
    rows, books = [], {}
    for case, pair, afe, margins in results.values():
        fs = pair['p']['frequency_Hz']
        z = hdd(fs, afe)
        matrix56 = matrix_at(fs, afe, 56e9)
        _, hdc = modal.modes(matrix56)
        hdd7, _ = modal.modes(matrix_at(fs, afe, 7e9))
        worst = min(margins, key=lambda name: margins[name]['margin_V'])
        power = sum(pair['p']['DC_supply_power_W'].values())
        row = {field: case[field] for field in FIELDS}
        row.update(stage=case['stage'], case_id_p=case['case_id'],
                   Hdd_56GHz_dB=modal.db(abs(z)), Hdd_56GHz_complex=[z.real, z.imag],
                   Hdc_56GHz_complex=[hdc.real, hdc.imag],
                   Hmatrix_56GHz_pp_pn_np_nn=[[v.real,v.imag] for v in matrix56],
                   Hdd_56_over_7GHz_dB=ratio(z, hdd7),
                   power_mW=power*1000, rails_W=pair['p']['DC_supply_power_W'],
                   noise=pair['p']['noise'], source_input_Y_56GHz_S=modal.source_load_at_56(pair),
                   worst_active_MOS=worst, worst_active_headroom=margins[worst],
                   active_MOS_headroom=margins)
        if case['launch'] in drive.LAUNCHES:
            row['CS_nodes'] = gate_row(case, pair, fs)
        ideal = results.get(key(case, launch='ideal'))
        if case['probe'] == 'full' and ideal and fs == ideal[1]['p']['frequency_Hz']:
            z0 = hdd(fs, ideal[2])
            row['launch_delta_dB_vs_same_route_ideal'] = ratio(z, z0)
            row['power_delta_mW_vs_same_route_ideal'] = (
                power-sum(ideal[1]['p']['DC_supply_power_W'].values()))*1000
            row['launch_gt_minus_2dB'] = abs(z0) > 0 and abs(z/z0) > 10**(-2/20)
        if case['probe'] == 'dormant':
            full = results.get(key(case, probe='full'))
            if full and fs == full[1]['p']['frequency_Hz']:
                selected = hdd(fs, full[2]) - z
                row['OFF_over_selected_56GHz_dBc'] = ratio(z, selected)
                if abs(selected) > 0:
                    leak = z/selected
                    row['OFF_over_selected_56GHz_complex'] = [leak.real, leak.imag]
        control = controls.get(case['process'])
        if control and fs == control[0]['p']['frequency_Hz']:
            ref_pair, ref_afe = control
            row['vs_matched_bypass'] = modal.plane56(fs, afe, ref_afe)
            if case['launch'] != 'bypass' and case['probe'] == 'full':
                target = weighted_delay.ENDPOINT_PS
                row['known_skew_scores_56GHz'] = {
                    str(ps): modal.plane56(fs, modal.cancel_input_skew(fs, afe, ps), ref_afe)
                    for ps in (-target, target)}
                track = modal.matrix(ref_pair, ('X_h0p', 'X_h0m'))
                fit = weighted_delay.evaluate(fs, column_projection(afe),
                                              column_projection(ref_afe), track)
                fit['plane'] = 'output P-N column responses under separate input P and N excitation'
                row['delay'] = fit
                if case['segment'] is not None:
                    group = (case['process'], case['direction'], case['launch'], case['segment'])
                    band = fit['bands']['7_to_56_GHz']
                    books.setdefault(group, {})[case['count_b']] = band['tau_effective_ps']
        rows.append(row)
    codebooks = []
    seams = []
    for group, book in sorted(books.items()):
        measured = sorted(book.items())
        increments = [b-a for (i, a), (j, b) in zip(measured, measured[1:])
                      if j == i+1 and a is not None and b is not None]
        monotone = (all(x>0 for x in increments) or all(x<0 for x in increments)) if increments else None
        max_step = max(map(abs, increments), default=None)
        codebooks.append({'process_direction_launch_segment': group, 'measured_code_delay_ps': measured,
                          'complete_nine_codes': all(book.get(k) is not None for k in range(9)),
                          'adjacent_steps_checked': len(increments), 'monotone_where_checked': monotone,
                          'max_measured_adjacent_step_ps': max_step,
                          'all_checked_steps_at_most_0p30_ps': max_step <= .30 and monotone
                          if max_step is not None else None})
        next_book = books.get((*group[:3], group[3]+1), {})
        if book.get(8) is not None and next_book.get(0) is not None:
            seams.append({'process_direction_launch_from_segment': group,
                          'next_code0_minus_this_code8_ps': next_book[0] - book[8]})
    return {'format': 'pam4_gmdrive_summary_v1', 'rows': rows, 'codebooks': codebooks,
            'seam_checks': seams, 'missing_cases': missing, 'invalid_cases': invalid, 'FFE_SER': None}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    common.write_new(args.output, summarize(args.run_root.resolve()))
