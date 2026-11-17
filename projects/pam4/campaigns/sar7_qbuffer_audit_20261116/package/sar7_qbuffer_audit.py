"""Read two completed SAR7 transients once each; never stage, collect or simulate."""

import argparse
from bisect import bisect_left,bisect_right
from functools import partial
import hashlib
import json
import math
import os
from pathlib import Path
import sys


ROOT=Path(__file__).resolve().parent
MANIFEST=ROOT/'SHA256SUMS.txt'
PLAN=ROOT/'PLAN.json'
SCHEMA='pam4_sar7_qbuffer_retained_audit_v1'
PARENT=Path(os.environ.get('PAM4_SAR7_QBUFFER_PACKAGE',ROOT.parent/'PAM4_SAR7_QBUFFER_PILOT_20261116')).resolve()
QMANIFEST='928590bc897d6755e208f2729f8c0c9882e15a42262032edddf9b491fa0188ca'
if hashlib.sha256((PARENT/'SHA256SUMS.txt').read_bytes()).hexdigest()!=QMANIFEST:
    raise ValueError('Wrong frozen qbuffer package')
sys.path.insert(0,str(PARENT))
import sar7_qbuffer as qbuffer

strong=qbuffer.parent
base,common,score,native=qbuffer.base,qbuffer.common,qbuffer.score,qbuffer.native
TARGETS=((0,6),(7,4),(7,3),(7,2),(8,3),(8,2),(8,1))
PINS={
 'qbuffer':dict(job='761549',root='pam4_sar7_qbuffer_pilot_20261116.GscWI6',
   summary='8ab3c03c13658704b2c4a20be6bd453e864f74c4e7e1a6169434a275bbe2eb93',
   measurements='569c78e621d19bd6a9ab066b8fd87e0b1382c13fb872abd928f55964d1e4308a',
   tran='1abec792de375805df2b212a6ef8681855acc619d3202d09384180e067a3568a',
   manifest=QMANIFEST,portable='509bbedfdc2be956eafade7021b968eeb60d29f0fcb654d2c0037a22b5da813a'),
 'strong':dict(job='761524',root='pam4_sar7_strong_decode_pilot_20261116.qUaOJ0',
   summary='73dafa11235da6c63048536e447cd3bda60dba23155b03a399d86c725a84ac03',
   measurements='a8b0c965f0a4a7e9ccdf11523aa7f0b2fb9142e24a3349fc0b6cb343c3813a18',
   tran='fc21cd54451e4c2798e08366c859db125e898eaf0a4f5584c280450ec4fcb318',
   manifest='43b93d73f5f5e08fc350a6b9a12ae6c54ec3c5eac280190be93a38b3fe4b8bd8',
   portable='31d7e4e66c8f33a6432d640050285736454e63fa8cc171b04f13b39875180da8')}


def verify_receipt(content,expected,label):
    common.need(hashlib.sha256(content).hexdigest()==expected,'Source receipt differs: '+label)
    return json.loads(content.decode('utf-8-sig'))


def read_checked(path,expected):
    owned,_=common.owned_file(path.parent,path)
    return verify_receipt(owned.read_bytes(),expected,path.name)


def unchanged(before,after):
    common.need(before==after,'Source evidence changed during read-only audit')


def separate_paths(sources,output):
    for source in sources:
        common.need(not output.is_relative_to(source) and not source.is_relative_to(output),
                    'Output must be separate from every original source tree')


def window_for(conversion,bit,stop):
    trials=conversion['trials'];index=next(i for i,t in enumerate(trials) if t['bit']==bit)
    trial=trials[index];previous=trials[index-1] if index else None
    following=trials[index+1] if index+1<len(trials) else None
    lo=(previous['trial_release_s'] if previous else trial['launch_s'])-native.timing(5)
    hi=max(following['compare_s']+native.timing(30),following['read_s']) if following else trial['read_s']+native.timing(30)
    return dict(lo=max(0.,lo),hi=min(stop,hi),previous=previous,current=trial,following=following)


def edges(time,trace,lo,hi,threshold,conversion_origin,compare):
    output=[]
    for i in range(max(1,bisect_left(time,lo)),min(len(time),bisect_right(time,hi)+1)):
        a,b=trace[i-1],trace[i]
        if a<threshold<=b or b<=threshold<a:
            at=time[i-1]+(time[i]-time[i-1])*(threshold-a)/(b-a)
            if lo<=at<=hi:
                output.append(dict(at_s=at,ps_from_conversion=(at-conversion_origin)/native.PS,
                                   ps_from_current_compare=(at-compare)/native.PS,direction='rise' if b>a else 'fall'))
    return output


