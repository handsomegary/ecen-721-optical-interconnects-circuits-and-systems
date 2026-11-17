#!/usr/bin/env python3
"""Bounded three-candidate r6b screen queued after r6; Python 3.6.

Reuses an exactly matched, completed r6 baseline. No baseline simulation is
repeated. All additional runs execute sequentially, occupying the r6 slot
only after its runner has finished. Never opens final-holdout directories.
"""
import argparse
import copy
import hashlib
import json
import os
import time
from pathlib import Path

import adc_backend_screen_r6 as common

a=common.a
ng=common.ng
opt=common.opt
pi=common.pi
NAME='adc_backend_r6b_screen_20261013'
REQUIRED_R6_SHA256='f14fb804fafa9f6b4f59b793ba0ddb232ed3eeb25ed380bf922b064a13c74b2b'
BASELINE=common.BASELINE
NEW_ORDER=['input3_r350_bias060','input2_r400_bias060','input3_r350_bias065']


def cases():
    reference=common.cases()[BASELINE]
    result={BASELINE:copy.deepcopy(reference)}
    for name,width,resistance,bias in [
        ('input3_r350_bias060',3e-6,350.,.60),
        ('input2_r400_bias060',2e-6,400.,.60),
        ('input3_r350_bias065',3e-6,350.,.65)]:
        cfg=copy.deepcopy(reference)
        cfg.update(buffer_width_m=width,current_width_m=3e-6,load_ohm=resistance,
                   n_bias_V=bias,degeneration_ohm=0.,secondary_cap_F=10e-15,
                   secondary_switch_width_m=1e-6)
        result[name]=cfg
    return result


def identity(frontend,native,noise_check):
    if a.digest(common.__file__)!=REQUIRED_R6_SHA256:
        raise ValueError('r6 helper source differs from the reviewed immutable version')
    original=common.file_identity(frontend,native,noise_check)
    return dict(schema_version=1,study=NAME,frontend=frontend,native_geometry=native,
                new_cases={name:cases()[name] for name in NEW_ORDER},new_case_order=NEW_ORDER,
                baseline_configuration=cases()[BASELINE],baseline_source_study=common.NAME,
                gates=copy.deepcopy(common.GATES),training_symbols=common.TRAIN_COUNT,
                training_data_seed=common.DATA_SEED,training_noise_seed=common.NOISE_SEED,
                noise_check_enabled=noise_check,script_sha256=a.digest(__file__),
                reviewed_r6_helper_sha256=REQUIRED_R6_SHA256,
                dependency_script_hashes=original['script_hashes'],
                training_data_reuse='Same512training-onlydata allows an exactly matched existing baseline. This isnotnewholdout.',
                limits=dict(maximum_new_DC_cases=3,maximum_new_noiseless_training_cases=3,
                            maximum_new_noise_training_cases=1,maximum_simultaneous_jobs=1),
                decision_rule='UnchangedDCgates, then training-only secondaryADC+FFE SER/MSE; hardwarefixedbeforeoptionalnoise181.',
                holdout_accessed=False,complete_ADC_verified=False)


def wait_for_r6(root,summary,source,wait,limit_s):
    started=time.time()
    observed_pid=None
    while True:
        lock=source/'runner.lock'
        if lock.exists():
            try:observed_pid=int(json.loads(lock.read_text())['pid'])
            except (ValueError,KeyError):pass
        status=json.loads((source/'summary.json').read_text()) if (source/'summary.json').exists() else {}
        process_alive=False
        if observed_pid is not None:
            try:
                os.kill(observed_pid,0)
                process_alive=True
            except ProcessLookupError:pass
            except PermissionError:process_alive=True
        complete=status.get('status') in ('complete','complete_with_failures') and status.get('stage')=='complete'
        if complete and not lock.exists() and not process_alive:
            summary['predecessor_completion']=dict(study=str(source),status=status['status'],
                                                  last_observed_runner_pid=observed_pid,
                                                  runner_lock_absent=True,observed_process_finished=True,
                                                  source_summary_sha256=a.digest(source/'summary.json'))
            common.checkpoint(root,summary,'predecessor_finished','r6 finished; its single simulation slot is now available to r6b.')
            return
        if not wait:
            raise RuntimeError('r6 is not complete and stopped; use --wait-for-r6 to queue this bounded screen')
        if time.time()-started>=limit_s:
            raise RuntimeError('Timed out waiting for r6 completion; no r6b simulation was launched')
        summary['predecessor_last_observed']=dict(status=status.get('status'),stage=status.get('stage'),
                                                lock_present=lock.exists(),runner_pid=observed_pid)
        common.checkpoint(root,summary,'waiting_for_r6','Waiting for r6 to finish; no r6b simulation is running.')
        time.sleep(30)


