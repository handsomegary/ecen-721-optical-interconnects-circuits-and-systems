#!/usr/bin/env python3
"""Read pinned AC60 compact evidence and write a reproducible diagnostic JSON."""
import argparse
import bisect
import cmath
import collections
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import tarfile
import zipfile


OUTPUTS = Path(__file__).resolve().parents[1]
RESULTS = OUTPUTS / 'pam4_pnskew_comp_20261113_results'
PINS = {
    'tgz': '4204f256b9386bbb0d3d36b98521811e8fb01cd9dff22e65b45ce6f6b0f09203',
    'summary': '45819d80e7b259d6af8e6c6f00a8c402acca972412cbd993bba082f5a3a9be29',
    'r0_zip': '6cd2afb099c61a640eb783b998d290703bf1ff75707852114758d60d3b8fc95c',
}
FREQ = tuple(range(7, 57, 7))
WEIGHTS = (1.25, 2.5, 5., 10., 20., 40.)
REQUIRED_PS = .5 / 112e9 * 1e12


def need(condition, detail):
    if not condition:
        raise ValueError(detail)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def close(actual, expected, detail):
    need(math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-11), detail)


def db(value):
    return 20. * math.log10(value)


def source_evidence(path):
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        need(len(names) == len(archive.namelist()), 'Duplicate ZIP member')
        checksums = dict((line.split(None, 1)[1].strip(), line.split()[0])
                         for line in archive.read('SHA256SUMS.txt').decode().splitlines() if line.strip())
        need(set(checksums) == names - {'SHA256SUMS.txt'}, 'r0 SHA inventory differs')
        for name, digest in checksums.items():
            need(sha(archive.read(name)) == digest, 'r0 member SHA mismatch: ' + name)
        selected = {n: checksums[n] for n in ('comp_cell.py', 'comp_plan.json', 'comp_measure.py',
                    'comp_summary.py', 'pvt/cases/nominal_parent.scs.txt', 'r5_original/quiet.scs')}
        return selected, json.loads(archive.read('comp_plan.json'))['cases']


def check_trim_diff(text, case):
    additions = {line[1:].split()[0]: line[1:] for line in text.splitlines()
                 if line.startswith('+') and not line.startswith('+++') and not line.startswith('+//')}
    drive = case['drive']
    for name, active in [('XVin', drive == 'p'), ('PNCVN', drive == 'n')]:
        need(additions[name].endswith('mag=' + str(int(active))), 'AC drive mismatch: ' + name)
    if case['bypass']:
        need(not any(re.fullmatch(r'PNC[PN]\dT[NP]\d', key) for key in additions), 'Bypass contains trim TGs')
        return None
    result = {}
    for leg in 'PN':
        tag = 'PNC' + leg
        code = case[leg.lower() + '_code']
        vdd = case['vdd_V']
        gate_bits = []
        for bit, weight in enumerate(WEIGHTS):
            on = bool(code & (1 << bit))
            for side, voltage in [('N', vdd if on else 0.), ('P', 0. if on else vdd)]:
                name = '%sV%s%d' % (tag, side, bit)
                expected = '%s (%sG%s%d 0) vsource dc=%.9g' % (name, tag, side, bit, voltage)
                need(additions.get(name) == expected, 'Unexpected gate voltage/topology: ' + name)
            gate_bits.append(int(on))
            for section in range(4):
                stem = tag + str(section)
                capnode = '%sC%d' % (stem, bit)
                for side, bulk, primitive in [('N', '0', 'nmos_lvt'), ('P', 'PNC_VDD', 'pmos_lvt')]:
                    name = '%sT%s%d' % (stem, side, bit)
                    prefix = '%s (%s %sG%s%d %sM %s) %s l=30n w=1u multi=1 nf=1 ' % (
                        name, capnode, tag, side, bit, stem, bulk, primitive)
                    need(additions.get(name, '').startswith(prefix), 'TG instance geometry or wiring mismatch: ' + name)
                    mirror = name[:3] + ('N' if leg == 'P' else 'P') + name[4:]
                    need(additions[name].split(') ', 1)[1] == additions[mirror].split(') ', 1)[1],
                         'P/N exact native geometry tails differ')
                cap = '%sCB%d' % (stem, bit)
                need(additions.get(cap) == '%s (%s 0) capacitor c=%.9gf' % (cap, capnode, weight),
                     'Switched capacitor weight mismatch: ' + cap)
        need(sum(bool(re.fullmatch(tag + r'\dT[NP]\d', key)) for key in additions) == 48,
             'Expected exactly 48 TG MOS instances per leg')
        result[leg] = {'code': code, 'bits_MSB_first': ''.join(str(x) for x in gate_bits[::-1]),
                       'enabled_bits_LSB_index': [i for i, x in enumerate(gate_bits) if x],
                       'nominal_enabled_cap_fF_per_section': sum(w for w, x in zip(WEIGHTS, gate_bits) if x),
                       'TG_pairs': 24, 'TG_MOS_instances': 48}
    return result


