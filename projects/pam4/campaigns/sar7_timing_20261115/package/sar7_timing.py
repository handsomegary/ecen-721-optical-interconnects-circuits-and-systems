"""One SAR7 timing-only comparison against Olympus job 759069."""

import argparse
import copy
import hashlib
import importlib.util
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT/'SHA256SUMS.txt'
PLAN = ROOT/'PLAN.json'
BASE = Path(os.environ.get('PAM4_SAR7_PACKAGE',ROOT.parent/'PAM4_R5_SAR7_SLICE_20261115')).resolve()
BASE_MANIFEST_SHA = 'a6271a138e7a4b4c896323d6f4c56f30f9d661bfba902457d91fe39281f1250f'
BASE_DECK_SHA = '508d969b0717a7010f579035a86d79db20ddf805f75284fc894f48fcd0baa867'
SCHEMA = 'pam4_r5_sar7_timing_pilot_v1'
CASE_ID = 'sar7_02_tt_earlycmp42'
SHIFT_PS = 17
if hashlib.sha256((BASE/'SHA256SUMS.txt').read_bytes()).hexdigest()!=BASE_MANIFEST_SHA:
    raise ValueError('Original SAR7 package manifest differs')
sys.path.insert(0,str(BASE))
spec = importlib.util.spec_from_file_location('_sar7_timing_frozen_runner',BASE/'sar7_run.py')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
common = base.common
native = base.native
base_build = base.build
base_plan = Path(base.PLAN)


def build(case):
    prior = common.read(base_plan)['cases'][0]
    common.need(prior['case_id']=='sar7_00_tt_pilot' and case==dict(prior,case_id=CASE_ID),
                'The timing case must preserve the original TT input and 12 code centers')
    source,old = base_build(prior)
    common.need(old['portable_sha256']==BASE_DECK_SHA, 'Baseline netlist changed')
    clocks = {native.pulse(f'clk{bit}',116+66*step,560):
              native.pulse(f'clk{bit}',116-SHIFT_PS+66*step,560)
              for step,bit in enumerate(native.BITS)}
    lines = source.decode('ascii').splitlines()
    common.need(all(lines.count(clock)==1 for clock in clocks),
                'Expected one original source for each comparator clock')
    bench = ('\n'.join(clocks.get(line,line) for line in lines)+'\n').encode('ascii')
    wave = copy.deepcopy(old['wave'])
    for conversion in wave['conversions']:
        for trial in conversion['trials']:
            trial['pre_s'] -= native.timing(SHIFT_PS)
            trial['compare_s'] -= native.timing(SHIFT_PS)
            common.need(trial['launch_s']<trial['pre_s']<trial['compare_s']<trial['read_s']<trial['trial_release_s'],
                        'Timing shift changed the order of SAR events')
    return bench,dict(case=case,wave=wave,portable_sha256=hashlib.sha256(bench).hexdigest(),
                      baseline_bench_sha256=BASE_DECK_SHA,comparison_window_ps=42,
                      trial_launch_to_compare_ps=21)


def verify():
    # Verify all original assets before attaching this process-local adapter.
    base.verify()
    verify_local()
    plan = common.read(PLAN)
    common.need(plan['schema']==SCHEMA and len(plan['cases'])==1, 'Wrong timing pilot plan')
    case, = plan['cases']
    build(case)
    return case


def verify_local():
    for line in MANIFEST.read_text(encoding='ascii').splitlines():
        digest,name = line.split('  ',1)
        path = ROOT/name
        common.need(path.resolve().is_relative_to(ROOT) and common.sha(path)==digest,
                    'Timing package file differs: '+name)


def attach_runner():
    # The immutable original runner uses module-level package bindings; configure
    # this separately loaded instance for the new one-case evidence root.
    base.build = build
    base.PLAN = PLAN
    base.MANIFEST = MANIFEST
    base.SCHEMA = SCHEMA


def summary(report):
    conversions = [row for row in report['conversions'] if row['scored']]
    common.need(len(conversions)==report['tested_conversions']==12, 'Expected all 12 SAR7 centers')
    trials = [trial for conv in conversions for trial in conv['trial_results']]
    unresolved = {str(bit):sum(trial['decision'] is None for trial in trials if trial['bit']==bit)
                  for bit in native.BITS}
    cm_changes = [1000*row['final_dac_common_mode_change_from_sample_V'] for row in conversions]
    prior = dict(job_id='759069',comp_window_ps=25,trial_launch_to_compare_ps=38,
                 unresolved_conversions=12,wrong_conversions=5,
                 unresolved_bits={'6':7,'5':8,'4':10,'3':12,'2':12,'1':12,'0':12},
                 final_cm_change_mV=[-111.8687372147853,-106.67895826015339])
    reference = dict(prior,tran_sha256='9ff38501a7c959565bc96a2738064bf7c5c4ed4e55840aa27527858fd6b8b884')
    return dict(status='measured',case_id=CASE_ID,baseline=reference,
                candidate=dict(job_id=report['slurm_task_id'],comp_window_ps=42,trial_launch_to_compare_ps=21,
                  unresolved_conversions=report['unresolved_conversions'],wrong_conversions=report['wrong_conversions'],
                  unresolved_bits=unresolved,final_cm_change_mV=[min(cm_changes),max(cm_changes)],
                  solver_seconds=report['solver_seconds'],raw_bytes=report['raw_bytes'],
                  max_abs_sample_error_lsb=report['max_abs_sample_error_lsb'],
                  max_observed_resolve_delay_s=report['max_observed_resolve_delay_s'],
                  tran_sha256=report['tran_sha256'],logic_smoke_pass=report['logic_smoke_pass']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('verify','approval-template','stage','run','collect-only'))
    parser.add_argument('--root',type=Path)
    parser.add_argument('--model-root',type=Path)
    parser.add_argument('--approval',type=Path)
    args = parser.parse_args()
    case = verify()
    _,meta = build(case)
    if args.mode=='verify':
        print(case['case_id'],meta['portable_sha256'])
        return
    common.need(args.root is not None and args.approval is not None, 'Provide isolated timing root and approval file')
    root = common.checked_root(args.root)
    common.need(root.name.startswith('pam4_sar7_timing_'), 'Use a new SAR7 timing pilot directory')
    attach_runner()
    approval = args.approval.absolute()
    common.need(approval.parent==root, 'Keep approval inside the timing campaign directory')
    if args.mode=='approval-template':
        common.write_new(approval,dict(approved=False,platform='Olympus',campaign=SCHEMA,
                       case_ids=[CASE_ID],design_source_sha256=common.sha(MANIFEST),authorized_run_root=str(root)))
        return
    common.need(common.read(approval).get('authorized_run_root')==str(root), 'Approval belongs to another run root')
    base.verify_approval(case,approval)
    if args.mode in ('stage','run'):
        common.need(args.model_root is not None, 'Use the same approved private kit')
        if args.mode=='stage':
            print(base.stage(root,case,args.model_root))
            return
        report = base.run(root,case,args.model_root,approval)
    else:
        report = base.collect(root,case)
    target = root/'sar7_timing_summary.json'
    record = summary(report)
    if target.exists():
        common.need(common.read(target)==record,'Existing timing summary differs')
    else:
        common.write_new(target,record)
    print(target)


if __name__=='__main__':
    main()
