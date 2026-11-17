"""Read the staged Spectre PSF ASCII and retain compact design evidence."""
import bisect
import cmath
import math
from pathlib import Path

from comp_cell import ROOT, UI
from pilot_controller import FREQUENCIES_HZ
from pvt.reference.psf_ascii import parse_file
import admit
import collect_r5
import olympus_common as common

AC_PORTS = ('PNC_PREP','PNC_PREN','X_ip','X_im','X_o_p','X_o_m','X_h0p','X_h0m')


def as_pair(value):
    return [value.real, value.imag]


def at(xs, values, x):
    j = bisect.bisect_left(xs, x)
    if j < len(xs) and xs[j] == x:
        return values[j]
    if j == 0 or j == len(xs):
        raise ValueError('Point outside saved frequency grid')
    a = math.log(x/xs[j-1])/math.log(xs[j]/xs[j-1])
    return values[j-1]*(1-a)+values[j]*a


def ac_report(ac, dc, noise, case):
    frequencies = [v.real for v in ac.values['freq']]
    admit.require(ac.sweep_names == ['freq'] and len(frequencies) >= 350 and
                  frequencies[0] <= 1000.01 and frequencies[-1] >= 56e9 and
                  all(0<a<b for a,b in zip(frequencies, frequencies[1:])), 'Incomplete AC grid')
    def trace(data, name, count):
        vals = data.values[name]
        admit.require(len(vals) == count and all(math.isfinite(z.real) and math.isfinite(z.imag) for z in vals),
                      'Incomplete or nonfinite trace ' + name)
        return vals
    cur = ('XVin:p','PNCVN:p')
    ports = AC_PORTS + (('PNCPS','PNCNS') if case['source_ohm'] and not case['bypass'] else ())
    records = {name: trace(ac,name,len(frequencies)) for name in ports+cur}
    expected = (1,0) if case['drive']=='p' else (0,1)
    for name, amplitude in zip(('PNC_PREP','PNC_PREN'),expected):
        admit.require(max(abs(x-amplitude) for x in records[name])<1e-7,'Unexpected AC source normalization')
    supplies = ('XVs:p',) if case['bypass'] else ('XVs:p','PNCVTRIM:p')+tuple(
        'PNC%sV%s%d:p'%(leg,gate,b) for leg in 'PN' for gate in 'NP' for b in range(6))
    currents = {name:trace(dc,name,1)[0].real for name in supplies}
    vdd = case['vdd_V']
    dc_voltages = {n:trace(dc,n,1)[0].real for n in ('X_ip','X_im','X_o_p','X_o_m')}
    supplies_power = {}
    for name,current in currents.items():
        voltage = vdd
        if name not in ('XVs:p','PNCVTRIM:p'):
            p_code, n_code = case['p_code'],case['n_code']
            code = p_code if name[3] == 'P' else n_code
            high = bool(code & (1 << int(name[6])))
            voltage = vdd if high == (name[5]=='N') else 0.
        supplies_power[name] = -voltage * current
    noise_out = None
    if noise is not None:
        fs = [x.real for x in noise.values['freq']]
        ys = trace(noise,'out',len(fs))
        admit.require(noise.unit('out') == 'V/sqrt(Hz)' and fs[0] <= 1.00001e6 and fs[-1] >= 56e9/1.06 and
                      all(a<b for a,b in zip(fs,fs[1:])) and all(v.imag==0 and v.real>=0 for v in ys),
                      'Noise sweep or amplitude-density units not admitted')
        dens = [z.real**2 for z in ys]
        area = sum((a+b)*(y-x)/2 for x,y,a,b in zip(fs,fs[1:],dens,dens[1:]))
        area += max(0.,56e9-fs[-1])*dens[-1]
        noise_out = {'Vrms':math.sqrt(area),'measured_frequency_endpoints_Hz':[fs[0],fs[-1]],
                     'terminal':'X_ip-X_im; stationary linearized input trim noise with r3 connected'}
    at56 = {n:at(frequencies,vs,56e9) for n,vs in records.items()}
    driver, pin, current = (('PNC_PREP','PNCPS','XVin:p') if case['drive']=='p' else
                            ('PNC_PREN','PNCNS','PNCVN:p'))
    if pin not in at56:
        pin = ('X_ip' if case['drive']=='p' else 'X_im') if case['bypass'] else driver
    y = -at56[current]/at56[pin] if abs(at56[pin])>1e-15 else None
    return {'format':'pn_comp_ac_v1','frequency_Hz':frequencies,
            'traces':{n:[as_pair(z) for z in vs] for n,vs in records.items()},
            'phasors_56GHz':{n:as_pair(v) for n,v in at56.items()},
            'driven_pin_input_admittance_56GHz_S':as_pair(y) if y is not None else None,
            'supply_terminal_currents_A':currents, 'supply_power_W':supplies_power,
            'DC_voltages_V':dc_voltages,'noise':noise_out}


