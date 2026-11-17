"""Characterize existing comparator cores with stiff inputs and exact physical output fanout."""

import argparse
from bisect import bisect_left,bisect_right
import copy
from datetime import datetime,timezone
from functools import partial
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
from types import FunctionType

ROOT=Path(__file__).resolve().parent
MANIFEST=ROOT/'SHA256SUMS.txt'
PLAN=ROOT/'PLAN.json'
AUTHORIZATION=ROOT/'AUTHORIZATION.json'
SCHEMA='pam4_sar7_core_sentinels_v1'
CASE_ID='sar7_22_tt_core_sentinels'
PARENT_MANIFEST_SHA='2887bf0705fb20245f65d8745abdd01624debb53b2aa8bdf7c7c5564adad84e1'
PARENT_DECK_SHA='c587a30cf264dc2b815bd9f23b057ce15edeed9b59591edcfe2370a403f3bfbf'
VCM_SOURCE_SUMMARY_SHA='7b93590f85c18b85b1cca6dae343d5e550d7b582d3922ee01a3fdb57a1eea851'
PARENT=Path(os.environ.get('PAM4_SAR7_B2_LOCAL_DRIVE_PACKAGE',ROOT.parent/'PAM4_SAR7_B2_LOCAL_DRIVE_PILOT_20261117')).resolve()
if hashlib.sha256((PARENT/'SHA256SUMS.txt').read_bytes()).hexdigest()!=PARENT_MANIFEST_SHA:
    raise ValueError('Expected immutable case20 physical source')
sys.path.insert(0,str(PARENT))
import sar7_b2_local_drive as parent

base,common,native,score=parent.base,parent.common,parent.native,parent.score
STARTS=datetime(2026,11,17,13,55,tzinfo=timezone.utc)
VCM=.8346351044855786
LSB=.1/128
SENTINELS=(-LSB/16,LSB/16,-LSB,LSB,-.005,.005)
DIAG_NODES=('diag_p','diag_n')
MEASUREMENT='measurements.json'
TIMEOUT_S=540
AUTH_RECORD=dict(schema='pam4_sar7_authorization_v2',
    user_quote='SAR7如果一直修不好你叫codex看看相關論文 然後也可以換方向 由codex決定',
    source_note='20261117T0755_user_delegates_sar7_papers_direction.md',
    source_note_sha256='d9491abfb1429caf097c1c798d763d6529264fb3fa9cbbf2b82cd78b0d4183ea',
    starts_utc='2026-11-17T13:55:00Z',no_expiry=True,
    scope='One short existing-core input characterization; not a SAR ADC validation',
    max_solver_cases_this_packet=1,max_accepted_slurm_jobs=1,cpus_this_job=1,max_concurrent_sar7_jobs=1,
    c2_temporary_throttle=dict(original=5,temporary=4,restore=5),
    excluded=['new long campaigns','PVT','112GS/s integration','other C2 changes','other projects'])
PLAN_RECORD=dict(schema=SCHEMA,authorization=AUTH_RECORD,cases=[dict(case_id=CASE_ID,
    parent_job='761688',parent_manifest_sha256=PARENT_MANIFEST_SHA,parent_deck_sha256=PARENT_DECK_SHA,
    vcm_source_summary_sha256=VCM_SOURCE_SUMMARY_SHA,vcm_V=VCM,sentinels_V=list(SENTINELS),
    frames=12,target_frames=6,cores=7,target_samples=42,precondition_samples=42,
    input_change_start_ps=10,input_change_end_ps=11,common_read_delays_ps=[44,48,60],
    adc_scoring_applicable=False,physical_changes='Seven comparator input port substitutions, two stiff PWL sources and two saved nodes only')])
FILES={'sar7_core_sentinels.py','test_sar7_core_sentinels.py','c2_slot_lease.py','test_c2_slot_lease.py',
       'sar7_core_sentinels.sbatch','PLAN.json','AUTHORIZATION.json','HANDOFF_zh_TW.md'}


