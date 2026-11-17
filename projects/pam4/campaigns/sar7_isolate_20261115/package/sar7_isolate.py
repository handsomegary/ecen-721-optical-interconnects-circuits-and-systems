"""Isolate comparator input loading in the measured relaxed SAR7 benchmark."""

import argparse
from functools import partial
import hashlib
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent
PARENT = Path(os.environ.get('PAM4_SAR7_RELAXED_PACKAGE',ROOT.parent/
    'PAM4_SAR7_RELAXED_PILOT_20261115')).resolve()
MANIFEST = ROOT/'SHA256SUMS.txt'
PLAN = ROOT/'PLAN.json'
SCHEMA = 'pam4_sar7_ideal_input_isolation_v1'
CASE_ID = 'sar7_04_tt_ideal_sense_isolation'
PARENT_DECK_SHA = 'ab1d631671e34660e96ec0fdec76b8f435db0a247ee857771eb70787a1eb12f3'
if hashlib.sha256((PARENT/'SHA256SUMS.txt').read_bytes()).hexdigest()!= (
        '7bb2bb49ccfa5f9498bcde4f8f5f7e92ef7729c4cc99bd7a733c94525ae71040'):
    raise ValueError('Unexpected relaxed timing dependency')
sys.path.insert(0,str(PARENT))
import sar7_relaxed as relaxed


base = relaxed.base
common = base.common
review = base.review
scorer = base.score


def build(case):
    original, = common.read(relaxed.PLAN)['cases']
    common.need(case==dict(original,case_id=CASE_ID),'Expected a single input-isolation arm')
    bench,meta = relaxed.build(original)
    common.need(meta['portable_sha256']==PARENT_DECK_SHA,'Unexpected relaxed circuit')
    changes = []
    result = []
    for line in bench.decode('ascii').splitlines():
        if line.startswith('XCMP'):
            common.need(line.endswith(' SAR_CMP') and line.count('(mp mn ')==1,
                        'Expected each comparator to load the original differential hold nodes')
            label = line.split()[0]
            if not changes:
                result.extend(('EISO_P (isop 0 mp 0) vcvs gain=1',
                               'EISO_N (ison 0 mn 0) vcvs gain=1'))
            changes.append(label)
            line = line.replace('(mp mn ','(isop ison ')
        result.append(line)
    common.need(set(changes)=={f'XCMP{b}' for b in range(7)} and len(changes)==7,
                'Expected exactly seven comparator input pairs')
    data = ('\n'.join(result)+'\n').encode('ascii')
    return data,dict(case=case,wave=meta['wave'],portable_sha256=hashlib.sha256(data).hexdigest(),
             reference_bench_sha256=PARENT_DECK_SHA,changed_comparators=changes,
             diagnostic_load='unloaded CDAC hold nodes with ideal unity drives for comparator gates')


def verify():
    ref,meta = relaxed.verify()
    common.need(meta['portable_sha256']==PARENT_DECK_SHA,'Relaxed baseline differs')
    for line in MANIFEST.read_text(encoding='ascii').splitlines():
        sha,name = line.split('  ',1)
        file = ROOT/name
        common.need(file.resolve().is_relative_to(ROOT) and common.sha(file)==sha,'Package differs: '+name)
    plan = common.read(PLAN)
    common.need(plan['schema']==SCHEMA and len(plan['cases'])==1,'Expected one isolation arm')
    case, = plan['cases']
    return ref,case,build(case)[1]


def bind(renderer,plan,manifest,schema):
    base.build,base.PLAN,base.MANIFEST,base.SCHEMA = renderer,plan,manifest,schema


def rails_table(values,wave):
    rows = []
    time = values['time']
    for conversion in wave['conversions']:
        data = []
        end = conversion['end_s']
        for trial,pair in zip(conversion['trials'],conversion['code_pairs'],strict=True):
            rails = lambda nodes,t: [scorer.interpolate(time,values[node],t) for node in nodes]
            original = rails(trial['cmp_pair'],trial['read_s'])
            final_q = rails(trial['cmp_pair'],end)
            final_out = rails(pair,end)
            vdd = wave['vdd_V']
            cmp_now = scorer.classify(*original,vdd)
            cmp_end = scorer.classify(*final_q,vdd)
            out = scorer.classify(*final_out,vdd)
            if cmp_now != cmp_end or out is None or out != cmp_end:
                data.append(dict(bit=trial['bit'],original_cmp=cmp_now,final_cmp=cmp_end,final_out=out,
                                 compare_read_V=original,compare_end_V=final_q,output_end_V=final_out))
        if data:
            rows.append(dict(index=conversion['index'],expected_code=conversion['expected_code'],bits=data))
    return rows