def pilot_report(raw, stop, oversample=32):
    t = raw.values[raw.sweep_names[0]]
    step = UI/oversample
    admit.require(raw.sweep_names[0].lower()=='time' and t[0] <= step and t[-1] >= stop-step*1.01 and
                  all(b>a for a,b in zip(t,t[1:])), 'Pilot waveform incomplete')
    def window(index):
        start = 200e-12 + (128 + index*224)*UI
        stop = start + 224*UI
        samples = [j for j,x in enumerate(t) if start <= x < stop]
        admit.require(len(samples) >= 224*oversample-2 and all(t[j+1]-t[j]<=step*1.001 for j in samples[:-1]),
                      'Missing uniform pilot samples')
        result = {}
        for f in FREQUENCIES_HZ:
            kernel = [cmath.exp(-2j*math.pi*f*t[j]) for j in samples]
            values = []
            for node in ('X_ip','X_im'):
                signal = [raw.values[node][j] for j in samples]
                dc = sum(signal)/len(signal)
                values.append(as_pair(2*sum((x-dc)*w for x,w in zip(signal,kernel))/len(signal)))
            result[str(int(f))] = dict(zip(('p','n'),values))
        return result
    windows = [window(k) for k in range(4)]
    def pair_average(a,b):
        # Relative phase is coherent across windows even if the data spectrum differs.
        result = {}
        for f in a:
            ps = [complex(*x[f]['p']) for x in (a,b)]
            ns = [complex(*x[f]['n']) for x in (a,b)]
            energy = sum(abs(x)**2 for x in ns)
            admit.require(energy > 0, 'No N pilot energy')
            c = sum(p*n.conjugate() for p,n in zip(ps,ns))/energy
            n = complex(math.sqrt(energy/2))
            result[f] = {'p':as_pair(c*n),'n':as_pair(n)}
        return result
    return {'train':pair_average(*windows[:2]),'verify':pair_average(*windows[2:])}


def safe_raw(root, status, name, parser=parse_file, *, max_bytes=512*1024**2):
    path = root / 'raw' / name
    _, before = common.owned_file(root,path)
    admit.require(0 < before.st_size <= max_bytes,'Raw file outside supported size')
    found = [r for r in status['raw_inventory'] if r['path']=='raw/'+name]
    admit.require(len(found)==1 and common.same_identity(before,found[0]), 'Unattested raw output '+name)
    actual = common.sha(path)
    admit.require(found[0]['sha256']==actual, 'Unattested raw output '+name)
    collect_r5.ensure_end(path)
    data = parser(path)
    _, after = common.owned_file(root,path)
    admit.require(data.sha256==actual and common.same_identity(after,found[0]), 'Raw changed during parsing')
    return data