def stimulus_records():
    records=[]
    for target_index,target in enumerate(SENTINELS):
        group='nearzero' if abs(target)<LSB/2 else 'one_lsb' if abs(target)<.002 else 'five_mV'
        for role,value in (('precondition',-.005 if target>0 else .005),('target',target)):
            index=len(records);origin=index*native.PERIOD
            records.append(dict(index=index,role=role,target_index=target_index,group=group,
                differential_V=value,expected_polarity=1 if value>0 else 0,
                change_start_s=origin+native.timing(10),change_end_s=origin+native.timing(11)))
    return records


def stimulus_points(side):
    common.need(side in ('p','n'),'Select p or n stimulus polarity')
    sign=1 if side=='p' else -1;records=stimulus_records()
    level=lambda value:VCM+sign*value/2
    points=[(0.,level(records[0]['differential_V']))];previous=records[0]['differential_V']
    for row in records:
        points.extend(((row['change_start_s'],level(previous)),(row['change_end_s'],level(row['differential_V']))))
        previous=row['differential_V']
    return points


def stimulus_card(side):
    values=' '.join(native.number(value) for point in stimulus_points(side) for value in point)
    return f'V_DIAG_{side.upper()} (diag_{side} 0) vsource type=pwl wave=[{values}]'


def input_patch(source):
    rows=source.decode('ascii').splitlines();output=[];seen=set();saves=0;inserted=False
    common.need(not any('diag_p' in row or 'diag_n' in row or row.startswith('V_DIAG_') for row in rows),'Diagnostic nodes already exist')
    for row in rows:
        match=re.match(r'^XCMP([0-6]) ',row)
        if match:
            bit=int(match[1]);common.need(bit not in seen,'Duplicate comparator instance')
            expected=f'XCMP{bit} (sensep sensen vdd vdd clk{bit} q{bit}p q{bit}n) SAR_CMP'
            common.need(row==expected,'Original comparator input/port mapping differs')
            if not inserted:output.extend((stimulus_card('p'),stimulus_card('n')));inserted=True
            row=f'XCMP{bit} (diag_p diag_n vdd vdd clk{bit} q{bit}p q{bit}n) SAR_CMP';seen.add(bit)
        if row.startswith('save '):row+=' diag_p diag_n';saves+=1
        output.append(row)
    common.need(seen==set(native.BITS) and saves==1 and inserted,'Expected seven original input instances and one save row')
    return ('\n'.join(output)+'\n').encode('ascii'),dict(comparator_input_instances=7,ideal_stimulus_sources=2,saved_nodes_added=2,save_rows_changed=1)


def case_record():
    common.need(common.read(PLAN)==PLAN_RECORD and common.read(AUTHORIZATION)==AUTH_RECORD,'Frozen characterization plan/authorization differs')
    return dict(case_id=CASE_ID,fixture='full_case20_circuit_with_stiff_comparator_inputs',corner='tt',
        common_mode_V=VCM,sentinels_V=list(SENTINELS),adc_scoring_applicable=False)


def build(case):
    common.need(case==case_record(),'Only the frozen characterization case is supported')
    source,old=parent.build(parent.case_record())
    common.need(old['portable_sha256']==PARENT_DECK_SHA and hashlib.sha256(source).hexdigest()==PARENT_DECK_SHA,'Wrong immutable parent source bytes')
    bench,counts=input_patch(source);wave=copy.deepcopy(old['wave']);wave['saved_signals'].extend(DIAG_NODES)
    wave['diagnostic_input_pair']=list(DIAG_NODES);wave['adc_scoring_applicable']=False
    return bench,dict(case=case,wave=wave,portable_sha256=hashlib.sha256(bench).hexdigest(),
        parent_job='761688',parent_manifest_sha256=PARENT_MANIFEST_SHA,parent_deck_sha256=PARENT_DECK_SHA,
        vcm_source_summary_sha256=VCM_SOURCE_SUMMARY_SHA,stimulus=stimulus_records(),input_patch_counts=counts,
        physical_circuit_and_timing_unchanged=True,adc_scoring_applicable=False,
        authorization=AUTH_RECORD,authorization_sha256=common.sha(AUTHORIZATION))