def verify_baseline(source,frontend,native,noise_check):
    """Only reads completed baseline runs; no validation directory is opened."""
    old=json.loads((source/'identity.json').read_text())
    expected=cases()[BASELINE]
    if old['frontend']!=frontend or old['native_geometry']!=native:
        raise ValueError('Baseline frontend or native geometry identity differs')
    if old['cases'][BASELINE]!=expected:
        raise ValueError('Baseline physical configuration is not an exact match')
    if (old['training_symbols'],old['data_seed'],old['noise_seed'])!=(common.TRAIN_COUNT,common.DATA_SEED,common.NOISE_SEED):
        raise ValueError('Baseline training protocol differs')
    if old['script_hashes'].get('adc_backend_screen_r6.py')!=REQUIRED_R6_SHA256:
        raise ValueError('Baseline was not produced by the reviewed r6 helper')
    current=common.file_identity(frontend,native,old['optional_noise_check_enabled'])
    if old['script_hashes']!=current['script_hashes']:
        raise ValueError('Baseline dependency scripts changed')
    symbols=opt.random_symbols(common.DATA_SEED,pi.WARMUP+common.TRAIN_COUNT+pi.GUARD)
    requested=[('dc',None),('noiseless',None)]+([('noise181',common.NOISE_SEED)] if noise_check else [])
    result={}
    provenance={}
    for mode,seed in requested:
        directory=source/mode/BASELINE
        lines=common.dc_deck(frontend,expected) if mode=='dc' else common.pam4_deck(frontend,expected,symbols,seed)[0]
        deck_sha=hashlib.sha256(('\n'.join(lines)+'\n').encode()).hexdigest()
        execution=json.loads((directory/'execution.json').read_text())
        if execution.get('status')!='simulation_complete' or execution['deck_sha256']!=deck_sha:
            raise ValueError('Baseline simulation is incomplete or its deck differs: '+mode)
        if a.digest(directory/'bench.scs')!=deck_sha:
            raise ValueError('Baseline saved deck changed: '+mode)
        for relative,digest in execution['raw_hashes'].items():
            path=(directory/relative).resolve()
            if directory.resolve() not in path.parents:raise ValueError('Baseline raw path outside its owned case')
            if a.digest(path)!=digest:raise ValueError('Baseline raw hash changed: '+mode)
        measured=json.loads((directory/'summary.json').read_text())
        if measured.get('status')!='complete' or measured['execution']!=execution:
            raise ValueError('Baseline derived summary disagrees with execution: '+mode)
        if mode=='dc':
            if measured['configuration']!=expected:raise ValueError('Baseline DC configuration changed')
        else:
            if measured['data_seed']!=common.DATA_SEED or measured['train_symbols']!=common.TRAIN_COUNT:
                raise ValueError('Baseline sample count or seed differs')
            if measured['symbol_sequence_sha256']!=opt.canonical_hash(symbols) or measured['noise_seed']!=seed:
                raise ValueError('Baseline symbol sequence or noise seed differs')
            if measured['raw_transient_sha256']!=a.digest(a._raw_file(directory)):
                raise ValueError('Baseline parsed raw provenance differs')
        result[mode]=measured
        provenance[mode]=dict(source_directory=str(directory),summary_sha256=a.digest(directory/'summary.json'),
                              execution_sha256=a.digest(directory/'execution.json'),deck_sha256=deck_sha,
                              raw_hashes=execution['raw_hashes'])
    return result,dict(source_identity_sha256=a.digest(source/'identity.json'),
                       exact_frontend_native_cards_config_deck_symbols_verified=True,
                       completed_raw_hashes_verified=True,baseline_simulations_repeated=0,runs=provenance)


def compact_training(result,source_path=None):
    record=dict(status='complete',case=result['case'],noise_seed=result['noise_seed'],
                 compact_scores=result['compact_scores'],VDD_power=result['VDD_power'])
    if source_path is not None:
        record.update(summary_sha256=a.digest(source_path),source_summary=str(source_path),reused_verified_baseline=True)
    return record


