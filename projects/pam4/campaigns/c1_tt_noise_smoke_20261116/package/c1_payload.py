"""Render the five native C1 noise cases and score the historical long window."""

from functools import lru_cache, partial
import hashlib
import math
import re

import c0_formal_deck as design
import c0_formal_score as formal_score


review = design.review
common = review.common
CASES = (('zero',0), ('a',0), ('a',-60), ('b',0), ('b',60))
PHASE = -1
STOP_S = 2.941428571428571e-8
NOISE_SEED = 1001
NOISE_FMIN_HZ = 500_000_000
NOISE_FMAX_HZ = 150_000_000_000
TRAINING_PREFIX_SEED = 2026101301
PAYLOAD_SEED = 2026101302
WINDOW = (1152, 3200)
INPUT_COUNT = WINDOW[1] - WINDOW[0]
FFE_COUNT = INPUT_COUNT - 16
TRANSIENT = re.compile(rb'(?m)^tranResponse tran stop=(\S+)([^\r\n]*)$')


@lru_cache(maxsize=1)
def stimulus():
    review.pinned_r5()
    functions = review.collect_r5.original_functions(review.R5/'source_dir')
    sequence = tuple(functions.r5.validation_symbols())
    common.need(len(sequence)==3264 and all(0<=s<=3 for s in sequence),
                'Unexpected historical r5 validation stimulus')
    return sequence


def window_record():
    start, stop = WINDOW
    return dict(tx_symbol_indices=[start,stop], FFE_center_symbol_indices=[start+8,stop-8],
                symbol_sha256=hashlib.sha256(bytes(stimulus()[start:stop])).hexdigest())


def render(condition, code):
    common.need(type(code) is int and (condition,code) in CASES, 'Unknown C1 case')
    _, _, original_clocks, source = design.template()
    deck, clocks = design.shifted_clock_spec(design.base_deck(code),original_clocks,PHASE)
    clocks['stop_s'] = STOP_S
    data = design.fresh_pwl(deck.encode('ascii'),stimulus(),design.SKEW_PS[condition],source)
    match, = TRANSIENT.finditer(data)
    common.need(not re.search(rb'\bnoise(?:fmin|fmax|seed)=',match[2]), 'Expected a quiet C0 base bench')
    line = (b'tranResponse tran stop=2.941428571428571e-08' + match[2] +
            b' noisefmax=150G noisefmin=500M noiseseed=1001')
    data = data[:match.start()] + line + data[match.end():]
    for name in ('PAM4Vp','PAM4Vm'):
        final_event = review.pn_stage.pwl_block(data,name)[-2][-1]
        common.need(final_event>design.T0+WINDOW[1]*review.UI and final_event<STOP_S,
                    'Expected the historical end guard before the fixed transient horizon')
    tag = ('m' if code<0 else 'p') + f'{abs(code):02d}'
    return data, dict(case_id=f'c1n_{condition}_c{tag}_phm1_s1001', condition=condition,
                      code=code, phase=PHASE, skew_ps=design.SKEW_PS[condition],
                      stop_s=STOP_S, clock_spec=clocks, stimulus='validation',
                      deck_sha256=hashlib.sha256(data).hexdigest(),
                      specimen='fixed_endpoint_diagnostic' if condition=='a' and code==-60 else 'fixed_endpoint',
                      noise=dict(seed=NOISE_SEED, fmin_Hz=NOISE_FMIN_HZ, fmax_Hz=NOISE_FMAX_HZ),
                      stimulus_provenance=dict(training_prefix_seed=TRAINING_PREFIX_SEED,
                                               validation_seed=PAYLOAD_SEED,
                                               symbol_sha256=hashlib.sha256(bytes(stimulus())).hexdigest()),
                      **window_record())


