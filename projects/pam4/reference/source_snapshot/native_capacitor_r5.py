#!/usr/bin/env python3
"""Create/extract a native MOM-capacitor fixture, Python3.6, VM execution only.

Six requested three-terminal mom_cap geometries pass through native CDF callbacks.
Only m=1 is an OA build verification requirement. Requested dimensions are NOT
assumed accepted: saved CDF snapshot and measured AC admittance are separate.
Full instance cards/tokens stay VM-side. This is not a CDAC, DRC, or PVT proof.
"""
import argparse
import hashlib
import json
import math
import re
from pathlib import Path

import oa_manifest as o
import p6_bench as b
import psf_ascii
from pam4_integration import _spectre_number

PROJECT = Path(o.PROJECT)
CELL = 'tb_p6_native_capacitor_r5'
CARD_PATH = PROJECT/'configs/native_capacitor_cards_r5.json'
SNAPSHOT_PATH = PROJECT/'results/native_capacitor_saved_cdf_r5.tsv'
CARDS = {}
FREQUENCIES = [('1M', 1e6), ('1G', 1e9), ('10G', 10e9), ('56G', 56e9)]
FIELDS = ('Wfinger', 'Sfinger', 'Lfinger', 'Nfinger', 'StartMn', 'StopMn', 'm', 'c')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic_json(path, value):
    path = Path(path)
    tmp = path.with_name(path.name+'.tmp')
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False)+'\n')
    tmp.replace(path)


def geometries():
    for length, fingers in [(1., 32), (1., 16), (1., 8), (1., 4), (.5, 8), (.2, 4)]:
        key = 'l%d_n%d' % (round(length*1000), fingers)
        yield key, dict(Wfinger='50n', Sfinger='50n', Lfinger='%.12gu' % length,
                        Nfinger=str(fingers), StartMn='1', StopMn='3')


