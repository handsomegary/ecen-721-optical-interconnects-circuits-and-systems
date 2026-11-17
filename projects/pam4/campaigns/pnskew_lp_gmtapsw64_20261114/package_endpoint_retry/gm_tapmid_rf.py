"""Render Trim32 with a resistive Vb1 derived from the existing Vb2 rail."""

import gm_taptrim as trim
import gm_taptrim_rf
import olympus_common as common
from recover_bias import validate_save_currents


BASE = gm_taptrim_rf.BASE
DIVIDERS = {'divider': (1000, 57000), 'divider_lowz': (250, 14250)}
headroom = gm_taptrim_rf.headroom


def render(case, model_root):
    """Use the original Trim32 fixture or replace only its ideal Vb1 supply."""
    kind = case.get('bias_kind', 'ideal')
    common.need(kind in ('ideal', *DIVIDERS), 'Unknown first-stage tail bias circuit')
    deck, rails, ac, dc, currents, diff = trim.render(case, model_root)
    if kind == 'ideal':
        return deck, rails, ac, dc, currents, diff

    common.need(case.get('vb1_V') == .570 and rails.get('GMSKV1:p') == .570 and
                rails.get('XVb:p') == .580 and 'GMSKVBIAS' in dc,
                'Divider requires the nominal 570 mV Trim32 source and 580 mV Vb2 rail')
    upper, lower = DIVIDERS[kind]
    divider = '\n'.join((
        'GMSKVDIV (X_vb GMSKVDIVIN) vsource dc=0',
        f'GMSKVRU (GMSKVDIVIN GMSKV1RAW) resistor r={upper}',
        f'GMSKVRD (GMSKV1RAW 0) resistor r={lower}',
        'GMSKV1 (GMSKV1RAW GMSKVBIAS) vsource dc=0',
        'GMSKVC1 (GMSKVBIAS 0) capacitor c=2p',
    ))
    deck = BASE.replace_once(deck, 'GMSKV1 (GMSKVBIAS 0) vsource dc=0.57', divider)
    # Both sense sources are oriented for positive load current. All delivered
    # power is booked at XVb, including the bias divider's own standing loss.
    del rails['GMSKV1:p']
    currents.extend(('GMSKVDIV:p', 'GMSKV1:p'))
    deck = BASE.replace_once(deck, ' GMSKV1:p\n', ' GMSKV1:p GMSKVDIV:p\n')
    validate_save_currents(deck, {'AC_traces': ac, 'DC_nodes': dc, 'DC_currents': currents,
                                  'rail_voltages_V': rails})
    parent, _ = BASE.load_inputs()
    diff = BASE.unified(parent.replace(BASE.MODEL_TOKEN, model_root), deck)
    return deck, rails, ac, dc, currents, diff
