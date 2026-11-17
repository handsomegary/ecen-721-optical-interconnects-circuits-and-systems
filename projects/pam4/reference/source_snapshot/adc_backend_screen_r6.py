#!/usr/bin/env python3
"""Bounded r6 gain/drive/noise-capacitance screen; Python 3.6, VM-only.

Fixed4cases: matchedr5baseline plus3predeclaredhardware candidates. First
actualAFE frozenDC/AC, then512fresh training-only PAM4. Optional noise check
compares the noiseless-selected candidate and baseline; no holdout is read.
The completeADC flag remains false: all64 comparison elements stay reset.
"""
import argparse
import copy
import hashlib
import json
import math
import os
import re
import time
from pathlib import Path

import adc_backend_pam4_r5 as backend
import adc_comparator_probe as a
import adc_frontend_load_r5 as load
import native_geometry_r5 as ng
import optimize_pam4 as opt
import pam4_integration as pi
import psf_ascii

NAME='adc_backend_r6_screen_20261013'
TRAIN_COUNT=512
DATA_SEED=2026101303
NOISE_SEED=181
BASELINE='baseline_r5_late1'
ORDER=[BASELINE,'gain350_bias060_c10','drive250_bias065_c10','drive250_bias065_c25']
GATES=dict(min_buffer_gain_1GHz_VV=.8,min_buffer_DC_common_mode_V=.60,
           max_buffer_DC_common_mode_V=.85,min_primary_H56_change_vs_bare_dB=-3.,
           max_total_frozen_static_W=.040,max_primary_training_SER=.02)


def cases():
    reference=backend.configuration('cml2_late1','in100_tail3')
    result={BASELINE:reference}
    for name,load_ohm,bias,cap,width in [
        ('gain350_bias060_c10',350.,.60,10e-15,1e-6),
        ('drive250_bias065_c10',250.,.65,10e-15,1e-6),
        ('drive250_bias065_c25',250.,.65,25e-15,2e-6)]:
        cfg=copy.deepcopy(reference)
        cfg.update(current_width_m=3e-6,load_ohm=load_ohm,n_bias_V=bias,
                   degeneration_ohm=0.,secondary_cap_F=cap,secondary_switch_width_m=width)
        result[name]=cfg
    return result


def short_zero_degeneration(lines):
    """Physical source-node wire; no0-ohm resistor orideal signal amplifier."""
    result=[]
    found=0
    pattern=re.compile(r'^(B\d+_)RDEG \(([^)]*)\) resistor r=0(?:\.0*)?$')
    for line in lines:
        match=pattern.match(line)
        if match:
            line='%sVDEG (%s) vsource dc=0'%(match.group(1),match.group(2))
            found+=1
        result.append(line)
    if found not in (0,8):raise ValueError('Expectedzerooreight explicitlyshorted degenerationbridges')
    return result


def dc_deck(frontend,cfg):
    return short_zero_degeneration(load.make_deck(frontend,cfg,cfg['comparator_candidate'],True))


def pam4_deck(frontend,cfg,symbols,noise_seed):
    lines,clocks=backend.build_deck(frontend,cfg,symbols,noise_seed)
    return short_zero_degeneration(lines),clocks


def file_identity(frontend,native,noise_check):
    dependencies=['adc_backend_screen_r6.py','adc_backend_pam4_r5.py','adc_isolation_r5.py',
                  'adc_frontend_load_r5.py','adc_frontend_load_r4.py','adc_comparator_r5.py',
                  'native_geometry_r5.py','pam4_integration.py','optimize_pam4.py',
                  'pam4_ffe_diagnostic.py','pam4_metrics.py']
    return dict(frontend=frontend,native_geometry=native,cases=cases(),case_order=ORDER,
                gates=GATES,training_symbols=TRAIN_COUNT,data_seed=DATA_SEED,noise_seed=NOISE_SEED,
                optional_noise_check_enabled=noise_check,
                script_hashes={name:a.digest(Path(__file__).with_name(name)) for name in dependencies},
                primary_and_secondary_phase_UI=.25,holdout_accessed=False,complete_ADC_verified=False,
                decision_rule='PredeclaredDCgates ->512training-only noiseless ADC+FFE ranking; selectoncebeforenoisepair. Nochoicefromholdout.')


def checkpoint(root,summary,stage,message):
    summary.update(stage=stage,message=message,updated_unix_s=time.time())
    a.atomic_json(root/'summary.json',summary)
    print(json.dumps(dict(stage=stage,message=message,completed_DC_cases=len(summary['DC_cases']),
                          completed_noiseless_cases=len(summary['noiseless_training']),
                          completed_noise_cases=len(summary['noise_training']),
                          selected_case=summary.get('selected_case'))),flush=True)


