"""VM-only reanalysis and compact numerical audit of six completed training runs."""
import json,subprocess
import control_secondary_r7_20261022 as c
REMOTE=c.PRELUDE+r'''
import importlib.util,math
script=P/'scripts/secondary_cap_training_r7_20261022.py'
assert sha(script)=='a83a0795f0cfb341889649f9578cfd82dbf7ecf380d2cea799938dd84ce1bbac'
spec=importlib.util.spec_from_file_location('r7_final_check',str(script));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
helper,runner,frozen,backend,ffe,metrics,psf=m.load_verified()
state=json.loads((R/'status.json').read_text());protocol=json.loads((R/'protocol.json').read_text())
assert state['status']=='complete' and state['current_case'] is None and len(state['completed_cases'])==6
assert sha(R/'protocol.json')=='52589424ae376221ffb488b3e1a92d5ca1e411768eed96825defa8f4cd3af1f0'
assert protocol['data_seed']==2026102202 and protocol['noise_seed']==223
assert [x['name'] for x in state['completed_cases']]==[x['name'] for x in m.case_specs()]
assert not any((x.get('cwd') or '').startswith(str(P)+'/') for x in actual())
m.assert_unchanged(protocol)
symbols=m.symbols_new();assert m.canonical(symbols)==protocol['symbol_sequence_sha256']
def stats(xs):
 mu=math.fsum(xs)/len(xs)
 return dict(count=len(xs),mean=mu,rms=math.sqrt(math.fsum(x*x for x in xs)/len(xs)),centered_rms=math.sqrt(math.fsum((x-mu)**2 for x in xs)/len(xs)),peak_abs=max(abs(x) for x in xs))
def corr(xs,ys):
 mx=math.fsum(xs)/len(xs);my=math.fsum(ys)/len(ys)
 a=[x-mx for x in xs];b=[y-my for y in ys]
 den=math.sqrt(math.fsum(x*x for x in a)*math.fsum(y*y for y in b))
 return math.fsum(x*y for x,y in zip(a,b))/den if den else None
scores={};pair_arrays={};case_hashes=[]
for item,case in zip(state['completed_cases'],m.case_specs()):
 d=R/case['name'];s=json.loads((d/'summary.json').read_text());p=json.loads((d/'prepared.json').read_text())
 assert sha(d/'summary.json')==item['summary_sha256']
 assert s['status']=='analysis_complete' and s['run_status']['exit_code']==0 and 'SPECTRE-18' not in s['run_status']['issue_codes']
 assert s['frozen_sha256']==m.FROZEN_SHA and s['frozen_unchanged'] and s['protocol_sha256']==state['protocol_sha256']
 assert s['training_only'] and not s['independent_holdout'] and not s['noise_fitting_performed']
 assert s['new_fit_performed']==(case['kind']=='noiseless') and s['data_seed']==m.DATA_SEED and s['noise_seed']==case['noise_seed']
 assert s['fit_input_count']==256 and s['score_input_count']==240 and s['FFE_score_count']==224
 assert sha(d/'prepared.json')==state['prepared_sha256'][case['name']]
 assert sha(d/'bench.scs')==p['deck_sha256']==s['deck_sha256']
 detector_path=R/(case['candidate']+'_detectors.json');det=json.loads(detector_path.read_text())
 assert sha(detector_path)==state['detector_sha256'][case['candidate']]==s['detector_file_sha256']
 assert det['protocol_sha256']==state['protocol_sha256']
 psf.MAX_FILE_BYTES=512*1024*1024;raw=psf.parse_file(backend.a._raw_file(d))
 assert raw.sha256==s['raw_transient_sha256']
 records,audit=backend.extract_records(raw,p['clock_specification'])
 branches={};arrays={}
 for point in ('primary','secondary'):
  samples,labels,rows=m.align_fixed(records[point],symbols,m.LAGS[point])
  check=m.evaluate_detector(samples,labels,det['branches'][point],ffe,metrics)
  for mode in ('raw_FFE','ADC_FFE'):
   for key in ('symbol_errors','sample_count','MSE_target_units_squared'):
    assert check[mode][key]==s['branches'][point][mode][key]
  score=samples[272:];target=labels[280:-8];q,clipped=metrics.quantize_symmetric(score,m.RANGES[point],7)
  pred=ffe.predict_window(q,det['branches'][point]['ADC_FFE'])
  assert len(pred)==len(target)==224
  branches[point]=dict(raw_FFE_errors=check['raw_FFE']['symbol_errors'],ADC_FFE_errors=check['ADC_FFE']['symbol_errors'],
   ADC_FFE_SER=check['ADC_FFE']['SER'],raw_FFE_MSE=check['raw_FFE']['MSE_target_units_squared'],ADC_FFE_MSE=check['ADC_FFE']['MSE_target_units_squared'],
   symbols=224,held_Vpp=max(score)-min(score),held_centered_RMS_V=check['held_centered_RMS_V'],score_clipped=clipped,
   first256_clipped=check['first256_ADC_clipped_count'],fullscale_Vpp=m.RANGES[point],
   normalized_tap_L2=det['branches'][point]['ADC_FFE']['normalized_input_tap_L2'],
   equivalent_per_V_tap_L2=det['branches'][point]['ADC_FFE']['equivalent_per_V_tap_L2'])
  arrays[point]=dict(held=score,pred=pred,labels=labels[272:])
 # Physical clock-close diagnostics use matched native saved nodes, not FFE labels.
 t=raw.values[raw.sweep_names[0]];v=raw.values
 get=lambda node,when:backend.a.interpolate(t,v[node],when)
 physical={key:[] for key in ('secondary_closing_edge_change_V','secondary_acquisition_lag_before_close_V','buffer_change_final8ps_V')}
 for row in records['secondary']:
  if not 528<=row[0]-3<768:continue
  bank=row[4];master=p['clock_specification']['primary_clocks'][bank]
  cycle=int(round((row[3]-master['first_fall_midpoint_s'])/master['period']));branch=cycle%8
  close=row[2]-1.5e-12;before=close-.6e-12;after=close+.6e-12
  h='B%d_h%d'%(bank,branch)
  hd=lambda when:get(h+'p',when)-get(h+'m',when)
  physical['secondary_closing_edge_change_V'].append(hd(after)-hd(before))
  if bank in (0,7):
   f='B%d_f'%bank;bd=lambda when:get(f+'p',when)-get(f+'m',when)
   physical['secondary_acquisition_lag_before_close_V'].append(hd(before)-bd(before))
   physical['buffer_change_final8ps_V'].append(bd(before)-bd(before-8e-12))
 scores[case['name']]=dict(candidate=case['candidate'],kind=case['kind'],branches=branches,
  measured_VDD_W=s['modeled_power']['total_measured_VDD_W'],buffer_secondary_W=s['modeled_power']['all8_buffer_secondary_banks_W'],
  power_scope=s['modeled_power']['scope'],physical_training_stats={k:stats(xs) for k,xs in physical.items()},
  detector_sha256=sha(detector_path),seconds=s['run_status']['seconds'])
 pair_arrays[case['name']]=arrays
 case_hashes.append(dict(name=case['name'],summary_sha256=sha(d/'summary.json'),deck_sha256=sha(d/'bench.scs'),raw_transient_sha256=raw.sha256,exit_code=0,independent_metrics_recomputed=True))
 del raw,records
paired={}
for name in m.CANDIDATES:
 a=pair_arrays['noiseless_'+name];b=pair_arrays['noise_'+name];out={};deltas={}
 for point in ('primary','secondary'):
  assert a[point]['labels']==b[point]['labels']
  diff=[y-x for x,y in zip(a[point]['held'],b[point]['held'])]
  pdiff=[y-x for x,y in zip(a[point]['pred'],b[point]['pred'])]
  out[point]=dict(noise_minus_noiseless_held_V=stats(diff),noise_minus_noiseless_ADC_FFE_target_units=stats(pdiff))
  deltas[point]=diff
 out['primary_secondary_delta_correlation_at_same_aligned_symbol_label']=corr(deltas['primary'],deltas['secondary'])
 paired[name]=out
m.assert_unchanged(protocol)
delivery=dict(status='verified_six_case_training_complete',created_utc=now(),finished_utc=state['updated_utc'],root=str(R),
 script_sha256=sha(script),protocol_sha256=sha(R/'protocol.json'),status_sha256=sha(R/'status.json'),frozen_sha256=sha(original.FROZEN_PATH),
 data_seed=m.DATA_SEED,noise_seed=m.NOISE_SEED,fit_inputs=256,fit_FFE_windows=240,internal_guard=16,score_inputs=240,score_FFE_outputs=224,
 candidate_order=list(m.CANDIDATES),candidate_configurations={k:dict(secondary_cap_F=v['secondary_cap_F'],secondary_switch_width_m=v['secondary_switch_width_m']) for k,v in protocol['configurations'].items()},
 all_six_exit0=True,independent_metrics_recomputed=True,noise_fitting_performed=False,training_only=True,independent_holdout=False,complete_ADC_verified=False,
 case_hashes=case_hashes,comparisons=scores,paired_training_diagnostics=paired,
 paired_difference_scope='Noise-minus-noiseless trajectory difference includes noise-induced dynamics/nonlinearity. Same seed across changed hardware is neither identical noise realization nor independent replicate. Correlation pairs same aligned symbol labels, not the exact same sampling aperture across stages. No isolated device noise decomposition.',
 physical_diagnostic_scope='Closing-edge change includes signal dynamics/injection/feedthrough; acquisition and final8ps buffer motion are finite training diagnostics, not pure device noise.',
 tap_L2_scope='White uncorrelated input sample-noise reference only; not measured integrated actual correlated noise.',
 next='Compare only this new training baseline and fixed candidates; no automatic candidate expansion or holdout. Physical ADC still unverified.')
path=P/'notes/secondary_r7_delivery_20261022.json'
if path.exists():
 previous=json.loads(path.read_text());assert previous['status_sha256']==delivery['status_sha256'];delivery=previous
else:original.atomic_json(path,delivery)
print(json.dumps(delivery))
'''
cmd=['C:/Windows/System32/OpenSSH/ssh.exe','-i',str(c.LOCAL/'work/ssh/vm_pdk_access_ed25519'),'-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes','-o','HostKeyAlias=192.0.2.1','user@192.0.2.1','python3 -']
r=subprocess.run(cmd,input=REMOTE,text=True,encoding='utf-8',capture_output=True,timeout=55)
if r.returncode:raise RuntimeError(r.stderr or r.stdout)
v=json.loads(r.stdout)
(c.LOCAL/'work/secondary_r7_delivery_20261022.json').write_text(json.dumps(v,indent=2)+'\n',encoding='utf-8')
compact=[]
for name in v['candidate_order']:
 n=v['comparisons']['noiseless_'+name];q=v['comparisons']['noise_'+name]
 compact.append(dict(candidate=name,secondary_noiseless_errors=n['branches']['secondary']['ADC_FFE_errors'],secondary_noise_errors=q['branches']['secondary']['ADC_FFE_errors'],primary_noise_errors=q['branches']['primary']['ADC_FFE_errors'],secondary_noise_MSE=q['branches']['secondary']['ADC_FFE_MSE'],secondary_noise_Vpp=q['branches']['secondary']['held_Vpp'],noise_VDD_W=q['measured_VDD_W'],noise_physical=q['physical_training_stats'],paired=v['paired_training_diagnostics'][name]))
print(json.dumps(dict(status=v['status'],finished_utc=v['finished_utc'],score_FFE_outputs=224,comparisons=compact),indent=2))
