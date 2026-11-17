"""Render the reviewable AFE input trim circuit. No simulation is launched here."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'native'))
import admit
import pn_stage
from pvt import model_preflight

AC_SHA = 'a5608d0445047bde7211f365d0b56c38a6d42dd73b29d639ec85180c94046c28'
R5_SHA = 'c9f576a9dbfb1afd6f8fdcb39a52039329231c3696bed01368c335c49b35e6d3'
MODEL_TOKEN = '__pdk_root__'
NEW_NODES = ('PNC_PREP', 'PNC_PREN', 'X_ip', 'X_im')
CAP_WEIGHTS_FF = (1.25, 2.5, 5., 10., 20., 40.)
INDUCTANCE_PH = 65.
FIXED_CAP_FF = 12.
INDUCTOR_SERIES_OHM = 1.5
UI = 1.0 / 112e9


def pin_read(path, digest):
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != digest:
        raise ValueError('Unexpected parent SHA: ' + str(path))
    return payload.decode('ascii')


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Expected exactly one parent token: ' + old[:90])
    return text.replace(old, new, 1)


def device_cards(parent):
    cards = {}
    for label, name, primitive in (('N', 'B0_SN0p', 'nmos_lvt'),
                                   ('P', 'B0_SP0p', 'pmos_lvt')):
        match = re.search(r'^' + name + r' \([^\n]*?\) (' + primitive +
                          r' l=30n w=1u multi=1 nf=1 [^\n]+)$', parent, re.M)
        if not match:
            raise ValueError('Missing exact original geometry card: ' + name)
        cards[label] = match.group(1)
    return cards


def trim_lines(p_code, n_code, cards, vdd, source_ohm, load_fF=0., bypass=False):
    """Each leg uses four L/2-C-L/2 sections and static 6-bit capacitor banks."""
    lines = ['// BEGIN PNC: four symmetric LC sections per leg, static controls']
    if not bypass:
        lines.append('PNCVTRIM (PNC_VDD 0) vsource dc=%.9g' % vdd)
    for leg, code, pre, out in zip(('P', 'N'), (p_code, n_code), NEW_NODES[:2], NEW_NODES[2:]):
        if type(code) is not int or not 0 <= code <= 63:
            raise ValueError('Trim code must be an integer 0 through 63')
        tag = 'PNC' + leg
        if bypass:
            if source_ohm:
                lines.append('%sRS (%s %s) resistor r=%.9g' % (tag, pre, out, source_ohm))
            else:
                lines.append('%sBYP (%s X_cm %s X_cm) vcvs gain=1' % (tag, out, pre))
            if load_fF:
                lines.append('%sCL (%s 0) capacitor c=%.9gf' % (tag, out, load_fF))
            continue
        if source_ohm:
            lines.append('%sRS (%s %sS) resistor r=%.9g' % (tag, pre, tag, source_ohm))
            pre = tag + 'S'
        if load_fF:
            lines.append('%sCL (%s 0) capacitor c=%.9gf' % (tag, out, load_fF))
        for bit in range(6):
            on = bool(code & (1 << bit))
            lines += [
                '%sVN%d (%sGN%d 0) vsource dc=%.9g' % (tag, bit, tag, bit, vdd if on else 0),
                '%sVP%d (%sGP%d 0) vsource dc=%.9g' % (tag, bit, tag, bit, 0 if on else vdd),
            ]
        for section in range(4):
            stem = '%s%d' % (tag, section)
            following = out if section == 3 else stem + 'O'
            lines += [
                '%sLA (%s %sA) inductor l=%.9gp' % (stem, pre, stem, INDUCTANCE_PH / 2),
                '%sRA (%sA %sM) resistor r=%.9g' % (stem, stem, stem, INDUCTOR_SERIES_OHM / 2),
                '%sCF (%sM 0) capacitor c=%.9gf' % (stem, stem, FIXED_CAP_FF),
                '%sLB (%sM %sB) inductor l=%.9gp' % (stem, stem, stem, INDUCTANCE_PH / 2),
                '%sRB (%sB %s) resistor r=%.9g' % (stem, stem, following, INDUCTOR_SERIES_OHM / 2),
            ]
            for bit, cap in enumerate(CAP_WEIGHTS_FF):
                capnode = '%sC%d' % (stem, bit)
                lines += [
                    '%sTN%d (%s %sGN%d %sM 0) %s' % (stem, bit, capnode, tag, bit, stem, cards['N']),
                    '%sTP%d (%s %sGP%d %sM PNC_VDD) %s' % (stem, bit, capnode, tag, bit, stem, cards['P']),
                    '%sCB%d (%s 0) capacitor c=%.9gf' % (stem, bit, capnode, cap),
                    '%sRB%d (%s X_cm) resistor r=1T' % (stem, bit, capnode),
                ]
            pre = following
    return '\n'.join(lines + ['// END PNC', ''])


def ac_deck(parent, cards, case, model_root):
    tt_include = 'include "' + MODEL_TOKEN + '/models/spectre/pdk_toplevel.scs" section=tt'
    process, temp, vdd = (case[k] for k in ('process', 'temperature_C', 'vdd_V'))
    need = admit.require
    need(process in ('tt', 'ss', 'ff') and temp in (-40, 25, 85) and vdd in (.81, .9, .99),
         'Case outside the declared PVT matrix')
    include = (tt_include.replace(MODEL_TOKEN, model_root) if process == 'tt' else
               'include "la5_foundry_corners.scs" section=top_' + process)
    text = replace_once(parent, tt_include, include)
    text = replace_once(text, 'options temp=25 tnom=25', 'options temp=%d tnom=25' % temp)
    text = replace_once(text, 'XVs (X_vdd 0) vsource dc=0.9', 'XVs (X_vdd 0) vsource dc=%.9g' % vdd)
    drive = case['drive']
    need(drive in ('p', 'n'), 'Expected a single driven input for 2x2 extraction')
    p, n = (1, 0) if drive=='p' else (0, 1)
    sources = ('XVin (PNC_PREP X_cm) vsource dc=0 mag=%.9g\n'
               'PNCVN (PNC_PREN X_cm) vsource dc=0 mag=%.9g\n') % (p,n)
    text = replace_once(text, 'XVin (X_ip X_cm) vsource dc=0 mag=0.5\n'
                        'XEin (X_im X_cm X_ip X_cm) vcvs gain=-1\n',
                        sources + trim_lines(case['p_code'], case['n_code'], cards, vdd,
                                             case['source_ohm'], case['load_fF'], case['bypass']))
    save = 'save X_ip X_im X_c_p X_c_m X_o_p X_o_m X_s1_p X_s1_m X_s2_p X_s2_m XVs:p X_h0p X_h0m'
    extra = ' PNC_PREP PNC_PREN XVin:p PNCVN:p'
    if case['source_ohm'] and not case['bypass']:
        extra += ' PNCPS PNCNS'
    if not case['bypass']:
        extra += ' PNCVTRIM:p ' + ' '.join('PNC%sV%s%d:p' % (leg, gate, b)
                                          for leg in 'PN' for gate in 'NP' for b in range(6))
    text = replace_once(text, save, save + extra)
    text = replace_once(text, 'noiseResponse (X_h0p X_h0m) noise',
                        'noiseResponse (X_ip X_im) noise')
    if drive != 'p':
        text = replace_once(text, 'noiseResponse (X_ip X_im) noise start=1M stop=56G dec=40 iprobe=XVin\n', '')
    return text


def tran_deck(original, admission, case, cards):
    """Original integrated r5 fixture, with the same selected-code cell at X_ip/X_im."""
    staged, profile = pn_stage.render_deck(original.encode('ascii'), admission, case['stimulus'])
    parent = staged.decode('ascii')
    stress = case.get('added_differential_stress_ps', 0.)
    if stress:
        admit.require(abs(stress)<=1.25, 'Stress outside the predeclared bounded offset')
        data = staged
        edits = []
        for name,sign in (('PAM4Vp',1),('PAM4Vm',-1)):
            block = pn_stage.pwl_block(data,name)
            shift = sign*stress*1e-12/2
            admit.require(block[4][-1]+abs(shift)<profile['stop_s'], 'Stress exceeds original stop')
            edits.append((block[0],block[1],pn_stage.shifted_body(block,shift)))
        for lo,hi,body in sorted(edits,reverse=True):
            data = data[:lo]+body+data[hi:]
        parent = data.decode('ascii')
    for suffix, pin, pre in (('p', 'X_ip', 'PNC_PREP'), ('m', 'X_im', 'PNC_PREN')):
        parent = replace_once(parent, 'CHB2%s (%s X_cm ' % (suffix, pin),
                              'CHB2%s (%s X_cm ' % (suffix, pre))
    cell = trim_lines(case['p_code'], case['n_code'], cards, case['vdd_V'], 0.)
    parent = replace_once(parent, 'saveOptions options save=selected currents=selected\n',
                          cell + 'saveOptions options save=selected currents=selected\n')
    extra = ' PNC_PREP PNC_PREN PNCVTRIM:p ' + ' '.join(
        'PNC%sV%s%d:p' % (leg, gate, b) for leg in 'PN' for gate in 'NP' for b in range(6))
    match = re.search(r'^save X_o_p X_o_m X_ip X_im[^\n]+$', parent, re.M)
    admit.require(match is not None, 'Expected original r5 save line')
    parent = replace_once(parent, match.group(), match.group() + extra)
    return original, parent, profile


def pilot_deck(original, admission, case, cards):
    """Use the original TX PWL prefix and early independent windows only."""
    parent, deck, profile = tran_deck(original, admission, case, cards)
    stop = 200e-12 + (128 + 4*224 + 8)*UI
    analysis = re.search(r'^tranResponse tran stop=([^ ]+) [^\n]+$', deck, re.M)
    admit.require(analysis is not None and 'noisefmax' not in analysis.group(),
                  'Pilot uses the admitted quiet stimulus')
    deck = replace_once(deck, analysis.group(), 'tranResponse tran stop=%.17g maxstep=200f '
                        'errpreset=conservative strobeperiod=%.17g strobeoutput=strobeonly' % (stop, UI/32))
    save = re.search(r'^save X_o_p X_o_m X_ip X_im[^\n]+$', deck, re.M)
    deck = replace_once(deck, save.group(), 'save X_ip X_im')
    for name in ('PAM4Vp', 'PAM4Vm'):
        data = deck.encode('ascii')
        begin, end, body, tokens, times, _ = pn_stage.pwl_block(data, name)
        beyond = next(i for i, t in enumerate(times) if t > stop)
        deck = (data[:begin] + body[:tokens[2*beyond+1].end()] + b' ' + data[end:]).decode('ascii')
    return parent, deck, dict(profile, pilot_stop_s=stop)


def unified(parent, child):
    return ''.join(difflib.unified_diff(parent.splitlines(keepends=True),
                                       child.splitlines(keepends=True), 'parent.scs', 'bench.scs'))


def load_inputs():
    return (pin_read(ROOT / 'pvt/cases/nominal_parent.scs.txt', AC_SHA),
            pin_read(ROOT / 'r5_original/quiet.scs', R5_SHA))


def stage_ac(case, destination, model_path=None):
    parent, r5 = load_inputs()
    wrapper, proof = None, None
    process = case['process']
    if model_path is not None:
        if process == 'tt':
            proof = model_preflight.verify_private_kit(model_path, 'tt')
        else:
            wrapper, proof = model_preflight.stage_corner(process, model_path)
        model_root = proof['model_root']
    else:
        model_root = MODEL_TOKEN
        if process != 'tt':
            wrapper = (ROOT / 'pvt/reference/la5_foundry_corners.scs').read_bytes()
    bench = ac_deck(parent, device_cards(r5), case, model_root)
    destination.mkdir()
    for name, contents in [('bench.scs', bench.encode('ascii')),
                           ('parent_diff.txt', unified(parent.replace(MODEL_TOKEN, model_root), bench).encode('ascii'))]:
        (destination / name).write_bytes(contents)
    if wrapper is not None:
        (destination / 'la5_foundry_corners.scs').write_bytes(wrapper)
    sources = {p.name: admit.sha256_file(p) for p in destination.iterdir()}
    admit.write_new_json(destination / 'case.json',
                         dict(case, staged_source_sha256=sources, model_preflight=proof))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan', type=Path, required=True)
    p.add_argument('--case-index', type=int, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--model-root', type=Path, help='Use existing Olympus private kit. Omit for portable review.')
    args = p.parse_args()
    plan = admit.read_json(args.plan)
    admit.require(0 <= args.case_index < len(plan['cases']), 'Case index outside plan')
    stage_ac(plan['cases'][args.case_index], args.out, args.model_root)


if __name__ == '__main__':
    main()
