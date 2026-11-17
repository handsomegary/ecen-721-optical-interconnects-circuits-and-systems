"""VM-only postprocessing of completed frozen results; no simulations or fitting."""
import sys
sys.dont_write_bytecode = True
import hashlib
import json
import gc
from pathlib import Path

P = Path('/path/to/local/cadence-home/Desktop/cadence_projects/project6_28nm')
assert (P/'.codex_project6_owned').is_file()
sys.path.insert(0, str(P/'scripts'))
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
import adc_backend_pam4_r5 as backend
import psf_ascii
import pam4_ffe_diagnostic as ffe
import pam4_metrics as metrics

S = P/'runs/adc_backend_pam4_r5_20261013/r5_late1'
OUT = P/'results/eye_review_20261020'
FROZEN = '4cda4c9ec967f2af4bf4f89eacdd1beae372668877c358cf6aa26092597482eb'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(S/'frozen.json') == FROZEN
frozen = json.loads((S/'frozen.json').read_text())
assert not OUT.exists(), 'Refuse overwrite'
OUT.mkdir()
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.titlesize':13,
                     'axes.labelsize':11,'figure.facecolor':'white','savefig.facecolor':'white'})
eye, axes = plt.subplots(2, 2, figsize=(13.5, 8.2))
dist, dx = plt.subplots(2, 2, figsize=(13.5, 8.2))
psf_ascii.MAX_FILE_BYTES = 512*1024*1024
pi = backend.pi
symbols = backend.validation_symbols()
lo_index = pi.WARMUP + backend.TRAIN_COUNT
hi_index = lo_index + backend.VALID_COUNT
starts = pi.T0 + np.arange(lo_index, hi_index-1)*pi.UI
colors = ['#2563eb','#0f9d8a','#e7a31a','#d74d64']
bins = np.linspace(-8,8,161)
eye_limits = [0.,0.]
receipt = {'purpose':'Derived raster visualizations from existing completed paired validation',
 'new_simulations':False,'validation_fitting_performed':False,'complete_ADC_verified':False,
 'frozen_sha256':FROZEN,'UI_ps':pi.UI*1e12,'saved_spacing_ps':backend.STROBE*1e12,
 'holdout_input_symbols':2048,'eye_windows_per_panel':len(starts),
 'eye_timebase':'Fixed TX period; no phase optimization; lines connect saved samples only',
 'conditions':'112 Gbaud PAM4, synthetic 20 dB channel at 56 GHz, TT 25 C, 0.9 V',
 'pairs':{},'files':{}}