def verify():
    common.need(common.read(PLAN)==PLAN_RECORD and common.read(AUTHORIZATION)==AUTH_RECORD,'Plan/authorization differs')
    entries=[line.split('  ',1) for line in MANIFEST.read_text(encoding='ascii').splitlines()]
    common.need(len(entries)==len(FILES) and {name for digest,name in entries}==FILES,'Unexpected package inventory')
    for digest,name in entries:
        path=ROOT/name
        common.need(path.resolve().parent==ROOT and common.sha(path)==digest and b'\r' not in path.read_bytes(),'Package differs or is not LF: '+name)
    common.need(b'\r' not in MANIFEST.read_bytes(),'Manifest must use LF')
    _,old=parent.verify()
    common.need(common.sha(parent.MANIFEST)==PARENT_MANIFEST_SHA and old['portable_sha256']==PARENT_DECK_SHA,'Frozen parent differs')
    case=case_record();return case,build(case)[1]


def approval_record(root,meta,approved):
    return dict(approved=approved,platform='Olympus',campaign=SCHEMA,case_ids=[CASE_ID],
        authorized_run_root=str(root),design_source_sha256=common.sha(MANIFEST),deck_sha256_by_case={CASE_ID:meta['portable_sha256']})


def stable_rail(time,positive,negative,start,end,vdd,expected):
    final=score.classify(score.interpolate(time,positive,end),score.interpolate(time,negative,end),vdd)
    arrival=None;arrived_at=None
    if final is not None:
        samples=[start,*time[bisect_right(time,start):bisect_left(time,end)],end]
        samples=sorted(set(samples+[start+native.timing(delay) for delay in (44,48) if start+native.timing(delay)<end]))
        states=[score.classify(score.interpolate(time,positive,at),score.interpolate(time,negative,at),vdd) for at in samples]
        index=len(states)-1
        while index>0 and states[index-1]==final:index-=1
        arrived_at=samples[index];arrival=(arrived_at-start)/native.PS
    return dict(observed_class=final,stable_observed_delay_ps=arrival,stable_observed_at_s=arrived_at,
        stable_expected_at_s=arrived_at if final==expected else None,
        stable_expected_delay_ps=arrival if final==expected else None,
        arrival_scope='First admitted saved/interpolated observation remaining at the final class through +60ps; not an exact continuous crossing')


