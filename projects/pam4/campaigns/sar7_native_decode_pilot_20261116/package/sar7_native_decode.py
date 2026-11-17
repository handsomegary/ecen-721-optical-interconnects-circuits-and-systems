"""One native CDAC reference decoder candidate at 1.75 GS/s."""

import argparse
from bisect import bisect_left, bisect_right
import copy
from functools import partial
import hashlib
import json
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / 'SHA256SUMS.txt'
PLAN = ROOT / 'PLAN.json'
SCHEMA = 'pam4_sar7_native_decode_pilot_v1'
CASE_ID = 'sar7_14_tt_175gs_native_decode'
PARENT_JOB = '761321'
PARENT_DECK_SHA = '903d79a53dcc36162f08c198f9337bbf8fcfe94308bc6fa2c4cb79ad2c785032'
PARENT_MANIFEST_SHA = 'e049fa8bda238eb15777db392ec377634807d7f630eae51caa7b062372bf98d0'
ISOLATION_JOB = '761426'
ISOLATION_SUMMARY_SHA = 'fdcca5230efa8c6a8b534d54c4acd6ecdd2b290d2af4cfc0a55bd24a87625748'
REVIEWED_DECK_SHA = 'ecd325622c426dfe2c1f5dd42cb00ca30c59f238ba77764d7757af15dd04720a'
FAST = Path(os.environ.get('PAM4_SAR7_FAST_PACKAGE', ROOT.parent / 'PAM4_SAR7_FAST_PILOT_20261116')).resolve()
if hashlib.sha256((FAST / 'SHA256SUMS.txt').read_bytes()).hexdigest() != PARENT_MANIFEST_SHA:
    raise ValueError('Measured 761321 dependency manifest differs')
sys.path.insert(0, str(FAST))
import sar7_fast as fast


base, common, native, score = fast.base, fast.common, fast.native, fast.base.score
BITS = native.BITS
WAITS = (42, 40, 24, 17, 13, 10, 8)
READS = (39, 42, 38, 39, 42, 44, 54)
EXTRA_SAVES = tuple(f'{prefix}{bit}{ref}' for bit in BITS for ref in 'zo' for prefix in ('c', 'cb')) + tuple(
    f'b{bit}{leg}' for bit in BITS for leg in 'pn') + ('V_RHI:p', 'V_RLO:p')
PLAN_RECORD = dict(schema=SCHEMA, cases=[dict(case_id=CASE_ID, parent_job=PARENT_JOB,
                   parent_deck_sha256=PARENT_DECK_SHA, isolation_job=ISOLATION_JOB,
                   isolation_summary_sha256=ISOLATION_SUMMARY_SHA, waits_ps=list(WAITS), reads_ps=list(READS))])


def case_record():
    common.need(common.read(PLAN) == PLAN_RECORD, 'Expected the frozen one-case design and timing plan')
    return dict(fast.case_record(), case_id=CASE_ID)


def timing_schedule():
    launch = 78
    schedule = {}
    for bit, wait, observe in zip(BITS, WAITS, READS, strict=True):
        compare, read = launch + wait, launch + wait + observe
        schedule[bit] = (launch, compare, read, read + 2)
        launch = read + 3
    common.need(schedule[0] == (486, 494, 548, 550), 'Timing budget differs')
    return schedule


