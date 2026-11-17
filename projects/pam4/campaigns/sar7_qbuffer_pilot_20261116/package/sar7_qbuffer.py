"""One matched1x-INV/2x-INV isolation probe for the strong decoder q inputs."""

import argparse
from bisect import bisect_left,bisect_right
import copy
from datetime import datetime,timezone
from functools import partial
import hashlib
import json
import os
from pathlib import Path
import re
import sys


ROOT=Path(__file__).resolve().parent
MANIFEST=ROOT/'SHA256SUMS.txt'
PLAN=ROOT/'PLAN.json'
SCHEMA='pam4_sar7_qbuffer_pilot_v1'
CASE_ID='sar7_16_tt_175gs_qbuffer'
PARENT_JOB='761524'
PARENT_MANIFEST_SHA='43b93d73f5f5e08fc350a6b9a12ae6c54ec3c5eac280190be93a38b3fe4b8bd8'
PARENT_DECK_SHA='31d7e4e66c8f33a6432d640050285736454e63fa8cc171b04f13b39875180da8'
PARENT_SUMMARY_SHA='73dafa11235da6c63048536e447cd3bda60dba23155b03a399d86c725a84ac03'
REVIEWED_DECK_SHA='509bbedfdc2be956eafade7021b968eeb60d29f0fcb654d2c0037a22b5da813a'
PARENT=Path(os.environ.get('PAM4_SAR7_STRONG_DECODE_PACKAGE',ROOT.parent/
    'PAM4_SAR7_STRONG_DECODE_PILOT_20261116')).resolve()
if hashlib.sha256((PARENT/'SHA256SUMS.txt').read_bytes()).hexdigest()!=PARENT_MANIFEST_SHA:
    raise ValueError('Wrong exact strong-decode parent package')
sys.path.insert(0,str(PARENT))
import sar7_strong_decode as parent

base,common,native,score,fast=parent.base,parent.common,parent.native,parent.score,parent.fast
BITS=parent.BITS;WAITS=parent.WAITS;READS=parent.READS;READOUTS=parent.READOUTS
CLOCK_OFF_PS=parent.CLOCK_OFF_PS;EXPIRES=parent.EXPIRES
Q_NODES={str(bit):{side:dict(raw=f'q{bit}{side}',mid=f'qmid{bit}{side}',decode=f'qdecode{bit}{side}')
                         for side in 'pn'} for bit in BITS}
Q_SAVES=tuple(node for branch in Q_NODES.values() for nodes in branch.values()
              for node in (nodes['mid'],nodes['decode']))
EXTRA_SAVES=(*parent.EXTRA_SAVES,*Q_SAVES)
PLAN_RECORD=dict(schema=SCHEMA,cases=[dict(case_id=CASE_ID,parent_job=PARENT_JOB,
    parent_manifest_sha256=PARENT_MANIFEST_SHA,parent_deck_sha256=PARENT_DECK_SHA,
    source_summary_sha256=PARENT_SUMMARY_SHA,q_buffer_first_cell='SAR_INV',
    q_buffer_second_cell='SAR_NDINV2',q_buffer_stage_count=2,schedule_unchanged=True)])


def case_record():
    common.need(common.read(PLAN)==PLAN_RECORD,'Expected one frozen q-isolation candidate')
    return dict(parent.case_record(),case_id=CASE_ID)


def timing_schedule():
    return parent.timing_schedule()


