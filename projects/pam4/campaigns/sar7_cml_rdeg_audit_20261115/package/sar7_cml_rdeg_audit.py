"""Audit one completed SAR7 CML run without invoking a simulator or rewriting evidence."""

import argparse
from functools import partial
import hashlib
import math
import os
from pathlib import Path
import statistics
import sys


ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT/'SHA256SUMS.txt'
PILOT = Path(os.environ.get('PAM4_SAR7_CML_RDEG_PACKAGE',
    ROOT.parent/'PAM4_SAR7_CML_RDEG_20261115')).resolve()
AUDIT = Path(os.environ.get('PAM4_SAR7_AUDIT_PACKAGE',
    ROOT.parent/'PAM4_SAR7_CDAC_AUDIT_20261115')).resolve()
PILOT_MANIFEST_SHA = 'bd6428e1f85aa5eaf1a8ee99c521b05ffef64c848eb0c53402ccb1be4f995ce3'
AUDIT_MANIFEST_SHA = '91f528381bb0cc61b555f0ab673026faf61063803b1d19ed2c574b66143061c4'
PORTABLE_SHA = '362dc80f1ca8444f59c1f620d2fb5fdae2d8c8948ef2bb7aa3155b2533cbf006'
SOURCE_ZIP_SHA = '938e179f33863ddec49894ba0a44f27b5249cf4efad3dfbfe4ac1bd9248e43dc'
SUMMARY_SHA = 'ab2cdaaa6840bbb81841bc120d5d2cb69a47553c1e71e2c8ec22f0f2283dec95'
CASE_ID = 'sar7_07_tt_r5_cml_rdeg'
JOB = '760348'
SOURCE_NAME = 'pam4_sar7_cml_rdeg_20261115.ot1Vbg'


def dependency(path, expected):
    if hashlib.sha256((path/'SHA256SUMS.txt').read_bytes()).hexdigest() != expected:
        raise ValueError('Unexpected dependency: '+path.name)


dependency(PILOT, PILOT_MANIFEST_SHA)
dependency(AUDIT, AUDIT_MANIFEST_SHA)
sys.path.insert(0, str(PILOT))
import sar7_cml_rdeg as pilot
sys.path.insert(0, str(AUDIT))
import sar7_cdac_audit as old_audit

base, common, scorer = pilot.base, pilot.common, pilot.base.score


def sign_counts(points):
    products = [p['held_diff_V']*p['sense_diff_V'] for p in points]
    return dict(points=len(products),same_sign=sum(p>0 for p in products),
                opposite_sign=sum(p<0 for p in products),zero_product=sum(p==0 for p in products))


def sense_fit(points, lsb_V):
    """Return sense-stage affine fit; its zero crossing is not comparator offset."""
    common.need(math.isfinite(lsb_V) and lsb_V>0, 'Expected positive finite LSB in volts')
    xs = [row['held_diff_V'] for row in points]
    ys = [row['sense_diff_V'] for row in points]
    common.need(len(xs)>1 and all(math.isfinite(x) for x in [*xs,*ys]),
                'Expected finite sense pairs')
    line = statistics.linear_regression(xs, ys)
    residual = [y-(line.slope*x+line.intercept) for x,y in zip(xs,ys,strict=True)]
    crossing = None if line.slope==0 else -line.intercept/line.slope
    threshold = .25*lsb_V
    return dict(fit_model='sense_diff_V = slope_V_per_V * held_diff_V + output_intercept_V',
                slope_V_per_V=line.slope,output_intercept_V=line.intercept,
                fit_rmse_output_V=math.sqrt(statistics.mean(v*v for v in residual)),
                zero_crossing_label='SENSE STAGE ZERO CROSSING; not comparator offset',
                sense_stage_zero_crossing_input_V=crossing,
                sense_stage_zero_crossing_input_LSB=None if crossing is None else crossing/lsb_V,
                sign_threshold_input_V=threshold,sign_threshold_input_LSB=.25,
                sign_all=sign_counts(points),
                sign_abs_held_ge_0p25_LSB=sign_counts([p for p in points if abs(p['held_diff_V'])>=threshold]),
                sign_abs_held_lt_0p25_LSB=sign_counts([p for p in points if abs(p['held_diff_V'])<threshold]))


