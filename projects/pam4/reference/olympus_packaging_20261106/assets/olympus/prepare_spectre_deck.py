#!/usr/bin/env python3
"""Prepare a separate Olympus copy of a user-owned historical Spectre deck."""
import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

BUNDLE = Path(__file__).resolve().parent.parent
VM_PROJECT = (BUNDLE / 'vm_project').resolve()
OLD_PROJECT = '/path/to/local/cadence-home/Desktop/cadence_projects/project6_28nm'
OLD_PDK = '<PDK_ROOT>'
DEFAULT_PDK = Path.home() / 'pdks/28nm/pdk_kit.0_2p2a_20160226_all/28nm_pdk'

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('netlist', help='A .scs file inside this bundle\'s vm_project directory')
parser.add_argument('--pdk-root', default=os.environ.get('PROJECT6_PDK_ROOT', str(DEFAULT_PDK)))
parser.add_argument('--dry-run', action='store_true', help='Inspect replacements without writing any files')
args = parser.parse_args()

source = Path(args.netlist).expanduser().resolve()
try:
    source.relative_to(VM_PROJECT)
except ValueError:
    sys.exit('Input must be inside the bundled vm_project directory.')
if not source.is_file() or source.suffix.lower() != '.scs':
    sys.exit('Input must be an existing .scs file: {}'.format(source))

pdk = Path(args.pdk_root).expanduser().resolve()
if not pdk.is_dir():
    sys.exit('PDK root not found: {}'.format(pdk))
for name, value in [('PDK root', str(pdk)), ('bundle directory', str(VM_PROJECT))]:
    if any(c in value for c in ('\n', '\r', '"')):
        sys.exit('Unsafe character in {}.'.format(name))

original = source.read_bytes()
try:
    text = original.decode('utf-8')
except UnicodeDecodeError:
    sys.exit('Input netlist is not UTF-8; no copy was written.')
counts = {'pdk_root': text.count(OLD_PDK), 'project_root': text.count(OLD_PROJECT)}
text = text.replace(OLD_PDK, str(pdk)).replace(OLD_PROJECT, str(VM_PROJECT))
if '/path/to/local/cadence-home/' in text:
    sys.exit('Unmapped /path/to/local/cadence-home/ path remains; inspect this deck and its dependencies manually.')

includes = re.findall(r'(?im)^\s*(?:include|\.include)\s+["\']([^"\']+)["\']', text)
for entry in includes:
    candidate = Path(entry)
    if not candidate.is_absolute():
        sys.exit('Relative include needs manual review before copying: {}'.format(entry))
    if not candidate.is_file():
        sys.exit('Referenced include file is not available: {}'.format(candidate))

adapted = text.encode('utf-8')
report = {'source': str(source), 'source_sha256': hashlib.sha256(original).hexdigest(),
          'adapted_sha256': hashlib.sha256(adapted).hexdigest(), 'replacements': counts,
          'includes': includes, 'simulation_started': False}
if args.dry_run:
    print(json.dumps(report, indent=2))
    sys.exit(0)

out_root = BUNDLE / 'olympus_runs'
out_root.mkdir(exist_ok=True)
out_dir = Path(tempfile.mkdtemp(prefix='prepared-', dir=str(out_root)))
(out_dir / 'input.scs').write_bytes(adapted)
(out_dir / 'adaptation.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print('Prepared:', out_dir / 'input.scs')
print('Record:', out_dir / 'adaptation.json')
print('No simulation was started. Review all external dependencies before running.')
