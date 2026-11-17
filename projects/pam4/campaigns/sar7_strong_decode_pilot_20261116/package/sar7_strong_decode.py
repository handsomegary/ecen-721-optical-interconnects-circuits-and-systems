"""One stack-compensated native decoder experiment at unchanged1.75GS/s."""

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
SCHEMA='pam4_sar7_strong_decode_pilot_v1'
CASE_ID='sar7_15_tt_175gs_strong_decode'
PARENT_JOB='761433'
PARENT_MANIFEST_SHA='12e5745c9a28f26a5a1bbb8cc11030e1f41da59176d7fdca9b1b187c9763ae24'
PARENT_DECK_SHA='ecd325622c426dfe2c1f5dd42cb00ca30c59f238ba77764d7757af15dd04720a'
PARENT_SUMMARY_SHA='c2f46592839597c54d61ee843da089f86fcc9771aadc7cec0d01ed15f4bfbab6'
REVIEWED_DECK_SHA='31d7e4e66c8f33a6432d640050285736454e63fa8cc171b04f13b39875180da8'
PARENT=Path(os.environ.get('PAM4_SAR7_NATIVE_DECODE_PACKAGE',ROOT.parent/
    'PAM4_SAR7_NATIVE_DECODE_PILOT_20261116')).resolve()
if hashlib.sha256((PARENT/'SHA256SUMS.txt').read_bytes()).hexdigest()!=PARENT_MANIFEST_SHA:
    raise ValueError('Expected exact native R2 parent')
sys.path.insert(0,str(PARENT))
import sar7_native_decode as parent

base,common,native,score=parent.base,parent.common,parent.native,parent.score
fast=parent.fast
BITS=native.BITS
WAITS=(42,45,25,19,15,8,6)
READS=(39,44,40,40,38,41,54)
READOUTS=(565,563,554,557)
CLOCK_OFF_PS=568
EXPIRES=datetime(2026,11,17,5,15,tzinfo=timezone.utc)
EXTRA_SAVES=parent.EXTRA_SAVES
PLAN_RECORD=dict(schema=SCHEMA,cases=[dict(case_id=CASE_ID,parent_job=PARENT_JOB,
    parent_manifest_sha256=PARENT_MANIFEST_SHA,parent_deck_sha256=PARENT_DECK_SHA,
    source_summary_sha256=PARENT_SUMMARY_SHA,waits_ps=list(WAITS),reads_ps=list(READS),
    readouts_ps=list(READOUTS),clock_off_ps=CLOCK_OFF_PS,oai_series_replicas=2,
    nor3_p_replicas=3,decoder_inv_replicas=2,reference_tg_replicas=1)])


def case_record():
    common.need(common.read(PLAN)==PLAN_RECORD,'Expected one frozen driver-only candidate')
    return dict(parent.case_record(),case_id=CASE_ID)


def timing_schedule():
    launch=78;schedule={}
    for bit,wait,observe in zip(BITS,WAITS,READS,strict=True):
        compare=launch+wait;read=compare+observe
        schedule[bit]=(launch,compare,read,read+2)
        launch=read+3
    common.need(schedule[0]==(492,498,552,554),'Wrong b0 budget')
    return schedule


def replicas(template,name,pins,count):
    for index in range(count):
        yield native.mos(template,f'{name}_R{index}',pins)


def decoder_subcircuits():
    _,(_,_,n,p)=native.read_cdf(base.review.R5/'quiet.scs')
    yield 'subckt SAR_OAI21_X2 (a b en y vdd)'
    for name,pins in (('MN1',('y','a','nx','0')),('MN2',('y','b','nx','0')),
                      ('MN3',('nx','en','0','0'))):
        yield from replicas(n,name,pins,2)
    for name,pins,count in (('MP1',('y','a','px','vdd'),2),('MP2',('px','b','vdd','vdd'),2),
                            ('MP3',('y','en','vdd','vdd'),1)):
        yield from replicas(p,name,pins,count)
    yield 'ends SAR_OAI21_X2'
    yield 'subckt SAR_NOR3_P3 (a b enb y vdd)'
    for index,input_name in enumerate(('a','b','enb'),1):
        yield from replicas(n,f'MN{index}',('y',input_name,'0','0'),1)
    for name,pins in (('MP1',('y','a','px','vdd')),('MP2',('px','b','py','vdd')),
                      ('MP3',('py','enb','vdd','vdd'))):
        yield from replicas(p,name,pins,3)
    yield 'ends SAR_NOR3_P3'
    yield 'subckt SAR_NDINV2 (a y vdd)'
    yield from replicas(n,'MN',('y','a','0','0'),2)
    yield from replicas(p,'MP',('y','a','vdd','vdd'),2)
    yield 'ends SAR_NDINV2'


