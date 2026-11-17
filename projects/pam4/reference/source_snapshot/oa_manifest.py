#!/usr/bin/env python3
"""Generate Project 6 native OA circuit data; contains no foundry model data.

The LA OA builder consumes these row lists using the installed native symbols
and their real CDF callbacks.  Run on the VM with --output-dir <new project>/scripts.
No Cadence database or existing project is edited by this generator.
"""
import argparse
import json
from pathlib import Path

PROJECT = '/path/to/local/cadence-home/Desktop/cadence_projects/project6_28nm'
LIBRARY = 'p6_224g_lib'
MODEL = '/path/to/pdk_28nm/models/spectre/pdk_toplevel.scs'
CORE = 'p6_ctle2_lvt_r2'
SAMPLER = 'p6_sampler8_lvt_r2'
TESTBENCH = 'tb_p6_ctle_sampler_ac_r2'
CONFIG = dict(nc=8, nv=8, input_W_m=3e-6, input_L_m=30e-9,
              tail_W_m=3e-6, tail_L_m=60e-9, load_R_ohm=50,
              degeneration_R_ohm=64000, degeneration_C_F=100e-15,
              supply_V=.9, tail_bias_V=.58, input_common_mode_V=.6,
              sampler_lanes=8, sampler_N_W_m=3e-6, sampler_P_W_m=3e-6,
              sampler_L_m=30e-9, hold_C_F=5e-15, leakage_R_ohm=1e12,
              fingers_per_instance=1, multiplicity_per_instance=1,
              native_sim_flag='ON', native_preSimflag='OFF',
              ccoflag=1, rcoflag=1, rgflag=1)


def pairs(mapping):
    return [[k, v] for k, v in mapping.items()]


def row(name, lib, cell, x, y, connections, props=None, callbacks=None,
        verify=None, mode='cell'):
    return [name, lib, cell, x, y, 'R0', pairs(connections),
            pairs(props or {}), pairs(callbacks or {}), pairs(verify or {}), mode]


def passive(name, cell, x, y, p, n, value):
    key = {'res': 'r', 'cap': 'c'}[cell]
    return row(name, 'analogLib', cell, x, y,
               {'PLUS': p, 'MINUS': n}, {key: value})


def mos(name, x, y, d, g, s, b, pmos=False, tail=False):
    length = '60n' if tail else '30n'
    # Separate W=3um, nf=1 devices preserve the original explicit parallel
    # topology.  Native callbacks calculate all geometry/parasitic parameters.
    # Actual installed CDF callbacks, verified by the native CDF probe, enable
    # simulation overrides and derive the hidden netlisted flag parameters.
    # The verified sequence requires preSimflag OFF after sim_flag ON. This
    # PDK setting enables schematic model parasitics; it is not physical PEX.
    # Never set hidden parameters directly or replace callback-derived geometry.
    return row(name, '28nm', 'pmos_lvt' if pmos else 'nmos_lvt',
               x, y, {'D': d, 'G': g, 'S': s, 'B': b},
               callbacks={'l': length, 'Wfg': '3u', 'fingers': '1', 'simM': '1',
                          'sim_flag': 'ON', 'preSimflag': 'OFF', 'ccoflag': '1',
                          'rcoflag': '1', 'rgflag': '1'},
               verify={'w': '3u', 'Wfg': '3u', 'lgb': length,
                       'fingers': '1', 'simM': '1', 'sim_flag': 'ON',
                       'preSimflag': 'OFF',
                       'ccoflag': '1', 'rcoflag': '1', 'rgflag': '1',
                       '_ccoflag': '1', '_rcoflag': '1', '_rgflag': '1'},
               mode='instance')


