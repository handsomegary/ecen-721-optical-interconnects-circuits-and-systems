"""Run one SAR7 timing control with ample DAC settling and comparator time."""

import argparse
import copy
import hashlib
import importlib.util
import os
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parent
BASE = Path(os.environ.get('PAM4_SAR7_PACKAGE',ROOT.parent/'PAM4_R5_SAR7_SLICE_20261115')).resolve()
MANIFEST = ROOT/'SHA256SUMS.txt'
PLAN = ROOT/'PLAN.json'
SCHEMA = 'pam4_sar7_relaxed_timing_pilot_v1'
CASE_ID = 'sar7_03_tt_relaxed'
BASE_SHA = '508d969b0717a7010f579035a86d79db20ddf805f75284fc894f48fcd0baa867'
PERIOD_PS = 1080
STEP_PS = 136
SETTLE_PS = 60
EVAL_PS = 60
END_PS = 1027
STOP_PS = 1040
if hashlib.sha256((BASE/'SHA256SUMS.txt').read_bytes()).hexdigest() != (
        'a6271a138e7a4b4c896323d6f4c56f30f9d661bfba902457d91fe39281f1250f'):
    raise ValueError('Original SAR7 package differs')
sys.path.insert(0,str(BASE))
spec = importlib.util.spec_from_file_location('_sar7_relaxed_parent',BASE/'sar7_run.py')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
common = base.common
native = base.native
base_build = base.build
base_plan = base.PLAN


def pulse(name,on,off,inverted=False):
    prefix,sep,_ = native.pulse(name,on,off,inverted).partition(' period=')
    common.need(bool(sep),'Expected a native periodic pulse')
    return prefix + sep + native.number(native.timing(PERIOD_PS))


def source_with_period(line,last):
    left,sep,body = line.partition(' wave=[')
    common.need(bool(sep) and body.endswith(']'),'Unexpected source vector')
    source = body[:-1].split()
    common.need(len(source)==2*(2*11+2),'Expected twelve original SAR input plateaus')
    old_period_ps = native.PERIOD/native.PS
    begin = PERIOD_PS-(old_period_ps-557)
    times = [0.]
    for i in range(11):
        times.extend(native.timing(t+i*PERIOD_PS) for t in (begin,begin+4))
    times.append(last)
    values = ' '.join(f'{native.number(t)} {v}' for t,v in zip(times,source[1::2],strict=True))
    return left+sep+values+']'


def build(case):
    prior = common.read(base_plan)['cases'][0]
    common.need(case==dict(prior,case_id=CASE_ID),'Expected the same original twelve centers and circuit')
    original,meta = base_build(prior)
    common.need(meta['portable_sha256']==BASE_SHA,'Original SAR bench differs')
    old_period_ps = native.PERIOD/native.PS
    track_on = PERIOD_PS-(old_period_ps-569)
    reset_on = PERIOD_PS-(old_period_ps-566)
    schedule = [('track',65,569,65,track_on,True),('trackb',65,569,65,track_on,False),
                ('lowtrack',55,569,55,track_on,True),('lowtrackb',55,569,55,track_on,False),
                ('reset',69,566,69,reset_on,True),('resetb',69,566,69,reset_on,False),
                ('conv',73,558,73,END_PS+4,False),('convb',73,558,73,END_PS+4,True)]
    for step,bit in enumerate(native.BITS):
        launch = 78+step*STEP_PS
        schedule.extend(((f'trial{bit}',78+step*66,143+step*66,launch,launch+SETTLE_PS+EVAL_PS+2,False),
                         (f'clk{bit}',116+step*66,560,launch+SETTLE_PS,END_PS+6,False)))
    replacements = {native.pulse(name,on,off,inv):pulse(name,new_on,new_off,inv)
                    for name,on,off,new_on,new_off,inv in schedule}
    lines = original.decode('ascii').splitlines()
    common.need(all(lines.count(line)==1 for line in replacements),'Missing original pulse line')
    stop = native.timing(11*PERIOD_PS+STOP_PS)
    changed = []
    changed_labels = []
    for line in lines:
        if line in replacements:
            out = replacements[line]
        elif line.startswith(('V_srcp ','V_srcn ')):
            out = source_with_period(line,stop)
        elif line.startswith('tranResponse tran '):
            out,n = re.subn(r'\bstop=\S+',f'stop={native.number(stop)}',line)
            common.need(n==1,'Expected one transient stop')
        else:
            out = line
        changed.append(out)
        if out!=line:
            changed_labels.append(line.split()[0])
    common.need(set(changed_labels)=={line.split()[0] for line in replacements}|{'V_srcp','V_srcn','tranResponse'}
                and len(changed_labels)==25,'Unexpected original bench modifications')
    wave = copy.deepcopy(meta['wave'])
    wave.update(period_s=native.timing(PERIOD_PS),stop_s=stop)
    for i,conversion in enumerate(wave['conversions']):
        start = i*PERIOD_PS
        conversion.update(sample_s=native.timing(start+67),end_s=native.timing(start+END_PS))
        for step,trial in enumerate(conversion['trials']):
            at = start+78+step*STEP_PS
            compare = at+SETTLE_PS
            read = compare+EVAL_PS
            trial.update(launch_s=native.timing(at),pre_s=native.timing(compare-.5),
                         compare_s=native.timing(compare),read_s=native.timing(read),
                         trial_release_s=native.timing(read+2))
            common.need(read+2 < start+END_PS,'Trial misses the retained result deadline')
    bench = ('\n'.join(changed)+'\n').encode('ascii')
    return bench,dict(case=case,wave=wave,portable_sha256=hashlib.sha256(bench).hexdigest(),
                      reference_sha256=BASE_SHA,changed_labels=changed_labels,
                      diagnostic_period_ps=PERIOD_PS,trial_launch_to_compare_ps=SETTLE_PS,comparison_window_ps=EVAL_PS)


