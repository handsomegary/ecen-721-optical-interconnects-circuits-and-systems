"""Run two independent bounded SAR7 load/threshold probes with a measured gate."""

import argparse
import copy
from datetime import datetime, timezone
from functools import partial
import hashlib
import json
import math
import os
from pathlib import Path
import re
import statistics
import subprocess
import sys


ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT/'SHA256SUMS.txt'
PLAN = ROOT/'PLAN.json'
SCHEMA = 'pam4_sar7_offset_pilot_v1'
PARENT = Path(os.environ.get('PAM4_SAR7_CDAC_FIX_PACKAGE', ROOT.parent/
    'PAM4_SAR7_CDAC_FIX_20261116')).resolve()
PARENT_MANIFEST_SHA256 = 'bb97b973466cc63a8d6c282b7ab142e35b4af911e107d01da0efa51ef3005153'
BASELINE_PORTABLE_SHA256 = 'f2231b54d5138538c57102e5cd25dcc1047829ed71f02d79ab3d37d5726a6153'
BASELINE_CASE_ID = 'sar7_09_tt_cml_main_ratio'
EXPIRES_AT_UTC = '2026-11-17T05:15:00Z'
EXPIRES = datetime(2026,11,17,5,15,tzinfo=timezone.utc)
PROBE_OFFSETS_PS = (0.,.25,.5,1.,2.,5.,15.,30.,50.,60.)
SUMMARY = 'sar7_offset_pilot_summary.json'
STAGE_PROOF = 'stage_authorization.json'
if hashlib.sha256((PARENT/'SHA256SUMS.txt').read_bytes()).hexdigest()!=PARENT_MANIFEST_SHA256:
    raise ValueError('Unexpected frozen CDAC correction package')
sys.path.insert(0,str(PARENT))
import sar7_cdac_fix as parent

base,common,native = parent.base,parent.common,parent.native
scorer = base.score
_PARENTS = (base.build,base.PLAN,base.MANIFEST,base.SCHEMA)
_ORIGINAL_STAGE = base.stage
INTERNAL_PAIRS = {str(bit):[f'XCMP{bit}.x',f'XCMP{bit}.y'] for bit in range(6,-1,-1)}


def utcnow():
    return datetime.now(timezone.utc)


def original_case():
    case = parent.plan_cases()[1]
    common.need(case['case_id']==BASELINE_CASE_ID,'Wrong baseline case')
    return case


def plan_cases():
    plan = common.read(PLAN)
    common.need(plan.get('schema')==SCHEMA and 1<=len(plan.get('cases',[]))<=2,
                'Expected one or two independent offset pilot cases')
    common.need(set(plan)<={'schema','cases','provenance'},'Unexpected plan fields')
    old = original_case()
    cases = plan['cases']
    common.need(len({case['case_id'] for case in cases})==len(cases),'Duplicate pilot case ID')
    for index,case in enumerate(cases):
        common.need(set(case)==set(old)|{'offset_fix'},'Unexpected offset case fields')
        common.need(re.fullmatch(r'sar7_[A-Za-z0-9_]+',case['case_id']) is not None
                    and case['case_id']!=BASELINE_CASE_ID,'Use a new simple case ID')
        common.need({k:case[k] for k in old if k!='case_id'}=={k:old[k] for k in old if k!='case_id'},
                    'Keep every original input and CDAC correction unchanged')
        expected = (dict(kind='matched_complement_load') if index==0 else
                    dict(kind='balanced_cml_load_trim',rsense_p_ohm=498.5,rsense_n_ohm=501.5))
        common.need(case['offset_fix']==expected,'Use only the two fixed independent pilot changes')
    return cases


def confirm_internal_nodes():
    cells,_ = native.read_cdf(base.review.R5/'quiet.scs')
    for output,node in (('bx','x'),('by','y')):
        matches=[]
        for line in cells:
            match=re.fullmatch(r'\w+ \(([^)]*)\) (\S+) (.*)',line)
            common.need(match is not None,'Unexpected native comparator device')
            pins=match[1].split()
            if len(pins)==4 and pins[0]==output and pins[1]==node:
                matches.append(match[2])
        common.need(len(matches)==2 and any(m.startswith('nmos') for m in matches)
                    and any(m.startswith('pmos') for m in matches),'Internal probe must precede the buffered outputs')