def audit(root,case):
    directory = root/case['case_id']
    with base.lock_case(directory):
        wave,status,hashes = base.evidence(case,directory)
        native, = [r for r in status['raw_inventory']
                   if r['path'] in ('raw/tranResponse.tran',review.RAW_NAME)]
        live = common.raw_inventory(directory)
        common.need(common.matches_historical_inventory(status['raw_inventory'],live),'Unexpected transient inventory')
        traces = {'time'}
        for conversion in wave['conversions']:
            traces.update(x for trial in conversion['trials'] for x in trial['cmp_pair'])
            traces.update(x for pair in conversion['code_pairs'] for x in pair)
        raw = review.safe_raw(directory,dict(status,raw_inventory=live),native['path'].removeprefix('raw/'),
                              parser=partial(review.parse_selected,required=traces))
        common.need(raw.unit('time')=='s' and raw.sha256==native['sha256'],'Unexpected native trace units or SHA')
        rows = rails_table(raw.values,wave)
        common.need(base.evidence(case,directory)[2]==hashes,'Execution inputs changed during rail audit')
        return dict(job_id=status['slurm_job_id'],tran_sha256=raw.sha256,rails_not_matching=rows)


def save(path,value):
    if path.exists():
        common.need(common.read(path)==value,'Existing output differs')
    else:
        common.write_new(path,value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('verify','approval-template','stage','run','collect-only','baseline-audit'))
    parser.add_argument('--root',type=Path)
    parser.add_argument('--baseline-root',type=Path)
    parser.add_argument('--approval',type=Path)
    parser.add_argument('--model-root',type=Path)
    args = parser.parse_args()
    ref,case,meta = verify()
    if args.mode=='verify':
        print(CASE_ID,meta['portable_sha256'])
        return
    common.need(args.root is not None,'Provide the isolated campaign root')
    root = common.checked_root(args.root)
    common.need(root.name.startswith('pam4_sar7_isolate_'),'Use a new isolated run root')
    if args.mode=='baseline-audit':
        common.need(args.baseline_root is not None,'Supply the completed relaxed diagnostic root')
        bind(relaxed.build,relaxed.PLAN,relaxed.MANIFEST,relaxed.SCHEMA)
        result = audit(args.baseline_root.resolve(strict=True),ref)
        common.need(result['job_id']=='760091','Expected the actual relaxed control')
        target = root/'sar7_760091_rail_audit.json'
        save(target,result)
        print(target)
        return
    common.need(args.approval is not None and args.approval.absolute().parent==root,'Keep approval inside root')
    approval = args.approval.absolute()
    bind(build,PLAN,MANIFEST,SCHEMA)
    expected = dict(approved=True,platform='Olympus',campaign=SCHEMA,case_ids=[CASE_ID],
                    design_source_sha256=common.sha(MANIFEST),authorized_run_root=str(root),
                    deck_sha256=meta['portable_sha256'])
    if args.mode=='approval-template':
        common.write_new(approval,dict(expected,approved=False))
        return
    common.need(common.read(approval)==expected,'Approval must bind the isolated diagnostic')
    if args.mode in ('stage','run'):
        common.need(args.model_root is not None,'Use the original private model root')
        if args.mode=='stage':
            print(base.stage(root,case,args.model_root))
            return
        report = base.run(root,case,args.model_root,approval)
    else:
        report = base.collect(root,case)
    result = relaxed.summarize(report)
    rail = audit(root,case)
    common.need(rail['tran_sha256']==report['tran_sha256'],'Rail audit differs from measured input')
    result.update(case_id=CASE_ID,baseline_job_id='760091',diagnostic_load=meta['diagnostic_load'],
                  baseline_final_cm_change_mV_approx=[-112.5,-109.1],**rail)
    target = root/'sar7_isolation_summary.json'
    save(target,result)
    print(target)


if __name__=='__main__':
    main()