def sign(value):return 1 if value>0 else -1 if value<0 else 0


def command(co,cbo,cz,cbz,vdd):
    def on(c,cb):return c>=.8*vdd and cb<=.2*vdd
    def off(c,cb):return c<=.2*vdd and cb>=.8*vdd
    if on(co,cbo) and off(cz,cbz):return 'O_rail_command'
    if on(cz,cbz) and off(co,cbo):return 'Z_rail_command'
    if on(co,cbo) and on(cz,cbz):return 'both_rail_commands'
    if off(co,cbo) and off(cz,cbz):return 'neither_rail_command'
    return 'transition_or_noncomplementary'


def runs(times,states):
    result=[]
    for at,state in zip(times,states,strict=True):
        if not result or result[-1]['state']!=state:
            result.append(dict(state=state,start_s=at,end_s=at,samples=1))
        else:result[-1].update(end_s=at,samples=result[-1]['samples']+1)
    for record in result:record['sample_span_ps']=(record['end_s']-record['start_s'])/native.PS
    return result


def selected_window(values,wave,conversion,bit,kind,report_row):
    time=values['time'];lsb=wave['lsb_V'];vdd=wave['vdd_V']
    window=window_for(conversion,bit,wave['stop_s']);lo,hi=window['lo'],window['hi']
    trial=window['current'];compare=trial['compare_s'];origin=conversion['index']*wave['period_s']
    contexts=[t for t in (window['previous'],trial,window['following']) if t is not None]
    names={}
    for t in contexts:
        b=t['bit']
        names[str(b)]=dict(raw=[f'q{b}p',f'q{b}n'],register=[f'bit{b}',f'bit{b}b'],
            internal=[f'XCMP{b}.x',f'XCMP{b}.y'],bottom=[f'b{b}p',f'b{b}n'],
            gates=[f'c{b}o',f'cb{b}o',f'c{b}z',f'cb{b}z'],trial=f'trial{b}',clock=f'clk{b}')
        if kind=='qbuffer':names[str(b)].update(mid=[f'qmid{b}p',f'qmid{b}n'],decode=[f'qdecode{b}p',f'qdecode{b}n'])
        else:names[str(b)]['decode']=names[str(b)]['raw']
    def voltage(node,at):return score.interpolate(time,values[node],at)
    def pair(nodes,at):return [voltage(n,at) for n in nodes]
    def observe(at,b):
        n=names[str(b)];held,held_cm=score.differential(time,values,wave['dac_pair'],at)
        sensed,sense_cm=score.differential(time,values,('sensep','sensen'),at)
        raw=pair(n['raw'],at);decoded=pair(n['decode'],at);gate=pair(n['gates'],at)
        internal=pair(n['internal'],at);bottom=pair(n['bottom'],at)
        return dict(at_s=at,ps_from_conversion=(at-origin)/native.PS,ps_from_current_compare=(at-compare)/native.PS,
            held_lsb=held/lsb,held_cm_V=held_cm,sense_lsb=sensed/lsb,sense_cm_V=sense_cm,
            raw_q_V=raw,mid_V=pair(n['mid'],at) if 'mid'in n else None,decode_V=decoded,
            decoder_input_source='noninverting_q_buffer' if kind=='qbuffer' else 'direct_raw_q',
            raw_class=score.classify(*raw,vdd),decode_class=score.classify(*decoded,vdd),
            internal_xy_V=internal,internal_x_minus_y_V=internal[0]-internal[1],register_V=pair(n['register'],at),
            reference_gates_co_cbo_cz_cbz_V=gate,rail_command=command(*gate,vdd),bottom_V=bottom,
            bottom_sum_error_from_0p9_V=sum(bottom)-.9,trial_V=voltage(n['trial'],at),clock_V=voltage(n['clock'],at))
    phase_records=[]
    for t in contexts:
        points=[(f'compare_plus_{offset}ps',t['compare_s']+native.timing(offset)) for offset in (0,5,10,15,20,30)]
        points.extend((('read',t['read_s']),('release',t['trial_release_s'])))
        points.extend((f'release_plus_{offset}ps',t['trial_release_s']+native.timing(offset)) for offset in (1,2,5,10,15,20,30))
        for label,at in points:
            if lo<=at<=hi:phase_records.append(dict(context_bit=t['bit'],phase=label,**observe(at,t['bit'])))
    native_times=time[bisect_left(time,lo):bisect_right(time,hi)]
    compact=[];dense=[]
    decisions={t['bit']:t['decision'] for t in report_row['trial_results']}
    for t in contexts:
        b=t['bit'];n=names[str(b)]
        samples=[observe(at,b) for at in native_times]
        dense.append(dict(context_bit=b,samples=samples))
        channels={node:values[node] for field in ('raw','decode','gates','bottom','internal','register') for node in n[field]}
        if 'mid'in n:channels.update({node:values[node] for node in n['mid']})
        channels.update({n['trial']:values[n['trial']],n['clock']:values[n['clock']]})
        all_edges={node:edges(time,trace,lo,hi,vdd/2,origin,compare) for node,trace in channels.items()}
        held_trace=[a-b for a,b in zip(values[wave['dac_pair'][0]],values[wave['dac_pair'][1]],strict=True)]
        sense_trace=[a-b for a,b in zip(values['sensep'],values['sensen'],strict=True)]
        all_edges['held_zero']=edges(time,held_trace,lo,hi,0.,origin,compare)
        all_edges['sense_zero']=edges(time,sense_trace,lo,hi,0.,origin,compare)
        release=observe(t['trial_release_s'],b)
        late=observe(hi,b)
        raw_late=late['raw_class'];expected_state='O_rail_command' if raw_late==1 else 'Z_rail_command' if raw_late==0 else None
        post=[record for record in samples if record['at_s']>=t['trial_release_s']]
        compact.append(dict(context_bit=b,original_read_decision=decisions[b],release_raw_class=release['raw_class'],
            eventual_raw_class_at_window_end=raw_late,
            registered_bit_at_formal_565=None if report_row['observed_registered_code'] is None else (report_row['observed_registered_code']>>b)&1,
            late_class_label='Diagnostic only; does not replace original compare-read score or establish causation',
            all_half_vdd_and_zero_edges=all_edges,
            postrelease_command_runs=runs([r['at_s'] for r in post],[r['rail_command'] for r in post]),
            command_for_eventual_raw_bit=expected_state,
            opposite_final_command_samples=sum(r['rail_command'] in ('O_rail_command','Z_rail_command')
                and r['rail_command']!=expected_state for r in post) if expected_state else None,
            held_sign_runs=runs(native_times,[sign(r['held_lsb']) for r in samples]),
            sense_sign_runs=runs(native_times,[sign(r['sense_lsb']) for r in samples]),
            maximum_abs_bottom_sum_error_V=max(abs(r['bottom_sum_error_from_0p9_V']) for r in samples)))
    metadata=dict(conversion=conversion['index'],target_bit=bit,window_start_s=lo,window_end_s=hi,
        origin_s=origin,current_compare_s=compare,current_read_s=trial['read_s'],
        current_read_minus_compare_ps=(trial['read_s']-compare)/native.PS,
        previous_release_s=None if window['previous'] is None else window['previous']['trial_release_s'],
        following_compare_s=None if window['following'] is None else window['following']['compare_s'],
        following_read_s=None if window['following'] is None else window['following']['read_s'])
    return dict(metadata,contexts=compact),dict(metadata,phase_observations=phase_records,dense_native_samples=dense)