def run_study(root,source,frontend,native,args):
    common.write_bound_record(root/'identity.json',identity(frontend,native,args.noise_check))
    path=root/'summary.json'
    summary=json.loads(path.read_text()) if path.exists() else dict(
        schema_version=1,status='running' if args.run else 'generated_only',
        identity_sha256=a.digest(root/'identity.json'),DC_cases={},noiseless_training={},noise_training={},errors=[],
        holdout_accessed=False,complete_ADC_verified=False,
        limitations=['Threefixedadditionalhardwarecandidates; noautomaticparameterexpansion.',
                     'Existingbaseline isreusedonlyafterconfig/deck/raw/symbol/dependencyidentity checks.',
                     '512training-onlysymbols,224selectionFFEwindows; nofreshholdoutorBERcertification.',
                     'All64comparatorsremainreset; noactual7-bitconversion.',
                     'InputW3candidates addrealnativegateparasitics; sameprimary56GHzloadgateisrequired.',
                     'NoPVT/mismatch/jitter/PEX; measuredpowerexcludesclock/biasgenerators,CDAC/reference/control/DSP.'])
    if summary['identity_sha256']!=a.digest(root/'identity.json'):raise ValueError('r6b study identity changed')
    configs=cases()
    if not args.run:
        for name in NEW_ORDER:
            common.execute(root/'dc'/name,common.dc_deck(frontend,configs[name]),False,args.timeout)
        common.checkpoint(root,summary,'generated_only','Three fixed r6b DC/AC decks generated; no simulations launched.')
        return summary
    wait_for_r6(root,summary,source,args.wait_for_r6,args.wait_limit_seconds)
    baseline,proof=verify_baseline(source,frontend,native,args.noise_check)
    common.write_bound_record(root/'baseline_reuse.json',proof)
    summary['baseline_reuse_sha256']=a.digest(root/'baseline_reuse.json')
    summary['DC_cases'][BASELINE]=baseline['dc']
    summary['noiseless_training'][BASELINE]=compact_training(baseline['noiseless'],source/'noiseless'/BASELINE/'summary.json')
    if args.noise_check:
        summary['noise_training'][BASELINE]=compact_training(baseline['noise181'],source/'noise181'/BASELINE/'summary.json')
    common.checkpoint(root,summary,'baseline_reused','Completed r6 baseline passed exact identity checks; no baseline rerun is needed.')
    for name in NEW_ORDER:
        common.checkpoint(root,summary,'dc_running','Checking native input geometry, gain and actual r3 loading: '+name)
        directory=root/'dc'/name
        execution=common.execute(directory,common.dc_deck(frontend,configs[name]),True,min(args.timeout,300))
        if execution['status']!='simulation_complete':
            summary['DC_cases'][name]=dict(status='failed',execution=execution)
            continue
        measured=common.load.metrics(directory,True)
        result=dict(status='complete',configuration=configs[name],execution=execution,
                    metrics=measured,eligibility=common.dc_eligibility(name,measured))
        common.write_bound_record(directory/'summary.json',result)
        summary['DC_cases'][name]=result
        common.checkpoint(root,summary,'dc_case_complete','Completed r6b DC/AC screen: '+name)
    symbols=opt.random_symbols(common.DATA_SEED,pi.WARMUP+common.TRAIN_COUNT+pi.GUARD)
    for name in NEW_ORDER:
        if not summary['DC_cases'].get(name,{}).get('eligibility',{}).get('eligible_for_training'):continue
        common.checkpoint(root,summary,'noiseless_training_running','Running bounded 512-symbol training-only PAM4: '+name)
        directory=root/'noiseless'/name
        lines,clocks=common.pam4_deck(frontend,configs[name],symbols,None)
        execution=common.execute(directory,lines,True,args.timeout)
        if execution['status']!='simulation_complete':
            summary['noiseless_training'][name]=dict(status='failed',execution=execution)
            continue
        result=common.training_analysis(directory,execution,clocks,symbols)
        result.update(status='complete',case=name,noise_seed=None)
        common.write_bound_record(directory/'summary.json',result)
        summary['noiseless_training'][name]=compact_training(result)
        summary['noiseless_training'][name]['summary_sha256']=a.digest(directory/'summary.json')
        common.checkpoint(root,summary,'noiseless_case_complete','Completed r6b noiseless training: '+name)
    completed={name:r for name,r in summary['noiseless_training'].items() if r.get('status')=='complete'}
    base_primary=completed[BASELINE]['compact_scores']['primary']['ideal7bit_FFE']['selection_SER']
    eligible={name:r for name,r in completed.items() if name==BASELINE or
              r['compact_scores']['primary']['ideal7bit_FFE']['selection_SER']<=max(common.GATES['max_primary_training_SER'],base_primary)}
    selected=min(eligible,key=lambda name:opt.score_key(eligible[name]['compact_scores']['secondary']['ideal7bit_FFE']))
    chosen=dict(selected_case=selected,configuration=configs[selected],training_data_seed=common.DATA_SEED,
                training_only=True,holdout_accessed=False,selection_stage='beforeoptionalnoise181',
                selection_key=opt.score_key(eligible[selected]['compact_scores']['secondary']['ideal7bit_FFE']),
                baseline_key=opt.score_key(completed[BASELINE]['compact_scores']['secondary']['ideal7bit_FFE']),
                compact_training_scores={name:r['compact_scores'] for name,r in completed.items()},
                baseline_reuse_sha256=summary['baseline_reuse_sha256'],complete_ADC_verified=False)
    common.write_bound_record(root/'selected_before_noise.json',chosen)
    summary['selected_case']=selected
    summary['selected_before_noise_sha256']=a.digest(root/'selected_before_noise.json')
    common.checkpoint(root,summary,'hardware_selected_before_noise','Fixed r6b hardware selection before the noise check: '+selected)
    if args.noise_check and selected!=BASELINE:
        common.checkpoint(root,summary,'noise_training_running','Checking the selected candidate with noise181; exact baseline noise run is reused.')
        directory=root/'noise181'/selected
        lines,clocks=common.pam4_deck(frontend,configs[selected],symbols,common.NOISE_SEED)
        execution=common.execute(directory,lines,True,args.timeout)
        if execution['status']!='simulation_complete':
            summary['noise_training'][selected]=dict(status='failed',execution=execution)
        else:
            result=common.training_analysis(directory,execution,clocks,symbols)
            result.update(status='complete',case=selected,noise_seed=common.NOISE_SEED,
                          hardware_selected_before_noise_sha256=summary['selected_before_noise_sha256'])
            common.write_bound_record(directory/'summary.json',result)
            summary['noise_training'][selected]=compact_training(result)
            summary['noise_training'][selected]['summary_sha256']=a.digest(directory/'summary.json')
            common.checkpoint(root,summary,'noise_case_complete','Completed the fixed-candidate r6b noise check.')
    allrecords=list(summary['DC_cases'].values())+list(summary['noiseless_training'].values())+list(summary['noise_training'].values())
    summary['status']='complete_with_failures' if any(r.get('status')=='failed' for r in allrecords) else 'complete'
    common.checkpoint(root,summary,'complete','Bounded r6b milestone finished; no further candidates or final validation will be launched automatically.')
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',action='store_true')
    p.add_argument('--noise-check',action='store_true')
    p.add_argument('--wait-for-r6',action='store_true')
    p.add_argument('--wait-limit-seconds',type=int,default=21600)
    p.add_argument('--timeout',type=int,default=7200)
    p.add_argument('--config',type=Path,default=a.PROJECT/'configs/ctle_selected_r3.json')
    p.add_argument('--cards',type=Path,default=ng.CARD_PATH)
    args=p.parse_args()
    if not 60<=args.timeout<=7200:p.error('Simulationtimeout mustbe60..7200seconds')
    if not 30<=args.wait_limit_seconds<=86400:p.error('Waitlimit mustbe30..86400seconds')
    if not (a.PROJECT/'.codex_project6_owned').exists():raise ValueError('Projectmarker absent')
    root=a.PROJECT/'runs'/NAME
    source=a.PROJECT/'runs'/common.NAME
    root.mkdir(parents=True,exist_ok=True)
    lock=root/'runner.lock'
    try:
        with lock.open('x') as handle:handle.write(json.dumps(dict(pid=os.getpid(),started_unix_s=time.time())))
    except FileExistsError:
        raise RuntimeError('r6b runnerlockexists; verify priorworker state before resuming')
    try:
        frontend=json.loads(args.config.read_text())
        native=ng.install(args.cards)
        result=run_study(root,source,frontend,native,args)
        print(json.dumps(dict(status=result['status'],selected_case=result.get('selected_case'),
                              summary_path=str(root/'summary.json'),complete_ADC_verified=False)),flush=True)
    except Exception as error:
        path=root/'summary.json'
        if path.exists():
            state=json.loads(path.read_text())
            state.update(status='stopped_with_error',stage='error',message=str(error),updated_unix_s=time.time())
            state.setdefault('errors',[]).append(dict(error=repr(error),unix_s=time.time()))
            a.atomic_json(path,state)
        print(json.dumps(dict(status='stopped_with_error',error=repr(error),completed_files_preserved=True)),flush=True)
        raise
    finally:lock.unlink()


if __name__=='__main__':main()
