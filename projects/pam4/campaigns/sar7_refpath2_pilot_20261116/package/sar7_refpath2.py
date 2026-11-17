"""One coordinated physical reference-path scale2 pilot, clocks and scoring fixed."""

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
from types import FunctionType

ROOT=Path(__file__).resolve().parent
MANIFEST=ROOT/'SHA256SUMS.txt'
PLAN=ROOT/'PLAN.json'
AUTHORIZATION=ROOT/'AUTHORIZATION.json'
SCHEMA='pam4_sar7_refpath2_pilot_v1'
CASE_ID='sar7_17_tt_175gs_refpath2'
PARENT_MANIFEST_SHA='928590bc897d6755e208f2729f8c0c9882e15a42262032edddf9b491fa0188ca'
PARENT_DECK_SHA='509bbedfdc2be956eafade7021b968eeb60d29f0fcb654d2c0037a22b5da813a'
PARENT_SUMMARY_SHA='8ab3c03c13658704b2c4a20be6bd453e864f74c4e7e1a6169434a275bbe2eb93'
PARENT=Path(os.environ.get('PAM4_SAR7_QBUFFER_PACKAGE',ROOT.parent/'PAM4_SAR7_QBUFFER_PILOT_20261116')).resolve()
if hashlib.sha256((PARENT/'SHA256SUMS.txt').read_bytes()).hexdigest()!=PARENT_MANIFEST_SHA:
    raise ValueError('Expected exact measured qbuffer package')
sys.path.insert(0,str(PARENT))
import sar7_qbuffer as parent

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
PLAN_RECORD=dict(schema=SCHEMA,authorization=AUTH_RECORD,cases=[dict(case_id=CASE_ID,
    parent_job='761549',parent_manifest_sha256=PARENT_MANIFEST_SHA,parent_deck_sha256=PARENT_DECK_SHA,
    source_summary_sha256=PARENT_SUMMARY_SHA,reference_path_scale=2,timing_changes=False,
    reference_tg_instances=56,decoder_instances=56,qbuffer_second_instances=14,
    first_qbuffer_cell='SAR_INV',reference_cell='SAR_REFTG2',decoder_output_cell='SAR_NDINV4')])


def case_record():
    common.need(common.read(PLAN)==PLAN_RECORD and common.read(AUTHORIZATION)==AUTH_RECORD,'Frozen plan/authorization differs')
    return dict(parent.case_record(),case_id=CASE_ID)


def local_subcircuits():
    _,(ntg,ptg,_,_)=native.read_cdf(base.review.R5/'quiet.scs')
    yield 'subckt SAR_REFTG2 (a b en enb vdd)'
    for i in range(2):
        yield native.mos(ntg,f'MTN_R{i}',('a','en','b','0'))
        yield native.mos(ptg,f'MTP_R{i}',('a','enb','b','vdd'))
    yield 'ends SAR_REFTG2'
    definitions=list(parent.parent.decoder_subcircuits())
    names={'SAR_OAI21_X2':'SAR_OAI21_RP2','SAR_NOR3_P3':'SAR_NOR3_RP2','SAR_NDINV2':'SAR_NDINV4'}
    for line in definitions:
        if line.startswith(('subckt ','ends ')):
            for old,new in names.items():line=line.replace(old,new)
            yield line
        else:
            name,tail=line.split(' ',1)
            for i in range(2):yield f'{name}_S{i} {tail}'


