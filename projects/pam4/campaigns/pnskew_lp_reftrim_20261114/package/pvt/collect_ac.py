#!/usr/bin/env python3
"""Collect an r3 fixed-track PVT run with the frozen PSF parser and interpolator."""
import argparse
import json
import math
import re
from pathlib import Path

from generate import bench, need, sha
from model_preflight import load
from psf_ascii import parse_file

MAX_RAW_BYTES = 32*1024*1024
NYQUIST = 56e9
LOW_FREQ = 1e3


def finite(value):
    return math.isfinite(value.real) and math.isfinite(value.imag)


def gain_db(magnitude):
    return 20*math.log10(magnitude) if magnitude>0 else None


def validate_sweep(data, sweep, low, high, points_per_decade):
    need(data.sweep_names == [sweep], 'Expected one '+sweep+' sweep')
    xs = data.values[sweep]
    need(len(xs)>1 and all(finite(x) and x.imag==0 for x in xs), 'Nonfinite frequency sweep')
    xs = [x.real for x in xs]
    maximum_step = 10**(1/points_per_decade)*(1+1e-8)
    need(abs(xs[0]-low) <= low*1e-8 and high/maximum_step <= xs[-1] <= high*(1+1e-8) and
         all(a<b<=a*maximum_step for a,b in zip(xs,xs[1:])), 'Sweep incomplete, sparse, or not ordered')
    return xs


def get_trace(data,name,count):
    need(name in data.values and len(data.values[name])==count and all(finite(v) for v in data.values[name]),
         'Missing, incomplete, or nonfinite trace '+name)
    return data.values[name]


def summarize_transfer(frequencies, transfer):
    low = abs(transfer[0])
    at56 = abs(bench.at(frequencies, transfer, NYQUIST))
    peak_index = max(range(len(transfer)),key=lambda i:abs(transfer[i]))
    peak = abs(transfer[peak_index])
    return dict(low_frequency_1kHz_gain_VV=low, low_frequency_1kHz_gain_dB=gain_db(low),
                gain_56GHz_VV=at56,gain_56GHz_dB=gain_db(at56),
                peaking_56GHz_vs_1kHz_dB=gain_db(at56/low) if low else None,
                absolute_peak_frequency_Hz=frequencies[peak_index],
                absolute_peak_gain_VV=peak,absolute_peak_gain_dB=gain_db(peak),
                absolute_peak_vs_1kHz_dB=gain_db(peak/low) if low else None,
                peak_is_at_sweep_boundary=peak_index in (0,len(transfer)-1))


