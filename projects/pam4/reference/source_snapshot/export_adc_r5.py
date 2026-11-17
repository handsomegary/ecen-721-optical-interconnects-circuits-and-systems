#!/usr/bin/env python3
"""Approved derived numerical export only; native cards and waves stay on VM."""
import argparse
import collections
import datetime
import hashlib
import json
import math
import re
from pathlib import Path

P=Path('/path/to/local/cadence-home/Desktop/cadence_projects/project6_28nm')

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_text())
def pick(d,keys): return {k:d[k] for k in keys if k in d}
def round_values(v):
    if isinstance(v,float): return float('%.8g'%v)
    if isinstance(v,list): return [round_values(x) for x in v]
    if isinstance(v,dict): return {k:round_values(x) for k,x in v.items()}
    return v

def comparators(folder,filename,clamp=False):
    rows=[]
    common={}
    for p in sorted((P/'runs'/folder).glob('*/'+filename)):
        d=read(p)
        if d.get('status')!='complete': raise ValueError('Incomplete '+str(p))
        s=d['summary']; i=d['identity']
        row=pick(d,['case','conditional_seven_decision_timing'])
        if 'conditional_seven_decision_timing' in row:
            row['conditional_seven_decision_timing']=pick(row['conditional_seven_decision_timing'],['cases','valid_complete_ADC_schedule'])
        common[d['case']]=pick(i,['configuration','timing','input_pattern_LSB'])
        row.update(source_summary_sha256=sha(p),identity=pick(i,[
            'geometry_widths_um','topology','candidate']))
        row['summary']=pick(s,['decisions','held_source_sign_disagreements','stable_resolution_max_s',
            'minimum_prelaunch_internal_V','minimum_prelaunch_p_q_V','maximum_prelaunch_x_y_V',
            'max_abs_held_input_error_V','max_abs_held_input_prelaunch_error_V',
            'max_abs_reference_input_error_V','max_abs_sampler_only_prelaunch_error_V',
            'max_abs_prelaunch_P_minus_Q_V','max_abs_prelaunch_X_minus_Y_V',
            'max_abs_direct_input_error_V','all_32_ideal_clamp_decisions_correct_by48ps',
            'comparator_mean_power_W','buffer_mean_power_W',
            'compare_clock_mean_power_W','compare_clock_bar_mean_power_W'])
        row['summary']['endpoints']={k:(v['buffered'] if clamp else
            {basis:v[basis]['buffered'] for basis in ('source','held')})
            for k,v in s['endpoints'].items() if k in (('48ps',) if clamp else ('end',))}
        rows.append(row)
    # Exact shared condition objects are referenced by number to avoid repeating
    # the same bench parameters dozens of times in the authorized small export.
    conditions=[]
    for row in rows:
        c=common[row['case']]
        if c not in conditions:conditions.append(c)
        row['conditions_index']=conditions.index(c)
    return {'conditions':conditions,'cases':rows}

def interfaces(folder):
    rows=[]
    for p in sorted((P/'runs'/folder).glob('*/summary.json')):
        d=read(p)
        if d.get('status')!='complete': raise ValueError('Incomplete '+str(p))
        row=pick(d,['case','configuration','timing_s','timing'])
        row['source_summary_sha256']=sha(p)
        row['summary']=pick(d['summary'],['decisions','exploratory_transfer_fit',
            'buffered_source_counts','buffered_held_counts','buffered_source_resolution_max_s',
            'buffered_held_resolution_max_s','source_to_hold_polarity_agrees_count',
            'held_prelaunch_indeterminate_count','held_sign_indeterminate_band_V',
            'secondary_common_mode_range_V','noise_reference_subtraction_is_not_pure_kickback',
            'all64_acquisition_diagnostics']+['max_'+k for k in (
                'master_compare_extra_differential_peak_V','master_compare_extra_common_mode_peak_V',
                'secondary_compare_extra_differential_peak_V','secondary_compare_extra_common_mode_peak_V',
                'reference_secondary_hold_change_peak_V')]+['mean_'+k for k in (
                'buffer_bank_power_W','comparator_power_W','output_inverters_power_W')])
        rows.append(row)
    return rows


