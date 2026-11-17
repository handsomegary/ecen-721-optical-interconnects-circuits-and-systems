"""One bit2-only native decoder drive2 pilot and a two-picosecond read-budget transfer."""

import argparse
from bisect import bisect_left,bisect_right
import copy
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from types import FunctionType,SimpleNamespace

ROOT=Path(__file__).resolve().parent
MANIFEST=ROOT/'SHA256SUMS.txt'
PLAN=ROOT/'PLAN.json'
AUTHORIZATION=ROOT/'AUTHORIZATION.json'
SCHEMA='pam4_sar7_b2_local_drive_pilot_v1'
CASE_ID='sar7_20_tt_175gs_b2_local_drive'
PARENT_MANIFEST_SHA='29234008ed5dcc04727ec9200c5a1e3b63c57fd8a589bec971b304eae319934d'
PARENT_DECK_SHA='13cb54f364340ce86656e3f1b7280f53fa69f11d996ae55ac65b5ee2b63f8d73'
PARENT_SUMMARY_SHA='bb7c5418c967d1b7e76d31e93e6dea64115e7888660b521cca797292c35e1594'
PARENT=Path(os.environ.get('PAM4_SAR7_COMPARE_WINDOW_PACKAGE',ROOT.parent/'PAM4_SAR7_COMPARE_WINDOW_PILOT_20261117')).resolve()
if hashlib.sha256((PARENT/'SHA256SUMS.txt').read_bytes()).hexdigest()!=PARENT_MANIFEST_SHA:
    raise ValueError('Expected exact measured case19 package')
sys.path.insert(0,str(PARENT))
import sar7_compare_window as parent

base,common,native,score=parent.base,parent.common,parent.native,parent.score
STARTS=datetime(2026,11,17,5,37,tzinfo=timezone.utc)
EXPIRES=datetime(2026,11,17,13,37,tzinfo=timezone.utc)
AUTH_RECORD=dict(schema='pam4_sar7_authorization_v1',user_quote='Yes, 8 hours',
    source_note='20261116T2337_user_delegates_8h_sar7_175gs.md',
    source_note_sha256='26523d076e396f82acc8844f3441c3517ebba4f05e2073e1629436586287da58',
    starts_utc='2026-11-17T05:37:00Z',expires_utc='2026-11-17T13:37:00Z',
    scope='SAR7 single-channel 1.75GS/s TT short fixes',max_solver_cases_this_packet=1,
    cpus_this_job=1,max_concurrent_sar7_cpus=2,c2_untouched=True,
    excluded=['PVT','long campaigns','112GS/s integration','other projects','raw deletion','C2 changes'])
WAITS=(30,45,25,26,31,8,6)
EVALS=(37,44,40,40,47,44,48)
GUARD_PS=.5
LOCAL_CELLS={'SAR_OAI21_X2':'SAR_B2_OAI21_X4','SAR_NOR3_P3':'SAR_B2_NOR3_P6','SAR_NDINV2':'SAR_B2_INV4'}
TARGETS={}
for side,pad in (('p',''),('n','d_')):
    TARGETS[f'XNDO{side}2']=('SAR_OAI21_X2','SAR_B2_OAI21_X4',('trial2',f'qdecode2{side}','conv',f'{pad}cb2o','vdd'),'oai')
    TARGETS[f'XNDZ{side}2']=('SAR_NOR3_P3','SAR_B2_NOR3_P6',('trial2',f'qdecode2{side}','convb',f'{pad}c2z','vdd'),'nor')
    TARGETS[f'XNDIO{side}2']=('SAR_NDINV2','SAR_B2_INV4',(f'{pad}cb2o',f'{pad}c2o','vdd'),'decoder_inv')
    TARGETS[f'XNDIZ{side}2']=('SAR_NDINV2','SAR_B2_INV4',(f'{pad}c2z',f'{pad}cb2z','vdd'),'decoder_inv')
    TARGETS[f'XQOUT2{side}']=('SAR_NDINV2','SAR_B2_INV4',(f'qmid2{side}',f'qdecode2{side}','vdd'),'qbuffer_second')
