"""Generate quiet Split64 switching fixtures using the physical Vb1 network."""
import math
import re

import gm_center64
import gm_center64_rf
import lp_diagnostics as diagnostics
import olympus_common as common


BASE = diagnostics.BASE
UI = diagnostics.UI
EDGE_S = 1e-12
MAXSTEP_S = .5e-12
WORD = diagnostics.WORD[:16]
BANKS = (6, 11, 16)
ENABLE = re.compile(
    r"(?m)^(GMSK(06|11|16)VE(\d+) \(GMSK\2EN\3 0\) vsource dc=)([^\s]+)$"
)
TAIL_CURRENTS = tuple(f"GMSK{anchor:02d}{leg}VT:p" for anchor in BANKS for leg in "PM")
CONTROL_NODES = ('GF_VDD','GMSKVBIAS','X_vb','GMSKVDIV:p','GMSKV1:p')
HELD_NODES = tuple(f"X_h{i}{leg}" for i in range(8) for leg in "pm")
CLOCK_NODES = tuple(f"X_ck{i}" for i in range(8))
XT2_TRACES = tuple(f"{name}:{term}" for name in diagnostics.TAILS
                   for term in ('vds','vdsat','region'))
OUTPUT_NODES = ('TX_p','TX_m','PNC_PREP','PNC_PREN','X_c_p','X_c_m','X_o_p','X_o_m',
                'X_s2_p','X_s2_m')
TRACES = CONTROL_NODES+TAIL_CURRENTS+OUTPUT_NODES+HELD_NODES+CLOCK_NODES+XT2_TRACES


def timing(case):
    event, slew, offset, stop = (
        case['switch_time_s'], case['slew_s'], case.get('offset_s',0.), case['stop_s']
    )
    common.need(all(type(v) in (int,float) and math.isfinite(v) for v in (event,slew,offset,stop))
                and event>64*UI and slew>0 and offset>=0 and stop>event+offset+slew+64*UI,
                'Invalid switch and recovery times')
    return event, slew, offset, stop


def active_by_bank(code):
    common.need(type(code) is int and abs(code)<=60,'Unexpected Split64 dynamic code')
    weights = gm_center64.distribution(code,64)
    return {bank:set(gm_center64_rf.active_cells(weight)) for bank,weight in zip(BANKS,weights)}


def enable_lines(deck, case):
    start, slew, offset, _ = timing(case)
    before, after = (active_by_bank(case[key]) for key in ('initial_code','final_code'))
    changed = []
    seen = set()
    vdd = case['vdd_V']

    def replace(match):
        stem, bank, index, voltage = match.groups()
        bank, index = int(bank), int(index)
        seen.add((bank,index))
        was_on, now_on = index in before[bank], index in after[bank]
        old, new = vdd*was_on, vdd*now_on
        common.need(float(voltage)==old,'Initial physical enable voltage disagrees with the old code')
        if was_on==now_on:
            return match[0]
        edge = start+offset if now_on else start
        changed.append(f'GMSK{bank:02d}EN{index}')
        return f'{stem}{old:.12g} type=pwl wave=[0 {old:.12g} {edge:.16g} {old:.12g} {edge+slew:.16g} {new:.12g}]'

    deck = ENABLE.sub(replace,deck)
    expected = {(bank,index) for bank in BANKS for index in range(18)}
    common.need(seen==expected and len(changed)==sum(len(before[bank]^after[bank]) for bank in BANKS),
                'Unexpected bank-enable inventory')
    return deck, tuple(changed)


def stimulus(case, leg):
    """P/N edges shift by +skew/2 and -skew/2 respectively."""
    _,_,_,stop = timing(case)
    skew = case.get('skew_ps',0.)
    amplitude = case.get('amplitude_Vppd',.4)
    common.need(type(skew) in (float,int) and math.isfinite(skew) and abs(skew)<=.5*UI*1e12+1e-9,
                'Input skew exceeds the supported ±0.5 UI')
    common.need(amplitude in (.2,.4),'Unsupported dynamic swing')
    sign = {'p':1,'m':-1}[leg]
    shift = sign*skew*1e-12/2
    levels = tuple(sign*amplitude*level/4 for level in (-1.,-1/3,1/3,1.))
    points = [(0.,0.)]
    prior = 0.
    symbols = math.ceil((stop+abs(shift))/UI)+1
    for i in range(16,symbols):
        value = levels[WORD[(i-16)%len(WORD)]]
        if value!=prior:
            edge = i*UI+shift
            points.extend(((edge,prior),(edge+EDGE_S,value)))
            prior = value
    return points


