#!/usr/bin/env python3
"""Export only approved derived ADC numbers/conditions/hashes, never PDK or waves."""
import datetime
import hashlib
import json
import math
from pathlib import Path

P = Path('/path/to/local/cadence-home/Desktop/cadence_projects/project6_28nm')


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def read(p):
    return json.loads(p.read_text())


def selected(d, keys):
    return {k:d[k] for k in keys if k in d}


def rounded(value):
    if isinstance(value,float): return float('%.8g'%value)
    if isinstance(value,list): return [rounded(v) for v in value]
    if isinstance(value,dict): return {k:rounded(v) for k,v in value.items() if k!='audit'}
    return value


def sweep(name, filename):
    p=P/'runs'/name/filename
    d=read(p)
    if d['status']!='complete': raise ValueError('Unfinished sweep '+name)
    return {'status':d['status'],'scope':d['scope'],'assumptions':d['assumptions'],
            'source_summary_sha256':digest(p),
            'identity':selected(d['identity'],['script_sha256','reset_sweep_script_sha256','probe_script_sha256',
                       'native_cards_sha256','baseline_summary_sha256','input_pattern_LSB','base_configuration',
                       'evaluation_s','compare_high_midpoint_interval_s','equalizer_geometry']),
            'cases':[selected(r,['case','precharge_copies','tail_copies','equalizer_PMOS_copies_per_pair',
                                'timing','deck_sha256','raw_sha256','run_status','status','summary']) for r in d['cases']]}


def held_agreement(d):
    counts={k:0 for k in ['agrees','disagrees','unresolved','indeterminate']}
    first_capture=False
    input_reversed=0
    for r in d['cycles']:
        value=r.get('secondary_prelaunch_differential_V',r['secondary_at_capture_V'])
        first_capture |= 'secondary_prelaunch_differential_V' not in r
        status=r['buffered_classification']
        expected=-1 if r['source_input_LSB']>0 else 1
        if abs(value)<10e-6:
            counts['indeterminate']+=1
            continue
        held=1 if value>0 else -1
        input_reversed+=held!=expected
        if status=='unresolved': counts['unresolved']+=1
        else:
            observed=expected if status=='correct' else -expected
            counts['agrees' if observed==held else 'disagrees']+=1
    return {'counts':counts,'input_sign_already_reversed':input_reversed,
            'reference_time':'capture (prelaunch unavailable)' if first_capture else 'immediately before compare rising edge',
            'indeterminate_band_V':10e-6,
            'scope':'Valid output at +120ps vs saved held sign; input can move during evaluation; no output latch or ADC accuracy proof.'}


def noise_difference(base,noise):
    if len(base['cycles'])!=len(noise['cycles']): raise ValueError('Noise cycle mismatch')
    result={}
    for key in ['master_at_capture_V','secondary_at_capture_V','secondary_prelaunch_differential_V']:
        delta=[]
        for b,n in zip(base['cycles'],noise['cycles']):
            if b['group']!=n['group'] or b['source_input_LSB']!=n['source_input_LSB']:
                raise ValueError('Mismatched noise input')
            delta.append(n[key]-b[key])
        mean=sum(delta)/len(delta)
        result[key]={'samples':len(delta),'mean_difference_V':mean,
                     'rms_difference_V':math.sqrt(sum(x*x for x in delta)/len(delta)),
                     'centered_rms_difference_V':math.sqrt(sum((x-mean)**2 for x in delta)/len(delta))}
    return result


