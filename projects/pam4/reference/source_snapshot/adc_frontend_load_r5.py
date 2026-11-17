#!/usr/bin/env python3
"""Actual r3 AFE plus small-geometry r5 ADC input loading, Python 3.6.

All eight buffer banks and 64 reset comparator loads. Four primary tracks,
four holds, one secondary track per bank: an artificial frozen state.
This diagnoses AFE loading/static power, not clocked conversion or ADC ENOB.
"""
import argparse
import copy
import hashlib
import json
import math
import re
from pathlib import Path

import adc_comparator_probe as a
import adc_comparator_r5 as cmp
import adc_frontend_load_r4 as old
import adc_isolation_r5 as interface
import native_geometry_r5 as ng

PROJECT = a.PROJECT
NAME = 'adc_frontend_load_r5_20261013'
BARE_REFERENCE_H56 = .1892565127


def remap_nodes(lines, mapping):
    """Exact identifier substitution: never replace node-name substrings."""
    pattern = re.compile(r'(?<![A-Za-z0-9_])('+'|'.join(re.escape(x) for x in sorted(mapping,key=len,reverse=True))+r')(?![A-Za-z0-9_])')
    return [pattern.sub(lambda match: mapping[match.group(1)],line) for line in lines]


def make_deck(frontend, cfg, comparator, loaded=True):
    fc = copy.deepcopy(frontend)
    cap, copies = (cfg['primary_cap_F'],cfg['primary_switch_copies']) if loaded else (5e-15,1)
    if loaded and cfg['primary_switch_width_m'] != 3e-6:
        raise ValueError('Shared primary sampler helper is explicitly native3um')
    fc.update(ch=cap,vdd=.9)
    previous = a.b.sampler
    try:
        a.b.sampler = lambda c,t,clocked=False,cap=None: old.primary_sampler(c,t,copies,clocked,cap)
        body, saves = a.b.circuit(fc,'X',cap=cap)
    finally:
        a.b.sampler = previous
    lines = a.b.header(temp=25)+[
        '// r5 actual r3 AFE, frozen 4 primary tracks /4holds; not clocked ADC.']+body
    if loaded:
        lines += ['VBANK (bankvdd 0) vsource dc=.9',
                  'VNBIAS (nbias 0) vsource dc=%.15g' % cfg['n_bias_V'],
                  'VPBIAS (pbias 0) vsource dc=%.15g' % cfg['p_bias_V'],
                  'VCOMP (compvdd 0) vsource dc=.9',
                  'VLOGIC (logicvdd 0) vsource dc=.9',
                  'subckt COMPLOAD (inp inn avdd bvdd)']
        lines += cmp.sized_strongarm(cmp.candidates()[comparator],ng.mos,inp='inp',inn='inn',clk='0')
        lines += ['CBX (bx 0) capacitor c=1f','CBY (by 0) capacitor c=1f','ends COMPLOAD']
        saves += ['VBANK:p','VNBIAS:p','VPBIAS:p','VCOMP:p','VLOGIC:p']
        for bank in range(8):
            tag = 'B%d_' % bank
            for side in ('p','m'):
                temporary = []
                out, mid = interface.buffer(temporary,tag,side,cfg)
                # Primary held nodes are the actual native AFE nodes, not ideal
                # copies. All bank identifiers are unique at the top level.
                mapping = {tag+'m'+side:'X_h%d%s' % (bank,side),tag+'supply':'bankvdd'}
                lines += remap_nodes(temporary,mapping)
                saves += [out,mid]
                for lane in range(8):
                    hold = tag+'h%d%s' % (lane,side)
                    ck,kb = ('bankvdd','0') if lane==0 else ('0','bankvdd')
                    lines += [ng.mos(tag+'SN%d%s' % (lane,side),hold,ck,out,'0',w=cfg['secondary_switch_width_m']),
                              ng.mos(tag+'SP%d%s' % (lane,side),hold,kb,out,'bankvdd',pmos=True,w=cfg['secondary_switch_width_m']),
                              '%sCH%d%s (%s 0) capacitor c=%.15g' % (tag,lane,side,hold,cfg['secondary_cap_F']),
                              '%sRH%d%s (%s %s) resistor r=1T' % (tag,lane,side,hold,out)]
                    if lane in (0,1): saves.append(hold)
            if cfg['buffer_kind']=='cml':
                lines.append('%sRDEG (%sep %sem) resistor r=%.15g' % (tag,tag,tag,cfg['degeneration_ohm']))
            for lane in range(8):
                lines.append('%sCOMP%d (%sh%dp %sh%dm compvdd logicvdd) COMPLOAD' % (tag,lane,tag,lane,tag,lane))
    lines += ['saveOptions options save=selected currents=selected','save '+' '.join(dict.fromkeys(saves)),
              'dcOp dc','acResponse ac start=100M stop=150G dec=60',
              'noisePrimary (X_h0p X_h0m) noise start=1M stop=150G dec=40 iprobe=XVin']
    if loaded:
        lines.append('noiseSecondary (B0_h0p B0_h0m) noise start=1M stop=150G dec=40 iprobe=XVin')
    return lines