def decoder_subcircuits():
    _, (_, _, n, p) = native.read_cdf(base.review.R5 / 'quiet.scs')
    yield 'subckt SAR_OAI21 (a b en y vdd)'
    for name, pins in (('MN1', ('y', 'a', 'nx', '0')), ('MN2', ('y', 'b', 'nx', '0')),
                       ('MN3', ('nx', 'en', '0', '0'))):
        yield native.mos(n, name, pins)
    for name, pins in (('MP1', ('y', 'a', 'px', 'vdd')), ('MP2', ('px', 'b', 'vdd', 'vdd')),
                       ('MP3', ('y', 'en', 'vdd', 'vdd'))):
        yield native.mos(p, name, pins)
    yield 'ends SAR_OAI21'
    yield 'subckt SAR_NOR3 (a b enb y vdd)'
    for number, input_name in enumerate(('a', 'b', 'enb'), 1):
        yield native.mos(n, f'MN{number}', ('y', input_name, '0', '0'))
    for name, pins in (('MP1', ('y', 'a', 'px', 'vdd')), ('MP2', ('px', 'b', 'py', 'vdd')),
                       ('MP3', ('py', 'enb', 'vdd', 'vdd'))):
        yield native.mos(p, name, pins)
    yield 'ends SAR_NOR3'


def decoder_instances(bit):
    trial = f'trial{bit}'
    for side, pad in (('p', ''), ('n', 'd_')):
        q = f'q{bit}{side}'
        c_o, cb_o = f'{pad}c{bit}o', f'{pad}cb{bit}o'
        c_z, cb_z = f'{pad}c{bit}z', f'{pad}cb{bit}z'
        yield f'XNDO{side}{bit} ({trial} {q} conv {cb_o} vdd) SAR_OAI21'
        yield f'XNDZ{side}{bit} ({trial} {q} convb {c_z} vdd) SAR_NOR3'
        yield f'XNDIO{side}{bit} ({cb_o} {c_o} vdd) SAR_INV'
        yield f'XNDIZ{side}{bit} ({c_z} {cb_z} vdd) SAR_INV'
        if side == 'n':
            for ref, c, cb in (('O', c_o, cb_o), ('Z', c_z, cb_z)):
                for leg in ('P', 'N'):
                    yield f'XNDLOAD{bit}{ref}{leg} (rcm rcm {c} {cb} vdd) SAR_TG'


def build(case):
    common.need(case == case_record(), 'Only the single frozen decoder pilot is supported')
    source, prior = fast.build(fast.case_record())
    common.need(prior['portable_sha256'] == PARENT_DECK_SHA, 'Wrong native 761321 bench')
    schedule = timing_schedule()
    clocks, old_decoders = {}, {}
    for step, bit in enumerate(BITS):
        launch, compare, _, release = schedule[bit]
        clocks[native.pulse(f'trial{bit}', 78 + 66 * step, 143 + 66 * step)] = native.pulse(f'trial{bit}', launch, release)
        clocks[native.pulse(f'clk{bit}', 99 + 66 * step, 560)] = native.pulse(f'clk{bit}', compare, 560)
        old_decoders.update({f'XZb{bit} (conv bit{bit}b cb{bit}z vdd) SAR_NAND': bit,
                             f'XZ{bit} (cb{bit}z c{bit}z vdd) SAR_INV': None,
                             f'XOb{bit} (conv bit{bit} cb{bit}o vdd) SAR_NAND': None,
                             f'XO{bit} (cb{bit}o c{bit}o vdd) SAR_INV': None})
    original = source.decode('ascii').splitlines()
    common.need(all(original.count(card) == 1 for card in (*clocks, *old_decoders, 'ends SAR_NOR')),
                'Frozen native decoder, clock or gate definitions differ')
    rows, save_count = [], 0
    for line in original:
        if line in old_decoders:
            bit = old_decoders[line]
            if bit is not None:
                rows.extend(decoder_instances(bit))
            continue
        if line.startswith('save '):
            common.need(not set(line.split()) & set(EXTRA_SAVES), 'Unexpected already saved probe')
            line += ' ' + ' '.join(EXTRA_SAVES)
            save_count += 1
        rows.append(clocks.get(line, line))
        if line == 'ends SAR_NOR':
            rows.extend(decoder_subcircuits())
    common.need(save_count == 1, 'Expected one Spectre save card')
    wave = copy.deepcopy(prior['wave'])
    wave['saved_signals'].extend(EXTRA_SAVES)
    for conversion in wave['conversions']:
        start = conversion['index'] * wave['period_s']
        conversion['read_late_s'] = start + native.timing(557)
        for trial in conversion['trials']:
            launch, compare, read, release = schedule[trial['bit']]
            trial.update(launch_s=start + native.timing(launch), pre_s=start + native.timing(compare - .5),
                         compare_s=start + native.timing(compare), read_s=start + native.timing(read),
                         trial_release_s=start + native.timing(release))
    bench = ('\n'.join(rows) + '\n').encode('ascii')
    digest = hashlib.sha256(bench).hexdigest()
    common.need(digest == REVIEWED_DECK_SHA, 'Native decoder portable netlist SHA: ' + digest)
    return bench, dict(case=case, wave=wave, portable_sha256=digest, baseline_job=PARENT_JOB,
                       baseline_deck_sha256=PARENT_DECK_SHA, isolation_summary_sha256=ISOLATION_SUMMARY_SHA,
                       schedule_ps={str(bit): list(times) for bit, times in schedule.items()})