def main():
    result={'schema_version':1,'created_UTC':datetime.datetime.utcnow().isoformat()+'Z',
            'scope':'Exploratory physical ADC interface and reset work; complete_ADC_verified=false',
            'complete_ADC_verified':False,'new_integrated_PAM4_BER_claim':False,
            'reset':sweep('adc_reset_r4_20261013','reset_sweep_summary.json'),
            'equalizer':sweep('adc_equalizer_r4_20261013','equalizer_sweep_summary.json'),
            'isolation':[],'noise_differences':[],
            'noise_note':'Two seeds, eight branch-0 samples each, 150GHz cutoff/500MHz low-frequency flattening. Difference to same deterministic deck estimates sampled noise plus numerical differences; tiny diagnostic sample, not BER/ENOB.',
            'scope_limits':['Block transients use50ohm source, not complete r3 AFE.',
                            'ADC has no CDAC, SAR controller, output latch, clock generator, mismatch calibration or layout.',
                            'Source-polarity errors include acquisition/transfer memory and are not all comparator errors.',
                            'DUT/reference disturbance includes changed comparator loading, not pure kickback.',
                            'Reported VDD powers omit ideal clock/bias generation; branch banks omit seven comparators in transient.',
                            'Frozen AC load experiment includes64 reset comparators; does not prove periodically switched ADC performance.',
                            'After time demultiplexing, backend need not pass a continuous56GHz sine; secondary frozen H56 is a diagnostic, not a receiver bandwidth pass/fail. Primary AFE aperture response and settling are the relevant checks.']}
    records={}
    root=P/'runs/adc_isolation_r4_20261013'
    for p in sorted(root.glob('*/summary.json')):
        d=read(p)
        item=selected(d,['case','configuration','native_cards_sha256','deck_sha256','raw_sha256','script_sha256',
                         'run_status','summary'])
        item['source_summary_sha256']=digest(p)
        if 'cycles' in d:
            item['held_sign_agreement']=held_agreement(d)
            records[d['case']]=d
        result['isolation'].append(item)
    base=records['cml8_m25_sw4_c25']
    result['isolation_testbench_common']=selected(base,['scope','assumptions','timing_s'])
    for seed in [41,83]:
        name='cml8_m25_sw4_c25_noise'+str(seed)
        result['noise_differences'].append({'case':name,'seed':seed,'noiseless_reference':base['case'],
                                          'metrics':noise_difference(base,records[name])})
    acfile=P/'runs/adc_frontend_load_r4_20261013/frontend_load_summary.json'
    ac=read(acfile)
    if ac['status']!='complete' or len(ac['cases'])!=4:
        raise ValueError('Incomplete actual-frontend load experiment')
    if any(c['status']!='complete' for c in ac['cases']):
        raise ValueError('Incomplete AC case')
    # This own script schema contains derived metrics and condition/hash metadata only.
    for c in ac['cases']:
        m=c['metrics']
        m['transfer']={k:v for k,v in m['transfer'].items() if k not in ('primary_hold_lane4','secondary_hold_bank0')}
        if 'DC_per_bank' in m:
            banks=m.pop('DC_per_bank')
            m['DC_bank_common_mode_ranges_V']={k:[min(b[k] for b in banks),max(b[k] for b in banks)]
                for k in ['primary_common_mode_V','buffer_common_mode_V','secondary_track_common_mode_V']}
    result['frontend_load']=ac
    result['frontend_load_source_sha256']=digest(acfile)
    result['protected_hashes']={
        'frozen_frontend_validation':digest(P/'configs/pam4_optimization_frozen.json'),
        'native_cards':digest(P/'configs/native_device_cards.json'),
        'PDK_model':digest(Path('<PDK_ROOT>/models/spectre/pdk_model.scs'))}
    # Common timing definitions remain in the scripts and identity; retain varying
    # intervals per case. Full-precision original summaries stay on the VM.
    for name in ['reset','equalizer']:
        for c in result[name]['cases']:
            c['timing']=selected(c['timing'],['period_s','reset_low_midpoint_interval_s','track_overlaps_previous_evaluation_s'])
            c['summary'].pop('reset_screen_is_diagnostic_not_input_offset_proof',None)
    result['export_precision']='8 significant digits; original full-precision summaries remain VM-side and are SHA256-bound.'
    result=rounded(result)
    encoded=(json.dumps(result,ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n').encode('utf-8')
    if len(encoded)>70*1024: raise ValueError('Numeric summary exceeds approximate70KiB: '+str(len(encoded)))
    out=P/'results/Project6_ADC_r4_summary.json'
    out.write_bytes(encoded)
    print(json.dumps({'bytes':len(encoded),'sha256':digest(out),'isolation_cases':len(result['isolation']),
                      'noise_differences':result['noise_differences'],'held_sign_checks':[
                          {'case':d['case'],'held_sign_agreement':d.get('held_sign_agreement')} for d in result['isolation']]}),flush=True)


if __name__=='__main__': main()