def execute(directory,lines,run,timeout):
    """Completed exactdecks areverified/reused; unfinishedraw isneveroverwritten."""
    directory.mkdir(parents=True,exist_ok=True)
    text='\n'.join(lines)+'\n'
    sha=hashlib.sha256(text.encode()).hexdigest()
    deck_path=directory/'bench.scs'
    record_path=directory/'execution.json'
    prior=json.loads(record_path.read_text()) if record_path.exists() else None
    if deck_path.exists() and a.digest(deck_path)!=sha:raise ValueError('Existingdeckidentitydiffers: '+str(directory))
    if prior and prior['deck_sha256']!=sha:raise ValueError('Existingexecutionidentitydiffers')
    if prior and prior['status']=='simulation_complete':
        for relpath,digest in prior['raw_hashes'].items():
            if a.digest(directory/relpath)!=digest:raise ValueError('Completedrawhashchanged')
        return prior
    if (directory/'raw').exists():
        if prior and prior['status']=='simulation_failed':return prior
        raise ValueError('Incompleteorunboundrawpreserved; refusingoverwrite: '+str(directory))
    if not deck_path.exists():deck_path.write_text(text)
    record=dict(status='generated_only',deck_sha256=sha)
    a.atomic_json(record_path,record)
    if not run:return record
    record['status']='simulation_running'
    a.atomic_json(record_path,record)
    record['run_status']=a.b.run(directory,lines,timeout=timeout)
    if record['run_status']['exit_code']!=0:
        record['status']='simulation_failed'
        a.atomic_json(record_path,record)
        return record
    record['raw_hashes']={str(path.relative_to(directory)):a.digest(path)
                          for path in sorted((directory/'raw').iterdir())
                          if path.is_file() and (path.name=='dcOp.dc' or path.name.endswith(('.ac','.noise')) or path.name.startswith('tranResponse.tran'))}
    if not record['raw_hashes']:raise ValueError('Successfulsimulationhasnorequestedrawresults')
    record['status']='simulation_complete'
    a.atomic_json(record_path,record)
    return record


def dc_eligibility(name,result):
    measured=result['transfer']
    gain=measured['buffer_lane0']['H1GHz']['magnitude_VV']/measured['primary_track_lane0']['H1GHz']['magnitude_VV']
    cm=measured['buffer_lane0']['DC_common_mode_V']
    h56=result['primary_H56GHz_change_vs_historical_r3_bare_dB']
    power=result['DC_power']['total_static_W']
    checks=dict(buffer_gain=gain>=GATES['min_buffer_gain_1GHz_VV'],
                buffer_common_mode=GATES['min_buffer_DC_common_mode_V']<=cm<=GATES['max_buffer_DC_common_mode_V'],
                primary_H56=h56>=GATES['min_primary_H56_change_vs_bare_dB'],
                static_power=power<=GATES['max_total_frozen_static_W'])
    return dict(is_baseline_control=name==BASELINE,
                eligible_for_training=name==BASELINE or all(checks.values()),checks=checks,
                buffer_gain_vs_primary_1GHz_VV=gain,buffer_DC_common_mode_V=cm,
                primary_H56_change_vs_historical_bare_dB=h56,total_frozen_static_W=power,
                scope='Internalbounded-screen criteria, notcourseorcompleteADCrequirements; secondaryH56isnotapasscriterion.')


def training_analysis(directory,record,clocks,symbols):
    psf_ascii.MAX_FILE_BYTES=512*1024*1024
    raw=a.parse_file(a._raw_file(directory))
    records,audit=backend.extract_records(raw,clocks)
    selections={point:opt.select_training_alignment(rows,symbols,TRAIN_COUNT) for point,rows in records.items()}
    result=dict(execution=record,raw_transient_sha256=raw.sha256,clock_mapping_audit=audit,
                selections=selections,training_only=True,complete_ADC_verified=False,
                symbol_sequence_sha256=opt.canonical_hash(symbols),data_seed=DATA_SEED,
                train_symbols=TRAIN_COUNT,holdout_accessed=False)
    values,labels,times=pi.aligned_window(records['primary'],symbols,selections['primary']['integer_symbol_lag'],TRAIN_COUNT,0)
    result['VDD_power']=backend.power(raw,times[0],times[-1]+pi.UI)
    result['compact_scores']={point:dict(raw_FFE=selection['raw_FFE_score'],ideal7bit_FFE=selection['ADC_score'],
                                        integer_symbol_lag=selection['integer_symbol_lag'],
                                        ADC_fullscale_differential_Vpp=selection['ADC_fullscale_differential_Vpp'])
                              for point,selection in selections.items()}
    return result