def build(case):
    common.need(case==case_record(),'Only the frozen qbuffer case is supported')
    source,old=parent.build(parent.case_record())
    common.need(old['portable_sha256']==PARENT_DECK_SHA,'Wrong measured strong decoder baseline')
    rows,inserted,rewired,save_count=[],set(),set(),0
    for line in source.decode('ascii').splitlines():
        match=re.fullmatch(r'(XNDO([pn])([0-6])) \(([^)]*)\) SAR_OAI21_X2',line)
        other=re.fullmatch(r'(XNDZ([pn])([0-6])) \(([^)]*)\) SAR_NOR3_P3',line)
        if match or other:
            record=match or other;label,side,bit,payload=record.groups();nodes=payload.split()
            branch=Q_NODES[bit][side]
            common.need(len(nodes)==5 and nodes[0]==f'trial{bit}' and nodes[1]==branch['raw']
                        and nodes[-1]=='vdd','Unexpected decoder q input role')
            if match:
                key=(bit,side);common.need(key not in inserted,'Duplicate q buffer')
                rows.append(f'XQIN{bit}{side} ({branch["raw"]} {branch["mid"]} vdd) SAR_INV')
                rows.append(f'XQOUT{bit}{side} ({branch["mid"]} {branch["decode"]} vdd) SAR_NDINV2')
                inserted.add(key)
            nodes[1]=branch['decode']
            line=f'{label} ({" ".join(nodes)}) '+('SAR_OAI21_X2' if match else 'SAR_NOR3_P3')
            rewired.add(label)
        if line.startswith('save '):
            common.need(not set(Q_SAVES)&set(line.split()),'Buffer probes already exist')
            line+=' '+' '.join(Q_SAVES);save_count+=1
        rows.append(line)
    common.need(len(inserted)==14 and len(rewired)==28 and save_count==1,'Wrong buffer or q-port count')
    wave=copy.deepcopy(old['wave'])
    wave['saved_signals'].extend(Q_SAVES)
    wave['q_buffer_nodes']=copy.deepcopy(Q_NODES)
    wave['q_buffer_polarity']='Two inverters: mid inverted, decode noninverting; raw q remains the comparator scoring source'
    bench=('\n'.join(rows)+'\n').encode('ascii');digest=hashlib.sha256(bench).hexdigest()
    if REVIEWED_DECK_SHA is not None:
        common.need(digest==REVIEWED_DECK_SHA,'Qbuffer portable SHA differs: '+digest)
    return bench,dict(case=case,wave=wave,portable_sha256=digest,parent_job=PARENT_JOB,
        parent_manifest_sha256=PARENT_MANIFEST_SHA,parent_deck_sha256=PARENT_DECK_SHA,
        parent_summary_sha256=PARENT_SUMMARY_SHA,schedule_ps=copy.deepcopy(old['schedule_ps']),
        clock_off_ps=CLOCK_OFF_PS,primary_readout_ps=565,diagnostic_readouts_ps=[563,554,557],
        buffer_cells=['SAR_INV','SAR_NDINV2'],new_buffer_instances=28,rewired_decoder_q_ports=28)


def verify():
    entries=[line.split('  ',1) for line in MANIFEST.read_text(encoding='ascii').splitlines()]
    names={'sar7_qbuffer.py','sar7_qbuffer.sbatch','test_sar7_qbuffer.py','PLAN.json','HANDOFF_zh_TW.md'}
    common.need(len(entries)==len(names) and {name for digest,name in entries}==names,'Unexpected qbuffer manifest')
    for digest,name in entries:
        path=ROOT/name
        common.need(path.resolve().parent==ROOT and common.sha(path)==digest,'Qbuffer package differs: '+name)
    _,old=parent.verify()
    common.need(old['portable_sha256']==PARENT_DECK_SHA,'Original strong package differs')
    case=case_record();return case,build(case)[1]


def approval_record(root,meta,approved):
    return dict(approved=approved,platform='Olympus',campaign=SCHEMA,case_ids=[CASE_ID],
                authorized_run_root=str(root),design_source_sha256=common.sha(MANIFEST),
                deck_sha256_by_case={CASE_ID:meta['portable_sha256']})


