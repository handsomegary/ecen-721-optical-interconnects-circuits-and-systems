#!/usr/bin/env python3
"""Small native-geometry physical ADC-interface screen, Python 3.6.

One 14GHz master, eight 1.75GHz secondary holds, only branch 0 comparator.
Finite 50-ohm source is a surrogate; this is not a complete receiver or ADC.
Generate-only by default. Native cards and all raw traces stay on the VM.
"""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path

import adc_comparator_probe as a
import adc_isolation_r4 as r4
import native_geometry_r5 as ng

P, SUPER, TRACK = r4.P, r4.SUPER, r4.TRACK
SECOND_OFF, LAUNCH, EVAL = r4.SECOND_OFF, r4.LAUNCH, r4.EVAL
GROUPS, WARMUP, TARGET_LSB = r4.GROUPS, r4.WARMUP, r4.TARGET_LSB
HELD_SIGN_BAND_V = 10e-6


def presets():
    common = dict(vdd_V=.9, primary_switch_width_m=3e-6,
                  primary_switch_copies=1, primary_cap_F=5e-15,
                  secondary_cap_F=10e-15, secondary_switch_width_m=.5e-6,
                  source_resistance_per_side_ohm=50., noise_seed=None,
                  n_bias_V=.5, p_bias_V=.4)
    result = {}
    for name, settings in [
        ('cml_w1_m5_s10', dict(buffer_kind='cml', buffer_width_m=1e-6,
                              current_width_m=1e-6, load_ohm=1000., degeneration_ohm=250.)),
        ('cml_w2_m5_s10', dict(buffer_kind='cml', buffer_width_m=2e-6,
                              current_width_m=2e-6, load_ohm=500., degeneration_ohm=250.)),
        ('follower_w1_m5_s10', dict(buffer_kind='follower', buffer_width_m=1e-6,
                                   current_width_m=.5e-6)),
        ('follower_w2_m10_s10', dict(buffer_kind='follower', buffer_width_m=2e-6,
                                    current_width_m=1e-6, primary_cap_F=10e-15,
                                    secondary_switch_width_m=1e-6)),
        ('follower_w2_m25_s25', dict(buffer_kind='follower', buffer_width_m=2e-6,
                                    current_width_m=1e-6, primary_cap_F=25e-15,
                                    secondary_cap_F=25e-15, secondary_switch_width_m=1e-6))]:
        cfg = copy.deepcopy(common)
        cfg.update(settings)
        cfg['nominal_polarity'] = -1 if cfg['buffer_kind'] == 'cml' else 1
        result[name] = cfg
    return result


def buffer(lines, tag, side, cfg):
    """Real CML or N-follower/P-follower; no ideal signal gain element."""
    master, out, mid = tag+'m'+side, tag+'f'+side, tag+'e'+side
    supply, width, current = tag+'supply', cfg['buffer_width_m'], cfg['current_width_m']
    if cfg['buffer_kind'] == 'cml':
        lines += ['R%sL%s (%s %s) resistor r=%.15g' % (tag, side, supply, out, cfg['load_ohm']),
                  ng.mos(tag+'F'+side, out, master, mid, '0', w=width),
                  ng.mos(tag+'T'+side, mid, 'nbias', '0', '0', w=current, l=60e-9)]
    else:
        # First stage lowers CM; second restores it. Bodies remain tied to rails.
        # Both stages have MOS current biases, whose VDD currents are measured.
        lines += [ng.mos(tag+'NF'+side, supply, master, mid, '0', w=width),
                  ng.mos(tag+'NS'+side, mid, 'nbias', '0', '0', w=current, l=60e-9),
                  ng.mos(tag+'PF'+side, '0', mid, out, supply, pmos=True, w=width),
                  ng.mos(tag+'PS'+side, out, 'pbias', supply, supply, pmos=True,
                         w=current, l=60e-9)]
    return out, mid


def comparator_lines(candidate):
    """Adapter to the shared r5 comparator generator; candidate never auto-changes."""
    import adc_comparator_r5 as cmp
    if candidate not in cmp.candidates():
        raise ValueError('Unknown fixed comparator candidate: '+candidate)
    return cmp.sized_strongarm(cmp.candidates()[candidate], ng.mos, inp='dh0p', inn='dh0n')


