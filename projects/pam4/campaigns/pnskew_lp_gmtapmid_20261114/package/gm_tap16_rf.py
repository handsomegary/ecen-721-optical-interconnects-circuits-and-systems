"""Render 16 native MOS tail half-fingers on the unchanged coarse3 RF banks."""

import math
import re

import drive_summary
import gm_tap_rf as legacy
import olympus_common as common
from recover_bias import validate_save_currents


BASE = legacy.BASE
ANCHORS = (6, 11, 16)
TAIL_UNITS = 16

# Local saved/reopened r5 nominal CDF references, N LVT, L=60 nm, nf=1.
# W=1 um: squares=.289519. W=2 um: squares=.144730.
# The exact 1.5 um CDF card is unavailable. The single-finger diffusion
# rules match the archived 0.24/0.5/1/2/3 um cards. Interpolate access
# conductance (rather than access resistance) between 1 and 2 um.
HALF_ACCESS_SQUARES = 2 / (1 / .289519 + 1 / .144730)
HALF_GEOMETRY = {
    'w': ('3u', '1.5u'),
    'ad': ('2.25e-13', '1.125e-13'),
    'as': ('2.25e-13', '1.125e-13'),
    'pd': ('6.15u', '3.15u'),
    'ps': ('6.15u', '3.15u'),
    'nrd': ('0.096480', f'{HALF_ACCESS_SQUARES:.9f}'),
    'nrs': ('0.096480', f'{HALF_ACCESS_SQUARES:.9f}'),
}
CONTROL_TEMPLATE = re.compile(
    r'(?P<tag>GMSK\d{2})(?P<stem>VE|IN|IP|BN|BP|BD|BR)(?P<cell>[0-7]) (?P<rest>.*)'
)
TAIL_TEMPLATE = re.compile(
    r'(?P<tag>GMSK\d{2})(?P<stem>[PM]T)(?P<cell>[0-7]) (?P<rest>.*)'
)


def states(case):
    """Validate the current map and return ordered tap-to-half-finger counts."""
    taps, weights = case['anchors'], case['weights']
    common.need(len(taps)==len(weights) and tuple(taps)==tuple(sorted(set(taps))) and
                all(type(tap) is int and tap in ANCHORS for tap in taps),
                'Invalid coarse3 anchor set')
    common.need(all(type(w) is int and 0<=w<=TAIL_UNITS for w in weights) and
                sum(weights)==TAIL_UNITS,'Exactly sixteen half-tail units must be enabled')
    active = [tap for tap,w in zip(taps,weights) if w]
    common.need(len(active)==1 or (len(active)==2 and 11 in active),
                'Only adjacent coarse3 banks may interpolate')
    if case.get('group')=='oracle' or case.get('variant_name')=='oracle':
        common.need(list(taps)==active,'Minimal-load oracle must only retain enabled banks')
    else:
        common.need(tuple(taps)==ANCHORS,'Physical coarse3 always retains three RF banks')
    common.need(case.get('match_load',False) is False,'Fine16 retains no launch matching shunt')
    return dict(zip(taps,weights))


def half_geometry(line):
    """Keep physical MOS model and stress flags, recalculating single-finger geometry."""
    common.need(' nmos_lvt l=60n ' in line and ' multi=1 nf=1 sd=100n ' in line,
                'Unexpected native tail template')
    for key,(old,new) in HALF_GEOMETRY.items():
        line = BASE.replace_once(line, f' {key}={old} ', f' {key}={new} ')
    return line