def build(case):
    common.need(case==case_record(),'Only the frozen full-path2 case is supported')
    source,old=parent.build(parent.case_record())
    common.need(old['portable_sha256']==PARENT_DECK_SHA,'Wrong measured parent')
    rows=[];counts=dict(reference=0,oai=0,nor=0,decoder_inv=0,qbuffer_second=0)
    for line in source.decode('ascii').splitlines():
        if re.match(r'^(XRef\w+|XNDLOAD\w+) ',line):
            common.need(line.endswith(' SAR_TG'),'Unexpected reference leaf')
            line=line[:-len('SAR_TG')]+'SAR_REFTG2';counts['reference']+=1
        elif re.match(r'^XNDO[pn][0-6] ',line):
            common.need(line.endswith(' SAR_OAI21_X2'),'Wrong OAI')
            line=line[:-len('SAR_OAI21_X2')]+'SAR_OAI21_RP2';counts['oai']+=1
        elif re.match(r'^XNDZ[pn][0-6] ',line):
            common.need(line.endswith(' SAR_NOR3_P3'),'Wrong NOR')
            line=line[:-len('SAR_NOR3_P3')]+'SAR_NOR3_RP2';counts['nor']+=1
        elif re.match(r'^XNDI[OZ][pn][0-6] ',line):
            common.need(line.endswith(' SAR_NDINV2'),'Wrong decoder inverter')
            line=line[:-len('SAR_NDINV2')]+'SAR_NDINV4';counts['decoder_inv']+=1
        elif re.match(r'^XQOUT[0-6][pn] ',line):
            common.need(line.endswith(' SAR_NDINV2'),'Wrong second qbuffer')
            line=line[:-len('SAR_NDINV2')]+'SAR_NDINV4';counts['qbuffer_second']+=1
        rows.append(line)
        if line=='ends SAR_NDINV2':rows.extend(local_subcircuits())
    common.need(counts==dict(reference=56,oai=14,nor=14,decoder_inv=28,qbuffer_second=14),'Wrong bounded instance delta')
    bench=('\n'.join(rows)+'\n').encode('ascii');digest=hashlib.sha256(bench).hexdigest()
    return bench,dict(case=case,wave=copy.deepcopy(old['wave']),portable_sha256=digest,
        parent_job='761549',parent_manifest_sha256=PARENT_MANIFEST_SHA,parent_deck_sha256=PARENT_DECK_SHA,
        parent_summary_sha256=PARENT_SUMMARY_SHA,schedule_ps=copy.deepcopy(old['schedule_ps']),
        primary_readout_ps=565,diagnostic_readouts_ps=[563,554,557],clock_off_ps=568,
        reference_path_scale=2,changed_instances=counts,authorization=AUTH_RECORD,
        authorization_sha256=common.sha(AUTHORIZATION))


def verify():
    names={'sar7_refpath2.py','sar7_refpath2.sbatch','test_sar7_refpath2.py','PLAN.json','AUTHORIZATION.json','HANDOFF_zh_TW.md'}
    entries=[line.split('  ',1) for line in MANIFEST.read_text(encoding='ascii').splitlines()]
    common.need(len(entries)==len(names) and {n for h,n in entries}==names,'Unexpected refpath2 inventory')
    for digest,name in entries:
        path=ROOT/name
        common.need(path.resolve().parent==ROOT and common.sha(path)==digest,'Package differs: '+name)
    _,old=parent.verify()
    common.need(common.sha(parent.MANIFEST)==PARENT_MANIFEST_SHA and old['portable_sha256']==PARENT_DECK_SHA,'Nested frozen parent differs')
    case=case_record();return case,build(case)[1]


def approval_record(root,meta,approved):
    return dict(approved=approved,platform='Olympus',campaign=SCHEMA,case_ids=[CASE_ID],
        authorized_run_root=str(root),design_source_sha256=common.sha(MANIFEST),
        deck_sha256_by_case={CASE_ID:meta['portable_sha256']})


def rail_command(gates,vdd):
    co,cbo,cz,cbz=gates
    def on(a,b):return a>=.8*vdd and b<=.2*vdd
    def off(a,b):return a<=.2*vdd and b>=.8*vdd
    if on(co,cbo) and off(cz,cbz):return 'O'
    if on(cz,cbz) and off(co,cbo):return 'Z'
    if on(co,cbo) and on(cz,cbz):return 'both'
    if off(co,cbo) and off(cz,cbz):return 'neither'
    return 'transition'


