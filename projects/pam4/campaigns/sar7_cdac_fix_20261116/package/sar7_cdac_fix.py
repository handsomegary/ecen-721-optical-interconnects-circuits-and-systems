"""Run at most two fixed SAR7 CDAC corrections with a measured sequential gate."""

import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT/'SHA256SUMS.txt'
PLAN = ROOT/'PLAN.json'
SCHEMA = 'pam4_sar7_cdac_fix_v1'
PARENT = Path(os.environ.get('PAM4_SAR7_CML_RDEG_PACKAGE', ROOT.parent/
    'PAM4_SAR7_CML_RDEG_20261115')).resolve()
PARENT_MANIFEST_SHA256 = 'bd6428e1f85aa5eaf1a8ee99c521b05ffef64c848eb0c53402ccb1be4f995ce3'
if hashlib.sha256((PARENT/'SHA256SUMS.txt').read_bytes()).hexdigest() != PARENT_MANIFEST_SHA256:
    raise ValueError('Unexpected original RDEG package')
sys.path.insert(0, str(PARENT))
import sar7_cml_rdeg as pilot

base, common, native = pilot.base, pilot.common, pilot.native
_PARENT_BINDINGS = (base.build, base.PLAN, base.MANIFEST, base.SCHEMA)
CAP_INSTANCE = re.compile(r'C(?:(?:unit|top|bott)(?:[0-6]|d)|bridge(?:_(?:main|low))?)[pn]')
SUMMARY = 'sar7_cdac_fix_summary.json'


def plan_cases():
    plan = common.read(PLAN)
    common.need(plan.get('schema') == SCHEMA and 1 <= len(plan.get('cases', [])) <= 2,
                'Expected one or two fixed CDAC correction cases')
    common.need(set(plan) <= {'schema', 'cases', 'provenance'}, 'Unexpected plan fields')
    cases = plan['cases']
    common.need(len({case['case_id'] for case in cases}) == len(cases), 'Duplicate case IDs')
    original, = common.read(pilot.PLAN)['cases']
    for index, case in enumerate(cases):
        common.need(set(case) == set(original)|{'correction'}, 'Unexpected case fields')
        common.need(re.fullmatch(r'sar7_[a-zA-Z0-9_]+', case['case_id']) is not None,
                    'Use a simple SAR7 case ID')
        common.need({key: case[key] for key in original if key != 'case_id'} ==
                    {key: original[key] for key in original if key != 'case_id'},
                    'Keep the original twelve inputs and source conditions')
        fix = case['correction']
        common.need(set(fix) == {'reference_span_V', 'capacitance_F'}, 'Unexpected correction fields')
        span = fix['reference_span_V']
        common.need(isinstance(span, (int, float)) and not isinstance(span, bool)
                    and math.isfinite(span) and 0 < span < .9, 'Invalid reference span')
        caps = fix['capacitance_F']
        common.need(isinstance(caps, dict) and (not caps if index == 0 else bool(caps)),
                    'Case zero is reference-only; case one must correct capacitor ratios')
        for name, value in caps.items():
            common.need(CAP_INSTANCE.fullmatch(name) is not None, 'Unapproved capacitor instance')
            common.need(isinstance(value, (int, float)) and not isinstance(value, bool)
                        and math.isfinite(value) and value > 0, 'Invalid capacitor value')
            partner = name[:-1]+('n' if name.endswith('p') else 'p')
            common.need(caps.get(partner) == value, 'Apply identical correction to both CDAC arms')
    return cases