def q_buffer_detail(values,time,conversion,trial,wave):
    bit=str(trial['bit']);vdd=wave['vdd_V']
    def observe(at):
        rails={stage:[score.interpolate(time,values[Q_NODES[bit][side][stage]],at) for side in 'pn']
               for stage in ('raw','mid','decode')}
        raw=score.classify(*rails['raw'],vdd);decoded=score.classify(*rails['decode'],vdd)
        inverted=score.classify(*reversed(rails['mid']),vdd)
        return dict(at_s=at,raw_q_pair_V=rails['raw'],inverted_mid_pair_V=rails['mid'],decode_pair_V=rails['decode'],
            raw_class=raw,decode_class=decoded,mid_class_in_raw_polarity=inverted,
            noninverting_match=None if raw is None or decoded is None else raw==decoded)
    following=next((t['launch_s'] for t in conversion['trials'] if t['bit']==trial['bit']-1),
                   (conversion['index']+1)*wave['period_s']+native.timing(78))
    times=[('compare_plus_15ps',trial['compare_s']+native.timing(15)),
           ('compare_plus_30ps',trial['compare_s']+native.timing(30)),
           ('read',trial['read_s']),('release',trial['trial_release_s']),('next_launch',following)]
    observations={label:observe(at) for label,at in times if time[0]<=at<=time[-1]}
    end=min(following,time[-1])
    crossings={stage:{side:parent.crossings(time,values[Q_NODES[bit][side][stage]],trial['compare_s'],end,
                                           vdd/2,trial['compare_s']) for side in 'pn'}
               for stage in ('raw','mid','decode')}
    raw_decision,raw_stable=score.rail_exit(time,values,trial['cmp_pair'],trial['compare_s'],trial['read_s'],vdd)
    pair=[Q_NODES[bit][side]['decode'] for side in 'pn']
    decode_decision,decode_stable=score.rail_exit(time,values,pair,trial['compare_s'],trial['read_s'],vdd)
    return dict(observations=observations,gate_half_crossings_ps_from_compare=crossings,
        raw_class_at_original_read=raw_decision,decode_class_at_original_read=decode_decision,
        raw_stable_rail_delay_ps=None if raw_stable is None else (raw_stable-trial['compare_s'])/native.PS,
        decode_stable_rail_delay_ps=None if decode_stable is None else (decode_stable-trial['compare_s'])/native.PS,
        next_launch_within_saved_trace=following<=time[-1],
        observation_limit='No extrapolation after saved stop; the last b0 next-cycle launch is unavailable')


def read_code(values, time, conversion, at, vdd):
    decisions = [score.classify(*(score.interpolate(time, values[k], at) for k in pair), vdd)
                 for pair in conversion['code_pairs']]
    return None if None in decisions else sum(decision << bit for decision, bit in zip(decisions, BITS, strict=True))


def overlap_proxy(time, traces, lo, hi, half):
    # Each reference path counts as possibly on when either TG gate crosses the half-supply proxy.
    first, stop = bisect_left(time, lo), bisect_right(time, hi)
    co, cbo, cz, cbz = traces
    active = [index for index in range(first, stop)
              if (co[index] >= half or cbo[index] <= half) and (cz[index] >= half or cbz[index] <= half)]
    runs = []
    for index in active:
        if not runs or runs[-1][-1] + 1 != index:
            runs.append([index])
        else:
            runs[-1].append(index)
    return dict(samples=len(active), events=len(runs), max_sample_span_ps=max(
        ((time[run[-1]] - time[run[0]]) / native.PS for run in runs), default=0.0))


def crossings(time, trace, lo, hi, threshold, origin):
    result = []
    for i in range(max(1, bisect_left(time, lo)), min(len(time), bisect_right(time, hi) + 1)):
        a, b = trace[i - 1], trace[i]
        if (a < threshold <= b) or (b <= threshold < a):
            when = time[i - 1] + (time[i] - time[i - 1]) * (threshold - a) / (b - a)
            if lo <= when <= hi:
                result.append([(when - origin) / native.PS, 'rise' if b > a else 'fall'])
    return result


def screen(rows, observed, cm):
    cmp = fast.offset.error_metrics(rows, 'observed_comparator_code')
    reg = fast.offset.error_metrics(observed, 'observed_registered_code')
    unresolved = sum(trial['decision'] is None for row in rows for trial in row['trial_results'])
    agreement = all(c['observed_comparator_code'] is not None and
                    c['observed_comparator_code'] == r['observed_registered_code']
                    for c, r in zip(rows, observed, strict=True))
    passed = (unresolved == 0 and agreement and max(map(abs, cm)) <= 10 and
              cmp['max_abs_code_error'] is not None and cmp['max_abs_code_error'] <= 1 and cmp['wrong'] <= 6)
    return dict(screen_pass=passed, logic_smoke_pass=unresolved == 0 and agreement and cmp['wrong'] == 0,
                comparator=cmp, registered=reg, unresolved_bits=unresolved,
                comparator_registered_agreement=agreement, final_dac_cm_change_mV=[min(cm), max(cm)])



