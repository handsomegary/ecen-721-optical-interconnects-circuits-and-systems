"""Read-only waveform storage inventory, metadata only; never starts VM or jobs."""
import json, subprocess
from pathlib import Path
LOCAL=Path(__file__).resolve().parents[1]
REMOTE=r'''
import os,json,datetime,collections
from pathlib import Path
P=Path('/path/to/local/cadence-home/Desktop/cadence_projects/project6_28nm')
assert P.resolve()==P and (P/'.codex_project6_owned').is_file()
groups=collections.defaultdict(lambda:dict(files=0,bytes=0,allocated=0,raw=[]))
raw={};large=[];total=0
for directory,dirs,files in os.walk(str(P),followlinks=False):
 dirs[:]=[d for d in dirs if not (Path(directory)/d).is_symlink()]
 for name in files:
  f=Path(directory)/name
  if f.is_symlink():continue
  s=f.stat();rel=f.relative_to(P);total+=s.st_blocks*512
  key='/'.join(rel.parts[:2]) if rel.parts[0]=='runs' else rel.parts[0]
  g=groups[key];g['files']+=1;g['bytes']+=s.st_size;g['allocated']+=s.st_blocks*512
  if s.st_size>1000000:large.append(dict(path=str(rel),bytes=s.st_size,allocated=s.st_blocks*512))
  parts=rel.parts
  if 'raw' in parts:
   i=parts.index('raw');r='/'.join(parts[:i+1])
   if r not in raw:raw[r]=dict(files=0,bytes=0,allocated=0,extensions={},parent_metadata={})
   d=raw[r];d['files']+=1;d['bytes']+=s.st_size;d['allocated']+=s.st_blocks*512
   d['extensions'][f.suffix]=d['extensions'].get(f.suffix,0)+1
for r,d in raw.items():
 parent=(P/r).parent
 d['parent_files']=sorted(x.name for x in parent.iterdir() if x.is_file() and not x.is_symlink())
 for n in ('run_status.json','summary.json'):
  p=parent/n
  if p.exists():
   try:
    v=json.loads(p.read_text());d['parent_metadata'][n]={k:v[k] for k in ('status','exit_code','issue_codes','frozen_unchanged','validation_fitting_performed','run_status') if k in v}
   except Exception:d['parent_metadata'][n]={'read_error':True}
for key,g in groups.items():g['raw']=[r for r in raw if r.startswith(key+'/')]
opened=[]
for proc in Path('/proc').iterdir():
 if not proc.name.isdigit():continue
 try:
  for fd in (proc/'fd').iterdir():
   try:
    dest=os.readlink(str(fd))
    if dest.startswith(str(P)+'/'):opened.append(dict(pid=int(proc.name),path=dest[len(str(P))+1:]))
   except OSError:pass
 except OSError:pass
out=dict(observed_utc=datetime.datetime.utcnow().isoformat()+'Z',project=str(P),allocated_total=total,
 groups=dict(groups),raw_directories=raw,large_files=sorted(large,key=lambda x:x['allocated'],reverse=True),
 open_project_files=opened,boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())
print(json.dumps(out))
'''
cmd=['C:/Windows/System32/OpenSSH/ssh.exe','-i',str(LOCAL/'work/ssh/vm_pdk_access_ed25519'),'-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes','-o','HostKeyAlias=192.0.2.1','user@192.0.2.1','python3 -']
r=subprocess.run(cmd,input=REMOTE,text=True,encoding='utf-8',capture_output=True,timeout=45)
if r.returncode:raise RuntimeError(r.stderr or r.stdout)
out=json.loads(r.stdout)
(LOCAL/'work/project6_retention_inventory_20261022.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(observed_utc=out['observed_utc'],allocated_total=out['allocated_total'],groups=sorted([(k,v['allocated'],len(v['raw'])) for k,v in out['groups'].items()],key=lambda x:x[1],reverse=True),open_project_files=out['open_project_files']),indent=2))