def archive_evidence(tgz, summary_bytes, selected, plan):
    plan_by_id = {case['case_id']: case for case in plan if case['stage'] in
                  ('standalone_pilot_TT', 'standalone_pilot_endpoints')}
    need(len(plan_by_id) == 60, 'Expected exactly 60 predeclared pilot columns')
    groups, run_hashes, jobs, times, rss = {}, {}, [], [], []
    with tarfile.open(tgz, 'r:gz') as archive:
        names = {member.name for member in archive.getmembers() if member.isfile()}
        need(len(names) == sum(member.isfile() for member in archive.getmembers()), 'Duplicate TGZ member')
        def get(name):
            need(name in names, 'Missing compact evidence: ' + name)
            return archive.extractfile(name).read()
        need(get('review/ac60_summary.json') == summary_bytes, 'Archived and standalone summaries differ')
        expected = {'run/' + key + '/measurements.json' for key in plan_by_id}
        need({n for n in names if n.startswith('run/') and n.endswith('/measurements.json')} == expected,
             'AC60 measured case census differs')
        for case_id, template in plan_by_id.items():
            prefix = 'run/' + case_id + '/'
            files = {name: get(prefix + name) for name in ('case.json', 'measurements.json', 'completion.json',
                     'run_status.json', 'spectre.log', 'parent_diff.txt', 'raw_retirement_manual_20261113.json')}
            c, m, completion, status, retirement = [json.loads(files[name]) for name in
                ('case.json', 'measurements.json', 'completion.json', 'run_status.json', 'raw_retirement_manual_20261113.json')]
            need(all(c[k] == v for k, v in template.items()), 'Case differs from r0 plan: ' + case_id)
            need(c['load_fF'] == 0 and (c['bypass'] or c['p_code'] + c['n_code'] == 63), 'Unexpected load or noncomplementary code')
            need(m['case_id'] == status['case_id'] == retirement['case'] == case_id, 'Cross-case compact evidence')
            need(m['measurement_complete'] is True and completion['measurement_complete'] is True and
                 completion['measurement_sha256'] == retirement['measurement_sha256'] == sha(files['measurements.json']),
                 'Measurement completion binding mismatch')
            need(status['case_sha256'] == sha(files['case.json']) and m['run_status_sha256'] == sha(files['run_status.json']) and
                 status['spectre_log_sha256'] == sha(files['spectre.log']) and
                 status['plan_sha256'] == selected['comp_plan.json'], 'Case/runner/log/plan binding mismatch')
            need(status['status'] == 'spectre_completed' and status['exit_code'] == 0 and
                 status['cpus_allocated'] == 1 and status['solver_mode'] == 'classic' and
                 status['simulator_build'] == '23.1.0.722.isr15' and
                 status['input_deck_sha256_before'] == status['input_deck_sha256_after'] == m['bench_sha256'] ==
                 c['staged_source_sha256']['bench.scs'], 'AC solver or deck identity mismatch')
            need(c['staged_source_sha256']['parent_diff.txt'] == sha(files['parent_diff.txt']), 'Line-diff digest mismatch')
            need(re.search(rb'(?mi)^\s*spectre completes with\s+0\s+errors\b', files['spectre.log']), 'No clean solver log')
            inventory = {x['path']: (x['bytes'], x['sha256']) for x in status['raw_inventory']}
            removed = {x['path']: (x['bytes'], x['sha256']) for x in retirement['removed']}
            need(inventory == removed and len(inventory) == len(retirement['removed']) == len(status['raw_inventory']),
                 'Manual raw receipt inventory mismatch')
            mapping = check_trim_diff(files['parent_diff.txt'].decode(), c)
            corner = '%s_%s%d_v%03d_r%d' % (c['process'], 'm' if c['temperature_C'] < 0 else 'p',
                     abs(c['temperature_C']), round(c['vdd_V'] * 100), c['source_ohm'])
            code = -1 if c['bypass'] else c['p_code']
            groups.setdefault(corner, {}).setdefault(code, {})[c['drive']] = (m, mapping)
            run_hashes[case_id] = {'measurement_sha256': sha(files['measurements.json']), 'deck_sha256_attested': m['bench_sha256'],
                                   'parent_diff_sha256': sha(files['parent_diff.txt']), 'job_id': status['slurm_job_id']}
            jobs.append(int(status['slurm_job_id']))
            times.append(status['spectre_wall_seconds'])
            rss.append(status['child_peak_rss_KiB_after_solver'])
    return groups, run_hashes, {'job_ids': sorted(jobs), 'wall_s_min_max': [min(times), max(times)],
                                'peak_RSS_KiB_min_max': [min(rss), max(rss)]}