def build(case):
    cases = plan_cases()
    common.need(case in cases, 'Case must exactly match the frozen plan')
    original, = common.read(pilot.PLAN)['cases']
    parent, old_meta = pilot.build(original)
    rows, changed, found = [], [], set()
    fix = case['correction']
    values = {'V_RHI': .45+fix['reference_span_V']/2,
              'V_RLO': .45-fix['reference_span_V']/2}
    for line in parent.decode('ascii').splitlines():
        label = line.split()[0] if line.split() else ''
        out = line
        if label in values:
            out, count = re.subn(r'\bdc=\S+', 'dc='+native.number(values[label]), line)
            common.need(count == 1 and label not in found, 'Unexpected reference source')
            found.add(label)
        elif label in fix['capacitance_F']:
            common.need(CAP_INSTANCE.fullmatch(label) is not None and ' capacitor ' in line,
                        'Only original ideal CDAC capacitors may change')
            out, count = re.subn(r'\bc=\S+', 'c='+native.number(fix['capacitance_F'][label]), line)
            common.need(count == 1 and label not in found, 'Unexpected capacitor card')
            found.add(label)
        rows.append(out)
        if out != line:
            changed.append(label)
    common.need(found == set(values)|set(fix['capacitance_F']), 'Missing planned CDAC component')
    bench = ('\n'.join(rows)+'\n').encode('ascii')
    wave = copy.deepcopy(old_meta['wave'])
    wave['nominal_reference_span_V'] = fix['reference_span_V']
    if cases.index(case) == 1:
        caps = {}
        for line in rows:
            match = re.fullmatch(r'(C\S+) \([^\n]+\) capacitor c=(\S+)', line)
            if match and CAP_INSTANCE.fullmatch(match[1]):
                caps[match[1]] = float(match[2])
        ratios = []
        for side in ('p', 'n'):
            bridge = caps['Cbridge'+side]
            low_total = bridge+caps['Cbridge_low'+side]+sum(
                caps[kind+bit+side] for kind in ('Cunit', 'Ctop') for bit in ('0', '1', '2', 'd'))
            ratios.append(bridge/low_total)
        common.need(math.isclose(*ratios, rel_tol=1e-12), 'The two CDAC arms have different bridge ratios')
        wave['nominal_low_to_main_unit_weight'] = ratios[0]
    meta = dict(case=case, wave=wave, portable_sha256=hashlib.sha256(bench).hexdigest(),
                parent_case_id=pilot.CASE_ID, parent_manifest_sha256=PARENT_MANIFEST_SHA256,
                reference_bench_sha256=old_meta['portable_sha256'],
                correction=copy.deepcopy(fix), changed_labels=changed)
    return bench, meta


def verify():
    # Parent verification uses a shared base module; restore its original bindings briefly.
    saved = (base.build, base.PLAN, base.MANIFEST, base.SCHEMA)
    try:
        base.build, base.PLAN, base.MANIFEST, base.SCHEMA = _PARENT_BINDINGS
        pilot.verify()
    finally:
        base.build, base.PLAN, base.MANIFEST, base.SCHEMA = saved
    entries = MANIFEST.read_text(encoding='ascii').splitlines()
    common.need(bool(entries), 'Empty correction manifest')
    for line in entries:
        digest, name = line.split('  ', 1)
        path = ROOT/name
        common.need(path.resolve().is_relative_to(ROOT) and common.sha(path) == digest,
                    'Correction package differs: '+name)
    return [(case, build(case)[1]) for case in plan_cases()]


def bind():
    base.build, base.PLAN, base.MANIFEST, base.SCHEMA = build, PLAN, MANIFEST, SCHEMA
    base.TIMEOUT_S = 540


def expected_approval(root, verified):
    return dict(approved=True, platform='Olympus', campaign=SCHEMA,
                case_ids=[case['case_id'] for case, meta in verified],
                authorized_run_root=str(root), design_source_sha256=common.sha(MANIFEST),
                deck_sha256_by_case={case['case_id']: meta['portable_sha256'] for case, meta in verified})


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
                parent_case_id=pilot.CASE_ID, job_id=report['slurm_task_id'], tested_conversions=12,
                comparison_records=84, unresolved_bits=unresolved,
                unresolved_bits_total=sum(unresolved.values()), comparator=comparator, registered=registered,
                registered_available_consistency=consistent,
                valid=(missing == 0 and consistent and not any(unresolved.values())),
                final_cm_change_mV=[min(cm), max(cm)],
                max_abs_sample_error_lsb=report['max_abs_sample_error_lsb'],
                max_observed_resolve_delay_s=report['max_observed_resolve_delay_s'],
                logic_smoke_pass=report['logic_smoke_pass'], solver_seconds=report['solver_seconds'],
                raw_bytes=report['raw_bytes'], tran_sha256=report['tran_sha256'],
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


def write_summary(root, index, case, report):
    sense = pilot.measured_sense(root/case['case_id'], case)
    result = summarize(report, sense, root, index, case)
    target = summary_path(root, case)
    if target.exists():
        common.need(common.read(target) == result, 'Existing measured summary differs')
    else:
        common.write_new(target, result)
    digest = common.sha(target)
    sidecar = target.with_suffix('.json.sha256')
    record = dict(sha256=digest, filename=target.name)
    if sidecar.exists():
        common.need(common.read(sidecar) == record, 'Summary SHA256 record differs')
    else:
        common.write_new(sidecar, record)
    return result, digest


