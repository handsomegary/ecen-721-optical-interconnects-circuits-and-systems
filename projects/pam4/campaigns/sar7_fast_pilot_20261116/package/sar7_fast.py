"""Retest the measured SAR7 circuit at 1.75 GS/s with the earlier 42 ps compare schedule."""

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / 'SHA256SUMS.txt'
PLAN = ROOT / 'PLAN.json'
SCHEMA = 'pam4_sar7_fast_pilot_v1'
CASE_ID = 'sar7_12_tt_175gs_matched_q'
PARENT_JOB = '761279'
PARENT_CASE = 'sar7_10_tt_matched_q_load'
PARENT_DECK_SHA = '2070f861b4e07e1037c6593ad5518bfd379fef185248ee60fa54c0c8c3832347'
PARENT_MANIFEST_SHA = 'f04d9107421d0a9d826df1c00252b264987fc678f6139a4d018fc2fa42250e90'
REVIEWED_DECK_SHA = '903d79a53dcc36162f08c198f9337bbf8fcfe94308bc6fa2c4cb79ad2c785032'
OFFSET = Path(os.environ.get('PAM4_SAR7_OFFSET_PACKAGE', ROOT.parent / 'PAM4_SAR7_OFFSET_PILOT_20261116')).resolve()
if hashlib.sha256((OFFSET / 'SHA256SUMS.txt').read_bytes()).hexdigest() != PARENT_MANIFEST_SHA:
    raise ValueError('The approved 761279 package manifest differs')
sys.path.insert(0, str(OFFSET))
import sar7_offset_pilot as offset


base, common, native = offset.base, offset.common, offset.native
ORIGINAL_BINDINGS = (base.build, base.PLAN, base.MANIFEST, base.SCHEMA)
COMPARE_SHIFT_PS = 17
CASE_PLAN = dict(schema=SCHEMA, cases=[dict(case_id=CASE_ID, parent_job=PARENT_JOB,
                                          parent_case=PARENT_CASE, parent_deck_sha256=PARENT_DECK_SHA)])


def case_record():
    common.need(common.read(PLAN) == CASE_PLAN, 'Fast plan differs from its single qualified test')
    return dict(offset.plan_cases()[0], case_id=CASE_ID)


def by_label(lines, labels):
    names = set(labels)
    cards = {}
    for line in lines:
        name = line.split(maxsplit=1)[0] if line.strip() else ''
        if name in names:
            common.need(name not in cards, f'Duplicate timing card {name}')
            cards[name] = line
    common.need(cards.keys() == names, 'Missing one or more of the frozen timing cards')
    return cards


def source_voltage_tokens(line):
    head, separator, payload = line.partition(' wave=[')
    common.need(bool(separator) and payload.endswith(']'), 'Expected a PWL stimulus card')
    tokens = payload[:-1].split()
    common.need(len(tokens) % 2 == 0, 'Each PWL sample needs time and voltage')
    return head, tokens[1::2]