def verify():
    base.verify()
    for line in MANIFEST.read_text(encoding='ascii').splitlines():
        digest,name = line.split('  ',1)
        path = ROOT/name
        common.need(path.resolve().is_relative_to(ROOT) and common.sha(path)==digest,'Modified package file '+name)
    plan = common.read(PLAN)
    common.need(plan['schema']==SCHEMA and len(plan['cases'])==1,'Expected one relaxed diagnostic')
    case, = plan['cases']
    return case,build(case)[1]


def summarize(report):
    scored = [row for row in report['conversions'] if row['scored']]
    common.need(len(scored)==report['tested_conversions']==12,'Expected the twelve original centers')
    by_bit = {str(bit):sum(trial['decision'] is None for row in scored for trial in row['trial_results']
                          if trial['bit']==bit) for bit in native.BITS}
    cm = [1000*row['final_dac_common_mode_change_from_sample_V'] for row in scored]
    codes = [dict(expected=row['expected_code'],comparator=row['observed_comparator_code'],
                  registered=row['observed_registered_code']) for row in scored]
    return dict(status='measured',case_id=CASE_ID,job_id=report['slurm_task_id'],
        baseline_job_id='760002',baseline_wrong_conversions=10,baseline_unresolved_bits=0,
        diagnostic_period_ps=PERIOD_PS,trial_launch_to_compare_ps=SETTLE_PS,comparison_window_ps=EVAL_PS,
        wrong_conversions=report['wrong_conversions'],unresolved_bits=by_bit,
        final_cm_change_mV=[min(cm),max(cm)],max_abs_sample_error_lsb=report['max_abs_sample_error_lsb'],
        max_observed_resolve_delay_s=report['max_observed_resolve_delay_s'],logic_smoke_pass=report['logic_smoke_pass'],
        solver_seconds=report['solver_seconds'],raw_bytes=report['raw_bytes'],tran_sha256=report['tran_sha256'],codes=codes)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('verify','approval-template','stage','run','collect-only'))
    parser.add_argument('--root',type=Path)
    parser.add_argument('--model-root',type=Path)
    parser.add_argument('--approval',type=Path)
    args = parser.parse_args()
    case,meta = verify()
    if args.mode=='verify':
        print(CASE_ID,meta['portable_sha256'])
        return
    common.need(args.root is not None and args.approval is not None,'Provide the diagnostic root and approval file')
    root = common.checked_root(args.root)
    common.need(root.name.startswith('pam4_sar7_relaxed_'),'Use a new relaxed-control run root')
    approval = args.approval.absolute()
    common.need(approval.parent==root,'Keep approval inside the campaign directory')
    base.build,base.PLAN,base.MANIFEST,base.SCHEMA = build,PLAN,MANIFEST,SCHEMA
    allowed = dict(approved=True,platform='Olympus',campaign=SCHEMA,case_ids=[CASE_ID],
                   design_source_sha256=common.sha(MANIFEST),authorized_run_root=str(root),
                   deck_sha256=meta['portable_sha256'])
    if args.mode=='approval-template':
        common.write_new(approval,dict(allowed,approved=False))
        return
    common.need(common.read(approval)==allowed,'Approval must bind the exact new root, manifest and case')
    if args.mode in ('stage','run'):
        common.need(args.model_root is not None,'Use the same approved private kit')
        if args.mode=='stage':
            print(base.stage(root,case,args.model_root))
            return
        report = base.run(root,case,args.model_root,approval)
    else:
        report = base.collect(root,case)
    target = root/'sar7_relaxed_summary.json'
    result = summarize(report)
    if target.exists():
        common.need(common.read(target)==result,'Existing relaxed timing summary differs')
    else:
        common.write_new(target,result)
    print(target)


if __name__=='__main__':
    main()