def native_summaries():
    out={}
    p=P/'results/native_geometry_r5_summary.json'; d=read(p)
    out['geometry']={'source_summary_sha256':sha(p),'summary':pick(d,[
        'native_CDF_saved_reopened_verified','geometry_count'])}
    out['geometry']['summary']['native']=pick(d['native'],['native_cards_sha256','source_netlist_sha256'])
    p=P/'results/native_geometry_speed_r5.json'; d=read(p)
    out['speed']={'source_summary_sha256':sha(p),'device_cases':len(d['results']),
        'scope':'Full DC/current-gain diagnostics remain in the VM summary and prior MOS evidence; omitted from compact ADC milestone.'}
    p=P/'results/native_capacitor_r5_summary.json'; d=read(p)
    out['capacitor']={'source_summary_sha256':sha(p),'summary':pick(d,[
        'conditions','native_capacitors','requested_geometries_verified','actual_CDF_snapshot_available'])}
    out['capacitor']['summary']['native']=pick(d['native'],['native_cards_sha256','source_netlist_sha256','geometry_verification'])
    fields=['Wfinger','Sfinger','Lfinger','Nfinger','StartMn','StopMn','m','c']
    ac=['frequency_Hz','plus_total_effective_C_F','mutual_effective_C_F','plus_minus_difference_effective_C_F',
        'plus_conductance_S','transfer_real_admittance_S','plus_minus_difference_real_admittance_S',
        'plus_impedance_magnitude_ohm','plus_admittance_phase_degrees']
    out['capacitor']['cases']={key:{'requested_geometry':pick(row['requested_geometry'],fields),
        'saved_CDF_geometry':pick(row.get('saved_CDF_geometry') or {},fields),
        'requested_geometry_matches_saved_CDF':row['requested_geometry_matches_saved_CDF'],
        'AC':[pick(point,ac) for point in row['AC'] if point['frequency_Hz'] in (1e6,56e9)]}
        for key,row in d['cases'].items()}
    out['capacitor']['omitted_AC_points_Hz']=[1e9,10e9]
    return out


def native_cdac():
    p=P/'runs/adc_cdac_native_r5_20261013/cdac_summary.json'; d=read(p)
    if d.get('status')!='complete':raise ValueError('Native CDAC aggregate incomplete')
    result={'source_summary_sha256':sha(p),'conditions':d['conditions'],
        'identity':pick(d['identity'],['script_sha256','mos_cards_sha256','capacitor_cards_sha256',
            'unit_key','unit_actual_Nfinger','bridge_key','bridge_actual_Nfinger']),'cases':[],
        'interpretation':'DNL/INL composed from independent bit steps, comparator held reset. No all-code ADC, short acquisition or seven dependent SAR decisions.'}
    linear=['individual_step_V','normalized_sum_weights','ideal_normalized_weights','composed_span_V',
        'endpoint_normalized_LSB_V','adjacent_step_DNL_min_LSB','adjacent_step_DNL_max_LSB',
        'worst_abs_DNL_LSB','worst_transition','nonpositive_composed_code_steps',
        'endpoint_INL_max_abs_LSB','carry_DNL_LSB']
    steps=['bit_LSB_index','step_differential_V','sample_hold_differential_drift_peak_V',
        'last_50ps_differential_peak_to_peak_V','top_common_mode_at_capture_V','top_common_mode_final_V',
        'bottom_final_V','bottom_settling_to_50mV_over_256_s','top_settling_to_half_100mVpp_input_LSB_s',
        'top_settling_to_half_composed_endpoint_LSB_s','low_node_plus_final_V','low_node_minus_final_V']
    for case in d['cases']:
        if case.get('status')!='complete':raise ValueError('Incomplete native CDAC topology')
        m=case['metrics']; row=pick(case,['topology','deck_sha256','raw_sha256',
            'native_unit_capacitors_per_side','native_bridge_capacitors_per_side'])
        row.update(composed_linearity=pick(m['composed_linearity'],linear),
            bit_steps=[pick(x,steps) for x in m['bit_steps']],bottom_settling_max_s=m['bottom_settling_max_s'])
        result['cases'].append(row)
    if {x['topology'] for x in result['cases']}!={'binary','split'}:raise ValueError('Require two completed CDAC topologies')
    return result


