"""One physical CML drive2 test; immutable case21 SAR timing and acceptance gates."""

import argparse
from bisect import bisect_left, bisect_right
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from types import FunctionType, SimpleNamespace

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / 'SHA256SUMS.txt'
PLAN = ROOT / 'PLAN.json'
AUTHORIZATION = ROOT / 'AUTHORIZATION.json'
SCHEMA = 'pam4_sar7_cml_drive2_v1'
CASE_ID = 'sar7_23_tt_175gs_cml_drive2'
PARENT_MANIFEST_SHA = '40a490ab88adfb1bbc370e52f80ced9bfd7954f5be56e3adc93dfcb8f51d650b'
PARENT_DECK_SHA = '532f9e8f79e9d4c9f668080a76a74b63b9681a01115f16703bc79e12754f70ec'
PARENT_SUMMARY_SHA = '7b93590f85c18b85b1cca6dae343d5e550d7b582d3922ee01a3fdb57a1eea851'
SENTINEL_SUMMARY_SHA = 'e5f8635a27f1e68a67f32499340ccf4cc3e43cb43c7242a1894235450bdb1d82'
PARENT = Path(os.environ.get('PAM4_SAR7_ACCEPT_GAP_PACKAGE', ROOT.parent / 'PAM4_SAR7_ACCEPT_GAP_PILOT_20261117')).resolve()
if hashlib.sha256((PARENT / 'SHA256SUMS.txt').read_bytes()).hexdigest() != PARENT_MANIFEST_SHA:
    raise ValueError('Expected immutable measured case21 physical source')
sys.path.insert(0, str(PARENT))
import sar7_accept_gap as parent

base, common, native, score = parent.base, parent.common, parent.native, parent.score
SUMMARY_ENGINE, SUMMARY_PARENT, Q_PARENT = parent.SUMMARY_ENGINE, parent.SUMMARY_PARENT, parent.Q_PARENT
STARTS = datetime(2026, 11, 17, 13, 55, tzinfo=timezone.utc)
TIMEOUT_S = 540
WAITS, EVALS, GUARD_PS = parent.WAITS, parent.EVALS, parent.GUARD_PS
SUPPLY_V, LOAD_OHM, BRIDGE_OHM = .9, 250, 125
TARGETS = {
    'MSENSE_P': dict(ports=('sensen', 'mp', 'sem', '0'), clone='MSENSE_P_D2'),
    'MSENSE_N': dict(ports=('sensep', 'mn', 'sep', '0'), clone='MSENSE_N_D2'),
    'MTAIL_P': dict(ports=('sem', 'sbias', '0', '0'), clone='MTAIL_P_D2'),
    'MTAIL_N': dict(ports=('sep', 'sbias', '0', '0'), clone='MTAIL_N_D2'),
}
R_TARGETS = {
    'RSENSE_P': ('svdd', 'sensen', 500, 250),
    'RSENSE_N': ('svdd', 'sensep', 500, 250),
    'RSENSE_DEG': ('sem', 'sep', 250, 125),
}
AUTH_RECORD = dict(schema='pam4_sar7_authorization_v2',
    user_quote='SAR7如果一直修不好你叫codex看看相關論文 然後也可以換方向 由codex決定',
    source_note='20261117T0755_user_delegates_sar7_papers_direction.md',
    source_note_sha256='d9491abfb1429caf097c1c798d763d6529264fb3fa9cbbf2b82cd78b0d4183ea',
    starts_utc='2026-11-17T13:55:00Z', no_expiry=True,
    scope='One short whole-SAR TT CML drive2 physical pilot; original ADC acceptance unchanged',
    max_solver_cases_this_packet=1, max_accepted_slurm_jobs=1, cpus_this_job=1, max_concurrent_sar7_jobs=1,
    c2_temporary_throttle=dict(original=5, temporary=4, restore=5),
    excluded=['new long campaigns', 'PVT', '112GS/s integration', 'other C2 changes', 'other projects'])