def build(case):
    cases=plan_cases()
    common.need(case in cases,'Case must exactly match the frozen offset plan')
    old=original_case()
    source,old_meta=parent.build(old)
    common.need(old_meta['portable_sha256']==BASELINE_PORTABLE_SHA256,'Wrong completed760874 portable baseline')
    confirm_internal_nodes()
    kind=case['offset_fix']['kind']
    rows,changed,real,loads=[],[],set(),set()
    probes=[node for pair in INTERNAL_PAIRS.values() for node in pair]
    save_count=0
    for line in source.decode('ascii').splitlines():
        label=line.split()[0] if line.split() else ''
        out=line
        if label in ('RSENSE_P','RSENSE_N') and kind=='balanced_cml_load_trim':
            key='rsense_p_ohm' if label=='RSENSE_P' else 'rsense_n_ohm'
            common.need(line.endswith(' resistor r=500'),'Unexpected original sense load')
            out,count=re.subn(r'\br=\S+','r='+native.number(case['offset_fix'][key]),line)
            common.need(count==1,'Unexpected sense resistor card')
            loads.add(label)
            changed.append(label)
        if line.startswith('save '):
            out+=' '+' '.join(probes)
            save_count+=1
            changed.append('save')
        rows.append(out)
        match=re.fullmatch(r'XBitb([0-6]) \(trial\1 q\1p bit\1b vdd\) SAR_NOR',line)
        if match:
            bit=int(match[1]);real.add(bit)
            if kind=='matched_complement_load':
                label=f'XQCOMPLOAD{bit}'
                rows.append(f'{label} (trial{bit} q{bit}n dqload{bit} vdd) SAR_NOR')
                changed.append(label)
    common.need(real==set(range(7)) and save_count==1,'Expected the original seven control NOR gates and one save')
    if kind=='balanced_cml_load_trim':
        common.need(loads=={'RSENSE_P','RSENSE_N'},'Expected exactly two changed loads')
    wave=copy.deepcopy(old_meta['wave'])
    common.need(not any(node in wave['saved_signals'] for node in probes),'Internal probes already exist')
    wave['saved_signals'].extend(probes)
    wave['internal_regeneration_pairs']=copy.deepcopy(INTERNAL_PAIRS)
    wave['internal_regeneration_sign']='x-minus-y; buffered positive-minus-negative is inverted'
    bench=('\n'.join(rows)+'\n').encode('ascii')
    return bench,dict(case=case,wave=wave,portable_sha256=hashlib.sha256(bench).hexdigest(),
                      parent_case_id=BASELINE_CASE_ID,parent_manifest_sha256=PARENT_MANIFEST_SHA256,
                      reference_bench_sha256=BASELINE_PORTABLE_SHA256,
                      offset_fix=copy.deepcopy(case['offset_fix']),changed_labels=changed)


def verify():
    common.need(hashlib.sha256((PARENT/'SHA256SUMS.txt').read_bytes()).hexdigest()==PARENT_MANIFEST_SHA256,
                'Frozen parent package differs')
    saved=(base.build,base.PLAN,base.MANIFEST,base.SCHEMA)
    try:
        base.build,base.PLAN,base.MANIFEST,base.SCHEMA=_PARENTS
        checked=parent.verify()
    finally:
        base.build,base.PLAN,base.MANIFEST,base.SCHEMA=saved
    common.need(len(checked)==2 and checked[1][0]==original_case()
                and checked[1][1]['portable_sha256']==BASELINE_PORTABLE_SHA256,'Wrong parent index1')
    lines=MANIFEST.read_text(encoding='ascii').splitlines()
    common.need(bool(lines),'Empty pilot manifest')
    for line in lines:
        digest,name=line.split('  ',1);path=ROOT/name
        common.need(path.resolve().is_relative_to(ROOT) and common.sha(path)==digest,'Pilot package differs: '+name)
    return [(case,build(case)[1]) for case in plan_cases()]


def bind():
    base.build,base.PLAN,base.MANIFEST,base.SCHEMA=build,PLAN,MANIFEST,SCHEMA
    base.TIMEOUT_S=540