for col,kind in enumerate(('noiseless','noise')):
 d = S/('validation_'+kind)
 summary = json.loads((d/'run_summary.json').read_text())
 assert summary['status']=='validation_complete' and summary['run_status']['exit_code']==0
 assert summary['frozen_file_unchanged'] and not summary['validation_fitting_performed']
 assert summary['validation_input_symbols']==2048 and summary['FFE_complete_windows']==2032
 assert summary['fresh_holdout_seed']==2026101302
 raw = psf_ascii.parse_file(d/'raw/tranResponse.tran.tran')
 assert raw.sha256==summary['raw_transient_sha256']
 times = np.asarray(raw.values[raw.sweep_names[0]])
 assert np.allclose(np.diff(times)[1:-1],backend.STROBE,rtol=1e-4,atol=1e-17)
 cond = 'Noiseless' if kind=='noiseless' else 'Transient noise (seed 173)'
 for row,(plus,minus,title,limit) in enumerate((('X_ip','X_im','After channel',45),
                                             ('X_o_p','X_o_m','Continuous AFE output',65))):
  volts = (np.asarray(raw.values[plus])-np.asarray(raw.values[minus]))*1e3
  holdout_mask=(times>=starts[0]) & (times<=starts[-1]+2*pi.UI)
  eye_limits[row]=max(eye_limits[row],float(np.max(np.abs(volts[holdout_mask]))))
  segments = []
  for start in starts:
   lower,upper = np.searchsorted(times,[start,start+2*pi.UI])
   phase = (times[lower:upper]-start)/pi.UI
   segments.append(np.column_stack((phase,volts[lower:upper])))
  ax=axes[row,col]
  ax.set_facecolor('#0c1425')
  ax.add_collection(LineCollection(segments,colors='#43e7c0',linewidths=.55,alpha=.035,rasterized=True))
  ax.set(xlim=(0,2),ylim=(-limit,limit),xlabel='Time within 2-UI window (UI)',ylabel='Differential voltage (mV)',
         title=title+' | '+cond)
  ax.set_xticks([0,.5,1,1.5,2])
  ax.grid(alpha=.13,color='white')
 records,audit=backend.extract_records(raw,summary['clock_specification'])
 receipt['pairs'][kind]={'summary_sha256':sha(d/'run_summary.json'),'raw_sha256':raw.sha256,'branches':{}}
 for row,point in enumerate(('primary','secondary')):
  choice=frozen['selections'][point]
  samples,labels,unused=pi.aligned_window(records[point],symbols,choice['integer_symbol_lag'],1024,2048)
  samples=samples[1024:];labels=labels[1024:]
  assert len(samples)==2048
  det=choice['frozen_detectors']
  q,clipped=metrics.quantize_symmetric(samples,det['ADC_fullscale_differential_Vpp'],7)
  predicted=np.asarray(ffe.predict_window(q,det['ADC_FFE']))
  target=np.asarray(labels[ffe.HALF:-ffe.HALF])
  score=ffe.prediction_metrics(predicted.tolist(),target.tolist())
  expected=summary['results'][point]['metrics']['ideal7bit_ADC_then_FFE']
  assert len(predicted)==2032 and score['symbol_errors']==expected['symbol_errors']
  assert score['symbol_errors']==({'primary':0,'secondary':2 if kind=='noiseless' else 164}[point])
  assert clipped==0
  assert predicted.min()>=bins[0] and predicted.max()<=bins[-1], 'Histogram range misses values'
  ax=dx[row,col]
  for symbol,color in enumerate(colors):
   ax.hist(predicted[target==symbol],bins=bins,histtype='stepfilled',alpha=.5,color=color,
           label='Target '+str(2*symbol-3))
  for threshold in (-2,0,2):ax.axvline(threshold,color='#334155',ls='--',lw=1)
  ax.set(xlim=(-8,8),xlabel='Frozen FFE output (PAM4 target units)',ylabel='Symbol count per bin',
         title=point.title()+' | '+cond+'\n'+str(score['symbol_errors'])+'/2032 symbol errors')
  ax.grid(axis='y',alpha=.2)
  if row==0 and col==0:ax.legend(ncol=2,fontsize=9)
  receipt['pairs'][kind]['branches'][point]={'symbol_errors':score['symbol_errors'],'scored_symbols':2032}
 del raw,records
 gc.collect()
 print(json.dumps({'event':'plot_data_verified','kind':kind}),flush=True)

for row in range(2):
 limit=np.ceil(eye_limits[row]*1.08/10)*10
 for col in range(2):axes[row,col].set_ylim(-limit,limit)
eye.suptitle('Project 6 | Saved-waveform PAM4 eyes',fontsize=19,fontweight='bold',y=.99)
eye.text(.5,.939,'112 Gbaud | 20 dB channel at 56 GHz | TT, 25 C, 0.9 V | fixed TX timing',ha='center',fontsize=12)
eye.text(.5,.035,'2047 overlapping 2-UI windows per panel from the 2048-symbol holdout. 1 UI = 8.929 ps.',ha='center',fontsize=10)
eye.text(.5,.012,'Saved spacing = 1.116 ps (8 points/UI); line connections are display interpolation. Simulated, not a hardware real-time acquisition.',ha='center',fontsize=9)
eye.tight_layout(rect=[0,.065,1,.92])
dist.suptitle('Project 6 | Frozen sampled-decision distributions',fontsize=19,fontweight='bold',y=.99)
dist.text(.5,.939,'Actual held samples + ideal 7-bit numerical quantizer + frozen 17-tap FFE',ha='center',fontsize=12)
dist.text(.5,.035,'2032 decisions per panel. Dashed lines: fixed thresholds -2 / 0 / +2. No holdout fitting.',ha='center',fontsize=10)
dist.text(.5,.012,'These are sample distributions, not continuous eyes; the complete physical ADC and clock/reference/control system are not verified.',ha='center',fontsize=9)
dist.tight_layout(rect=[0,.065,1,.92])
for fig,name in ((eye,'Project6_r5_paired_eyes.png'),(dist,'Project6_r5_sample_distributions.png')):
 path=OUT/name
 fig.savefig(str(path),dpi=150)
 plt.close(fig)
 receipt['files'][name]={'bytes':path.stat().st_size,'sha256':sha(path)}
assert sha(S/'frozen.json')==FROZEN
(OUT/'visualization_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt))