def write_bound_record(path,data):
    if path.exists():
        previous=json.loads(path.read_text())
        if opt.canonical_hash(previous)!=opt.canonical_hash(data):
            raise ValueError('Completedderivedrecorddiffers; originalpreserved: '+str(path))
    else:a.atomic_json(path,data)


def run_study(root,frontend,native,args):
    root.mkdir(parents=True,exist_ok=True)
    ident=file_identity(frontend,native,args.noise_check)
    identity_path=root/'identity.json'
    write_bound_record(identity_path,ident)
    summary_path=root/'summary.json'
    summary=json.loads(summary_path.read_text()) if summary_path.exists() else dict(
        schema_version=1,status='running' if args.run else 'generated_only',
        identity_sha256=a.digest(identity_path),DC_cases={},noiseless_training={},noise_training={},errors=[],
        complete_ADC_verified=False,holdout_accessed=False,
        limitations=[
            'All64comparatorsremainreset; noCDAC,reference,7decisions,controloreffectiveADCconversion.',
            'Samefixedr3AFE/phase andnativeinput2um atallcandidatebufferbanks; nativeCDFcards retained.',
            'Noiselessandnoise181 runs are512training-onlysymbols, notindependent BERvalidation.',
            'DCcriteria arepredeclaredscreenlimits, notspecificationapproval.',
            'Noisecheck hardwareisselectedbeforenoise; eachcasefitsitsowntraining-onlyidealADC+FFE.',
            'TT25C0.9V synthetic20dBchannel/idealclocks andbias; noPVT/mismatch/jitter/PEX.',
            'Powerexcludesclock/biasgeneration,reference/CDAC/control/DSP.'])
    if summary['identity_sha256']!=a.digest(identity_path):raise ValueError('Studyidentitychanged')
    configurations=cases()
    for name in ORDER:
        checkpoint(root,summary,'dc_running','Checking actual r3 AFE loading, bias and gain: '+name)
        directory=root/'dc'/name
        execution=execute(directory,dc_deck(frontend,configurations[name]),args.run,min(args.timeout,300))
        if execution['status']=='generated_only':continue
        if execution['status']!='simulation_complete':
            summary['DC_cases'][name]=dict(status='failed',execution=execution)
            continue
        measured=load.metrics(directory,True)
        result=dict(status='complete',configuration=configurations[name],execution=execution,
                    metrics=measured,eligibility=dc_eligibility(name,measured))
        write_bound_record(directory/'summary.json',result)
        summary['DC_cases'][name]=result
        checkpoint(root,summary,'dc_case_complete','Completed DC/AC/noise loading screen: '+name)
    if not args.run:
        checkpoint(root,summary,'generated_only','Four DC/AC decks generated; no simulation ortrainingselection performed.')
        return summary
    symbols=opt.random_symbols(DATA_SEED,pi.WARMUP+TRAIN_COUNT+pi.GUARD)
    for name in ORDER:
        dc=summary['DC_cases'].get(name,{})
        if not dc.get('eligibility',{}).get('eligible_for_training'):continue
        checkpoint(root,summary,'noiseless_training_running','Running fresh 512-symbol training-only PAM4: '+name)
        directory=root/'noiseless'/name
        lines,clocks=pam4_deck(frontend,configurations[name],symbols,None)
        execution=execute(directory,lines,True,args.timeout)
        if execution['status']!='simulation_complete':
            summary['noiseless_training'][name]=dict(status='failed',execution=execution)
            continue
        result=training_analysis(directory,execution,clocks,symbols)
        result.update(status='complete',case=name,noise_seed=None)
        write_bound_record(directory/'summary.json',result)
        summary['noiseless_training'][name]=dict(status='complete',case=name,noise_seed=None,
                                                compact_scores=result['compact_scores'],VDD_power=result['VDD_power'],
                                                summary_sha256=a.digest(directory/'summary.json'))
        checkpoint(root,summary,'noiseless_case_complete','Completed noiseless training-only PAM4: '+name)
    completed={name:r for name,r in summary['noiseless_training'].items() if r.get('status')=='complete'}
    if BASELINE not in completed:
        summary['status']='incomplete_baseline_failed'
        checkpoint(root,summary,'stopped','Baseline control failed; no hardware winner selected.')
        return summary
    baseline_primary=completed[BASELINE]['compact_scores']['primary']['ideal7bit_FFE']['selection_SER']
    valid={name:r for name,r in completed.items()
           if name==BASELINE or r['compact_scores']['primary']['ideal7bit_FFE']['selection_SER']<=max(GATES['max_primary_training_SER'],baseline_primary)}
    selected=min(valid,key=lambda name:opt.score_key(valid[name]['compact_scores']['secondary']['ideal7bit_FFE']))
    chosen=dict(selected_case=selected,configuration=configurations[selected],data_seed=DATA_SEED,
                selection_data='512training-onlynoiselesssymbols; noholdout',selection_stage='beforeoptionalnoisecheck',
                selection_key=opt.score_key(valid[selected]['compact_scores']['secondary']['ideal7bit_FFE']),
                baseline_key=opt.score_key(completed[BASELINE]['compact_scores']['secondary']['ideal7bit_FFE']),
                candidate_scores={name:r['compact_scores'] for name,r in completed.items()},
                complete_ADC_verified=False)
    write_bound_record(root/'selected_before_noise.json',chosen)
    summary['selected_case']=selected
    summary['selected_before_noise_sha256']=a.digest(root/'selected_before_noise.json')
    checkpoint(root,summary,'hardware_selected_before_noise','Noiseless training selected '+selected+'; choice now fixed for noise check.')
    if args.noise_check:
        for name in list(dict.fromkeys([BASELINE,selected])):
            checkpoint(root,summary,'noise_training_running','Checking fixed hardware with noise181 on training data: '+name)
            directory=root/'noise181'/name
            lines,clocks=pam4_deck(frontend,configurations[name],symbols,NOISE_SEED)
            execution=execute(directory,lines,True,args.timeout)
            if execution['status']!='simulation_complete':
                summary['noise_training'][name]=dict(status='failed',execution=execution)
                continue
            result=training_analysis(directory,execution,clocks,symbols)
            result.update(status='complete',case=name,noise_seed=NOISE_SEED,
                          hardware_selected_before_noise_sha256=summary['selected_before_noise_sha256'])
            write_bound_record(directory/'summary.json',result)
            summary['noise_training'][name]=dict(status='complete',case=name,noise_seed=NOISE_SEED,
                                                compact_scores=result['compact_scores'],VDD_power=result['VDD_power'],
                                                summary_sha256=a.digest(directory/'summary.json'))
            checkpoint(root,summary,'noise_case_complete','Completed paired training-only noise check: '+name)
    allrecords=list(summary['DC_cases'].values())+list(summary['noiseless_training'].values())+list(summary['noise_training'].values())
    summary['status']='complete_with_failures' if any(r.get('status')=='failed' for r in allrecords) else 'complete'
    checkpoint(root,summary,'complete','Bounded r6 screen finished. A new full training/fresh holdout is still required beforeperformanceclaims.')
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',action='store_true')
    p.add_argument('--noise-check',action='store_true')
    p.add_argument('--timeout',type=int,default=7200)
    p.add_argument('--config',type=Path,default=a.PROJECT/'configs/ctle_selected_r3.json')
    p.add_argument('--cards',type=Path,default=ng.CARD_PATH)
    args=p.parse_args()
    if not 60<=args.timeout<=7200:p.error('Timeout mustbe60..7200seconds')
    if not (a.PROJECT/'.codex_project6_owned').exists():raise ValueError('Projectmarker absent')
    root=a.PROJECT/'runs'/NAME
    root.mkdir(parents=True,exist_ok=True)
    lock=root/'runner.lock'
    # Never resume on top of a possiblyliveworker. A stale lock isexplicitly
    # reported for operatorverification; nodeck/rawfile isdeletedorreplaced.
    try:
        with lock.open('x') as handle:handle.write(json.dumps(dict(pid=os.getpid(),started_unix_s=time.time())))
    except FileExistsError:
        raise RuntimeError('Runnerlockexists; verify priorworker state before resuming: '+str(lock))
    try:
        frontend=json.loads(args.config.read_text())
        native=ng.install(args.cards)
        result=run_study(root,frontend,native,args)
        print(json.dumps(dict(status=result['status'],selected_case=result.get('selected_case'),
                              summary_path=str(root/'summary.json'),complete_ADC_verified=False)),flush=True)
    except Exception as error:
        summary_path=root/'summary.json'
        if summary_path.exists():
            state=json.loads(summary_path.read_text())
            state.update(status='stopped_with_error',stage='error',message=str(error),updated_unix_s=time.time())
            state.setdefault('errors',[]).append(dict(error=repr(error),unix_s=time.time()))
            a.atomic_json(summary_path,state)
        print(json.dumps(dict(status='stopped_with_error',error=repr(error),completed_files_preserved=True)),flush=True)
        raise
    finally:
        lock.unlink()


if __name__=='__main__':main()
