#!/usr/bin/env python3
"""Evaluate the existing passive TG selector from its compact TT AC records."""

import argparse
import bisect
import hashlib
import json
import math
from pathlib import Path
import tarfile


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARCHIVE = ROOT / 'pam4_pnskew_selector_20261113_results/olympus_compact_selector_tt.tgz'
PREFIX = 'run/sel_tt_p25_v090_'
FREQUENCY_HZ = 56e9
OMEGA = math.tau * FREQUENCY_HZ
SOURCE_OHM = 25.0
TERMINATION_OHM = 25.0
UNIT_L_H = 13e-12
UNIT_C_F = 20.8e-15
UNIT_R_OHM = 0.305
UNIT_WIDTH_UM = 3.0
MAX_LOSS_DB = 3.0
WIDTH_FACTORS = (1, 2, 4, 8, 12, 16, 24, 32, 48, 64, 96, 128, 256)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def pair(z):
    return [z.real, z.imag]


def multiply(a, b):
    return (a[0]*b[0]+a[1]*b[2], a[0]*b[1]+a[1]*b[3],
            a[2]*b[0]+a[3]*b[2], a[2]*b[1]+a[3]*b[3])


def inverse(a):
    det = a[0]*a[3]-a[1]*a[2]
    return a[3]/det, -a[1]/det, -a[2]/det, a[0]/det


def to_chain(y):
    a,b,c,d = y
    return -d/c, -1/c, (b*c-a*d)/c, -a/c


def to_y(chain):
    a,b,c,d = chain
    return d/b, c-d*a/b, -1/b, a/b


def ladder(count):
    arm = (1, (UNIT_R_OHM+1j*OMEGA*UNIT_L_H)/2, 0, 1)
    cell = multiply(multiply(arm, (1, 0, 1j*OMEGA*UNIT_C_F, 1)), arm)
    result = (1, 0, 0, 1)
    for _ in range(count):
        result = multiply(result, cell)
    return result


SHORT_ROUTE = ladder(6)
LONG_ROUTE = ladder(16)


def read_record(archive, stem, drive):
    case_id = f'sel_tt_p25_v090_{stem}_{drive}'
    directory = f'{PREFIX}{stem}_{drive}/'
    def record(filename):
        member = archive.getmember(directory + filename)
        if not member.isfile() or not 0 < member.size < 12*1024**2:
            raise ValueError(f'Invalid compact member: {member.name}')
        with archive.extractfile(member) as stream:
            return stream.read()
    payload = record('measurements.json')
    measurement = json.loads(payload)
    completion = json.loads(record('completion.json'))
    status_bytes = record('run_status.json')
    status = json.loads(status_bytes)
    if (measurement['measurement_complete'] is not True or completion['measurement_complete'] is not True
            or completion['measurement_sha256'] != sha(payload)
            or status['status'] != 'spectre_completed' or status['exit_code'] != 0
            or measurement['run_status_sha256'] != sha(status_bytes)
            or measurement['bench_sha256'] != status['input_deck_sha256_after']
            or measurement['case_id'] != case_id or status['case_id'] != case_id):
        raise ValueError(f'Compact evidence did not match the completed case: {case_id}')
    proof = {'case_id': case_id, 'measurement_sha256': sha(payload),
             'run_status_sha256': sha(status_bytes), 'bench_sha256': measurement['bench_sha256']}
    return measurement, proof


def read_pair(archive, stem):
    return [read_record(archive, stem, drive) for drive in 'pn']


def at(measurement, trace):
    grid = measurement['frequency_Hz']
    data = measurement['traces'][trace]
    i = bisect.bisect_left(grid, FREQUENCY_HZ)
    if i < len(grid) and grid[i] == FREQUENCY_HZ:
        return complex(*data[i])
    if not 0 < i < len(grid):
        raise ValueError('Measurement grid does not bracket 56 GHz')
    weight = math.log(FREQUENCY_HZ/grid[i-1])/math.log(grid[i]/grid[i-1])
    return (1-weight)*complex(*data[i-1])+weight*complex(*data[i])


def matrix(records, names):
    p, n = [record[0] for record in records]
    first, second = names
    return at(p, first), at(n, first), at(p, second), at(n, second)


def hdd(a):
    return (a[0]-a[1]-a[2]+a[3])/2


def ratio_db(value, reference):
    return 20*math.log10(abs(value/reference))


def device_admittance(records):
    ports = matrix(records, ('PNC_PREP','PNC_PREN'))
    currents = matrix(records, ('XVin:p','PNCVN:p'))
    return multiply(tuple(-i for i in currents), inverse(ports))


def reduced_output(load, paths):
    a,b,c,d = paths
    driver_term = 1+SOURCE_OHM*a
    current_drive = -c/driver_term
    shunt = d-SOURCE_OHM*c*b/driver_term
    transfer = inverse((load[0]+shunt, load[1], load[2], load[3]+shunt))
    return tuple(current_drive*v for v in transfer)


def path(switch, route):
    return to_y(multiply(multiply(switch, route), switch))


