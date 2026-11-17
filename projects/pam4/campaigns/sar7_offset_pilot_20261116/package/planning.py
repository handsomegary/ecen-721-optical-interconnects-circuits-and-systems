"""Reproduce bounded descriptive offset-pilot predictions from immutable scalar evidence."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics


ROOT = Path(__file__).resolve().parent
FEATURES = ROOT/'evidence/source_features.json'
FEATURES_SHA = 'ebf8da4379a8380eeea317870f22ad9ee639ca4da566768eabef5acb96cbbae4'
TRIM_RESISTANCE_OHM = 1.5
FLOAT_REL_TOL = 1e-11
FLOAT_ABS_TOL = 1e-12


def read_features():
    payload = FEATURES.read_bytes()
    if hashlib.sha256(payload).hexdigest()!=FEATURES_SHA:
        raise ValueError('Changed original760874 scalar evidence')
    source = json.loads(payload)
    if source['schema']!='pam4_sar7_offset_source_features_v1' or source['source_job_id']!='760874':
        raise ValueError('Unexpected source feature identity')
    if len(source['cases'])!=12 or len(source['trials'])!=84:
        raise ValueError('Expected12conversions and84original comparisons')
    return source


def threshold_band(rows, frame, field):
    zeros = [row['frames'][frame][field] for row in rows if row['decision']==0]
    ones = [row['frames'][frame][field] for row in rows if row['decision']==1]
    lower,upper = max(zeros),min(ones)
    threshold = (lower+upper)/2
    matched = sum(int(row['frames'][frame][field]>=threshold)==row['decision'] for row in rows)
    loco = []
    for index in range(12):
        train = [row for row in rows if row['index']!=index]
        test = [row for row in rows if row['index']==index]
        t = (max(row['frames'][frame][field] for row in train if row['decision']==0)
             +min(row['frames'][frame][field] for row in train if row['decision']==1))/2
        loco.append(sum(int(row['frames'][frame][field]>=t)==row['decision'] for row in test))
    return dict(frame=frame,voltage_field=field,lower_exclusive_LSB=lower,upper_inclusive_LSB=upper,
                separable=lower<upper,midpoint_LSB=threshold,decision_matches=matched,
                leave_one_conversion_out_matches=sum(loco),tested=84,
                interpretation='Descriptive finaldecision threshold; not independently measured static comparator offset')


def sense_fit(rows, frame):
    xs = [row['frames'][frame]['held_LSB'] for row in rows]
    ys = [row['frames'][frame]['sense_LSB'] for row in rows]
    line = statistics.linear_regression(xs,ys)
    residuals = [y-line.slope*x-line.intercept for x,y in zip(xs,ys,strict=True)]
    return dict(frame=frame,slope_V_per_V=line.slope,output_intercept_LSB=line.intercept,
                output_rmse_LSB=math.sqrt(statistics.mean(r*r for r in residuals)))


def predict(source, frame, threshold, slope, trim_ohm, weights=None, new_path_held_perturbation=0.):
    lsb = source['lsb_V']
    if weights is None:
        weights = source['weight_fit']['weight_b6_to_b0_lsb']
    trials = {(row['index'],row['bit']):row for row in source['trials']}
    codes,errors,changed = [],[],0
    for conversion in source['cases']:
        code = 0
        for bit in range(6,-1,-1):
            row = trials[conversion['index'],bit]
            candidate = code | (1<<bit)
            actual_bits = row['actual_pre_control_bits_b6_to_b0']
            candidate_bits = [(candidate>>b)&1 for b in range(6,-1,-1)]
            held_adjust = -sum(w*(new-old) for w,new,old in zip(weights,candidate_bits,actual_bits,strict=True))
            different = candidate!=row['actual_pre_control_word']
            changed += different
            if different:
                held_adjust += new_path_held_perturbation
            bias = -trim_ohm*row['precomparison_total_current_A']/lsb
            sensed = row['frames'][frame]['sense_LSB']+slope*held_adjust+bias
            if sensed>=threshold:
                code = candidate
        codes.append(code)
        errors.append(code-conversion['expected'])
    return dict(codes=codes,errors=errors,wrong_conversions=sum(error!=0 for error in errors),
                sum_abs_code_error=sum(abs(error) for error in errors),max_abs_code_error=max(abs(error) for error in errors),
                matches_source_actual_codes=sum(code==row['actual'] for code,row in zip(codes,source['cases'],strict=True)),
                changed_trial_control_states=changed)


def prediction():
    source = read_features()
    bands = [threshold_band(source['trials'],frame,field) for frame in ('pre','0','2') for field in ('held_LSB','sense_LSB')]
    fits = [sense_fit(source['trials'],frame) for frame in ('pre','0','2')]
    currents = [row['precomparison_total_current_A'] for row in source['trials']]
    frame_predictions = []
    for frame in ('pre','0','2'):
        band = next(row for row in bands if row['frame']==frame and row['voltage_field']=='sense_LSB')
        fit = next(row for row in fits if row['frame']==frame)
        if not band['separable'] or band['decision_matches']!=84:
            raise ValueError('Common threshold does not describe the source observations')
        threshold = band['midpoint_LSB']
        baseline = predict(source,frame,threshold,fit['slope_V_per_V'],0.)
        if baseline['matches_source_actual_codes']!=12:
            raise ValueError('Conditional model does not reproduce the observed source path')
        nominal = predict(source,frame,threshold,fit['slope_V_per_V'],TRIM_RESISTANCE_OHM)
        thresholds = [band['lower_exclusive_LSB']+1e-9,threshold,band['upper_inclusive_LSB']-1e-9]
        bracket = [dict(threshold_LSB=t,result=predict(source,frame,t,fit['slope_V_per_V'],TRIM_RESISTANCE_OHM))
                   for t in thresholds]
        fit_rmse = source['weight_fit']['heldout_rmse_lsb']
        sensitivity = [dict(new_path_held_residual_LSB=extra,
            result=predict(source,frame,threshold,fit['slope_V_per_V'],TRIM_RESISTANCE_OHM,
                           new_path_held_perturbation=extra)) for extra in (-fit_rmse,fit_rmse)]
        ideal_weights = predict(source,frame,threshold,fit['slope_V_per_V'],TRIM_RESISTANCE_OHM,
                                weights=[64.,32.,16.,8.,4.,2.,1.])
        frame_predictions.append(dict(frame=frame,baseline_consistency=baseline,conditional_trim=nominal,
            threshold_bracket_sensitivity=bracket,new_path_residual_sensitivity=sensitivity,
            ideal_binary_weight_sensitivity=ideal_weights))
    mean_current = statistics.mean(currents)
    return dict(schema='pam4_sar7_offset_pilot_prediction_v1',status='offline_conditional_prediction_not_measurement',
        source_job_id='760874',source_features_sha256=FEATURES_SHA,source_receipts_sha256=source['source_sha256'],
        source_portable_sha256=source['source_portable_sha256'],lsb_V=source['lsb_V'],
        LSB_units='Sense and held voltage quantities both use original input LSB0.78125mV',
        source_actual_codes=[row['actual'] for row in source['cases']],expected_codes=[row['expected'] for row in source['cases']],
        original_measured_scores=source['original_scores'],descriptive_thresholds=bands,sense_affine=fits,
        cases=[dict(index=0,case_key='matched_complementary_nor_load',electrical_parent_job_id='760874',
                    intervention='Matched complementary NOR output loading only; old electrical settings otherwise fixed',
                    prediction_status='Performance not numerically identified from source data',
                    distinction='A changed one-sided threshold or latch trajectory at unchanged CDAC would support loading/regeneration asymmetry'),
               dict(index=1,case_key='balanced_cml_resistor_trim',electrical_parent_job_id='760874',
                    intervention='Only balanced CML load resistors; no extra NOR and no CDAC/reference/sample/timing changes',
                    resistor_ohm={'RSENSE_P':498.5,'RSENSE_N':501.5},
                    sense_node_assignment={'RSENSE_P':'sensen','RSENSE_N':'sensep'},
                    delta_sense_diff_formula='-1.5ohm * observed total precomparison CML supply current',
                    observed_mean_total_current_A=mean_current,
                    estimated_delta_sense_diff_mean_V=-TRIM_RESISTANCE_OHM*mean_current,
                    estimated_delta_sense_diff_range_V=[-TRIM_RESISTANCE_OHM*max(currents),-TRIM_RESISTANCE_OHM*min(currents)],
                    estimated_delta_sense_diff_mean_LSB=-TRIM_RESISTANCE_OHM*mean_current/source['lsb_V'],
                    frame_predictions=frame_predictions)],
        execution_note='Predictions do not authorize execution; measured gate controls conditional index1. Cases independently start from760874.',
        reproduction_tolerance=dict(float_relative=FLOAT_REL_TOL,float_absolute=FLOAT_ABS_TOL),
        limits=['84labels/12sourcecodes are consistency checks, not independent counterfactual validation',
                'Finaldecision versus pre/trigger/2ps brackets do not identify a unique causal decision time',
                'New paths reuse measured pertrial residuals and descriptive CDAC weight shifts; settling/kickback can change',
                'Precomparison totalcurrent estimates resistor-induced differential bias; early-clock current changes are not measured here',
                'Mean500ohm is preserved, but actual gain/common-mode/loading must be measured in the new run',
                'The two cases are separate mechanism tests, not a resistor-amplitude sweep',
                'No all-code correctness,1.75GS/s,noise,PVT or fullADC validation is predicted'])


def tolerant_equal(actual, expected, where='root'):
    if isinstance(actual,bool) or isinstance(expected,bool):
        if type(actual) is not type(expected) or actual!=expected:
            raise ValueError('Prediction differs at '+where)
    elif isinstance(actual,int) or isinstance(expected,int):
        if type(actual) is not type(expected) or actual!=expected:
            raise ValueError('Prediction integer differs at '+where)
    elif isinstance(actual,float) and isinstance(expected,float):
        if not math.isclose(actual,expected,rel_tol=FLOAT_REL_TOL,abs_tol=FLOAT_ABS_TOL):
            raise ValueError('Prediction differs at '+where)
    elif isinstance(actual,dict) and isinstance(expected,dict):
        if set(actual)!=set(expected):
            raise ValueError('Prediction keys differ at '+where)
        for key in actual:
            tolerant_equal(actual[key],expected[key],where+'.'+key)
    elif isinstance(actual,list) and isinstance(expected,list):
        if len(actual)!=len(expected):
            raise ValueError('Prediction length differs at '+where)
        for index,(a,b) in enumerate(zip(actual,expected,strict=True)):
            tolerant_equal(a,b,where+'['+str(index)+']')
    elif type(actual) is not type(expected) or actual!=expected:
        raise ValueError('Prediction differs at '+where)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--output',type=Path,help='Write a new prediction file')
    group.add_argument('--check',type=Path,help='Check a frozen prediction with numeric tolerance')
    args = parser.parse_args()
    result = prediction()
    if args.check is not None:
        tolerant_equal(result,json.loads(args.check.read_text(encoding='utf-8')))
        print('Prediction reproduced within numeric tolerance')
        return
    encoded = json.dumps(result,indent=2)+'\n'
    if args.output is not None:
        with args.output.open('x',encoding='utf-8',newline='\n') as target:
            target.write(encoded)
        print(args.output.name,hashlib.sha256(args.output.read_bytes()).hexdigest())
    else:
        print(encoded,end='')


if __name__=='__main__':
    main()