def build(case):
    common.need(case == case_record(), 'Only the one frozen fast test is supported')
    parent = offset.plan_cases()[0]
    deck, prior = offset.build(parent)
    common.need(parent['case_id'] == PARENT_CASE and prior['portable_sha256'] == PARENT_DECK_SHA,
                'The 761279 measured circuit differs')

    # Use the original fast SAR inputs, trial schedule and stop time. Override only
    # the comparator rise in that schedule, exactly as in measured job 760002.
    original_case = dict(case, case_id='sar7_00_tt_pilot')
    fast, protocol = native.build(original_case, base.review.R5 / 'quiet.scs')
    clock_labels = [f'V_clk{bit}' for bit in native.BITS]
    labels = ['V_track', 'V_trackb', 'V_lowtrack', 'V_lowtrackb', 'V_reset', 'V_resetb',
              'V_conv', 'V_convb', 'V_srcp', 'V_srcn', 'tranResponse',
              *[f'V_trial{bit}' for bit in native.BITS], *clock_labels]
    source = deck.decode('ascii').splitlines()
    previous = by_label(source, labels)
    replacement = by_label(fast.splitlines(), labels)
    for step, bit in enumerate(native.BITS):
        replacement[f'V_clk{bit}'] = native.pulse(f'clk{bit}', 116 - COMPARE_SHIFT_PS + 66 * step, 560)
    for label in ('V_srcp', 'V_srcn'):
        common.need(source_voltage_tokens(previous[label]) == source_voltage_tokens(replacement[label]),
                    'Input source voltage values must be unchanged')
    without_stop = lambda card: re.sub(r'\bstop=\S+', 'stop=<time>', card)
    common.need(without_stop(previous['tranResponse']) == without_stop(replacement['tranResponse']),
                'Transient tolerances and save grid must stay unchanged')
    without_time = lambda card: re.sub(r'\b(?:delay|width|period)=\S+', '<time>', card)
    for label in set(labels) - {'V_srcp', 'V_srcn', 'tranResponse'}:
        common.need(without_time(previous[label]) == without_time(replacement[label]),
                    f'Only pulse timing can differ on {label}')
    common.need(all(previous[label] != replacement[label] for label in labels), 'Expected exactly 25 changes')
    rows = [replacement.get(line.split(maxsplit=1)[0], line) if line.strip() else line for line in source]
    bench = ('\n'.join(rows) + '\n').encode('ascii')
    digest = hashlib.sha256(bench).hexdigest()
    common.need(digest == REVIEWED_DECK_SHA, 'Reconstructed 1.75 GS/s deck differs from the reviewed version')

    # Preserve 761279's actual electrical metadata and probes, which differ from
    # the original untouched SAR. Copy only time and unchanged stimulus metadata.
    wave = copy.deepcopy(prior['wave'])
    conversions = copy.deepcopy(protocol['conversions'])
    for row, old in zip(conversions, wave['conversions'], strict=True):
        common.need(all(row[k] == old[k] for k in ('index', 'expected_code', 'source_diff_V', 'code_pairs')),
                    'Analysis stimulus and registered output wiring must remain unchanged')
        for trial, old_trial in zip(row['trials'], old['trials'], strict=True):
            common.need(trial['bit'] == old_trial['bit'] and trial['cmp_pair'] == old_trial['cmp_pair'],
                        'Comparator output mapping must remain unchanged')
            trial['pre_s'] -= native.timing(COMPARE_SHIFT_PS)
            trial['compare_s'] -= native.timing(COMPARE_SHIFT_PS)
            common.need(trial['launch_s'] < trial['pre_s'] < trial['compare_s'] < trial['read_s']
                        < trial['trial_release_s'] < row['end_s'], 'Invalid fast trial timing')
    wave.update(period_s=protocol['period_s'], stop_s=protocol['stop_s'], conversions=conversions)
    return bench, dict(case=case, wave=wave, portable_sha256=digest,
                       baseline_sha256=PARENT_DECK_SHA, baseline_job=PARENT_JOB,
                       timing_changed_card_labels=labels, launch_to_compare_ps=21, compare_to_read_ps=42)


def verify():
    files = {'sar7_fast.py', 'sar7_fast.sbatch', 'PLAN.json', 'HANDOFF_zh_TW.md', 'test_sar7_fast.py'}
    entries = [line.split('  ', 1) for line in MANIFEST.read_text(encoding='ascii').splitlines()]
    common.need(len(entries) == len(files) and {name for _, name in entries} == files, 'Unexpected fast manifest')
    for digest, name in entries:
        path = ROOT / name
        common.need(path.is_file() and path.resolve().parent == ROOT and common.sha(path) == digest,
                    'Fast package file differs: ' + name)
    saved = (base.build, base.PLAN, base.MANIFEST, base.SCHEMA)
    try:
        base.build, base.PLAN, base.MANIFEST, base.SCHEMA = ORIGINAL_BINDINGS
        parents = offset.verify()
    finally:
        base.build, base.PLAN, base.MANIFEST, base.SCHEMA = saved
    common.need(parents[0][0]['case_id'] == PARENT_CASE and parents[0][1]['portable_sha256'] == PARENT_DECK_SHA,
                'Expected frozen 761279 index zero')
    case = case_record()
    return case, build(case)[1]


def approval_record(root, meta, approved):
    return dict(approved=approved, platform='Olympus', campaign=SCHEMA, case_ids=[CASE_ID],
                authorized_run_root=str(root), design_source_sha256=common.sha(MANIFEST),
                deck_sha256_by_case={CASE_ID: meta['portable_sha256']})