def collect(root, admission_path=None):
    case = common.read(root/'case.json')
    status = common.read(root/'run_status.json')
    deck_sha = common.sha(root/'bench.scs')
    admit.require(status['status']=='spectre_completed' and status['exit_code']==0 and
                  status['case_id']==case['case_id'] and
                  status['input_deck_sha256_before']==status['input_deck_sha256_after']==deck_sha,
                  'New solver completion does not bind the case')
    admit.require(status['spectre_log_sha256']==common.sha(root/'spectre.log') and
                  all(common.sha(root/n)==v for n,v in case['staged_source_sha256'].items()),
                  'Log or staged input SHA differs')
    if case['kind']=='ac':
        safe_raw(root,status,'dcOpInfo.info')
        ac,dc = [safe_raw(root,status,n) for n in ('acResponse.ac','dcOp.dc')]
        noise = safe_raw(root,status,'noiseResponse.noise') if case['drive']=='p' else None
        report = ac_report(ac,dc,noise,case)
    else:
        admitted = admit.read_admission(admission_path, verify=True)
        functions = collect_r5.original_functions(admitted['source_dir'])
        path = functions.a._raw_file(root)
        raw = safe_raw(root,status,Path(path).name,functions.a.parse_file)
        if case['kind']=='pilot':
            report = {'format':'pn_comp_blind_pilot_v1',
                      'observation':dict(p_code=case['p_code'],n_code=case['n_code'],
                                         **pilot_report(raw,case['stop_s']))}
        else:
            collect_r5.validate_raw(raw,case['stop_s'])
            frozen = admit.read_json(admitted['frozen_r5']['path'])
            report, rows = collect_r5.evaluate_records(functions,raw,frozen)
            held_stats = {}
            from skew.summarize_skew import percentile
            for point, polarity in (('primary',1),('secondary',-1)):
                levels = [[polarity*r[7] for r in rows if r[0]==point and r[8]==label] for label in range(4)]
                gaps = [percentile(b,.05)-percentile(a,.95) for a,b in zip(levels,levels[1:])]
                held_stats[point] = {'gaps_V':gaps,'min_gap_V':min(gaps)}
            rail_names = ['PNCVTRIM:p'] + ['PNC%sV%s%d:p'%(leg,gate,b)
                                           for leg in 'PN' for gate in 'NP' for b in range(6)]
            rail_power = {}
            for name in rail_names:
                current = raw.values[name]
                code = case['p_code'] if name[3]=='P' else case['n_code']
                voltage = case['vdd_V']
                if name!='PNCVTRIM:p' and bool(code & (1<<int(name[6]))) != (name[5]=='N'):
                    voltage = 0.
                lo = bisect.bisect_left(raw.values[raw.sweep_names[0]],report['results']['primary']['first_read_s'])
                hi = bisect.bisect_right(raw.values[raw.sweep_names[0]],report['results']['primary']['last_read_s'])
                admit.require(hi>lo and len(current)==len(raw.values[raw.sweep_names[0]]),'Incomplete new rail samples')
                rail_power[name] = -voltage*sum(current[lo:hi])/(hi-lo)
            import csv
            samples = root/'held_samples.csv'
            with samples.open('x',encoding='utf-8',newline='') as output:
                w = csv.writer(output); w.writerow(collect_r5.CSV_FIELDS); w.writerows(rows)
            short, short_rows = collect_r5.short_waveform(raw,frozen,functions)
            clip = root/'short_waveform.csv'
            admit.require(short.get('available') is True and short_rows, 'Original validation clip missing')
            with clip.open('x',encoding='utf-8',newline='') as output:
                w = csv.writer(output); w.writerow(collect_r5.SHORT_FIELDS); w.writerows(short_rows)
            fit = pilot_report(raw,case['stop_s'],oversample=8)
            report.update(format='pn_comp_payload_v1',held_csv_sha256=common.sha(samples),
                          held_sample_count=len(rows),frozen_r5_sha256=admitted['frozen_r5']['sha256'],
                          short_waveform=dict(short,rows=len(short_rows),sha256=common.sha(clip)),
                          early_validation_pilot=fit,
                          held_voltage_statistics=held_stats, trim_validation_mean_rail_W=rail_power,
                          independent_new_holdout=False, complete_physical_ADC=False)
    report.update(measurement_complete=True,case_id=case['case_id'],
                  bench_sha256=deck_sha,run_status_sha256=common.sha(root/'run_status.json'))
    common.write_new(root/'measurements.json',report)
    return report