def metrics(directory,loaded):
    result = old.metrics(directory,loaded,'reset')
    power = result['DC_power']
    power['all_eight_buffer_banks_W'] = power.pop('all_eight_CML_buffer_banks_W')
    h56 = result['transfer']['primary_track_lane0']['H56GHz']['magnitude_VV']
    result['primary_H56GHz_change_vs_historical_r3_bare_dB'] = 20*math.log10(h56/BARE_REFERENCE_H56)
    result['historical_r3_bare_H56GHz_reference_VV'] = BARE_REFERENCE_H56
    if not loaded:
        result['baseline_H56GHz_relative_error_vs_verified_r3'] = abs(h56-BARE_REFERENCE_H56)/BARE_REFERENCE_H56
    if loaded:
        dc = a.parse_file(directory/'raw/dcOp.dc')
        for item in result['DC_per_bank']:
            bank = item['bank']
            item['buffer_intermediate_common_mode_V'] = (dc.values['B%d_ep' % bank][0]+dc.values['B%d_em' % bank][0])/2
    result['secondary_H56_interpretation'] = ('A diagnostic transfer of the artificial frozen circuit only; '
                                              'backend is after demultiplexing and secondary H56 is not a pass/fail criterion.')
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case',required=True)
    p.add_argument('--preset',required=True,choices=['bare']+sorted(interface.presets()))
    p.add_argument('--comparator',default='in100_tail3',choices=sorted(cmp.candidates()))
    p.add_argument('--config',type=Path,default=PROJECT/'configs/ctle_selected_r3.json')
    p.add_argument('--cards',type=Path,default=ng.CARD_PATH)
    p.add_argument('--run',action='store_true')
    args = p.parse_args()
    if not args.case.replace('_','').isalnum(): p.error('Safe case name required')
    if not (PROJECT/'.codex_project6_owned').exists(): raise ValueError('Project marker absent')
    fc = json.loads(args.config.read_text())
    required = ('nc','nv','rc','rv','vb','cm','rdeg','rdeg2','cdeg','cdeg2')
    if not isinstance(fc,dict) or any(x not in fc for x in required) or fc.get('arch','cml')!='cml':
        raise ValueError('Require selected flat r3 CML configuration')
    native = ng.install(args.cards)
    loaded = args.preset != 'bare'
    cfg = interface.presets()[args.preset] if loaded else {}
    lines = make_deck(fc,cfg,args.comparator,loaded)
    directory = PROJECT/'runs'/NAME/args.case
    if directory.exists(): raise ValueError('Refuse to overwrite existing case')
    directory.mkdir(parents=True)
    deck = '\n'.join(lines)+'\n'
    (directory/'bench.scs').write_text(deck)
    result = dict(case=args.case,preset=args.preset,status='generated_only',
                  selected_r3_configuration=fc,interface_configuration=cfg,
                  eight_buffer_banks_present=loaded,reset_comparator_count=64 if loaded else 0,
                  comparator_candidate=args.comparator,comparator_widths_um=cmp.candidates()[args.comparator],
                  native_geometry_metadata=native,native_cards_sha256=a.digest(args.cards),
                  config_sha256=a.digest(args.config),script_sha256=a.digest(__file__),
                  interface_script_sha256=a.digest(interface.__file__),
                  comparator_script_sha256=a.digest(cmp.__file__),geometry_script_sha256=a.digest(ng.__file__),
                  r4_metrics_script_sha256=a.digest(old.__file__),
                  deck_sha256=hashlib.sha256(deck.encode()).hexdigest())
    result['scope'] = 'Actual r3 AFE, all8 frozen primary/buffer banks, all64 secondary/reset comparator loads.'
    result['assumptions'] = [
        'TT25C0.9V. Four primary lanes track/four hold. One secondary tracks/seven hold in every bank.',
        'This is an artificial frozen phase, not a simultaneous phase of the real interleaved clock sequence.',
        'Held-node DC points settle through 1T leakage resistors and contain no sampled history.',
        'All64 comparators remain reset; no conversion energy or evaluation kickback is measured.',
        'Buffer circuit and sizes reuse the transient r5 candidate exactly; its finite50ohm surrogate source is removed here.',
        'Primary H56 is AFE-input-to-primary-tracking-node gain, normalized to1V differential AFE input.',
        'Secondary H56 is a frozen diagnostic, never a pass/fail criterion for the demultiplexed backend.',
        'Frozen small-signal output noise excludes sampling aliasing and actual decision noise.',
        'Static VDD power includes all8 banks and all64 reset comparators/outputinverters, excludes clock/bias generators, reference/CDAC/SAR and DSP.',
        'Ideal capacitors/wiring; CDF native MOS parasitics retained; no PEX/PVT/mismatch proof.']
    a.atomic_json(directory/'summary.json',result)
    if args.run:
        result['run_status'] = a.b.run(directory,lines,timeout=300)
        if result['run_status']['exit_code'] != 0:
            result['status'] = 'simulation_failed'
            a.atomic_json(directory/'summary.json',result)
            raise RuntimeError('Frozen loading simulation failed')
        result.update(status='complete',metrics=metrics(directory,loaded))
        a.atomic_json(directory/'summary.json',result)
    print(json.dumps({key:result[key] for key in ('case','status','metrics') if key in result}),flush=True)


if __name__ == '__main__':
    main()