PLAN_RECORD = dict(schema=SCHEMA, authorization=AUTH_RECORD, cases=[dict(case_id=CASE_ID,
    parent_job='761700', parent_manifest_sha256=PARENT_MANIFEST_SHA, parent_deck_sha256=PARENT_DECK_SHA,
    source_summary_sha256=PARENT_SUMMARY_SHA, sentinel_evidence_summary_sha256=SENTINEL_SUMMARY_SHA,
    physical_scale=2, complete_cdf_copies_added=4, load_resistance_ohm=LOAD_OHM, bridge_resistance_ohm=BRIDGE_OHM,
    supply_V=SUPPLY_V, bias_V=.5, schedule_unchanged=True, waits_ps=list(WAITS), evals_ps=list(EVALS),
    primary_readout_ps=565, active_cm_readout_ps=552, diagnostic_readouts_ps=[563, 554, 557],
    changed_pulse_rows=0, changed_save_rows=0, original_adc_gates_unchanged=True,
    max_solver_cases=1, automatic_followup=False)])
FILES = {'sar7_cml_drive2.py', 'test_sar7_cml_drive2.py', 'c2_slot_lease.py', 'test_c2_slot_lease.py',
         'sar7_cml_drive2.sbatch', 'PLAN.json', 'AUTHORIZATION.json', 'HANDOFF_zh_TW.md'}


def case_record():
    common.need(common.read(PLAN) == PLAN_RECORD and common.read(AUTHORIZATION) == AUTH_RECORD, 'Frozen plan/authorization differs')
    return dict(parent.case_record(), case_id=CASE_ID, schedule_unchanged=True, cml_drive_scale=2)


def timing_schedule():
    return parent.timing_schedule()


def _parent_source():
    source, old = parent.build(parent.case_record())
    common.need(old['portable_sha256'] == PARENT_DECK_SHA and hashlib.sha256(source).hexdigest() == PARENT_DECK_SHA,
                'Wrong immutable case21 source bytes')
    return source, old


def _top_rows(source):
    selected = {}; depth = 0
    for row in source.decode('ascii').splitlines():
        if row.startswith('subckt '): depth += 1
        if row.startswith('ends '): depth -= 1
        common.need(depth >= 0, 'Unbalanced subcircuit boundaries')
        if depth == 0 and row:
            name = row.split()[0]
            selected.setdefault(name, []).append(row)
    common.need(depth == 0, 'Unbalanced subcircuit boundaries')
    return selected


def physical_patch(source):
    reference, _ = _parent_source(); expected = _top_rows(reference); actual = _top_rows(source)
    for name, spec in TARGETS.items():
        common.need(len(actual.get(name, [])) == 1 and actual[name] == expected[name], 'Wrong, missing or duplicate CML card: ' + name)
        ports = re.search(r'\(([^)]+)\)', actual[name][0]).group(1).split()
        common.need(tuple(ports) == spec['ports'] and spec['clone'] not in actual, 'Wrong CML ports or preexisting replica')
    replacements = {}
    for name, (first, second, old, new) in R_TARGETS.items():
        original = f'{name} ({first} {second}) resistor r={old}'
        common.need(actual.get(name) == [original] and expected.get(name) == [original], 'Wrong, missing or duplicate CML resistor: ' + name)
        replacements[original] = f'{name} ({first} {second}) resistor r={new}'
    output = []
    for row in source.decode('ascii').splitlines():
        name = row.split()[0] if row else ''
        output.append(replacements.get(row, row))
        if name in TARGETS:
            output.append(TARGETS[name]['clone'] + row[len(name):])
    return ('\n'.join(output) + '\n').encode('ascii'), dict(original_mos_cards=4, complete_cdf_replicas_added=4,
        load_resistors_halved=2, bridge_resistors_halved=1, changed_pulse_rows=0, changed_save_rows=0)


def build(case):
    common.need(case == case_record(), 'Only the frozen whole-SAR case23 drive2 test is supported')
    source, old = _parent_source(); bench, counts = physical_patch(source)
    wave = copy.deepcopy(old['wave'])
    return bench, dict(case=case, wave=wave, portable_sha256=hashlib.sha256(bench).hexdigest(),
        parent_job='761700', parent_manifest_sha256=PARENT_MANIFEST_SHA, parent_deck_sha256=PARENT_DECK_SHA,
        parent_summary_sha256=PARENT_SUMMARY_SHA, sentinel_evidence_summary_sha256=SENTINEL_SUMMARY_SHA,
        schedule_ps=copy.deepcopy(old['schedule_ps']), primary_readout_ps=565, diagnostic_readouts_ps=[563, 554, 557],
        clock_off_ps=568, changed_pulse_rows=0, next_launch_midpoint_guard_ps=GUARD_PS,
        finite_trial_edge_starts_at_previous_read=True, physical_changes=True,
        authorization=AUTH_RECORD, authorization_sha256=common.sha(AUTHORIZATION),
        circuit_change=dict(kind='cml_drive2', physical_scale=2, counts=counts,
            complete_original_cdf_cards_preserved=True, all_other_devices_unchanged=True,
            bias_and_supply_unchanged=True, timing_unchanged=True, saves_unchanged=True),
        inherited_circuit_change=copy.deepcopy(old['circuit_change']),
        relative_to_parent=dict(physical_changes=True, changed_pulse_rows=0, parent_job='761700'),
        automatic_followup=False)