def characterize(values,wave,stimulus):
    required={'time',*wave['saved_signals']};time=score.validate_trace_arrays(values,required,wave['stop_s'],wave['strobe_s'])
    common.need(len(stimulus)==len(wave['conversions'])==12,'Expected twelve existing clock frames')
    vdd=wave['vdd_V'];rows=[]
    def at(node,instant):return score.interpolate(time,values[node],instant)
    def input_observe(instant,expected):
        pair=[at(node,instant) for node in DIAG_NODES];diff=pair[0]-pair[1];cm=sum(pair)/2
        return dict(pair_V=pair,diff_V=diff,common_mode_V=cm,
            matches_expected=abs(diff-expected)<=1e-8 and abs(cm-VCM)<=1e-8)
    for cv,stim in zip(wave['conversions'],stimulus,strict=True):
        common.need(cv['index']==stim['index'],'Clock/stimulus frame mismatch')
        for trial in cv['trials']:
            bit=trial['bit'];compare=trial['compare_s'];end=compare+native.timing(60)
            common.need(end<=time[-1] and end<cv['index']*wave['period_s']+native.timing(567.5),'Common read must precede comparator reset')
            pairs=dict(raw=(f'q{bit}p',f'q{bit}n'),xy=(f'XCMP{bit}.x',f'XCMP{bit}.y'),
                mid=(f'qmid{bit}p',f'qmid{bit}n'),decode=(f'qdecode{bit}p',f'qdecode{bit}n'))
            def observe(instant):
                result=dict(at_s=instant,delay_from_compare_ps=(instant-compare)/native.PS,
                    input=input_observe(instant,stim['differential_V']),clock_V=at(f'clk{bit}',instant),trial_V=at(f'trial{bit}',instant),
                    register_pair_V=[at(f'bit{bit}',instant),at(f'bit{bit}b',instant)])
                for stage,pair in pairs.items():
                    volts=[at(node,instant) for node in pair]
                    logical=volts[::-1] if stage in ('xy','mid') else volts
                    decision=score.classify(*logical,vdd)
                    result[stage]=dict(pair_V=volts,**{'class':decision},correct=None if decision is None else decision==stim['expected_polarity'])
                return result
            reset_time=compare-native.timing(2);reset_values=observe(reset_time)
            xy=reset_values['xy']['pair_V'];raw=reset_values['raw']['pair_V'];mid=reset_values['mid']['pair_V'];decode=reset_values['decode']['pair_V']
            reset=dict(at_s=reset_time,clock_low=reset_values['clock_V']<=.2*vdd,
                xy_both_high=min(xy)>=.8*vdd,raw_both_low=max(raw)<=.2*vdd,
                mid_both_high=min(mid)>=.8*vdd,decode_both_low=max(decode)<=.2*vdd,
                xy_difference_V=xy[0]-xy[1],raw_difference_V=raw[0]-raw[1],
                input=reset_values['input'])
            reset['pass']=all(reset[k] for k in ('clock_low','xy_both_high','raw_both_low','mid_both_high','decode_both_low'))
            stable={}
            for stage,pair in pairs.items():
                logical=pair[::-1] if stage in ('xy','mid') else pair
                stable[stage]=stable_rail(time,values[logical[0]],values[logical[1]],compare,end,vdd,stim['expected_polarity'])
            probes=[input_observe(instant,stim['differential_V']) for instant in (reset_time,compare,end)]
            rows.append(dict(cycle_index=cv['index'],bit=bit,role=stim['role'],target_index=stim['target_index'],group=stim['group'],
                differential_V=stim['differential_V'],expected_polarity=stim['expected_polarity'],reset=reset,
                actual_input_valid=all(probe['matches_expected'] for probe in probes),
                input_probes=probes,at_original_read=observe(trial['read_s']),
                at_44=observe(compare+native.timing(44)),at_48=observe(compare+native.timing(48)),at_60=observe(end),stable=stable))
    controls=[row for row in rows if row['role']=='precondition' or abs(row['differential_V'])==.005]
    common.need(len(rows)==84 and len(controls)==56,'Expected84 samples and56 strong controls')
    common.need(all(row['actual_input_valid'] for row in rows),'Stiff diagnostic input differs from the declared common mode or differential')
    def stable_by(row,label):
        arrival=row['stable']['raw']['stable_expected_at_s']
        return arrival is not None and arrival<=row['at_'+label]['at_s']
    control=dict(required=56,raw_correct_by_44=sum(row['at_44']['raw']['correct'] is True for row in controls),
        raw_stable_correct_by_44=sum(stable_by(row,'44') for row in controls),
        reset_valid=sum(row['reset']['pass'] for row in controls),input_valid=sum(row['actual_input_valid'] for row in controls))
    control['valid']=(control['raw_correct_by_44']==control['raw_stable_correct_by_44']==control['reset_valid']==control['input_valid']==56
        and all(row['reset']['pass'] for row in rows))
    targets={}
    for group in ('nearzero','one_lsb','five_mV'):
        subset=[row for row in rows if row['role']=='target' and row['group']==group]
        record=dict(samples=len(subset))
        for label,key in (('original_read','at_original_read'),('44','at_44'),('48','at_48'),('60','at_60')):
            record['raw_available_'+label]=sum(row[key]['raw']['class'] is not None for row in subset)
            record['raw_correct_'+label]=sum(row[key]['raw']['correct'] is True for row in subset)
            if label!='original_read':record['raw_stable_correct_by_'+label]=sum(stable_by(row,label) for row in subset)
        targets[group]=record
    return dict(schema=SCHEMA,status='characterized',case_id=CASE_ID,adc_screen_applicable=False,adc_screen='not_applicable',adc_screen_pass=None,
        controls=control,target_groups=targets,reset_valid_trials=sum(row['reset']['pass'] for row in rows),
        actual_input_valid_trials=sum(row['actual_input_valid'] for row in rows),trials=rows,stimulus=stimulus,
        classification=dict(rail_low_fraction=.2,rail_high_fraction=.8,positive_raw='p high, n low',
            positive_xy='y high, x low',positive_mid='n high, p low',positive_decode='p high, n low'),
        limits=['This is existing-core input characterization, not a SAR ADC result',
            'Late/internal resolution never rescues the original-read raw classification',
            'Saved0.25ps observations through+60 are not exact continuous delay or statistical offset/noise validation'])


