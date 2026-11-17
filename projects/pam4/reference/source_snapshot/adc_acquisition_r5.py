#!/usr/bin/env python3
"""Four bounded r5 secondary-acquisition variants; Python 3.6, VM-only runs.

Keeps the two successful low-load CML topologies and 5fF/10fF capacitors.
Extends acquisition by7ps, then contrasts secondary switch Ron/injection.
No signal-dependent correction or ideal gain element is introduced.
"""
import argparse
import contextlib
import copy
import hashlib
import json
from pathlib import Path

import adc_comparator_probe as a
import adc_comparator_r5 as cmp
import adc_isolation_r5 as base
import native_geometry_r5 as ng

NAME = 'adc_acquisition_r5_20261013'
VARIANTS = {
    'cml1_late32_s05': ('cml_w1_m5_s10', .5e-6),
    'cml2_late32_s05': ('cml_w2_m5_s10', .5e-6),
    'cml2_late32_s10': ('cml_w2_m5_s10', 1e-6),
    'cml2_late32_s024': ('cml_w2_m5_s10', .24e-6)}
SECOND_OFF = base.TRACK+32e-12
LAUNCH = SECOND_OFF+a.EDGE/2+3e-12


def timing():
    data = dict(primary_period_s=base.P,primary_track_midpoint_duration_s=base.TRACK,
                secondary_period_s=base.SUPER,secondary_on_midpoint_s=2e-12,
                secondary_off_midpoint_s=SECOND_OFF,secondary_track_midpoint_duration_s=SECOND_OFF-2e-12,
                compare_launch_midpoint_s=LAUNCH,compare_evaluation_s=base.EVAL,
                next_primary_on_begin_s=base.P-a.EDGE/2,
                secondary_off_end_s=SECOND_OFF+a.EDGE/2,
                next_secondary_on_begin_s=base.P+2e-12-a.EDGE/2,
                compare_on_begin_s=LAUNCH-a.EDGE/2)
    data['secondary_to_next_primary_nonoverlap_s'] = data['next_primary_on_begin_s']-data['secondary_off_end_s']
    data['secondary_to_next_secondary_nonoverlap_s'] = data['next_secondary_on_begin_s']-data['secondary_off_end_s']
    data['secondary_off_end_to_compare_on_begin_s'] = data['compare_on_begin_s']-data['secondary_off_end_s']
    data['compare_evaluation_overlaps_later_primary_tracks'] = True
    if min(data[k] for k in ('secondary_to_next_primary_nonoverlap_s',
                             'secondary_to_next_secondary_nonoverlap_s',
                             'secondary_off_end_to_compare_on_begin_s')) <= 0:
        raise ValueError('Acquisition clocks violate the intended nonoverlap')
    return data


@contextlib.contextmanager
def selected_timing():
    # The old analyst and new classifier both use actual clock crossings but
    # must share their expected edge locations. Restore globals on every exit.
    previous = [(module,module.SECOND_OFF,module.LAUNCH) for module in (base,base.r4)]
    try:
        for module,unused1,unused2 in previous:
            module.SECOND_OFF, module.LAUNCH = SECOND_OFF, LAUNCH
        yield
    finally:
        for module,off,launch in previous:
            module.SECOND_OFF,module.LAUNCH = off,launch


def configuration(variant,cm,comparator,noise_seed=None):
    preset,width = VARIANTS[variant]
    cfg = copy.deepcopy(base.presets()[preset])
    cfg.update(secondary_switch_width_m=width,input_cm_V=cm,
               comparator_candidate=comparator,noise_seed=noise_seed)
    return preset,cfg


def build(cfg):
    timing()
    with selected_timing():
        return base.build(cfg)


