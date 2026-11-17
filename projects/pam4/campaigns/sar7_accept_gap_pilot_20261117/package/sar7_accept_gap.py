"""One accepted-reference timing-gap test, immutable case20 physical circuit."""

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
SCHEMA='pam4_sar7_accept_gap_pilot_v1'
CASE_ID='sar7_21_tt_175gs_accept_gap'
PARENT_MANIFEST_SHA='2887bf0705fb20245f65d8745abdd01624debb53b2aa8bdf7c7c5564adad84e1'
PARENT_DECK_SHA='c587a30cf264dc2b815bd9f23b057ce15edeed9b59591edcfe2370a403f3bfbf'
PARENT_SUMMARY_SHA='83d41a50aeea4285dbecf922deb94f949c2a4265cc2a8ce3d6acda4d7b7682a3'
PARENT=Path(os.environ.get('PAM4_SAR7_B2_LOCAL_DRIVE_PACKAGE',ROOT.parent/'PAM4_SAR7_B2_LOCAL_DRIVE_PILOT_20261117')).resolve()
if hashlib.sha256((PARENT/'SHA256SUMS.txt').read_bytes()).hexdigest()!=PARENT_MANIFEST_SHA:
    raise ValueError('Expected exact measured case20 package')
sys.path.insert(0,str(PARENT))
import sar7_b2_local_drive as parent

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
WAITS=(30,45,25,26,31,13,6)
EVALS=(35,44,40,40,44,44,48)
GUARD_PS=.5
PLAN_RECORD=dict(schema=SCHEMA,authorization=AUTH_RECORD,cases=[dict(case_id=CASE_ID,
    parent_job='761688',parent_manifest_sha256=PARENT_MANIFEST_SHA,parent_deck_sha256=PARENT_DECK_SHA,
    source_summary_sha256=PARENT_SUMMARY_SHA,waits_ps=list(WAITS),evals_ps=list(EVALS),
    next_launch_after_previous_read_ps=GUARD_PS,previous_release_after_read_ps=2,
    first_launch_ps=78,primary_readout_ps=565,clock_off_ps=568,changed_pulse_rows=10,
    physical_changes=False,stop_branch_after_rejection=True,accepted_gap_ps=11.5)])


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


def build(case):
    common.need(case==case_record(),'Only the frozen case21 accepted-gap case is supported')
    source,old=parent.build(parent.case_record())
    common.need(old['portable_sha256']==PARENT_DECK_SHA and hashlib.sha256(source).hexdigest()==PARENT_DECK_SHA,'Wrong measured case20 parent')
    schedule=timing_schedule();prior=parent.timing_schedule();replacements={}
    for bit in native.BITS:
        launch,compare,read,release=schedule[bit]
        old_launch,old_compare,old_read,old_release=prior[bit]
        for original,updated in ((native.pulse(f'trial{bit}',old_launch,old_release),native.pulse(f'trial{bit}',launch,release)),
                                 (native.pulse(f'clk{bit}',old_compare,568),native.pulse(f'clk{bit}',compare,568))):
            if original!=updated:replacements[original]=updated
    rows=source.decode('ascii').splitlines()
    common.need(len(replacements)==10 and all(rows.count(line)==1 for line in replacements),'Expected exactly10 original pulse rows')
    rows=[replacements.get(line,line) for line in rows]
    wave=copy.deepcopy(old['wave'])
    for cv in wave['conversions']:
        origin=cv['index']*wave['period_s']
        for trial in cv['trials']:
            launch,compare,read,release=schedule[trial['bit']]
            trial.update(launch_s=origin+native.timing(launch),pre_s=origin+native.timing(compare-.5),
                compare_s=origin+native.timing(compare),read_s=origin+native.timing(read),trial_release_s=origin+native.timing(release))
    bench=('\n'.join(rows)+'\n').encode('ascii');digest=hashlib.sha256(bench).hexdigest()
    return bench,dict(case=case,wave=wave,portable_sha256=digest,parent_job='761688',
        parent_manifest_sha256=PARENT_MANIFEST_SHA,parent_deck_sha256=PARENT_DECK_SHA,
        parent_summary_sha256=PARENT_SUMMARY_SHA,schedule_ps={str(bit):list(times) for bit,times in schedule.items()},
        primary_readout_ps=565,diagnostic_readouts_ps=[563,554,557],clock_off_ps=568,
        changed_pulse_rows=10,next_launch_midpoint_guard_ps=GUARD_PS,
        finite_trial_edge_starts_at_previous_read=True,physical_changes=False,
        authorization=AUTH_RECORD,authorization_sha256=common.sha(AUTHORIZATION),
        circuit_change=copy.deepcopy(old['circuit_change']),
        inherited_circuit_change=copy.deepcopy(old['circuit_change']),
        relative_to_parent=dict(physical_changes=False,changed_pulse_rows=10,parent_job='761688'),
        stop_branch_after_rejection=True)



def verify():
    names={'sar7_accept_gap.py','sar7_accept_gap.sbatch','test_sar7_accept_gap.py','PLAN.json','AUTHORIZATION.json','HANDOFF_zh_TW.md'}
    entries=[line.split('  ',1) for line in MANIFEST.read_text(encoding='ascii').splitlines()]
    common.need(len(entries)==len(names) and {n for h,n in entries}==names,'Unexpected accept_gap inventory')
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