def expected_approval(root,verified):
    return dict(approved=True,platform='Olympus',campaign=SCHEMA,
        case_ids=[case['case_id'] for case,meta in verified],authorized_run_root=str(root),
        design_source_sha256=common.sha(MANIFEST),
        deck_sha256_by_case={case['case_id']:meta['portable_sha256'] for case,meta in verified},
        authorization_expires_at_utc=EXPIRES_AT_UTC)


def error_metrics(rows, channel):
    values = [row[channel] for row in rows]
    errors = [value-row['expected_code'] for value, row in zip(values, rows, strict=True)
              if isinstance(value, int) and not isinstance(value, bool)]
    return dict(available=len(errors), missing=len(rows)-len(errors),
                wrong=sum(value != row['expected_code'] for value, row in zip(values, rows, strict=True)
                          if isinstance(value, int) and not isinstance(value, bool)),
                sum_abs_code_error=sum(abs(error) for error in errors),
                max_abs_code_error=max(map(abs, errors), default=None))


def summarize(report, sense, root, index, case):
    scored = [row for row in report['conversions'] if row['scored']]
    common.need(len(scored) == report['tested_conversions'] == 12, 'Expected twelve fixed code centers')
    common.need([row['expected_code'] for row in scored] == case['pattern_codes'], 'Changed scoring inputs')
    trials = [trial for row in scored for trial in row['trial_results']]
    common.need(len(trials) == 84 and all(len(row['trial_results']) == 7 for row in scored),
                'Expected all 84 comparison records')
    common.need(report['case'] == case and sense['pairs'] == 84
                and sense['tran_sha256'] == report['tran_sha256'], 'Mismatched case or sense evidence')
    comparator = error_metrics(scored, 'observed_comparator_code')
    registered = error_metrics(scored, 'observed_registered_code')
    missing = comparator['missing']+registered['missing']
    consistent = all(row['observed_comparator_code'] == row['observed_registered_code']
                     for row in scored if row['observed_comparator_code'] is not None
                     and row['observed_registered_code'] is not None)
    unresolved = {str(bit): sum(trial['decision'] is None for trial in trials if trial['bit'] == bit)
                  for bit in native.BITS}
    cm = [1000*row['final_dac_common_mode_change_from_sample_V'] for row in scored]
    directory = root/case['case_id']
    return dict(schema=SCHEMA, status='measured', index=index, case_id=case['case_id'],
                parent_case_id=BASELINE_CASE_ID, job_id=report['slurm_task_id'], tested_conversions=12,
                comparison_records=84, unresolved_bits=unresolved,
                unresolved_bits_total=sum(unresolved.values()), comparator=comparator, registered=registered,
                registered_available_consistency=consistent,
                valid=(missing == 0 and consistent and not any(unresolved.values())),
                final_cm_change_mV=[min(cm), max(cm)],
                max_abs_sample_error_lsb=report['max_abs_sample_error_lsb'],
                max_observed_resolve_delay_s=report['max_observed_resolve_delay_s'],
                logic_smoke_pass=report['logic_smoke_pass'], solver_seconds=report['solver_seconds'],
                raw_bytes=report['raw_bytes'], tran_sha256=report['tran_sha256'], offset_fix=copy.deepcopy(case['offset_fix']),
                codes=[dict(index=row.get('index', i), expected=row['expected_code'],
                            comparator=row['observed_comparator_code'], registered=row['observed_registered_code'])
                       for i, row in enumerate(scored)], sense=sense,
                provenance=dict(manifest_sha256=common.sha(MANIFEST),
                                portable_deck_sha256=build(case)[1]['portable_sha256'],
                                measurements_sha256=common.sha(directory/base.MEASUREMENT),
                                run_status_sha256=common.sha(directory/'run_status.json'),
                                execution_files_sha256=report['execution_files_sha256']))


def summary_path(root, case):
    return root/case['case_id']/SUMMARY


def read_existing_report(root, case):
    directory = root/case['case_id']
    # Gate/summary cannot silently manufacture a missing original measurement.
    for name in (base.MEASUREMENT, 'run_status.json'):
        common.owned_file(directory, directory/name)
    return base.collect(root, case)