def verify():
    entries = [line.split('  ', 1) for line in MANIFEST.read_text(encoding='ascii').splitlines()]
    common.need(len(entries) == len(FILES) and {name for digest, name in entries} == FILES, 'Unexpected package inventory')
    for digest, name in entries:
        path = ROOT / name
        common.need(path.resolve().parent == ROOT and common.sha(path) == digest and b'\r' not in path.read_bytes(), 'Package differs or is not LF: ' + name)
    common.need(b'\r' not in MANIFEST.read_bytes(), 'Manifest must use LF')
    _, old = parent.verify()
    common.need(common.sha(parent.MANIFEST) == PARENT_MANIFEST_SHA and old['portable_sha256'] == PARENT_DECK_SHA, 'Nested frozen parent differs')
    case = case_record(); return case, build(case)[1]


def approval_record(root, meta, approved):
    return dict(approved=approved, platform='Olympus', campaign=SCHEMA, case_ids=[CASE_ID],
        authorized_run_root=str(root), design_source_sha256=common.sha(MANIFEST), deck_sha256_by_case={CASE_ID: meta['portable_sha256']})


def execution_namespace():
    context = dict(base.run.__globals__)
    context.update(build=build, PLAN=PLAN, MANIFEST=MANIFEST, SCHEMA=SCHEMA, TIMEOUT_S=TIMEOUT_S,
        verify_approval=lambda case, path: common.need(common.read(path) == approval_record(path.parent, build(case)[1], True), 'Exact case23 approval differs'))
    context['evidence'] = FunctionType(base.evidence.__code__, context)
    context['stage'] = FunctionType(base.stage.__code__, context)
    context['collect'] = FunctionType(base.collect.__code__, context)
    return context


def _summary_globals(review=None):
    context = dict(SUMMARY_ENGINE.summarize.__globals__)
    base_proxy = SimpleNamespace(**vars(base)); base_proxy.evidence = execution_namespace()['evidence']
    if review is not None: base_proxy.review = review
    context.update(CASE_ID=CASE_ID, SCHEMA=SCHEMA, MANIFEST=MANIFEST, PARENT_MANIFEST_SHA=PARENT_MANIFEST_SHA,
        PARENT_DECK_SHA=PARENT_DECK_SHA, PARENT_SUMMARY_SHA=PARENT_SUMMARY_SHA,
        AUTHORIZATION=AUTHORIZATION, AUTH_RECORD=AUTH_RECORD, base=base_proxy)
    return context


def child_summary_function(q_summary):
    return FunctionType(SUMMARY_ENGINE.child_summary_function.__code__, _summary_globals())(q_summary)