def summarize(report, root, case, meta):
    rows = [row for row in report['conversions'] if row['scored']]
    common.need(len(rows) == report['tested_conversions'] == 12
                and [row['expected_code'] for row in rows] == case['pattern_codes'], 'Invalid stimulus evidence')
    per_bit = {}
    for bit in native.BITS:
        trials = [trial for row in rows for trial in row['trial_results'] if trial['bit'] == bit]
        common.need(len(trials) == 12 and all(sum(t['bit'] == bit for t in row['trial_results']) == 1 for row in rows),
                    'Expected one trial at this bit in every conversion')
        margins = [(t['compare_to_read_s'] - t['stable_rail_delay_s']) / native.PS
                   for t in trials if t['stable_rail_delay_s'] is not None]
        deltas = [abs(t['dac_residue_at_read_V'] - t['residue_prelaunch_V']) / meta['wave']['lsb_V']
                  for t in trials]
        per_bit[str(bit)] = dict(unresolved=sum(t['decision'] is None for t in trials),
                                min_buffered_rail_read_margin_ps=min(margins, default=None),
                                max_precompare_to_read_dac_change_lsb=max(deltas))
    cmp = offset.error_metrics(rows, 'observed_comparator_code')
    reg = offset.error_metrics(rows, 'observed_registered_code')
    agreement = all(row['observed_comparator_code'] is not None
                    and row['observed_comparator_code'] == row['observed_registered_code'] for row in rows)
    cm = [1000 * row['final_dac_common_mode_change_from_sample_V'] for row in rows]
    unresolved = sum(item['unresolved'] for item in per_bit.values())
    screen_pass = (unresolved == 0 and agreement and max(map(abs, cm)) <= 10
                   and cmp['max_abs_code_error'] is not None and cmp['max_abs_code_error'] <= 1
                   and cmp['wrong'] <= 6)
    measurements = root / CASE_ID / base.MEASUREMENT
    return dict(schema=SCHEMA, stage='single_slice_fixed_timing_tt_12_centers', case_id=CASE_ID,
                sampling_rate_gsps=1 / meta['wave']['period_s'] / 1e9,
                launch_to_compare_ps=21, compare_to_read_ps=42, compared_baseline_job=PARENT_JOB,
                screen_pass=screen_pass, logic_smoke_pass=report['logic_smoke_pass'],
                comparator=cmp, registered=reg, comparator_registered_agreement=agreement,
                unresolved_bits=unresolved, per_bit=per_bit, final_dac_cm_change_mV=[min(cm), max(cm)],
                max_abs_sample_error_lsb=report['max_abs_sample_error_lsb'],
                max_observed_resolve_delay_s=report['max_observed_resolve_delay_s'],
                job_id=report['slurm_task_id'], solver_seconds=report['solver_seconds'], raw_bytes=report['raw_bytes'],
                codes=[dict(expected=row['expected_code'], comparator=row['observed_comparator_code'],
                            registered=row['observed_registered_code']) for row in rows],
                provenance=dict(manifest_sha256=common.sha(MANIFEST),
                                baseline_portable_deck_sha256=PARENT_DECK_SHA,
                                portable_deck_sha256=meta['portable_sha256'],
                                measurements_sha256=common.sha(measurements),
                                tran_sha256=report['tran_sha256'], execution_files_sha256=report['execution_files_sha256']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('verify', 'approval-template', 'stage', 'run', 'collect-only'))
    parser.add_argument('--root', type=Path)
    parser.add_argument('--approval', type=Path)
    parser.add_argument('--model-root', type=Path)
    args = parser.parse_args()
    case, meta = verify()
    if args.mode == 'verify':
        print(CASE_ID, meta['portable_sha256'])
        return
    common.need(args.root is not None and args.approval is not None, 'Supply isolated root and approval path')
    root = common.checked_root(args.root)
    approval = args.approval.absolute()
    common.need(root.name.startswith('pam4_sar7_fast_pilot_') and approval.parent == root,
                'Fast root must be new, with its approval stored inside')
    if args.mode == 'approval-template':
        common.write_new(approval, approval_record(root, meta, False))
        return
    common.need(common.read(approval) == approval_record(root, meta, True),
                'Approval must bind the run root, manifest and single reviewed deck')
    base.build, base.PLAN, base.MANIFEST, base.SCHEMA = build, PLAN, MANIFEST, SCHEMA
    base.TIMEOUT_S = 540
    if args.mode in ('stage', 'run'):
        common.need(args.model_root is not None, 'Supply the same verified private model root')
        if args.mode == 'stage':
            print(base.stage(root, case, args.model_root))
            return
        # Original runner verifies stage byte equality, writes evidence, and
        # performs at most one solver invocation in an owned case directory.
        report = base.run(root, case, args.model_root, approval)
    else:
        report = base.collect(root, case)
    result = summarize(report, root, case, meta)
    out = root / 'sar7_fast_summary.json'
    if not out.exists():
        common.write_new(out, result)
    else:
        common.need(common.read(out) == result, 'Existing summary differs from verified evidence')
    print(json.dumps(dict(summary=str(out), sha256=common.sha(out), screen_pass=result['screen_pass'])))


if __name__ == '__main__':
    main()