def measure(ac,dc,op,noise,vdd):
    frequencies = validate_sweep(ac,'freq',LOW_FREQ,150e9,50)
    count = len(frequencies)
    def diff(p,n):
        return [a-b for a,b in zip(get_trace(ac,p,count),get_trace(ac,n,count))]
    input_diff = diff('X_ip','X_im')
    need(max(abs(v-1) for v in input_diff)<=1e-7,'Frozen AC differential source normalization differs')
    output = [v/in_v for v,in_v in zip(diff('X_o_p','X_o_m'),input_diff)]
    held = [v/in_v for v,in_v in zip(diff('X_h0p','X_h0m'),input_diff)]
    def scalar(name):
        value = get_trace(dc,name,1)[0]
        need(value.imag==0, 'Complex DC value at '+name)
        return value.real
    current = scalar('XVs:p')
    need(current<0,'Nonpositive DC power delivered by the AFE supply')
    out_cm = (scalar('X_o_p')+scalar('X_o_m'))/2
    nodes = ('c_p','c_m','o_p','o_m','s1_p','s1_m','s2_p','s2_m')
    voltages = {name:scalar('X_'+name) for name in nodes}
    clearances = {name:min(value,vdd-value) for name,value in voltages.items()}
    tails = {}
    for name in ('XT1p0','XT2p0'):
        primitive = next((rows[0] for trace,rows in op.values.items()
                          if (trace==name or trace.startswith(name+'.')) and rows and isinstance(rows[0],dict)),None)
        if primitive is not None:
            tails[name] = {k:primitive[k] for k in ('gm','gds','vgs','vds','vdsat','ids','region') if k in primitive}
            if 'vds' in primitive and 'vdsat' in primitive:
                tails[name]['vds_minus_vdsat_V'] = primitive['vds']-primitive['vdsat']
    noise_frequencies = validate_sweep(noise,'freq',1e6,56e9,40)
    need(noise.unit('out')=='V/sqrt(Hz)','Unexpected differential output noise density unit')
    density = get_trace(noise,'out',len(noise_frequencies))
    need(all(v.imag==0 and v.real>=0 for v in density),'Noise amplitude density must be real nonnegative')
    noise_rms = bench.noise_band(noise_frequencies,density,1e6,56e9)
    output_metrics = summarize_transfer(frequencies,output)
    held_metrics = summarize_transfer(frequencies,held)
    peaking = output_metrics['peaking_56GHz_vs_1kHz_dB']
    return dict(afe_output=output_metrics, frozen_tracking_lane0=held_metrics,
                course_56GHz_max_peaking_dB=20.0,
                afe_output_56GHz_headroom_to_20dB_dB=20.0-peaking if peaking is not None else None,
                afe_output_56GHz_max_peaking_metric_met=peaking<=20.0 if peaking is not None else None,
                static_supply_V=vdd,static_supply_terminal_current_A=current,static_afe_supply_power_W=-vdd*current,
                static_output_common_mode_V=out_cm, static_first_stage_common_mode_V=(scalar('X_c_p')+scalar('X_c_m'))/2,
                static_node_voltage_V=voltages,static_node_rail_clearance_V=clearances,
                static_minimum_rail_clearance_V=min(clearances.values()),representative_tail_primitive_OP=tails,
                frozen_tracking_noise_1MHz_to_56GHz_Vrms=noise_rms,
                noise_scope='Stationary differential h0p-h0m noise with lane 0 held in track; excludes sampled noise folding.',
                noise_last_measured_frequency_Hz=noise_frequencies[-1],
                noise_at_most_one_step_edge_extension='Original integration clamps the endpoint to the last measured density if needed.',
                gain_note='Linearized gain at 1 kHz is the near-DC small-signal proxy. dcOp reports bias/current.',
                scope='Standalone r3 AFE with four tracking and four holding primary TG loads; fixed-clock small-signal snapshot',
                AC_curve=dict(frequency_Hz=frequencies, output_diff_gain_real=[v.real for v in output],
                              output_diff_gain_imag=[v.imag for v in output], track0_diff_gain_real=[v.real for v in held],
                              track0_diff_gain_imag=[v.imag for v in held]),
                frozen_track_noise_curve=dict(frequency_Hz=noise_frequencies,density_V_per_sqrt_Hz=[v.real for v in density]))


def require_effective_scale(log):
    number = rb'([+-]?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?)(?![0-9eE]|\.[0-9])'
    direct = rb'(?mi)^\s*scalefactor\s*=\s*'+number
    replacement = (rb'(?mi)scalefactor[^\r\n]{0,140}(?:\r?\n[^\r\n]{0,140}){0,2}?'
                   rb'(?:last|final|effective)[^\r\n]{0,80}?\b(?:value\s*)?(?:is\s+|=\s*|to\s+)'+number)
    matches = sorted((m.start(),float(m.group(1))) for pattern in (direct,replacement) for m in re.finditer(pattern,log))
    need(matches and math.isclose(matches[-1][1],.9,rel_tol=1e-12),
         'Original Spectre log did not confirm the effective scalefactor=0.9')