def cml_diagnostics(values, wave):
    required = {'time', 'sensep', 'sensen', 'V_SENSE_DD:p', *wave['dac_pair']}
    common.need(required <= values.keys(), 'Missing existing CML diagnostics trace')
    time = values['time']; supply = values['V_SENSE_DD:p']
    def at(node, instant): return score.interpolate(time, values[node], instant)
    def point(instant):
        held, held_cm = score.differential(time, values, wave['dac_pair'], instant)
        sense, sense_cm = score.differential(time, values, ('sensep', 'sensen'), instant)
        signed = at('V_SENSE_DD:p', instant)
        analytical = (2 * SUPPLY_V - at('sensep', instant) - at('sensen', instant)) / LOAD_OHM
        return dict(at_s=instant, held_diff_lsb=held / wave['lsb_V'], held_common_mode_V=held_cm,
            sense_diff_lsb=sense / wave['lsb_V'], sense_common_mode_V=sense_cm,
            signed_source_current_A=signed, supply_draw_current_A=-signed, analytical_load_current_A=analytical,
            analytical_minus_draw_A=analytical + signed, supply_power_W=-SUPPLY_V * signed)
    windows = []; trials = []
    for conversion in wave['conversions']:
        origin = conversion['index'] * wave['period_s']; first = origin + native.timing(78); last = origin + native.timing(565)
        lo, hi = bisect_right(time, first), bisect_left(time, last)
        points = [point(instant) for instant in (first, *time[lo:hi], last)]
        duration = last - first
        signed_charge = sum((b['at_s'] - a['at_s']) * (a['signed_source_current_A'] + b['signed_source_current_A']) / 2 for a, b in zip(points, points[1:]))
        draw = [p['supply_draw_current_A'] for p in points]
        windows.append(dict(conversion=conversion['index'], start_ps=78, end_ps=565,
            mean_signed_source_current_A=signed_charge / duration, mean_draw_current_A=-signed_charge / duration,
            mean_supply_power_W=-SUPPLY_V * signed_charge / duration, supply_energy_J=-SUPPLY_V * signed_charge,
            minimum_draw_current_A=min(draw), maximum_draw_current_A=max(draw),
            maximum_abs_analytical_minus_draw_A=max(abs(p['analytical_minus_draw_A']) for p in points),
            sense_common_mode_range_V=[min(p['sense_common_mode_V'] for p in points), max(p['sense_common_mode_V'] for p in points)]))
        for trial in conversion['trials']:
            phases = [('before_launch', trial['launch_s'] - native.timing(1)), ('precompare', trial['pre_s']),
                ('compare', trial['compare_s']), ('compare_plus_15ps', trial['compare_s'] + native.timing(15)),
                ('compare_plus_30ps', trial['compare_s'] + native.timing(30)), ('read', trial['read_s']),
                ('after_release_1ps', trial['trial_release_s'] + native.timing(1))]
            trials.append(dict(conversion=conversion['index'], bit=trial['bit'], phases={label: point(instant) for label, instant in phases}))
    common.need(len(windows) == 12 and len(trials) == 84, 'Expected twelve CML windows and84 trial records')
    return dict(active_windows=windows, trial_phase_points=trials, trial_records=84, active_window_ps=[78, 565],
        load_resistance_ohm=LOAD_OHM, current_sign='Supply draw is negative of V_SENSE_DD:p',
        analytical_current='(1.8-sensep-sensen)/250 amperes',
        limits='Additive diagnostics only; output/input loading, evolving input and comparator kickback remain coupled; no new acceptance threshold or fitted gain')


def summarize(report, root, case, meta):
    original_review = base.review; captured = []
    def capture_raw(*args, **kwargs):
        common.need(not captured, 'Only one custom-summary raw parse is permitted')
        raw = original_review.safe_raw(*args, **kwargs)
        common.need(raw.unit('V_SENSE_DD:p') == 'A' and all(raw.unit(node) == 'V' for node in ('sensep', 'sensen')), 'Wrong existing CML current/voltage units')
        captured.append(raw)
        return raw
    review_proxy = SimpleNamespace(**vars(original_review)); review_proxy.safe_raw = capture_raw
    context = _summary_globals(review_proxy)
    context['child_summary_function'] = FunctionType(SUMMARY_ENGINE.child_summary_function.__code__, context)
    result = FunctionType(SUMMARY_ENGINE.summarize.__code__, context)(report, root, case, meta)
    common.need(len(captured) == 1 and result['selected_parser']['summary_psf_parse_count'] == 1, 'Expected one captured custom-summary parse')
    result.update(stage='physical_cml_drive2_tt_12_centers', circuit_change=meta['circuit_change'],
        inherited_circuit_change=meta['inherited_circuit_change'], relative_to_parent=meta['relative_to_parent'],
        cml_diagnostic=cml_diagnostics(captured[0].values, meta['wave']),
        sentinel_evidence_summary_sha256=SENTINEL_SUMMARY_SHA, automatic_followup=False,
        mechanism_limits='Parallel CML devices and halved resistors preserve ideal DC ratios but double input loading; improved output response, input charge loss, kickback and gain/CM shifts must be distinguished; static sentinel success is not ADC validation')
    return result


def check_started(now):
    common.need(now >= STARTS, 'New authorization has not started')


