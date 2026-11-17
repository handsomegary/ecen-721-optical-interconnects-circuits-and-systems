"""Render the LP14 differential through-line with complementary tap selection."""

import re

import ac_next
import lp_integrate as integrated
import olympus_common as common
from recover_bias import validate_save_currents


BASE = integrated.BASE
TAPS = range(6,17)


def tap_node(leg, tap):
    return f'GL{leg}T{tap:02d}'


def through_line(leg, matched):
    tag = 'GL'+leg
    rows = [f'{tag}DRV (GMSH{leg}L {tag}I) vsource dc=0',
            f'{tag}RT ({tap_node(leg,16)} X_cm) resistor r=50']
    if matched:
        rows.append(f'{tag}MATCH ({tag}I X_cm) resistor r=50')
    previous = tag+'I'
    # Same 50-ohm sections as the fixed-route LP14 benches.
    for i in range(1,17):
        cell = f'{tag}S{i:02d}'
        end = tap_node(leg,i)
        rows.extend((f'{cell}LA ({previous} {cell}A) inductor l=13p',
                     f'{cell}RA ({cell}A {cell}M) resistor r=0.1525',
                     f'{cell}C ({cell}M 0) capacitor c=10.4f',
                     f'{cell}LB ({cell}M {cell}B) inductor l=13p',
                     f'{cell}RB ({cell}B {end}) resistor r=0.1525'))
        previous = end
    return rows


def selection(case):
    selected = {(bank,leg):case[f'tap_{bank.lower()}_{port}']
                for bank in 'AB' for leg,port in (('P','p'),('M','n'))}
    for bank,parity in (('A',0),('B',1)):
        p,m = selected[bank,'P'],selected[bank,'M']
        common.need(type(p) is int and type(m) is int and p in TAPS and m in TAPS
                    and p%2==parity and p+m==22,'Invalid complementary bank tap')
    common.need(abs(selected['A','P']-selected['B','P'])==1,'Bank taps must be adjacent')
    common.need(type(case['count_b']) is int and 0<=case['count_b']<=8,'Invalid bank weight')
    return selected


def switches(case, selected, cards, rails):
    native = case['switch_mode']=='native'
    rows = []
    if native:
        copies = case.get('tg_parallel',1)
        common.need(type(copies) is int and copies in (1,2,4),'Invalid parallel TG size')
        for tap in TAPS:
            prefix = f'GLSEL{tap:02d}'
            voltage = case['vdd_V'] if tap in (selected['A','P'],selected['B','P']) else 0.
            rows.append(f'{prefix}V ({prefix}N 0) vsource dc={voltage:.9g}')
            rows.extend((f'{prefix}IN ({prefix}P {prefix}N 0 0) {cards["N"]}',
                         f'{prefix}IP ({prefix}P {prefix}N GF_VDD GF_VDD) {cards["P"]}'))
            rails[prefix+'V:p'] = voltage
    for (bank,leg), tap in selected.items():
        name = 'GMS'+bank+leg
        # The sense source remains the original input probe. Its input and the
        # bank's RF gates retain a DC return even during an all-off transition.
        rows.extend((f'{name}DRV ({name}L {name}G) vsource dc=0',
                     f'{name}TAPBIAS ({name}G X_cm) resistor r=100K'))
        if not native:
            rows.append(f'GL{bank}{leg}SHORT ({tap_node(leg,tap)} {name}L) vsource dc=0')
            continue
        for physical in TAPS:
            if physical%2 != tap%2:
                continue
            # A single select bit and physical inverter drive both complementary
            # P/N switches. All unselected TGs stay present with native parasitics.
            logical = physical if leg=='P' else 22-physical
            ctrl = f'GLSEL{logical:02d}'
            source = tap_node(leg,physical)
            for unit in range(copies):
                name_tg = f'GL{bank}{leg}{physical:02d}U{unit}'
                rows.extend((f'{name_tg}N ({source} {ctrl}N {name}L 0) {cards["N"]}',
                             f'{name_tg}P ({source} {ctrl}P {name}L GF_VDD) {cards["P"]}'))
    return rows


def render(case, model_root):
    deck,rails,ac,dc,currents,diff = integrated.render(case,model_root)
    if case['variant_name']=='r3':
        return deck,rails,ac,dc,currents,diff
    common.need(case['switch_mode'] in ('native','ideal'),'Unknown RF switch mode')
    common.need(case['integration']=='native_direct' and case['topology']=='shared',
                'Expected shared native-bias LP14')
    selected = selection(case)
    parent,r5 = BASE.load_inputs()
    rows = []
    for leg in 'PM':
        rows.extend(through_line(leg,case.get('match_load',False)))
        ac.extend([f'GL{leg}DRV:p',f'GL{leg}I',f'GMSH{leg}L'])
        ac.extend(tap_node(leg,i) for i in TAPS)
    rows.extend(switches(case,selected,ac_next.switch_cards(r5),rails))
    for bank,leg in selected:
        prefix = 'GMS'+bank+leg
        pattern = rf'(?m)^{prefix}(?:DRV|RS|RT|\d{{2}}(?:LA|RA|C|LB|RB)) [^\n]+\n'
        deck,count = re.subn(pattern,'',deck)
        common.need(count>=8 and (count-3)%5==0,'Unexpected fixed-route ladder '+prefix)
        # The predecessor synthesizes this weak drain/source leak only for an
        # idle bank. Install it on both banks so the physical netlist is fixed.
        deck = re.sub(rf'(?m)^{prefix}BLEED [^\n]+\n','',deck)
        rows.append(f'{prefix}BLEED ({prefix}S {prefix}D) resistor r=100G')
        ac.remove(prefix+'I')
    deck = BASE.replace_once(deck,'// END GMFINE','\n'.join(rows)+'\n// END GMFINE')
    save = re.search(r'(?m)^save PNC_PREP [^\n]+$',deck)
    common.need(save is not None,'Missing global RF save list')
    record = dict(AC_traces=ac,DC_nodes=dc,DC_currents=currents,rail_voltages_V=rails)
    deck = BASE.replace_once(deck,save.group(),'save '+' '.join(dict.fromkeys(ac+dc+currents+list(rails))))
    validate_save_currents(deck,record)
    return deck,rails,ac,dc,currents,BASE.unified(parent.replace(BASE.MODEL_TOKEN,model_root),deck)
