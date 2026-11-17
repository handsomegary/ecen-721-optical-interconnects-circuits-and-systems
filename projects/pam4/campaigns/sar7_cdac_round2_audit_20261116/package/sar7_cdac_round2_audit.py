"""Read completed job760874 once and export bounded SAR evidence, without simulations."""

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
PARENT = Path(os.environ.get('PAM4_SAR7_CDAC_FIX_PACKAGE',ROOT.parent/'PAM4_SAR7_CDAC_FIX_20261116')).resolve()
OLD_AUDIT = Path(os.environ.get('PAM4_SAR7_AUDIT_PACKAGE',ROOT.parent/'PAM4_SAR7_CDAC_AUDIT_20261115')).resolve()
PARENT_SHA = 'bb97b973466cc63a8d6c282b7ab142e35b4af911e107d01da0efa51ef3005153'
OLD_AUDIT_SHA = '91f528381bb0cc61b555f0ab673026faf61063803b1d19ed2c574b66143061c4'
SUMMARY_SHA = '6573a387cf24fccfad5ffbaa98016b59f22d21402b7b59cfbba8ef72527fc150'
MEASUREMENTS_SHA = '416735e041446ec7e596498ae5ca537b5851139a42e030b899437e260ee47cd6'
TRAN_SHA = '22de6869fca439d446ad6e04de2e1e1809708fce82081c8b40215ef7061fb4f9'
PORTABLE_SHA = 'f2231b54d5138538c57102e5cd25dcc1047829ed71f02d79ab3d37d5726a6153'
SOURCE_NAME = 'pam4_sar7_cdac_fix_20261116.zN5rXs'
CASE_ID = 'sar7_09_tt_cml_main_ratio'
JOB_ID = '760874'
SPARSE_OFFSETS_PS = (0.,.25,.5,1.,2.,5.,15.,30.,50.,60.)


def dependency(path, expected):
    if hashlib.sha256((path/'SHA256SUMS.txt').read_bytes()).hexdigest()!=expected:
        raise ValueError('Unexpected dependency: '+path.name)


dependency(PARENT,PARENT_SHA)
dependency(OLD_AUDIT,OLD_AUDIT_SHA)
sys.path.insert(0,str(PARENT))
import sar7_cdac_fix as parent
sys.path.insert(0,str(OLD_AUDIT))
import sar7_cdac_audit as old_audit

base,common,scorer = parent.base,parent.common,parent.base.score
SENSE = parent.pilot.SENSE


def control_state(values, times, pairs, at, vdd):
    voltages = [[scorer.interpolate(times,values[node],at) for node in pair] for pair in pairs]
    bits = [scorer.classify(*pair,vdd) for pair in voltages]
    return dict(bits_b6_to_b0=bits,pair_voltages_V=voltages,
                control_word=None if None in bits else sum(b<<bit for b,bit in zip(bits,range(6,-1,-1),strict=True)))


def observation(values, wave, trial, at):
    time = values['time']
    held,held_cm = scorer.differential(time,values,wave['dac_pair'],at)
    sense,sense_cm = scorer.differential(time,values,SENSE,at)
    rails = [scorer.interpolate(time,values[node],at) for node in trial['cmp_pair']]
    return dict(held_diff_V=held,held_common_mode_V=held_cm,sense_diff_V=sense,
                sense_common_mode_V=sense_cm,comparator_pair_V=rails,
                comparator_class=scorer.classify(*rails,wave['vdd_V']))


def sparse_observations(values, wave, trial):
    result = []
    for offset in SPARSE_OFFSETS_PS:
        at = trial['compare_s']+offset*1e-12
        if at>trial['read_s'] and not math.isclose(at,trial['read_s'],rel_tol=0.,abs_tol=1e-21):
            continue
        at = min(at,trial['read_s'])
        result.append(dict(offset_from_compare_ps=offset,at_s=at,**observation(values,wave,trial,at)))
    return result


def affine_sense(rows, lsb):
    x = [row['pre']['held_diff_V'] for row in rows]
    y = [row['pre']['sense_diff_V'] for row in rows]
    line = statistics.linear_regression(x,y)
    residuals = [yi-line.slope*xi-line.intercept for xi,yi in zip(x,y,strict=True)]
    return dict(slope_V_per_V=line.slope,output_intercept_V=line.intercept,
                output_rmse_V=math.sqrt(statistics.mean(r*r for r in residuals)),
                sense_stage_zero_crossing_input_V=None if line.slope==0 else -line.intercept/line.slope,
                sense_stage_zero_crossing_input_LSB=None if line.slope==0 else -line.intercept/line.slope/lsb,
                zero_crossing_label='Sense stage affine zero crossing, not comparator offset')


