"""Render native C0 benches with fresh data and physically shifted apertures."""

import copy
from functools import lru_cache
import hashlib
import random
import re

import c0_review as review


T0 = 200e-12
EDGE = 1e-12
STOP_S = 6.5e-9
WARMUP = 128
SCORED_INPUTS = 512
GUARD = 96
SEEDS = {'training': 2026111501, 'payload': 2026111502}
PHASES = (-1, 0, 1)
SKEW_PS = {'zero': 0.0, 'a': review.ENDPOINT_PS, 'b': -review.ENDPOINT_PS}
PULSE = re.compile(r'(?m)^(X(?:CK|KB)[0-7]|B[0-7]_(?:ck|kb)[0-7]V) [^\n]+$')
DELAY = re.compile(r'\bdelay=([^\s]+)')


def symbols(stimulus):
    generator = random.Random(SEEDS[stimulus])
    return [generator.randrange(4) for _ in range(WARMUP + SCORED_INPUTS + GUARD)]


@lru_cache(maxsize=1)
def template():
    frozen = review.pinned_r5()
    r5 = (review.R5/'quiet.scs').read_bytes().decode('ascii')
    controls = {
        case['code']: case for case in review.gm_gmtap_common.build_plan()['cases']
        if case['process']=='tt' and case['group'] in ('divider','codes') and case['drive']=='p'
    }
    pwl_source = review.collect_r5.load_definitions(
        review.R5/'source_dir'/'pam4_integration.py', {'pwl_source'},
        {'T0':T0,'UI':review.UI,'EDGE':EDGE},
    ).pwl_source
    return r5, controls, frozen['training_run']['clock_specification'], pwl_source


@lru_cache(maxsize=16)
def base_deck(code):
    r5, controls, _, _ = template()
    review.common.need(type(code) is int and code in controls, 'Unknown COMMON64 control word')
    deck, _ = review.render('c0_formal_base', 0., code, controls, r5)
    return deck


def shifted_clock_spec(deck, clock_spec, phase):
    offset = phase * review.UI / 8
    names = set()

    def shift(match):
        name = match[1]
        review.common.need(name not in names, 'Duplicate pulse clock: '+name)
        names.add(name)
        line = match[0]
        delay, = DELAY.finditer(line)
        shifted = review.pn_stage.number(delay[1]) + offset
        review.common.need(shifted > 0, 'Clock delay became nonpositive: '+name)
        if not phase:
            return line
        return line[:delay.start(1)] + f'{shifted:.16g}' + line[delay.end(1):]

    output = PULSE.sub(shift,deck)
    expected = {f'X{name}{i}' for name in ('CK','KB') for i in range(8)}
    expected.update(f'B{i}_{name}{j}V' for i in range(8) for name in ('ck','kb') for j in range(8))
    review.common.need(names==expected, 'Primary or secondary clock inventory differs')
    spec = copy.deepcopy(clock_spec)
    for clock in spec['primary_clocks']:
        for key in ('delay','first_rise_midpoint_s','first_fall_midpoint_s'):
            clock[key] += offset
    for clock in spec['secondary_clocks']:
        for key in ('first_open_midpoint_s','first_close_midpoint_s'):
            clock[key] += offset
    spec['stop_s'] = STOP_S
    return output, spec


def fresh_pwl(deck, sequence, skew_ps, source):
    for side, sign in (('p',1),('m',-1)):
        name = 'PAM4V'+side
        begin, end, *_ = review.pn_stage.pwl_block(deck,name)
        first_line = deck.rfind(b'\n',0,begin)+1
        lines = source(name,'PAM4_src_'+side,sequence,sign,sign*skew_ps*1e-12/2)
        replacement = '\n'.join(lines).encode('ascii')
        deck = deck[:first_line] + replacement + deck[end+1:]
        *_, times, _ = review.pn_stage.pwl_block(deck,name)
        review.common.need(times[-1]>STOP_S, 'PWL guard does not extend past transient stop')
    return deck


def render(condition, code, phase, stimulus):
    review.common.need(condition in SKEW_PS and stimulus in SEEDS, 'Unknown condition or stimulus')
    review.common.need(type(phase) is int and phase in PHASES, 'Unknown common aperture offset')
    _, _, original_spec, source = template()
    deck, spec = shifted_clock_spec(base_deck(code),original_spec,phase)
    deck, count = re.subn(r'(?m)^(tranResponse tran stop=)[^\s]+',
                         lambda match: match[1]+f'{STOP_S:.16g}',deck)
    review.common.need(count==1, 'Expected one native transient statement')
    data = fresh_pwl(deck.encode('ascii'),symbols(stimulus),SKEW_PS[condition],source)
    code_tag = ('m' if code<0 else 'p')+f'{abs(code):02d}'
    phase_tag = ('m' if phase<0 else 'p')+str(abs(phase))
    case_id = f'c0f_{stimulus}_{condition}_c{code_tag}_ph{phase_tag}'
    return data, dict(clock_spec=spec,stop_s=STOP_S,case_id=case_id,
                      deck_sha256=hashlib.sha256(data).hexdigest(),condition=condition,
                      code=code,phase=phase,stimulus=stimulus)
