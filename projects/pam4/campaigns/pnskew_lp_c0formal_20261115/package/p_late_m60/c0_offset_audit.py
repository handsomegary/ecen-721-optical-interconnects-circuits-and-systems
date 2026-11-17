"""Audit the common residual using the retained zero-skew training and payload raws."""

from functools import partial
from bisect import bisect_left
import math
from statistics import fmean

from c0_plate_m60 import formal, common, previous, review, score


TRAINING = ('zero',0,-1,'training')
PAYLOAD = ('zero',0,-1,'payload')
MONITORS = {'before_driver':('PNC_PREP','PNC_PREN'), 'AFE_output':('X_o_p','X_o_m')}


def stimulus_audit():
    training, tm = formal.deck.render(*TRAINING)
    payload, pm = formal.deck.render(*PAYLOAD)
    common.need(tm['clock_spec']==pm['clock_spec'], 'Zero-skew clocks differ')
    waveforms = {}

    def remove_sources(deck):
        out = {}
        for name in ('PAM4Vp','PAM4Vm'):
            begin, end, *_, timing, values = review.pn_stage.pwl_block(deck,name)
            out[name] = (timing,values)
            deck = deck[:begin]+deck[end:]
        return deck,out

    tdeck,t = remove_sources(training)
    pdeck,p = remove_sources(payload)
    common.need(tdeck==pdeck, 'Training differs from payload outside PWL stimuli')
    for name in t:
        common.need(t[name][0]==p[name][0] and set(t[name][1])==set(p[name][1]),
                    'PWL has changed times, levels or differential centering')
        waveforms[name] = dict(levels_V=sorted(set(t[name][1])),
                               first_training_V=t[name][1][0],first_payload_V=p[name][1][0],
                               identical_time_grid=True,training_values_differ_from_payload=t[name][1]!=p[name][1])
    return dict(non_stimulus_deck_identical=True,pwl=waveforms,
                training_initial_differential_V=t['PAM4Vp'][1][0]-t['PAM4Vm'][1][0],
                payload_initial_differential_V=p['PAM4Vp'][1][0]-p['PAM4Vm'][1][0],
                training_seed=formal.deck.SEEDS['training'],payload_seed=formal.deck.SEEDS['payload'])


def observations(root, job, calibration, pins, functions, required):
    _, meta = formal.deck.render(*job)
    directory = root/meta['case_id']
    with formal.original.lock_case(directory):
        prior,_,report_sha,status = formal.read_report(root,job,pins)
        if job==TRAINING:
            common.need(prior['calibration']==calibration,
                        'Retained training sample did not supply the frozen detector')
        live = common.raw_inventory(directory)
        common.need(common.matches_historical_inventory(status['raw_inventory'],live), 'Retained inventory differs')
        native, = [row for row in live if row['path'] in ('raw/tranResponse.tran',review.RAW_NAME)]
        required = required | {signal for pair in MONITORS.values() for signal in pair}
        raw = review.safe_raw(directory,dict(status,raw_inventory=live),native['path'].removeprefix('raw/'),
                              parser=partial(review.parse_selected,required=required))
        common.need(raw.sha256==prior['tran_sha256'] and raw.unit('time')=='s', 'Retained PSF evidence differs')
        review.collect_r5.validate_raw(raw,meta['stop_s'])
        records, clock_audit = functions.r5.extract_records(raw,meta['clock_spec'])
        common.need(clock_audit==prior['clock_audit'], 'Retained clock evidence differs')
        _, after = formal.execution(directory,meta,pins)
        common.need(after==prior['execution_files_sha256'] and common.sha(directory/formal.MEASURE)==report_sha,
                    'Run evidence changed during audit')
    return prior,records,dict(case_id=meta['case_id'],measurement_sha256=report_sha,raw_sha256=raw.sha256,
                            slurm_task_id=status['slurm_job_id'],saved_analog_monitor_window=monitor_means(raw))


def monitor_means(raw):
    times = raw.values['time']
    start = bisect_left(times,formal.deck.T0+128*review.UI)
    split = bisect_left(times,previous.CUTOFF_S)
    stop = bisect_left(times,formal.deck.T0+640*review.UI)
    common.need(start<split<stop, 'Saved analog monitor has incomplete scored-time intervals')
    data = {}
    for window,lo,hi in (('early',start,split),('late',split,stop)):
        row = {}
        for label,(p,n) in MONITORS.items():
            positive,negative = raw.values[p][lo:hi],raw.values[n][lo:hi]
            row[label] = dict(mean_differential_V=fmean(vp-vn for vp,vn in zip(positive,negative,strict=True)),
                              mean_common_mode_V=(fmean(positive)+fmean(negative))/2,
                              saved_signals=[p,n])
        data[window] = row | dict(sample_count=hi-lo,first_time_s=times[lo],last_time_s=times[hi-1])
    return data


