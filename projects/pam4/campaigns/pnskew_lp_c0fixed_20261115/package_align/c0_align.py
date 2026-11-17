"""Calibrate C0 on the zero-skew training prefix and score the fixed payload."""

import bisect
import math
from functools import partial

import c0_review as review


common = review.common
PLAN = review.ROOT / 'c0_review_plan.json'
BASELINE = review.CASES[0][0]
PLANES = ('primary', 'secondary')
EXPECTED_POLARITY = {'primary': 1, 'secondary': -1}
WARMUP = 128
TRAINING_INPUTS = 960
TRAINING_STOP = WARMUP + TRAINING_INPUTS
LAGS = range(-6, 40)
SCHEMA = 'pam4_c0_zero_skew_prefix_v1'


def scoring_functions():
    source = review.R5/'source_dir'
    loader = review.collect_r5.load_definitions
    functions = review.collect_r5.original_functions(source)
    metrics = loader(source/'pam4_metrics.py', {'fit_training'},
                     dict(vars(functions.metrics), math=math, bisect=bisect,
                          GRAY_CODES=(0,1,3,2)))
    ffe = loader(source/'pam4_ffe_diagnostic.py', {'mean', 'cholesky_solve', 'fit_ffe'},
                 dict(math=math, metrics=metrics, integration=functions.pi),
                 assignments=('TAPS','HALF','RIDGE','TARGETS'))
    functions.opt.freeze_detectors = loader(source/'optimize_pam4.py', {'freeze_detectors'},
                                             dict(ffe=ffe,metrics=metrics)).freeze_detectors
    return functions


def correlation(samples, labels):
    sample_mean = math.fsum(samples) / len(samples)
    label_mean = math.fsum(labels) / len(labels)
    samples = [sample - sample_mean for sample in samples]
    labels = [label - label_mean for label in labels]
    scale = math.sqrt(math.fsum(x*x for x in samples) * math.fsum(y*y for y in labels))
    if not scale:
        return 0.0
    return math.fsum(x*y for x, y in zip(samples, labels, strict=True)) / scale


def capture(records, symbols, start, stop, lag):
    indices = range(start, stop)
    chosen = [records[index + lag] for index in indices]
    return [row[1] for row in chosen], symbols[start:stop], [row[2] for row in chosen]


def calibrate(functions, records, symbols, frozen, raw_sha256, status_sha256):
    # Truncate the observable records too. A positive lag and the later secondary
    # read could otherwise admit a payload observation with a training label.
    training_symbols = symbols[:TRAINING_STOP]
    selections = {}
    for point in PLANES:
        by_index = {row[0]: row for row in records[point] if row[2] < review.FIRST_PAYLOAD_S}
        sweep = []
        for lag in LAGS:
            samples, labels, _ = capture(by_index, training_symbols, WARMUP, TRAINING_STOP, lag)
            sweep.append({'lag': lag, 'pearson': correlation(samples, labels)})
        best = max(sweep, key=lambda row: abs(row['pearson']))
        lag = best['lag']
        samples, labels, times = capture(by_index, training_symbols, WARMUP, TRAINING_STOP, lag)
        prior = frozen['selections'][point]
        fullscale = prior['frozen_detectors']['ADC_fullscale_differential_Vpp']
        detectors = functions.opt.freeze_detectors(samples, labels, fullscale)
        selections[point] = dict(lag=lag, pearson=best['pearson'], expected_raw_p_minus_n_sign=EXPECTED_POLARITY[point],
                                 correlation_sign_matches_circuit=best['pearson']*EXPECTED_POLARITY[point]>0,
                                 historical_lag=prior['integer_symbol_lag'], search=sweep,
                                 last_training_read_s=max(times), detectors=detectors)
    return dict(schema=SCHEMA, baseline_case=BASELINE, baseline_tran_sha256=raw_sha256,
                baseline_run_status_sha256=status_sha256, historical_frozen_sha256=review.FROZEN_SHA,
                training_tx_indices=[WARMUP, TRAINING_STOP], payload_tx_start=review.FIRST_PAYLOAD,
                time_cutoff_s=review.FIRST_PAYLOAD_S, training_payload_guard_symbols=review.FIRST_PAYLOAD-TRAINING_STOP,
                lag_candidates=[LAGS.start, LAGS.stop-1], phase='original measured aperture',
                polarity_application='native P minus N at each plane, detector fits that orientation',
                selections=selections)


