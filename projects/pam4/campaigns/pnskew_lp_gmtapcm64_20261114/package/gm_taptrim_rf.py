"""Render a separately biased coarse3 tail array with an optional split end cell."""

import math
import re

import drive_summary
import gm_tap16_rf as fine
import olympus_common as common
from recover_bias import validate_save_currents


BASE = fine.BASE
ANCHORS = fine.ANCHORS

# Archived single-finger N LVT, L=60 nm, W=0.5/1 µm CDF geometries give
# .662935/.289519 access squares. Interpolate conductance at W=0.75 µm.
# This is a schematic estimate. Replace with the exact CDF card when available.
QUARTER_ACCESS_SQUARES = 2/(1/.662935+1/.289519)
QUARTER_GEOMETRY = {
    'w': ('1.5u','0.75u'),
    'ad': ('1.125e-13','5.625e-14'),
    'as': ('1.125e-13','5.625e-14'),
    'pd': ('3.15u','1.65u'),
    'ps': ('3.15u','1.65u'),
    'nrd': (f'{fine.HALF_ACCESS_SQUARES:.9f}',f'{QUARTER_ACCESS_SQUARES:.9f}'),
    'nrs': (f'{fine.HALF_ACCESS_SQUARES:.9f}',f'{QUARTER_ACCESS_SQUARES:.9f}'),
}
CONTROL_ROW = re.compile(r'(?P<tag>GMSK\d{2})(?P<stem>VE|IN|IP|BN|BP|BD|BR)(?P<cell>\d+) (?P<rest>.*)')
TAIL_ROW = re.compile(r'(?P<tag>GMSK\d{2})(?P<stem>[PM]T)(?P<cell>\d+) (?P<rest>.*)')


