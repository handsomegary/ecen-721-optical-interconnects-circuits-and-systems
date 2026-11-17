"""Render a coarse3 tail array with a hardware 1/64 centre increment."""

import math
import re

import drive_summary
import gm_taptrim_rf as trim
import olympus_common as common
from recover_bias import validate_save_currents


BASE = trim.BASE
ANCHORS = trim.ANCHORS
CONTROL_COUNT = 18

# Same-L single-finger archived CDF cards at W=0.24/0.50 um bracket
# W=0.375 um. Interpolate access conductance; the exact CDF is unavailable.
EIGHTH_POSITION = (.375-.24)/(.50-.24)
EIGHTH_ACCESS = 1/((1-EIGHTH_POSITION)/1.326151+EIGHTH_POSITION/.662935)
EIGHTH_GEOMETRY = {
    'w': ('0.75u','375n'),
    'ad': ('5.625e-14','2.8125e-14'),
    'as': ('5.625e-14','2.8125e-14'),
    'pd': ('1.65u','900n'),
    'ps': ('1.65u','900n'),
    'nrd': (f'{trim.QUARTER_ACCESS_SQUARES:.9f}',f'{EIGHTH_ACCESS:.9f}'),
    'nrs': (f'{trim.QUARTER_ACCESS_SQUARES:.9f}',f'{EIGHTH_ACCESS:.9f}'),
}
FINE_CELLS = ((),(16,),(15,),(15,16),(15,16,17))


def active_cells(eighth_units):
    """Decode 15 halves, one quarter and two eighth-size fingers."""
    common.need(type(eighth_units) is int and 0<=eighth_units<=64,
                'Eighth-unit weight must be in 0..64')
    halves = min(eighth_units//4,15)
    return (*range(halves),*FINE_CELLS[eighth_units-4*halves])


def split_states(case):
    anchors,weights = case['anchors'],case['weights']
    common.need(tuple(anchors)==tuple(sorted(set(anchors))) and len(anchors)==len(weights) and
                all(type(a) is int and a in ANCHORS for a in anchors),'Invalid coarse3 anchors')
    active = {a:active_cells(q) for a,q in zip(anchors,weights)}
    common.need(sum(weights)==64, 'Exactly 64 eighth-units of nominal width must be selected')
    conducting = [a for a,indices in active.items() if indices]
    common.need(len(conducting)==1 or len(conducting)==2 and 11 in conducting,
                'Only adjacent banks may interpolate')
    if case['group']=='oracle':
        common.need(list(anchors)==conducting,'Minimal-load oracle retains conducting banks only')
    else:
        common.need(tuple(anchors)==ANCHORS,'Physical coarse3 must retain all three banks')
    common.need(case.get('match_load',False) is False,'Centre64 retains no launch shunt')
    return active


def eighth_geometry(line):
    common.need(' nmos_lvt l=60n ' in line and ' multi=1 nf=1 sd=100n ' in line,
                'Unexpected quarter-tail template')
    for key,(old,new) in EIGHTH_GEOMETRY.items():
        line = BASE.replace_once(line,f' {key}={old} ',f' {key}={new} ')
    return line


def rebuild_split(deck,rails,active,supply):
    rows,inventory = [],{}
    for line in deck.splitlines():
        control,tail = trim.CONTROL_ROW.fullmatch(line),trim.TAIL_ROW.fullmatch(line)
        match = control or tail
        if match is None:
            rows.append(line)
            continue
        tag,stem,suffix,rest = match.group('tag','stem','cell','rest')
        bank,cell = int(tag[-2:]),int(suffix)
        inventory[bank] = inventory.get(bank,0)+1
        for index in (16,17) if cell==16 else (cell,):
            name = f'{tag}{stem}{index}'
            nodes = re.sub(rf'\b{tag}(EN|EB|VB){cell}\b',lambda m:f'{tag}{m[1]}{index}',rest)
            row = name+' '+nodes
            if stem=='VE':
                voltage = supply if index in active[bank] else 0.
                row = re.sub(r' dc=\S+$',f' dc={voltage:.9g}',row)
                rails[name+':p'] = voltage
            if tail is not None and cell==16:
                row = eighth_geometry(row)
            rows.append(row)
    common.need(inventory=={bank:153 for bank in active},'Unexpected Trim32 control/tail inventory')
    return '\n'.join(rows)+'\n'


def render(case,model_root):
    if case.get('resolution')!=64:
        return trim.render(case,model_root)
    common.need(case.get('tail_variant')=='split64' and 'vb1_V' in case,
                'Centre64 requires the split64 physical array and explicit Vb1')
    active = split_states(case)
    # The seed only constructs the static topology. Rebuild all enable values
    # from the 64-way code below, including the duplicated eighth-size cell.
    seed_weights = [max(1,q//2) if q else 0 for q in case['weights']]
    last = max(i for i,q in enumerate(seed_weights) if q)
    seed_weights[last] += 32-sum(seed_weights)
    seed = dict(case,resolution=32,tail_variant='split32',weights=seed_weights)
    deck,rails,ac,dc,currents,_ = trim.render(seed,model_root)
    deck = rebuild_split(deck,rails,active,case['vdd_V'])
    dc.extend(f'GMSK{bank:02d}VB17' for bank in active)
    save = re.search(r'(?m)^save PNC_PREP [^\n]+$',deck)
    common.need(save is not None,'Missing native save list')
    deck = BASE.replace_once(deck,save.group(),'save '+' '.join(dict.fromkeys(ac+dc+currents+list(rails))))
    validate_save_currents(deck,dict(AC_traces=ac,DC_nodes=dc,DC_currents=currents,rail_voltages_V=rails))
    parent,_ = BASE.load_inputs()
    return deck,rails,ac,dc,currents,BASE.unified(parent.replace(BASE.MODEL_TOKEN,model_root),deck)


def headroom(case,record,deck):
    """Audit physically conducting fingers without altering inherited XT2 OP."""
    if case.get('resolution')!=64:
        return trim.headroom(case,record,deck)
    original = re.sub(r'(?m)^GMSK\d{2}\w+ [^\n]+\n','',deck)
    report = drive_summary.headroom(case,record,original)
    for anchor,indices in split_states(case).items():
        if not indices:
            continue
        for leg in 'PM':
            for kind,devices in (('M',range(8)),('T',indices)):
                for index in devices:
                    name = f'GMSK{anchor:02d}{leg}{kind}{index}'
                    op = record['saved_mos_oppoint'].get(name,{})
                    common.need(all(type(op.get(k)) in (int,float) and math.isfinite(op[k])
                                    for k in ('vds','vdsat','ids','gm')),
                                'Incomplete active Centre64 OP: '+name)
                    report[name] = {'role':'AFE_input_active_bank' if kind=='M' else 'AFE_tail_enabled',
                                    'margin_V':op['vds']-abs(op['vdsat']),
                                    'region':op.get('region'),'ids_A':op['ids'],'gm_S':op['gm'],
                                    'vgs_V':op.get('vgs'),'vbs_V':op.get('vbs'),
                                    'vds_V':op['vds'],'vdsat_V':op['vdsat']}
    return report