def apply_physical_screen(measured,window,active_cm_pass):
    result=dict(measured)
    result.update(physical_read_window_valid=window,active_last_read_cm_pass=active_cm_pass)
    result['screen_pass']=measured['screen_pass'] and window and active_cm_pass
    # Keep the historical digital zero-error definition independent of analog gates.
    return result


def summarize(report,root,case,meta):
    directory=root/CASE_ID
    wave,status,hashes=base.evidence(case,directory)
    common.need(report['execution_files_sha256']==hashes,'Different original report provenance')
    live=common.raw_inventory(directory)
    common.need(common.matches_historical_inventory(status['raw_inventory'],live),'Retained transient differs')
    traces=[item for item in live if item['path'] in ('raw/tranResponse.tran',base.review.RAW_NAME)]
    common.need(len(traces)==1,'Expected one completed native transient')
    required={'time',*EXTRA_SAVES,*wave['dac_pair'],'sensep','sensen','conv','reset','track',
        *[f'clk{k}' for k in BITS],*[f'q{k}{side}' for k in BITS for side in 'pn'],
        *[f'XCMP{k}.{node}' for k in BITS for node in 'xy'],
        *[pin for cv in wave['conversions'] for pair in cv['code_pairs'] for pin in pair]}
    raw=base.review.safe_raw(directory,dict(status,raw_inventory=live),traces[0]['path'].removeprefix('raw/'),
                            parser=partial(base.review.parse_selected,required=required))
    common.need(raw.unit('time')=='s' and raw.sweep_names==['time'] and raw.sha256==report['tran_sha256']
        and all(raw.unit(key)=='A' for key in ('V_RHI:p','V_RLO:p')),'Wrong time/current units or source')
    values=raw.values
    time=score.validate_trace_arrays(values,required,wave['stop_s'],wave['strobe_s'])
    rows=[row for row in report['conversions'] if row['scored']]
    common.need(len(rows)==len(wave['conversions'])==report['tested_conversions']==12
        and all(len(row['trial_results'])==7 for row in rows),'Expected all12conversions and84trials')
    observed={at:[] for at in READOUTS};cm_by_read={at:[] for at in READOUTS}
    validity={at:[] for at in READOUTS}
    codes,details,rail_currents,last_trigger_cm,last_read_cm=[],[],[],[],[]
    vdd,half,lsb=wave['vdd_V'],wave['vdd_V']/2,wave['lsb_V']
    for conversion,row in zip(wave['conversions'],rows,strict=True):
        late=conversion['end_s']
        common.need(read_code(values,time,conversion,late,vdd)==row['observed_registered_code'],
                    'Original report is not the predeclared565ps readout')
        code=dict(expected=row['expected_code'],comparator=row['observed_comparator_code'])
        for at in READOUTS:
            instant=conversion['readout_times_s'][str(at)]
            value=read_code(values,time,conversion,instant,vdd)
            observed[at].append(dict(expected_code=row['expected_code'],observed_registered_code=value))
            code[f'registered_{at}']=value
            _,cm=score.differential(time,values,wave['dac_pair'],instant)
            cm_by_read[at].append(1000*(cm-row['sample_dac_common_mode_V']))
            phases={name:score.interpolate(time,values[name],instant) for name in ('conv','reset','track')}
            clocks=[score.interpolate(time,values[f'clk{bit}'],instant) for bit in BITS]
            valid=(phases['reset']<=.2*vdd and phases['track']<=.2*vdd and min(clocks)>=.8*vdd)
            validity[at].append(dict(index=conversion['index'],reset_V=phases['reset'],track_V=phases['track'],
                conv_V=phases['conv'],minimum_comparator_clock_V=min(clocks),valid_read_window=valid))
        codes.append(code)
        for target,at in ((last_trigger_cm,conversion['trials'][-1]['compare_s']),
                          (last_read_cm,conversion['trials'][-1]['read_s'])):
            _,cm=score.differential(time,values,wave['dac_pair'],at)
            target.append(1000*(cm-row['sample_dac_common_mode_V']))
        active_lo=conversion['index']*wave['period_s']+native.timing(73)
        first,stop=bisect_left(time,active_lo),bisect_right(time,late)
        rail_currents.append({key:max(map(abs,values[key][first:stop])) for key in ('V_RHI:p','V_RLO:p')})
        for trial, scored in zip(conversion['trials'], row['trial_results'], strict=True):
            bit = trial['bit']
            launch, pre, read, release = (trial[k] for k in ('launch_s', 'pre_s', 'read_s', 'trial_release_s'))
            gates = (f'c{bit}o', f'cb{bit}o', f'c{bit}z', f'cb{bit}z')
            drive_edges = {g: crossings(time, values[g], launch - native.timing(3), release, half, launch) for g in gates}
            snapshots = {}
            for label, at in (('before_launch', launch - native.timing(1)), ('precompare', pre),
                              ('compare_plus_15ps', trial['compare_s'] + native.timing(15)),
                              ('compare_plus_30ps', trial['compare_s'] + native.timing(30)),
                              ('read', read), ('after_release_1ps', release + native.timing(1))):
                held, _ = score.differential(time, values, wave['dac_pair'], at)
                sense,sense_cm=score.differential(time,values,('sensep','sensen'),at)
                snapshots[label] = dict(held_diff_lsb=held / lsb,sense_diff_lsb=sense/lsb,sense_common_mode_V=sense_cm,
                                        sense_pair_V=[score.interpolate(time,values[node],at) for node in ('sensep','sensen')],
                                        p_bottom_V=score.interpolate(time, values[f'b{bit}p'], at),
                                        n_bottom_V=score.interpolate(time, values[f'b{bit}n'], at),
                                        q_V=[score.interpolate(time, values[p], at) for p in trial['cmp_pair']],
                                        cmp_xy_V=[score.interpolate(time, values[f'XCMP{bit}.{node}'], at) for node in 'xy'])
            p, n = (values[k] for k in wave['dac_pair'])
            last = bisect_right(time, read) - 1
            j, stop = last, bisect_left(time, launch)
            target = snapshots['read']['held_diff_lsb'] * lsb
            while j >= stop and abs(p[j] - n[j] - target) <= lsb:
                j -= 1
            enter = ((time[j + 1] - launch) / native.PS) if j + 1 <= last else None
            stable = scored['stable_rail_delay_s']
            details.append(dict(conversion=conversion['index'], bit=bit, decision=scored['decision'],
                                sampled_margin_ps=None if stable is None else (scored['compare_to_read_s'] - stable) / native.PS,
                                gate_half_vdd_crossings_ps=drive_edges,
                                overlap_proxy_full_conversion=overlap_proxy(time, [values[g] for g in gates], active_lo, late, half),
                                first_remains_in_read_plus_minus_lsb_after_launch_ps=enter, snapshots=snapshots))
            details[-1]['q_buffer']=q_buffer_detail(values,time,conversion,trial,wave)

    _,_,after=base.evidence(case,directory)
    common.need(after==hashes and common.raw_inventory(directory)==live,'Evidence changed during summary')
    active_cm_pass=max(map(abs,last_read_cm))<=10
    result=dict(schema=SCHEMA,case_id=CASE_ID,stage='physical_qbuffer_tt_12_centers',
        sampling_rate_gsps=1/wave['period_s']/1e9,schedule_ps=meta['schedule_ps'],primary_readout_ps=565,
        clock_off_ps=CLOCK_OFF_PS,max_abs_sample_error_lsb=report['max_abs_sample_error_lsb'],
        max_observed_resolve_delay_s=report['max_observed_resolve_delay_s'],job_id=report['slurm_task_id'],
        solver_seconds=report['solver_seconds'],raw_bytes=report['raw_bytes'],codes=codes,timing=details,
        last_comparison_trigger_cm_change_mV=[min(last_trigger_cm),max(last_trigger_cm)],
        last_comparison_read_cm_change_mV=[min(last_read_cm),max(last_read_cm)],
        active_last_read_cm_pass=active_cm_pass,
        post_conv_readout_cm_label='Readout563/565ps occurs after conv off558ps and before reset566ps; not the active-comparison CM',
        ref_source_peak_abs_A_during_conv_and_postconv=rail_currents,
        provenance=dict(manifest_sha256=common.sha(MANIFEST),portable_deck_sha256=meta['portable_sha256'],
            parent_manifest_sha256=PARENT_MANIFEST_SHA,parent_portable_deck_sha256=PARENT_DECK_SHA,
            parent_reported_summary_sha256=PARENT_SUMMARY_SHA,measurements_sha256=common.sha(directory/base.MEASUREMENT),
            tran_sha256=report['tran_sha256'],execution_files_sha256=hashes))
    for at in READOUTS:
        measured=screen(rows,observed[at],cm_by_read[at])
        window=all(record['valid_read_window'] for record in validity[at])
        measured=apply_physical_screen(measured,window,active_cm_pass)
        measured['read_window_evidence']=validity[at]
        result[f'readout_{at}']=measured
    return result