def validate_submission(text, jobid, now):
    common.need(re.fullmatch(r'\d+', jobid or '') is not None, 'SLURM_JOB_ID must contain digits')
    ids = re.findall(r'(?:^|\s)JobId=(\S+)', text); times = re.findall(r'(?:^|\s)SubmitTime=(\S+)', text)
    common.need(ids == [jobid] and len(times) == 1 and re.fullmatch(r'\d+', times[0]) is not None, 'Ambiguous Slurm submission evidence')
    submitted = datetime.fromtimestamp(int(times[0]), timezone.utc)
    common.need(STARTS <= submitted <= now, 'Job submission must be after new authorization start and not in the future')
    return dict(slurm_job_id=jobid, submit_time_utc=submitted.isoformat(), authorization_source_sha256=AUTH_RECORD['source_note_sha256'])


def query_submission(now):
    check_started(now); jobid = os.environ.get('SLURM_JOB_ID', '')
    common.need(re.fullmatch(r'\d+', jobid) is not None, 'Run requires an actual Slurm job')
    env = dict(os.environ, SLURM_TIME_FORMAT='%s', TZ='UTC', LC_ALL='C')
    result = subprocess.run(['scontrol', '--oneliner', 'show', 'job', jobid], env=env, timeout=15, check=True, capture_output=True, text=True)
    return validate_submission(result.stdout, jobid, now)


def existing_stage(root, case, model_root):
    directory = root / CASE_ID
    common.need(directory.is_dir() and directory == directory.resolve(strict=True), 'Run requires existing real byte-exact stage')
    source, meta = build(case); proof = base.original.model_preflight.verify_private_kit(model_root, 'tt')
    token = base.review.gm_center64.BASE.MODEL_TOKEN.encode('ascii'); model = proof['model_root'].encode('utf-8'); bench = source.replace(token, model)
    common.need(source.count(token) == 1 and bench.replace(model, token) == source, 'Nonreversible model root substitution')
    expected = dict(meta, model_preflight=proof, bench_sha256=hashlib.sha256(bench).hexdigest())
    common.need(common.read(directory / 'case.json') == expected and (directory / 'bench.scs').read_bytes() == bench, 'Existing staged case23 differs')
    return directory


def stage_for_run(root, case, model_root, now):
    receipt = query_submission(now)
    return existing_stage(root, case, model_root), receipt


def run(root, case, model_root, approval):
    directory, receipt = stage_for_run(root, case, model_root, datetime.now(timezone.utc))
    receipt_path = root / 'submission_proof.json'
    if receipt_path.exists(): common.need(common.read(receipt_path) == receipt, 'Existing submission proof differs')
    else: common.write_new(receipt_path, receipt)
    context = execution_namespace(); context['stage'] = existing_stage
    return FunctionType(base.run.__code__, context)(root, case, model_root, approval)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('verify', 'approval-template', 'stage', 'run', 'collect-only'))
    parser.add_argument('--root', type=Path); parser.add_argument('--approval', type=Path); parser.add_argument('--model-root', type=Path)
    args = parser.parse_args(); case, meta = verify()
    if args.mode == 'verify': print(CASE_ID, meta['portable_sha256']); return
    common.need(args.root is not None and args.approval is not None, 'Supply isolated root and approval')
    root = common.checked_root(args.root); approval = args.approval.absolute()
    common.need(root.name.startswith('pam4_sar7_cml_drive2_') and approval.parent == root, 'Use new case23 root and its own approval')
    if args.mode == 'approval-template': common.write_new(approval, approval_record(root, meta, False)); return
    common.need(common.read(approval) == approval_record(root, meta, True), 'Exact case23 approval differs')
    if args.mode in ('stage', 'run'):
        common.need(args.model_root is not None, 'Use existing verified private model root')
        if args.mode == 'stage': check_started(datetime.now(timezone.utc)); print(execution_namespace()['stage'](root, case, args.model_root)); return
        report = run(root, case, args.model_root, approval)
    else: report = execution_namespace()['collect'](root, case)
    result = summarize(report, root, case, meta); target = root / 'sar7_cml_drive2_summary.json'
    if target.exists(): common.need(common.read(target) == result, 'Existing summary differs')
    else: common.write_new(target, result)
    print(json.dumps(dict(summary=str(target), sha256=common.sha(target), screen_pass=result['readout_565']['screen_pass'])))


if __name__ == '__main__': main()
