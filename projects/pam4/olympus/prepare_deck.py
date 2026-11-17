#!/usr/bin/env python3
"""Prepare a separate Spectre deck for Olympus; never start a simulation."""
import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
config = json.loads((ROOT / 'cases.json').read_text(encoding='utf-8'))
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--case', required=True, choices=sorted(config['cases']))
parser.add_argument('--mode', choices=['smoke', 'full'], default='smoke')
parser.add_argument('--output', required=True, help='A new .scs file in your own empty run directory')
parser.add_argument('--pdk-root', default=os.environ.get('PROJECT6_PDK_ROOT', str(
    Path.home() / 'pdks/28nm/pdk_kit.0_2p2a_20160226_all/28nm_pdk')))
args = parser.parse_args()

case = config['cases'][args.case]
source = (ROOT / case['path']).resolve()
try:
    source.relative_to(ROOT)
except ValueError:
    sys.exit('Input escapes this package.')
if not source.is_file():
    sys.exit('Source deck missing: {}'.format(source))
data = source.read_bytes()
digest = hashlib.sha256(data).hexdigest()
if digest != case['sha256']:
    sys.exit('Source deck hash mismatch; no file written.')
text = data.decode('utf-8')

pdk_marker = '__pdk_root__'
pdk = Path(args.pdk_root).expanduser().resolve()
if not pdk.is_dir():
    sys.exit('PDK root does not exist: {}'.format(pdk))
if any(c in str(pdk) for c in ('\n', '\r', '"')):
    sys.exit('PDK path has an unsupported character.')
if text.count(pdk_marker) != 1:
    sys.exit('Unexpected number of PDK root placeholders; inspect manually.')
text = text.replace(pdk_marker, pdk.as_posix())
if pdk_marker in text:
    sys.exit('Unexpanded PDK root remains; inspect it manually.')

include_paths = re.findall(r'(?im)^\s*(?:include|\.include)\s+["\']([^"\']+)["\']', text)
if not include_paths:
    sys.exit('No model include found; inspect the deck manually.')
for entry in include_paths:
    path = Path(entry)
    if not path.is_absolute() or not path.is_file():
        sys.exit('Model include is missing or not absolute: {}'.format(entry))

shortened = False
if config['kind'] == 'PAM4' and args.mode == 'smoke':
    text, count = re.subn(r'(?m)^(\s*tranResponse\s+tran\s+stop=)[^\s]+',
                          r'\g<1>500p', text)
    if count != 1:
        sys.exit('Could not identify the single expected transient analysis.')
    shortened = True

out = Path(args.output).expanduser().resolve()
if out.suffix.lower() != '.scs' or not out.parent.is_dir():
    sys.exit('Output must be a .scs file in an existing run directory.')
if out.exists():
    sys.exit('Refusing to overwrite: {}'.format(out))
adapted = text.encode('utf-8')
with out.open('xb') as stream:
    stream.write(adapted)
print('Prepared:', out)
print('Case:', args.case, 'mode:', args.mode)
print('Source SHA256:', digest)
print('Adapted SHA256:', hashlib.sha256(adapted).hexdigest())
if shortened:
    print('SMOKE ONLY: 500 ps; not a full data record, FFE, SER or BER validation.')
print('No simulation was started.')
