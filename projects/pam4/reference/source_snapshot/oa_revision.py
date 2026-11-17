#!/usr/bin/env python3
"""Create new native OA circuit-intent files from a selected CML configuration.

Uses the already verified native symbol/CDF recipe. Does not edit an OA view.
The existing project builder consumes the resulting revision-specific data.
"""
import argparse
import json
import re
from pathlib import Path
import oa_manifest as original


def core(config, ground='vss'):
    rows = []
    for stage, copies, load, deg, cap, inputs, outputs in [
        (1, config['nc'], config['rc'], config['rdeg'], config['cdeg'], ('inp', 'inn'), ('c_p', 'c_n')),
        (2, config['nv'], config['rv'], config.get('rdeg2', 0), config.get('cdeg2', 0), ('c_p', 'c_n'), ('outp', 'outn'))]:
        if int(copies) != copies or not 1 <= copies <= 24:
            raise ValueError('Unsupported parallel-copy count')
        sx = (stage - 1) * 24
        for index, (side, gate, drain) in enumerate(zip(('p', 'n'), inputs, outputs)):
            x0 = sx + index * 11
            source = 's%d_%s' % (stage, side)
            rows.append(original.passive('R%d%s' % (stage, side), 'res', x0, 34,
                                         'vdd', drain, '%.12g' % load))
            for i in range(int(copies)):
                x, y = x0 + (i % 2) * 4.5, 28 - (i // 2) * 4
                rows.append(original.mos('M%d%s%d' % (stage, side, i), x, y,
                                         drain, gate, source, ground))
                rows.append(original.mos('T%d%s%d' % (stage, side, i), x, y - 55,
                                         source, 'vb', ground, ground, tail=True))
        if deg:
            rows.append(original.passive('Rdeg%d' % stage, 'res', sx + 4, -80,
                                         's%d_p' % stage, 's%d_n' % stage, '%.12g' % deg))
            if cap:
                rows.append(original.passive('Cdeg%d' % stage, 'cap', sx + 14, -80,
                                             's%d_p' % stage, 's%d_n' % stage, '%.12g' % cap))
        else:
            rows.append(original.row('Vtie%d' % stage, 'analogLib', 'vdc', sx + 4, -80,
                                     {'PLUS': 's%d_p' % stage, 'MINUS': 's%d_n' % stage}, {'vdc': '0'}))
    return rows


def generate(config, revision, output):
    if not re.match(r'^r[0-9]+$', revision) or int(revision[1:]) < 3:
        raise ValueError('Require a new revision r3 or later')
    if config.get('arch', 'cml') != 'cml':
        raise ValueError('Only verified native CML topology supported')
    for key in ('wn_sw', 'wp_sw'):
        if abs(config.get(key, 3e-6) - 3e-6) > 1e-15:
            raise ValueError('Switch geometry differs from verified native cards')
    if abs(config.get('ch', 5e-15) - 5e-15) > 1e-24:
        raise ValueError('This revision reuses the 5fF native sampler')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    core_name = 'p6_ctle2_lvt_' + revision
    tb_name = 'tb_p6_ctle_sampler_ac_' + revision
    original_cells = original.cells()
    ports = original_cells[0][2]
    sources = original.source_rows()
    values = {'VDD': config.get('vdd', .9), 'VB': config['vb'], 'VCM': config.get('cm', .6)}
    for row in sources:
        if row[0] in values:
            row[7] = [['vdc', '%.12g' % values[row[0]]]]
    labels = [[0, 42, 'PROJECT 6 / SELECTED CTLE-VGA ' + revision, .25],
              [0, 39, 'Native W=3u copies; input L=30n; tail L=60n; nf=multi=1', .125],
              [0, -88, 'nc=%s nv=%s; Rc=%g Rv=%g; VB=%g V; input CM=%g V' % (
                  config['nc'], config['nv'], config['rc'], config['rv'], config['vb'], config.get('cm', .6)), .125],
              [0, -91, 'Stage1 R=%g C=%g; Stage2 R=%g C=%g' % (
                  config['rdeg'], config['cdeg'], config.get('rdeg2', 0), config.get('cdeg2', 0)), .125],
              [0, -94, 'Fixed selected component values; ideal R/C and bias; physical programming circuitry remains pending', .125]]
    cells = [[core_name, core(config), ports, labels],
             [tb_name, sources + core(config, 'gnd!') +
              original.sampler_rows('gnd!', ('outp', 'outn'), True, 55), [],
              labels + original.sampler_labels(55, True)]]
    for name, rows, pins, unused in cells:
        assert len({r[0] for r in rows}) == len(rows)
        assert all(len(r) == 11 for r in rows)
    data = ['; New native revision. Old views preserved.',
            'laOaProject=' + original.skill(original.PROJECT),
            'laOaLibrary=' + original.skill(original.LIBRARY),
            'laOaCells=' + original.skill(cells),
            'laOaNetlistCell=' + original.skill(tb_name),
            'laOaModels=' + original.skill([[original.MODEL, 'tt']]),
            'laOaVariables=list()', '']
    destination = output / ('p6_oa_data_' + revision + '.il')
    if destination.exists():
        raise ValueError('Refusing to overwrite revision circuit intent')
    destination.write_text('\n'.join(data), encoding='utf8')
    manifest = {'revision': revision, 'library': original.LIBRARY, 'config': config,
                'netlist_cell': tb_name, 'reuse_sampler': original.SAMPLER,
                'data_file': str(destination), 'cells': [
                    {'name': c[0], 'primitive_count': len(c[1]), 'top_port_count': len(c[2])} for c in cells]}
    (output / ('p6_oa_manifest_' + revision + '.json')).write_text(
        json.dumps(manifest, indent=2) + '\n', encoding='utf8')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    print(json.dumps(generate(config, args.revision, args.output_dir)))