def verify():
    files = {'sar7_native_decode.py', 'sar7_native_decode.sbatch', 'PLAN.json', 'HANDOFF_zh_TW.md', 'test_sar7_native_decode.py'}
    entries = [line.split('  ', 1) for line in MANIFEST.read_text(encoding='ascii').splitlines()]
    common.need(len(entries) == len(files) and {name for _, name in entries} == files, 'Unexpected manifest inventory')
    for digest, name in entries:
        path = ROOT / name
        common.need(path.is_file() and path.resolve().parent == ROOT and common.sha(path) == digest,
                    'Package file differs: ' + name)
    _, parent = fast.verify()
    common.need(parent['portable_sha256'] == PARENT_DECK_SHA, 'Original 761321 dependency differs')
    case = case_record()
    return case, build(case)[1]


def approval_record(root, meta, approved):
    return dict(approved=approved, platform='Olympus', campaign=SCHEMA, case_ids=[CASE_ID],
                authorized_run_root=str(root), design_source_sha256=common.sha(MANIFEST),
                deck_sha256_by_case={CASE_ID: meta['portable_sha256']})


def read_code(values, time, conversion, at, vdd):
    decisions = [score.classify(*(score.interpolate(time, values[k], at) for k in pair), vdd)
                 for pair in conversion['code_pairs']]
    return None if None in decisions else sum(decision << bit for decision, bit in zip(decisions, BITS, strict=True))


def overlap_proxy(time, traces, lo, hi, half):
    # Each reference path counts as possibly on when either TG gate crosses the half-supply proxy.
    first, stop = bisect_left(time, lo), bisect_right(time, hi)
    co, cbo, cz, cbz = traces
    active = [index for index in range(first, stop)
              if (co[index] >= half or cbo[index] <= half) and (cz[index] >= half or cbz[index] <= half)]
    runs = []
    for index in active:
        if not runs or runs[-1][-1] + 1 != index:
            runs.append([index])
        else:
            runs[-1].append(index)
    return dict(samples=len(active), events=len(runs), max_sample_span_ps=max(
        ((time[run[-1]] - time[run[0]]) / native.PS for run in runs), default=0.0))


def crossings(time, trace, lo, hi, threshold, origin):
    result = []
    for i in range(max(1, bisect_left(time, lo)), min(len(time), bisect_right(time, hi) + 1)):
        a, b = trace[i - 1], trace[i]
        if (a < threshold <= b) or (b <= threshold < a):
            when = time[i - 1] + (time[i] - time[i - 1]) * (threshold - a) / (b - a)
            if lo <= when <= hi:
                result.append([(when - origin) / native.PS, 'rise' if b > a else 'fall'])
    return result