PLAN_RECORD=dict(schema=SCHEMA,authorization=AUTH_RECORD,cases=[dict(case_id=CASE_ID,
    parent_job='761674',parent_manifest_sha256=PARENT_MANIFEST_SHA,parent_deck_sha256=PARENT_DECK_SHA,
    source_summary_sha256=PARENT_SUMMARY_SHA,waits_ps=list(WAITS),evals_ps=list(EVALS),
    next_launch_after_previous_read_ps=GUARD_PS,previous_release_after_read_ps=2,
    first_launch_ps=78,primary_readout_ps=565,clock_off_ps=568,changed_pulse_rows=13,
    physical_changes=True,local_driver_bit=2,local_driver_scale=2,
    local_driver_instances=10,reference_tg_scale=1,first_qbuffer_scale=1)])


def case_record():
    common.need(common.read(PLAN)==PLAN_RECORD and common.read(AUTHORIZATION)==AUTH_RECORD,'Frozen plan/authorization differs')
    return dict(parent.case_record(),case_id=CASE_ID,schedule_unchanged=False)


def timing_schedule():
    launch=78.;schedule={}
    for bit,wait,evaluate in zip(native.BITS,WAITS,EVALS,strict=True):
        compare=launch+wait;read=compare+evaluate
        schedule[bit]=(launch,compare,read,read+2)
        launch=read+GUARD_PS
    common.need(schedule[0]==(498.,504.,552.,554.),'Wrong frozen final-bit budget')
    return schedule


def physical_patch(source):
    """Double complete existing CDF cards only in three dedicated bit2 cells."""
    original=source.decode('ascii').splitlines()
    common.need(not any(row.startswith('subckt '+name+' ') or row=='ends '+name for name in LOCAL_CELLS.values() for row in original),
                'Local bit2 cells must not already exist')
    blocks={};active=None
    for row in original:
        if row.startswith('subckt '):
            active=row.split()[1]
            if active in LOCAL_CELLS:
                common.need(active not in blocks,'Duplicate original cell')
                blocks[active]=[row]
        elif row.startswith('ends '):
            if active in LOCAL_CELLS:
                common.need(row=='ends '+active,'Original cell end differs')
                blocks[active].append(row)
            active=None
        elif active in LOCAL_CELLS:blocks[active].append(row)
    common.need(set(blocks)==set(LOCAL_CELLS),'Original driver cell missing')
    expected_devices={'SAR_OAI21_X2':11,'SAR_NOR3_P3':12,'SAR_NDINV2':4}
    additions=[]
    for old,new in LOCAL_CELLS.items():
        rows=blocks[old]
        common.need(len(rows)-2==expected_devices[old] and all(row.startswith('M') for row in rows[1:-1]),'Unexpected original CDF body')
        additions.append(rows[0].replace('subckt '+old+' ','subckt '+new+' ',1))
        for row in rows[1:-1]:
            name,tail=row.split(' ',1)
            additions.extend(f'{name}_B2R{index} {tail}' for index in range(2))
        additions.append('ends '+new)
    counts=dict(oai=0,nor=0,decoder_inv=0,qbuffer_second=0);seen=set();output=[];inserted=0
    for row in original:
        label=row.split()[0] if row else ''
        if label in TARGETS:
            old,new,pins,kind=TARGETS[label]
            common.need(label not in seen and row==f'{label} ({" ".join(pins)}) {old}','Missing/duplicate/wrong bit2 instance ports or cell: '+label)
            row=f'{label} ({" ".join(pins)}) {new}';seen.add(label);counts[kind]+=1
        output.append(row)
        if row=='ends SAR_NDINV2':output.extend(additions);inserted+=1
    common.need(seen==set(TARGETS) and counts==dict(oai=2,nor=2,decoder_inv=4,qbuffer_second=2) and inserted==1,'Wrong bounded bit2 delta')
    return ('\n'.join(output)+'\n').encode('ascii'),counts


