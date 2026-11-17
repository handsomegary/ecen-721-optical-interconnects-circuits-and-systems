"""Render hardwired 50-ohm tap banks with native tail-only selection."""

import math
import re

import drive_summary
import global_rf
import lp_integrate as integrated
import olympus_common as common
from recover_bias import validate_save_currents


BASE = integrated.BASE
ANCHORS = (6, 8, 10, 11, 12, 14, 16)
TAIL_UNITS = 8
OLD_BANK = re.compile(r'(?m)^GMS[AB]\w+ [^\n]+\n')
RETAINED_UNIT = re.compile(r'GMSA(?:(?:VE|IN|IP|BN|BP|BD|BR)[0-7]|'
                           r'[PM](?:(?:M|T)[0-7]|VD|VT)|RD|CD)$')


def banks(case):
    anchors, weights = case['anchors'], case['weights']
    common.need(all(type(k) is int and k in ANCHORS for k in anchors) and
                list(anchors)==sorted(set(anchors)) and len(anchors)==len(weights),
                'Invalid tap sequence')
    common.need(all(type(k) is int and 0<=k<=TAIL_UNITS for k in weights) and
                sum(weights)==TAIL_UNITS,'Exactly eight tail units must be enabled')
    active = [i for i,k in enumerate(weights) if k]
    common.need(len(active)==1 or len(active)==2 and active[-1]-active[0]==1,
                'Only adjacent banks may interpolate')
    if case.get('group')=='oracle' or case.get('variant_name')=='oracle':
        common.need(len(anchors)==len(active),'Loading oracle may only retain enabled banks')
    else:
        common.need({6,11,16}<=set(anchors) and len(anchors) in (3,5,7) and
                    {22-k for k in anchors}==set(anchors),
                    'Native bank families must have symmetric anchor sets')
    return zip(anchors,weights)


def bank_rows(template, anchor, weight, case, rails, ac, dc, currents):
    tag = f'GMSK{anchor:02d}'
    rows = []
    for line in template:
        line = line.replace('GMSA',tag)
        match = re.fullmatch(rf'({tag}VE([0-7])) \(({tag}EN\d) 0\) vsource dc=\S+',line)
        if match:
            device, unit, gate = match.groups()
            voltage = case['vdd_V'] if int(unit)<weight else 0.
            line = f'{device} ({gate} 0) vsource dc={voltage:.9g}'
            rails[device+':p'] = voltage
        rows.append(line)
    for leg,tap in (('P',anchor),('M',22-anchor)):
        name = tag+leg
        rows.extend((f'{name}DRV ({global_rf.tap_node(leg,tap)} {name}G) vsource dc=0',
                     f'{name}BLEED ({name}S {name}D) resistor r=100G'))
        ac.extend((name+'G',name+'S',name+'DRV:p',name+'VD:p'))
        dc.extend((name+'G',name+'S',name+'D'))
        currents.extend((name+'VD:p',name+'VT:p'))
    dc.extend(f'{tag}VB{i}' for i in range(TAIL_UNITS))
    return rows


def render(case, model_root):
    deck,rails,ac,dc,currents,diff = integrated.render(case,model_root)
    if case['variant_name']=='r3' or 'anchors' not in case:
        return deck,rails,ac,dc,currents,diff
    common.need(case['integration']=='native_direct' and case['topology']=='shared',
                'Expected shared LP14 with original physical bias')
    template = [line.rstrip('\n') for line in OLD_BANK.findall(deck)
                if RETAINED_UNIT.fullmatch(line.split(' ',1)[0])]
    device_names = {line.split(' ',1)[0] for line in template}
    common.need(len(template)==len(device_names)==94,'Native input bank template inventory differs')
    deck = OLD_BANK.sub('',deck)
    rails = {key:value for key,value in rails.items() if not key.startswith(('GMSA','GMSB'))}
    ac,dc,currents = [[name for name in values if not name.startswith(('GMSA','GMSB'))]
                      for values in (ac,dc,currents)]
    rows = []
    for leg in 'PM':
        rows.extend(global_rf.through_line(leg,case.get('match_load',False)))
        ac.extend((f'GL{leg}DRV:p',f'GL{leg}I',f'GMSH{leg}L'))
        ac.extend(global_rf.tap_node(leg,i) for i in global_rf.TAPS)
    for anchor,weight in banks(case):
        rows.extend(bank_rows(template,anchor,weight,case,rails,ac,dc,currents))
    deck = BASE.replace_once(deck,'// END GMFINE','\n'.join(rows)+'\n// END GMFINE')
    save = re.search(r'(?m)^save PNC_PREP [^\n]+$',deck)
    common.need(save is not None,'Missing native save list')
    deck = BASE.replace_once(deck,save.group(),'save '+' '.join(dict.fromkeys(ac+dc+currents+list(rails))))
    validate_save_currents(deck,dict(AC_traces=ac,DC_nodes=dc,DC_currents=currents,rail_voltages_V=rails))
    parent,_ = BASE.load_inputs()
    return deck,rails,ac,dc,currents,BASE.unified(parent.replace(BASE.MODEL_TOKEN,model_root),deck)


def headroom(case, record, deck):
    """Retain original stage-2/LP14 OP and include active native tap banks."""
    original = re.sub(r'(?m)^GMSK\d{2}\w+ [^\n]+\n','',deck)
    report = drive_summary.headroom(case,record,original)
    for anchor,weight in zip(case.get('anchors',[]),case.get('weights',[])):
        for leg in 'PM':
            for kind,size in (('M',TAIL_UNITS if weight else 0),('T',weight)):
                for unit in range(size):
                    name = f'GMSK{anchor:02d}{leg}{kind}{unit}'
                    current = record['saved_mos_oppoint'].get(name,{})
                    common.need(all(isinstance(current.get(k),(int,float)) and math.isfinite(current[k])
                                    for k in ('vds','vdsat','ids','gm')),
                                'Incomplete active tap bank OP: '+name)
                    report[name] = {'role':'AFE_input_active_bank' if kind=='M' else 'AFE_tail_enabled',
                                    'margin_V':current['vds']-abs(current['vdsat']),
                                    'region':current.get('region'),'ids_A':current['ids'],'gm_S':current['gm']}
    return report