def collect(case_dir,raw_dir,output):
    case_dir,raw_dir,output = Path(case_dir),Path(raw_dir),Path(output)
    case = load(case_dir/'case.json')
    need(case['schema']=='PAM4_FOCUS55_PVT_AC_CASE_V1' and
         case['execution_state']=='PRIVATE_KIT_PREFLIGHT_VERIFIED_AWAITING_SPECTRE','Use original staged PVT runtime')
    bench_sha = sha((case_dir/'bench.scs').read_bytes())
    need(bench_sha==case['bench_sha256'],'Staged input changed')
    proof_path = case_dir/'model_preflight.json'
    proof = load(proof_path)
    need(sha(proof_path.read_bytes())==case['preflight_sha256'] and proof['runtime_bench_sha256']==bench_sha and
         proof['static_identity_verified'] is True and proof['case_id']==case['case_id'],'Missing or changed original PVT model preflight')
    for name,digest in case['inputs_sha256'].items():
        need(Path(name).name==name and sha((case_dir/name).read_bytes())==digest,'Changed staged input: '+name)
    status_path = case_dir/'run_status.json'
    status = load(status_path)
    need(type(status.get('exit_code')) is int and status['exit_code']==0 and
         status.get('status')=='spectre_completed','No original successful solver receipt')
    need(status.get('input_deck_sha256_before')==status.get('input_deck_sha256_after')==bench_sha,
         'Original solver receipt input differs')
    need(status.get('case_id')==case['case_id'],'Original solver receipt case differs')
    log_path = case_dir/'spectre.log'
    log = log_path.read_bytes()
    need(sha(log)==status.get('spectre_log_sha256'),'Changed original Spectre log')
    require_effective_scale(log)
    paths = {}
    for name in ('acResponse.ac','dcOp.dc','dcOpInfo.info','noiseResponse.noise'):
        p = raw_dir/name
        need(p.is_file() and not p.is_symlink() and 0<p.stat().st_size<=MAX_RAW_BYTES,'Missing or oversized raw analysis '+name)
        paths[name]=p
    ac,dc,op,noise = (parse_file(paths[name]) for name in ('acResponse.ac','dcOp.dc','dcOpInfo.info','noiseResponse.noise'))
    summary = measure(ac,dc,op,noise,case['vdd_V'])
    hashes = {'acResponse.ac':ac.sha256,'dcOp.dc':dc.sha256,'noiseResponse.noise':noise.sha256,
              'dcOpInfo.info':op.sha256}
    recorded = {r['path']:r for r in status.get('raw_inventory',[])}
    for name,digest in hashes.items():
        row = recorded.get('raw/'+name,{})
        need(row.get('bytes')==paths[name].stat().st_size and row.get('sha256')==digest,
             'Raw differs from original solver receipt: '+name)
    r2 = case.get('historical_r2_56GHz_vs_1kHz_dB')
    measured = summary['afe_output']['peaking_56GHz_vs_1kHz_dB']
    result = dict(schema='PAM4_FOCUS55_PVT_AC_MEASUREMENT_V1', measurement_complete=True, case_id=case['case_id'],
                  process=case['process'],temperature_C=case['temperature_C'],vdd_V=case['vdd_V'],
                  bench_sha256=bench_sha,input_deck_sha256=bench_sha,run_status_sha256=sha(status_path.read_bytes()),
                  raw_analysis_sha256=hashes,confirmed_spectre_effective_scalefactor=.9,compact_outputs={},metrics=summary,
                  historical_r2_56GHz_vs_1kHz_dB=r2,
                  r3_minus_historical_r2_dB=measured-r2 if measured is not None and r2 is not None else None,
                  revision_compare_scope='Historical endpoint reference with its original r2 analysis grid; r3 result uses the frozen r3 grid.',
                  course_spec_pass=None)
    with output.open('x',encoding='utf-8') as handle:
        json.dump(result,handle,indent=2,sort_keys=True,allow_nan=False)
        handle.write('\n')
    return result


if __name__=='__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case-dir',type=Path,required=True)
    p.add_argument('--raw-dir',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args = p.parse_args()
    result=collect(args.case_dir,args.raw_dir,args.output)
    print(json.dumps(dict(case_id=result['case_id'],measurement_complete=True,bench_sha256=result['bench_sha256'])))