def build(case):
    common.need(case==case_record(),'Only the frozen case20 local-drive case is supported')
    source,old=parent.build(parent.case_record())
    common.need(old['portable_sha256']==PARENT_DECK_SHA and hashlib.sha256(source).hexdigest()==PARENT_DECK_SHA,'Wrong measured case19 parent')
    schedule=timing_schedule();prior=parent.timing_schedule();replacements={}
    for bit in native.BITS:
        launch,compare,read,release=schedule[bit]
        old_launch,old_compare,old_read,old_release=prior[bit]
        for original,updated in ((native.pulse(f'trial{bit}',old_launch,old_release),native.pulse(f'trial{bit}',launch,release)),
                                 (native.pulse(f'clk{bit}',old_compare,568),native.pulse(f'clk{bit}',compare,568))):
            if original!=updated:replacements[original]=updated
    patched,physical_counts=physical_patch(source)
    rows=patched.decode('ascii').splitlines()
    common.need(len(replacements)==13 and all(rows.count(line)==1 for line in replacements),'Expected exactly13 original pulse rows')
    rows=[replacements.get(line,line) for line in rows]
    wave=copy.deepcopy(old['wave'])
    for cv in wave['conversions']:
        origin=cv['index']*wave['period_s']
        for trial in cv['trials']:
            launch,compare,read,release=schedule[trial['bit']]
            trial.update(launch_s=origin+native.timing(launch),pre_s=origin+native.timing(compare-.5),
                compare_s=origin+native.timing(compare),read_s=origin+native.timing(read),trial_release_s=origin+native.timing(release))
    bench=('\n'.join(rows)+'\n').encode('ascii');digest=hashlib.sha256(bench).hexdigest()
    return bench,dict(case=case,wave=wave,portable_sha256=digest,parent_job='761674',
        parent_manifest_sha256=PARENT_MANIFEST_SHA,parent_deck_sha256=PARENT_DECK_SHA,
        parent_summary_sha256=PARENT_SUMMARY_SHA,schedule_ps={str(bit):list(times) for bit,times in schedule.items()},
        primary_readout_ps=565,diagnostic_readouts_ps=[563,554,557],clock_off_ps=568,
        changed_pulse_rows=13,next_launch_midpoint_guard_ps=GUARD_PS,
        finite_trial_edge_starts_at_previous_read=True,physical_changes=True,
        authorization=AUTH_RECORD,authorization_sha256=common.sha(AUTHORIZATION),
        circuit_change=dict(bit=2,scale=2,instance_counts=physical_counts,new_cells=list(LOCAL_CELLS.values()),
            original_global_cells_unchanged=True,tg_unchanged=True,all14_first_qbuffer_inv1_unchanged=True))


def verify():
    names={'sar7_b2_local_drive.py','sar7_b2_local_drive.sbatch','test_sar7_b2_local_drive.py','PLAN.json','AUTHORIZATION.json','HANDOFF_zh_TW.md'}
    entries=[line.split('  ',1) for line in MANIFEST.read_text(encoding='ascii').splitlines()]
    common.need(len(entries)==len(names) and {n for h,n in entries}==names,'Unexpected b2_local_drive inventory')
    for digest,name in entries:
        path=ROOT/name
        common.need(path.resolve().parent==ROOT and common.sha(path)==digest and b'\r' not in path.read_bytes(),'Package differs or is not LF: '+name)
    common.need(b'\r' not in MANIFEST.read_bytes(),'Manifest must use LF')
    _,old=parent.verify()
    common.need(common.sha(parent.MANIFEST)==PARENT_MANIFEST_SHA and old['portable_sha256']==PARENT_DECK_SHA,'Nested frozen parent differs')
    case=case_record();return case,build(case)[1]


def approval_record(root,meta,approved):
    return dict(approved=approved,platform='Olympus',campaign=SCHEMA,case_ids=[CASE_ID],
        authorized_run_root=str(root),design_source_sha256=common.sha(MANIFEST),
        deck_sha256_by_case={CASE_ID:meta['portable_sha256']})


SUMMARY_PARENT=parent.parent
Q_PARENT=SUMMARY_PARENT.parent


def _summary_globals():
    # Keep the original function's parent=case18, while rebinding BOTH nested functions to case20.
    context=dict(parent.summarize.__globals__)
    context.update(CASE_ID=CASE_ID,SCHEMA=SCHEMA,MANIFEST=MANIFEST,PARENT_MANIFEST_SHA=PARENT_MANIFEST_SHA,
        PARENT_DECK_SHA=PARENT_DECK_SHA,PARENT_SUMMARY_SHA=PARENT_SUMMARY_SHA,
        AUTHORIZATION=AUTHORIZATION,AUTH_RECORD=AUTH_RECORD)
    return context


def child_summary_function(q_summary):
    return FunctionType(parent.child_summary_function.__code__,_summary_globals())(q_summary)


def summarize(report,root,case,meta):
    context=_summary_globals()
    context['child_summary_function']=FunctionType(parent.child_summary_function.__code__,context)
    result=FunctionType(parent.summarize.__code__,context)(report,root,case,meta)
    result.update(stage='physical_bit2_local_drive2_tt_12_centers',circuit_change=meta['circuit_change'],
        mechanism_limits='Bit2-only decoder drive and qbuffer load may speed acceptedZ but delay qdecode and restore an O-bubble; no2x speed or pass guarantee')
    return result