def trace_at(report, name, frequency_hz):
    grid, trace = report['frequency_Hz'], report['traces'][name]
    i = bisect.bisect_left(grid, frequency_hz)
    if i < len(grid) and grid[i] == frequency_hz:
        return complex(*trace[i])
    need(0 < i < len(grid), 'Frequency outside preserved grid')
    fraction = math.log(frequency_hz / grid[i-1]) / math.log(grid[i] / grid[i-1])
    return complex(*trace[i-1]) * (1-fraction) + complex(*trace[i]) * fraction


def matrix_at(p, n, names, frequency_hz):
    return tuple(trace_at(report, node, frequency_hz) for report, node in
                 ((p, names[0]), (n, names[0]), (p, names[1]), (n, names[1])))


def modes(matrix):
    p, x, y, n = matrix
    return (p-x-y+n)/2, p+x-y-n


def delay(transfer, grid_ghz):
    phases = [cmath.phase(value) for value in transfer]
    for i in range(1, len(phases)):
        phases[i] = phases[i-1] + math.remainder(phases[i]-phases[i-1], 2*math.pi)
    grid = [f * .001 for f in grid_ghz]
    phase_delay = [-v/(2*math.pi*f) for v, f in zip(phases, grid)]
    local_group = [-(b-a)/(2*math.pi*(h-g)) for a,b,g,h in zip(phases, phases[1:], grid, grid[1:])]
    fbar, pbar = statistics.mean(grid), statistics.mean(phases)
    fitted = -sum((f-fbar)*(p-pbar) for f,p in zip(grid, phases)) / sum((f-fbar)**2 for f in grid) / (2*math.pi)
    return phase_delay, local_group, fitted