def active_cells(quarter_units):
    """Return 1.5-um cell indices 0–14 and 0.75-um indices 15–16."""
    common.need(type(quarter_units) is int and 0<=quarter_units<=32,
                'Quarter-unit weight must be in 0..32')
    halves = tuple(range(min(quarter_units//2,15)))
    if quarter_units==32:
        return (*halves,15,16)
    return (*halves,15) if quarter_units%2 else halves


def split_states(case):
    anchors,weights = case['anchors'],case['weights']
    common.need(tuple(anchors)==tuple(sorted(set(anchors))) and len(anchors)==len(weights) and
                all(type(a) is int and a in ANCHORS for a in anchors),'Invalid coarse3 anchors')
    active = {anchor:active_cells(weight) for anchor,weight in zip(anchors,weights)}
    common.need(sum(weights)==32,'Exactly 32 quarter-units of nominal width must be selected')
    conducting = [anchor for anchor,indices in active.items() if indices]
    common.need(len(conducting)==1 or len(conducting)==2 and 11 in conducting,
                'Only adjacent banks may interpolate')
    if case['group']=='oracle':
        common.need(list(anchors)==conducting,'Minimal-load oracle retains conducting banks only')
    else:
        common.need(tuple(anchors)==ANCHORS,'Physical coarse3 must retain all three banks')
    common.need(case.get('match_load',False) is False,'Trim32 retains no launch shunt')
    return active


def quarter_geometry(line):
    common.need(' nmos_lvt l=60n ' in line and ' multi=1 nf=1 sd=100n ' in line,
                'Unexpected half-tail template')
    for key,(old,new) in QUARTER_GEOMETRY.items():
        line = BASE.replace_once(line,f' {key}={old} ',f' {key}={new} ')
    return line


def rebuild_split(deck,rails,active,supply):
    rows,inventory = [],{}
    for line in deck.splitlines():
        control,tail = CONTROL_ROW.fullmatch(line),TAIL_ROW.fullmatch(line)
        m = control or tail
        if m is None:
            rows.append(line)
            continue
        tag,stem,suffix,rest = m.group('tag','stem','cell','rest')
        bank = int(tag[-2:])
        cell = int(suffix)
        inventory[bank] = inventory.get(bank,0)+1
        for new in (15,16) if cell==15 else (cell,):
            name = f'{tag}{stem}{new}'
            nodes = re.sub(rf'\b{tag}(EN|EB|VB){cell}\b',lambda k:f'{tag}{k[1]}{new}',rest)
            row = name+' '+nodes
            if stem=='VE':
                voltage = supply if new in active[bank] else 0.
                row = re.sub(r' dc=\S+$',f' dc={voltage:.9g}',row)
                rails[name+':p'] = voltage
            if tail is not None and cell==15:
                row = quarter_geometry(row)
            rows.append(row)
    common.need(inventory=={bank:144 for bank in active},'Unexpected Fine16 per-bank control/tail inventory')
    return '\n'.join(rows)+'\n'


def separate_bias(deck,rails,ac,dc,currents,case,control_count):
    voltage = case['vb1_V']
    common.need(type(voltage) in (int,float) and math.isfinite(voltage) and 0<voltage<case['vdd_V'],
                'Invalid independent first-stage bias')
    pattern = re.compile(r'(?m)^(GMSK\d{2}B[NP]\d+ \(GMSK\d{2}VB\d+ GMSK\d{2}E[NB]\d+ )X_vb( [^\n]+)$')
    deck,count = pattern.subn(r'\g<1>GMSKVBIAS\g<2>',deck)
    common.need(count==2*control_count*len(case['anchors']),'Unexpected first-stage bias wiring')
    source = f'GMSKV1 (GMSKVBIAS 0) vsource dc={voltage:.9g}'
    deck = BASE.replace_once(deck,'// END GMFINE',source+'\n// END GMFINE')
    common.need('XVb (X_vb 0) vsource dc=0.58\n' in deck,'Original Vb2 must remain 0.580 V')
    rails['GMSKV1:p'] = voltage
    dc.append('GMSKVBIAS')
    save = re.search(r'(?m)^save PNC_PREP [^\n]+$',deck)
    common.need(save is not None,'Missing native save list')
    deck = BASE.replace_once(deck,save.group(),'save '+' '.join(dict.fromkeys(ac+dc+currents+list(rails))))
    validate_save_currents(deck,dict(AC_traces=ac,DC_nodes=dc,DC_currents=currents,rail_voltages_V=rails))
    return deck


def render(case,model_root):
    resolution = case.get('resolution')
    variant = case.get('tail_variant')
    if 'vb1_V' not in case:
        common.need(resolution!=32,'Split32 requires explicit tail geometry and Vb1')
        return fine.render(case,model_root)
    common.need((resolution,variant) in {(16,'half16'),(32,'split32')},
                'Inconsistent static tail resolution and physical array')
    if resolution==32:
        active = split_states(case)
        seeds = [min(15,max(1,w//2)) if w else 0 for w in case['weights']]
        enabled = [i for i,w in enumerate(seeds) if w]
        seeds[enabled[-1]] += 16-sum(seeds)
        seed = dict(case,resolution=16,weights=seeds)
    else:
        seed = case
    deck,rails,ac,dc,currents,_ = fine.render(seed,model_root)
    if resolution==32:
        deck = rebuild_split(deck,rails,active,case['vdd_V'])
        dc.extend(f'GMSK{bank:02d}VB16' for bank in active)
    deck = separate_bias(deck,rails,ac,dc,currents,case,17 if resolution==32 else 16)
    parent,_ = BASE.load_inputs()
    return deck,rails,ac,dc,currents,BASE.unified(parent.replace(BASE.MODEL_TOKEN,model_root),deck)


def headroom(case,record,deck):
    """Audit 17-cell arrays by physical active index and retain legacy XT2 OP."""
    if case.get('resolution')!=32:
        return fine.headroom(case,record,deck)
    original = re.sub(r'(?m)^GMSK\d{2}\w+ [^\n]+\n','',deck)
    report = drive_summary.headroom(case,record,original)
    for anchor,indices in split_states(case).items():
        if not indices:
            continue
        for leg in 'PM':
            for kind,devices in (('M',range(8)),('T',indices)):
                for i in devices:
                    name = f'GMSK{anchor:02d}{leg}{kind}{i}'
                    op = record['saved_mos_oppoint'].get(name,{})
                    common.need(all(type(op.get(k)) in (int,float) and math.isfinite(op[k])
                                    for k in ('vds','vdsat','ids','gm')),
                                'Incomplete active Trim32 OP: '+name)
                    report[name] = {'role':'AFE_input_active_bank' if kind=='M' else 'AFE_tail_enabled',
                                    'margin_V':op['vds']-abs(op['vdsat']),
                                    'region':op.get('region'),'ids_A':op['ids'],'gm_S':op['gm'],
                                    'vgs_V':op.get('vgs'),'vbs_V':op.get('vbs'),
                                    'vds_V':op['vds'],'vdsat_V':op['vdsat']}
    return report
