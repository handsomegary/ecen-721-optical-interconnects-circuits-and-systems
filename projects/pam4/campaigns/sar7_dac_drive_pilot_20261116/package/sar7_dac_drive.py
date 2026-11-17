"""One 1.75 GS/s comparator/CDAC run with ideal reference-selection gate drive."""

import argparse
from bisect import bisect_left, bisect_right
import copy
from functools import partial
import hashlib
import json
import os
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / 'SHA256SUMS.txt'
PLAN = ROOT / 'PLAN.json'
SCHEMA = 'pam4_sar7_dac_drive_pilot_v1'
CASE_ID = 'sar7_13_tt_175gs_dac_gate_bypass'
PARENT_JOB = '761321'
PARENT_DECK_SHA = '903d79a53dcc36162f08c198f9337bbf8fcfe94308bc6fa2c4cb79ad2c785032'
PARENT_MANIFEST_SHA = 'e049fa8bda238eb15777db392ec377634807d7f630eae51caa7b062372bf98d0'
AUDIT_SHA = 'b4220fb8c268a55c4425029dcfc7a1f36e55bbc6cb7bfef7be0ebad26abe5f7b'
REVIEWED_DECK_SHA = '49d09ab9b9042f6cfc5befc4b018281c7f3f7f5542168bb4144ad8e7f3fb89b5'
FAST = Path(os.environ.get('PAM4_SAR7_FAST_PACKAGE', ROOT.parent / 'PAM4_SAR7_FAST_PILOT_20261116')).resolve()
if hashlib.sha256((FAST / 'SHA256SUMS.txt').read_bytes()).hexdigest() != PARENT_MANIFEST_SHA:
    raise ValueError('The measured 761321 package manifest differs')
sys.path.insert(0, str(FAST))
import sar7_fast as fast


base, common, native, score = fast.base, fast.common, fast.native, fast.base.score
BITS = native.BITS
GATES = tuple(f'{prefix}{k}{reference}' for k in BITS for reference in 'zo' for prefix in ('c', 'cb'))
ACTUAL_GATES = tuple(f'ff_{signal}' for signal in GATES)
BOTTOMS = tuple(f'b{k}{leg}' for k in BITS for leg in 'pn')
EXTRA_SAVES = (*GATES, *ACTUAL_GATES, *BOTTOMS)
PLAN_RECORD = dict(schema=SCHEMA, cases=[dict(case_id=CASE_ID, parent_job=PARENT_JOB,
                                            parent_deck_sha256=PARENT_DECK_SHA, audit_sha256=AUDIT_SHA)])


def case_record():
    common.need(common.read(PLAN) == PLAN_RECORD, 'Expected one frozen diagnostic case')
    return dict(fast.case_record(), case_id=CASE_ID)


def clipped(expression):
    return f'min(max({expression},0),1)'


def bsource_cards():
    # All controls use the same 0.9 V supply as the frozen TT branch. Limit
    # algebraic gain and preserve complementary switch controls at both rails.
    volt = '0.9'
    yield f'FF_CONV (ff_conv 0) bsource v={clipped(f"(v(conv)/{volt}-0.3)/0.4")}'
    for k in BITS:
        choice = f'ff_choice{k}'
        yield f'FF_CHOICE{k} ({choice} 0) bsource v=max(v(trial{k}),v(q{k}p))'
        gate = {'z': f'(0.48-v({choice})/{volt})/0.12',
                'o': f'(v({choice})/{volt}-0.52)/0.12'}
        for ref, expression in gate.items():
            yield f'FF_C{k}{ref} (ff_c{k}{ref} 0) bsource v=v(vdd)*v(ff_conv)*{clipped(expression)}'
            yield f'FF_CB{k}{ref} (ff_cb{k}{ref} 0) bsource v=v(vdd)-v(ff_c{k}{ref})'


def build(case):
    common.need(case == case_record(), 'Only the qualified DAC-driver experiment is supported')
    source, prior = fast.build(fast.case_record())
    common.need(prior['portable_sha256'] == PARENT_DECK_SHA and prior['wave']['vdd_V'] == .9,
                'Wrong 761321 bench or nominal supply')
    rows, treated = [], set()
    save_count = 0
    for line in source.decode('ascii').splitlines():
        match = re.fullmatch(r'(XRef([0-6])([pn])([ZO])) \((\S+) (\S+) (\S+) (\S+) vdd\) SAR_TG', line)
        if match:
            label, bit, side, ref, bottom, reference, control, complement = match.groups()
            expected_reference = 'rhi' if (side == 'p') == (ref == 'Z') else 'rlo'
            common.need(label not in treated and bottom == f'b{bit}{side}' and reference == expected_reference
                        and control == f'c{bit}{ref.lower()}' and complement == f'cb{bit}{ref.lower()}',
                        'Frozen reference TG wiring differs')
            treated.add(label)
            line = f'{label} ({bottom} {reference} ff_{control} ff_{complement} vdd) SAR_TG'
        if line.startswith('save '):
            rows.extend(bsource_cards())
            common.need(not set(line.split()) & set(EXTRA_SAVES), 'Unexpected already saved DAC-drive probe')
            line += ' ' + ' '.join(EXTRA_SAVES)
            save_count += 1
        rows.append(line)
    common.need(len(treated) == 28 and save_count == 1, 'Expected 28 reference switches and one save card')
    wave = copy.deepcopy(prior['wave'])
    wave['saved_signals'].extend(EXTRA_SAVES)
    bench = ('\n'.join(rows) + '\n').encode('ascii')
    digest = hashlib.sha256(bench).hexdigest()
    common.need(digest == REVIEWED_DECK_SHA, 'Reconstructed DAC-drive deck differs')
    return bench, dict(case=case, wave=wave, portable_sha256=digest,
                       baseline_job=PARENT_JOB, baseline_deck_sha256=PARENT_DECK_SHA,
                       audit_sha256=AUDIT_SHA, circuit_change='reference_tg_gate_nets_only')