def row_data(p, n):
    for report, drives in [(p, (1., 0.)), (n, (0., 1.))]:
        frequencies = report['frequency_Hz']
        need(len(frequencies) >= 350 and all(0 < a < b for a,b in zip(frequencies, frequencies[1:])), 'Bad AC grid')
        for node, expected in zip(('PNC_PREP','PNC_PREN'), drives):
            need(all(abs(complex(*v)-expected) < 1e-7 for v in report['traces'][node]), 'Wrong input source normalization')
    need(p['frequency_Hz'] == n['frequency_Hz'] and n['noise'] is None, 'P/N AC grid or noise scope differs')
    trim = [matrix_at(p,n,('X_ip','X_im'), f*1e9) for f in FREQ]
    afe = [matrix_at(p,n,('X_o_p','X_o_m'), f*1e9) for f in FREQ]
    diagonal = [[m[j] for m in trim] for j in (0,3)]
    p_delay, p_group, p_fit = delay(diagonal[0], FREQ)
    n_delay, n_group, n_fit = delay(diagonal[1], FREQ)
    differential = [a-b for a,b in zip(p_delay,n_delay)]
    local_group = [a-b for a,b in zip(p_group,n_group)]
    # Dense grid is diagnostic only. The eight-probe metric is reproduced above.
    dense_freq = sorted(set([7e9,56e9] + [f for f in p['frequency_Hz'] if 7e9 < f < 56e9]))
    dense = [matrix_at(p,n,('X_ip','X_im'), f) for f in dense_freq]
    dense_p, dense_pg, _ = delay([m[0] for m in dense], [f/1e9 for f in dense_freq])
    dense_n, dense_ng, _ = delay([m[3] for m in dense], [f/1e9 for f in dense_freq])
    dense_delay = [a-b for a,b in zip(dense_p,dense_n)]
    dense_group = [a-b for a,b in zip(dense_pg,dense_ng)]
    return {'d56_ps': differential[-1], 'differential_phase_delay_ps': differential,
            'differential_phase_delay_8probe_min_max_ps': [min(differential),max(differential)],
            'differential_phase_delay_8probe_span_ps': max(differential)-min(differential),
            'differential_phase_delay_dense_min_max_ps': [min(dense_delay),max(dense_delay)],
            'differential_group_delay_8probe_min_max_ps': [min(local_group),max(local_group)],
            'differential_group_delay_dense_min_max_ps': [min(dense_group),max(dense_group)],
            'dense_band_points': len(dense_freq), 'differential_phase_slope_fit_ps': p_fit-n_fit,
            'diagonal_leg_magnitude_56GHz_V_per_V': [abs(diagonal[0][-1]),abs(diagonal[1][-1])],
            'diagonal_leg_magnitude_56GHz_dB': [db(abs(x[-1])) for x in diagonal],
            'diagonal_leg_magnitude_7_to_56GHz_min_max_dB': [[min(db(abs(x)) for x in leg),max(db(abs(x)) for x in leg)] for leg in diagonal],
            'diagonal_leg_phase_delay_56GHz_ps': [p_delay[-1],n_delay[-1]],
            'diagonal_leg_magnitude_imbalance_P_over_N_dB': db(abs(diagonal[0][-1]/diagonal[1][-1])),
            'trim_offdiagonal_magnitude_56GHz_V_per_V': [abs(trim[-1][1]), abs(trim[-1][2])],
            'AFE_Hdd_56GHz_V_per_V': abs(modes(afe[-1])[0]),
            'input_noise_mVrms': p['noise']['Vrms']*1e3,
            'DC_power_W': sum(p['supply_power_W'].values())}, trim, afe, dense