def existing_stage(root,case,model_root):
    directory=root/CASE_ID
    common.need(directory.is_dir() and directory==directory.resolve(strict=True),'Run requires the existing real staged case')
    for name in ('bench.scs','case.json'):
        common.owned_file(directory,directory/name)
    source,meta=build(case)
    proof=base.original.model_preflight.verify_private_kit(model_root,'tt')
    token=base.review.gm_center64.BASE.MODEL_TOKEN.encode('ascii');model=proof['model_root'].encode('utf-8')
    bench=source.replace(token,model)
    common.need(source.count(token)==1 and bench.replace(model,token)==source,'Nonreversible model root substitution')
    record=dict(meta,model_preflight=proof,bench_sha256=hashlib.sha256(bench).hexdigest())
    common.need((directory/'bench.scs').read_bytes()==bench and common.read(directory/'case.json')==record,
                'Existing staged design is not byte-exact')
    return directory


def check_stage_deadline(now):
    common.need(now<EXPIRES,'No new stage after23:15Chicago; collect-only remains permitted')


def check_run_submission(now):
    if now>=EXPIRES:
        # Reuse the pinned, tested single read-only Slurm SubmitTime query.
        return fast.offset.query_preexpiry_slurm_submission(now)
    return None


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('verify','approval-template','stage','run','collect-only'))
    parser.add_argument('--root',type=Path);parser.add_argument('--approval',type=Path)
    parser.add_argument('--model-root',type=Path)
    args=parser.parse_args();case,meta=verify()
    if args.mode=='verify':
        print(CASE_ID,meta['portable_sha256']);return
    common.need(args.root is not None and args.approval is not None,'Supply isolated root and approval')
    root=common.checked_root(args.root);approval=args.approval.absolute()
    common.need(root.name.startswith('pam4_sar7_qbuffer_pilot_') and approval.parent==root,
                'Use a new qbuffer root with its own approval')
    if args.mode=='approval-template':
        common.write_new(approval,approval_record(root,meta,False));return
    common.need(common.read(approval)==approval_record(root,meta,True),'Approval must bind this exact root,manifest and deck')
    base.build,base.PLAN,base.MANIFEST,base.SCHEMA=build,PLAN,MANIFEST,SCHEMA
    base.TIMEOUT_S=540
    if args.mode in ('stage','run'):
        common.need(args.model_root is not None,'Use the existing verified private model root')
        if args.mode=='stage':
            check_stage_deadline(datetime.now(timezone.utc))
            print(base.stage(root,case,args.model_root));return
        check_run_submission(datetime.now(timezone.utc))
        existing_stage(root,case,args.model_root)
        saved=base.stage
        try:
            base.stage=existing_stage
            report=base.run(root,case,args.model_root,approval)
        finally:
            base.stage=saved
    else:
        report=base.collect(root,case)
    result=summarize(report,root,case,meta);target=root/'sar7_qbuffer_summary.json'
    if target.exists():common.need(common.read(target)==result,'Existing qbuffer summary differs')
    else:common.write_new(target,result)
    print(json.dumps(dict(summary=str(target),sha256=common.sha(target),screen_pass=result['readout_565']['screen_pass'])))


if __name__=='__main__':
    main()
