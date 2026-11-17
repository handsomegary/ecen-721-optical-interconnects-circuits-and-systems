#!/usr/bin/env python3
"""Collect only derived metrics and hashes; no models or raw waveforms exported."""
import hashlib,json,math,pathlib,re
import p6_bench as b
import p6_dynamic as d

EXPECTED_MAIN_SHA='002300afbc872cca7c0bab744740eb74ff2cc71e770832c6e6d97c447dbfff78'

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1048576),b''):h.update(block)
    return h.hexdigest()

def clean(obj):
    if isinstance(obj,dict):return {k:clean(v) for k,v in obj.items() if k not in ['directory','selected_primitive_op']}
    if isinstance(obj,list):return [clean(v) for v in obj]
    return obj

def time_bounds(path):
    with path.open('rb') as f:
        first=f.read(131072);f.seek(max(0,path.stat().st_size-131072));last=f.read()
    pattern=rb'^\s*"time"\s+([+\-0-9.eE]+)\s*$'
    a=re.findall(pattern,first,re.M);z=re.findall(pattern,last,re.M)
    if not a or not z:raise ValueError('Could not independently verify saved time bounds')
    return float(a[0]),float(z[-1])

def main():
    load=lambda name:json.loads((b.BASE/name).read_text())
    gridfiles=['grid_v2_summary.json','expanded_summary.json','inverter_summary.json','double_eq_summary.json']
    grids=[load(n)['results'] for n in gridfiles]
    if list(map(len,grids))!=[288,288,160,96]:raise ValueError('Incomplete grid')
    counts=[]
    for name,rr in zip(gridfiles,grids):
        valid=[r for r in rr if r.get('static_headroom_ok')]
        counts.append({'source':name,'configuration_count':len(rr),'static_headroom_screen_count':len(valid),
            'best_absolute_held_AC_gain':clean(max(valid,key=lambda r:r['hold_gain_56GHz_VV']))})
    refine=load('refine_summary.json')['results'];tune=load('tune_summary.json')['results']
    dynamic=load('dynamic_summary.json');extra=load('extra_summary.json');eq=load('equalized_summary.json');pr=load('peaking_range_summary.json')
    if (len(refine),len(tune),len(dynamic['results']),len(extra['results']),len(eq['results']))!=(18,8,21,9,3):raise ValueError('Incomplete confirmation runs')
    if len(pr['AC_results'])!=8 or len(pr['results'])!=2:raise ValueError('Incomplete peaking range confirmation')
    for rr in grids+[refine,tune,dynamic['results'],extra['results'],eq['results'],[eq['low_reference_ac']],pr['AC_results'],pr['results']]:
        for r in rr:
            if r.get('analysis_error') or r.get('run_status',{}).get('exit_code')!=0:raise ValueError('Failed simulation or analysis')
    checked=[]
    for rr in [dynamic['results'],extra['results'],eq['results'],pr['results']]:
        for r in rr:
            raw=list((pathlib.Path(r['directory'])/'raw').glob('tranResponse.tran*'))
            if len(raw)!=1:raise ValueError('Ambiguous waveform')
            lo,hi=time_bounds(raw[0]);clocked=r.get('clocked',True);stop=8e-9 if clocked else 3e-9
            if lo>(5e-9 if clocked else 2.5e-9) or hi<stop-1e-15:raise ValueError('Saved time coverage incomplete')
            checked.append({'run':str(pathlib.Path(r['directory']).relative_to(b.BASE)),'saved_first_time_s':lo,'saved_last_time_s':hi})
            # Older dynamic labels used the differential fitted DC term.
            if r in dynamic['results'] and 'steady_window_differential_offset_drift_V' not in r:
                r['steady_window_differential_offset_drift_V']=r.pop('steady_window_common_mode_drift_V')
    # Explicitly check real output common-mode settling for the two largest-swing VGA runs.
    cmchecks=[]
    for r in dynamic['results']:
        if r.get('clocked') and r['input_Vppd']==.4 and r['config']['ch'] in [5e-15,10e-15]:
            z=d.analyze(pathlib.Path(r['directory']),r['config'],r['input_Vppd'],r['tone_Hz'],True,8e-9)
            r['steady_window_common_mode_drift_V']=z['steady_window_common_mode_drift_V']
            cmchecks.append({'hold_capacitance_per_lane_per_side_F':r['config']['ch'],'output_common_mode_half_window_drift_V':z['steady_window_common_mode_drift_V']})
    for r in extra['results']:
        if r.get('SNDR_includes_simulated_noise'):
            r['held_fit']['SNDR_with_simulated_noise_dB']=r['held_fit'].pop('deterministic_SNDR_dB')
    nominal=next(r for r in dynamic['results'] if r.get('clocked') and r['config']['ch']==5e-15 and r['input_Vppd']==.2)
    finer=next(r for r in extra['results'] if r['noiseseed'] is None)
    stepcheck={'conditions':'CH5f,0.2Vppd,55.5625GHz,zero noise,measured clock timing',
        'maxstep_0p2ps_gain_VV':nominal['held_gain_VV'],'maxstep_0p1ps_gain_VV':finer['held_gain_VV'],
        'relative_gain_change_percent':100*(finer['held_gain_VV']/nominal['held_gain_VV']-1),
        'SNDR_change_dB':finer['held_fit']['deterministic_SNDR_dB']-nominal['held_samples_fit']['deterministic_SNDR_dB']}
    mainpath=pathlib.Path('<PDK_ROOT>/models/spectre/pdk_model.scs')
    actualhash=digest(mainpath)
    if actualhash!=EXPECTED_MAIN_SHA:raise ValueError('PDK main model changed')
    if pathlib.Path('/path/to/local/cadence-home/pdk_probe').exists():raise ValueError('Prior removed directory unexpectedly exists')
    report={'schema_version':1,'scope':'schematic feasibility screening of existing 28nm LVT,not full ADC receiver signoff',
        'course_requirements':{'source':'https://people.engr.tamu.edu/spalermo/ecen689_oi/ecen721_project.pdf','PAM4_bit_rate_bps':224e9,'Nyquist_Hz':56e9,'AFE_peaking_up_to_dB':20,'ADC_nominal_bits':7,'ADC_sample_rate_per_s':112e9,'differential_PN_skew_range_UI':[-.5,.5],'explicit_noise_or_power_limit_in_course_spec':None},
        'test_conditions':{'model_section':'tt','temperature_C':25,'supply_V':.9,'input_device_drawn_L_m':30e-9,'tail_device_drawn_L_m':60e-9,'cells':['nmos_lvt','pmos_lvt'],'parasitic_flags':{'_ccoflag':1,'_rcoflag':1,'_rgflag':1},'sampler_lanes':8,'sample_rate_per_s':112e9,'lane_clock_Hz':14e9,'clock_edge_s':1e-12,'measured_track_duty_approximately':.5,'hold_capacitance_per_lane_per_side_F':[5e-15,10e-15,20e-15],'sampler_N_and_P_drawn_W_m':3e-6,'clocked_tone_Hz':112e9*127/256,'held_sample_count':256,'sampling_rule':'actual CK fall midpoint plus0.5ps to edge end plus1ps hold delay; phase shift one UI per lane','transient_noise_max_Hz':150e9,'transient_noise_cutoff_sensitivity_Hz':300e9,'transient_noise_flattened_below_Hz':5e8,'input_source':'ideal zero-impedance balanced voltage source; no channel'},
        'grid_screen':counts,'grid_configuration_evaluations':832,'additional_low_reference_tuning_evaluations':8,
        'refined_AC_noise_cases':clean(refine),'CTLE_low_reference_tuning':clean(tune),
        'best_absolute_gain_dynamic':clean(dynamic),'sampled_transient_noise_and_step_checks':clean(extra),
        'strong_peaking_CTLE_confirmation':clean(eq),'CTLE_adjustable_peaking_range_confirmation':clean(pr),
        'verification':{'all_summary_records_have_successful_simulation_status':True,'saved_transient_coverage_checks':checked,'numerical_step_check':stepcheck,'common_mode_settling_checks':cmchecks,'main_model_sha256':actualhash,'main_model_unchanged_from_baseline':True,'prior_pdk_probe_absent':True,'script_sha256':{f.name:digest(f) for f in b.BASE.glob('p6_*.py')},'parser_sha256':digest(b.BASE/'psf_ascii.py')},
        'limitations':['Only TT25C/0.9V schematic; no extracted interconnect parasitics or full PVT validation.','RF validity of this exact model revision at56GHz and150/300GHz noise cutoff has not been established.','Ideal zero-jitter complementary clocks; no physical clock/bias generation or distribution. Reported ideal clock power is net delivered energy,not complete clock-system power.','Transient noise includes switching/folding within the modeled finite bandwidth; noise below500MHz is flattened; finite seeds and256-sample windows are screening estimates,not precision noise metrology.','Sine tests do not prove PAM4 BER,channel equalization,PN-skew compensation,7-bit ADC quantization or ADC ENOB. Nominal7-bit resolution does not require7ENOB by itself.','Static headroom filter only checks node voltage ranges; it is not saturation,reliability or foundry approval.','Equalization and absolute gain are separate quantities; lowering low-frequency gain can increase peaking while leaving a small held signal.'],
        'recommendation':'28nm is worth retaining as a Project6 device candidate: the measured CTLE/sampler has initial56GHz frontend feasibility. Complete Project6 feasibility remains unproven until channel,PAM4,ADC,PN-skew,nonideal clocks andPVT/PEX are evaluated;16.6GHz from the earlier low-power TIA is not a process speed ceiling.'}
    output=b.BASE/'Project6_feasibility_results.json'
    output.write_text(json.dumps(report,indent=2,ensure_ascii=True,allow_nan=False)+'\n')
    print(json.dumps({'summary_bytes':output.stat().st_size,'summary_sha256':digest(output),'stepcheck':stepcheck,'common_mode_checks':cmchecks,'PDK_unchanged':True,'old_probe_absent':True}))

if __name__=='__main__':main()
