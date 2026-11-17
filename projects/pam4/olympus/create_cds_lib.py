#!/usr/bin/env python3
"""Create a new, independent cds.lib; never overwrite an existing file."""
import json
import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
cfg = json.loads((root / 'cases.json').read_text(encoding='utf-8'))
library = Path(os.environ.get('ECEN720_OA_LIBRARY_DIR', str(root / cfg['library_path']))).expanduser().resolve()
pdk = Path(os.environ.get('PROJECT6_PDK_ROOT', str(
    Path.home() / 'pdks/28nm/pdk_kit.0_2p2a_20160226_all/28nm_pdk'))).expanduser().resolve()
foundry = pdk / '28nm'
target = root / 'olympus_workspace' / 'cds.lib'
for name, path in [('project OA library', library), ('28nm library', foundry)]:
    if not path.is_dir():
        sys.exit('Missing {}: {}'.format(name, path))
    if any(c.isspace() for c in str(path)):
        sys.exit('Whitespace in {} path needs manual cds.lib configuration: {}'.format(name, path))
target.parent.mkdir(parents=True, exist_ok=True)
content = ('DEFINE basic $CDSHOME/tools/dfII/etc/cdslib/basic\n'
           'DEFINE analogLib $CDSHOME/tools/dfII/etc/cdslib/artist/analogLib\n'
           'DEFINE 28nm {}\n'
           'DEFINE {} {}\n').format(foundry, cfg['library_name'], library)
try:
    with target.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(content)
except FileExistsError:
    sys.exit('Refusing to overwrite existing cds.lib: {}'.format(target))
print('Created:', target)
print('No GUI or simulation was started.')