def execution_namespace():
    context=dict(base.run.__globals__)
    context.update(build=build,PLAN=PLAN,MANIFEST=MANIFEST,SCHEMA=SCHEMA,TIMEOUT_S=TIMEOUT_S,
        collect=collect_diagnostic,verify_approval=lambda case,path:common.need(common.read(path)==approval_record(path.parent,build(case)[1],True),'Exact characterization approval differs'))
    context['evidence']=FunctionType(base.evidence.__code__,context)
    context['stage']=FunctionType(base.stage.__code__,context)
    return context


def evidence(case,directory):
    return execution_namespace()['evidence'](case,directory)


def parse_and_characterize(directory,wave,status,hashes,case,meta):
    live=common.raw_inventory(directory)
    common.need(common.matches_historical_inventory(status['raw_inventory'],live),'Existing raw inventory differs')
    traces=[row for row in live if row['path'] in ('raw/tranResponse.tran',base.review.RAW_NAME)]
    common.need(len(traces)==1,'Expected one completed transient')
    required={'time',*wave['saved_signals']};common.need(len(required)==146,'Expected146 existing+diagnostic saved traces')
    calls=0
    def selected(path):
        nonlocal calls
        calls+=1;common.need(calls==1,'Only one characterization PSF parse is permitted')
        return base.review.parse_selected(path,required=required)
    raw=base.review.safe_raw(directory,dict(status,raw_inventory=live),traces[0]['path'].removeprefix('raw/'),parser=selected)
    common.need(calls==1 and raw.sha256==traces[0]['sha256'] and raw.sweep_names==['time'] and raw.unit('time')=='s'
        and all(raw.unit(node)=='V' for node in DIAG_NODES),'Wrong characterization PSF or units')
    report=characterize(raw.values,wave,meta['stimulus'])
    report.update(case=case,execution_files_sha256=hashes,tran_sha256=raw.sha256,slurm_task_id=status['slurm_job_id'],
        solver_seconds=status['spectre_wall_seconds'],raw_bytes=sum(row['bytes'] for row in live),
        psf_parse_count=calls,selected_required=sorted(required),manifest_sha256=common.sha(MANIFEST),
        portable_deck_sha256=meta['portable_sha256'],parent_manifest_sha256=PARENT_MANIFEST_SHA,parent_deck_sha256=PARENT_DECK_SHA,
        authorization_sha256=common.sha(AUTHORIZATION))
    return report,live


def collect_diagnostic(root,case):
    directory=root/CASE_ID;path=directory/MEASUREMENT
    with base.lock_case(directory):
        wave,status,hashes=evidence(case,directory);_,meta=build(case)
        if path.exists():
            report=common.read(common.owned_file(directory,path)[0]);live=common.raw_inventory(directory)
            traces=[r for r in live if r['path'] in ('raw/tranResponse.tran',base.review.RAW_NAME)]
            common.need(report['schema']==SCHEMA and report['status']=='characterized' and report['case']==case
                and report['execution_files_sha256']==hashes and len(traces)==1 and report['tran_sha256']==traces[0]['sha256']
                and report['manifest_sha256']==common.sha(MANIFEST) and report['psf_parse_count']==1
                and common.matches_historical_inventory(status['raw_inventory'],live),'Existing characterization report provenance differs')
            return report
        report,before=parse_and_characterize(directory,wave,status,hashes,case,meta)
        after_wave,after_status,after_hashes=evidence(case,directory)
        common.need(after_wave==wave and after_status==status and after_hashes==hashes and common.raw_inventory(directory)==before,
                    'Execution evidence/raw changed during characterization')
        report['source_unchanged_during_parse']=True
        common.write_new(path,report);return report


def check_started(now):
    common.need(now>=STARTS,'New authorization has not started')


