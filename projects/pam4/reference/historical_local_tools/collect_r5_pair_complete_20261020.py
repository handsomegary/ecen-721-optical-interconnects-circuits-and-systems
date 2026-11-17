"""Export only verified completed summary metrics, conditions and hashes."""
import json
import subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
REMOTE=r'''
import datetime,hashlib,json,os
from pathlib import Path
P=Path('/path/to/local/cadence-home/Desktop/cadence_projects/project6_28nm')
R=P/'runs/project6_noise_retry2_20261020'
S=P/'runs/adc_backend_pam4_r5_20261013/r5_late1'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
FROZEN='4cda4c9ec967f2af4bf4f89eacdd1beae372668877c358cf6aa26092597482eb'
assert sha(S/'frozen.json')==FROZEN
state=json.loads((R/'status.json').read_text())
assert state['status']=='complete' and state['stage']=='noise_validation_complete' and state['exit_code']==0
assert not state['remaining_session_members']
assert state['wrapper_sha256']=='a8e2db3fe63ab7777f6ff0300dfa8927248308f45936fe54a249ad9e7506c81e'
assert sha(P/'scripts/run_r5_noise_retry2_20261020.py')==state['wrapper_sha256']
out={'observed_UTC':datetime.datetime.utcnow().isoformat()+'Z',
     'status':'paired_validation_complete','complete_ADC_verified':False,
     'frozen_sha256':FROZEN,'state_sha256':sha(R/'status.json'),
     'ended_UTC':state['updated_UTC'],'boot_id':state['boot_id'],
     'wrapper_sha256':state['wrapper_sha256'],'pairs':{}}
for kind,expected,seed in (
 ('noiseless','ff8a466c80549cc476e8c768e56aea64cdab4ed4abb8a6b5d2709769519f716f',None),
 ('noise','16a9fdc53903720c057eaa173fca0c1b2c13128937fec5277f2eee3fcbc43ce2',173)):
 d=S/('validation_'+kind)
 path=d/'run_summary.json'
 assert sha(path)==expected
 s=json.loads(path.read_text())
 assert s['status']=='validation_complete' and s['run_status']['exit_code']==0
 assert s['frozen_file_sha256_before_run']==FROZEN and s['frozen_file_unchanged'] is True
 assert s['validation_fitting_performed'] is False and s['complete_ADC_verified'] is False
 assert s['fresh_holdout_seed']==2026101302
 assert s['validation_input_symbols']==2048 and s['FFE_complete_windows']==2032
 assert s['noise_seed']==seed
 assert s['deck_sha256']==sha(d/'bench.scs')
 result={k:s[k] for k in ('status','fresh_holdout_seed','validation_input_symbols',
     'FFE_complete_windows','noise_seed','frozen_file_unchanged','validation_fitting_performed',
     'deck_sha256','symbol_sequence_sha256','raw_transient_sha256')}
 result.update(summary_sha256=expected,run_status=s['run_status'],
     modeled_VDD_mW=s['VDD_power']['total_measured_VDD_W']*1000,
     power_scope=s['VDD_power'].get('scope'),noise_conditions=s.get('noise_conditions'),
     branches={})
 for point in ('primary','secondary'):
  p=s['results'][point];m=p['metrics']
  assert p['sample_count']==2048 and m['ADC_validation_input_count']==2048
  assert m['FFE_validation_output_count']==2032 and m['validation_fitting_performed'] is False
  row={k:p[k] for k in ('sample_count','held_min_V','held_max_V','held_Vppd','integer_symbol_lag')}
  row.update(fullscale_Vpp=m['ADC_fullscale_differential_Vpp'],
       clipped_input_count=m['ADC_validation_input_clipped_count'])
  for name in ('ideal7bit_ADC_then_FFE','raw_held_FFE_before_ADC'):
   z=m[name]
   assert z['sample_count']==2032 and z['bit_count']==4064
   row[name]={k:z[k] for k in ('sample_count','symbol_errors','SER','bit_count','gray_bit_errors','gray_BER')}
  result['branches'][point]=row
 out['pairs'][kind]=result
assert out['pairs']['noise']['symbol_sequence_sha256']==out['pairs']['noiseless']['symbol_sequence_sha256']
out['owned_workers']=[]
for p in Path('/proc').iterdir():
 if not p.name.isdigit() or int(p.name)==os.getpid():continue
 try:
  exe=os.readlink(str(p/'exe'));cwd=os.readlink(str(p/'cwd'))
  fields=(p/'stat').read_text().rsplit(')',1)[1].split()
  if fields[0]=='Z':continue
  args=(p/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace')
 except OSError:continue
 owned=cwd==str(P) or cwd.startswith(str(P)+'/') or str(P)+'/scripts/' in args
 if owned and ('python' in Path(exe).name.lower() or Path(exe).name.lower()=='spectre'):
  out['owned_workers'].append({'pid':int(p.name),'start':fields[19],'exe':Path(exe).name})
assert not out['owned_workers']
out['noise_spectre_log_sha256']=sha(S/'validation_noise/spectre.log')
print(json.dumps(out))
'''
cmd=['C:/Windows/System32/OpenSSH/ssh.exe','-i',str(ROOT/'work/ssh/vm_pdk_access_ed25519'),
     '-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','ConnectTimeout=8',
     '-o','StrictHostKeyChecking=yes','user@192.0.2.1','python3 -']
r=subprocess.run(cmd,input=REMOTE,encoding='utf-8',capture_output=True,timeout=40)
if r.returncode:raise RuntimeError(r.stderr)
data=json.loads(r.stdout)
(ROOT/'work/paired_r5_evidence_20261020.json').write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
print(json.dumps(data,indent=2))