def expand_half_fingers(deck, rails, counts, supply):
    """Expand all bank tail devices and their independent native enable circuits."""
    previous_rails = {f'GMSK{tap:02d}VE{i}:p' for tap in counts for i in range(8)}
    common.need(previous_rails <= rails.keys(),'Missing inherited tail enable rail')
    for name in previous_rails:
        del rails[name]
    existing = {}
    lines = []
    for line in deck.splitlines():
        control = CONTROL_TEMPLATE.fullmatch(line)
        tail = TAIL_TEMPLATE.fullmatch(line)
        if control is None and tail is None:
            lines.append(line)
            continue
        m = control or tail
        tag, stem, original, rest = m.group('tag','stem','cell','rest')
        anchor = int(tag[-2:])
        common.need(anchor in counts,'Unexpected tail-bank anchor in template')
        existing[anchor] = existing.get(anchor,0)+1
        for half in (2*int(original),2*int(original)+1):
            nodes = re.sub(rf'\b{tag}(EN|EB|VB){original}\b',
                           lambda k: f'{tag}{k[1]}{half}',rest)
            name = f'{tag}{stem}{half}'
            item = name+' '+nodes
            if stem=='VE':
                voltage = supply if half<counts[anchor] else 0.
                item = re.sub(r' dc=\S+$',f' dc={voltage:.9g}',item)
                rails[name+':p'] = voltage
            if tail is not None:
                item = half_geometry(item)
            lines.append(item)
    common.need(existing=={tap:72 for tap in counts},
                'Expected eight tail devices per leg plus seven native enable elements per cell')
    return '\n'.join(lines)+'\n'


def render(case, model_root):
    if case.get('resolution')!=TAIL_UNITS:
        return legacy.render(case,model_root)
    counts = states(case)
    # The seed deck supplies the fixed-wire hardware using a valid integer
    # eight-tail state. Tail/enable rows are then rebuilt entirely from counts.
    taps = case['anchors']
    active = [tap for tap in taps if counts[tap]]
    first = active[0]
    seed = {first:8}
    if len(active)==2:
        seed[first] = min(7,max(1,counts[first]//2))
        seed[active[1]] = 8-seed[first]
    parent_state = dict(case,weights=[seed.get(tap,0) for tap in taps])
    deck,rails,ac,dc,currents,_ = legacy.render(parent_state,model_root)
    deck = expand_half_fingers(deck,rails,counts,case['vdd_V'])
    dc.extend(f'GMSK{tap:02d}VB{i}' for tap in taps for i in range(8,TAIL_UNITS))
    save = re.search(r'(?m)^save PNC_PREP [^\n]+$',deck)
    common.need(save is not None,'Missing native save list')
    deck = BASE.replace_once(deck,save.group(),'save '+' '.join(dict.fromkeys(ac+dc+currents+list(rails))))
    validate_save_currents(deck,dict(AC_traces=ac,DC_nodes=dc,DC_currents=currents,rail_voltages_V=rails))
    parent,_ = BASE.load_inputs()
    return deck,rails,ac,dc,currents,BASE.unified(parent.replace(BASE.MODEL_TOKEN,model_root),deck)


def headroom(case, record, deck):
    """Audit all conducting half-tail MOS and original RF input devices."""
    if case.get('resolution')!=TAIL_UNITS:
        return legacy.headroom(case,record,deck)
    original = re.sub(r'(?m)^GMSK\d{2}\w+ [^\n]+\n','',deck)
    report = drive_summary.headroom(case,record,original)
    for anchor,weight in states(case).items():
        for leg in 'PM':
            for kind,size in (('M',legacy.TAIL_UNITS if weight else 0),('T',weight)):
                for i in range(size):
                    name = f'GMSK{anchor:02d}{leg}{kind}{i}'
                    op = record['saved_mos_oppoint'].get(name,{})
                    common.need(all(isinstance(op.get(k),(float,int)) and math.isfinite(op[k])
                                    for k in ('vds','vdsat','ids','gm')),
                                'Incomplete active fine16 OP: '+name)
                    report[name] = {'role':'AFE_input_active_bank' if kind=='M' else 'AFE_tail_enabled',
                                    'margin_V':op['vds']-abs(op['vdsat']),
                                    'region':op.get('region'),'ids_A':op['ids'],'gm_S':op['gm'],
                                    'vgs_V':op.get('vgs'),'vbs_V':op.get('vbs'),
                                    'vds_V':op['vds'],'vdsat_V':op['vdsat']}
    return report