def verify():
    common.need(common.read(PLAN)==dict(schema=SCHEMA,sources=PINS,targets=[list(t) for t in TARGETS]),'Audit plan differs')
    files={'sar7_qbuffer_audit.py','sar7_qbuffer_audit.sbatch','test_sar7_qbuffer_audit.py','PLAN.json','HANDOFF_zh_TW.md'}
    entries=[line.split('  ',1) for line in MANIFEST.read_text(encoding='ascii').splitlines()]
    common.need(len(entries)==len(files) and {n for h,n in entries}==files,'Unexpected audit inventory')
    for digest,name in entries:
        path=ROOT/name
        common.need(path.resolve().parent==ROOT and common.sha(path)==digest,'Audit package differs: '+name)
    for kind,module in (('qbuffer',qbuffer),('strong',strong)):
        case,meta=module.verify()
        common.need(common.sha(module.MANIFEST)==PINS[kind]['manifest'] and meta['portable_sha256']==PINS[kind]['portable'],
                    'Original source build differs')
    return True


def audit_source(root,kind):
    module=qbuffer if kind=='qbuffer' else strong;pin=PINS[kind]
    root=root.absolute()
    common.need(root==root.resolve(strict=True) and root.is_dir() and root.name==pin['root'],'Wrong exact completed source root')
    case=module.case_record();directory=root/case['case_id']
    saved=(base.build,base.PLAN,base.MANIFEST,base.SCHEMA)
    try:
        base.build,base.PLAN,base.MANIFEST,base.SCHEMA=module.build,module.PLAN,module.MANIFEST,module.SCHEMA
        wave,status,hashes=base.evidence(case,directory)
        report=read_checked(directory/base.MEASUREMENT,pin['measurements'])
        name='sar7_qbuffer_summary.json' if kind=='qbuffer' else 'sar7_strong_decode_summary.json'
        summary=read_checked(root/name,pin['summary'])
        common.need(status['slurm_job_id']==report['slurm_task_id']==summary['job_id']==pin['job']
            and report['case']==case and report['execution_files_sha256']==hashes and report['tran_sha256']==pin['tran']
            and summary['provenance']['tran_sha256']==pin['tran']
            and summary['provenance']['measurements_sha256']==pin['measurements']
            and summary['provenance']['portable_deck_sha256']==pin['portable'],'Source evidence/provenance differs')
        inventory=common.raw_inventory(directory)
        common.need(common.matches_historical_inventory(status['raw_inventory'],inventory),'Original raw inventory differs')
        trace=[r for r in inventory if r['path'] in ('raw/tranResponse.tran',base.review.RAW_NAME)]
        common.need(len(trace)==1 and trace[0]['sha256']==pin['tran'],'Wrong original transient')
        required={'time',*wave['saved_signals']}
        raw=base.review.safe_raw(directory,dict(status,raw_inventory=inventory),trace[0]['path'].removeprefix('raw/'),
            parser=partial(base.review.parse_selected,required=required))
        common.need(raw.unit('time')=='s' and raw.sweep_names==['time'] and raw.sha256==pin['tran'],'Wrong PSF time axis')
        score.validate_trace_arrays(raw.values,required,wave['stop_s'],wave['strobe_s'])
        reports={r['index']:r for r in report['conversions'] if r['scored']}
        conversions={r['index']:r for r in wave['conversions']}
        compact,dense=[],[]
        for index,bit in TARGETS:
            a,b=selected_window(raw.values,wave,conversions[index],bit,kind,reports[index]);compact.append(a);dense.append(b)
        unchanged(hashes,base.evidence(case,directory)[2]);unchanged(inventory,common.raw_inventory(directory))
        common.need(common.sha(directory/base.MEASUREMENT)==pin['measurements'] and common.sha(root/name)==pin['summary'],
                    'Source measured JSON changed during audit')
        metadata=dict(source_kind=kind,job_id=pin['job'],case_id=case['case_id'],source_root_name=root.name,
                      source_sha256=pin,new_solver_jobs=0,source_read_only=True,raw_parse_count=1)
        return dict(metadata,windows=compact),dict(metadata,windows=dense)
    finally:base.build,base.PLAN,base.MANIFEST,base.SCHEMA=saved