def threshold_bracket(points, field, lsb):
    zero=[p[field]/lsb for p in points if p['decision']==0]
    one=[p[field]/lsb for p in points if p['decision']==1]
    lower=max(zero) if zero else None
    upper=min(one) if one else None
    return dict(zero_decisions=len(zero),one_decisions=len(one),
                largest_zero_input_LSB=lower,smallest_one_input_LSB=upper,
                constant_threshold_feasible=lower is None or upper is None or lower<upper,
                interval_convention='lower open, upper closed; descriptive finite-data bracket, not offset/noise calibration')


def measured_probe(directory,case,report):
    wave,status,hashes=base.evidence(case,directory)
    traces=[item for item in status['raw_inventory'] if item['path'] in
            ('raw/tranResponse.tran',base.review.RAW_NAME)]
    common.need(len(traces)==1,'Expected one native retained transient')
    live=common.raw_inventory(directory)
    common.need(common.matches_historical_inventory(status['raw_inventory'],live),'Retained transient differs')
    probes={node for pair in INTERNAL_PAIRS.values() for node in pair}
    required=set(scorer.required_traces(wave))|set(parent.pilot.SENSE)|probes|{'V_SENSE_DD:p'}
    raw=base.review.safe_raw(directory,dict(status,raw_inventory=live),
        traces[0]['path'].removeprefix('raw/'),parser=partial(base.review.parse_selected,required=required))
    common.need(raw.unit('time')=='s' and raw.sweep_names==['time']
                and raw.sha256==report['tran_sha256'],'Probe is not from the original measured PSF')
    scorer.validate_trace_arrays(raw.values,required,wave['stop_s'],wave.get('strobe_s',0.))
    values,time=raw.values,raw.values['time']
    scored={row['index']:row for row in report['conversions'] if row['scored']}
    points,dynamics=[],None
    def pair_voltage(pair,at):
        return [scorer.interpolate(time,values[node],at) for node in pair]
    def observe(conversion,trial,at):
        held,held_cm=scorer.differential(time,values,wave['dac_pair'],at)
        sense,sense_cm=scorer.differential(time,values,parent.pilot.SENSE,at)
        internal=pair_voltage(INTERNAL_PAIRS[str(trial['bit'])],at)
        buffered=pair_voltage(trial['cmp_pair'],at)
        return dict(at_s=at,held_diff_V=held,held_common_mode_V=held_cm,
                    sense_diff_V=sense,sense_common_mode_V=sense_cm,
                    internal_x_y_V=internal,internal_x_minus_y_V=internal[0]-internal[1],
                    buffered_positive_negative_V=buffered,buffered_diff_V=buffered[0]-buffered[1],
                    buffered_class=scorer.classify(*buffered,wave['vdd_V']))
    for conversion in wave['conversions']:
        original={t['bit']:t for t in scored[conversion['index']]['trial_results']}
        for trial in conversion['trials']:
            pre=observe(conversion,trial,trial['pre_s'])
            read=observe(conversion,trial,trial['read_s'])
            decision=original[trial['bit']]['decision']
            common.need(read['buffered_class']==decision,'Probe changed the original read classification')
            current=scorer.interpolate(time,values['V_SENSE_DD:p'],trial['pre_s'])
            points.append(dict(index=conversion['index'],bit=trial['bit'],decision=decision,
                               supply_current_A=current,**pre))
            if conversion['index']==8 and trial['bit']==2:
                samples=[dict(offset_from_compare_ps=(trial['pre_s']-trial['compare_s'])/1e-12,
                              label='original_pre',**pre)]
                for offset in PROBE_OFFSETS_PS:
                    at=trial['compare_s']+offset*1e-12
                    if at>trial['read_s'] and not math.isclose(at,trial['read_s'],rel_tol=0.,abs_tol=1e-21):
                        continue
                    samples.append(dict(offset_from_compare_ps=offset,label='retained_interpolation',
                                        **observe(conversion,trial,min(at,trial['read_s']))))
                dynamics=dict(index=8,bit=2,expected_bit=original[2]['expected_bit'],decision=decision,
                    compare_s=trial['compare_s'],read_s=trial['read_s'],observations=samples)
    common.need(len(points)==84 and dynamics is not None,'Expected84precomparison points and index8bit2')
    xs=[point['held_diff_V'] for point in points]
    ys=[point['sense_diff_V'] for point in points]
    line=statistics.linear_regression(xs,ys)
    cm=[point['sense_common_mode_V'] for point in points]
    residuals=[y-line.slope*x-line.intercept for x,y in zip(xs,ys,strict=True)]
    sense=dict(tran_sha256=raw.sha256,pairs=84,sign_agreement=sum(x*y>0 for x,y in zip(xs,ys,strict=True)),
        projected_gain=line.slope,sense_common_mode_range_V=[min(cm),max(cm)],
        mean_precomparison_supply_current_A=statistics.mean(point['supply_current_A'] for point in points),points=points)
    signs={}
    for field in ('held_diff_V','sense_diff_V'):
        available=[p for p in points if p['decision'] is not None and p[field]!=0]
        mismatches=[dict(index=p['index'],bit=p['bit'],decision=p['decision'],pre_diff_V=p[field])
                    for p in available if int(p[field]>0)!=p['decision']]
        signs[field]=dict(available=len(available),agrees=len(available)-len(mismatches),
                          disagrees=len(mismatches),disagreement_records=mismatches)
    affine=dict(slope_V_per_V=line.slope,output_intercept_V=line.intercept,
                output_rmse_V=math.sqrt(statistics.mean(r*r for r in residuals)),
                sense_stage_zero_crossing_input_LSB=None if line.slope==0 else
                    -line.intercept/line.slope/wave['lsb_V'],
                label='Sense-stage affine zero crossing, not comparator offset')
    brackets={str(bit):threshold_bracket([p for p in points if p['bit']==bit],
                                        'sense_diff_V',wave['lsb_V']) for bit in range(6,-1,-1)}
    common.need(base.evidence(case,directory)[2]==hashes and common.raw_inventory(directory)==live,
                'Execution evidence or PSF changed during probing')
    return dict(sense=sense,sense_affine=affine,decision_vs_pre_sign=signs,
        per_bit_sense_threshold_brackets=brackets,
        common_sense_threshold_bracket=threshold_bracket(points,'sense_diff_V',wave['lsb_V']),
        index8_bit2_dynamics=dynamics,
        probe_limits=['Saved x/y are internal regeneration nodes; q outputs are buffered and inverted',
                      'Finite deterministic input points do not measure noise or establish constant per-bit offsets',
                      'Interpolation uses existing saved points and does not alter clocks or scoring'])