def gate_recommendation(summary):
    valid = summary['valid']
    cm_ok = max(map(abs, summary['final_cm_change_mV'])) <= 10
    maxima = [summary[channel]['max_abs_code_error'] for channel in ('comparator', 'registered')]
    sums = [summary[channel]['sum_abs_code_error'] for channel in ('comparator', 'registered')]
    peak = max(maxima) if all(value is not None for value in maxima) else None
    total = max(sums)
    if valid and cm_ok and peak <= 1:
        recommendation = 'STOP_TARGET'
    elif valid and cm_ok and peak <= 2 and total <= 8:
        recommendation = 'STOP_CONVERGED'
    elif valid and cm_ok and peak <= 5 and total <= 23:
        recommendation = 'ALLOW_INDEX1'
    else:
        recommendation = 'STOP_REVIEW'
    return dict(recommendation=recommendation, valid=valid, cdac_cm_within_10mV=cm_ok,
                max_abs_code_error=peak, sum_abs_code_error=total)


def measured_gate(root, cases):
    case = cases[0]
    target = summary_path(root, case)
    common.owned_file(root/case['case_id'], target)
    common.owned_file(root/case['case_id'], target.with_suffix('.json.sha256'))
    report = read_existing_report(root, case)
    sense = pilot.measured_sense(root/case['case_id'], case)
    expected = summarize(report, sense, root, 0, case)
    common.need(common.read(target) == expected, 'Case zero summary is not its measured evidence')
    digest = common.sha(target)
    common.need(common.read(target.with_suffix('.json.sha256')) == dict(sha256=digest, filename=target.name),
                'Case zero summary SHA256 differs')
    return dict(gate_recommendation(expected), source_case_id=case['case_id'],
                source_summary_sha256=digest, source_tran_sha256=report['tran_sha256'],
                source_measurements_sha256=common.sha(root/case['case_id']/base.MEASUREMENT),
                manifest_sha256=common.sha(MANIFEST))


def require_index1_gate(root, cases):
    result = measured_gate(root, cases)
    common.need(result['recommendation'] == 'ALLOW_INDEX1',
                'Index one forbidden by measured gate: '+result['recommendation'])
    record = root/'index1_gate.json'
    if record.exists():
        common.need(common.read(record) == result, 'Existing index one gate proof differs')
    else:
        common.write_new(record, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('verify', 'list', 'approval-template', 'stage', 'run',
                                        'collect-only', 'summary', 'gate'))
    parser.add_argument('--root', type=Path)
    parser.add_argument('--index', type=int)
    parser.add_argument('--model-root', type=Path)
    parser.add_argument('--approval', type=Path)
    args = parser.parse_args()
    verified = verify()
    cases = [case for case, meta in verified]
    if args.mode in ('verify', 'list'):
        for index, (case, meta) in enumerate(verified):
            print(index, case['case_id'], meta['portable_sha256'])
        return
    common.need(args.root is not None, 'Supply an isolated campaign root')
    root = common.checked_root(args.root)
    common.need(root.name.startswith('pam4_sar7_cdac_fix_'), 'Use a new CDAC correction campaign root')
    bind()
    if args.mode == 'gate':
        print(json.dumps(measured_gate(root, cases), sort_keys=True))
        return
    if args.mode == 'approval-template':
        common.need(args.approval is not None and args.approval.absolute().parent == root,
                    'Keep the approval in the new campaign root')
        common.write_new(args.approval.absolute(), dict(expected_approval(root, verified), approved=False))
        print(args.approval.absolute())
        return
    common.need(args.index is not None and 0 <= args.index < len(cases), 'Supply a valid fixed case index')
    case = cases[args.index]
    if args.mode in ('stage', 'run'):
        common.need(args.approval is not None and args.approval.absolute().parent == root,
                    'Keep the approval in the new campaign root')
        approval = args.approval.absolute()
        common.need(common.read(approval) == expected_approval(root, verified),
                    'Approval must bind all fixed cases, decks, the manifest and root')
        common.need(args.model_root is not None, 'Use the existing verified private model root')
        if args.index == 1:
            require_index1_gate(root, cases)
        if args.mode == 'stage':
            print(base.stage(root, case, args.model_root))
            return
        report = base.run(root, case, args.model_root, approval)
    elif args.mode == 'summary':
        report = read_existing_report(root, case)
    else:
        report = base.collect(root, case)
    result, digest = write_summary(root, args.index, case, report)
    print(json.dumps(dict(summary=str(summary_path(root, case)), sha256=digest,
                          gate=gate_recommendation(result) if args.index == 0 else None), sort_keys=True))


if __name__ == '__main__':
    main()
