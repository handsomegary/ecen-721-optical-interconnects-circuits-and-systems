"""Offline CDAC pilot estimates from preserved measured summaries; no simulator access."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics


ROOT = Path(__file__).resolve().parent
AUDIT_PATH = ROOT/'evidence/source_audit.json'
SUMMARY_PATH = ROOT/'evidence/source_summary.json'
AUDIT_SHA = 'bc8c4e64c7d053b458adc5efe1c3c865202d1e02e52c7d48581f58c62898f9c4'
SUMMARY_SHA = 'ab2cdaaa6840bbb81841bc120d5d2cb69a47553c1e71e2c8ec22f0f2283dec95'
# Linear MOM-equivalent values from the original reviewed sar7_native.py.
# No private model or source deck is loaded by this planner.
UNIT = 1.4605585e-15
UNIT_SHUNT = .1879047e-15
BRIDGE = 2.0605472e-15
BRIDGE_SHUNT = .2120421e-15


def fit_states(summary, fit, lsb):
    weights = fit['weight_b6_to_b0_lsb']
    rows = []
    for index,code in enumerate(summary['codes']):
        observed = code['comparator']
        points = sorted((p for p in summary['sense']['points'] if p['index']==index),
                        key=lambda p:-p['bit'])
        state_rows = []
        for point in points:
            bit = point['bit']
            # Accepted higher bits, active trial=1, unresolved lower bits=0.
            candidate = (observed >> (bit+1) << (bit+1)) | (1 << bit)
            bits = [(candidate>>b)&1 for b in range(6,-1,-1)]
            contribution = sum(w*b for w,b in zip(weights,bits,strict=True))
            held_lsb = point['held_diff_V']/lsb
            intercept = held_lsb+contribution
            state_rows.append(dict(bit=bit,candidate=candidate,held_lsb=held_lsb,
                                   intercept_lsb=intercept,actual_bit=(observed>>bit)&1))
        intercept = statistics.mean(r['intercept_lsb'] for r in state_rows)
        sampled = (intercept-fit['offset_lsb'])/fit['sample_gain']
        for row in state_rows:
            row['trajectory_residual_lsb'] = row['intercept_lsb']-intercept
        rows.append(dict(index=index,expected=code['expected'],actual=observed,
            nominal_input_lsb=code['expected']+.5-64,inferred_sampled_input_lsb=sampled,
            inferred_sample_error_lsb=sampled-(code['expected']+.5-64),
            intercept_std_lsb=statistics.pstdev(r['intercept_lsb'] for r in state_rows),
            intercept_minmax_lsb=[min(r['intercept_lsb'] for r in state_rows),
                                  max(r['intercept_lsb'] for r in state_rows)],states=state_rows))
    return rows


def decide(row, weights, offset, sample_gain, threshold=0., trajectory=False, perturbation=0.):
    code = 0
    for step,bit in enumerate(range(6,-1,-1)):
        candidate = code | (1<<bit)
        subtract = sum(w*((candidate>>b)&1) for w,b in zip(weights,range(6,-1,-1),strict=True))
        residual = row['states'][step]['trajectory_residual_lsb'] if trajectory else 0.
        held = offset+sample_gain*row['inferred_sampled_input_lsb']-subtract+residual+perturbation
        if held >= threshold:
            code = candidate
    return code


def outcome(rows, weights, offset, sample_gain, threshold=0., trajectory=False):
    codes = [decide(r,weights,offset,sample_gain,threshold,trajectory) for r in rows]
    errors = [c-r['expected'] for c,r in zip(codes,rows,strict=True)]
    actual_delta = [c-r['actual'] for c,r in zip(codes,rows,strict=True)]
    return dict(codes=codes,errors=errors,wrong=sum(e!=0 for e in errors),
                sum_abs_error=sum(abs(e) for e in errors),max_abs_error=max(abs(e) for e in errors),
                matches_actual=sum(e==0 for e in actual_delta),
                max_abs_difference_from_actual=max(abs(e) for e in actual_delta))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,help='Write a new prediction JSON; default is stdout')
    args = parser.parse_args()
    if hashlib.sha256(AUDIT_PATH.read_bytes()).hexdigest()!=AUDIT_SHA:
        raise ValueError('Unexpected source audit evidence')
    if hashlib.sha256(SUMMARY_PATH.read_bytes()).hexdigest()!=SUMMARY_SHA:
        raise ValueError('Unexpected source summary evidence')
    audit = json.loads(AUDIT_PATH.read_text(encoding='utf-8'))
    summary = json.loads(SUMMARY_PATH.read_text(encoding='utf-8'))
    if audit['source_receipts_sha256']['summary']!=SUMMARY_SHA:
        raise ValueError('Summary does not match audit receipt')
    fit = audit['weight_fit']
    weights = fit['weight_b6_to_b0_lsb']
    offset = fit['offset_lsb']
    gain = fit['sample_gain']
    lsb = audit['lsb_V']
    rows = fit_states(summary,fit,lsb)
    ideal = [64.,32.,16.,8.,4.,2.,1.]
    ratios = [i/w for i,w in zip(ideal,weights,strict=True)]
    U,S,B,BS = UNIT,UNIT_SHUNT,BRIDGE,BRIDGE_SHUNT
    counts = [8.,4.,2.,1.,4.,2.,1.]
    original_main = sum(counts[:4])
    original_low = sum(counts[4:])
    cm = original_main*(U+S)+B+BS
    cl = (original_low+1)*(U+S)+B+BS
    determinant = cm*cl-B*B
    # Preserve total main-bank capacitance; the low bank and its dummy stay fixed.
    kmain = original_main/sum(c*r for c,r in zip(counts[:4],ratios[:4],strict=True))
    scales = [kmain*r for r in ratios[:4]]+[1.]*3
    # Restore binary attenuation B'/Cl'=1/8 with bridge geometry and shunts tied.
    bridge_scale = 8*(U+S)/(7*B-BS)
    new_main = sum(c*s for c,s in zip(counts[:4],scales[:4],strict=True))
    new_low = sum(c*s for c,s in zip(counts[4:],scales[4:],strict=True))
    B2,BS2 = B*bridge_scale,BS*bridge_scale
    cm2 = new_main*(U+S)+B2+BS2
    cl2 = (new_low+1)*(U+S)+B2+BS2
    # Empirical mean main attenuation identifies one descriptive fixed shunt.
    a = cm-B*B/cl
    a2 = cm2-B2*B2/cl2
    fixed_extra_main_cap = a*(1/kmain-1)
    determinant_eff = (cm+fixed_extra_main_cap)*cl-B*B
    determinant_eff2 = (cm2+fixed_extra_main_cap)*cl2-B2*B2
    main_denominator_ratio = (a+fixed_extra_main_cap)/(a2+fixed_extra_main_cap)
    low_denominator_ratio = bridge_scale*determinant_eff/determinant_eff2
    shaped = [w*s*main_denominator_ratio for w,s in zip(weights[:4],scales[:4],strict=True)]
    shaped += [w*s*low_denominator_ratio for w,s in zip(weights[4:],scales[4:],strict=True)]
    shape_ratio = kmain*main_denominator_ratio
    if max(abs(w/i-shape_ratio) for w,i in zip(shaped[:4],ideal[:4],strict=True))>=1e-12:
        raise ValueError('Main-bank shape does not reproduce its intended transfer')
    base_ref = .100*a/(32*U)
    candidates = [dict(case='ref_common_span127',reference_factor=127/sum(weights),
                       cap_scales_b6_to_b0=[1.]*7,bridge_scale=1.,
                       denominator_ratio_main=1.,denominator_ratio_low=1.),
                  dict(case='main_ratio_binary_bridge',reference_factor=1/shape_ratio,
                       bridge_scale=bridge_scale,
                       cap_scales_b6_to_b0=scales,denominator_ratio_main=main_denominator_ratio,
                       denominator_ratio_low=low_denominator_ratio)]
    sense_crossing = audit['sense_affine']['sense_stage_zero_crossing_input_LSB']
    for case in candidates:
        f = case['reference_factor']
        ws = [w*s*(case['denominator_ratio_main'] if k<4 else case['denominator_ratio_low'])*f
              for k,(w,s) in enumerate(zip(weights,case['cap_scales_b6_to_b0'],strict=True))]
        # Only the capacitive reference contribution scales; preserve fitted excess offset.
        new_offset = .5*sum(ws)+(offset-.5*sum(weights))
        physical_caps = {}
        for side in ('p','n'):
            for bit,c,s in zip(range(6,-1,-1),counts,case['cap_scales_b6_to_b0'],strict=True):
                if s!=1.:
                    physical_caps['Cunit'+str(bit)+side] = c*U*s
                    physical_caps['Ctop'+str(bit)+side] = c*S*s
                    physical_caps['Cbott'+str(bit)+side] = c*S*s
            if case['bridge_scale']!=1.:
                physical_caps['Cbridge'+side] = B*case['bridge_scale']
                physical_caps['Cbridge_main'+side] = BS*case['bridge_scale']
                physical_caps['Cbridge_low'+side] = BS*case['bridge_scale']
        case.update(weights_lsb_b6_to_b0=ws,predicted_span_lsb=sum(ws),offset_lsb=new_offset,
            reference_span_V=base_ref*f,reference_hi_V=.45+.5*base_ref*f,
            reference_lo_V=.45-.5*base_ref*f,
            correction=dict(reference_span_V=base_ref*f,capacitance_F=physical_caps),
            capacitance_fF_b6_to_b0=[c*s*U/1e-15 for c,s in zip(counts,case['cap_scales_b6_to_b0'],strict=True)],
            affine_model=outcome(rows,ws,new_offset,gain),
            path_residual_model=outcome(rows,ws,new_offset,gain,trajectory=True),
            sensitivity_sense_stage_zero_as_threshold=outcome(rows,ws,new_offset,gain,threshold=sense_crossing),
            sensitivity_fit_rmse_code_intervals=[[decide(r,ws,new_offset,gain,perturbation=-fit['heldout_rmse_lsb']),
                                                   decide(r,ws,new_offset,gain,perturbation=fit['heldout_rmse_lsb'])]
                                                  for r in rows])
    result = dict(source_job='760348',source_summary_sha256=hashlib.sha256(SUMMARY_PATH.read_bytes()).hexdigest(),
        source_audit_sha256=hashlib.sha256(AUDIT_PATH.read_bytes()).hexdigest(),
        measurements_available_locally=False,
        inference='Per-conversion sampled input inferred from 7 measured held values, actual prefix states, and existing9parameterfit; not direct sample measurements',
        actual_codes=[r['actual'] for r in rows],expected_codes=[r['expected'] for r in rows],
        baseline_affine=outcome(rows,weights,offset,gain),
        baseline_path_residual=outcome(rows,weights,offset,gain,trajectory=True),
        baseline_observed_held_sign_decision_matches=sum((s['held_lsb']>=0)==bool(s['actual_bit']) for r in rows for s in r['states']),
        existing_fit_cv_rmse_lsb=fit['heldout_rmse_lsb'],
        inferred_sample_records=rows,nominal_reference_span_V=base_ref,
        cap_shape_design=dict(main_group_total_units_before=original_main,main_group_total_units_after=new_main,
            low_group_total_units_excluding_dummy_before=original_low,low_group_total_units_excluding_dummy_after=new_low,
            dummy_unchanged=True,low_bank_unchanged=True,main_shape_constant=kmain,
            binary_bridge_scale=bridge_scale,binary_low_to_main_attenuation=B2/cl2,
            effective_fixed_extra_main_capacitance_F=fixed_extra_main_cap,
            cap_and_top_bottom_shunts_scale_together=True,
            denominator_model='Two-node linear capacitor matrix plus one fit-derived fixed main shunt; transistor voltage dependence and settling changes not identified'),
        cases=candidates,
        limits=['All outcomes are counterfactual model estimates, not simulator measurements',
                'Exact sampled values absent locally; inferred samples absorb residual model error',
                'Baseline affine match rate and 0.861LSB heldout RMSE bound confidence',
                'Path-residual transfer assumes new paths preserve old bit-index residuals',
                'Sense-stage zero crossing is not comparator offset; threshold variant is sensitivity only',
                'Cap denominator correction omits unidentified voltage-dependent MOS parasitics and settling changes',
                'Only main Cunit/Ctop/Cbott are rebalanced; low bank and dummy unchanged',
                'Bridge coupling and both bridge shunts scale together to restore binary attenuation'])
    encoded = json.dumps(result,indent=2)+'\n'
    if args.output is None:
        print(encoded,end='')
    else:
        with args.output.open('x',encoding='utf-8',newline='\n') as output:
            output.write(encoded)
        print(args.output.name,hashlib.sha256(args.output.read_bytes()).hexdigest())


if __name__=='__main__':
    main()