def score_records(functions, raw, frozen, case, status_sha256, calibration):
    records, audit = functions.r5.extract_records(raw, frozen['training_run']['clock_specification'])
    symbols = functions.r5.validation_symbols()
    if calibration is None:
        common.need(case['case_id']==BASELINE, 'Calibrate only on the zero-skew case')
        calibration = calibrate(functions, records, symbols, frozen, raw.sha256, status_sha256)
    common.need(calibration['schema']==SCHEMA and calibration['baseline_case']==BASELINE
                and calibration['historical_frozen_sha256']==review.FROZEN_SHA
                and calibration['training_tx_indices']==[WARMUP,TRAINING_STOP]
                and calibration['payload_tx_start']==review.FIRST_PAYLOAD, 'C0 calibration identity differs')
    results = {}
    start = review.FIRST_PAYLOAD
    stop = start + review.HOLDOUT
    for point in PLANES:
        choice = calibration['selections'][point]
        lag = choice['lag']
        common.need(type(lag) is int and lag in LAGS and choice['last_training_read_s']<review.FIRST_PAYLOAD_S,
                    'C0 calibration used an unexpected lag or training window')
        by_index = {row[0]: row for row in records[point]}
        samples, labels, times = capture(by_index, symbols, start, stop, lag)
        common.need(len(samples)==len(labels)==review.HOLDOUT and min(times)>choice['last_training_read_s'],
                    'C0 payload coverage or training separation differs')
        scores = functions.opt.evaluate_frozen(samples, labels, choice['detectors'])
        common.need(scores['ADC_validation_input_count']==review.HOLDOUT
                    and scores['FFE_validation_output_count']==review.HOLDOUT-16
                    and scores['validation_fitting_performed'] is False, 'C0 scoring window differs')
        results[point] = dict(first_read_s=times[0], last_read_s=times[-1], lag=lag, metrics=scores)
    return dict(metrics=results, clock_audit=audit, calibration=calibration,
                scoring=dict(payload_tx_indices=[start,stop], ffe_center_tx_indices=[start+8,stop-8],
                             fit_scope='zero-skew pre-payload prefix', phase_optimized=False))


def measure(run, calibration=None):
    """Read the original completed PSF after the caller verifies execution evidence."""
    frozen = review.pinned_r5()
    status_sha = common.sha(run/'run_status.json')
    status = common.read(run/'run_status.json')
    case, = [row for row in common.read(PLAN)['cases'] if row['case_id']==status['case_id']]
    native, = [row['path'] for row in status['raw_inventory']
               if row['path'] in ('raw/tranResponse.tran', review.RAW_NAME)]
    live = common.raw_inventory(run)
    common.need(common.matches_historical_inventory(status['raw_inventory'],live),
                'Recorded raw differs from retained outputs')
    parser = partial(review.parse_selected, required={'time', *review.save_names((review.R5/'quiet.scs').read_text('ascii'))})
    raw = review.safe_raw(run,dict(status,raw_inventory=live),native.removeprefix('raw/'),parser=parser)
    common.need(raw.unit('time')=='s', 'C0 native time sweep must explicitly use seconds')
    review.collect_r5.validate_raw(raw,review.STOP_S)
    functions = scoring_functions()
    result = score_records(functions,raw,frozen,case,status_sha,calibration)
    return dict(result,case=case,frozen_sha256=review.FROZEN_SHA,
                run_status_sha256=status_sha,tran_sha256=raw.sha256)