def complete_summary(report,root,index,case):
    probe=measured_probe(root/case['case_id'],case,report)
    result=summarize(report,probe.pop('sense'),root,index,case)
    result.update(probe)
    return result


def write_summary(root,index,case,report):
    result=complete_summary(report,root,index,case)
    target=summary_path(root,case)
    if target.exists():
        common.need(common.read(target)==result,'Existing offset summary differs')
    else:
        common.write_new(target,result)
    digest=common.sha(target)
    sidecar=target.with_suffix('.json.sha256')
    record=dict(sha256=digest,filename=target.name)
    if sidecar.exists():
        common.need(common.read(sidecar)==record,'Offset summary SHA differs')
    else:
        common.write_new(sidecar,record)
    return result,digest


def gate_recommendation(summary):
    valid=summary['valid']
    cm_ok=max(map(abs,summary['final_cm_change_mV']))<=10
    peaks=[summary[channel]['max_abs_code_error'] for channel in ('comparator','registered')]
    peak=max(peaks) if all(p is not None for p in peaks) else None
    total=max(summary[channel]['sum_abs_code_error'] for channel in ('comparator','registered'))
    if valid and cm_ok and peak<=1:
        recommendation='STOP_TARGET'
    elif valid and cm_ok and peak<=2 and total<=7:
        recommendation='ALLOW_INDEX1'
    else:
        recommendation='STOP_REVIEW'
    return dict(recommendation=recommendation,valid=valid,cdac_cm_within_10mV=cm_ok,
                max_abs_code_error=peak,sum_abs_code_error=total)