def loaded_gain(y_on, y_off, factor, load, reference, include_off):
    selected = path(to_chain(tuple(factor*x for x in y_on)), SHORT_ROUTE)
    if include_off:
        unselected = path(to_chain(tuple(factor*x for x in y_off)), LONG_ROUTE)
        selected = tuple(a+b for a,b in zip(selected, unselected))
    return ratio_db(hdd(reduced_output(load, selected)), hdd(reference))


def search_peak(function):
    # Scan the broad width domain before refining the best bracket. The
    # continuous peak is a sizing diagnostic. Actual fingers are discrete.
    grid = [i/250 for i in range(-250, 1251)]
    samples = [(function(10**value), value) for value in grid]
    best_index = max(range(len(samples)), key=lambda i: samples[i][0])
    if best_index == 0 or best_index == len(grid)-1:
        gain, factor = samples[best_index]
        return 10**factor, gain, True
    low, high = grid[best_index-1], grid[best_index+1]
    for _ in range(60):
        first = low+(high-low)/3
        second = high-(high-low)/3
        if function(10**first) < function(10**second):
            low = first
        else:
            high = second
    factor = 10**((low+high)/2)
    return factor, function(factor), False


def series_only_limit(load, reference):
    low, high = 0.0, 100.0
    for _ in range(55):
        ron = (low+high)/2
        output = reduced_output(load, path((1, ron, 0, 1), SHORT_ROUTE))
        if ratio_db(hdd(output),hdd(reference)) >= -MAX_LOSS_DB:
            low = ron
        else:
            high = ron
    return low