def residual_components(ffe, samples, quantized, labels, times, detector):
    """Attribute residual to the frozen linear detector and separate symbol mix."""
    half = ffe.HALF
    inputs = len(labels)
    centers = labels[half:-half]
    predictions = ffe.predict_window(quantized,detector)
    analog_outputs = ffe.predict_window(samples,detector)
    target = [ffe.TARGETS[label] for label in centers]
    residual = [pred-actual for pred,actual in zip(predictions,target,strict=True)]
    tap_means = [fmean(quantized[tap:inputs-2*half+tap]) for tap in range(2*half+1)]
    center = detector['normalization_training_mean_V']
    scale = detector['normalization_training_centered_RMS_V']
    bias = detector['bias_in_target_symbol_units']
    linear_terms = [w*(x-center)/scale for w,x in zip(detector['weights_on_normalized_input'],tap_means,strict=True)]
    expected_residual = bias+math.fsum(linear_terms)-fmean(target)
    common.need(math.isclose(fmean(residual),expected_residual,rel_tol=1e-10,abs_tol=1e-13),
                'Frozen FFE linear decomposition failed')
    counts = [centers.count(k) for k in range(4)]
    by_level = [fmean(v for v,label in zip(residual,centers,strict=True) if label==k)
                if count else None for k,count in enumerate(counts)]
    return dict(window=previous.window_metrics(ffe,predictions,centers,times[half:-half],score.VERIFY[0]+half),
        center_symbol_histogram=counts,mean_residual_by_true_level=by_level,
        mean_quantized_ADC_V=fmean(quantized),mean_analog_ADC_V=fmean(samples),
        frozen_intercept_target_units=bias,frozen_normalization_center_V=center,
        frozen_ADC_input_scale_V=scale,mean_tap_linear_contributions_target_units=linear_terms,
        mean_predicted_target_units=fmean(predictions),mean_true_target_units=fmean(target),
        mean_quantization_contribution_target_units=fmean(p-a for p,a in zip(predictions,analog_outputs,strict=True)))


def compare_residuals(training, payload):
    remaining = dict(
        delta_frozen_intercept=payload['frozen_intercept_target_units']-training['frozen_intercept_target_units'],
        delta_held_sample_linear_terms=math.fsum(payload['mean_tap_linear_contributions_target_units'])-
                                       math.fsum(training['mean_tap_linear_contributions_target_units']),
        negative_delta_target_sequence_mean=training['mean_true_target_units']-payload['mean_true_target_units'],
        delta_FS_ADC_quantization_contribution=payload['mean_quantization_contribution_target_units']-
                                              training['mean_quantization_contribution_target_units'],
    )
    before = training['mean_residual_by_true_level']
    after = payload['mean_residual_by_true_level']
    if None not in before+after:
        train_weights = [c/sum(training['center_symbol_histogram']) for c in training['center_symbol_histogram']]
        payload_weights = [c/sum(payload['center_symbol_histogram']) for c in payload['center_symbol_histogram']]
        remaining.update(residual_delta_from_label_mix_at_training_residuals=math.fsum(
                            r*(p-t) for r,t,p in zip(before,train_weights,payload_weights,strict=True)),
                         residual_delta_within_true_levels_at_payload_mix=math.fsum(
                            (p-t)*w for t,p,w in zip(before,after,payload_weights,strict=True)),
                         equal_class_weight_delta=fmean(after)-fmean(before))
    return remaining


def audit(root, calibration, pins, functions, required):
    start,stop = score.VERIFY
    ffe = functions.opt.evaluate_frozen.__globals__['ffe']
    train,tr,train_evidence = observations(root,TRAINING,calibration,{},functions,required)
    payload,pr,payload_evidence = observations(root,PAYLOAD,calibration,pins,functions,required)
    out = {}
    for plane in score.aligned.PLANES:
        choice = calibration['selections'][plane]
        detector = choice['detectors']['ADC_FFE']
        planes = {}
        for kind,records,original in (('training',tr,train),('payload',pr,payload)):
            indexed = {record[0]:record for record in records[plane]}
            samples,labels,times = score.aligned.capture(indexed,formal.deck.symbols(kind),start,stop,choice['lag'])
            common.need(times[0]>=previous.CUTOFF_S and len(times)==192, 'Matched late aperture window differs')
            fs = choice['detectors']['ADC_fullscale_differential_Vpp']
            quantized, clipping = functions.metrics.quantize_symmetric(samples,fs,7)
            data = residual_components(ffe,samples,quantized,labels,times,detector)
            data.update(clipping_count=clipping,ADC_input_count=len(samples))
            if kind=='training':
                common.need(data['window']['sample_count']==176
                            and data['window']['confusion_rows_true_cols_decided']==
                                formal.metric(original,plane)['confusion_rows_true_cols_decided'],
                            'Historical training score does not match replay')
            else:
                all_samples,all_labels,all_times = score.aligned.capture(
                    indexed,formal.deck.symbols(kind),*score.PAYLOAD,choice['lag'])
                check = previous.score_plane(all_samples,all_labels,all_times,choice['detectors'],functions,
                                             original['metrics'][plane])
                common.need(data['window']['confusion_rows_true_cols_decided']==
                          check['late_rescore']['confusion_rows_true_cols_decided'], 'Payload late score differs')
            planes[kind] = data
        out[plane] = planes | {'payload_minus_training':compare_residuals(planes['training'],planes['payload'])}
    return dict(schema='pam4_c0_frozen_detector_offset_audit_v1',stimulus_comparison=stimulus_audit(),
                training_evidence=train_evidence,payload_evidence=payload_evidence,selection_files_sha256=pins,
                late_adc_tx_indices=[start,stop],evaluation_samples_per_plane=176,planes=out,
                interpretation='Exposes seed/label mix, frozen intercept, and held/quantized sample contribution. '
                 'No intercept estimate from scored payload or claim about unsaved analog bias nodes.')