def channel_sources(deck,case):
    for leg,source,pre in (('p','XVin','PNC_PREP'),('m','PNCVN','PNC_PREN')):
        pattern = rf'(?m)^{source} \({pre} X_cm\) vsource [^\n]+$'
        old = re.search(pattern,deck)
        common.need(old is not None,'Missing input source '+source)
        rows = [f'{source} (TX_{leg} X_cm) vsource dc=0 type=pwl wave=[ \\']
        rows.extend(f' {t:.16g} {v:.12g} \\' for t,v in stimulus(case,leg))
        rows.extend((
            ' ]',
            f'XTCH1{leg} (TX_{leg} TXA_{leg}) resistor r=100',
            f'XTCC1{leg} (TXA_{leg} X_cm) capacitor c=85.26157665637249f',
            f'XTCB1{leg} (TXB_{leg} X_cm TXA_{leg} X_cm) vcvs gain=1',
            f'XTCH2{leg} (TXB_{leg} TXC_{leg}) resistor r=100',
            f'XTCC2{leg} (TXC_{leg} X_cm) capacitor c=85.26157665637249f',
            f'XTCB2{leg} ({pre} X_cm TXC_{leg} X_cm) vcvs gain=1',
        ))
        deck = BASE.replace_once(deck,old[0],'\n'.join(rows))
    return deck


def primary_clocks(deck,r5,vdd):
    clocks = []
    for index in range(8):
        for name in (f'XCK{index}',f'XKB{index}'):
            row = re.search(rf'(?m)^{name} [^\n]+$',r5)
            common.need(row is not None and len(re.findall(r'\bval[01]=0\.9\b',row[0]))==1,
                        'Expected a native r5 clock '+name)
            clocks.append(re.sub(r'(?<=\=)0\.9(?=\s)',f'{vdd:.12g}',row[0],count=1))
        for leg in 'pm':
            for prefix,new_gate in (('XSN',f'X_ck{index}'),('XSP',f'X_kb{index}')):
                match = re.search(rf'(?m)^{prefix}{index}{leg} \(X_h{index}{leg} (?:0|X_vdd) ',deck)
                common.need(match is not None,'Missing static primary gate')
                new = f'{prefix}{index}{leg} (X_h{index}{leg} {new_gate} '
                deck = BASE.replace_once(deck,match[0],new)
    return BASE.replace_once(deck,'saveOptions options','\n'.join(clocks)+'\nsaveOptions options')


def render(case,model_root):
    _,_,_,stop = timing(case)
    common.need(case['code']==case['initial_code'] and case['resolution']==64
                and case['bias_kind']=='divider_lowz' and case['tail_variant']=='split64'
                and case['vb1_V']==.565 and tuple(case['anchors'])==BANKS
                and tuple(case['weights'])==gm_center64.distribution(case['initial_code'],64),
                'Expected the selected physical Split64 topology and old code')
    deck,_,_,_,_,_ = gm_center64.render(case,model_root)
    deck,count = re.subn(r'(?m)^(?:acResponse|noiseResponse) [^\n]+\n','',deck)
    common.need(count in (1,2),'Unexpected AC testbench analyses')
    parent,r5 = BASE.load_inputs()
    deck,changed = enable_lines(deck,case)
    deck = primary_clocks(channel_sources(deck,case),r5,case['vdd_V'])
    deck = diagnostics.replace_save(deck,(*TRACES,*changed))
    deck += f'codeSwitch tran stop={stop:.16g} maxstep={MAXSTEP_S:.12g} errpreset=conservative\n'
    diff = BASE.unified(parent.replace(BASE.MODEL_TOKEN,model_root),deck)
    return deck,{},[],[],[],diff
