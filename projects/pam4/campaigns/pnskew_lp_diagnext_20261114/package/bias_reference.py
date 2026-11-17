"""Derive the LP_BIAS reference current from its hash-bound DC branch."""
import math
import re

import olympus_common as common

VNUM = r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?'


def reference_current(deck, record, report):
    def unique(pattern):
        rows = re.findall(pattern,deck,re.M)
        common.need(len(rows)==1,'Reference branch topology differs')
        return float(rows[0])
    supply = unique(r'^GFVDD \(GF_VDD 0\) vsource dc=('+VNUM+r')$')
    resistance = unique(r'^GMSRRREF \(GF_VDD GMSR_REF\) resistor r=('+VNUM+r')$')
    programmed = unique(r'^GMSRIREF \(GMSR_REF 0\) isource dc=('+VNUM+r')$')
    expected = record['target_mA_per_leg']*1e-3/14
    common.need(supply==record['rail_voltages_V']['GFVDD:p']==record['vdd_V'] and resistance==462 and
                math.isclose(programmed,expected,rel_tol=1e-10),'Reference source settings differ')
    voltage = report['DC_voltage_V']['GMSR_REF']
    inferred = (supply-voltage)/resistance
    common.need(math.isfinite(inferred) and inferred>0 and
                math.isclose(inferred,programmed,rel_tol=1e-4,abs_tol=1e-8),
                'Reference current disagrees with the programmed value')
    return {'programmed_A':programmed,'recovered_A':inferred,
            'source':'(GFVDD_DC - V(GMSR_REF)) / 462 ohm'}