def frozen_training():
    root=P/'runs/adc_backend_pam4_r5_20261013/r5_late1'
    p=root/'training/run_summary.json'; d=read(p)
    if d.get('status')!='training_complete_frozen':raise ValueError('Training not frozen complete')
    frozen_hash=sha(root/'frozen.json') # Hash only: never parse detector coefficients.
    if frozen_hash!=d['frozen_file_sha256']:raise ValueError('Frozen training file changed')
    protocol=read(root/'protocol.json')['protocol']
    result={'study':'r5_late1','status':d['status'],'source_summary_sha256':sha(p),
        'frozen_file_sha256':frozen_hash,'protocol_sha256':sha(root/'protocol.json'),
        'deck_sha256':d['deck_sha256'],'raw_transient_sha256':d['raw_transient_sha256'],
        'protocol':pick(protocol,['variant','comparator','training_data_seed','validation_data_seed',
            'training_noise_seed','training_input_symbols','validation_input_symbols','phase_UI',
            'loss_dB_at_56GHz','conditions','complete_ADC_verified']),
        'holdout_results_included':False,'holdout_files_opened':False,'selections':{},
        'interpretation':'Training-only selection metrics; no validation/receiver BER conclusion.'}
    score=['selection_symbol_errors','selection_symbol_count','selection_SER','selection_gray_BER',
        'selection_MSE_target_units_squared','fit_input_clipped_count','selection_input_clipped_count',
        'fullscale_differential_Vpp','split']
    for point in ('primary','secondary'):
        s=d['selection_summary'][point]
        result['selections'][point]=dict(integer_symbol_lag=s['integer_symbol_lag'],
            ADC_fullscale_differential_Vpp=s['ADC_fullscale_differential_Vpp'],
            raw_FFE_score=pick(s['raw_FFE_score'],score),ADC_score=pick(s['ADC_score'],score))
    return result


def training_diagnostic():
    p=P/'runs/adc_backend_pam4_r5_20261013/r5_late1/training_diagnostic_v1.json'; d=read(p)
    if d.get('frozen_file_unchanged') is not True:raise ValueError('Training diagnostic changed frozen design')
    s=d['statistics']; statkeys=['count','mean','rms','centered_rms','minimum','maximum']
    globalkeys=['count','gain_VV','offset_V','residual_rms_V','residual_peak_V','primary_Vppd','secondary_Vppd']
    physicalkeys=['secondary_common_mode_V','secondary_closing_edge_change_V',
                  'secondary_hold_change_first8ps_V','secondary_hold_change_120ps_V']
    bufferkeys=['buffer_change_final8ps_V','secondary_acquisition_lag_before_close_V',
                'buffer_common_mode_before_close_V','buffer_positive_rail_headroom_before_close_V',
                'buffer_negative_rail_headroom_before_close_V']
    out=pick(d,['complete_ADC_verified','training_input_count','training_data_seed','training_noise_seed',
                'frozen_file_sha256','raw_training_sha256','script_sha256','frozen_file_unchanged'])
    out.update(source_summary_sha256=sha(p),global_aperture_transfer=pick(s['global_aperture_transfer'],globalkeys),
        physical_summary={k:pick(s['physical_summary'][k],statkeys) for k in physicalkeys if k in s['physical_summary']},
        buffer0_and7_summary={k:pick(s['buffer0_and7_summary'][k],statkeys) for k in bufferkeys if k in s['buffer0_and7_summary']},
        memory_fit_residuals={},training_DSP_selection={})
    allowedfits=['same_aperture','previous_bank_sample','bank_and_branch_history','nearby_plus_bank_branch',
                 '17tap_primary_history','17tap_plus64UI']
    for name,row in pick(d['physical_transfer_memory']['models'],allowedfits).items():
        out['memory_fit_residuals'][name]=pick(row,['training_rows','residual_rms_V','residual_peak_V'])
    for representation,row in pick(d['secondary_training_FFE_history']['results'],['raw','ideal7bit']).items():
        out['training_DSP_selection'][representation]={name:pick(values['training_selection_metrics'],[
            'symbol_errors','sample_count','prediction_EVM_RMS_percent_of_target_RMS'])
            for name,values in pick(row,['17tap','17tap_plus64UI','17tap_plus_delayed17']).items()}
    out['scope']='Training-only diagnostic. Residual combines noise/nonlinearity/memory; no holdout, lane calibration or isolated thermal-noise claim. Coefficients and lane rows excluded.'
    return out