def build(cfg):
    vdd = cfg['vdd_V']
    stop = a.T0 + (GROUPS*8+8)*P
    changes = [(a.T0+q*P+2e-12, r4.stimulus(q)) for q in range(GROUPS*8+1)]
    sigp = a.pwl(cfg['input_cm_V'], [(t,cfg['input_cm_V']+d/2) for t,d in changes], stop)
    sign = a.pwl(cfg['input_cm_V'], [(t,cfg['input_cm_V']-d/2) for t,d in changes], stop)
    lines = a.b.header(temp=25) + [
        '// r5 small native geometry physical interface; only branch 0 comparator.',
        'VSP (srcp 0) vsource type=pwl wave='+a.wave(sigp),
        'VSN (srcn 0) vsource type=pwl wave='+a.wave(sign),
        'VA (avdd 0) vsource dc=%.15g' % vdd,
        'VB (bvdd 0) vsource dc=%.15g' % vdd,
        'VNBIAS (nbias 0) vsource dc=%.15g' % cfg['n_bias_V'],
        'VPBIAS (pbias 0) vsource dc=%.15g' % cfg['p_bias_V']]
    saves = ['srcp','srcn','VA:p','VB:p','VNBIAS:p','VPBIAS:p']
    changes = []
    for q in range(GROUPS*8+8):
        changes += [(a.T0+q*P,vdd), (a.T0+q*P+TRACK,0.)]
    r4.clock(lines, saves, 'm', changes, stop, vdd)
    for lane in range(8):
        changes = []
        for group in range(GROUPS+1):
            start = a.T0+(group*8+lane)*P
            if start+SECOND_OFF+a.EDGE/2 < stop:
                changes += [(start+2e-12,vdd),(start+SECOND_OFF,0.)]
        r4.clock(lines, saves, 's'+str(lane), changes, stop, vdd)
    # b=bare master; r=matched buffer+bank without comparator; d=DUT.
    for tag in ('b','r','d'):
        supply = tag+'supply'
        lines.append('V%sDD (%s 0) vsource dc=%.15g' % (tag,supply,vdd))
        saves.append('V'+tag+'DD:p')
        for side in ('p','n'):
            master, upstream = tag+'m'+side, tag+'i'+side
            lines += ['R%s%s (src%s %s) resistor r=%.15g' % (tag,side,side,upstream,cfg['source_resistance_per_side_ohm']),
                      'C%sM%s (%s 0) capacitor c=%.15g' % (tag,side,master,cfg['primary_cap_F']),
                      'R%sM%s (%s %s) resistor r=1T' % (tag,side,master,upstream)]
            for index in range(cfg['primary_switch_copies']):
                lines += [ng.mos(tag+'MN'+side+str(index),master,'mck',upstream,'0',w=cfg['primary_switch_width_m']),
                          ng.mos(tag+'MP'+side+str(index),master,'mkb',upstream,supply,pmos=True,w=cfg['primary_switch_width_m'])]
            saves.append(master)
            if tag == 'b':
                continue
            out, mid = buffer(lines,tag,side,cfg)
            saves += [out,mid]
            for lane in range(8):
                hold = tag+'h'+str(lane)+side
                lines += [ng.mos(tag+'SN'+str(lane)+side,hold,'s'+str(lane)+'ck',out,'0',w=cfg['secondary_switch_width_m']),
                          ng.mos(tag+'SP'+str(lane)+side,hold,'s'+str(lane)+'kb',out,supply,pmos=True,w=cfg['secondary_switch_width_m']),
                          'C%sH%d%s (%s 0) capacitor c=%.15g' % (tag,lane,side,hold,cfg['secondary_cap_F']),
                          'R%sH%d%s (%s %s) resistor r=1T' % (tag,lane,side,hold,out)]
                saves.append(hold)
        if tag != 'b' and cfg['buffer_kind'] == 'cml':
            lines.append('R%sDEG (%sep %sen) resistor r=%.15g' % (tag,tag,tag,cfg['degeneration_ohm']))
    changes = []
    for group in range(GROUPS+1):
        start = a.T0+group*SUPER
        changes += [(start+LAUNCH,vdd), (start+LAUNCH+EVAL+a.EDGE/2+.1e-12,0.)]
    points = a.pwl(0.,changes,stop)
    lines += ['VCMP (cmp 0) vsource type=pwl wave='+a.wave(points)]
    saves += ['cmp','VCMP:p','p','q','x','y','tail','bx','by']
    lines += comparator_lines(cfg['comparator_candidate'])
    lines += ['CBX (bx 0) capacitor c=1f','CBY (by 0) capacitor c=1f']
    noise = '' if cfg.get('noise_seed') is None else ' noisefmax=150G noisefmin=500M noiseseed=%d' % cfg['noise_seed']
    lines += ['saveOptions options save=selected currents=selected','save '+' '.join(saves),
              'tranResponse tran stop=%.15g maxstep=100f outputstart=%.15g errpreset=conservative%s' % (stop,a.T0+(WARMUP-1)*SUPER,noise)]
    return lines