def measured_gate(root,cases):
    case=cases[0]
    target=summary_path(root,case)
    common.owned_file(root/case['case_id'],target)
    sidecar=target.with_suffix('.json.sha256')
    common.owned_file(root/case['case_id'],sidecar)
    report=read_existing_report(root,case)
    expected=complete_summary(report,root,0,case)
    common.need(common.read(target)==expected,'Case zero summary is not its measured evidence')
    digest=common.sha(target)
    common.need(common.read(sidecar)==dict(sha256=digest,filename=target.name),'Case zero summary SHA differs')
    return dict(gate_recommendation(expected),source_case_id=case['case_id'],source_summary_sha256=digest,
                source_tran_sha256=report['tran_sha256'],
                source_measurements_sha256=common.sha(root/case['case_id']/base.MEASUREMENT),
                manifest_sha256=common.sha(MANIFEST))


def require_index1_gate(root,cases):
    result=measured_gate(root,cases)
    common.need(result['recommendation']=='ALLOW_INDEX1','Index one forbidden by measured gate: '+result['recommendation'])
    target=root/'index1_gate.json'
    if target.exists():
        common.need(common.read(target)==result,'Existing index one gate differs')
    else:
        common.write_new(target,result)
    return result


def stage_proof_fields(root,case,directory):
    return dict(schema='pam4_sar7_offset_stage_authorization_v1',case_id=case['case_id'],
                campaign=SCHEMA,authorized_run_root=str(root),authorization_expires_at_utc=EXPIRES_AT_UTC,
                design_source_sha256=common.sha(MANIFEST),portable_deck_sha256=build(case)[1]['portable_sha256'],
                staged_bench_sha256=common.sha(directory/'bench.scs'),
                case_json_sha256=common.sha(directory/'case.json'))


def validate_stage_proof(proof,expected,now):
    common.need(set(proof)==set(expected)|{'authorized_at_utc'},'Unexpected stage authorization fields')
    common.need(all(proof[key]==value for key,value in expected.items()),'Stage authorization differs')
    try:
        authorized=datetime.fromisoformat(proof['authorized_at_utc'].replace('Z','+00:00'))
    except (TypeError,ValueError):
        raise ValueError('Invalid stage authorization timestamp') from None
    common.need(authorized.tzinfo is not None and authorized<EXPIRES and authorized<=now,
                'Stage was not authorized before the deadline')
    return proof


def stage_before_expiry(root,case,model_root):
    common.need(utcnow()<EXPIRES,'No new stage after the delegation deadline')
    directory=_ORIGINAL_STAGE(root,case,model_root)
    now=utcnow()
    common.need(now<EXPIRES,'Staging crossed the deadline; no valid authorization proof was issued')
    expected=stage_proof_fields(root,case,directory)
    target=directory/STAGE_PROOF
    if target.exists():
        common.owned_file(directory,target)
        validate_stage_proof(common.read(target),expected,now)
    else:
        common.write_new(target,dict(expected,authorized_at_utc=now.isoformat().replace('+00:00','Z')))
    return directory


def existing_preexpiry_stage(root,case,model_root):
    directory=root/case['case_id']
    common.need(directory.is_dir() and directory==directory.resolve(strict=True),'Queued job requires an existing real staged case')
    for name in ('bench.scs','case.json',STAGE_PROOF):
        common.owned_file(directory,directory/name)
    source,meta=build(case)
    private=base.original.model_preflight.verify_private_kit(model_root,'tt')
    token=base.review.gm_center64.BASE.MODEL_TOKEN.encode('ascii')
    model=private['model_root'].encode('utf-8')
    bench=source.replace(token,model)
    common.need(source.count(token)==1 and bench.replace(model,token)==source,'Nonreversible model substitution')
    expected_record=dict(meta,model_preflight=private,bench_sha256=hashlib.sha256(bench).hexdigest())
    common.need((directory/'bench.scs').read_bytes()==bench and common.read(directory/'case.json')==expected_record,
                'Queued case is not byte-exactly the reviewed pre-staged design')
    validate_stage_proof(common.read(directory/STAGE_PROOF),stage_proof_fields(root,case,directory),utcnow())
    return directory


