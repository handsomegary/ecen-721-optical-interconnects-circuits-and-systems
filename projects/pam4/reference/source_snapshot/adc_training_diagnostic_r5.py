#!/usr/bin/env python3
"""Training-only r5 backend diagnostic. Never opens validation directories.

Reads one frozen training waveform and emits derived numerical summaries.
No circuit, frozen detector, native model/card, or validation data is changed.
Regression residuals combine settling, nonlinearity and noise; not noise alone.
Python 3.6, standard library.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

import adc_backend_pam4_r5 as backend
import adc_comparator_probe as a
import pam4_ffe_diagnostic as ffe
import pam4_integration as pi
import pam4_metrics as pm
import optimize_pam4 as opt
import psf_ascii


def mean(values):return math.fsum(values)/len(values)


def stats(values):
    center=mean(values)
    return dict(count=len(values),mean=center,rms=math.sqrt(mean([v*v for v in values])),
                centered_rms=math.sqrt(mean([(v-center)**2 for v in values])),
                minimum=min(values),maximum=max(values))


def fit_linear(rows,targets,ridge=1e-4):
    """Standardized features, unregularized intercept; training-only fit."""
    count=len(rows)
    width=len(rows[0])
    centers=[mean([row[j] for row in rows]) for j in range(width)]
    scales=[math.sqrt(mean([(row[j]-centers[j])**2 for row in rows])) for j in range(width)]
    if min(scales)<1e-15:raise ValueError('Degenerate diagnostic feature')
    norm=[[(v-centers[j])/scales[j] for j,v in enumerate(row)]+[1.] for row in rows]
    size=width+1
    normal=[[0.]*size for unused in range(size)]
    rhs=[0.]*size
    for i in range(size):
        rhs[i]=math.fsum(row[i]*target for row,target in zip(norm,targets))
        for j in range(i,size):
            normal[i][j]=normal[j][i]=math.fsum(row[i]*row[j] for row in norm)
        if i<width:normal[i][i]+=ridge*count
    weights=ffe.cholesky_solve(normal,rhs)
    direct=[weights[j]/scales[j] for j in range(width)]
    intercept=weights[-1]-math.fsum(direct[j]*centers[j] for j in range(width))
    return dict(coefficients=direct,intercept=intercept,ridge=ridge,training_count=count)


def predict(rows,fit):
    return [fit['intercept']+math.fsum(w*x for w,x in zip(fit['coefficients'],row)) for row in rows]


def simple_transfer(xs,ys):
    if len(xs)<4:return {'count':len(xs),'status':'insufficient_samples'}
    fit=fit_linear([[x] for x in xs],ys,ridge=0.)
    residual=[y-z for y,z in zip(ys,predict([[x] for x in xs],fit))]
    return dict(count=len(xs),gain_VV=fit['coefficients'][0],offset_V=fit['intercept'],
                residual_rms_V=math.sqrt(mean([x*x for x in residual])),
                residual_peak_V=max(abs(x) for x in residual),
                primary_Vppd=max(xs)-min(xs),secondary_Vppd=max(ys)-min(ys))


def transfer_memory(physical):
    by={r['symbol_time_index']:r for r in physical}
    models={'same_aperture':[0], 'previous_bank_sample':[0,8],
            'bank_and_branch_history':[0,8,64],
            'nearby_plus_bank_branch':list(range(-3,5))+[8,64],
            '17tap_primary_history':list(range(-8,9)),
            '17tap_plus64UI':list(range(-8,9))+[64]}
    # Same training rows for every fit; no model gets easier edge samples.
    indices=[i for i in sorted(by) if all(i-offset in by for offset in range(-8,65))]
    ys=[by[i]['secondary_V'] for i in indices]
    output={}
    for name,offsets in models.items():
        rows=[[by[i-off]['primary_V'] for off in offsets] for i in indices]
        fit=fit_linear(rows,ys)
        residual=[y-z for y,z in zip(ys,predict(rows,fit))]
        output[name]=dict(training_rows=len(indices),previous_sample_offsets_UI=offsets,
                          coefficients_VV=fit['coefficients'],intercept_V=fit['intercept'],
                          residual_rms_V=math.sqrt(mean([x*x for x in residual])),
                          residual_peak_V=max(abs(x) for x in residual))
    return dict(models=output,scope='Same1024trainingapertures only. Physicalsecondaryvsprimary observationalfits; noholdout andnoncausalfuturefeaturesin17tapdiagnostics.',
                residual_note='Residual includes samplednoise, nonlinearities andunmodeledhistory; itisnotisolatedthermalnoise.')


def extended_training_ffe(records,symbols,selection):
    samples,labels,unused=pi.aligned_window(records,symbols,selection['integer_symbol_lag'],backend.TRAIN_COUNT,0)
    fs=selection['ADC_fullscale_differential_Vpp']
    quantized,clipped=pm.quantize_symmetric(samples,fs,7)
    feature_sets={'17tap':list(range(-8,9)),
                  '17tap_plus64UI':list(range(-8,9))+[64],
                  '17tap_plus_delayed17':list(range(-8,9))+list(range(56,73))}
    first_end=len(samples)//2
    # Same432fit/432selection target rows, with72UI feature isolation.
    fit_indices=list(range(72,first_end-8))
    selection_indices=list(range(first_end+72,len(samples)-8))
    targets=[ffe.TARGETS[labels[i]] for i in fit_indices]
    target_labels=[labels[i] for i in selection_indices]
    output={}
    for representation,values in [('raw',samples),('ideal7bit',quantized)]:
        output[representation]={}
        for name,offsets in feature_sets.items():
            rows=[[values[i-off] for off in offsets] for i in fit_indices]
            held_rows=[[values[i-off] for off in offsets] for i in selection_indices]
            fit=fit_linear(rows,targets,ridge=1e-3)
            measured=ffe.prediction_metrics(predict(held_rows,fit),target_labels)
            output[representation][name]=dict(tap_count=len(offsets),offsets_UI=offsets,
                                              fit_input_window_count=len(fit_indices),
                                              selection_input_window_count=len(selection_indices),
                                              training_selection_metrics=measured)
    return dict(results=output,ADC_fullscale_differential_Vpp=fs,training_ADC_clipped_count=clipped,
                original_frozen_lag=selection['integer_symbol_lag'],
                disclaimer='Exploratorytrainingonly DSPdiagnostic, notdeploymentornewvalidation. Allmodels useidentical432fit/432selectionwindows. FrozenoriginalFFE isunchanged.')


def physical_samples(raw,records,spec):
    t,v=raw.values[raw.sweep_names[0]],raw.values
    primary={r[0]:r for r in records['primary']}
    secondary={r[0]:r for r in records['secondary']}
    first=spec['primary_clocks'][0]['first_fall_midpoint_s']
    period=spec['primary_clocks'][0]['period']
    get=lambda node,time:a.interpolate(t,v[node],time)
    output=[]
    for i in range(pi.WARMUP,pi.WARMUP+backend.TRAIN_COUNT):
        p,s=primary[i],secondary[i]
        bank=p[4]
        delay=spec['primary_clocks'][bank]['first_fall_midpoint_s']-first
        cycle=int(round((p[3]-delay-first)/period))
        branch=cycle%8
        sec_close=s[2]-1.5e-12
        prefix='B%d_h%d'%(bank,branch)
        before=sec_close-pi.EDGE/2-.1e-12
        after=sec_close+pi.EDGE/2+.1e-12
        hp,hn=get(prefix+'p',s[2]),get(prefix+'m',s[2])
        row=dict(symbol_time_index=i,bank=bank,branch=branch,master_cycle=cycle,
                 primary_V=p[1],secondary_V=s[1],secondary_common_mode_V=(hp+hn)/2,
                 secondary_positive_V=hp,secondary_negative_V=hn,
                 secondary_closing_edge_change_V=(get(prefix+'p',after)-get(prefix+'m',after))-
                                                (get(prefix+'p',before)-get(prefix+'m',before)),
                 secondary_hold_change_first8ps_V=(get(prefix+'p',s[2]+8e-12)-get(prefix+'m',s[2]+8e-12))-s[1])
        row['secondary_hold_change_120ps_V']=(get(prefix+'p',s[2]+120e-12)-get(prefix+'m',s[2]+120e-12))-s[1]
        if bank in (0,7):
            out='B%d_f'%bank
            mid='B%d_e'%bank
            outputdiff=lambda time:get(out+'p',time)-get(out+'m',time)
            held_before=get(prefix+'p',before)-get(prefix+'m',before)
            row.update(buffer_at_primary_capture_V=outputdiff(p[2]),
                       buffer_before_secondary_close_V=outputdiff(before),
                       buffer_change_final8ps_V=outputdiff(before)-outputdiff(before-8e-12),
                       secondary_acquisition_lag_before_close_V=held_before-outputdiff(before),
                       buffer_common_mode_before_close_V=(get(out+'p',before)+get(out+'m',before))/2,
                       buffer_positive_rail_headroom_before_close_V=.9-get(out+'p',before),
                       buffer_negative_rail_headroom_before_close_V=.9-get(out+'m',before),
                       input_N_positive_VDS_before_close_V=get(out+'p',before)-get(mid+'p',before),
                       input_N_negative_VDS_before_close_V=get(out+'m',before)-get(mid+'m',before),
                       input_N_positive_VGS_before_close_V=get('X_h%dp'%bank,before)-get(mid+'p',before),
                       input_N_negative_VGS_before_close_V=get('X_h%dm'%bank,before)-get(mid+'m',before))
        output.append(row)
    return output


def grouped_statistics(rows):
    per_lane=[]
    for bank in range(8):
        for branch in range(8):
            selected=[row for row in rows if (row['bank'],row['branch'])==(bank,branch)]
            fit=simple_transfer([r['primary_V'] for r in selected],[r['secondary_V'] for r in selected])
            fit.update(bank=bank,branch=branch,
                       secondary_common_mode_V=stats([r['secondary_common_mode_V'] for r in selected]),
                       closing_edge_change_V=stats([r['secondary_closing_edge_change_V'] for r in selected]),
                       hold_change_first8ps_V=stats([r['secondary_hold_change_first8ps_V'] for r in selected]),
                       hold_change_120ps_V=stats([r['secondary_hold_change_120ps_V'] for r in selected]))
            per_lane.append(fit)
    whole=simple_transfer([r['primary_V'] for r in rows],[r['secondary_V'] for r in rows])
    cutoff_low=pm._percentile([abs(r['primary_V']) for r in rows],1./3)
    cutoff_high=pm._percentile([abs(r['primary_V']) for r in rows],2./3)
    bands={}
    for label,selected in [('inner',[r for r in rows if abs(r['primary_V'])<=cutoff_low]),
                           ('outer',[r for r in rows if abs(r['primary_V'])>=cutoff_high])]:
        bands[label]=simple_transfer([r['primary_V'] for r in selected],[r['secondary_V'] for r in selected])
    physical_fields=[key for key in rows[0] if key.startswith(('secondary_common','secondary_closing','secondary_hold'))]
    buffer_rows=[r for r in rows if 'buffer_at_primary_capture_V' in r]
    buffer_fields=[key for key in buffer_rows[0] if key.startswith(('buffer_','input_N_','secondary_acquisition_'))]
    return dict(global_aperture_transfer=whole,per64_lane=per_lane,
                per_lane_warning='16samplesperlane, no mismatch included; lane fits arelow-countdiagnostics andnotcalibrationproof.',
                input_amplitude_bands=bands,amplitude_cutoffs_V=[cutoff_low,cutoff_high],
                physical_summary={key:stats([r[key] for r in rows]) for key in physical_fields},
                buffer0_and7_summary={key:stats([r[key] for r in buffer_rows]) for key in buffer_fields},
                held_leg_within30mV_of_rail_count=sum(r[k]<.03 or r[k]>.87 for r in rows for k in ('secondary_positive_V','secondary_negative_V')),
                held_leg_count=2*len(rows),
                headroom_note='Nodevoltages only, not MOSregion/thresholdproof. Closingedgechange includes signalmovement/noise, notpurechargeinjection.')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--study',required=True)
    args=p.parse_args()
    if not args.study.replace('_','').isalnum():p.error('Safe studyname required')
    root=a.PROJECT/'runs'/backend.ROOT_NAME/args.study
    frozen_path=root/'frozen.json'
    frozen,fh=opt.read_json_snapshot(frozen_path)
    if frozen['protocol']['training_data_seed']!=backend.TRAIN_SEED:raise ValueError('Unexpected trainingseed')
    training=frozen['training_run']
    raw_path=a._raw_file(root/'training')
    psf_ascii.MAX_FILE_BYTES=512*1024*1024
    raw=a.parse_file(raw_path)
    if raw.sha256!=training['raw_transient_sha256']:raise ValueError('Trainingrawhash disagreeswithfrozenfile')
    symbols=backend.training_symbols()
    if opt.canonical_hash(symbols)!=training['symbol_sequence_sha256']:raise ValueError('Trainingsequencehashchanged')
    records,audit=backend.extract_records(raw,training['clock_specification'])
    rows=physical_samples(raw,records,training['clock_specification'])
    result=dict(schema_version=1,scope='TRAININGONLY diagnostic; noholdout files opened andnofrozendetector changed.',
                complete_ADC_verified=False,training_input_count=len(rows),training_data_seed=backend.TRAIN_SEED,
                training_noise_seed=frozen['protocol']['training_noise_seed'],
                frozen_file_sha256=fh,raw_training_sha256=raw.sha256,script_sha256=a.digest(__file__),
                backend_script_sha256=a.digest(backend.__file__),clock_mapping_audit=audit,
                statistics=grouped_statistics(rows),physical_transfer_memory=transfer_memory(rows),
                secondary_training_FFE_history=extended_training_ffe(records['secondary'],symbols,frozen['selections']['secondary']))
    if a.digest(frozen_path)!=fh:raise ValueError('Frozenfilechangedduringdiagnostic')
    result['frozen_file_unchanged']=True
    destination=root/'training_diagnostic_v1.json'
    if destination.exists():raise ValueError('Refuse overwrite existing trainingdiagnostic')
    a.atomic_json(destination,result)
    compact=dict(status='complete',frozen_file_unchanged=True,diagnostic_scope='trainingonly',
                 global_aperture_transfer=result['statistics']['global_aperture_transfer'],
                 physical_summary=result['statistics']['physical_summary'],
                 buffer0_and7_summary=result['statistics']['buffer0_and7_summary'],
                 memory_model_residuals={k:dict(rms_V=v['residual_rms_V'],peak_V=v['residual_peak_V'],
                                               offsets_UI=v['previous_sample_offsets_UI'],coefficients_VV=v['coefficients_VV'])
                                         for k,v in result['physical_transfer_memory']['models'].items()},
                 training_DSP_diagnostics={rep:{name:dict(errors=z['training_selection_metrics']['symbol_errors'],
                                                        count=z['training_selection_metrics']['sample_count'],
                                                        EVM_percent=z['training_selection_metrics']['prediction_EVM_RMS_percent_of_target_RMS'])
                                                   for name,z in models.items()}
                                           for rep,models in result['secondary_training_FFE_history']['results'].items()},
                 report_sha256=a.digest(destination))
    print(json.dumps(compact),flush=True)


if __name__=='__main__':main()