def q_buffer_detail(values,time,conversion,trial,wave):
    detail=parent.q_buffer_detail(values,time,conversion,trial,wave)
    bit=trial['bit'];vdd=wave['vdd_V'];compare=trial['compare_s'];release=trial['trial_release_s']
    following=next((t for t in conversion['trials'] if t['bit']==bit-1),None)
    end=min(time[-1],max(following['compare_s']+native.timing(30),following['read_s']) if following else conversion['end_s'])
    gates=[f'c{bit}o',f'cb{bit}o',f'c{bit}z',f'cb{bit}z']
    def at(node,instant):return score.interpolate(time,values[node],instant)
    def observe(instant):
        gate=[at(node,instant) for node in gates]
        held,_=score.differential(time,values,wave['dac_pair'],instant)
        sense,_=score.differential(time,values,('sensep','sensen'),instant)
        return dict(at_s=instant,ps_from_conversion=(instant-conversion['index']*wave['period_s'])/native.PS,
            ps_from_compare=(instant-compare)/native.PS,gates_V=gate,command=rail_command(gate,vdd),
            bottom_V=[at(f'b{bit}{side}',instant) for side in 'pn'],held_lsb=held/wave['lsb_V'],sense_lsb=sense/wave['lsb_V'],
            raw_V=[at(f'q{bit}{side}',instant) for side in 'pn'],mid_V=[at(f'qmid{bit}{side}',instant) for side in 'pn'],
            decode_V=[at(f'qdecode{bit}{side}',instant) for side in 'pn'],xy_V=[at(f'XCMP{bit}.{side}',instant) for side in 'xy'])
    points=[('launch',trial['launch_s']),('read',trial['read_s']),('release',release)]
    points.extend((f'compare_plus_{offset}ps',compare+native.timing(offset)) for offset in (0,5,10,15,20,30))
    if following:
        points.extend((('victim_launch',following['launch_s']),('victim_compare',following['compare_s']),('victim_read',following['read_s'])))
        points.extend((f'victim_compare_plus_{offset}ps',following['compare_s']+native.timing(offset)) for offset in (5,10,15,20,30))
    observations={label:observe(instant) for label,instant in points if time[0]<=instant<=end}
    reg=score.classify(at(f'bit{bit}',conversion['end_s']),at(f'bit{bit}b',conversion['end_s']),vdd)
    wanted='O' if reg==1 else 'Z' if reg==0 else None
    victim=following['compare_s'] if following else None
    samples=[(instant,rail_command([values[g][i] for g in gates],vdd)) for i in range(bisect_left(time,release),bisect_right(time,end)) for instant in [time[i]]]
    before_compare=[record for record in samples if victim is None or record[0]<=victim]
    stable=None
    if before_compare and wanted is not None and before_compare[-1][1]==wanted:
        index=len(before_compare)-1
        while index>0 and before_compare[index-1][1]==wanted:index-=1
        stable=before_compare[index][0]
    runs=[]
    for instant,state in samples:
        if not runs or runs[-1]['command']!=state:runs.append(dict(command=state,start_s=instant,end_s=instant,samples=1))
        else:runs[-1].update(end_s=instant,samples=runs[-1]['samples']+1)
    nodes=[f'{prefix}{bit}{side}' for prefix in ('q','qmid','qdecode') for side in 'pn']+gates
    detail['reference_path']=dict(extended_window_end_s=end,following_compare_s=victim,following_read_s=None if not following else following['read_s'],
        registered_bit_565=reg,wanted_accepted_command=wanted,postrelease_command_runs=runs,
        stable_accepted_command_start_s=stable,accepted_command_margin_before_next_compare_ps=None if stable is None or victim is None else (victim-stable)/native.PS,
        phase_observations=observations,extended_half_vdd_crossings_ps={node:parent.crossings(time,values[node],trial['launch_s']-native.timing(3),end,vdd/2,compare) for node in nodes},
        limits='Gate voltages are command proxies, not conduction; rail/midpoint crossing is not LSB settling; final-class diagnostic never replaces original read gate')
    return detail


def summarize(report,root,case,meta):
    context=dict(parent.summarize.__globals__)
    context.update(CASE_ID=CASE_ID,SCHEMA=SCHEMA,MANIFEST=MANIFEST,PARENT_MANIFEST_SHA=PARENT_MANIFEST_SHA,
        PARENT_DECK_SHA=PARENT_DECK_SHA,PARENT_SUMMARY_SHA=PARENT_SUMMARY_SHA,q_buffer_detail=q_buffer_detail)
    result=FunctionType(parent.summarize.__code__,context)(report,root,case,meta)
    result.update(stage='physical_reference_path2_tt_12_centers',authorization=AUTH_RECORD,
        authorization_sha256=common.sha(AUTHORIZATION),reference_path_scale=2,
        mechanism_limits='Coordinated scaling is not a guaranteed2x speedup: first qbuffer sees more load; TG diffusion and feedthrough also increase')
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
    common.need(root.name.startswith('pam4_sar7_refpath2_pilot_') and approval.parent==root,'Use a new refpath2 root and its own approval')
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
    result=summarize(report,root,case,meta);target=root/'sar7_refpath2_summary.json'
    if target.exists():common.need(common.read(target)==result,'Existing summary differs')
    else:common.write_new(target,result)
    print(json.dumps(dict(summary=str(target),sha256=common.sha(target),screen_pass=result['readout_565']['screen_pass'])))


if __name__=='__main__':main()