def core_rows(vss='vss'):
    rows = []
    for stage, ins, outs in [(1, ('inp', 'inn'), ('c_p', 'c_n')),
                             (2, ('c_p', 'c_n'), ('outp', 'outn'))]:
        sx = (stage - 1) * 24
        for side_index, (side, gate, drain) in enumerate(zip(('p', 'n'), ins, outs)):
            x0 = sx + side_index * 11
            source = 's%d_%s' % (stage, side)
            rows.append(passive('R%d%s' % (stage, side), 'res',
                                x0, 34, 'vdd', drain, '50'))
            for i in range(8):
                x, y = x0 + (i % 2) * 4.5, 28 - (i // 2) * 4
                rows.append(mos('M%d%s%d' % (stage, side, i),
                                x, y, drain, gate, source, vss))
                rows.append(mos('T%d%s%d' % (stage, side, i),
                                x, y - 22, source, 'vb', vss, vss, tail=True))
        rows.append(passive('Rdeg%d' % stage, 'res', sx + 4, -13,
                            's%d_p' % stage, 's%d_n' % stage, '64k'))
        rows.append(passive('Cdeg%d' % stage, 'cap', sx + 14, -13,
                            's%d_p' % stage, 's%d_n' % stage, '100f'))
    return rows


def sampler_rows(vss='vss', inputs=('inp', 'inn'), frozen=False, dx=0):
    rows = []
    for lane in range(8):
        x0, y0 = dx + (lane % 4) * 15, 30 - (lane // 4) * 23
        ck = ('vdd' if lane < 4 else vss) if frozen else 'ck%d' % lane
        kb = (vss if lane < 4 else 'vdd') if frozen else 'kb%d' % lane
        for index, (side, source) in enumerate(zip(('p', 'n'), inputs)):
            x = x0 + index * 7
            hold = 'h%d%s' % (lane, side)
            rows.extend([
                mos('SN%d%s' % (lane, side), x, y0, hold, ck, source, vss),
                mos('SP%d%s' % (lane, side), x, y0 - 4, hold, kb,
                    source, 'vdd', pmos=True),
                passive('CH%d%s' % (lane, side), 'cap', x, y0 - 9,
                        hold, vss, '5f'),
                passive('RH%d%s' % (lane, side), 'res', x, y0 - 14,
                        hold, source, '1T')])
    return rows


def source_rows():
    return [
        row('VDD', 'analogLib', 'vdc', -10, 34,
            {'PLUS': 'vdd', 'MINUS': 'gnd!'}, {'vdc': '0.9'}),
        row('VB', 'analogLib', 'vdc', -10, 29,
            {'PLUS': 'vb', 'MINUS': 'gnd!'}, {'vdc': '0.58'}),
        row('VCM', 'analogLib', 'vdc', -10, 24,
            {'PLUS': 'vcm', 'MINUS': 'gnd!'}, {'vdc': '0.6'}),
        row('VIN', 'analogLib', 'vdc', -10, 19,
            {'PLUS': 'stim', 'MINUS': 'gnd!'}, {'vdc': '0', 'acm': '1'}),
        row('EP', 'analogLib', 'vcvs', -10, 13,
            {'PLUS': 'inp', 'MINUS': 'vcm', 'NC+': 'stim', 'NC-': 'gnd!'},
            {'egain': '0.5'}),
        row('EN', 'analogLib', 'vcvs', -10, 7,
            {'PLUS': 'inn', 'MINUS': 'vcm', 'NC+': 'stim', 'NC-': 'gnd!'},
            {'egain': '-0.5'}),
        row('GND', 'analogLib', 'gnd', -10, 0, {'gnd!': 'gnd!'})]


def core_labels():
    return [[0, 40, 'PROJECT 6 / CTLE STAGE 1', .25],
            [24, 40, 'CTLE STAGE 2 / OUTPUT', .25],
            [0, 37, 'Eight parallel W=3u, L=30n, nf=1 input MOS per side', .125],
            [0, -19, 'Each tail: eight W=3u / L=60n MOS; shared VB=0.58 V', .125],
            [0, -21, 'Both stages: load 50 ohm; source bridge 64k || 100f', .125],
            [0, -23, 'R/C are ideal analogLib components; native MOS geometry is callback-derived', .125]]


def sampler_labels(dx=0, frozen=False):
    labels = [[dx, 40, '8-LANE DIFFERENTIAL TG SAMPLER', .25],
              [dx, 37, 'Each N/P switch: W=3u, L=30n, nf=1; hold C=5f per side', .125],
              [dx, -20, '1T resistors bridge each switch only for DC convergence', .125]]
    if frozen:
        labels.append([dx, -22, 'AC SNAPSHOT: lanes 0-3 track; lanes 4-7 hold', .125])
    else:
        labels.append([dx, -22, 'External complementary ck0..ck7 / kb0..kb7; target 14 GHz per lane', .125])
    for lane in range(8):
        labels.append([dx + (lane % 4) * 15, 33 - (lane // 4) * 23,
                       'LANE %d' % lane, .1875])
    return labels


def cells():
    core_ports = [[n, direction, x, y] for n, direction, x, y in [
        ('inp', 'input', -7, 30), ('inn', 'input', -7, 26),
        ('vb', 'input', -7, 18), ('vdd', 'inputOutput', -7, 14),
        ('vss', 'inputOutput', -7, 10),
        ('outp', 'output', 46, 30), ('outn', 'output', 46, 26)]]
    sampler_ports = [['inp', 'input', -7, 30], ['inn', 'input', -7, 26],
                     ['vdd', 'inputOutput', -7, 18], ['vss', 'inputOutput', -7, 14]]
    for lane in range(8):
        # A port index below the schematic makes the main device panels legible.
        x, y = (lane % 4) * 15, -28 - (lane // 4) * 15
        sampler_ports.extend([['ck%d' % lane, 'input', x, y],
                              ['kb%d' % lane, 'input', x, y-3],
                              ['h%dp' % lane, 'output', x+7, y],
                              ['h%dn' % lane, 'output', x+7, y-3]])
    tb_labels = core_labels() + sampler_labels(52, True) + [
        [-10, 45, 'PROJECT 6 / NATIVE SCHEMATIC AC BASELINE r2', .3],
        [-10, 42, 'TT, 0.9 V, 25 C; 1 V differential AC input; ideal R/C and ideal sources', .125],
        [-10, -27, 'Not a completed ADC. Validate native extracted circuit before reusing feasibility numbers.', .1875]]
    result = [[CORE, core_rows(), core_ports, core_labels()],
              [SAMPLER, sampler_rows(), sampler_ports, sampler_labels()],
              [TESTBENCH, source_rows() + core_rows('gnd!') +
               sampler_rows('gnd!', ('outp', 'outn'), True, 52), [], tb_labels]]
    for name, rows, ports, labels in result:
        names = [r[0] for r in rows]
        assert len(names) == len(set(names)), 'Duplicate component names in ' + name
        assert all(len(r) == 11 for r in rows)
        assert len(ports) == len(set(p[0] for p in ports))
    return result


def skill(value):
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=True)
    if isinstance(value, (list, tuple)):
        return 'list(' + ' '.join(skill(x) for x in value) + ')'
    if isinstance(value, (int, float)):
        return str(value)
    raise TypeError(type(value))


def generate(output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    cell_rows = cells()
    data = [
        '; Generated circuit intent only. Native save/reopen and netlist checks are required.',
        'laOaProject=' + skill(PROJECT),
        'laOaLibrary=' + skill(LIBRARY),
        'laOaCells=' + skill(cell_rows),
        'laOaNetlistCell=' + skill(TESTBENCH),
        'laOaModels=' + skill([[MODEL, 'tt']]),
        'laOaVariables=list()', '']
    (output_dir / 'p6_oa_data.il').write_text('\n'.join(data), encoding='utf-8')
    metadata = dict(schema_version=1, project=PROJECT, library=LIBRARY,
                    netlist_cell=TESTBENCH, configuration=CONFIG,
                    cells=[dict(name=c[0], primitive_count=len(c[1]),
                                top_port_count=len(c[2])) for c in cell_rows],
                    validation_required=[
                        'Saved/reopened pin-net and CDF verification',
                        'Native Spectre netlist syntax and operating-point checks',
                        'Native MOS geometry differs from wrapper-only feasibility inputs; rerun AC/noise',
                        'Native callbacks must yield visible and netlisted cco/rco/rg = 1'],
                    rows=cell_rows)
    (output_dir / 'p6_oa_manifest.json').write_text(
        json.dumps(metadata, indent=2, ensure_ascii=True) + '\n', encoding='utf-8')
    (output_dir / 'p6_native_manifest_readme.txt').write_text(
        'Project 6 native OA baseline r2\n'
        'All MOS instances use installed 28nm symbols and their actual CDF callbacks.\n'
        'Each parallel copy remains a separate W=3um, nf=1, multi=1 MOS.\n'
        'Input/switch length is 30nm; tail length is 60nm.\n'
        'Native callbacks calculate geometry including junction areas/perimeters and spacing.\n'
        'These geometry values differ from the earlier wrapper-only feasibility inputs.\n'
        'Verified callbacks run sim_flag=ON, then preSimflag=OFF, then ccoflag/rcoflag/rgflag=1.\n'
        'This sequence enables all three schematic model parasitic overrides for both N and P MOS.\n'
        'preSimflag=OFF is a PDK model setting; this circuit is NOT PEX or a physically extracted layout.\n'
        'The native builder verifies visible flags and hidden _ccoflag/_rcoflag/_rgflag equal 1.\n'
        'No hidden parameter or foundry model is manually overridden.\n'
        'The generated native netlist must be checked for these flags, geometry and connectivity,\n'
        'and simulated before old feasibility performance can be carried forward.\n'
        'Resistors/capacitors and testbench sources remain ideal analogLib components.\n'
        'The AC testbench freezes lanes 0-3 in track and lanes 4-7 in hold.\n'
        'This is an AFE/sampler baseline, not a complete ADC or clock-generation design.\n',
        encoding='utf-8')
    return metadata


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True)
    args = parser.parse_args()
    summary = generate(args.output_dir)
    print(json.dumps({k: summary[k] for k in ('project', 'library', 'netlist_cell', 'cells')}))