def build(case):
    common.need(case==case_record(),'Only the frozen driver candidate is permitted')
    source,old_meta=parent.build(parent.case_record())
    common.need(old_meta['portable_sha256']==PARENT_DECK_SHA,'Wrong original native R2 deck')
    original=source.decode('ascii').splitlines()
    old_defs=list(parent.decoder_subcircuits())
    start=original.index(old_defs[0])
    common.need(original[start:start+len(old_defs)]==old_defs,'Unexpected original decoder definitions')
    original[start:start+len(old_defs)]=list(decoder_subcircuits())
    new_schedule=timing_schedule();old_schedule=parent.timing_schedule()
    pulses={}
    for bit in BITS:
        launch,compare,read,release=new_schedule[bit]
        old_launch,old_compare,old_read,old_release=old_schedule[bit]
        pulses[native.pulse(f'trial{bit}',old_launch,old_release)]=native.pulse(f'trial{bit}',launch,release)
        pulses[native.pulse(f'clk{bit}',old_compare,560)]=native.pulse(f'clk{bit}',compare,CLOCK_OFF_PS)
    common.need(all(original.count(line)==1 for line in pulses),'Missing parent pulse')
    rows=[];changed_instances=[]
    for line in original:
        if re.match(r'^XNDO[pn][0-6] ',line):
            common.need(line.endswith(' SAR_OAI21'),'Unexpected OAI instance')
            line=line[:-len('SAR_OAI21')]+'SAR_OAI21_X2';changed_instances.append(line.split()[0])
        elif re.match(r'^XNDZ[pn][0-6] ',line):
            common.need(line.endswith(' SAR_NOR3'),'Unexpected NOR3 instance')
            line=line[:-len('SAR_NOR3')]+'SAR_NOR3_P3';changed_instances.append(line.split()[0])
        elif re.match(r'^XNDI[OZ][pn][0-6] ',line):
            common.need(line.endswith(' SAR_INV'),'Unexpected complementary inverter')
            line=line[:-len('SAR_INV')]+'SAR_NDINV2';changed_instances.append(line.split()[0])
        rows.append(pulses.get(line,line))
    common.need(len(changed_instances)==56 and len(set(changed_instances))==56,'Expected56localdecoderinstances')
    wave=copy.deepcopy(old_meta['wave'])
    wave['readout_offsets_ps']=list(READOUTS)
    for conversion in wave['conversions']:
        origin=conversion['index']*wave['period_s']
        conversion['end_s']=origin+native.timing(565)
        conversion['read_late_s']=origin+native.timing(563)
        conversion['readout_times_s']={str(at):origin+native.timing(at) for at in READOUTS}
        for trial in conversion['trials']:
            launch,compare,read,release=new_schedule[trial['bit']]
            trial.update(launch_s=origin+native.timing(launch),pre_s=origin+native.timing(compare-.5),
                         compare_s=origin+native.timing(compare),read_s=origin+native.timing(read),
                         trial_release_s=origin+native.timing(release))
    bench=('\n'.join(rows)+'\n').encode('ascii');digest=hashlib.sha256(bench).hexdigest()
    if REVIEWED_DECK_SHA is not None:
        common.need(digest==REVIEWED_DECK_SHA,'Strong decoder portable SHA differs: '+digest)
    return bench,dict(case=case,wave=wave,portable_sha256=digest,parent_job=PARENT_JOB,
        parent_manifest_sha256=PARENT_MANIFEST_SHA,parent_deck_sha256=PARENT_DECK_SHA,
        parent_summary_sha256=PARENT_SUMMARY_SHA,schedule_ps={str(bit):list(times) for bit,times in new_schedule.items()},
        clock_off_ps=CLOCK_OFF_PS,primary_readout_ps=565,diagnostic_readouts_ps=[563,554,557],
        replicas=dict(oai_series=2,oai_single_en_p=1,nor3_n=1,nor3_p=3,decoder_inv=2,reference_tg=1))


def verify():
    entries=[line.split('  ',1) for line in MANIFEST.read_text(encoding='ascii').splitlines()]
    files={'sar7_strong_decode.py','sar7_strong_decode.sbatch','test_sar7_strong_decode.py','PLAN.json','HANDOFF_zh_TW.md'}
    common.need(len(entries)==len(files) and {name for _,name in entries}==files,'Unexpected strong pilot manifest')
    for digest,name in entries:
        path=ROOT/name
        common.need(path.resolve().parent==ROOT and common.sha(path)==digest,'Package differs: '+name)
    _,meta=parent.verify()
    common.need(meta['portable_sha256']==PARENT_DECK_SHA,'Original R2 dependency differs')
    case=case_record();return case,build(case)[1]


def approval_record(root,meta,approved):
    return dict(approved=approved,platform='Olympus',campaign=SCHEMA,case_ids=[CASE_ID],
        authorized_run_root=str(root),design_source_sha256=common.sha(MANIFEST),
        deck_sha256_by_case={CASE_ID:meta['portable_sha256']})


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
    _,_,after=base.evidence(case,directory)
    common.need(after==hashes and common.raw_inventory(directory)==live,'Evidence changed during summary')
    active_cm_pass=max(map(abs,last_read_cm))<=10
    result=dict(schema=SCHEMA,case_id=CASE_ID,stage='physical_stronger_decoder_tt_12_centers',
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
    common.need(root.name.startswith('pam4_sar7_strong_decode_pilot_') and approval.parent==root,
                'Use a new strong-decoder root with its own approval')
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
    result=summarize(report,root,case,meta);target=root/'sar7_strong_decode_summary.json'
    if target.exists():common.need(common.read(target)==result,'Existing strong summary differs')
    else:common.write_new(target,result)
    print(json.dumps(dict(summary=str(target),sha256=common.sha(target),screen_pass=result['readout_565']['screen_pass'])))


if __name__=='__main__':
    main()
