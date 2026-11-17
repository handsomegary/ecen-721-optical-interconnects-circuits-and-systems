"""Rebuild one completed case18 summary from existing evidence; zero solver/writes to source."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from types import FunctionType,SimpleNamespace

ROOT=Path(__file__).resolve().parent
MANIFEST=ROOT/'SHA256SUMS.txt'
PLAN=ROOT/'PLAN.json'
SCHEMA='pam4_sar7_read_overlap_collect_fix_v1'
PARENT=Path(os.environ.get('PAM4_SAR7_READ_OVERLAP_PACKAGE',ROOT.parent/'PAM4_SAR7_READ_OVERLAP_PILOT_20261117')).resolve()
SOURCE=dict(root_name='pam4_sar7_read_overlap_pilot_20261117.3abvDG',case_id='sar7_18_tt_175gs_read_overlap',job_id='761649',
    manifest_sha256='df3b60ef048c03175e2e07a0d02f5f971bd0840708b9ea85ac2235fff1e0079d',
    portable_sha256='63c73525a64b0136c66b2aa145da340386492ca5187082d295524213d2fe6aeb',
    authorization_sha256='ec86523474c7fb6a20bb5e2d806f31b12bed6d177060672e67ff0b08371a9fd8',
    measurements_sha256='1729b55e4f7ecbe8941bbde5826b9d22fe9125b413ff60728c55021ca64aad37',
    tran_sha256='a380f63b5e42532c98cfbf24f8352117c9c9a9e4080e314b4fc0abbfe2c6f69d',
    spectre_log_sha256='9a58539f46fe86b9b25a915fefc0882975f9232d6f07146bf266d89b36682211',
    staged_deck_sha256='cff34259f212d8c76ea342d06e7fef0ab7ae285cba5170b066eaf23462e7a3e4')
if hashlib.sha256((PARENT/'SHA256SUMS.txt').read_bytes()).hexdigest()!=SOURCE['manifest_sha256']:
    raise ValueError('Wrong immutable original case18 package')
sys.path.insert(0,str(PARENT))
import sar7_read_overlap as source

base,common=source.base,source.common
PLAN_RECORD=dict(schema=SCHEMA,source=SOURCE,modes=['verify','collect-only'],new_solver_jobs=0,new_raw_files=0,
    collector_cpus=1,collector_memory_GiB=6,collector_wall_minutes=10)
FILES={'sar7_read_overlap_collect_fix.py','sar7_read_overlap_collect_fix.sbatch',
       'test_sar7_read_overlap_collect_fix.py','PLAN.json','HANDOFF_zh_TW.md'}


def verify():
    common.need(common.read(PLAN)==PLAN_RECORD,'Frozen collector plan differs')
    entries=[line.split('  ',1) for line in MANIFEST.read_text(encoding='ascii').splitlines()]
    common.need(len(entries)==len(FILES) and {name for digest,name in entries}==FILES,'Unexpected collector inventory')
    for digest,name in entries:
        path=ROOT/name
        common.need(path.resolve().parent==ROOT and common.sha(path)==digest and b'\r' not in path.read_bytes(),
                    'Collector differs or is not LF text: '+name)
    common.need(b'\r' not in MANIFEST.read_bytes(),'Manifest must use LF')
    case,meta=source.verify()
    common.need(case['case_id']==SOURCE['case_id'] and common.sha(source.MANIFEST)==SOURCE['manifest_sha256']
        and meta['portable_sha256']==SOURCE['portable_sha256']
        and common.sha(source.AUTHORIZATION)==SOURCE['authorization_sha256'],'Original source package differs')
    return case,meta


def separate_paths(source_root,output):
    common.need(not output.is_relative_to(source_root) and not source_root.is_relative_to(output),
                'Collector output must be separate from original source')


def verify_bytes(content,expected,label):
    common.need(hashlib.sha256(content).hexdigest()==expected,'Original bytes differ: '+label)
    return content


def unchanged(before,after):
    common.need(before==after,'Original evidence changed during collect-only fix')


def b6_diagnostics(raw,wave):
    values=raw.values;time=values['time'];records=[]
    for cv in wave['conversions']:
        trial=next(t for t in cv['trials'] if t['bit']==6);points=[]
        for offset in (30,35,38,41):
            instant=trial['launch_s']+source.native.timing(offset)
            def at(node):return source.score.interpolate(time,values[node],instant)
            held,_=source.score.differential(time,values,wave['dac_pair'],instant)
            sense,_=source.score.differential(time,values,('sensep','sensen'),instant)
            points.append(dict(at_s=instant,ps_from_launch=offset,ps_from_compare=(instant-trial['compare_s'])/source.native.PS,
                held_lsb=held/wave['lsb_V'],sense_lsb=sense/wave['lsb_V'],
                xy_V=[at('XCMP6.x'),at('XCMP6.y')],raw_q_V=[at('q6p'),at('q6n')],
                clock_V=at('clk6'),trial_V=at('trial6')))
        records.append(dict(conversion=cv['index'],observations=points))
    return dict(label='Supplemental precompare observations only; no timing plan or score changes',b6=records)


def fixed_summarize(report,root,case,meta):
    """Clone only function contexts. No original module/global/threshold is changed."""
    wave=meta['wave']
    expanded=set(source.parent.EXTRA_SAVES)|set(wave['saved_signals'])|{'time'}
    expanded.update(f'{prefix}{bit}' for prefix in ('trial','clk') for bit in source.native.BITS)
    proof=dict(psf_parse_count=0,selected_required=[])
    original_review=base.review
    def admitted_raw(*args,parser=None,**kwargs):
        common.need(parser is not None,'Use the original selected PSF parser')
        required=set(parser.keywords['required'])
        common.need(expanded<=required,'Required saved signal expansion is incomplete')
        proof['selected_required']=sorted(required)
        def once(*parser_args,**parser_kwargs):
            proof['psf_parse_count']+=1
            common.need(proof['psf_parse_count']==1,'Only one existing PSF parse is permitted')
            return parser(*parser_args,**parser_kwargs)
        raw=original_review.safe_raw(*args,parser=once,**kwargs)
        proof['supplemental_diagnostics']=b6_diagnostics(raw,wave)
        return raw
    review_proxy=SimpleNamespace(**vars(original_review));review_proxy.safe_raw=admitted_raw
    base_proxy=SimpleNamespace(**vars(base));base_proxy.review=review_proxy
    q_context=dict(source.parent.summarize.__globals__)
    q_context.update(EXTRA_SAVES=tuple(sorted(expanded)),base=base_proxy)
    q_summary=FunctionType(source.parent.summarize.__code__,q_context)
    child_context=dict(source.summarize.__globals__)
    child_context['parent']=SimpleNamespace(summarize=q_summary)
    summarize=FunctionType(source.summarize.__code__,child_context)
    result=summarize(report,root,case,meta)
    common.need(proof['psf_parse_count']==1,'Expected exactly one retained PSF parse')
    return result,proof


def source_snapshot(root,case,meta):
    directory=root/case['case_id']
    wave,status,hashes=base.evidence(case,directory)
    report_path=common.owned_file(directory,directory/base.MEASUREMENT)[0]
    report_bytes=verify_bytes(report_path.read_bytes(),SOURCE['measurements_sha256'],'measurements')
    report=json.loads(report_bytes.decode('utf-8-sig'))
    approval_path=common.owned_file(root,root/'approval.json')[0]
    approval_bytes=approval_path.read_bytes()
    common.need(json.loads(approval_bytes.decode('utf-8-sig'))==source.approval_record(root,meta,True),'Original exact approval differs')
    inventory=common.raw_inventory(directory)
    traces=[row for row in inventory if row['path'] in ('raw/tranResponse.tran',base.review.RAW_NAME)]
    common.need(len(traces)==1 and traces[0]['sha256']==SOURCE['tran_sha256']
        and common.matches_historical_inventory(status['raw_inventory'],inventory),'Original transient/inventory differs')
    common.need(status['slurm_job_id']==report['slurm_task_id']==SOURCE['job_id'] and report['case']==case
        and report['status']=='measured' and report['execution_files_sha256']==hashes
        and report['tran_sha256']==SOURCE['tran_sha256'] and wave==meta['wave']
        and hashes['bench.scs']==SOURCE['staged_deck_sha256'] and hashes['spectre.log']==SOURCE['spectre_log_sha256'],
        'Original completed run provenance differs')
    files={name:dict(sha256=digest,bytes=(directory/name).stat().st_size) for name,digest in hashes.items()}
    files['measurements.json']=dict(sha256=hashlib.sha256(report_bytes).hexdigest(),bytes=len(report_bytes))
    files['root/approval.json']=dict(sha256=hashlib.sha256(approval_bytes).hexdigest(),bytes=len(approval_bytes))
    return report,dict(execution_and_report_bytes=files,raw_inventory=inventory)


def collect_only(root,output,case,meta):
    root=root.absolute()
    common.need(root==root.resolve(strict=True) and root.is_dir() and root.name==SOURCE['root_name'],'Use exact original completed case18 root')
    separate_paths(root,output)
    saved=base.build,base.PLAN,base.MANIFEST,base.SCHEMA
    try:
        base.build,base.PLAN,base.MANIFEST,base.SCHEMA=source.build,source.PLAN,source.MANIFEST,source.SCHEMA
        report,before=source_snapshot(root,case,meta)
        result,parser_proof=fixed_summarize(report,root,case,meta)
        _,after=source_snapshot(root,case,meta);unchanged(before,after)
    finally:base.build,base.PLAN,base.MANIFEST,base.SCHEMA=saved
    receipt=dict(schema=SCHEMA,source=SOURCE,collector_manifest_sha256=common.sha(MANIFEST),
        original_case_schema=source.SCHEMA,original_formal_readout_ps=565,
        original_report_and_raw_unchanged=True,new_solver_jobs=0,new_raw_files=0,source_writes=0,
        supplemental_diagnostics=parser_proof.pop('supplemental_diagnostics'),
        parser=parser_proof,source_before=before,source_after=after,
        limits='All original scoring and72-boundary helper functions are unchanged; only selected PSF signal admission expands')
    return result,receipt


def save_identical(path,value):
    if path.exists():common.need(common.read(path)==value,'Existing collector output differs')
    else:common.write_new(path,value)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('verify','collect-only'))
    parser.add_argument('--source-root',type=Path);parser.add_argument('--output-root',type=Path)
    args=parser.parse_args();case,meta=verify()
    if args.mode=='verify':print('Immutable case18 verified; collect-only, zero solver');return
    common.need(args.source_root is not None and args.output_root is not None,'Supply original source and separate new collector root')
    output=common.checked_root(args.output_root)
    common.need(output.name.startswith('pam4_sar7_read_overlap_collect_fix_'),'Use a fresh collector output root')
    summary,receipt=collect_only(args.source_root,output,case,meta)
    for filename,value in [('sar7_read_overlap_summary.json',summary),('sar7_read_overlap_collect_fix_receipt.json',receipt)]:
        path=output/filename;save_identical(path,value);print(path.name,common.sha(path))


if __name__=='__main__':main()