def screen(rows, observed, cm):
    cmp = fast.offset.error_metrics(rows, 'observed_comparator_code')
    reg = fast.offset.error_metrics(observed, 'observed_registered_code')
    unresolved = sum(trial['decision'] is None for row in rows for trial in row['trial_results'])
    agreement = all(c['observed_comparator_code'] is not None and
                    c['observed_comparator_code'] == r['observed_registered_code']
                    for c, r in zip(rows, observed, strict=True))
    passed = (unresolved == 0 and agreement and max(map(abs, cm)) <= 10 and
              cmp['max_abs_code_error'] is not None and cmp['max_abs_code_error'] <= 1 and cmp['wrong'] <= 6)
    return dict(screen_pass=passed, logic_smoke_pass=unresolved == 0 and agreement and cmp['wrong'] == 0,
                comparator=cmp, registered=reg, unresolved_bits=unresolved,
                comparator_registered_agreement=agreement, final_dac_cm_change_mV=[min(cm), max(cm)])


def summarize(report, root, case, meta):
    directory = root / CASE_ID
    wave, status, hashes = base.evidence(case, directory)
    common.need(report['execution_files_sha256'] == hashes, 'Different report provenance')
    live = common.raw_inventory(directory)
    common.need(common.matches_historical_inventory(status['raw_inventory'], live), 'Retained transient differs')
    traces = [item for item in live if item['path'] in ('raw/tranResponse.tran', base.review.RAW_NAME)]
    common.need(len(traces) == 1, 'Expected one physical retained transient')
    required = {'time', *EXTRA_SAVES, *wave['dac_pair'], 'conv', 'reset',
                *[f'q{k}{side}' for k in BITS for side in 'pn'],
                *[f'XCMP{k}.{node}' for k in BITS for node in 'xy'],
                *[pin for cv in wave['conversions'] for pair in cv['code_pairs'] for pin in pair]}
    raw = base.review.safe_raw(directory, dict(status, raw_inventory=live), traces[0]['path'].removeprefix('raw/'),
                               parser=partial(base.review.parse_selected, required=required))
    common.need(raw.unit('time') == 's' and raw.sweep_names == ['time'] and raw.sha256 == report['tran_sha256']
                and all(raw.unit(key) == 'A' for key in ('V_RHI:p', 'V_RLO:p')), 'Wrong time/current trace or source')
    values = raw.values
    time = score.validate_trace_arrays(values, required, wave['stop_s'], wave['strobe_s'])
    rows = [row for row in report['conversions'] if row['scored']]
    common.need(len(rows) == len(wave['conversions']) == report['tested_conversions'] == 12
                and all(len(row['trial_results']) == 7 for row in rows), 'Need all 12 conversions and 84 trials')
    cm_554, cm_557, late_rows, codes, details, rail_currents = [], [], [], [], [], []
    vdd, half, lsb = wave['vdd_V'], wave['vdd_V'] / 2, wave['lsb_V']
    for conversion, row in zip(wave['conversions'], rows, strict=True):
        end, late = conversion['end_s'], conversion['read_late_s']
        old_code = row['observed_registered_code']
        common.need(read_code(values, time, conversion, end, vdd) == old_code, 'Base readback differs at 554 ps')
        late_code = read_code(values, time, conversion, late, vdd)
        late_rows.append(dict(expected_code=row['expected_code'], observed_registered_code=late_code))
        codes.append(dict(expected=row['expected_code'], comparator=row['observed_comparator_code'],
                          registered_554=old_code, registered_557=late_code))
        cm_554.append(1000 * row['final_dac_common_mode_change_from_sample_V'])
        _, cm = score.differential(time, values, wave['dac_pair'], late)
        cm_557.append(1000 * (cm - row['sample_dac_common_mode_V']))
        active_lo = conversion['index'] * wave['period_s'] + native.timing(73)
        first, stop = bisect_left(time, active_lo), bisect_right(time, late)
        rail_currents.append({key: max(map(abs, values[key][first:stop])) for key in ('V_RHI:p', 'V_RLO:p')})
        for trial, scored in zip(conversion['trials'], row['trial_results'], strict=True):
            bit = trial['bit']
            launch, pre, read, release = (trial[k] for k in ('launch_s', 'pre_s', 'read_s', 'trial_release_s'))
            gates = (f'c{bit}o', f'cb{bit}o', f'c{bit}z', f'cb{bit}z')
            drive_edges = {g: crossings(time, values[g], launch - native.timing(3), release, half, launch) for g in gates}
            snapshots = {}
            for label, at in (('before_launch', launch - native.timing(1)), ('precompare', pre),
                              ('read', read), ('after_release_1ps', release + native.timing(1))):
                held, _ = score.differential(time, values, wave['dac_pair'], at)
                snapshots[label] = dict(held_diff_lsb=held / lsb, p_bottom_V=score.interpolate(time, values[f'b{bit}p'], at),
                                        n_bottom_V=score.interpolate(time, values[f'b{bit}n'], at),
                                        q_V=[score.interpolate(time, values[p], at) for p in trial['cmp_pair']],
                                        cmp_xy_V=[score.interpolate(time, values[f'XCMP{bit}.{node}'], at) for node in 'xy'])
            p, n = (values[k] for k in wave['dac_pair'])
            last = bisect_right(time, read) - 1
            j, stop = last, bisect_left(time, launch)
            target = snapshots['read']['held_diff_lsb'] * lsb
            while j >= stop and abs(p[j] - n[j] - target) <= lsb:
                j -= 1
            enter = ((time[j + 1] - launch) / native.PS) if j + 1 <= last else None
            stable = scored['stable_rail_delay_s']
            details.append(dict(conversion=conversion['index'], bit=bit, decision=scored['decision'],
                                sampled_margin_ps=None if stable is None else (scored['compare_to_read_s'] - stable) / native.PS,
                                gate_half_vdd_crossings_ps=drive_edges,
                                overlap_proxy_full_conversion=overlap_proxy(time, [values[g] for g in gates], active_lo, late, half),
                                first_remains_in_read_plus_minus_lsb_after_launch_ps=enter, snapshots=snapshots))
    _, _, after = base.evidence(case, directory)
    common.need(after == hashes, 'Evidence changed while summarizing')
    return dict(schema=SCHEMA, case_id=CASE_ID, stage='native_decoder_retimed_tt_12_centers',
                sampling_rate_gsps=1 / wave['period_s'] / 1e9, schedule_ps=meta['schedule_ps'],
                primary_readout_ps=557, readout_554=screen(rows, rows, cm_554), readout_557=screen(rows, late_rows, cm_557),
                max_abs_sample_error_lsb=report['max_abs_sample_error_lsb'],
                job_id=report['slurm_task_id'], solver_seconds=report['solver_seconds'], raw_bytes=report['raw_bytes'],
                codes=codes, timing=details, ref_source_peak_abs_A_during_conv=rail_currents,
                provenance=dict(manifest_sha256=common.sha(MANIFEST), portable_deck_sha256=meta['portable_sha256'],
                                parent_portable_deck_sha256=PARENT_DECK_SHA, isolation_summary_sha256=ISOLATION_SUMMARY_SHA,
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
    common.need(args.root is not None and args.approval is not None, 'Supply isolated root and approval path')
    root, approval = common.checked_root(args.root), args.approval.absolute()
    common.need(root.name.startswith('pam4_sar7_native_decode_pilot_') and approval.parent == root,
                'Use a new decoder pilot root with its own approval')
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
    out = root / 'sar7_native_decode_summary.json'
    if not out.exists():
        common.write_new(out, result)
    else:
        common.need(common.read(out) == result, 'Existing decoder summary differs')
    print(json.dumps(dict(summary=str(out), sha256=common.sha(out), screen_pass=result['readout_557']['screen_pass'])))


if __name__ == '__main__':
    main()