def native_cdac_acquisition():
    p=P/'runs/adc_cdac_acquisition_r6_20261013/acquisition_summary.json'
    if not p.exists():return None
    d=read(p)
    if d.get('status')!='complete':return None
    out={'source_summary_sha256':sha(p),'cases':[],
         'scope':'Two native CDAC acquisition screens; no comparator decision or ADC conversion proof.'}
    for case in d['cases']:
        if case.get('status')!='complete':raise ValueError('Partly complete CDAC acquisition aggregate')
        s=case['summary']; row=pick(case,['case','raw_sha256'])
        row['summary']=pick(s,['branch0_captures','native_CDAC_source_sign_agrees',
                              'reference_10f_source_sign_agrees','DUT_bank_mean_power_W'])
        row['summary']['errors']={k:pick(v,['rms_V','peak_abs_V']) for k,v in pick(s['errors'],[
            'DUT_lag_before_close_V','DUT_minus_reference_after_close_V','native_CDAC_held_drift_peak_V']).items()}
        out['cases'].append(row)
    return out


def compact_repeated_hashes(value):
    counts=collections.Counter()
    def scan(x):
        if isinstance(x,str) and re.match(r'^[0-9a-f]{64}$',x):counts[x]+=1
        elif isinstance(x,dict):
            for v in x.values():scan(v)
        elif isinstance(x,list):
            for v in x:scan(v)
    scan(value)
    pool=sorted(k for k,v in counts.items() if v>1); indices={key:i for i,key in enumerate(pool)}
    def replace(x):
        if isinstance(x,str) and x in indices:return {'sha256_ref':indices[x]}
        if isinstance(x,dict):return {k:replace(v) for k,v in x.items()}
        if isinstance(x,list):return [replace(v) for v in x]
        return x
    result=replace(value)
    result['repeated_sha256_values']=pool
    result['hash_reference_format']='{sha256_ref:N} refers to repeated_sha256_values[N]; unique hashes remain literal.'
    return result


def pack_tables(value):
    """Lossless readable tables: shared JSON-pointer columns plus value rows."""
    schemas=[]
    absent={'absent_in_row':True}
    def table(x):return isinstance(x,dict) and set(x)=={'table_schema','rows'}
    def flatten(x,prefix='',out=None):
        if out is None:out={}
        if isinstance(x,dict) and x and not table(x):
            for key,child in x.items():
                escaped=key.replace('~','~0').replace('/','~1')
                flatten(child,prefix+'/'+escaped,out)
        else:out[prefix]=x
        return out
    def visit(x):
        if isinstance(x,dict):return {k:visit(v) for k,v in x.items()}
        if not isinstance(x,list):return x
        rows=[visit(v) for v in x]
        if len(rows)<2 or not all(isinstance(v,dict) for v in rows):return rows
        flat=[flatten(v) for v in rows]
        columns=sorted(set(key for row in flat for key in row))
        if columns not in schemas:schemas.append(columns)
        return {'table_schema':schemas.index(columns),
                'rows':[[row.get(key,absent) for key in columns] for row in flat]}
    result=visit(value)
    result['table_schemas']=schemas
    result['table_format']='Objects {table_schema:N,rows:[...]} use JSON-pointer columns table_schemas[N]. {absent_in_row:true} denotes missing field; null is preserved. Nested tables use the same schema pool. All selected evidence is retained.'
    return result


