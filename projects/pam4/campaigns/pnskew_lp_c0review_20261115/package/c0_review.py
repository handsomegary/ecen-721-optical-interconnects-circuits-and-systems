"""Render five portable fixed-code C0 review decks and score a short r5 slice."""

import argparse
import hashlib
import os
from pathlib import Path
import re
import sys
from functools import partial


ROOT = Path(__file__).resolve().parent
SWITCH = Path(os.environ.get('PAM4_C0_SWITCH_PACKAGE', ROOT.parent/'PAM4_PNSKEW_LP_GMTAP_SWITCH64_ENDPOINT_COLLECT_FIX_20261115')).resolve()
R5 = Path(os.environ.get('PAM4_C0_R5_ORIGINAL', ROOT.parent/'PAM4_PNSKEW_COMP_20261113'/'r5_original')).resolve()
FROZEN_SHA = '4cda4c9ec967f2af4bf4f89eacdd1beae372668877c358cf6aa26092597482eb'
SWITCH_MANIFEST_SHA = '55d13973cf50c19cb281582bf9132e8cf7dea166895f30bb57659e186c1ed683'
sys.path.insert(0, str(SWITCH))

import gm_center64
import gm_gmtap_common
import gm_switch64_rf
from gm_switch64_psf import parse_selected
import olympus_common as common
from comp_measure import collect_r5, safe_raw
from native import pn_stage
from weighted_delay import ENDPOINT_PS


UI = 1 / 112e9
STOP_S = 14e-9
HOLDOUT = 256
FIRST_PAYLOAD = 128 + 1024
FIRST_PAYLOAD_S = 200e-12 + FIRST_PAYLOAD*UI
CASES = (
    ('c0_00_tt_zero', 0., 0),
    ('c0_01_tt_p_late_code0', ENDPOINT_PS, 0),
    ('c0_02_tt_p_late_preset', ENDPOINT_PS, -60),
    ('c0_03_tt_n_late_code0', -ENDPOINT_PS, 0),
    ('c0_04_tt_n_late_preset', -ENDPOINT_PS, 60),
)
RAW_NAME = 'raw/tranResponse.tran.tran'


def pinned_r5():
    common.need(common.sha(R5/'frozen.json') == FROZEN_SHA, 'Frozen r5 settings differ')
    provenance = common.read(R5/'provenance.json')['files']
    for key, row in provenance.items():
        if key == 'quiet.scs' or key.startswith('source_dir/'):
            common.need(common.sha(R5/key) == row['sha256'], f'Historical r5 input differs: {key}')
    return common.read(R5/'frozen.json')


def trim_channel(r5, skew_ps):
    source = r5[r5.index('PAM4Vp ('):r5.index('VBANK (')].encode('ascii')
    for name, direction in (('PAM4Vp', 1), ('PAM4Vm', -1)):
        block = pn_stage.pwl_block(source, name)
        start, end, _, _, _, _ = block
        shifted = pn_stage.shifted_body(block, direction*skew_ps*1e-12/2)
        source = source[:start] + shifted + source[end:]
        start, end, body, tokens, times, _ = pn_stage.pwl_block(source, name)
        past_stop = next(i for i, t in enumerate(times) if t > STOP_S)
        source = source[:start] + body[:tokens[2*past_stop+1].end()] + b' \\\n ' + source[end:]
    text = source.decode('ascii')
    text = text.replace('CHB2p (X_ip ', 'CHB2p (PNC_PREP ', 1)
    return text.replace('CHB2m (X_im ', 'CHB2m (PNC_PREN ', 1)


def save_names(r5):
    original, = re.findall(r'(?m)^save (X_o_p X_o_m X_ip X_im[^\n]*)$', r5)
    renamed = {'X_ip':'PNC_PREP', 'X_im':'PNC_PREN'}
    return tuple(dict.fromkeys([*(renamed.get(name,name) for name in original.split()),
                                *(f'X_ck{i}' for i in range(8)), 'GFVDD:p']))