def validate_preexpiry_slurm_submission(output,job_id,now):
    common.need(re.fullmatch(r'[0-9]+',job_id) is not None,'A numeric SLURM_JOB_ID is required')
    ids=re.findall(r'(?:^|\s)JobId=(\S+)',output)
    submitted=re.findall(r'(?:^|\s)SubmitTime=(\S+)',output)
    common.need(ids==[job_id] and len(submitted)==1
                and re.fullmatch(r'[0-9]+',submitted[0]) is not None,
                'Expected one matching Slurm job with a decimal SubmitTime')
    try:
        instant=datetime.fromtimestamp(int(submitted[0]),timezone.utc)
    except (OverflowError,OSError,ValueError):
        raise ValueError('Invalid Slurm submission timestamp') from None
    common.need(instant<EXPIRES and instant<=now,'Job was not submitted before the deadline')
    return dict(job_id=job_id,submit_time_epoch=int(submitted[0]),
                submitted_at_utc=instant.isoformat().replace('+00:00','Z'))


def query_preexpiry_slurm_submission(now):
    job_id=os.environ.get('SLURM_JOB_ID','')
    common.need(re.fullmatch(r'[0-9]+',job_id) is not None,'A numeric SLURM_JOB_ID is required after expiry')
    env=os.environ.copy()
    env.update(SLURM_TIME_FORMAT='%s',TZ='UTC',LC_ALL='C')
    result=subprocess.run(['scontrol','--oneliner','show','job',job_id],
                          env=env,timeout=15,check=True,capture_output=True,text=True)
    return validate_preexpiry_slurm_submission(result.stdout,job_id,now)


def stage_for_run(root,case,model_root):
    now=utcnow()
    if now>=EXPIRES:
        query_preexpiry_slurm_submission(now)
        return existing_preexpiry_stage(root,case,model_root)
    return stage_before_expiry(root,case,model_root)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('verify','list','approval-template','stage','run','collect-only','summary','gate'))
    parser.add_argument('--root',type=Path)
    parser.add_argument('--index',type=int)
    parser.add_argument('--model-root',type=Path)
    parser.add_argument('--approval',type=Path)
    args=parser.parse_args()
    verified=verify();cases=[case for case,meta in verified]
    if args.mode in ('verify','list'):
        for index,(case,meta) in enumerate(verified):
            print(index,case['case_id'],meta['portable_sha256'])
        return
    common.need(args.root is not None,'Supply an isolated offset pilot root')
    root=common.checked_root(args.root)
    common.need(root.name.startswith('pam4_sar7_offset_pilot_'),'Use a new offset pilot root')
    bind()
    if args.mode=='gate':
        print(json.dumps(measured_gate(root,cases),sort_keys=True));return
    if args.mode=='approval-template':
        common.need(args.approval is not None and args.approval.absolute().parent==root,'Keep approval in the campaign root')
        common.write_new(args.approval.absolute(),dict(expected_approval(root,verified),approved=False))
        print(args.approval.absolute());return
    common.need(args.index is not None and 0<=args.index<len(cases),'Supply a valid fixed case index')
    case=cases[args.index]
    if args.mode in ('stage','run'):
        common.need(args.approval is not None and args.approval.absolute().parent==root,'Keep approval in the campaign root')
        approval=args.approval.absolute()
        common.need(common.read(approval)==expected_approval(root,verified),'Approval must bind all cases, decks, manifest, root and expiry')
        common.need(args.model_root is not None,'Use the same verified private model root')
        if args.index==1:
            require_index1_gate(root,cases)
        if args.mode=='stage':
            print(stage_before_expiry(root,case,args.model_root));return
        stage_for_run(root,case,args.model_root)
        saved=base.stage
        try:
            # base.run may validate its stage but can never create it here.
            base.stage=existing_preexpiry_stage
            report=base.run(root,case,args.model_root,approval)
        finally:
            base.stage=saved
    elif args.mode=='summary':
        report=read_existing_report(root,case)
    else:
        report=base.collect(root,case)
    result,digest=write_summary(root,args.index,case,report)
    print(json.dumps(dict(summary=str(summary_path(root,case)),sha256=digest,
                         gate=gate_recommendation(result) if args.index==0 else None),sort_keys=True))


if __name__=='__main__':
    main()