def verify():
    files = {'sar7_dac_drive.py', 'sar7_dac_drive.sbatch', 'PLAN.json', 'HANDOFF_zh_TW.md', 'test_sar7_dac_drive.py'}
    entries = [line.split('  ', 1) for line in MANIFEST.read_text(encoding='ascii').splitlines()]
    common.need(len(entries) == len(files) and {name for _, name in entries} == files, 'Unexpected pilot manifest')
    for digest, name in entries:
        path = ROOT / name
        common.need(path.is_file() and path.resolve().parent == ROOT and common.sha(path) == digest,
                    'DAC-drive package file differs: ' + name)
    _, parent = fast.verify()
    common.need(parent['portable_sha256'] == PARENT_DECK_SHA, 'Expected original failed 1.75 GS/s deck')
    case = case_record()
    return case, build(case)[1]


def approval_record(root, meta, approved):
    return dict(approved=approved, platform='Olympus', campaign=SCHEMA, case_ids=[CASE_ID],
                authorized_run_root=str(root), design_source_sha256=common.sha(MANIFEST),
                deck_sha256_by_case={CASE_ID: meta['portable_sha256']})


def crossings_ps(time, values, threshold, lo, hi, origin):
    first = max(1, bisect_left(time, lo))
    last = min(len(time), bisect_right(time, hi) + 1)
    result = []
    for k in range(first, last):
        a, b = values[k - 1], values[k]
        rising = a < threshold <= b
        if rising or b <= threshold < a:
            at = time[k - 1] + (time[k] - time[k - 1]) * (threshold - a) / (b - a)
            if lo <= at <= hi:
                result.append([round((at - origin) / native.PS, 4), 'rise' if rising else 'fall'])
    return result


def observed_trials(values, wave):
    necessary = {'time', *EXTRA_SAVES, *wave['dac_pair'],
                 *(f'trial{k}' for k in BITS), 'conv', 'reset'}
    time = score.validate_trace_arrays(values, necessary, wave['stop_s'], wave['strobe_s'])
    half_vdd = wave['vdd_V'] / 2
    lsb = wave['lsb_V']
    output = []
    for conversion in wave['conversions']:
        for trial in conversion['trials']:
            k = trial['bit']
            launch, pre, read, release = [trial[t] for t in ('launch_s', 'pre_s', 'read_s', 'trial_release_s')]
            lo = launch - 3 * native.PS
            watched = [f'{prefix}{k}{ref}' for ref in 'zo' for prefix in ('c', 'cb', 'ff_c', 'ff_cb')]
            samples = {}
            for label, at in [('launch_minus_1ps', launch - native.PS), ('launch_plus_4ps', launch + 4 * native.PS),
                              ('precompare', pre), ('read', read)]:
                held = score.differential(time, values, wave['dac_pair'], at)[0]
                samples[label] = dict(held_diff_lsb=held / lsb,
                                      bot_p_mV=1000 * score.interpolate(time, values[f'b{k}p'], at),
                                      bot_n_mV=1000 * score.interpolate(time, values[f'b{k}n'], at))
            p, n = [values[signal] for signal in wave['dac_pair']]
            target = samples['read']['held_diff_lsb'] * lsb
            j = bisect_right(time, read) - 1
            stop = bisect_left(time, launch)
            while j >= stop and abs(p[j] - n[j] - target) <= lsb:
                j -= 1
            enter = (max(0, (time[j + 1] - launch) / native.PS)
                     if j + 1 <= bisect_right(time, read) - 1 else None)
            output.append(dict(conversion=conversion['index'], bit=k,
                               weights=dict(dac_precompare_to_read_lsb=(samples['read']['held_diff_lsb']
                                                                        - samples['precompare']['held_diff_lsb'])),
                               enter_read_plus_minus_1_lsb_and_remain_ps=enter,
                               gate_half_vdd_crossings_from_launch_ps={signal: crossings_ps(time, values[signal],
                                   half_vdd, lo, release, launch) for signal in watched}, samples=samples))
    return output