def render(case_id, skew_ps, code, candidates, r5):
    case = candidates[code]
    deck, *_ = gm_center64.render(case, gm_center64.BASE.MODEL_TOKEN)
    deck, count = re.subn(r'(?m)^(?:XVin \(PNC_PREP|PNCVN \(PNC_PREN)[^\n]+\n', '', deck)
    common.need(count == 2, 'Expected both AC input sources')
    deck, count = re.subn(r'(?m)^(?:acResponse|noiseResponse|dcOpInfo) [^\n]+\n', '', deck)
    common.need(count == 3, 'Expected only the three AC/OP exports to be removed')
    deck = gm_switch64_rf.primary_clocks(deck, r5, .9)
    backend = r5[r5.index('VBANK ('):r5.index('saveOptions options')]
    deck = gm_center64.BASE.replace_once(deck, 'saveOptions options',
        trim_channel(r5, skew_ps) + backend + 'saveOptions options')
    traces = save_names(r5)
    deck, count = re.subn(r'(?m)^save [^\n]+$', 'save '+' '.join(traces), deck)
    common.need(count==1 and len(re.findall(r'(?m)^XCK[0-7] ',deck))==8
                and len(re.findall(r'(?m)^GMSK(?:06|11|16)VE\d+ .* vsource dc=',deck))==54
                and len(re.findall(r'(?m)^B[0-7]_COMP[0-7] ',deck))==64,
                'Unexpected clocks, control enable or secondary load inventory')
    deck += f'tranResponse tran stop={STOP_S:.16g} maxstep=200f errpreset=conservative '
    deck += f'strobeperiod={UI/8:.16g} strobeoutput=strobeonly\n'
    return deck, dict(case_id=case_id, skew_ps=skew_ps, fixed_code=code, stop_s=STOP_S,
                      first_payload_s=FIRST_PAYLOAD_S, holdout_inputs=HOLDOUT,
                      FFE_scored_symbols=HOLDOUT-16, saved_trace_count=len(traces),
                      deck_sha256=hashlib.sha256(deck.encode('ascii')).hexdigest())


def render_all():
    common.need(common.sha(SWITCH/'SHA256SUMS.txt') == SWITCH_MANIFEST_SHA, 'Wrong SWITCH64 parent')
    gm_center64.trim.fine.endpoint.integrated.mirror.prior.gm.original.verify_package()
    pinned_r5()
    r5 = (R5/'quiet.scs').read_bytes().decode('ascii')
    controls = {case['code']:case for case in gm_gmtap_common.build_plan()['cases']
                if case['process']=='tt' and case['group']=='divider' and case['drive']=='p'
                and case['code'] in (-60,0,60)}
    common.need(set(controls)=={-60,0,60}, 'Missing verified COMMON64 controls')
    output = ROOT/'decks'
    output.mkdir(exist_ok=False)
    records = []
    for case_id, skew, code in CASES:
        deck, record = render(case_id,skew,code,controls,r5)
        (output/f'{case_id}.scs').write_bytes(deck.encode('ascii'))
        records.append(record)
    common.write_new(ROOT/'c0_review_plan.json', dict(status='portable_review', cases=records,
        model_token=gm_center64.BASE.MODEL_TOKEN, unchanged_frozen_sha256=FROZEN_SHA,
        endpoint_code_source='COMMON64 preset controls; independent acquisition is pending'))


def score_records(functions, raw, frozen):
    records, audit = functions.r5.extract_records(raw, frozen['training_run']['clock_specification'])
    symbols = functions.r5.validation_symbols()
    results = {}
    for point in ('primary','secondary'):
        choice = frozen['selections'][point]
        lag = choice['integer_symbol_lag']
        samples, labels, times = functions.pi.aligned_window(records[point], symbols, lag, 1024, HOLDOUT)
        scores = functions.opt.evaluate_frozen(samples[1024:], labels[1024:], choice['frozen_detectors'])
        common.need(scores['ADC_validation_input_count']==HOLDOUT
                    and scores['FFE_validation_output_count']==HOLDOUT-16
                    and scores['validation_fitting_performed'] is False
                    and times[1024] >= FIRST_PAYLOAD_S-2*UI, 'Short frozen scoring window differs')
        results[point] = dict(first_read_s=times[1024], last_read_s=times[-1], lag=lag, metrics=scores)
    return dict(metrics=results, clock_audit=audit)