SUMMARY_ENGINE=parent.parent
SUMMARY_PARENT=SUMMARY_ENGINE.parent
Q_PARENT=SUMMARY_PARENT.parent


def _summary_globals():
    # Direct case19 engine: its original parent remains case18, not the case20 wrapper.
    context=dict(SUMMARY_ENGINE.summarize.__globals__)
    context.update(CASE_ID=CASE_ID,SCHEMA=SCHEMA,MANIFEST=MANIFEST,PARENT_MANIFEST_SHA=PARENT_MANIFEST_SHA,
        PARENT_DECK_SHA=PARENT_DECK_SHA,PARENT_SUMMARY_SHA=PARENT_SUMMARY_SHA,
        AUTHORIZATION=AUTHORIZATION,AUTH_RECORD=AUTH_RECORD)
    return context


def child_summary_function(q_summary):
    return FunctionType(SUMMARY_ENGINE.child_summary_function.__code__,_summary_globals())(q_summary)


def acceptance_diagnostics(result,wave):
    accepted=[];msb=[]
    for row in result['timing']:
        if row['bit'] not in (2,6):continue
        q=row['q_buffer'];ref=q['reference_path'];wanted=ref['wanted_accepted_command']
        release=ref['phase_observations']['release']['at_s'];runs=ref['postrelease_command_runs']
        final=runs[-1] if wanted is not None and runs and runs[-1]['command']==wanted else None
        arrival=None if final is None else final['start_s']
        if row['bit']==2:
            following=ref['following_compare_s']
            accepted.append(dict(conversion=row['conversion'],wanted_command=wanted,
                raw_stable_rail_delay_ps=q['raw_stable_rail_delay_ps'],release_s=release,
                trailing_command_confirmed=final is not None,
                final_arrival_after_release_ps=None if arrival is None else (arrival-release)/native.PS,
                margin_before_next_compare_ps=None if arrival is None or following is None else (following-arrival)/native.PS))
        else:
            edges=ref['extended_half_vdd_crossings_ps']['qdecode6p']
            half=next((at for at,direction in edges if direction=='rise' and at>=0),None)
            compare=ref['phase_observations']['compare_plus_0ps']['at_s']
            msb.append(dict(conversion=row['conversion'],wanted_command=wanted,decision=row['decision'],
                sampled_margin_ps=row['sampled_margin_ps'],raw_stable_rail_delay_ps=q['raw_stable_rail_delay_ps'],
                qdecode_p_half_from_compare_ps=half,
                qdecode_p_half_after_release_ps=None if half is None else half-(release-compare)/native.PS,
                accepted_margin_before_next_compare_ps=ref['accepted_command_margin_before_next_compare_ps']))
    z=[row['final_arrival_after_release_ps'] for row in accepted if row['wanted_command']=='Z' and row['trailing_command_confirmed']]
    o=[row for row in msb if row['wanted_command']=='O']
    half=[row['qdecode_p_half_from_compare_ps'] for row in o if row['qdecode_p_half_from_compare_ps'] is not None]
    lag=[row['qdecode_p_half_after_release_ps'] for row in o if row['qdecode_p_half_after_release_ps'] is not None]
    return dict(b2_all_conversions=accepted,b2_Z_command_count=sum(row['wanted_command']=='Z' for row in accepted),
        b2_Z_unconfirmed_count=sum(row['wanted_command']=='Z' and not row['trailing_command_confirmed'] for row in accepted),
        b2_latest_Z_arrival_after_release_ps=max(z) if z else None,
        msb_all_conversions=msb,msb_O_count=len(o),
        msb_O_half_unavailable_count=sum(row['qdecode_p_half_from_compare_ps'] is None for row in o),
        msb_latest_O_qdecode_half_from_compare_ps=max(half) if half else None,
        msb_latest_O_qdecode_half_after_release_ps=max(lag) if lag else None,
        limits='Final trailing rail-command run is observed only through the existing next-read window; half-VDD and rail commands do not prove analog settling or switch conduction')


def summarize(report,root,case,meta):
    context=_summary_globals()
    context['child_summary_function']=FunctionType(SUMMARY_ENGINE.child_summary_function.__code__,context)
    result=FunctionType(SUMMARY_ENGINE.summarize.__code__,context)(report,root,case,meta)
    result.update(stage='physical_accept_gap_tt_12_centers',circuit_change=meta['inherited_circuit_change'],
        relative_to_parent=meta['relative_to_parent'],stop_branch_after_rejection=True,
        acceptance_gap_diagnostic=acceptance_diagnostics(result,meta['wave']),
        mechanism_limits='Earlier b2 release and larger following wait may advance Z but restore O-bubbles; source raw-rail headroom is not decoder readiness or analog-settling proof')
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
    common.need(root.name.startswith('pam4_sar7_accept_gap_pilot_') and approval.parent==root,'Use a new accept_gap root and its own approval')
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
    result=summarize(report,root,case,meta);target=root/'sar7_accept_gap_summary.json'
    if target.exists():common.need(common.read(target)==result,'Existing summary differs')
    else:common.write_new(target,result)
    print(json.dumps(dict(summary=str(target),sha256=common.sha(target),screen_pass=result['readout_565']['screen_pass'])))


if __name__=='__main__':main()