def sign_decision(rows, field):
    available = [row for row in rows if row['decision'] is not None and row['pre'][field]!=0]
    disagreements = [dict(index=r['index'],bit=r['bit'],decision=r['decision'],pre_diff_V=r['pre'][field])
                     for r in available if int(r['pre'][field]>0)!=r['decision']]
    return dict(available=len(available),agrees=len(available)-len(disagreements),
                disagrees=len(disagreements),zero_or_unresolved=len(rows)-len(available),
                disagreement_records=disagreements)


def collect_metrics(values, wave, report):
    times,lsb = values['time'],wave['lsb_V']
    measured = {row['index']:row for row in report['conversions'] if row['scored']}
    fit_rows,conversions,trials = [],[],[]
    previous = None
    for conversion in wave['conversions']:
        index = conversion['index']
        row = measured[index]
        sample = {}
        for label,pair in (('source',wave['input_pair']),('main',wave['dac_pair']),('low',wave['low_pair'])):
            diff,cm = scorer.differential(times,values,pair,conversion['sample_s'])
            sample[label+'_diff_V'],sample[label+'_common_mode_V'] = diff,cm
        for actual,field in ((sample['source_diff_V'],'sample_input_diff_V'),
                             (sample['main_diff_V'],'sample_dac_diff_V'),
                             (sample['low_diff_V'],'sample_low_diff_V')):
            common.need(math.isclose(actual,row[field],rel_tol=0.,abs_tol=1e-14),
                        'Retained sample differs from existing measurements')
        different = [bit for bit in range(6,-1,-1) if ((row['expected_code']^row['observed_registered_code'])>>bit)&1]
        conversions.append(dict(index=index,expected_code=row['expected_code'],
            observed_comparator_code=row['observed_comparator_code'],observed_registered_code=row['observed_registered_code'],
            delta_code=row['observed_registered_code']-row['expected_code'],
            first_different_bit=different[0] if different else None,
            previous_source_code=previous,sample_s=conversion['sample_s'],target_input_diff_V=row['target_input_diff_V'],
            sample=sample,sample_main_error_from_target_LSB=row['sample_dac_error_from_target_LSB'],
            sample_low_error_from_target_LSB=row['sample_low_error_from_target_LSB'],
            low_minus_main_sample_LSB=(sample['low_diff_V']-sample['main_diff_V'])/lsb,
            final_dac_residue_V=row['final_dac_residue_V'],
            final_dac_common_mode_change_from_sample_V=row['final_dac_common_mode_change_from_sample_V']))
        previous = row['expected_code']
        trial_measurements = {item['bit']:item for item in row['trial_results']}
        for trial in conversion['trials']:
            at = trial['pre_s']
            state = control_state(values,times,conversion['code_pairs'],at,wave['vdd_V'])
            pre = observation(values,wave,trial,at)
            low_diff,low_cm = scorer.differential(times,values,wave['low_pair'],at)
            pre.update(low_diff_V=low_diff,low_common_mode_V=low_cm)
            original = trial_measurements[trial['bit']]
            read = observation(values,wave,trial,trial['read_s'])
            bit = trial['bit']
            final_code = row['observed_comparator_code']
            assumed_word = (final_code>>(bit+1)<<(bit+1)) | (1<<bit)
            common.need(read['comparator_class']==original['decision'],'Read classification differs from measurement')
            common.need(math.isclose(pre['held_diff_V'],original['residue_prelaunch_V'],rel_tol=0.,abs_tol=1e-14),
                        'Trial held residual differs from existing measurement')
            record = dict(index=index,bit=trial['bit'],expected_bit=original['expected_bit'],
                decision=original['decision'],launch_s=trial['launch_s'],pre_s=at,
                compare_s=trial['compare_s'],read_s=trial['read_s'],pre_control=state,pre=pre,at_read=read,
                old_final_prefix_assumption_word=assumed_word,
                actual_control_matches_old_prefix_assumption=None if state['control_word'] is None else state['control_word']==assumed_word,
                stable_rail_delay_s=original['stable_rail_delay_s'],
                dac_trial_settle_window_s=original['dac_trial_settle_window_s'],
                peak_dac_residue_excursion_during_trial_V=original['peak_dac_residue_excursion_during_trial_V'],
                peak_dac_common_mode_excursion_during_trial_V=original['peak_dac_common_mode_excursion_during_trial_V'],
                sparse_retained_observations=sparse_observations(values,wave,trial))
            trials.append(record)
            if state['control_word'] is not None:
                fit_rows.append((index,[1.,sample['main_diff_V']/lsb/64,*state['bits_b6_to_b0']],pre['held_diff_V']/lsb))
    common.need(len(conversions)==12 and len(trials)==84,'Expected twelve conversions and84trials')
    try:
        fit = dict(status='identified',**old_audit.gain_record(fit_rows))
    except ValueError as error:
        fit = dict(status='underdetermined',reason=str(error),usable_points=len(fit_rows))
    available_states = [r for r in trials if r['pre_control']['control_word'] is not None]
    mismatched_states = [dict(index=r['index'],bit=r['bit'],actual_word=r['pre_control']['control_word'],
                             assumed_word=r['old_final_prefix_assumption_word'])
                         for r in available_states if not r['actual_control_matches_old_prefix_assumption']]
    return dict(conversions=conversions,trials=trials,
        cdac_weight_fit=fit,omitted_pre_control_states=84-len(fit_rows),sense_affine=affine_sense(trials,lsb),
        actual_control_vs_old_prefix=dict(available=len(available_states),matches=len(available_states)-len(mismatched_states),
                                         mismatches=len(mismatched_states),mismatch_records=mismatched_states),
        decision_vs_held_pre_sign=sign_decision(trials,'held_diff_V'),
        decision_vs_sense_pre_sign=sign_decision(trials,'sense_diff_V'),
        index8_detail=dict(conversion=next(r for r in conversions if r['index']==8),
                           trials=[r for r in trials if r['index']==8]))


