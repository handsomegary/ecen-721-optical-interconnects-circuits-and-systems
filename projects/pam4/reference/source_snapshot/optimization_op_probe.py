#!/usr/bin/env python3
"""Six-point native-card operating-point check, no PDK modifications."""
import hashlib
import json
import pathlib
import sys

PROJECT = pathlib.Path('/path/to/local/cadence-home/Desktop/cadence_projects/project6_28nm')
sys.path.insert(0, str(PROJECT / 'scripts'))
import p6_bench as b
import native_baseline as native
from psf_ascii import parse_file


def main():
    cardpath = PROJECT / 'configs/native_device_cards.json'
    native.install_cards(json.loads(cardpath.read_text()))
    configs = []
    for vb, cm in [(.58, .60), (.58, .65), (.58, .70), (.64, .60), (.64, .65), (.50, .60)]:
        configs.append(dict(arch='cml', nc=8, nv=8, rc=50, rv=50,
                            vb=vb, cm=cm, vdd=.9, rdeg=64000,
                            cdeg=100e-15, rdeg2=64000, cdeg2=100e-15,
                            ch=5e-15))
    directory = PROJECT / 'runs/optimization_op_probe'
    lines = b.header()
    saves = []
    for i, c in enumerate(configs):
        ll, ss = b.circuit(c, 'X%d' % i)
        lines += ll
        saves += ss
    lines += ['saveOptions options save=selected currents=selected',
              'save ' + ' '.join(saves), 'dcOp dc',
              'dcOpInfo info what=oppoint where=rawfile']
    status = b.run(directory, lines, 120)
    if status['exit_code'] != 0:
        raise RuntimeError(json.dumps(status))
    dc = parse_file(directory / 'raw/dcOp.dc')
    op = parse_file(directory / 'raw/dcOpInfo.info')
    results = []
    fields = ['gm', 'gds', 'vds', 'vdsat', 'vgs', 'ids', 'id', 'region']
    for i, c in enumerate(configs):
        tag = 'X%d' % i
        selected = {}
        for role in ['M1p0', 'T1p0', 'M2p0', 'T2p0']:
            matches = {}
            prefix = tag + role
            for key, value in op.values.items():
                if not (key == prefix or key.startswith(prefix + '.')):
                    continue
                if value and isinstance(value[0], dict):
                    entry = {f: value[0][f] for f in fields if f in value[0]}
                    if 'gm' in entry or 'gds' in entry:
                        if 'vds' in entry and 'vdsat' in entry:
                            entry['vds_minus_vdsat_V'] = entry['vds'] - entry['vdsat']
                        if entry.get('gds', 0):
                            entry['output_resistance_ohm'] = 1.0 / entry['gds']
                        matches[key] = entry
            selected[role] = matches
        node = {x: dc.values[tag + '_' + x][0] for x in
                ['ip', 'im', 'c_p', 'c_m', 'o_p', 'o_m', 's1_p', 's1_m', 's2_p', 's2_m', 'h0p', 'h0m']}
        power = -.9 * dc.values[tag + 'Vs:p'][0]
        r = {'config': c, 'node_DC_V': node,
             'VDD_power_W': power, 'selected_primitive_op': selected}
        if not all(selected.values()):
            r['missing_selected_primitive_roles'] = [k for k, v in selected.items() if not v]
        results.append(r)
        print(json.dumps(r, allow_nan=False), flush=True)
    output = {'scope': 'Six native-device-card DC operating points; schematic frozen four-track/four-hold eight-lane TG load.',
              'native_device_cards_sha256': hashlib.sha256(cardpath.read_bytes()).hexdigest(),
              'run_status': status, 'results': results,
              'raw_dc_sha256': dc.sha256, 'raw_oppoint_sha256': op.sha256,
              'export_scope': 'Derived selected MOS operating points, node DC values, test conditions and result hashes only.'}
    out = PROJECT / 'results/optimization_op_probe.json'
    out.write_text(json.dumps(output, indent=2, allow_nan=False) + '\n')
    print(str(out), flush=True)


if __name__ == '__main__':
    main()
