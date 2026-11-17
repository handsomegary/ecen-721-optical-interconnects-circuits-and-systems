#!/usr/bin/env python3
"""Prepare one independent PAM4 transient run from the installed package."""

import argparse
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


PAM4_STOP = 2.198571428571428e-8
PAM4_STROBE = 1.116071428571429e-12
TIME_ROUNDING = 1e-15


def make_config(project, stop, end_tolerance, signals):
    # All strings and numbers come from the fixed project choices below.
    lines = ['ecen720Project = "{}"'.format(project),
             'ecen720Stop = {:.16g}'.format(stop),
             'ecen720EndTolerance = {:.16g}'.format(end_tolerance)]
    names = ('ecen720InputP', 'ecen720InputN', 'ecen720OutputP', 'ecen720OutputN')
    lines.extend('{} = "{}"'.format(name, signal) for name, signal in zip(names, signals))
    return ('\n'.join(lines) + '\n').encode('ascii')


def main():
    kit = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', choices=('pam4',))
    parser.add_argument('--root', type=Path, default=kit.parents[1] / 'projects',
                        help='Directory containing the pam4 project folder')
    parser.add_argument('--pdk-root', type=Path, help='Pass a nondefault PDK directory to prepare_deck.py')
    args = parser.parse_args()
    root = args.root.expanduser().resolve()

    bundle, case = 'pam4', 'candidate'
    stop, signals = PAM4_STOP, ('X_ip', 'X_im', 'X_o_p', 'X_o_m')
    # With strobeoutput=strobeonly, the last saved point can precede stop.
    end_tolerance = PAM4_STROBE + TIME_ROUNDING

    preparer = root / bundle / 'olympus' / 'prepare_deck.py'
    if not preparer.is_file():
        parser.error('Installed package preparer missing: {}'.format(preparer))

    with tempfile.TemporaryDirectory(prefix='.ecen720_prepare.', dir=str(root)) as stage:
        adapted = Path(stage) / 'input.scs'
        command = [sys.executable, str(preparer), '--case', case, '--mode', 'full',
                   '--output', str(adapted)]
        if args.pdk_root is not None:
            command.extend(['--pdk-root', str(args.pdk_root)])
        subprocess.run(command, check=True)
        deck = adapted.read_bytes()
        match = re.search(rb'(?m)^\s*tranResponse\s+tran\s+stop=([^\s]+)', deck)
        if not match or float(match.group(1)) != PAM4_STOP:
            raise ValueError('PAM4 full transient stop does not match the verified candidate.')

    run_dir = Path(tempfile.mkdtemp(prefix='{}_long.'.format(args.project), dir=str(root)))
    (run_dir / 'input.scs').write_bytes(deck)
    (run_dir / 'measurement_config.il').write_bytes(make_config(args.project, stop, end_tolerance, signals))
    for filename in ('run_long.sbatch', 'measure_transient.ocn'):
        shutil.copyfile(str(kit / filename), str(run_dir / filename))

    print('RUN_DIR={}'.format(run_dir))
    print('PROJECT={}  CASE={}  TRAN_STOP_S={:.16g}'.format(args.project, case, stop))
    print('Prepared input.scs, measurement_config.il, measure_transient.ocn and run_long.sbatch')


if __name__ == '__main__':
    main()