def verify():
    dependency(PARENT,PARENT_SHA)
    dependency(OLD_AUDIT,OLD_AUDIT_SHA)
    verified = parent.verify()
    old_audit.verify()
    common.need(len(verified)==2 and base is old_audit.base,'Unexpected original correction cases or reader')
    case,meta = verified[1]
    common.need(case['case_id']==CASE_ID and meta['portable_sha256']==PORTABLE_SHA,
                'Expected original completed index1 design')
    for line in MANIFEST.read_text(encoding='ascii').splitlines():
        digest,name = line.split('  ',1)
        path = ROOT/name
        common.need(path.resolve().is_relative_to(ROOT) and common.sha(path)==digest,'Collector package differs: '+name)
    return case


def read_existing(path, expected):
    owned,_ = common.owned_file(path.parent,path)
    content = owned.read_bytes()
    common.need(hashlib.sha256(content).hexdigest()==expected,'Original JSON receipt differs: '+path.name)
    result = common.read(owned)
    common.need(common.sha(owned)==expected,'Original JSON changed during read')
    return result,content


def audit(source, case):
    root = source.absolute()
    common.need(root==root.resolve(strict=True) and root.is_dir() and root.name==SOURCE_NAME,
                'Use exact completed760874 campaign without redirection')
    directory = root/CASE_ID
    parent.bind()
    wave,status,hashes = base.evidence(case,directory)
    common.need(status['slurm_job_id']==JOB_ID,'Expected completed sourcejob760874')
    report,report_bytes = read_existing(directory/base.MEASUREMENT,MEASUREMENTS_SHA)
    summary,summary_bytes = read_existing(directory/parent.SUMMARY,SUMMARY_SHA)
    common.need(report['case']==case and report['slurm_task_id']==JOB_ID
                and report['execution_files_sha256']==hashes and report['tran_sha256']==TRAN_SHA,
                'Existing measurement evidence differs')
    common.need(summary['job_id']==JOB_ID and summary['case_id']==CASE_ID and summary['tran_sha256']==TRAN_SHA
                and summary['provenance']['measurements_sha256']==MEASUREMENTS_SHA
                and summary['provenance']['portable_deck_sha256']==PORTABLE_SHA,
                'Original measured summary provenance differs')
    common.need(parent.summarize(report,summary['sense'],root,1,case)==summary,
                'Original summary does not match existing measured evidence')
    live = common.raw_inventory(directory)
    common.need(common.matches_historical_inventory(status['raw_inventory'],live),'Retained raw inventory changed')
    traces = [r for r in status['raw_inventory'] if r['path'] in
              ('raw/tranResponse.tran',base.review.RAW_NAME)]
    common.need(len(traces)==1 and traces[0]['sha256']==TRAN_SHA,'Expected one hash-bound native PSF')
    required = set(scorer.required_traces(wave))|set(SENSE)
    raw = base.review.safe_raw(directory,dict(status,raw_inventory=live),
        traces[0]['path'].removeprefix('raw/'),parser=partial(base.review.parse_selected,required=required))
    common.need(raw.unit('time')=='s' and raw.sweep_names==['time'] and raw.sha256==TRAN_SHA,
                'Expected retained native transient in seconds')
    scorer.validate_trace_arrays(raw.values,required,wave['stop_s'],wave.get('strobe_s',0.))
    metrics = collect_metrics(raw.values,wave,report)
    stored_pairs = {(p['index'],p['bit']):p for p in summary['sense']['points']}
    common.need(len(stored_pairs)==84,'Expected84recorded sense pairs')
    for row in metrics['trials']:
        stored = stored_pairs[row['index'],row['bit']]
        for new,old in ((row['pre']['held_diff_V'],stored['held_diff_V']),
                        (row['pre']['sense_diff_V'],stored['sense_diff_V'])):
            common.need(math.isclose(new,old,rel_tol=0.,abs_tol=1e-14),'Retained pre_s metrics differ from summary')
    common.need(base.evidence(case,directory)[2]==hashes,'Original execution evidence changed during audit')
    common.need(common.raw_inventory(directory)==live,'Raw inventory changed during audit')
    common.need(common.sha(directory/base.MEASUREMENT)==MEASUREMENTS_SHA
                and common.sha(directory/parent.SUMMARY)==SUMMARY_SHA,'Original measured JSON changed during audit')
    result = dict(schema='pam4_sar7_cdac_round2_retained_audit_v1',status='measured_from_retained_evidence',
        job_id=JOB_ID,case_id=CASE_ID,source_campaign=SOURCE_NAME,source_read_only=True,new_solver_jobs=0,
        source_sha256=dict(summary=SUMMARY_SHA,measurements=MEASUREMENTS_SHA,tran=TRAN_SHA,
            portable=PORTABLE_SHA,staged_bench=hashes['bench.scs'],parent_manifest=PARENT_SHA,
            weight_analysis_manifest=OLD_AUDIT_SHA),lsb_V=wave['lsb_V'],
        original_scores=dict(comparator=summary['comparator'],registered=summary['registered'],
            valid=summary['valid'],logic_smoke_pass=summary['logic_smoke_pass'],
            unresolved_bits_total=summary['unresolved_bits_total'],
            max_abs_sample_error_lsb=summary['max_abs_sample_error_lsb']),
        limits=['No circuit design, parameter prediction or new simulation',
                'Sparse observations interpolate existing storedPSF points, without changing timing',
                'Weight fit uses actualpre_s control rails, never final-prefix assumptions',
                'Sense affine zero crossing is not comparator offset'],**metrics)
    return result,dict(source_summary=summary_bytes,source_measurements=report_bytes)


