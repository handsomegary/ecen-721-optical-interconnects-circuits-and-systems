"""Send postprocessing source to VM; fetch only derived PNG visualizations."""
import hashlib
import json
import subprocess
from pathlib import Path

P=Path(__file__).resolve().parents[1]
ssh=['C:/Windows/System32/OpenSSH/ssh.exe','-i',str(P/'work/ssh/vm_pdk_access_ed25519'),
     '-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','ConnectTimeout=8',
     '-o','StrictHostKeyChecking=yes','user@192.0.2.1']
source=(P/'work/render_r5_existing_eye_20261020.py').read_bytes()
r=subprocess.run(ssh+['python3 -'],input=source,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=180)
if r.returncode:
 print(r.stderr.decode(errors='replace'))
 raise SystemExit(r.returncode)
lines=r.stdout.decode().splitlines()
receipt=json.loads(lines[-1])
assert receipt['new_simulations'] is False
assert receipt['validation_fitting_performed'] is False
for name,meta in receipt['files'].items():
 assert name in ('Project6_r5_paired_eyes.png','Project6_r5_sample_distributions.png')
 path='/path/to/local/cadence-home/Desktop/cadence_projects/project6_28nm/results/eye_review_20261020/'+name
 image=subprocess.run(ssh+['cat '+path],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
 assert image.returncode==0
 assert image.stdout.startswith(b'\x89PNG\r\n\x1a\n')
 assert len(image.stdout)==meta['bytes'] and hashlib.sha256(image.stdout).hexdigest()==meta['sha256']
 output=P/'outputs'/name
 assert not output.exists()
 output.write_bytes(image.stdout)
(P/'work/r5_eye_visualization_receipt_20261020.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
print(json.dumps(receipt,indent=2))