def check_stage_deadline(now):
    common.need(STARTS<=now<EXPIRES,'New stage must fall within renewed05:37–13:37UTC authorization')


def validate_submission(text,jobid,now):
    common.need(re.fullmatch(r'\d+',jobid or '') is not None,'SLURM_JOB_ID must contain digits')
    ids=re.findall(r'(?:^|\s)JobId=(\S+)',text);times=re.findall(r'(?:^|\s)SubmitTime=(\S+)',text)
    common.need(ids==[jobid] and len(times)==1 and re.fullmatch(r'\d+',times[0]) is not None,'Ambiguous Slurm submission receipt')
    submitted=datetime.fromtimestamp(int(times[0]),timezone.utc)
    common.need(STARTS<=submitted<EXPIRES and submitted<=now,'Job was not submitted during renewed authorization')
    return dict(slurm_job_id=jobid,submit_time_utc=submitted.isoformat())


def query_preexpiry_slurm_submission(now):
    jobid=os.environ.get('SLURM_JOB_ID','')
    common.need(re.fullmatch(r'\d+',jobid) is not None,'Need actual Slurm job for postexpiry run')
    env=dict(os.environ,SLURM_TIME_FORMAT='%s',TZ='UTC',LC_ALL='C')
    result=subprocess.run(['scontrol','--oneliner','show','job',jobid],env=env,timeout=15,check=True,capture_output=True,text=True)
    return validate_submission(result.stdout,jobid,now)


def check_run_submission(now):
    common.need(now>=STARTS,'Renewed authorization has not started')
    return query_preexpiry_slurm_submission(now) if now>=EXPIRES else None


def existing_stage(root,case,model_root):
    directory=root/CASE_ID
    common.need(directory.is_dir() and directory==directory.resolve(strict=True),'Run requires the existing real staged case')
    for name in ('bench.scs','case.json'):common.owned_file(directory,directory/name)
    source,meta=build(case);proof=base.original.model_preflight.verify_private_kit(model_root,'tt')
    token=base.review.gm_center64.BASE.MODEL_TOKEN.encode('ascii');model=proof['model_root'].encode('utf-8')
    bench=source.replace(token,model)
    common.need(source.count(token)==1 and bench.replace(model,token)==source,'Nonreversible model root substitution')
    record=dict(meta,model_preflight=proof,bench_sha256=hashlib.sha256(bench).hexdigest())
    common.need((directory/'bench.scs').read_bytes()==bench and common.read(directory/'case.json')==record,'Existing stage differs')
    return directory


def stage_for_run(root,case,model_root,now):
    check_run_submission(now)
    return existing_stage(root,case,model_root)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('verify','approval-template','stage','run','collect-only'))
    parser.add_argument('--root',type=Path);parser.add_argument('--approval',type=Path);parser.add_argument('--model-root',type=Path)
    args=parser.parse_args();case,meta=verify()
    if args.mode=='verify':print(CASE_ID,meta['portable_sha256']);return
    common.need(args.root is not None and args.approval is not None,'Supply isolated root and approval')
    root=common.checked_root(args.root);approval=args.approval.absolute()
    common.need(root.name.startswith('pam4_sar7_b2_local_drive_pilot_') and approval.parent==root,'Use a new b2_local_drive root and its own approval')
    if args.mode=='approval-template':common.write_new(approval,approval_record(root,meta,False));return
    common.need(common.read(approval)==approval_record(root,meta,True),'Approval must bind exact root,manifest and deck')
    base.build,base.PLAN,base.MANIFEST,base.SCHEMA=build,PLAN,MANIFEST,SCHEMA
    base.TIMEOUT_S=540
    if args.mode in ('stage','run'):
        common.need(args.model_root is not None,'Use existing verified private model root')
        if args.mode=='stage':check_stage_deadline(datetime.now(timezone.utc));print(base.stage(root,case,args.model_root));return
        stage_for_run(root,case,args.model_root,datetime.now(timezone.utc))
        saved=base.stage
        try:base.stage=existing_stage;report=base.run(root,case,args.model_root,approval)
        finally:base.stage=saved
    else:report=base.collect(root,case)
    result=summarize(report,root,case,meta);target=root/'sar7_b2_local_drive_summary.json'
    if target.exists():common.need(common.read(target)==result,'Existing summary differs')
    else:common.write_new(target,result)
    print(json.dumps(dict(summary=str(target),sha256=common.sha(target),screen_pass=result['readout_565']['screen_pass'])))


if __name__=='__main__':main()
