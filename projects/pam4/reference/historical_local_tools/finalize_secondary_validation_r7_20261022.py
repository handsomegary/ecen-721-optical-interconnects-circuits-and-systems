"""VM-only independent rescore of the completed four-case frozen R7 holdout."""
import json
import subprocess
import control_secondary_validation_r7_20261022 as c

REMOTE = c.PRELUDE + r'''
import importlib.util,math
script=P/'scripts/secondary_cap_validation_r7_20261022.py'
assert sha(script)=='01eb4e152835f3ba4e7779bc63a5a3a081e543d26247c046e7b25294cec02fd0'
spec=importlib.util.spec_from_file_location('r7_independent_final_check',str(script))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
training,helper,runner,frozen,backend,ffe,metrics,psf=m.load_verified()
state=json.loads((R/'status.json').read_text());protocol=json.loads((R/'protocol.json').read_text())
assert state['status']=='complete' and state['current_case'] is None
assert len(state['completed_cases'])==state['simulations_started']==4
assert sha(R/'protocol.json')=='2f5a79e84e7deb0c083641effc204b2263c3e70e35c746ef7596edbd7a0ef86f'
assert protocol['data_seed']==2026102301 and protocol['noise_seed']==251
assert protocol['score_input_symbols']==2048 and protocol['score_complete_FFE_windows']==2032
assert protocol['score_target_indices']==[256,2303] and protocol['score_FFE_center_indices']==[264,2295]
assert protocol['fixed_lags']=={'primary':1,'secondary':3}
assert protocol['fixed_quantizer_fullscale_Vpp']=={'primary':.100,'secondary':.075}
assert protocol['validation_fitting_performed'] is False
assert [x['name'] for x in state['completed_cases']]==[x['name'] for x in m.case_specs()]
assert not any((x.get('cwd') or '').startswith(str(P)+'/') for x in actual())
launch=json.loads((P/'runs/secondary_cap_validation_r7_20261022_dispatch/launch_receipt.json').read_text())
boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
assert boot==launch['boot_id']
live=helper.process_record(launch['runner']['pid'])
assert not (live and live['start_ticks']==launch['runner']['start_ticks'])
m.assert_unchanged(protocol,state)
symbols=json.loads((R/'symbols.json').read_text())
assert len(symbols)==2432 and m.canonical(symbols)==protocol['symbol_sequence_sha256']
labels=symbols[256:2304];targets=labels[8:-8]
assert len(targets)==2032
scores={};arrays={};receipts=[]
for item,case in zip(state['completed_cases'],m.case_specs()):
 d=R/case['name'];s=json.loads((d/'summary.json').read_text());p=json.loads((d/'prepared.json').read_text())
 outcome=json.loads((d/'run_status.json').read_text())
 assert sha(d/'summary.json')==item['summary_sha256']
 assert outcome==s['run_status'] and outcome['exit_code']==0 and 'SPECTRE-18' not in outcome['issue_codes']
 assert s['status']=='validation_complete' and s['independent_holdout'] and not s['training_only']
 assert s['frozen_sha256']==m.FROZEN_SHA and s['frozen_unchanged']
 assert s['validation_fitting_performed'] is False and s['noise_fitting_performed'] is False and s['new_fit_performed'] is False
 assert s['validation_fit_input_count']==0 and s['previous_training_fit_input_count']==256
 assert s['score_input_count']==2048 and s['FFE_score_count']==2032
 assert s['data_seed']==2026102301 and s['noise_seed']==case['noise_seed'] and s['case']==case
 assert s['protocol_sha256']==state['protocol_sha256']
 assert sha(d/'prepared.json')==state['prepared_sha256'][case['name']]
 assert sha(d/'bench.scs')==p['deck_sha256']==s['deck_sha256']
 audit=p['hardware_only_change_audit']
 assert audit['changed_instance_count']==(0 if case['candidate']=='baseline_r5' else 384)
 assert audit['clock_specifications_unchanged'] and audit['pulse_sources_unchanged']==144
 detector_path=R/(case['candidate']+'_detectors.json');det=json.loads(detector_path.read_text())
 assert sha(detector_path)==state['detector_sha256'][case['candidate']]==s['detector_file_sha256']
 assert detector_path.read_bytes()==(P/protocol['training_provenance']['detectors'][case['candidate']]['source_path']).read_bytes()
 m.validate_detector(det,case['candidate'])
 psf.MAX_FILE_BYTES=512*1024*1024
 raw=psf.parse_file(backend.a._raw_file(d));assert raw.sha256==s['raw_transient_sha256']
 records,clock_audit=backend.extract_records(raw,p['clock_specification'])
 branches={};case_arrays={};all_rows=[]
 for point,lag in (('primary',1),('secondary',3)):
  by_label={row[0]-lag:row for row in records[point]}
  assert len(by_label)==len(records[point])
  rows=[by_label[index] for index in range(256,2304)];all_rows.extend(rows)
  samples=[row[1] for row in rows]
  assert len(samples)==2048 and all(math.isfinite(value) for value in samples)
  scale=.100 if point=='primary' else .075
  quantized,clipped=metrics.quantize_symmetric(samples,scale,7)
  stored=s['branches'][point]
  assert stored['score_input_count']==2048 and stored['FFE_score_count']==2032
  assert stored['fitting_performed'] is False and stored['integer_lag']==lag and stored['fullscale_Vpp']==scale
  assert stored['score_ADC_clipped_count']==clipped
  result={};err_vectors={};pred_vectors={}
  for mode,values in (('raw_FFE',samples),('ADC_FFE',quantized)):
   predictions=ffe.predict_window(values,det['branches'][point][mode])
   assert len(predictions)==2032 and all(math.isfinite(value) for value in predictions)
   measured=ffe.prediction_metrics(predictions,targets)
   mse=math.fsum((value-(2*target-3))**2 for value,target in zip(predictions,targets))/2032
   errors=[sum(value>=threshold for threshold in (-2.,0.,2.))!=target for value,target in zip(predictions,targets)]
   assert sum(errors)==measured['symbol_errors']==stored[mode]['symbol_errors']
   assert measured['sample_count']==stored[mode]['sample_count']==2032
   assert math.isclose(mse,stored[mode]['MSE_target_units_squared'],rel_tol=1e-12,abs_tol=1e-14)
   result[mode]=dict(errors=sum(errors),symbols=2032,SER=sum(errors)/2032.,MSE_target_units_squared=mse)
   err_vectors[mode]=errors;pred_vectors[mode]=predictions
  result.update(clipped_inputs=clipped,input_count=2048,held_Vpp=max(samples)-min(samples),
   held_centered_RMS_V=stored['held_centered_RMS_V'],fullscale_Vpp=scale,
   normalized_ADC_FFE_tap_L2=det['branches'][point]['ADC_FFE']['normalized_input_tap_L2'],
   equivalent_per_V_ADC_FFE_tap_L2=det['branches'][point]['ADC_FFE']['equivalent_per_V_tap_L2'])
  branches[point]=result;case_arrays[point]=dict(held=samples,predictions=pred_vectors,errors=err_vectors)
 power=backend.power(raw,min(row[2] for row in all_rows),max(row[2] for row in all_rows))
 assert math.isclose(power['total_measured_VDD_W'],s['modeled_power']['total_measured_VDD_W'],rel_tol=1e-12)
 scores[case['name']]=dict(candidate=case['candidate'],kind=case['kind'],branches=branches,
  measured_VDD_mW=power['total_measured_VDD_W']*1e3,power_scope=power['scope'],seconds=outcome['seconds'])
 arrays[case['name']]=case_arrays
 receipts.append(dict(name=case['name'],exit_code=0,summary_sha256=sha(d/'summary.json'),
  deck_sha256=sha(d/'bench.scs'),raw_sha256=raw.sha256,detector_sha256=sha(detector_path),
  validation_fitting_performed=False,independent_counts_MSE_power_recomputed=True))
 del raw,records

comparisons={}
for kind in ('noiseless','noise'):
 comparisons[kind]={}
 for point in ('primary','secondary'):
  comparisons[kind][point]={}
  for mode in ('raw_FFE','ADC_FFE'):
   base=arrays[kind+'_baseline_r5'][point]['errors'][mode]
   cand=arrays[kind+'_secondary_c25_w2'][point]['errors'][mode]
   comparisons[kind][point][mode]=dict(
    baseline_errors=sum(base),candidate_errors=sum(cand),symbols=2032,
    error_reduction_count=sum(base)-sum(cand),absolute_SER_change=(sum(cand)-sum(base))/2032.,
    relative_error_reduction=(sum(base)-sum(cand))/sum(base) if sum(base) else None,
    both_wrong=sum(a and b for a,b in zip(base,cand)),
    baseline_only_wrong=sum(a and not b for a,b in zip(base,cand)),
    candidate_only_wrong=sum(b and not a for a,b in zip(base,cand)),
    both_correct=sum(not a and not b for a,b in zip(base,cand)))
paired={}
for candidate in m.CANDIDATES:
 paired[candidate]={}
 for point in ('primary','secondary'):
  n=arrays['noiseless_'+candidate][point];q=arrays['noise_'+candidate][point]
  rms=lambda a,b:math.sqrt(math.fsum((x-y)**2 for x,y in zip(a,b))/len(a))
  paired[candidate][point]=dict(noise_minus_noiseless_held_RMS_V=rms(q['held'],n['held']),
   noise_minus_noiseless_ADC_FFE_RMS_target_units=rms(q['predictions']['ADC_FFE'],n['predictions']['ADC_FFE']))
m.assert_unchanged(protocol,state)
delivery=dict(status='verified_four_case_independent_validation_complete',created_utc=now(),
 finished_utc=state['updated_utc'],root=str(R),boot_id=boot,original_runner_active=False,owned_actual_simulators=0,
 script_sha256=sha(script),protocol_sha256=sha(R/'protocol.json'),status_sha256=sha(R/'status.json'),
 frozen_sha256=sha(original.FROZEN_PATH),detector_sha256=state['detector_sha256'],
 data_seed=2026102301,noise_seed=251,generated_symbols=2432,score_inputs=2048,FFE_outputs_per_branch=2032,
 validation_fitting_performed=False,all_four_exit0=True,independent_metrics_recomputed=True,
 independent_fresh_data=True,complete_ADC_verified=False,case_hashes=receipts,
 results=scores,same_round_comparison=comparisons,paired_noise_minus_noiseless=paired,
 limitations=[
 'One data sequence and one noise seed; overlapping FFE windows are correlated, not iid BER certification.',
 'Shared declared noise seed across hardware does not guarantee identical noise realization or independent replicas.',
 'Each candidate retains its own fixed training detector; comparison is the full candidate chain, not isolated component noise.',
 'Noise-minus-noiseless differences include noise-induced dynamics and nonlinear changes, not pure device-noise decomposition.',
 'Measured VDD excludes clock and bias generation, CDAC/reference/control and digital FFE power.',
 'Numerical7bit quantization and FFE, reset comparators and ideal clocks do not establish complete physical7bit112GS/s ADC performance.'],
 next='Deliver this fixed independent comparison and delete monitor. No further simulations, candidates, fitting or re-use for validation after tuning.')
path=P/'notes/secondary_validation_r7_delivery_20261022.json'
if path.exists():
 previous=json.loads(path.read_text());assert previous['status_sha256']==delivery['status_sha256'];delivery=previous
else:original.atomic_json(path,delivery)
print(json.dumps(delivery))
'''
cmd=['C:/Windows/System32/OpenSSH/ssh.exe','-i',str(c.LOCAL/'work/ssh/vm_pdk_access_ed25519'),
 '-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes',
 '-o','HostKeyAlias=192.0.2.1','user@192.0.2.1','python3 -']
r=subprocess.run(cmd,input=REMOTE,text=True,encoding='utf-8',capture_output=True,timeout=150)
if r.returncode:raise RuntimeError(r.stderr or r.stdout)
delivery=json.loads(r.stdout)
(c.LOCAL/'work/secondary_validation_r7_delivery_20261022.json').write_text(json.dumps(delivery,indent=2)+'\n',encoding='utf-8')
compact={name:dict(secondary=value['branches']['secondary'],primary=value['branches']['primary'],
                 measured_VDD_mW=value['measured_VDD_mW'],seconds=value['seconds'])
         for name,value in delivery['results'].items()}
print(json.dumps(dict(status=delivery['status'],finished_utc=delivery['finished_utc'],results=compact,
                     comparison=delivery['same_round_comparison']['noise']),indent=2))