def unpack_tables(value):
    """Round-trip verification helper; not used to read any VM artifact."""
    schemas=value['table_schemas']
    def visit(x):
        if isinstance(x,list):return [visit(v) for v in x]
        if not isinstance(x,dict):return x
        if set(x)=={'table_schema','rows'}:
            columns=schemas[x['table_schema']]; result=[]
            for row in x['rows']:
                obj={}
                for pointer,child in zip(columns,row):
                    if child=={'absent_in_row':True}:continue
                    parts=[k.replace('~1','/').replace('~0','~') for k in pointer.split('/')[1:]]
                    if not parts:
                        obj=visit(child);continue
                    at=obj
                    for key in parts[:-1]:at=at.setdefault(key,{})
                    at[parts[-1]]=visit(child)
                result.append(obj)
            return result
        return {k:visit(v) for k,v in x.items()}
    return visit({k:v for k,v in value.items() if k not in ('table_schemas','table_format')})


def validate_export(value):
    forbidden={'parameters','cards','model','models','coefficients','frozen_detectors',
               'raw_waveforms','raw_values','netlist','wave','waveforms'}
    if isinstance(value,dict):
        if forbidden.intersection(value):raise ValueError('Forbidden model/coefficient/raw field in export')
        for x in value.values():validate_export(x)
    elif isinstance(value,list):
        for x in value:validate_export(x)
    elif isinstance(value,float) and not math.isfinite(value):raise ValueError('Nonfinite export number')

def main():
    result=dict(schema_version=3,created_UTC=datetime.datetime.utcnow().isoformat()+'Z',
        export_kind='completed_blocks_and_frozen_training_only',holdout_files_opened=False,
        complete_ADC_verified=False,physical_SAR_conversion_verified=False,
        export_precision='8 significant digits; full precision originals and all waves remain VM-side.',
        compact_evidence_note='Every case retains its outcome and source-summary SHA256. Per-case deck/raw/script hashes, intermediate comparator checkpoints, MOS DC/speed rows and intermediate capacitor frequencies remain in the hash-bound full VM summaries. Capacitor1MHz/56GHz points retained; CDAC raw hashes retained.',
        scope_limits=[
            'TT25C0.9V nominal schematic simulations, native callback-derived MOS parasitics; no layout/PVT/mismatch proof.',
            '29ps fast,120ps control,short-reset and ideal-clamp comparator screens are distinct fixtures, not seven-bit conversions.',
            'Ideal clamps suppress real input loading/noise/kickback; they diagnose internal reset only.',
            'Block source errors include acquisition memory; held-sign comparison separates acquisition from latch decision.',
            'Interface transfer-fit residual is not sampled noise or ENOB; short noise records are not BER estimates.',
            'Frozen AFE AC/noise includes64 reset comparators. Clocked PAM4, when present, also holds comparators reset.',
            'PAM4 quantizer/17tapFFE are numerical; this export contains training only and never reads holdout files.',
            'Native CDAC charge steps use independent episodes with comparator reset; no dependent SAR conversion or controller.',
            'Reported powers exclude actual clock/bias/reference/CDAC/control/DSP generation.',
            'Device unity-current-gain diagnostic is model extrapolation, not foundry-qualified intrinsic fT or validated RF bandwidth.'
        ])
    result['strongarm']=comparators('adc_comparator_r5_20261013','comparator_r5_summary.json')
    result['doubletail']=comparators('adc_doubletail_r5_20261013','doubletail_r5_summary.json')
    result['burst']=comparators('adc_comparator_burst_r5_20261013','comparator_burst_r5_summary.json')
    result['ideal_clamp']=comparators('adc_reset_clamp_r5_20261013','reset_clamp_r5_summary.json',True)
    result['isolation']=interfaces('adc_isolation_r5_20261013')
    result['acquisition']=interfaces('adc_acquisition_r5_20261013')
    result['frontend_load']=[]
    for p in sorted((P/'runs/adc_frontend_load_r5_20261013').glob('*/summary.json')):
        d=read(p); m=d['metrics']
        if d.get('status')!='complete':raise ValueError('Incomplete frontend load summary')
        result['frontend_load'].append(dict(case=d['case'],source_summary_sha256=sha(p),
            configuration=d['interface_configuration'],
            DC_power=m['DC_power'],noise=m['noise'],
            primary_H56GHz_change_dB=m['primary_H56GHz_change_vs_historical_r3_bare_dB'],
            primary_transfer=m['transfer']['primary_track_lane0']))
    result['native']=native_summaries()
    result['native_CDAC']=native_cdac()
    result['frozen_training']=frozen_training()
    result['training_diagnostic']=training_diagnostic()
    extra_acquisition=native_cdac_acquisition()
    if extra_acquisition is not None:result['r6_native_CDAC_acquisition']=extra_acquisition
    result['protected_hashes']={
        'original_native_cards':sha(P/'configs/native_device_cards.json'),
        'frozen_r3':sha(P/'configs/pam4_optimization_frozen.json'),
        'native_geometry_r5':sha(P/'configs/native_geometry_cards_r5.json'),
        'PDK_model':sha(Path('<PDK_ROOT>/models/spectre/pdk_model.scs'))}
    assert result['protected_hashes']['original_native_cards']=='8d05bd62f3e668c64569459e90373024ca76998f510ec5d2b7a23cd3f5749b9a'
    assert result['protected_hashes']['frozen_r3']=='2eef7e17f3e51248f82d8f2ff7b643905f2e906c040ffb18b4e8d24a3f7f0309'
    assert result['protected_hashes']['PDK_model']=='002300afbc872cca7c0bab744740eb74ff2cc71e770832c6e6d97c447dbfff78'
    result['case_counts']={k:len(result[k]['cases']) for k in ['strongarm','doubletail','burst','ideal_clamp']}
    result['case_counts'].update({k:len(result[k]) for k in ['isolation','acquisition','frontend_load']})
    result['case_counts']['native_CDAC']=len(result['native_CDAC']['cases'])
    expected=dict(strongarm=19,doubletail=5,burst=6,ideal_clamp=4,isolation=7,acquisition=6,frontend_load=3,native_CDAC=2)
    if result['case_counts']!=expected:raise ValueError('Completed milestone counts differ: '+json.dumps(result['case_counts']))
    result=round_values(result)
    validate_export(result)
    encode=lambda value:(json.dumps(value,separators=(',',':'),allow_nan=False)+'\n').encode('utf-8')
    encoded=encode(result)
    if len(encoded)>65000:
        result=compact_repeated_hashes(result)
        encoded=encode(result)
    if len(encoded)>65000:
        before=result
        result=pack_tables(result)
        if unpack_tables(result)!=before:raise ValueError('Table compaction changed exported evidence')
        encoded=encode(result)
    if len(encoded)>70*1024: raise ValueError('Export exceeds approved approximate70KiB: '+str(len(encoded)))
    validate_export(result)
    out=P/'results/Project6_ADC_r5_block_summary.json'
    if out.exists(): raise ValueError('Refuse to replace existing milestone export')
    out.write_bytes(encoded)
    print(json.dumps({'bytes':len(encoded),'sha256':sha(out),'case_counts':result['case_counts'],
                      'holdout_files_opened':False,'output':str(out)}))