def collect_metrics(values, wave, report):
    times = values['time']
    lsb = wave['lsb_V']
    fit_rows, pairs = [], []
    correctness = {row['index']:row['observed_registered_code']==row['expected_code']
                   for row in report['conversions'] if row['scored']}

    def voltage(nodes, at):
        return [scorer.interpolate(times, values[n], at) for n in nodes]

    for row in wave['conversions']:
        a,b = voltage(wave['dac_pair'], row['sample_s'])
        sampled_lsb = (a-b)/lsb
        for trial in row['trials']:
            at = trial['pre_s']
            p,n = voltage(wave['dac_pair'], at)
            bits = [scorer.classify(*voltage(pair,at),wave['vdd_V']) for pair in row['code_pairs']]
            if None not in bits:
                fit_rows.append((row['index'],[1.,sampled_lsb/64,*bits],(p-n)/lsb))
            sensep,sensen = voltage(pilot.SENSE,at)
            pairs.append(dict(index=row['index'],bit=trial['bit'],held_diff_V=p-n,
                sense_diff_V=sensep-sensen,sense_common_mode_V=(sensep+sensen)/2,
                supply_current_A=scorer.interpolate(times,values['V_SENSE_DD:p'],at)))
    common.need(len(pairs)==84,'Expected exactly twelve by seven sense pairs')
    try:
        weights = dict(status='identified',**old_audit.gain_record(fit_rows))
    except ValueError as error:
        weights = dict(status='underdetermined',reason=str(error),usable_points=len(fit_rows))
    sense = sense_fit(pairs, lsb)
    sense['sign_correct_code_conversions'] = sign_counts([p for p in pairs if correctness[p['index']]])
    sense['sign_wrong_code_conversions'] = sign_counts([p for p in pairs if not correctness[p['index']]])
    return dict(weight_fit=weights,omitted_control_state_points=84-len(fit_rows),sense_affine=sense),pairs


def verify():
    dependency(PILOT, PILOT_MANIFEST_SHA)
    dependency(AUDIT, AUDIT_MANIFEST_SHA)
    case,meta = pilot.verify()
    old_audit.verify()
    common.need(base is old_audit.base,'Analysis dependencies must share the SAR evidence reader')
    common.need(case['case_id']==CASE_ID and meta['portable_sha256']==PORTABLE_SHA,
                'Unexpected completed CML design')
    for line in MANIFEST.read_text(encoding='ascii').splitlines():
        digest,name = line.split('  ',1)
        path = ROOT/name
        common.need(path.resolve().is_relative_to(ROOT) and common.sha(path)==digest,
                    'Package differs: '+name)
    return case,meta


def read_existing(path):
    owned,_ = common.owned_file(path.parent,path)
    before = common.sha(owned)
    data = common.read(owned)
    common.need(common.sha(owned)==before,'JSON changed during read')
    return data,before