def write_new_or_identical(path, content):
    if path.exists():
        common.need(path.is_file() and not path.is_symlink() and path.read_bytes()==content,
                    'Existing output differs: '+path.name)
    else:
        with path.open('xb') as stream:
            stream.write(content)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('verify','audit'))
    parser.add_argument('--source-root',type=Path)
    parser.add_argument('--output-root',type=Path)
    parser.add_argument('--copy-source-json',action='store_true')
    args = parser.parse_args()
    case = verify()
    if args.mode=='verify':
        print(CASE_ID,PORTABLE_SHA,'retained-only collector verified')
        return
    common.need(args.source_root is not None and args.output_root is not None,'Supply source and separate output roots')
    output_root = common.checked_root(args.output_root)
    source = args.source_root.resolve(strict=True)
    common.need(output_root.name.startswith('pam4_sar7_cdac_round2_audit_')
                and not output_root.is_relative_to(source) and not source.is_relative_to(output_root),
                'Use separate new round2 audit output root')
    result,copies = audit(args.source_root,case)
    target = output_root/'sar7_cdac_round2_retained_audit.json'
    old_audit.iso.save(target,result)
    if args.copy_source_json:
        for name,content in copies.items():
            write_new_or_identical(output_root/(name+'.json'),content)
    print(target)


if __name__=='__main__':
    main()