def self_test():
    value={'a':'0'*64,'b':['0'*64,.123456789]}
    compact=compact_repeated_hashes(value)
    assert compact['a']==compact['b'][0]=={'sha256_ref':0}
    assert compact['repeated_sha256_values'][0]=='0'*64
    validate_export(compact)
    try:validate_export({'nested':{'parameters':'forbidden'}})
    except ValueError:pass
    else:raise AssertionError('Forbidden model field accepted')
    assert round_values(.123456789)==.12345679
    payload={'cases':[{'name':'a','x':None,'empty':{},'a/b':{'~c':3},
        'nested':[{'mean':1,'rms':2},{'mean':2,'rms':3}]},
        {'name':'b','empty':{},'a/b':{'~c':4},
        'nested':[{'mean':3,'rms':4},{'mean':4,'rms':5}]}]}
    assert unpack_tables(pack_tables(payload))==payload
    assert len(json.dumps(pack_tables({'cases':[{'long_metric_name_for_capacitance':i,
        'long_metric_name_for_acquisition':i+1} for i in range(100)]})))<len(json.dumps(
        {'cases':[{'long_metric_name_for_capacitance':i,'long_metric_name_for_acquisition':i+1} for i in range(100)]}))
    print(json.dumps({'self_test':'passed','VM_files_read':False,'holdout_files_opened':False}))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--self-test',action='store_true')
    args=p.parse_args()
    self_test() if args.self_test else main()