def validate_submission(text,jobid,now):
    common.need(re.fullmatch(r'\d+',jobid or '') is not None,'SLURM_JOB_ID must contain digits')
    ids=re.findall(r'(?:^|\s)JobId=(\S+)',text);times=re.findall(r'(?:^|\s)SubmitTime=(\S+)',text)
    common.need(ids==[jobid] and len(times)==1 and re.fullmatch(r'\d+',times[0]) is not None,'Ambiguous Slurm submission evidence')
    submitted=datetime.fromtimestamp(int(times[0]),timezone.utc)
    common.need(STARTS<=submitted<=now,'Job submission must be after new authorization start and not in the future')
    return dict(slurm_job_id=jobid,submit_time_utc=submitted.isoformat(),authorization_source_sha256=AUTH_RECORD['source_note_sha256'])


def query_submission(now):
    check_started(now);jobid=os.environ.get('SLURM_JOB_ID','')
    common.need(re.fullmatch(r'\d+',jobid) is not None,'Run requires an actual Slurm job')
    env=dict(os.environ,SLURM_TIME_FORMAT='%s',TZ='UTC',LC_ALL='C')
    result=subprocess.run(['scontrol','--oneliner','show','job',jobid],env=env,timeout=15,check=True,capture_output=True,text=True)
    return validate_submission(result.stdout,jobid,now)


def existing_stage(root,case,model_root):
    directory=root/CASE_ID
    common.need(directory.is_dir() and directory==directory.resolve(strict=True),'Run requires an existing real byte-exact staged characterization')
    source,meta=build(case);proof=base.original.model_preflight.verify_private_kit(model_root,'tt')
    token=base.review.gm_center64.BASE.MODEL_TOKEN.encode('ascii');model=proof['model_root'].encode('utf-8');bench=source.replace(token,model)
    common.need(source.count(token)==1 and bench.replace(model,token)==source,'Nonreversible model root substitution')
    expected=dict(meta,model_preflight=proof,bench_sha256=hashlib.sha256(bench).hexdigest())
    common.need(common.read(directory/'case.json')==expected and (directory/'bench.scs').read_bytes()==bench,'Existing staged characterization differs')
    return directory


def run(root,case,model_root,approval):
    receipt=query_submission(datetime.now(timezone.utc));existing_stage(root,case,model_root)
    receipt_path=root/'submission_proof.json'
    if receipt_path.exists():common.need(common.read(receipt_path)==receipt,'Existing submission proof differs')
    else:common.write_new(receipt_path,receipt)
    context=execution_namespace();context['stage']=existing_stage
    return FunctionType(base.run.__code__,context)(root,case,model_root,approval)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('verify','approval-template','stage','run','collect-only'))
    parser.add_argument('--root',type=Path);parser.add_argument('--approval',type=Path);parser.add_argument('--model-root',type=Path)
    args=parser.parse_args();case,meta=verify()
    if args.mode=='verify':print(CASE_ID,meta['portable_sha256'],'ADC screen N/A');return
    common.need(args.root is not None and args.approval is not None,'Supply isolated root and approval')
    root=common.checked_root(args.root);approval=args.approval.absolute()
    common.need(root.name.startswith('pam4_sar7_core_sentinels_') and approval.parent==root,'Use a new characterization root and its own approval')
    if args.mode=='approval-template':common.write_new(approval,approval_record(root,meta,False));return
    common.need(common.read(approval)==approval_record(root,meta,True),'Exact characterization approval differs')
    if args.mode in ('stage','run'):
        common.need(args.model_root is not None,'Use the existing approved private model root')
        if args.mode=='stage':check_started(datetime.now(timezone.utc));print(execution_namespace()['stage'](root,case,args.model_root));return
        report=run(root,case,args.model_root,approval)
    else:report=collect_diagnostic(root,case)
    target=root/'sar7_core_sentinels_summary.json'
    if target.exists():common.need(common.read(target)==report,'Existing characterization summary differs')
    else:common.write_new(target,report)
    print(json.dumps(dict(summary=str(target),sha256=common.sha(target),control_valid=report['controls']['valid'],adc_screen='not_applicable')))


if __name__=='__main__':main()