def fixture_rows():
    rows = [o.row('VDRIVE', 'analogLib', 'vdc', -15, 35,
                  {'PLUS': 'drive', 'MINUS': 'gnd!'}, {'vdc': '.45', 'acm': '1'}),
            o.row('GND', 'analogLib', 'gnd', -15, 0, {'gnd!': 'gnd!'})]
    for i, (key, geometry) in enumerate(geometries()):
        x, y = (i % 3)*20, 25-(i//3)*25
        rows += [
            o.row('VP'+key, 'analogLib', 'vdc', x-5, y+5,
                  {'PLUS': 'drive', 'MINUS': 'cp'+key}, {'vdc': '0'}),
            o.row('VN'+key, 'analogLib', 'vdc', x+7, y-5,
                  {'PLUS': 'cn'+key, 'MINUS': 'gnd!'}, {'vdc': '0'}),
            o.row('C'+key, '28nm', 'mom_cap', x, y,
                  {'PLUS': 'cp'+key, 'MINUS': 'cn'+key, 'BULK': 'gnd!'},
                  props={'m': '1'}, callbacks=geometry, verify={'m': '1'}, mode='instance')]
    return rows


def snapshot_script():
    # Read only the newly created fixture, never PDK models or library-wide CDF.
    return '''; Read-only saved-instance CDF snapshot for the new capacitor fixture.
procedure(p6CapacitorSnapshotR5()
 let((cv port inst data field param lib)
  lib=ddGetObj("%s")
  unless(lib && equal(lib~>readPath "%s/%s")
    error("Unexpected Project6 library path\\n"))
  when(isFile("%s") error("Refusing to replace capacitor CDF snapshot\\n"))
  cv=dbOpenCellViewByType("%s" "%s" "schematic" "schematic" "r")
  unless(cv error("Native capacitor fixture absent\\n"))
  port=outfile("%s" "w")
  unless(port error("Cannot create CDF snapshot\\n"))
  fprintf(port "instance\\tfield\\tvalue\\n")
  foreach(inst cv~>instances
   when(equal(inst~>libName "28nm") && equal(inst~>cellName "mom_cap")
    data=cdfGetInstCDF(inst)
    unless(data error("Missing native capacitor CDF\\n"))
    foreach(field list("Wfinger" "Sfinger" "Lfinger" "Nfinger" "StartMn" "StopMn" "m" "c")
     param=cdfFindParamByName(data field)
     when(param fprintf(port "%%s\\t%%s\\t%%L\\n" inst~>name field param~>value))
    )
   )
  )
  close(port)
  dbClose(cv)
  printf("P6_NATIVE_CAPACITOR_CDF_SNAPSHOT_COMPLETE\\n")
  t
 )
)
p6CapacitorSnapshotR5()
exit()
''' % (o.LIBRARY, o.PROJECT, o.LIBRARY, str(SNAPSHOT_PATH), o.LIBRARY, CELL, str(SNAPSHOT_PATH))


def generate():
    rows = fixture_rows()
    if len(rows) != 20 or len({x[0] for x in rows}) != len(rows):
        raise ValueError('Unexpected fixture primitive count/duplicates')
    cells = [[CELL, rows, [], [[0, 42, 'PROJECT6 r5 / NATIVE MOM CAPACITOR AC FIXTURE', .25],
                               [0, 39, 'Requested sizes require saved CDF check; native HardCons remains unchanged', .125]]]]
    data = ['; New capacitor fixture only. No PDK modifications.',
            'laOaProject='+o.skill(o.PROJECT), 'laOaLibrary='+o.skill(o.LIBRARY),
            'laOaCells='+o.skill(cells), 'laOaNetlistCell='+o.skill(CELL),
            'laOaModels='+o.skill([[o.MODEL, 'tt']]), 'laOaVariables=list()', '']
    intent = PROJECT/'scripts/p6_oa_capacitor_r5.il'
    snapshot = PROJECT/'scripts/p6_capacitor_snapshot_r5.il'
    if intent.exists() or snapshot.exists():
        raise ValueError('Refuse to replace capacitor intent/snapshot script')
    intent.write_text('\n'.join(data))
    snapshot.write_text(snapshot_script())
    print(json.dumps({'intent': str(intent), 'snapshot_script': str(snapshot),
                      'cell': CELL, 'capacitors': 6, 'primitives': len(rows),
                      'requested_geometry_verified': False}), flush=True)


def read_snapshot(path):
    if path is None:
        return None
    path = Path(path)
    if not path.exists():
        raise ValueError('Requested saved CDF snapshot missing')
    result = {}
    for line in path.read_text().splitlines()[1:]:
        name, field, text = line.split('\t', 2)
        if name not in {'C'+key for key, unused in geometries()} or field not in FIELDS:
            raise ValueError('Unexpected native CDF snapshot entry')
        value = json.loads(text) if text.startswith('"') else text
        if field in result.setdefault(name, {}):
            raise ValueError('Duplicate CDF snapshot entry')
        result[name][field] = value
    if set(result) != {'C'+key for key, unused in geometries()}:
        raise ValueError('Incomplete six-capacitor CDF snapshot')
    for values in result.values():
        if any(field not in values for field in FIELDS[:-1]):
            raise ValueError('Required geometry/multiplicity field missing')
        if _spectre_number(str(values['m'])) != 1.:
            raise ValueError('Saved capacitor CDF m is not one')
    return result


def extract_cards(source, snapshot=None):
    source = Path(source).resolve()
    if (PROJECT/'runs').resolve() not in source.parents:
        raise ValueError('Require native netlist under own project runs')
    marker_parent = next((x for x in source.parents if (x/'OA_BUILD_VERIFIED').exists()), None)
    if marker_parent is None:
        raise ValueError('Native saved/reopened OA verification marker absent')
    text = source.read_text().replace('\\\n', ' ')
    actual = read_snapshot(snapshot)
    cards = {}
    for key, requested in geometries():
        matches = re.findall(r'^C'+re.escape(key)+r'\s+\(([^)]*)\)\s+(\S+)\s*(.*)$', text, re.M)
        if len(matches) != 1:
            raise ValueError('Native capacitor instance absent/nonunique: '+key)
        terminals, model, parameters = matches[0]
        terminals = terminals.split()
        if len(terminals) != 3 or model == 'capacitor':
            raise ValueError('Expected native three-terminal model, not ideal two-terminal capacitor')
        if terminals[:2] != ['cp'+key, 'cn'+key] or terminals[2] not in ('0', 'gnd!'):
            raise ValueError('Native capacitor port order/connectivity differs')
        # Parameters are preserved verbatim apart from continuation whitespace.
        # m is checked through native OA/CDF verification, not guessed model aliases.
        values = None if actual is None else actual['C'+key]
        accepted = None if values is None else all(math.isclose(_spectre_number(str(values[n])),
                       _spectre_number(value), rel_tol=1e-8, abs_tol=1e-18) for n, value in requested.items())
        cards[key] = dict(model=model, parameters=' '.join(parameters.split()),
                          requested_geometry=requested, saved_CDF_geometry=values,
                          requested_geometry_matches_saved_CDF=accepted,
                          native_three_terminal_card=True)
    return dict(schema_version=1, native_CDF_saved_reopened_verified=True,
                native_OA_cell=o.LIBRARY+'/'+CELL+'/schematic',
                source_netlist_VM_path=str(source), source_netlist_sha256=digest(source),
                saved_CDF_snapshot_sha256=None if snapshot is None else digest(snapshot),
                geometry_verification='not_checked' if actual is None else 'per_card_match_status', cards=cards)


def install(path=CARD_PATH):
    global CARDS
    data = json.loads(Path(path).read_text())
    if not data.get('native_CDF_saved_reopened_verified') or set(data['cards']) != {key for key, unused in geometries()}:
        raise ValueError('Incomplete/unverified native capacitor fixture')
    CARDS = data['cards']
    return dict(native_cards_sha256=digest(path), source_netlist_sha256=data['source_netlist_sha256'],
                geometry_verification=data['geometry_verification'], native_capacitor_keys=sorted(CARDS))


def capacitor(name, plus, minus, bulk, case):
    if case not in CARDS:
        raise ValueError('Install supported native capacitor cards first')
    card = CARDS[case]
    return '%s (%s %s %s) %s %s' % (name, plus, minus, bulk, card['model'], card['parameters'])


def measure_admittance(frequency, drive, ip, im):
    if not math.isfinite(frequency) or frequency <= 0 or abs(drive) < .5:
        raise ValueError('Invalid capacitor AC frequency/drive')
    plus, mutual = ip/drive, im/drive
    omega = 2*math.pi*frequency
    total_c, mutual_c = plus.imag/omega, mutual.imag/omega
    if mutual_c <= 0 or total_c <= 0:
        raise ValueError('Capacitor current orientation/noncapacitive response requires inspection')
    return dict(frequency_Hz=frequency, plus_total_effective_C_F=total_c,
                mutual_effective_C_F=mutual_c, plus_minus_difference_effective_C_F=total_c-mutual_c,
                plus_conductance_S=plus.real, transfer_real_admittance_S=mutual.real,
                plus_minus_difference_real_admittance_S=plus.real-mutual.real,
                plus_impedance_magnitude_ohm=1/abs(plus), plus_admittance_phase_degrees=math.degrees(math.atan2(plus.imag, plus.real)))


def extract(source, snapshot=None):
    data = extract_cards(source, snapshot)
    directory = PROJECT/'runs/native_capacitor_r5_20261013/native_fixture'
    if CARD_PATH.exists() or directory.exists():
        raise ValueError('Refuse to replace native capacitor cards or fixture run')
    atomic_json(CARD_PATH, data)
    native = install(CARD_PATH)
    lines = Path(source).read_text().split('simulatorOptions options')[0].splitlines()
    saves = ['drive', 'VDRIVE:p']+['V'+side+key+':p' for key, unused in geometries() for side in ('P', 'N')]
    lines += ['simulatorOptions options temp=25 tnom=25 reltol=1e-5 vabstol=1u iabstol=1p',
              'saveOptions options save=selected currents=selected', 'save '+' '.join(saves), 'dcOp dc']
    # A distinct auxiliary endpoint avoids zero-span sweep ambiguity. Only the
    # first, exact requested frequency from each two-point AC analysis is reported.
    for label, frequency in FREQUENCIES:
        lines.append('ac%s ac start=%.15g stop=%.15g lin=2' % (label, frequency, frequency*1.000001))
    status = b.run(directory, lines, timeout=120)
    if status['exit_code'] != 0:
        raise RuntimeError('Native capacitor fixture DC/AC execution failed; files retained')
    result = dict(schema_version=1, native=native, run_status=status, native_capacitors=6,
                  conditions=dict(temperature_C=25, process_corner='tt', PLUS_DC_V=.45,
                                  MINUS_DC_V=0., BULK_DC_V=0., plus_AC_drive_V=1.,
                                  deembedding='Separate zero-volt PLUS/MINUS probes; currents divided by measured AC drive'),
                  requested_geometries_verified=False, actual_CDF_snapshot_available=snapshot is not None,
                  cases={}, raw_sha256={'dc': digest(directory/'raw/dcOp.dc')},
                  scope='Native capacitor admittance screen; not CDAC operation, layout/DRC, mismatch or PVT qualification',
                  interpretation='At low frequency mutual C is imag(Iminus/Vplus)/(2*pi*f); total driven-terminal C uses Iplus. Their difference estimates driven-terminal substrate parasitic. High-frequency values are effective admittances, not a frequency-independent lumped capacitor model.')
    for key, requested in geometries():
        card = data['cards'][key]
        result['cases'][key] = dict(requested_geometry=requested,
                                    requested_geometry_matches_saved_CDF=card['requested_geometry_matches_saved_CDF'],
                                    saved_CDF_geometry=card['saved_CDF_geometry'], AC=[])
    for label, frequency in FREQUENCIES:
        raw = psf_ascii.parse_file(directory/'raw'/('ac'+label+'.ac'))
        actual_frequency = raw.values[raw.sweep_names[0]][0]
        if not math.isclose(actual_frequency, frequency, rel_tol=1e-10):
            raise ValueError('Unexpected capacitor AC frequency')
        result['raw_sha256']['ac'+label] = raw.sha256
        for key, unused in geometries():
            result['cases'][key]['AC'].append(measure_admittance(actual_frequency, raw.values['drive'][0],
                                                               raw.values['VP'+key+':p'][0], raw.values['VN'+key+':p'][0]))
    result['requested_geometries_verified'] = all(card['requested_geometry_matches_saved_CDF'] is True for card in data['cards'].values())
    output = PROJECT/'results/native_capacitor_r5_summary.json'
    if output.exists():
        raise ValueError('Refuse to replace native capacitor summary')
    atomic_json(output, result)
    print(json.dumps(result), flush=True)


def self_test():
    # Synthetic three-terminal admittance catches sign/normalization errors:
    # 3fF mutual, 1fF top-to-substrate, complex non-unit drive.
    f, drive = 1e9, complex(.6, .8)
    omega = 2*math.pi*f
    row = measure_admittance(f, drive, drive*complex(0, omega*4e-15), drive*complex(0, omega*3e-15))
    assert math.isclose(row['mutual_effective_C_F'], 3e-15, rel_tol=1e-12)
    assert math.isclose(row['plus_minus_difference_effective_C_F'], 1e-15, rel_tol=1e-12)
    try:
        measure_admittance(f, drive, drive*complex(0, omega*4e-15), -drive*complex(0, omega*3e-15))
    except ValueError:
        pass
    else:
        raise AssertionError('Reversed minus-probe sign was not rejected')
    assert len(fixture_rows()) == 20
    assert all(x[9] == [['m', '1']] for x in fixture_rows() if x[2] == 'mom_cap')
    assert 'p6CapacitorSnapshotR5()' in snapshot_script()
    print(json.dumps({'self_test': 'passed', 'native_CDF_or_simulator_executed': False}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('generate', 'extract', 'self-test'))
    p.add_argument('--input', type=Path)
    p.add_argument('--snapshot', type=Path)
    args = p.parse_args()
    if args.mode == 'generate':
        generate()
    elif args.mode == 'self-test':
        self_test()
    else:
        if args.input is None:
            p.error('--input native netlist required')
        extract(args.input, args.snapshot)