def group_data(paired, original):
    need(set(paired) == {-1,0,16,32,48,63}, 'Sparse code census changed')
    records, trim_matrices, afe_matrices, dense_matrices = {}, {}, {}, {}
    base_afe = base_noise = base_dc = None
    for code in sorted(paired):
        drives = paired[code]
        need(set(drives) == {'p','n'}, 'Missing paired drive')
        p, p_mapping = drives['p']
        n, n_mapping = drives['n']
        need(p_mapping == n_mapping, 'Same code has different P/N instance mapping across drives')
        row, trim, afe, dense = row_data(p,n)
        trim_matrices[code], afe_matrices[code], dense_matrices[code] = trim, afe, dense
        if code == -1:
            base_afe, base_noise, base_dc = afe[-1], row['input_noise_mVrms'], row['DC_power_W']
        hdd, hdc = modes(afe[-1])
        base_hdd, base_hdc = modes(base_afe)
        row.update(Hdd_56_change_vs_bypass_dB=db(abs(hdd/base_hdd)),
                   CM_to_DM_delta_ratio_at_56GHz=abs(hdc-base_hdc)/abs(base_hdd),
                   input_noise_increase_mVrms=row['input_noise_mVrms']-base_noise,
                   input_noise_increase_percent=100*(row['input_noise_mVrms']/base_noise-1) if base_noise else None,
                   input_noise_variance_change_V2=(row['input_noise_mVrms']**2-base_noise**2)*1e-6,
                   DC_power_increment_vs_bypass_W=row['DC_power_W']-base_dc,
                   gate_instance_mapping=p_mapping)
        reference = original['cases'][str(code)]
        for key in ('Hdd_56_change_vs_bypass_dB', 'CM_to_DM_delta_ratio_at_56GHz',
                    'input_noise_variance_change_V2','DC_power_increment_vs_bypass_W'):
            close(row[key], reference[key], 'Summary metric differs: ' + key)
        close(row['d56_ps'], reference['differential_phase_delay_56GHz_ps'], 'Summary phase delay differs')
        close(row['input_noise_mVrms'], reference['noise']['Vrms']*1e3, 'Summary noise differs')
        for phase,p_delay,n_delay in zip(row['differential_phase_delay_ps'],
                                      reference['P_delay']['phase_delay_ps'],reference['N_delay']['phase_delay_ps']):
            close(phase, p_delay-n_delay, 'Summary probe delay differs')
        records[str(code)] = row
    def swap_error(matrices):
        a, b = matrices[0], matrices[63]
        pairs = [(x,y) for first, second in zip(a,b) for x,y in zip(first,second[::-1])]
        return max(abs(a-b) for a,b in pairs), max(abs(a) for a,b in pairs)
    d0, d63 = (records[str(k)]['d56_ps'] for k in (0,63))
    observed = [records[str(k)]['d56_ps'] for k in (0,16,32,48,63)]
    trim_error, trim_scale = swap_error(dense_matrices)
    afe_error, afe_scale = swap_error(afe_matrices)
    return {'codes': records, 'observed_numbered_codes': [0,16,32,48,63],
            'missing_mirror_codes': {'16':47, '32':31, '48':15},
            'd56_observed_min_max_ps': [min(observed),max(observed)],
            'd56_endpoint_span_ps': d63-d0, 'd56_endpoint_offsets_ps': [d0,d63],
            'd56_endpoint_span_percent_of_required': 100*(d63-d0)/(2*REQUIRED_PS),
            'd56_endpoint_midpoint_ps': (d0+d63)/2,
            'd56_observed_adjacent_steps_ps': [b-a for a,b in zip(observed,observed[1:])],
            'endpoint_swap': {'trim_dense_max_complex_matrix_difference_V_per_V': trim_error,
                              'trim_dense_max_relative_to_matrix_peak': trim_error/trim_scale,
                              'AFE_8probe_max_complex_matrix_difference_V_per_V': afe_error,
                              'AFE_8probe_max_relative_to_matrix_peak': afe_error/afe_scale}}