def summarize(report, root, case, meta):
    directory = root / CASE_ID
    wave, status, hashes = base.evidence(case, directory)
    common.need(report['execution_files_sha256'] == hashes, 'Different report provenance')
    live = common.raw_inventory(directory)
    common.need(common.matches_historical_inventory(status['raw_inventory'], live), 'Retained transient differs')
    traces = [item for item in live if item['path'] in ('raw/tranResponse.tran', base.review.RAW_NAME)]
    common.need(len(traces) == 1, 'Expected one physical retained transient')
    required = {'time', *EXTRA_SAVES, *wave['dac_pair'], *(f'trial{k}' for k in BITS), 'conv', 'reset'}
    raw = base.review.safe_raw(directory, dict(status, raw_inventory=live), traces[0]['path'].removeprefix('raw/'),
                               parser=partial(base.review.parse_selected, required=required))
    common.need(raw.unit('time') == 's' and raw.sweep_names == ['time'] and raw.sha256 == report['tran_sha256'],
                'DAC-drive data must be the verified SAR measurement waveform in seconds')
    details = observed_trials(raw.values, wave)
    rows = [row for row in report['conversions'] if row['scored']]
    common.need(len(rows) == report['tested_conversions'] == 12 and len(details) == 84,
                'Need all result rows and bit observations')
    cmp = fast.offset.error_metrics(rows, 'observed_comparator_code')
    reg = fast.offset.error_metrics(rows, 'observed_registered_code')
    unresolved = sum(t['decision'] is None for row in rows for t in row['trial_results'])
    agreement = all(row['observed_comparator_code'] is not None
                    and row['observed_comparator_code'] == row['observed_registered_code'] for row in rows)
    cm = [1000 * row['final_dac_common_mode_change_from_sample_V'] for row in rows]
    criterion = (unresolved == 0 and agreement and max(map(abs, cm)) <= 10 and cmp['max_abs_code_error'] <= 1
                 and cmp['wrong'] <= 6)
    _, _, after = base.evidence(case, directory)
    common.need(after == hashes, 'Evidence changed while summarizing')
    return dict(schema=SCHEMA, case_id=CASE_ID, stage='ideal_reference_tg_drive_diagnostic', baseline_job=PARENT_JOB,
                max_resolve_delay_s=report['max_observed_resolve_delay_s'], comparator=cmp, registered=reg,
                comparator_registered_agreement=agreement, unresolved_bits=unresolved,
                code_screen_under_ideal_drive=criterion, logic_smoke_pass=report['logic_smoke_pass'],
                final_dac_cm_change_mV=[min(cm), max(cm)], max_abs_sample_error_lsb=report['max_abs_sample_error_lsb'],
                job_id=report['slurm_task_id'], solver_seconds=report['solver_seconds'], raw_bytes=report['raw_bytes'],
                codes=[dict(expected=row['expected_code'], comparator=row['observed_comparator_code'],
                            registered=row['observed_registered_code']) for row in rows], timing=details,
                provenance=dict(manifest_sha256=common.sha(MANIFEST), portable_deck_sha256=meta['portable_sha256'],
                                parent_portable_deck_sha256=PARENT_DECK_SHA, parent_audit_sha256=AUDIT_SHA,
                                measurements_sha256=common.sha(directory / base.MEASUREMENT),
                                tran_sha256=report['tran_sha256'], execution_files_sha256=hashes))


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
    common.need(args.root is not None and args.approval is not None, 'Supply the isolated root and approval')
    root = common.checked_root(args.root)
    approval = args.approval.absolute()
    common.need(root.name.startswith('pam4_sar7_dac_drive_pilot_') and approval.parent == root,
                'Use a new DAC-drive campaign root with its own approval')
    if args.mode == 'approval-template':
        common.write_new(approval, approval_record(root, meta, False))
        return
    common.need(common.read(approval) == approval_record(root, meta, True), 'Approval must bind this root and deck')
    base.build, base.PLAN, base.MANIFEST, base.SCHEMA = build, PLAN, MANIFEST, SCHEMA
    base.TIMEOUT_S = 540
    if args.mode in ('stage', 'run'):
        common.need(args.model_root is not None, 'Use the original private model root')
        if args.mode == 'stage':
            print(base.stage(root, case, args.model_root))
            return
        report = base.run(root, case, args.model_root, approval)
    else:
        report = base.collect(root, case)
    result = summarize(report, root, case, meta)
    out = root / 'sar7_dac_drive_summary.json'
    if not out.exists():
        common.write_new(out, result)
    else:
        common.need(common.read(out) == result, 'Existing DAC-drive summary differs')
    print(json.dumps(dict(summary=str(out), sha256=common.sha(out),
                          code_screen_under_ideal_drive=result['code_screen_under_ideal_drive'])))


if __name__ == '__main__':
    main()