def logic_result(t, values, get, sign, raw, launch, end, vdd):
    if not sign:
        return 'indeterminate_input', None
    hp, lp = ('y','x') if raw else ('bx','by')
    hi, lo = (hp,lp) if sign > 0 else (lp,hp)
    correct = [h >= .8*vdd and l <= .2*vdd for h,l in zip(values[hi],values[lo])]
    wrong = [l >= .8*vdd and h <= .2*vdd for h,l in zip(values[hi],values[lo])]
    ct, wt = a.first_stable(t,correct,launch,end), a.first_stable(t,wrong,launch,end)
    if get(hi,end) < .8*vdd or get(lo,end) > .2*vdd: ct = None
    if get(lo,end) < .8*vdd or get(hi,end) > .2*vdd: wt = None
    return ('correct',ct-launch) if ct is not None else (('wrong',None) if wt is not None else ('unresolved',None))


def analyze(raw, cfg):
    # Inherit the established aperture/power/disturbance calculations, then
    # replace its hardcoded CML-only comparator classifications explicitly.
    rows, summary = r4.analyze(raw,cfg)
    t, v = raw.values[raw.sweep_names[0]], raw.values
    get = lambda node,time: a.interpolate(t,v[node],time)
    launched = a.crossings(t,v['cmp'],cfg['vdd_V']/2,True)
    for row in rows:
        start = a.T0+row['group']*SUPER
        launch = a.near(launched,start+LAUNCH)
        before, end = launch-a.EDGE/2-.1e-12, launch+EVAL
        source = get('srcp',start+TRACK)-get('srcn',start+TRACK)
        held = row['secondary_prelaunch_differential_V']
        source_sign = (1 if source > 0 else (-1 if source < 0 else 0))*cfg['nominal_polarity']
        held_sign = 1 if held > HELD_SIGN_BAND_V else (-1 if held < -HELD_SIGN_BAND_V else 0)
        row.update(source_differential_at_primary_capture_V=source,
                   expected_source_polarity_at_comparator=source_sign,
                   held_prelaunch_polarity=held_sign,
                   held_prelaunch_indeterminate=held_sign==0,
                   source_to_hold_polarity_agrees=source_sign==held_sign,
                   source_primary_capture_time_s=start+TRACK,
                   comparator_prelaunch_sample_time_s=before)
        for label, is_raw in [('raw',True),('buffered',False)]:
            for reference, sign in [('source',source_sign),('held',held_sign)]:
                kind, elapsed = logic_result(t,v,get,sign,is_raw,launch,end,cfg['vdd_V'])
                row[label+'_'+reference+'_classification'] = kind
                row[label+'_'+reference+'_resolution_s'] = elapsed
            # Old aliases are intentionally removed: each classification names
            # its reference and cannot be misreported as comparator-alone error.
            row.pop(label+'_classification',None)
            row.pop(label+'_resolution_s',None)
        for node in ('dep','den','dfp','dfn'):
            unused, values = a.window(t,v[node],start,start+SUPER)
            row[node+'_voltage_range_V'] = [min(values),max(values)]
    for label in ('raw','buffered'):
        summary.pop(label+'_counts',None)
        summary.pop(label+'_resolution_max_s',None)
        for reference in ('source','held'):
            prefix = label+'_'+reference
            summary[prefix+'_counts'] = {kind:sum(row[prefix+'_classification']==kind for row in rows)
                                         for kind in ('correct','wrong','unresolved','indeterminate_input')}
            times = [row[prefix+'_resolution_s'] for row in rows if row[prefix+'_resolution_s'] is not None]
            summary[prefix+'_resolution_max_s'] = max(times) if times else None
    summary['source_to_hold_polarity_agrees_count'] = sum(row['source_to_hold_polarity_agrees'] for row in rows)
    summary['held_prelaunch_indeterminate_count'] = sum(row['held_prelaunch_indeterminate'] for row in rows)
    summary['held_sign_indeterminate_band_V'] = [-HELD_SIGN_BAND_V,HELD_SIGN_BAND_V]
    summary['voltage_ranges_V'] = {node:[min(row[node+'_voltage_range_V'][0] for row in rows),
                                        max(row[node+'_voltage_range_V'][1] for row in rows)]
                                   for node in ('dep','den','dfp','dfn')}
    summary['interpretation'] = ('Source agreement measures the entire surrogate acquisition path; held agreement compares '
                                 'the latch output with prelaunch held voltage. Neither is BER, offset, or ENOB validation.')
    return rows,summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case',required=True)
    p.add_argument('--preset',choices=sorted(presets()),required=True)
    p.add_argument('--comparator',default='in100_tail3')
    p.add_argument('--cards',type=Path,default=ng.CARD_PATH)
    p.add_argument('--noise-seed',type=int)
    p.add_argument('--run',action='store_true')
    args = p.parse_args()
    if not args.case.replace('_','').isalnum(): p.error('Safe case name required')
    if args.noise_seed is not None and not 1 <= args.noise_seed <= 2147483647:
        p.error('Noise seed must be a positive 32-bit integer')
    if not (a.PROJECT/'.codex_project6_owned').exists(): raise ValueError('Project marker absent')
    baseline_path = a.PROJECT/'runs/adc_comparator_r3_tt/comparator_probe_summary.json'
    baseline = json.loads(baseline_path.read_text())
    native = ng.install(args.cards)
    cfg = presets()[args.preset]
    cfg.update(input_cm_V=baseline['configuration']['common_mode_V'], noise_seed=args.noise_seed,
               comparator_candidate=args.comparator)
    lines = build(cfg)
    directory = a.PROJECT/'runs/adc_isolation_r5_20261013'/args.case
    if directory.exists(): raise ValueError('Refuse to overwrite an existing case')
    directory.mkdir(parents=True)
    deck = '\n'.join(lines)+'\n'
    (directory/'bench.scs').write_text(deck)
    import adc_comparator_r5 as cmp
    result = dict(case=args.case,preset=args.preset,configuration=cfg,
                  native_geometry_metadata=native,native_cards_sha256=a.digest(args.cards),
                  baseline_summary_sha256=a.digest(baseline_path),
                  script_sha256=a.digest(__file__),r4_analysis_script_sha256=a.digest(r4.__file__),
                  comparator_script_sha256=a.digest(cmp.__file__),geometry_script_sha256=a.digest(ng.__file__),
                  deck_sha256=hashlib.sha256(deck.encode()).hexdigest(),status='generated_only')
    result['scope'] = ('One 14GHz primary lane, physical native MOS buffer, eight secondary holds, '
                       'one branch-0 comparator. No CDAC/control/output latch/full receiver.')
    result['assumptions'] = [
        'TT25C0.9V. Finite 50ohm source per side; actual CTLE/VGA is absent.',
        'Ideal 1ps complementary clocks and bias voltages; buffer and comparator VDD currents are measured.',
        'Small MOS geometry comes from individually generated native CDF cards; no scaled old parasitics.',
        'CML is inverting; two-stage N/P source follower is non-inverting. Source and held polarity results are separate.',
        'Held-input polarity is indeterminate within inclusive +/-10uV before launch; source classification has no added deadband.',
        '120ps single-decision evaluation at1.75GHz is not seven SAR decisions within571.43ps.',
        'Other seven secondary branches omit comparator gate capacitance; bounded first interface screen.',
        'Power excludes clock/bias generation, CDAC/reference/logic and complete ADC.',
        'DUT/reference differences include comparator loading and evaluation; noisy differences are not pure kickback.',
        'Patterned transfer fit is exploratory and is neither independent PAM4 holdout nor ENOB.']
    result['timing_s'] = dict(primary_period=P,primary_track=TRACK,
                              secondary_track_midpoint_duration=SECOND_OFF-2e-12,
                              compare_launch_after_primary_start=LAUNCH,
                              compare_evaluation=EVAL,secondary_period=SUPER)
    a.atomic_json(directory/'summary.json',result)
    if args.run:
        result['run_status'] = a.b.run(directory,lines,timeout=300)
        if result['run_status']['exit_code'] != 0:
            result['status'] = 'simulation_failed'
            a.atomic_json(directory/'summary.json',result)
            raise RuntimeError('Simulation failed')
        raw = a.parse_file(a._raw_file(directory))
        result['raw_sha256'] = raw.sha256
        result['cycles'],result['summary'] = analyze(raw,cfg)
        result['status'] = 'complete'
        a.atomic_json(directory/'summary.json',result)
    print(json.dumps({key:result[key] for key in ('case','status','summary') if key in result}),flush=True)


if __name__ == '__main__':
    main()
