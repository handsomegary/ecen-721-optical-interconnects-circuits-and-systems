"""Restore the original r5 differential source path in one SAR7 CML sense arm."""

import argparse
import copy
from functools import partial
import hashlib
import os
from pathlib import Path
import re
import statistics
import sys


ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT/'SHA256SUMS.txt'
PLAN = ROOT/'PLAN.json'
PARENT = Path(os.environ.get('PAM4_SAR7_RELAXED_PACKAGE',ROOT.parent/
    'PAM4_SAR7_RELAXED_PILOT_20261115')).resolve()
SCHEMA = 'pam4_sar7_r5_cml_rdeg_v1'
CASE_ID = 'sar7_07_tt_r5_cml_rdeg'
PARENT_DECK = 'ab1d631671e34660e96ec0fdec76b8f435db0a247ee857771eb70787a1eb12f3'
SENSE = ('sensep','sensen')
if hashlib.sha256((PARENT/'SHA256SUMS.txt').read_bytes()).hexdigest()!= (
        '7bb2bb49ccfa5f9498bcde4f8f5f7e92ef7729c4cc99bd7a733c94525ae71040'):
    raise ValueError('Unexpected relaxed timing package')
sys.path.insert(0,str(PARENT))
import sar7_relaxed as relaxed


base,common,native = relaxed.base,relaxed.common,relaxed.native


def reused_cml():
    ref = (base.review.R5/'quiet.scs').read_bytes()
    common.need(hashlib.sha256(ref).hexdigest()==native.R5_SHA256,'Unexpected r5 CML source')
    deck = ref.decode('ascii')
    pairs = (('VBANK','V_SENSE_DD','svdd 0'),('VNBIAS','V_SENSE_B','sbias 0'),
             ('RB0_Lp','RSENSE_P','svdd sensen'),('B0_Fp','MSENSE_P','sensen mp sem 0'),
             ('B0_Tp','MTAIL_P','sem sbias 0 0'),('RB0_Lm','RSENSE_N','svdd sensep'),
             ('B0_Fm','MSENSE_N','sensep mn sep 0'),('B0_Tm','MTAIL_N','sep sbias 0 0'),
             ('B0_RDEG','RSENSE_DEG','sem sep'))
    lines = []
    for prior,instance,nodes in pairs:
        body, = re.findall(r'^'+re.escape(prior)+r' \([^\r\n]*?\) ([^\r\n]+)\r?$',deck,re.M)
        lines.append(f'{instance} ({nodes}) {body}')
    return lines


def build(case):
    original, = common.read(relaxed.PLAN)['cases']
    common.need(case==dict(original,case_id=CASE_ID),'Expected the exact CML single-arm case')
    parent,meta = relaxed.build(original)
    common.need(meta['portable_sha256']==PARENT_DECK,'Unexpected SAR7 relaxed deck')
    rows = []
    changed = []
    added = reused_cml()
    for line in parent.decode('ascii').splitlines():
        if line.startswith('XCMP'):
            common.need(line.endswith(' SAR_CMP') and '(mp mn ' in line,'Unexpected comparator input pins')
            if not changed:
                rows.extend(added)
            changed.append(line.split()[0])
            line = line.replace('(mp mn ','(sensep sensen ')
        if line.startswith('save '):
            line += ' sensep sensen V_SENSE_DD:p'
        rows.append(line)
    common.need(set(changed)=={f'XCMP{b}' for b in range(7)} and len(changed)==7,
                'Expected seven comparator input pairs')
    wave = copy.deepcopy(meta['wave'])
    wave['saved_signals'].extend([*SENSE,'V_SENSE_DD:p'])
    for conversion in wave['conversions']:
        conversion['end_s'] += 3e-12
    bench = ('\n'.join(rows)+'\n').encode('ascii')
    return bench,dict(case=case,wave=wave,portable_sha256=hashlib.sha256(bench).hexdigest(),
                      comparator_sense='r5 CML W2 load 500 ohm, tail bias 0.5 V, source bridge 250 ohm; inverted legs swapped',
                      reference_bench_sha256=PARENT_DECK)