def generate(archive_path):
    archive_path = Path(archive_path)
    with archive_path.open('rb') as stream:
        archive_sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    with tarfile.open(archive_path) as archive:
        bp = read_pair(archive,'bypass_native_f0_00_00_na')
        reference = matrix(bp, ('X_ip','X_im'))
        bypass_afe = matrix(bp, ('X_o_p','X_o_m'))
        load = tuple((v-int(i in (0,3)))/SOURCE_OHM for i,v in enumerate(inverse(reference)))
        ideal = read_pair(archive,'ttd_mid_direct_mid_f0_06_06_na')
        ideal_loss = ratio_db(hdd(matrix(ideal, ('X_o_p','X_o_m'))),hdd(bypass_afe))
        ron_limit = series_only_limit(load, reference)
        fits = {}
        for bias in ('native','mid'):
            on = read_pair(archive,f'device_{bias}_f1_00_00_on')
            off = read_pair(archive,f'device_{bias}_f1_00_00_off')
            y_on, y_off = device_admittance(on), device_admittance(off)
            z_on = -2/(y_on[1]+y_on[2])
            coff = -(y_off[1]+y_off[2]).imag/(2*OMEGA)
            con_shunt = (y_on[0]+y_on[1]+y_on[2]+y_on[3]).imag/(2*OMEGA)
            min_factor = z_on.real/ron_limit
            def evaluate(factor, include_off=True):
                return loaded_gain(y_on,y_off,factor,load,reference,include_off)
            optima = {}
            for include_off in (True, False):
                factor, gain, at_boundary = search_peak(lambda width: evaluate(width,include_off))
                nearest_integer = max(1, round(factor))
                optima['full_mux' if include_off else 'on_only'] = {
                    'continuous_factor': factor, 'um_per_polarity': factor*UNIT_WIDTH_UM,
                    'gain_dB': gain, 'at_search_boundary': at_boundary,
                    'nearest_integer_fingers': nearest_integer,
                    'nearest_integer_gain_dB': evaluate(nearest_integer,include_off),
                }
            fits[bias] = {'isolated_device_measurement': {
                            'on_proof': [x[1] for x in on], 'off_proof': [x[1] for x in off],
                            'Y_on_S_pp_pn_np_nn': list(map(pair,y_on)), 'Y_off_S_pp_pn_np_nn': list(map(pair,y_off)),
                            'on_transfer_Z_ohm': pair(z_on), 'off_mutual_C_fF': coff*1e15,
                            'on_terminal_shunt_C_fF': con_shunt*1e15,
                            'Ron_times_Coff_fs': z_on.real*coff*1e15,
                            'Ron_times_on_terminal_shunt_C_fs': z_on.real*con_shunt*1e15},
                          'series_only_width_lower_bound_um': min_factor*UNIT_WIDTH_UM,
                          'linear_Coff_at_that_width_fF': min_factor*coff*1e15,
                          'linear_on_terminal_shunt_C_at_that_width_fF': min_factor*con_shunt*1e15,
                          'best_modeled_widths': optima,
                          'width_sweep': [{'finger_factor': k, 'um_per_polarity': k*UNIT_WIDTH_UM,
                                           'linear_Ron_ohm': z_on.real/k, 'linear_Coff_fF': coff*k*1e15,
                                           'linear_on_terminal_shunt_C_fF': con_shunt*k*1e15,
                                           'full_mux_gain_dB': evaluate(k), 'on_only_gain_dB': evaluate(k,False)}
                                          for k in WIDTH_FACTORS],
                          'meets_3dB_loss_screen_in_model': optima['full_mux']['gain_dB'] >= -MAX_LOSS_DB}
        scale_check = {}
        for state in ('on','off'):
            m = read_pair(archive,f'device_mid_f4_00_00_{state}')
            actual = device_admittance(m)
            expected = [4*complex(*p) for p in fits['mid']['isolated_device_measurement'][f'Y_{state}_S_pp_pn_np_nn']]
            scale_check[state] = {'measured_f4_proof': [x[1] for x in m],
                                  'measured_f4_Y_S_pp_pn_np_nn': list(map(pair,actual)),
                                  'max_relative_mismatch_to_four_parallel_f1': max(abs(x-y) for x,y in zip(actual,expected))/max(map(abs,actual))}
        checks = []
        for variant,bias,k,include_off in (('ttd_switch','native',1,True),('ttd_on_only','native',1,False),
                                           ('ttd_mid_mux','mid',1,True),('ttd_mid_mux','mid',4,True),
                                           ('ttd_mid_on_only','mid',4,False)):
            actual = read_pair(archive,f'{variant}_{bias}_f{k}_06_06_na')
            observed_trim = ratio_db(hdd(matrix(actual, ('X_ip','X_im'))),hdd(reference))
            observed_afe = ratio_db(hdd(matrix(actual, ('X_o_p','X_o_m'))),hdd(bypass_afe))
            source = fits[bias]['isolated_device_measurement']
            y_on = tuple(complex(*p) for p in source['Y_on_S_pp_pn_np_nn'])
            y_off = tuple(complex(*p) for p in source['Y_off_S_pp_pn_np_nn'])
            modeled = loaded_gain(y_on,y_off,k,load,reference,include_off)
            checks.append({'variant': variant, 'bias': bias, 'finger_factor': k,
                           'measured_trim_gain_dB': observed_trim, 'measured_AFE_gain_dB': observed_afe,
                           'modeled_trim_gain_dB': modeled, 'model_minus_measured_trim_dB': modeled-observed_trim,
                           'measurement_proof': [x[1] for x in actual]})
    lf_bound = (SOURCE_OHM+TERMINATION_OHM+6*UNIT_R_OHM)/2*(10**((MAX_LOSS_DB+ideal_loss)/20)-1)
    return {'format': 'pam4_tg_width_model_v1', 'status': 'OFFLINE_MEASURED_Y_SCALING_MODEL',
            'source_archive_name': archive_path.name, 'source_archive_sha256': archive_sha,
            'frequency_Hz': FREQUENCY_HZ, 'process_temperature_C_vdd_V': ['TT',25,0.9],
            'source_ohm_per_leg': SOURCE_OHM, 'termination_ohm_per_leg': TERMINATION_OHM,
            'bypass_measurement_proof': [x[1] for x in bp], 'ideal_midrail_06_06_proof': [x[1] for x in ideal],
            'Y_load_S_pp_pn_np_nn_including_termination': list(map(pair,load)),
            'modeled_ladder': {'short_sections': 6, 'dormant_sections': 16, 'section_L_H': UNIT_L_H,
                               'section_C_F': UNIT_C_F, 'section_R_ohm': UNIT_R_OHM},
            'loss_screen': {'equal_length_gain_min_dB': -MAX_LOSS_DB, 'observed_ideal_06_06_AFE_gain_dB': ideal_loss,
                            'matched_50ohm_dc_style_Ron_limit_ohm_per_selected_switch': lf_bound,
                            'measured_complex_load_series_only_Ron_limit_ohm_per_selected_switch': ron_limit,
                            'width_limit_method': 'First remove all shunts and unused path. Bisect the two equal positive series resistances for a 3 dB loss at 56 GHz with the same measured complex bypass load. Convert using measured Re(Ztransfer)/width scaling. This is a series-only sizing bound, conditional on this fixed load and route.'},
            'width_model': fits, 'parallel_f4_measured_check': scale_check, 'measured_loaded_validation': checks,
            'width_search_factors': [0.1, 100000.0],
            'scope': ['Scale every measured complex 2x2 device Y element linearly with count, including OFF transfer, terminal shunts and conductance. Cascade two ON switches around the 6-section path and add the OFF branch admittance around the 16-section path.',
                      'Matched measured fixture is TT, 25 ohm source and termination per leg, with the fixed-track r3 load. Ideal bias-isolation components are approximated at 56 GHz. Results apply to this topology and device/bias range. Larger native devices, changed bias, retuned routes, layout parasitics and corners require their own characterization.',
                      'Equal-length 06/06 loss is a necessary screening condition. Endpoint delay versus width and FFE SER were not evaluated. This result does not establish a universal TG feasibility bound.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    rendered = json.dumps(generate(args.archive),indent=2,allow_nan=False)+'\n'
    if args.output:
        with args.output.open('x',encoding='utf-8') as stream:
            stream.write(rendered)
    else:
        print(rendered,end='')


if __name__ == '__main__':
    main()
