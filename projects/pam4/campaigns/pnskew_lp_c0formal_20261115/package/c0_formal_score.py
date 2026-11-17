"""Measure the clocked C0 receiver on disjoint fitting and scoring windows."""

from functools import partial
import hashlib

import c0_align as aligned
import c0_formal_deck as design


review = aligned.review
common = review.common
FIT = (128, 384)
VERIFY = (448, 640)
PAYLOAD = (design.WARMUP, design.WARMUP + design.SCORED_INPUTS)
FIT_READ_CUTOFF_S = design.T0 + VERIFY[0] * review.UI
CALIBRATION_SCHEMA = 'pam4_c0_formal_calibration_v1'


def fit_calibration(meta, records, symbols, functions, frozen):
    """Fit a zero-skew detector before reading the training verification block."""
    common.need(meta['stimulus'] == 'training' and meta['condition'] == 'zero'
                and meta['code'] == 0, 'Only zero-skew code-0 training may fit detectors')
    selections = {}
    for plane in aligned.PLANES:
        # Limit both labels and read times. The secondary aperture is later
        # than the primary, and some explored integer lags are positive.
        fit_records = {index: row for index, row in records[plane].items()
                       if row[2] < FIT_READ_CUTOFF_S}
        sweep = []
        for lag in aligned.LAGS:
            values, labels, _ = aligned.capture(fit_records, symbols, *FIT, lag)
            sweep.append(dict(lag=lag, pearson=aligned.correlation(values, labels)))
        best = max(sweep, key=lambda row: abs(row['pearson']))
        values, labels, times = aligned.capture(fit_records, symbols, *FIT, best['lag'])
        fullscale = frozen['selections'][plane]['frozen_detectors']['ADC_fullscale_differential_Vpp']
        detectors = functions.opt.freeze_detectors(values, labels, fullscale)
        expected_polarity = aligned.EXPECTED_POLARITY[plane]
        selections[plane] = dict(
            **best, detectors=detectors, expected_raw_p_minus_n_sign=expected_polarity,
            correlation_sign_matches_circuit=best['pearson'] * expected_polarity > 0,
            first_train_read_s=times[0], last_train_read_s=times[-1], lag_sweep=sweep,
        )
    return dict(schema=CALIBRATION_SCHEMA, phase=meta['phase'], source_case_id=meta['case_id'],
                fit_tx_symbol_indices=list(FIT), fit_read_cutoff_s=FIT_READ_CUTOFF_S,
                historical_frozen_sha256=review.FROZEN_SHA, selections=selections)


def score_records(meta, records, calibration, functions, frozen):
    """Score actual held samples using one supplied calibration or fit a phase trial."""
    stimulus = meta['stimulus']
    common.need(stimulus in ('training', 'payload'), 'Unknown C0 scoring stimulus')
    symbols = design.symbols(stimulus)
    indexed = {plane: {row[0]: row for row in records[plane]} for plane in aligned.PLANES}
    own_calibration = calibration is None
    if own_calibration:
        calibration = fit_calibration(meta, indexed, symbols[:FIT[1]], functions, frozen)
    common.need(calibration['schema'] == CALIBRATION_SCHEMA and calibration['phase'] == meta['phase']
                and calibration['historical_frozen_sha256'] == review.FROZEN_SHA
                and calibration['fit_tx_symbol_indices'] == list(FIT)
                and calibration['fit_read_cutoff_s'] == FIT_READ_CUTOFF_S,
                'Frozen receiver calibration differs from the actual phase or fit window')
    start, stop = VERIFY if stimulus == 'training' else PAYLOAD
    windows = dict(tx_symbol_indices=[start, stop], FFE_center_symbol_indices=[start+8, stop-8],
                   symbol_sha256=hashlib.sha256(bytes(symbols[start:stop])).hexdigest())
    scores = {}
    for plane in aligned.PLANES:
        selection = calibration['selections'][plane]
        lag = selection['lag']
        common.need(type(lag) is int and lag in aligned.LAGS and selection['last_train_read_s'] < FIT_READ_CUTOFF_S,
                    'Frozen lag or training read time outside the declared envelope')
        samples, labels, times = aligned.capture(indexed[plane], symbols, start, stop, lag)
        if own_calibration:
            common.need(selection['last_train_read_s'] < times[0], 'Training and verification reads overlap')
        result = functions.opt.evaluate_frozen(samples, labels, selection['detectors'])
        common.need(result['validation_fitting_performed'] is False
                    and result['ADC_validation_input_count'] == stop-start
                    and result['FFE_validation_output_count'] == stop-start-16,
                    'Receiver score used unexpected sample counts or fitted the scored data')
        scores[plane] = result
        windows[plane] = dict(first_read_s=times[0], last_read_s=times[-1], lag=lag)
    result = dict(case_id=meta['case_id'], metrics=scores, capture_window=windows)
    if own_calibration:
        result['calibration'] = calibration
    return result


def measure(run, meta, calibration=None):
    """Read a completed native PSF after the caller verifies execution evidence."""
    status_path = run/'run_status.json'
    status_sha = common.sha(status_path)
    status = common.read(status_path)
    common.need(status['status'] == 'spectre_completed' and status['exit_code'] == 0,
                'No complete C0 Spectre execution to measure')
    native, = [row['path'] for row in status['raw_inventory']
               if row['path'] in ('raw/tranResponse.tran', review.RAW_NAME)]
    live = common.raw_inventory(run)
    common.need(common.matches_historical_inventory(status['raw_inventory'], live),
                'C0 raw inventory differs from original execution evidence')
    parser = partial(review.parse_selected,
                     required={'time', *review.save_names((review.R5/'quiet.scs').read_text('ascii'))})
    raw = review.safe_raw(run, dict(status, raw_inventory=live), native.removeprefix('raw/'), parser=parser)
    common.need(raw.unit('time') == 's', 'C0 native time sweep must explicitly use seconds')
    review.collect_r5.validate_raw(raw, meta['stop_s'])
    frozen = review.pinned_r5()
    functions = aligned.scoring_functions()
    records, audit = functions.r5.extract_records(raw, meta['clock_spec'])
    result = score_records(meta, records, calibration, functions, frozen)
    common.need(common.sha(status_path) == status_sha, 'Run status changed while measuring C0')
    result.update(clock_audit=audit, run_status_sha256=status_sha, tran_sha256=raw.sha256)
    return result
