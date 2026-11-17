"""Read-only storage metadata audit; no waveform or model content is transferred."""
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REMOTE = r'''
import os,json,collections,datetime,importlib.util
from pathlib import Path
p=Path('/path/to/local/cadence-home/Desktop/cadence_projects/project6_28nm')
assert (p/'.codex_project6_owned').is_file()
groups=collections.defaultdict(lambda:[0,0,0])
names=collections.defaultdict(lambda:[0,0])
largest=[]
archives=collections.defaultdict(lambda:[0,0])
seen=set()
for directory,dirs,files in os.walk(str(p),followlinks=False):
 dirs[:]=[d for d in dirs if not os.path.islink(os.path.join(directory,d))]
 for name in files:
  f=Path(directory)/name
  s=f.lstat()
  if f.is_symlink():continue
  identity=(s.st_dev,s.st_ino)
  if identity in seen:continue
  seen.add(identity)
  rel=str(f.relative_to(p));size=s.st_size;allocated=s.st_blocks*512
  if name.endswith('.tran') or name.endswith('.psf'):kind='transient_waveform'
  elif name.endswith('.info'):kind='spectre_info'
  elif name.endswith('.ac') or name.endswith('.noise'):kind='ac_noise_result'
  elif name.endswith('.dc'):kind='dc_result'
  elif name.endswith(('.log','.out','.err')):kind='logs'
  elif name.endswith(('.scs','.va','.vams','.sp')):kind='netlist_or_model'
  elif name.endswith(('.json','.txt','.csv','.md')):kind='text_metadata_and_summaries'
  else:kind='other'
  groups[kind][0]+=1;groups[kind][1]+=size;groups[kind][2]+=allocated
  names[name][0]+=1;names[name][1]+=allocated
  largest.append((allocated,size,rel))
  for part in f.relative_to(p).parts[:-1]:
   if any(x in part for x in ('interrupted','failed','archived')):
    archives[part][0]+=1;archives[part][1]+=allocated;break
out={'observed_UTC':datetime.datetime.utcnow().isoformat()+'Z','read_only':True,
 'project':str(p),'group_columns':['files','apparent_bytes','allocated_bytes'],
 'groups':dict(groups),'largest_files':sorted(largest,reverse=True)[:12],
 'largest_repeated_filenames':sorted([(v[1],v[0],k) for k,v in names.items()],reverse=True)[:15],
 'preserved_interruption_failure_directories':dict(archives),
 'plot_libraries':{m:importlib.util.find_spec(m) is not None for m in ('numpy','matplotlib','PIL')},
 'r5_raw_sizes':{k:(p/'runs/adc_backend_pam4_r5_20261013/r5_late1'/('validation_'+k)/'raw/tranResponse.tran.tran').stat().st_size for k in ('noise','noiseless')}}
print(json.dumps(out))
'''
ssh = ['C:/Windows/System32/OpenSSH/ssh.exe','-i',str(ROOT/'work/ssh/vm_pdk_access_ed25519'),
       '-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','ConnectTimeout=8',
       '-o','StrictHostKeyChecking=yes','user@192.0.2.1','python3 -']
r = subprocess.run(ssh, input=REMOTE.encode(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45)
if r.returncode:
 raise RuntimeError(r.stderr.decode(errors='replace'))
out=json.loads(r.stdout)
local_total=0
for f in ROOT.rglob('*'):
 if f.is_file() and not f.is_symlink():local_total+=f.stat().st_size
out['local_workspace_apparent_bytes']=local_total
(ROOT/'work/project6_storage_audit_20261020.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8')
print(json.dumps(out,indent=2))