def audit(source, case, source_zip=None):
    root = source.absolute()
    common.need(root==root.resolve(strict=True) and root.is_dir() and root.name==SOURCE_NAME,
                'Use the exact completed 760348 root without a redirected path')
    directory = root/CASE_ID
    # Bind the original CML case before evidence() regenerates reviewed metadata.
    base.build,base.PLAN,base.MANIFEST,base.SCHEMA = pilot.build,pilot.PLAN,pilot.MANIFEST,pilot.SCHEMA
    wave,status,hashes = base.evidence(case,directory)
    common.need(status['slurm_job_id']==JOB,'Expected completed source job 760348')
    report,measurement_sha = read_existing(directory/base.MEASUREMENT)
    summary,summary_sha = read_existing(root/'sar7_cml_rdeg_summary.json')
    common.need(summary_sha==SUMMARY_SHA,'Existing completed summary differs from the received result')
    traces = [r for r in status['raw_inventory'] if r['path'] in
              ('raw/tranResponse.tran',base.review.RAW_NAME)]
    common.need(len(traces)==1,'Expected one retained native transient')
    native = traces[0]
    common.need(report['execution_files_sha256']==hashes and report['tran_sha256']==native['sha256']
                and report['slurm_task_id']==JOB and report['case']==case,
                'Existing measurements do not match original solver evidence')
    expected_summary = dict(pilot.relaxed.summarize(report),case_id=CASE_ID,baseline_job_id='760091',
                            ideal_sense_job_id='760132',uncoupled_cml_job_id='760254')
    common.need(all(summary.get(k)==v for k,v in expected_summary.items()),
                'Summary differs from original measurements')
    common.need(summary['sense']['tran_sha256']==report['tran_sha256'],
                'Existing sense summary uses another PSF')
    live = common.raw_inventory(directory)
    common.need(common.matches_historical_inventory(status['raw_inventory'],live),'Changed retained trace inventory')
    required = set(scorer.required_traces(wave))|set(pilot.SENSE)|{'V_SENSE_DD:p'}
    raw = base.review.safe_raw(directory,dict(status,raw_inventory=live),
        native['path'].removeprefix('raw/'),parser=partial(base.review.parse_selected,required=required))
    common.need(raw.unit('time')=='s' and raw.sweep_names==['time'],'Expected one time axis in seconds')
    common.need(raw.sha256==report['tran_sha256'],'Parsed PSF differs from existing measurement')
    scorer.validate_trace_arrays(raw.values,required,wave['stop_s'],wave.get('strobe_s',0.))
    metrics,pairs = collect_metrics(raw.values,wave,report)
    common.need(pairs==summary['sense']['points'],'Retained sense points differ from completed summary')
    common.need(metrics['sense_affine']['slope_V_per_V']==summary['sense']['projected_gain'],
                'Sense slope differs from original summary')
    zip_receipt = dict(status='unavailable',expected_sha256=SOURCE_ZIP_SHA,
                       reason='No original ZIP file supplied; expected SHA is not a remote receipt')
    if source_zip is not None:
        original_zip = source_zip.absolute()
        common.need(original_zip==original_zip.resolve(strict=True) and original_zip.is_file(),
                    'Original ZIP must be a real existing file')
        digest = common.sha(original_zip)
        common.need(digest==SOURCE_ZIP_SHA,'Original ZIP differs from submitted package')
        zip_receipt = dict(status='measured',sha256=digest)
    common.need(base.evidence(case,directory)[2]==hashes,'Original solver evidence changed during audit')
    common.need(common.raw_inventory(directory)==live,'Raw inventory changed during audit')
    common.need(common.sha(directory/base.MEASUREMENT)==measurement_sha
                and common.sha(root/'sar7_cml_rdeg_summary.json')==summary_sha,
                'Original measured JSON changed during audit')
    conversions = [row for row in report['conversions'] if row['scored']]
    return dict(status='measured_from_retained_evidence',job_id=JOB,case_id=CASE_ID,
        source_campaign=SOURCE_NAME,source_read_only=True,new_solver_jobs=0,
        source_receipts_sha256=dict(summary=summary_sha,measurements=measurement_sha,tran=raw.sha256,
            staged_bench=hashes['bench.scs'],portable_bench=PORTABLE_SHA,pilot_manifest=PILOT_MANIFEST_SHA,
            cdac_analysis_manifest=AUDIT_MANIFEST_SHA,original_zip=zip_receipt),
        diagnostic_period_ps=1080,comparison_window_ps=60,lsb_V=wave['lsb_V'],
        original_scores=dict(wrong_conversions=report['wrong_conversions'],
            logic_smoke_pass=report['logic_smoke_pass'],codes=summary['codes'],
            max_abs_sample_error_lsb=summary['max_abs_sample_error_lsb'],
            max_abs_sample_dac_error_from_target_lsb=max(abs(r['sample_dac_error_from_target_LSB']) for r in conversions),
            final_cm_change_mV=summary['final_cm_change_mV']),
        limits=['Measured 0.926 GS/s diagnostic; not 1.75 GS/s validation',
                'Sense-stage zero crossing is not comparator offset',
                'CDAC linear fit is descriptive, not a trim prediction',
                'No timing scan, parameter tuning, or new simulation is authorized by this collector'],**metrics)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('verify','audit'))
    parser.add_argument('--source-root',type=Path)
    parser.add_argument('--output-root',type=Path)
    parser.add_argument('--source-zip',type=Path)
    args = parser.parse_args()
    case,meta = verify()
    if args.mode=='verify':
        print(CASE_ID,meta['portable_sha256'],'read-only analysis verified')
        return
    common.need(args.source_root is not None and args.output_root is not None,
                'Supply completed source and separate output roots')
    output_root = common.checked_root(args.output_root)
    common.need(output_root.name.startswith('pam4_sar7_cml_rdeg_audit_'),
                'Use a new CML RDEG audit root')
    source = args.source_root.resolve(strict=True)
    common.need(not output_root.is_relative_to(source) and not source.is_relative_to(output_root),
                'Keep audit output outside original evidence')
    result = audit(args.source_root,case,args.source_zip)
    output = output_root/'sar7_cml_rdeg_final_audit.json'
    old_audit.iso.save(output,result)
    print(output)


if __name__=='__main__':
    main()