def analyze(tgz, summary, r0):
    paths = {'tgz': Path(tgz), 'summary': Path(summary), 'r0_zip': Path(r0)}
    inputs = {name: {'file': path.name, 'bytes': path.stat().st_size, 'sha256': sha(path.read_bytes())}
              for name,path in paths.items()}
    need(all(inputs[k]['sha256'] == expected for k,expected in PINS.items()), 'Input archive/summary SHA mismatch')
    source, plan = source_evidence(r0)
    summary_bytes = Path(summary).read_bytes()
    original = json.loads(summary_bytes)
    need(not original['invalid'] and len(original['AC']) == 5, 'AC60 original summary incomplete')
    groups, runs, resources = archive_evidence(tgz, summary_bytes, source, plan)
    need(set(groups) == set(original['AC']), 'AC60 group census differs')
    return {'format': 'pn_skew_ac60_independent_diagnostic_v1', 'inputs': inputs,
            'r0_source_member_sha256': source, 'native_runs_started': 0, 'AC_columns_verified': len(runs),
            'paired_code_points_verified': sum(len(v) for v in groups.values()), 'observed_resources': resources,
            'method': {'phase_delay': 'Unwrap diagonal trim-leg phases independently and compute -phase/(2*pi*f); d=P-N. This is phase delay, not group delay.',
                'group_delay': 'Finite differences of unwrapped phase; dense and eight-probe results reported separately.',
                'frequency_probes_GHz': FREQ, 'dense_scope_GHz': [7,56],
                'sparse_interpolation': 'Complex linear interpolation in log frequency, as original summary.',
                'endpoint_symmetry': 'Compare full H(0) against J H(63) J at identical frequency and source impedance; J exchanges P/N.',
                'noise': 'Saved P-driven stationary X_ip-X_im RMS integrated over 1MHz-56GHz, with r3 connected; no sampled noise or BER claim.',
                'phase_range_target_each_sign_ps': REQUIRED_PS,
                'compact_limit': 'Exact runner/deck hashes and actual parent diffs checked. The compact archive omits full runtime benches and raw PSF bytes.'},
            'conditions': {key: group_data(groups[key], original['AC'][key]) for key in sorted(groups)},
            'case_evidence': runs,
            'interpretation': {
                'verified_mapping': 'P=32 selects only bit 5 (40fF/section). N=31 selects bits 0-4 (38.75fF/section). Gates are complementary, all 24 native TG pairs per leg present, and P/N device parameter tails exactly match.',
                'what_data_support': 'Broadband differential delay varies strongly with frequency, sparse d56 samples are nonmonotone, endpoint P/N swap can be quantified independently, and source termination changes diagonal gain, mode conversion and noise.',
                'mechanism_limit': 'The 31-to-32 carry switches five low bits off and one MSB on per leg. Code-dependent effective TG loading and r3 input interaction are plausible. Symmetric endpoints and matched wiring do not prove the carry mechanism or exclude orientation-dependent intermediate behavior.',
                'missing_mirror_diagnostic': 'Measure k=31,47,15 with both drive directions to pair against k=32,16,48. Compare antisymmetric (d(k)-d(63-k))/2 and orientation-even (d(k)+d(63-k))/2 with per-leg complex swaps.',
                'separate_ablations': 'At fixed source impedance compare exact native TG vs controlled ideal switch with the same connected r3; independently compare loaded r3 vs the same declared symmetric substitute load while keeping each switch implementation fixed. Extract r3 input complex two-port admittance, not a guessed single capacitance.',
                'not_measured': 'No full 64-code DNL/INL, isolated mechanism, transistor nonideal transient, payload SER, post-layout, or compensator approval follows from AC60.'}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tgz', type=Path, default=RESULTS/'olympus_compact_ac60.tgz')
    parser.add_argument('--summary', type=Path, default=RESULTS/'ac60_summary.json')
    parser.add_argument('--r0', type=Path, default=OUTPUTS/'ECEN721_PAM4_PNSKEW_COMP_20261113_r0.zip')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.tgz, args.summary, args.r0)
    with args.output.open('x', encoding='utf-8') as out:
        json.dump(result, out, indent=2, sort_keys=True, allow_nan=False)
        out.write('\n')
    print('Verified %d AC columns across %d conditions' % (result['AC_columns_verified'],len(result['conditions'])))


if __name__ == '__main__':
    main()