def save_identical(path,value):
    if path.exists():common.need(common.read(path)==value,'Existing audit output differs')
    else:common.write_new(path,value)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('verify','audit'))
    parser.add_argument('--qbuffer-root',type=Path);parser.add_argument('--strong-root',type=Path)
    parser.add_argument('--output-root',type=Path)
    args=parser.parse_args();verify()
    if args.mode=='verify':print('Two frozen sources verified; retained-only audit, zero solver');return
    common.need(all(p is not None for p in (args.qbuffer_root,args.strong_root,args.output_root)),'Supply both source roots and separate output root')
    output=common.checked_root(args.output_root)
    common.need(output.name.startswith('pam4_sar7_qbuffer_audit_'),'Use a new audit output root')
    separate_paths([args.qbuffer_root.resolve(strict=True),args.strong_root.resolve(strict=True)],output)
    compact=[];dense=[]
    for kind,root in (('qbuffer',args.qbuffer_root),('strong',args.strong_root)):
        a,b=audit_source(root,kind);compact.append(a);dense.append(b)
    limits=['Gate rail and half-supply commands are proxies, not direct switch conduction/current measurements',
            'Late raw decisions never replace the frozen original compare-read scores',
            'Selected native0.25ps samples and phase voltages are local evidence only; do not commit them to GitHub',
            'No solver, no new circuit, no source collect/locks, no source writes']
    for filename,sources in (('sar7_qbuffer_audit_compact.json',compact),('sar7_qbuffer_audit_local_evidence.json',dense)):
        target=output/filename;save_identical(target,dict(schema=SCHEMA,status='retained_evidence',sources=sources,limits=limits))
        print(target.name,common.sha(target))


if __name__=='__main__':main()
