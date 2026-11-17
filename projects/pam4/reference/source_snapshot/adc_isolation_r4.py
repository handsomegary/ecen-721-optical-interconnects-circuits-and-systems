#!/usr/bin/env python3
"""Physical CML buffer + eight secondary holds + one comparator, Python 3.6.

Exploratory block test, not a 7-bit ADC or an integrated receiver validation.
All MOS instance cards and raw waveforms stay within the existing VM project.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import adc_comparator_probe as a

P = 8.0 / 112e9
SUPER = 8 * P
TRACK = P / 2
SECOND_OFF = TRACK + 25e-12
LAUNCH = SECOND_OFF + a.EDGE / 2 + 3e-12
EVAL = 120e-12
GROUPS = 10
WARMUP = 2
TARGET_LSB = [1., -1., 1., -1., .25, -.25, 32., -.25, -32., .25, 1.]


def stimulus(q):
    if q % 8 == 0:
        return TARGET_LSB[q // 8] * .1 / 128
    return [-.05, .05, -.05/3, .05/3][q % 4]


def clock(lines, saves, name, changes, stop, vdd):
    points = a.pwl(0., changes, stop)
    for suffix, wave in [('ck', points), ('kb', [(t, vdd-x) for t,x in points])]:
        node = name + suffix
        source = 'V' + node
        lines.append('%s (%s 0) vsource type=pwl wave=%s' % (source, node, a.wave(wave)))
        saves.extend([node, source+':p'])


def build(cfg):
    vdd = cfg['vdd_V']
    stop = a.T0 + (GROUPS * 8 + 8) * P
    changes = [(a.T0+q*P+2e-12, stimulus(q)) for q in range(GROUPS*8+1)]
    sigp = a.pwl(cfg['input_cm_V'], [(t,cfg['input_cm_V']+d/2) for t,d in changes], stop)
    sign = a.pwl(cfg['input_cm_V'], [(t,cfg['input_cm_V']-d/2) for t,d in changes], stop)
    lines = a.b.header(temp=25) + [
        '// r4 CML isolation exploration. Only branch 0 has a comparator.',
        'VSP (srcp 0) vsource type=pwl wave='+a.wave(sigp),
        'VSN (srcn 0) vsource type=pwl wave='+a.wave(sign),
        'VA (avdd 0) vsource dc=%.15g' % vdd,
        'VB (bvdd 0) vsource dc=%.15g' % vdd,
        'VBIAS (bias 0) vsource dc=%.15g' % cfg['bias_V']]
    saves = ['srcp','srcn','VA:p','VB:p','VBIAS:p']
    tr = []
    for q in range(GROUPS*8+8):
        tr += [(a.T0+q*P,vdd),(a.T0+q*P+TRACK,0.)]
    clock(lines, saves, 'm', tr, stop, vdd)
    for lane in range(8):
        changes = []
        for g in range(GROUPS+1):
            start = a.T0 + (g*8+lane)*P
            if start+SECOND_OFF+a.EDGE/2 < stop:
                changes += [(start+2e-12,vdd),(start+SECOND_OFF,0.)]
        clock(lines, saves, 's'+str(lane), changes, stop, vdd)
    # b: bare 5fF master reference; r: complete buffer/bank without comparator;
    # d: identical buffer/bank with comparator on secondary lane 0.
    for tag in ('b','r','d'):
        lines.append('V%sDD (%ssupply 0) vsource dc=%.15g' % (tag,tag,vdd))
        saves.append('V'+tag+'DD:p')
        for side in ('p','n'):
            master = tag+'m'+side
            lines += ['R%s%s (src%s %si%s) resistor r=50' % (tag,side,side,tag,side),
                      'C%sM%s (%s 0) capacitor c=%.15g' % (tag,side,master,cfg['primary_cap_F']),
                      'R%sM%s (%s %si%s) resistor r=1T' % (tag,side,master,tag,side)]
            for copy in range(cfg['primary_switch_copies']):
                lines += [a.b.mos(tag+'MN'+side+str(copy),master,'mck',tag+'i'+side,'0'),
                          a.b.mos(tag+'MP'+side+str(copy),master,'mkb',tag+'i'+side,tag+'supply',pmos=True)]
            saves.append(master)
            if tag == 'b':
                continue
            out, source = tag+'f'+side, tag+'e'+side
            lines += ['R%sL%s (%ssupply %s) resistor r=%.15g' % (tag,side,tag,out,cfg['load_ohm'])]
            for copy in range(cfg['buffer_copies']):
                lines += [a.b.mos(tag+'F'+side+str(copy),out,master,source,'0'),
                          a.b.mos(tag+'T'+side+str(copy),source,'bias','0','0',l=60e-9)]
            saves += [out,source]
            for lane in range(8):
                hold = tag+'h'+str(lane)+side
                lines += [a.b.mos(tag+'SN'+str(lane)+side,hold,'s'+str(lane)+'ck',out,'0'),
                          a.b.mos(tag+'SP'+str(lane)+side,hold,'s'+str(lane)+'kb',out,tag+'supply',pmos=True),
                          'C%sH%d%s (%s 0) capacitor c=%.15g' % (tag,lane,side,hold,cfg['secondary_cap_F']),
                          'R%sH%d%s (%s %s) resistor r=1T' % (tag,lane,side,hold,out)]
                saves.append(hold)
        if tag != 'b':
            lines.append('R%sDEG (%sep %sen) resistor r=%.15g' % (tag,tag,tag,cfg['degeneration_ohm']))
    compare = []
    for g in range(GROUPS+1):
        start = a.T0+g*SUPER
        compare += [(start+LAUNCH,vdd),(start+LAUNCH+EVAL+a.EDGE/2+.1e-12,0.)]
    points = a.pwl(0., compare, stop)
    lines.append('VCMP (cmp 0) vsource type=pwl wave='+a.wave(points))
    saves += ['cmp','VCMP:p','p','q','x','y','tail','bx','by']
    lines += a.strongarm(inp='dh0p',inn='dh0n',copies={'precharge':4,'tail':4})
    lines += ['CBX (bx 0) capacitor c=1f','CBY (by 0) capacitor c=1f']
    noise = '' if cfg.get('noise_seed') is None else ' noisefmax=150G noisefmin=500M noiseseed=%d' % cfg['noise_seed']
    lines += ['saveOptions options save=selected currents=selected','save '+' '.join(saves),
              'tranResponse tran stop=%.15g maxstep=100f outputstart=%.15g errpreset=conservative%s' % (stop,a.T0+(WARMUP-1)*SUPER,noise)]
    return lines


def diff(v, prefix):
    return [p-n for p,n in zip(v[prefix+'p'],v[prefix+'n'])]


def analyze(raw,cfg):
    t,v = raw.values[raw.sweep_names[0]],raw.values
    vdd = cfg['vdd_V']
    launched = a.crossings(t,v['cmp'],vdd/2,True)
    captured = a.crossings(t,v['s0ck'],vdd/2,False)
    master = a.crossings(t,v['mck'],vdd/2,False)
    get = lambda node,time: a.interpolate(t,v[node],time)
    rows = []
    for g in range(WARMUP,GROUPS):
        start = a.T0+g*SUPER
        launch = a.near(launched,start+LAUNCH)
        capture = a.near(captured,start+SECOND_OFF)+a.EDGE/2+1e-12
        mc = a.near(master,start+TRACK)+a.EDGE/2+1e-12
        before = launch-a.EDGE/2-.1e-12
        end = launch+EVAL
        expected = -1 if TARGET_LSB[g]>0 else 1  # CML inverts input polarity.
        row = {'group':g,'source_input_LSB':TARGET_LSB[g],
               'master_at_capture_V':get('dmp',mc)-get('dmn',mc),
               'bare_master_at_capture_V':get('bmp',mc)-get('bmn',mc),
               'secondary_at_capture_V':get('dh0p',capture)-get('dh0n',capture),
               'reference_secondary_at_capture_V':get('rh0p',capture)-get('rh0n',capture),
               'secondary_common_mode_V':(get('dh0p',capture)+get('dh0n',capture))/2,
               'secondary_prelaunch_differential_V':get('dh0p',before)-get('dh0n',before),
               'reset_internal_min_V':min(get(n,before) for n in ('p','q','x','y')),
               'reset_xy_imbalance_V':get('y',before)-get('x',before),
               'reset_pq_imbalance_V':get('p',before)-get('q',before)}
        for label, hp,lp in [('raw','y','x'),('buffered','bx','by')]:
            hi,lo = (hp,lp) if expected>0 else (lp,hp)
            correct = [h>=.8*vdd and l<=.2*vdd for h,l in zip(v[hi],v[lo])]
            wrong = [l>=.8*vdd and h<=.2*vdd for h,l in zip(v[hi],v[lo])]
            ct,wt = a.first_stable(t,correct,launch,end),a.first_stable(t,wrong,launch,end)
            if get(hi,end)<.8*vdd or get(lo,end)>.2*vdd: ct=None
            if get(lo,end)<.8*vdd or get(hi,end)>.2*vdd: wt=None
            row[label+'_classification'] = 'correct' if ct is not None else ('wrong' if wt is not None else 'unresolved')
            row[label+'_resolution_s'] = None if ct is None else ct-launch
        for name,dp,dn,rp,rn in [('master','dmp','dmn','rmp','rmn'),('secondary','dh0p','dh0n','rh0p','rh0n')]:
            for mode in ('differential','common_mode'):
                trace = [(x-y-z+w) if mode=='differential' else (x+y-z-w)/2
                         for x,y,z,w in zip(v[dp],v[dn],v[rp],v[rn])]
                base = a.interpolate(t,trace,before)
                unused,z = a.window(t,trace,before,end)
                row[name+'_compare_extra_'+mode+'_peak_V'] = max(abs(x-base) for x in z)
        # Secondary branch 0 holds its value while all other bank branches switch.
        rt = diff(v,'rh0')
        unused,z = a.window(t,rt,capture,start+SUPER-a.EDGE/2)
        row['reference_secondary_hold_change_peak_V'] = max(abs(x-z[0]) for x in z)
        for name,node in [('buffer_bank','VdDD:p'),('comparator','VA:p'),('output_inverters','VB:p')]:
            row[name+'_power_W'] = -vdd*a.integral(t,v[node],start,start+SUPER)/SUPER
        rows.append(row)
    captures = []
    for q in range(WARMUP*8,GROUPS*8):
        lane = q%8
        tm = a.T0+q*P+TRACK+a.EDGE/2+1e-12
        ts = a.T0+q*P+SECOND_OFF+a.EDGE/2+1e-12
        captures.append({'input_V':stimulus(q),'master_V':get('dmp',tm)-get('dmn',tm),
                         'bare_master_V':get('bmp',tm)-get('bmn',tm),
                         'secondary_V':get('dh'+str(lane)+'p',ts)-get('dh'+str(lane)+'n',ts)})
    def regression(key):
        mx = sum(r['input_V'] for r in captures)/len(captures)
        my = sum(r[key] for r in captures)/len(captures)
        gain = sum((r['input_V']-mx)*(r[key]-my) for r in captures)/sum((r['input_V']-mx)**2 for r in captures)
        offset = my-gain*mx
        errors = [r[key]-offset-gain*r['input_V'] for r in captures]
        return {'gain_VV':gain,'offset_V':offset,'fit_error_rms_V':math.sqrt(sum(e*e for e in errors)/len(errors)),
                'fit_error_peak_V':max(abs(e) for e in errors),'samples':len(captures)}
    summary = {'decisions':len(rows),'exploratory_transfer_fit':{key:regression(key) for key in ('master_V','bare_master_V','secondary_V')}}
    for label in ('raw','buffered'):
        summary[label+'_counts'] = {k:sum(r[label+'_classification']==k for r in rows) for k in ('correct','wrong','unresolved')}
        times = [r[label+'_resolution_s'] for r in rows if r[label+'_resolution_s'] is not None]
        summary[label+'_resolution_max_s'] = max(times) if times else None
    for key in ('master_compare_extra_differential_peak_V','master_compare_extra_common_mode_peak_V',
                'secondary_compare_extra_differential_peak_V','secondary_compare_extra_common_mode_peak_V',
                'reference_secondary_hold_change_peak_V'):
        summary['max_'+key] = max(r[key] for r in rows)
    for key in ('buffer_bank_power_W','comparator_power_W','output_inverters_power_W'):
        summary['mean_'+key] = sum(r[key] for r in rows)/len(rows)
    summary['secondary_common_mode_range_V'] = [min(r['secondary_common_mode_V'] for r in rows),max(r['secondary_common_mode_V'] for r in rows)]
    summary['noise_reference_subtraction_is_not_pure_kickback'] = cfg.get('noise_seed') is not None
    return rows,summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case',required=True)
    p.add_argument('--cap-ff',type=float,default=50.)
    p.add_argument('--primary-cap-ff',type=float,default=5.)
    p.add_argument('--primary-switch-copies',type=int,default=1)
    p.add_argument('--copies',type=int,default=2)
    p.add_argument('--load-ohm',type=float,default=100.)
    p.add_argument('--deg-ohm',type=float,default=250.)
    p.add_argument('--bias',type=float,default=.5)
    p.add_argument('--noise-seed',type=int)
    p.add_argument('--run',action='store_true')
    args = p.parse_args()
    if not args.case.replace('_','').isalnum() or not 1<=args.copies<=16 or not 1<=args.primary_switch_copies<=16:
        p.error('Safe case name and 1..16 copies required')
    if not all(math.isfinite(x) and x>0 for x in (args.cap_ff,args.primary_cap_ff,args.load_ohm,args.deg_ohm,args.bias)) or args.bias>=.9:
        p.error('Invalid circuit configuration')
    project = a.PROJECT
    if not (project/'.codex_project6_owned').exists(): raise ValueError('Project ownership marker absent')
    original = json.loads((project/'runs/adc_comparator_r3_tt/comparator_probe_summary.json').read_text())
    a.validate_card_identity(project/'configs/native_device_cards.json')
    native = a.install_native_cards(project/'configs/native_device_cards.json')
    if native['native_cards_sha256'] != original['native_cards']['native_cards_sha256']:
        raise ValueError('Native card identity changed')
    cfg = {'vdd_V':.9,'input_cm_V':original['configuration']['common_mode_V'],'secondary_cap_F':args.cap_ff*1e-15,
           'primary_cap_F':args.primary_cap_ff*1e-15,
           'primary_switch_copies':args.primary_switch_copies,
           'buffer_copies':args.copies,'load_ohm':args.load_ohm,'degeneration_ohm':args.deg_ohm,
           'bias_V':args.bias,'noise_seed':args.noise_seed}
    lines = build(cfg)
    directory = project/'runs/adc_isolation_r4_20261013'/args.case
    if directory.exists(): raise ValueError('Refuse to overwrite an existing case')
    directory.mkdir(parents=True)
    deck = '\n'.join(lines)+'\n'
    (directory/'bench.scs').write_text(deck)
    result = {'case':args.case,'configuration':cfg,'native_cards_sha256':native['native_cards_sha256'],
              'deck_sha256':hashlib.sha256(deck.encode()).hexdigest(),'script_sha256':a.digest(__file__),
              'scope':'One 14GHz primary lane + physical CML buffer + eight switched secondary holds, only branch 0 has comparator; no CDAC/control/output latch/full receiver.',
              'assumptions':['50ohm source per side; full AFE absent.','TT25C0.9V, ideal complementary 1ps clocks and bias source.',
                             'Primary capacitor is explicitly configured; W3um native MOS copies, N-tail L60nm; all other MOS L30nm.',
                             'CML is inverting. Comparator gets120ps per single decision at1.75GHz.',
                             'This does not demonstrate seven SAR decisions within571.43ps.',
                             'Other seven secondary branches omit comparator gate capacitance; first isolation screen only.',
                             'VDD powers exclude ideal clock and bias generation, CDAC, logic and complete ADC.',
                             'DUT-reference difference combines comparator gate loading and evaluation disturbance, not pure kickback.',
                             'Exploratory patterned transfer fit is not independent holdout or ADC ENOB.'],
              'timing_s':{'primary_period':P,'primary_track':TRACK,'secondary_track_midpoint_duration':SECOND_OFF-2e-12,
                          'compare_launch_after_primary_start':LAUNCH,'compare_evaluation':EVAL,'secondary_period':SUPER}}
    if args.run:
        result['run_status'] = a.b.run(directory,lines,timeout=240)
        if result['run_status']['exit_code'] != 0:
            a.atomic_json(directory/'summary.json',result)
            raise RuntimeError('Simulation failed')
        raw = a.parse_file(a._raw_file(directory))
        result['raw_sha256'] = raw.sha256
        result['cycles'],result['summary'] = analyze(raw,cfg)
    a.atomic_json(directory/'summary.json',result)
    print(json.dumps({k:result[k] for k in ('case','run_status','summary') if k in result}),flush=True)


if __name__ == '__main__': main()