def verify():
    relaxed.verify()
    for line in MANIFEST.read_text(encoding='ascii').splitlines():
        digest,name = line.split('  ',1)
        path = ROOT/name
        common.need(path.resolve().is_relative_to(ROOT) and common.sha(path)==digest,'Package differs: '+name)
    plan = common.read(PLAN)
    common.need(plan['schema']==SCHEMA and len(plan['cases'])==1,'Expected a single physical sense arm')
    case, = plan['cases']
    return case,build(case)[1]


def measured_sense(directory,case):
    wave,status,hashes = base.evidence(case,directory)
    native_trace, = [r for r in status['raw_inventory'] if r['path'] in
                     ('raw/tranResponse.tran',base.review.RAW_NAME)]
    live = common.raw_inventory(directory)
    common.need(common.matches_historical_inventory(status['raw_inventory'],live),'Unexpected trace inventory')
    required = {'time',*SENSE,*wave['dac_pair'],'V_SENSE_DD:p'}
    raw = base.review.safe_raw(directory,dict(status,raw_inventory=live),
          native_trace['path'].removeprefix('raw/'),parser=partial(base.review.parse_selected,required=required))
    common.need(raw.unit('time')=='s','Expected seconds for CML trace')
    time,values = raw.values['time'],raw.values
    sensed = []
    for conversion in wave['conversions']:
        for trial in conversion['trials']:
            at = trial['pre_s']
            x,_ = base.score.differential(time,values,wave['dac_pair'],at)
            y,cm = base.score.differential(time,values,SENSE,at)
            amps = base.score.interpolate(time,values['V_SENSE_DD:p'],at)
            sensed.append(dict(index=conversion['index'],bit=trial['bit'],held_diff_V=x,
                               sense_diff_V=y,sense_common_mode_V=cm,supply_current_A=amps))
    inputs = [row['held_diff_V'] for row in sensed]
    outputs = [row['sense_diff_V'] for row in sensed]
    cms = [row['sense_common_mode_V'] for row in sensed]
    common.need(base.evidence(case,directory)[2]==hashes,'Execution changed during CML sense audit')
    agree = sum(x*y>0 for x,y in zip(inputs,outputs,strict=True))
    return dict(tran_sha256=raw.sha256,pairs=len(sensed),sign_agreement=agree,
                projected_gain=statistics.linear_regression(inputs,outputs).slope,
                sense_common_mode_range_V=[min(cms),max(cms)],
                mean_precomparison_supply_current_A=statistics.mean(row['supply_current_A'] for row in sensed),
                points=sensed)


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
    common.need(args.root is not None and args.approval is not None,'Provide isolated sense root and approval file')
    root = common.checked_root(args.root)
    common.need(root.name.startswith('pam4_sar7_cml_rdeg_'),'Use new CML sense run root')
    approval = args.approval.absolute()
    common.need(approval.parent==root,'Keep approval in campaign root')
    base.build,base.PLAN,base.MANIFEST,base.SCHEMA = build,PLAN,MANIFEST,SCHEMA
    expected = dict(approved=True,platform='Olympus',campaign=SCHEMA,case_ids=[CASE_ID],
                    authorized_run_root=str(root),design_source_sha256=common.sha(MANIFEST),
                    deck_sha256=meta['portable_sha256'])
    if args.mode=='approval-template':
        common.write_new(approval,dict(expected,approved=False))
        return
    common.need(common.read(approval)==expected,'Approval must bind new root, deck and manifest')
    if args.mode in ('stage','run'):
        common.need(args.model_root is not None,'Use existing verified private model root')
        if args.mode=='stage':
            print(base.stage(root,case,args.model_root))
            return
        report = base.run(root,case,args.model_root,approval)
    else:
        report = base.collect(root,case)
    observed = measured_sense(root/CASE_ID,case)
    common.need(report['tran_sha256']==observed['tran_sha256'],'Sense metric is from a different PSF')
    target = root/'sar7_cml_rdeg_summary.json'
    result = dict(relaxed.summarize(report),case_id=CASE_ID,baseline_job_id='760091',
                  ideal_sense_job_id='760132',uncoupled_cml_job_id='760254',sense=observed)
    if target.exists():
        common.need(common.read(target)==result,'Existing summary differs')
    else:
        common.write_new(target,result)
    print(target)


if __name__=='__main__':
    main()
