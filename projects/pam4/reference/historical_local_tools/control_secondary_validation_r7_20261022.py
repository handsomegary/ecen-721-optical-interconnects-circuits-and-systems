"""Transport for one newly authorized independent R7 baseline/candidate comparison."""
import argparse
import base64
import hashlib
import json
import subprocess

import control_secondary_r7_20261022 as training

LOCAL = training.LOCAL
NAME = 'secondary_cap_validation_r7_20261022'
PRELUDE = training.PRELUDE.replace("R=P/'runs/secondary_cap_training_r7_20261022'", "R=P/'runs/secondary_cap_validation_r7_20261022'")
PREFLIGHT = r'''
import importlib.util,shutil
training_script=P/'scripts/secondary_cap_training_r7_20261022.py'
assert sha(training_script)=='a83a0795f0cfb341889649f9578cfd82dbf7ecf380d2cea799938dd84ce1bbac'
spec=importlib.util.spec_from_file_location('r7_training_preflight',str(training_script))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
helper,runner,frozen,backend,ffe,metrics,psf=m.load_verified()
source=P/'runs/secondary_cap_training_r7_20261022'
s=json.loads((source/'status.json').read_text());protocol=json.loads((source/'protocol.json').read_text())
assert s['status']=='complete' and len(s['completed_cases'])==6
m.assert_unchanged(protocol)
expected={'baseline_r5':'650597e127ef2d86a5645e16ee8dd361915e41497fb1cd15a395e75ac67bc847',
 'secondary_c25_w2':'04298d537e246b4714d0037ab1ff044c705a695e804de041632ee1139de41b4f'}
for name,value in expected.items():
 assert sha(source/(name+'_detectors.json'))==s['detector_sha256'][name]==value
matches=[];scanned=0
for path in (P/'runs').rglob('protocol.json'):
 if path.is_symlink():continue
 try:v=json.loads(path.read_text())
 except (ValueError,OSError):continue
 scanned+=1
 if v.get('data_seed')==2026102301 or v.get('noise_seed')==251:
  matches.append(str(path.relative_to(P)))
assert not matches,'Proposed new data/noise seed already used in protocol metadata'
assert not R.exists() and not R.is_symlink(),'New independent study already exists; inspect instead of duplicate'
records=runner.inventory(helper)
assert not any((x.get('cwd') or '')==str(P) or (x.get('cwd') or '').startswith(str(P)+'/') for x in records),'Owned simulation already active'
memory={}
for line in Path('/proc/meminfo').read_text().splitlines():
 key,value=line.split(':',1)
 if key in ('MemTotal','MemAvailable','SwapTotal','SwapFree'):memory[key+'_KiB']=int(value.strip().split()[0])
print(json.dumps(dict(utc=now(),boot_id=runner.boot_id(),uptime_s=float(Path('/proc/uptime').read_text().split()[0]),
 actual_simulators=records,capacity_available=runner.capacity_available(records),free_bytes=shutil.disk_usage(str(P)).free,
 memory=memory,frozen_sha256=sha(original.FROZEN_PATH),training_status_sha256=sha(source/'status.json'),
 training_protocol_sha256=sha(source/'protocol.json'),detector_sha256=expected,new_data_seed=2026102301,
 new_noise_seed=251,seed_metadata_protocols_scanned=scanned,seed_collision_metadata=matches,new_root_absent=True)))
'''
PREPARE = r'''
assert not R.exists() and not R.is_symlink(),'Study already prepared; no replay'
script=P/('scripts/'+NAME+'.py')
subprocess.check_call(['python3',str(script),'--self-test'])
subprocess.check_call(['python3',str(script),'--prepare'],cwd=str(P/'scripts'))
state=json.loads((R/'status.json').read_text())
state.pop('prepared_sha256',None)
print(json.dumps(dict(state=state,script_sha256=sha(script),protocol_sha256=sha(R/'protocol.json'))))
'''
LAUNCH = r'''
import fcntl
with (P/('runs/.'+NAME+'_dispatch.lock')).open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 D=P/('runs/'+NAME+'_dispatch')
 assert not D.exists() and not D.is_symlink(),'Already dispatched; no duplicate or retry'
 state=json.loads((R/'status.json').read_text());assert state['status']=='prepared'
 assert not any((x.get('cwd') or '')==str(P) or (x.get('cwd') or '').startswith(str(P)+'/') for x in actual()),'Project already simulating'
 script=P/('scripts/'+NAME+'.py')
 env=os.environ.copy();env['CDS_LIC_FILE']='<LICENSE_FILE>';env['LM_LICENSE_FILE']=env['CDS_LIC_FILE']
 D.mkdir()
 with (D/'worker.log').open('xb') as log:
  child=subprocess.Popen(['python3',str(script),'--run'],cwd=str(P/'scripts'),env=env,
   stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 time.sleep(.3)
 receipt=dict(started_utc=now(),runner=original.process_record(child.pid),boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
  script_sha256=sha(script),protocol_sha256=sha(R/'protocol.json'),automatic_retry=False,
  scope='2026-10-22 user explicitly authorized one independent fresh-data baseline vs25fF2um comparison: 2noiseless then2noise, fixed pre-existing trained detectors, no fitting or extra candidates; monitor30min, stop/report failures, no retry.')
 original.atomic_json(D/'launch_receipt.json',receipt)
 print(json.dumps(dict(launch=receipt)),flush=True);time.sleep(3)
 print(json.dumps(dict(state=json.loads((R/'status.json').read_text()),exit_code=child.poll())),flush=True)
'''
OBSERVE = r'''
state=json.loads((R/'status.json').read_text());launch=json.loads((P/('runs/'+NAME+'_dispatch/launch_receipt.json')).read_text())
boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip();ref=launch['runner'];live=original.process_record(ref['pid']) if ref else None
identity=dict(live=live,boot_matches=boot==launch['boot_id'],start_matches=bool(live and live['start_ticks']==ref['start_ticks']),script_matches=sha(P/('scripts/'+NAME+'.py'))==launch['script_sha256'])
if live:identity['command_matches']=str(P/('scripts/'+NAME+'.py')).encode() in (Path('/proc')/str(live['pid'])/'cmdline').read_bytes().split(b'\0')
diagnostic={};case=state.get('current_case')
if case:
 assert Path(case).name==case
 logpath=R/case/'spectre.log';log=logpath.read_text(errors='replace') if logpath.exists() else ''
 diagnostic=dict(transient_started="Transient Analysis `tranResponse'" in log,spectre18_seen='SPECTRE-18' in log,
  log_bytes=logpath.stat().st_size if logpath.exists() else 0,completion_lines=re.findall(r'spectre completes with[^\r\n]*',log)[-1:])
print(json.dumps(dict(observed_utc=now(),status=state,launch=launch,identity=identity,diagnostic=diagnostic,
 actual_simulators=actual(),frozen_sha256=sha(original.FROZEN_PATH))))
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('preflight', 'prepare', 'launch', 'observe'))
    args = parser.parse_args()
    code = PRELUDE + '\nNAME=' + repr(NAME) + '\n'
    if args.action == 'prepare':
        payload = (LOCAL / 'work/project6_start' / (NAME + '.py')).read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        code += '\nimport base64\ndata=base64.b64decode(' + repr(base64.b64encode(payload).decode()) + ')\n'
        code += 'assert hashlib.sha256(data).hexdigest()==' + repr(digest) + '\n'
        code += "target=P/('scripts/'+NAME+'.py')\nif target.exists():assert target.read_bytes()==data\nelse:\n with target.open('xb') as f:f.write(data)\n"
        code += PREPARE
    else:
        code += {'preflight': PREFLIGHT, 'launch': LAUNCH, 'observe': OBSERVE}[args.action]
    command = ['C:/Windows/System32/OpenSSH/ssh.exe', '-i', str(LOCAL / 'work/ssh/vm_pdk_access_ed25519'),
               '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes', '-o', 'ConnectTimeout=8',
               '-o', 'StrictHostKeyChecking=yes', '-o', 'HostKeyAlias=192.0.2.1',
               'user@192.0.2.1', 'python3 -u -']
    result = subprocess.run(command, input=code, text=True, encoding='utf-8', capture_output=True, timeout=55)
    if result.returncode:
        raise RuntimeError(result.stderr or result.stdout)
    rows = [json.loads(line) for line in result.stdout.splitlines() if line.strip().startswith('{')]
    obj = rows[-1] if args.action in ('preflight', 'observe') else rows
    (LOCAL / ('work/secondary_validation_r7_' + args.action + '_20261022.json')).write_text(
        json.dumps(obj, indent=2) + '\n', encoding='utf-8')
    for value in rows:
        if isinstance(value.get('state'), dict):
            value['state'].pop('prepared_sha256', None)
    print(json.dumps(rows))


if __name__ == '__main__':
    main()