def score_records(meta, records, calibration, functions):
    aligned = formal_score.aligned
    common.need(calibration['schema']==formal_score.CALIBRATION_SCHEMA
                and calibration['phase']==meta['phase']==PHASE
                and calibration['source_case_id']=='c0f_training_zero_cp00_phm1'
                and calibration['historical_frozen_sha256']==review.FROZEN_SHA
                and calibration['fit_tx_symbol_indices']==list(formal_score.FIT)
                and calibration['fit_read_cutoff_s']==formal_score.FIT_READ_CUTOFF_S,
                'C1 requires the frozen formal C0 zero-skew calibration')
    scores = {}
    windows = window_record()
    start,stop = WINDOW
    for plane in aligned.PLANES:
        selection = calibration['selections'][plane]
        lag = selection['lag']
        common.need(type(lag) is int and lag in aligned.LAGS
                    and selection['last_train_read_s']<formal_score.FIT_READ_CUTOFF_S,
                    'Unexpected frozen training window or lag')
        indexed = {row[0]:row for row in records[plane]}
        common.need(len(indexed)==len(records[plane]), 'Duplicate physical sample index')
        common.need(all(index in indexed for index in range(start+lag,stop+lag)),
                    'Physical samples do not cover the complete historical long window')
        samples, labels, times = aligned.capture(indexed,stimulus(),start,stop,lag)
        common.need(all(math.isfinite(t) for t in times) and all(a<b for a,b in zip(times,times[1:]))
                    and times[0]>formal_score.FIT_READ_CUTOFF_S and times[-1]<meta['stop_s'],
                    'Sample times are outside the ordered long window')
        scores[plane] = functions.opt.evaluate_frozen(samples, labels, selection['detectors'])
        windows[plane] = dict(first_read_s=times[0],last_read_s=times[-1],lag=lag)
    result = dict(case_id=meta['case_id'],metrics=scores,capture_window=windows,noise=meta['noise'],
                  stimulus_provenance=meta['stimulus_provenance'])
    validate_report(result,meta)
    return result


def validate_report(report, meta):
    window = report['capture_window']
    common.need(report['case_id']==meta['case_id'] and report['noise']==meta['noise']
                and report['stimulus_provenance']==meta['stimulus_provenance']
                and all(window.get(key)==expected for key,expected in window_record().items()),
                'Result uses a different physical case, noise seed, payload or scoring window')
    for plane in formal_score.aligned.PLANES:
        metrics = report['metrics'][plane]
        ffe = metrics['ideal7bit_ADC_then_FFE']
        common.need(metrics['ADC_validation_input_count']==INPUT_COUNT
                    and metrics['FFE_validation_output_count']==ffe['sample_count']==FFE_COUNT
                    and metrics['validation_fitting_performed'] is False
                    and 0<=metrics['ADC_validation_input_clipped_count']<=INPUT_COUNT
                    and 0<=ffe['symbol_errors']<=FFE_COUNT and 0<=ffe['gray_bit_errors']<=2*FFE_COUNT
                    and math.isclose(ffe['SER'],ffe['symbol_errors']/FFE_COUNT,rel_tol=1e-12,abs_tol=1e-15)
                    and math.isfinite(ffe['prediction_RMSE_in_target_symbol_units']),
                    'Result has inconsistent counts, re-fit detectors, or nonfinite metrics')


def measure(run, meta, calibration):
    status_path = run/'run_status.json'
    status_sha = common.sha(status_path)
    status = common.read(status_path)
    common.need(status['status']=='spectre_completed' and status['exit_code']==0,
                'No complete C1 Spectre execution to measure')
    native, = [row['path'] for row in status['raw_inventory']
               if row['path'] in ('raw/tranResponse.tran',review.RAW_NAME)]
    live = common.raw_inventory(run)
    common.need(common.matches_historical_inventory(status['raw_inventory'], live),
                'C1 raw inventory differs from original execution evidence')
    parser = partial(review.parse_selected,
                     required={'time', *review.save_names((review.R5/'quiet.scs').read_text('ascii'))})
    raw = review.safe_raw(run, dict(status,raw_inventory=live), native.removeprefix('raw/'), parser=parser)
    common.need(raw.unit('time')=='s','C1 native PSF time sweep must explicitly use seconds')
    review.collect_r5.validate_raw(raw,meta['stop_s'])
    functions = review.collect_r5.original_functions(review.R5/'source_dir')
    records,audit = functions.r5.extract_records(raw,meta['clock_spec'])
    result = score_records(meta,records,calibration,functions)
    common.need(common.sha(status_path)==status_sha,'Run status changed while measuring C1')
    return dict(result,clock_audit=audit,run_status_sha256=status_sha,tran_sha256=raw.sha256)