def score_existing(run, output):
    frozen = pinned_r5()
    status = common.read(run/'run_status.json')
    common.need(status['status']=='spectre_completed' and status['exit_code']==0
                and status['input_deck_sha256_before']==status['input_deck_sha256_after']==common.sha(run/'bench.scs')
                and status['spectre_log_sha256']==common.sha(run/'spectre.log'), 'Run status/source mismatch')
    deck = (run/'bench.scs').read_bytes().decode('ascii')
    roots = re.findall(r'(?m)^include "([^\n"]+)/models/spectre/pdk_toplevel\.scs" section=tt$',deck)
    common.need(len(roots)==1, 'Expected a single original TT model root')
    portable_sha = hashlib.sha256(deck.replace(roots[0],gm_center64.BASE.MODEL_TOKEN).encode('ascii')).hexdigest()
    matches = [case for case in common.read(ROOT/'c0_review_plan.json')['cases']
               if case['deck_sha256']==portable_sha and case['case_id']==status['case_id']]
    common.need(len(matches)==1, 'Bench does not match the case in the C0 review plan')
    native = [row['path'] for row in status['raw_inventory']
              if row['path'] in ('raw/tranResponse.tran',RAW_NAME)]
    common.need(len(native)==1, 'Expected exactly one original transient')
    raw = safe_raw(run,status,native[0].removeprefix('raw/'),
                   parser=partial(parse_selected, required={'time', *save_names((R5/'quiet.scs').read_text('ascii'))}))
    collect_r5.validate_raw(raw,STOP_S)
    report = score_records(collect_r5.original_functions(R5/'source_dir'),raw,frozen)
    common.write_new(output,dict(report,case=matches[0], frozen_sha256=FROZEN_SHA,
                                run_status_sha256=common.sha(run/'run_status.json'), tran_sha256=raw.sha256))


def summarize(paths):
    expected = common.read(ROOT/'c0_review_plan.json')['cases']
    reports = [common.read(path) for path in paths]
    keyed = {report['case']['case_id']:report for report in reports}
    common.need(len(reports)==len(keyed)==len(expected)
                and set(keyed)=={case['case_id'] for case in expected}, 'Need exactly five distinct C0 reports')
    result = {}
    for case in expected:
        name = case['case_id']
        report = keyed[name]
        common.need(report['case']==case and report['frozen_sha256']==FROZEN_SHA, 'C0 scope or frozen settings differ')
        result[name] = {}
        for point in ('primary','secondary'):
            metrics = report['metrics'][point]['metrics']
            ffe = metrics['ideal7bit_ADC_then_FFE']
            common.need(metrics['validation_fitting_performed'] is False
                        and ffe['sample_count']==metrics['FFE_validation_output_count']==HOLDOUT-16,
                        'C0 scored window mismatch')
            result[name][point] = {key:ffe[key] for key in ('sample_count','symbol_errors','SER',
                                          'gray_bit_errors','prediction_RMSE_in_target_symbol_units')}
    deltas = {}
    for sign, uncorrected, preset in (('P_late',1,2),('N_late',3,4)):
        before, after = result[CASES[uncorrected][0]], result[CASES[preset][0]]
        deltas[sign] = {point:after[point]['SER']-before[point]['SER'] for point in ('primary','secondary')}
    return dict(status='fixed_endpoint_diagnostic',metrics=result,paired_delta_SER=deltas)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--render', action='store_true')
    parser.add_argument('--score-run', type=Path)
    parser.add_argument('--summary', type=Path, nargs=5)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.render and args.score_run is None and args.summary is None:
        render_all()
    elif not args.render and args.summary is None and args.score_run is not None and args.output is not None:
        score_existing(args.score_run.resolve(strict=True),args.output)
    elif not args.render and args.score_run is None and args.summary is not None and args.output is not None:
        common.write_new(args.output,summarize(args.summary))
    else:
        parser.error('Use --render, --score-run with --output, or --summary with --output')


if __name__=='__main__':
    main()
