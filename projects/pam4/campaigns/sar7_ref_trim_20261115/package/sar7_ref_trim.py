"""Test one data-derived CDAC reference trim on the direct, relaxed SAR7 circuit."""

import argparse
import copy
import hashlib
import os
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT/'SHA256SUMS.txt'
PLAN = ROOT/'PLAN.json'
PARENT = Path(os.environ.get('PAM4_SAR7_RELAXED_PACKAGE',ROOT.parent/
    'PAM4_SAR7_RELAXED_PILOT_20261115')).resolve()
SCHEMA = 'pam4_sar7_relaxed_reference_span_v1'
CASE_ID = 'sar7_05_tt_ref_trim'
PARENT_DECK = 'ab1d631671e34660e96ec0fdec76b8f435db0a247ee857771eb70787a1eb12f3'
AUDIT_SHA = 'e7d7e006c6d7b5455b501aae2afaf338df5891b47302946995d24410aa3c58b7'
SCALE = 127/107.16
READ_SHIFT_S = 3e-12
if hashlib.sha256((PARENT/'SHA256SUMS.txt').read_bytes()).hexdigest()!= (
        '7bb2bb49ccfa5f9498bcde4f8f5f7e92ef7729c4cc99bd7a733c94525ae71040'):
    raise ValueError('Unexpected relaxed timing package')
sys.path.insert(0,str(PARENT))
import sar7_relaxed as relaxed


base,common = relaxed.base,relaxed.common
REFERENCE = re.compile(rb'(?m)^(V_R(?:HI|LO) \(r(?:hi|lo) 0\) vsource dc=)(\S+)$')


def build(case):
    original, = common.read(relaxed.PLAN)['cases']
    common.need(case==dict(original,case_id=CASE_ID),'Expected the same relaxed CDAC input conditions')
    bench,meta = relaxed.build(original)
    common.need(meta['portable_sha256']==PARENT_DECK,'Unexpected relaxed bench')
    reference = REFERENCE.findall(bench)
    common.need(len(reference)==2 and reference[0][0].startswith(b'V_RHI')
                and reference[1][0].startswith(b'V_RLO'),'Unexpected reference sources')
    high,low = (float(row[1]) for row in reference)
    prior = high-low
    middle = (high+low)/2
    common.need(abs(middle-.45)<1e-12 and prior>0,'Unexpected CDAC reference midpoint or span')
    result,count = REFERENCE.subn(lambda m:m[1]+relaxed.native.number(
                       middle+(float(m[2])-middle)*SCALE).encode('ascii'),bench)
    common.need(count==2,'Expected only two trimmed reference sources')
    wave = copy.deepcopy(meta['wave'])
    wave['reference_span_before_trim_V'] = prior
    wave['nominal_reference_span_V'] = prior*SCALE
    for conversion in wave['conversions']:
        conversion['end_s'] += READ_SHIFT_S
    return result,dict(case=case,wave=wave,portable_sha256=hashlib.sha256(result).hexdigest(),
                      reference_bench_sha256=PARENT_DECK,weight_audit_sha256=AUDIT_SHA,
                      measured_direct_span_lsb=107.16,span_scale=SCALE,final_read_shift_s=READ_SHIFT_S)


def verify():
    relaxed.verify()
    for line in MANIFEST.read_text(encoding='ascii').splitlines():
        digest,name = line.split('  ',1)
        path = ROOT/name
        common.need(path.resolve().is_relative_to(ROOT) and common.sha(path)==digest,'Package differs: '+name)
    plan = common.read(PLAN)
    common.need(plan['schema']==SCHEMA and len(plan['cases'])==1,'Expected a single Vref control')
    case, = plan['cases']
    return case,build(case)[1]


def summarize(report):
    result = relaxed.summarize(report)
    codes = result['codes']
    absolute = [abs(row['comparator']-row['expected']) for row in codes if row['comparator'] is not None]
    return dict(result,case_id=CASE_ID,baseline_job_id='760091',full_scale_trim=SCALE,
                baseline_audit_sha256=AUDIT_SHA,final_read_shift_s=READ_SHIFT_S,
                all_comparator_codes_available=len(absolute)==12,
                sum_abs_comparator_code_error=sum(absolute) if absolute else None,
                max_abs_comparator_code_error=max(absolute,default=None),
                registered_codes_undetermined=sum(row['registered'] is None for row in codes))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('verify','approval-template','stage','run','collect-only'))
    parser.add_argument('--root',type=Path)
    parser.add_argument('--approval',type=Path)
    parser.add_argument('--model-root',type=Path)
    args = parser.parse_args()
    case,meta = verify()
    if args.mode=='verify':
        print(CASE_ID,meta['portable_sha256'],meta['wave']['nominal_reference_span_V'])
        return
    common.need(args.root is not None and args.approval is not None,'Provide isolated trim root and approval file')
    root = common.checked_root(args.root)
    common.need(root.name.startswith('pam4_sar7_ref_trim_'),'Use new reference-trim run root')
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
    target = root/'sar7_ref_trim_summary.json'
    result = summarize(report)
    if target.exists():
        common.need(common.read(target)==result,'Existing summary differs')
    else:
        common.write_new(target,result)
    print(target)


if __name__=='__main__':
    main()