def analyze(raw,cfg):
    with selected_timing():
        rows,summary = base.analyze(raw,cfg)
    t,v = raw.values[raw.sweep_names[0]],raw.values
    get = lambda node,time:a.interpolate(t,v[node],time)
    differential = lambda prefix,time:get(prefix+'p',time)-get(prefix+'n',time)
    captures = []
    for q in range(base.WARMUP*8,base.GROUPS*8):
        start,lane = a.T0+q*base.P,q%8
        sec_before = start+SECOND_OFF-a.EDGE/2-.1e-12
        sec_after = start+SECOND_OFF+a.EDGE/2+.1e-12
        master_after = start+base.TRACK+a.EDGE/2+1e-12
        buffer_before = differential('df',sec_before)
        held_before,held_after = differential('dh'+str(lane),sec_before),differential('dh'+str(lane),sec_after)
        row = dict(primary_slot=q,secondary_branch=lane,source_command_V=base.r4.stimulus(q),
                   source_previous_slot_command_V=base.r4.stimulus(q-1),
                   master_capture_V=differential('dm',master_after),
                   bare_master_capture_V=differential('bm',master_after),
                   buffer_before_secondary_close_V=buffer_before,
                   secondary_before_close_V=held_before,secondary_after_close_V=held_after,
                   secondary_acquisition_lag_before_close_V=held_before-buffer_before,
                   secondary_closing_edge_change_V=held_after-held_before,
                   buffer_change_last5ps_before_close_V=buffer_before-differential('df',sec_before-5e-12),
                   reference_secondary_closing_edge_change_V=differential('rh'+str(lane),sec_after)-differential('rh'+str(lane),sec_before))
        captures.append(row)
    for cycle in rows:
        cycle['acquisition_diagnostic'] = next(row for row in captures if row['primary_slot']==cycle['group']*8)
    fields = ('secondary_acquisition_lag_before_close_V','secondary_closing_edge_change_V',
              'buffer_change_last5ps_before_close_V','reference_secondary_closing_edge_change_V')
    summary['all64_acquisition_diagnostics'] = {
        key:dict(mean_V=sum(r[key] for r in captures)/len(captures),
                 rms_V=(sum(r[key]**2 for r in captures)/len(captures))**.5,
                 peak_abs_V=max(abs(r[key]) for r in captures)) for key in fields}
    summary['acquisition_diagnostic_note'] = ('Closing-edge change includes signal movement, transistor charge injection and clock feedthrough; '
                                             'it is not an isolated injection measurement. The same fixed exploratory pattern is reused.')
    return rows,summary,captures


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case',required=True)
    p.add_argument('--variant',choices=sorted(VARIANTS),required=True)
    p.add_argument('--comparator',choices=sorted(cmp.candidates()),default='in100_tail3')
    p.add_argument('--noise-seed',type=int)
    p.add_argument('--cards',type=Path,default=ng.CARD_PATH)
    p.add_argument('--run',action='store_true')
    args = p.parse_args()
    if not args.case.replace('_','').isalnum():p.error('Safe case name required')
    if args.noise_seed is not None and not 1<=args.noise_seed<=2147483647:p.error('Invalid noise seed')
    if not (a.PROJECT/'.codex_project6_owned').exists():raise ValueError('Project marker absent')
    native = ng.install(args.cards)
    baseline_path = a.PROJECT/'runs/adc_comparator_r3_tt/comparator_probe_summary.json'
    original = json.loads(baseline_path.read_text())
    preset,cfg = configuration(args.variant,original['configuration']['common_mode_V'],args.comparator,args.noise_seed)
    lines = build(cfg)
    directory = a.PROJECT/'runs'/NAME/args.case
    if directory.exists():raise ValueError('Refuse to overwrite existing acquisition experiment')
    directory.mkdir(parents=True)
    deck='\n'.join(lines)+'\n'
    (directory/'bench.scs').write_text(deck)
    result = dict(case=args.case,variant=args.variant,parent_preset=preset,status='generated_only',
                  configuration=cfg,timing=timing(),native_geometry_metadata=native,
                  native_cards_sha256=a.digest(args.cards),baseline_summary_sha256=a.digest(baseline_path),
                  script_sha256=a.digest(__file__),base_script_sha256=a.digest(base.__file__),
                  r4_analysis_script_sha256=a.digest(base.r4.__file__),
                  comparator_script_sha256=a.digest(cmp.__file__),geometry_script_sha256=a.digest(ng.__file__),
                  deck_sha256=hashlib.sha256(deck.encode()).hexdigest())
    result['scope']='Bounded acquisition-timing/switch-sizing screen; one14GHz master and8 secondary holds, onlybranch0 comparator.'
    result['assumptions']=[
        'TT25C0.9V, per-side50ohm surrogate source; actual CTLE/VGA absent.',
        'Primary5fF andsecondary10fF capacitors retained; nativeCDF MOS parasitics retained.',
        'Ideal1ps complementary clocks andbias sources; noideal signalbuffer orsignal-dependent correction.',
        'Secondaryclose delayed7ps; ends2.714ps before nextmasterturn-onbegins; comparator evaluation overlaps latermastertracks.',
        'Other7branches omitcomparatorgate loading; one120psdecision per571.43ps, not7-bitADC conversion.',
        'All8branchsource-to-hold fit uses same64exploratorysamples; branch0 includes8small/large decision stresses, notBER/ENOB.',
        'Source andprelaunchheld classifications separate; inclusive+/-10uV heldsignband isindeterminate.',
        'Closing-edge change isnotpurechargeinjection; noisysubtraction isnotpurekickback.',
        'VDDpower excludes clock/biasgeneration,CDAC/reference/SARlogic andDSP.']
    a.atomic_json(directory/'summary.json',result)
    if args.run:
        result['run_status']=a.b.run(directory,lines,timeout=300)
        if result['run_status']['exit_code']!=0:
            result['status']='simulation_failed'
            a.atomic_json(directory/'summary.json',result)
            raise RuntimeError('Acquisition simulation failed')
        raw=a.parse_file(a._raw_file(directory))
        result['raw_sha256']=raw.sha256
        result['cycles'],result['summary'],result['all64_acquisition_samples']=analyze(raw,cfg)
        result['status']='complete'
        a.atomic_json(directory/'summary.json',result)
    print(json.dumps({k:result[k] for k in ('case','status','summary') if k in result}),flush=True)


if __name__=='__main__':main()
