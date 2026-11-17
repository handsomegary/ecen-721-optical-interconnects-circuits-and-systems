#!/usr/bin/env python3
"""Clocked r3 AFE/CML/64-secondary-hold PAM4 screen, Python 3.6.

All64 comparators are native MOS but permanently reset. The quantizer and
17-tap FFE are numerical diagnostics: complete_ADC_verified remains false.
Training freezes primary/secondary detectors before separate holdout runs.
Native cards, decks and raw traces remain in the existing VM project.
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
import adc_frontend_load_r5 as load
import adc_isolation_r5 as interface
import native_geometry_r5 as ng
import optimize_pam4 as opt
import pam4_integration as pi
import psf_ascii

ROOT_NAME = 'adc_backend_pam4_r5_20261013'
TRAIN_COUNT, VALID_COUNT = 1024, 2048
TRAIN_SEED, VALID_SEED = 2026101301, 2026101302
TRAIN_NOISE, VALID_NOISE = 157, 173
PHASE_UI = .25
STROBE = pi.UI/8
VARIANTS = {'cml2_original':('cml_w2_m5_s10',.5e-6,25e-12),
            'cml2_late05':('cml_w2_m5_s10',.5e-6,32e-12),
            'cml2_late1':('cml_w2_m5_s10',1e-6,32e-12)}


def configuration(variant,comparator='in100_tail3'):
    preset,width,extra = VARIANTS[variant]
    cfg=copy.deepcopy(interface.presets()[preset])
    cfg.update(secondary_switch_width_m=width,secondary_extra_after_primary_fall_s=extra,
               comparator_candidate=comparator,phase_UI=PHASE_UI)
    return cfg


def pulse_parameters(line):
    result={name:pi._spectre_number(value) for name,value in
            re.findall(r'\b(delay|rise|fall|width|period|val0|val1)=([^\s]+)',line)}
    if set(result)!=set(('delay','rise','fall','width','period','val0','val1')):
        raise ValueError('Pulse lacks required parameters')
    result['first_rise_midpoint_s']=result['delay']+result['rise']/2
    result['first_fall_midpoint_s']=result['delay']+result['rise']+result['width']+result['fall']/2
    return result


def add_backend(lines,saves,cfg,clocks):
    lines += ['VBANK (bankvdd 0) vsource dc=.9',
              'VNBIAS (nbias 0) vsource dc=%.16g'%cfg['n_bias_V'],
              'VPBIAS (pbias 0) vsource dc=%.16g'%cfg['p_bias_V'],
              'VCOMP (compvdd 0) vsource dc=.9','VLOGIC (logicvdd 0) vsource dc=.9',
              'subckt COMPLOAD (inp inn avdd bvdd)']
    lines += cmp.sized_strongarm(cmp.candidates()[cfg['comparator_candidate']],ng.mos,
                                inp='inp',inn='inn',clk='0')
    lines += ['CBX (bx 0) capacitor c=1f','CBY (by 0) capacitor c=1f','ends COMPLOAD']
    saves += ['VBANK:p','VNBIAS:p','VPBIAS:p','VCOMP:p','VLOGIC:p']
    secondary_specs=[]
    for bank,master in enumerate(clocks):
        tag='B%d_'%bank
        master_period=master['period']
        master_track=master['first_fall_midpoint_s']-master['first_rise_midpoint_s']
        sec_duration=master_track+cfg['secondary_extra_after_primary_fall_s']-2e-12
        if sec_duration<=pi.EDGE: raise ValueError('Secondary track window too short')
        gap=master_period-master_track-cfg['secondary_extra_after_primary_fall_s']-pi.EDGE
        if gap<=0: raise ValueError('Secondary falling edge overlaps next primary rising edge')
        for lane in range(8):
            open_mid=master['first_rise_midpoint_s']+lane*master_period+2e-12
            delay=open_mid-pi.EDGE/2
            width=sec_duration-pi.EDGE
            for suffix,low,high in [('ck',0.,.9),('kb',.9,0.)]:
                node=tag+suffix+str(lane)
                lines.append('%sV (%s 0) vsource type=pulse val0=%.16g val1=%.16g delay=%.16g rise=%.16g fall=%.16g width=%.16g period=%.16g'%
                             (node,node,low,high,delay,pi.EDGE,pi.EDGE,width,8*master_period))
                if (bank,lane) in ((0,0),(0,7),(7,7)):
                    saves.append(node)
            secondary_specs.append(dict(bank=bank,branch=lane,first_open_midpoint_s=open_mid,
                                        first_close_midpoint_s=open_mid+sec_duration,
                                        period_s=8*master_period,
                                        nonoverlap_to_next_primary_begin_s=gap))
        for side in ('p','m'):
            temp=[]
            out,mid=interface.buffer(temp,tag,side,cfg)
            lines += load.remap_nodes(temp,{tag+'m'+side:'X_h%d%s'%(bank,side),tag+'supply':'bankvdd'})
            # The output node is saved for two representative banks only.
            if bank in (0,7): saves.extend((out,mid))
            for lane in range(8):
                hold=tag+'h%d%s'%(lane,side)
                lines += [ng.mos(tag+'SN%d%s'%(lane,side),hold,tag+'ck'+str(lane),out,'0',w=cfg['secondary_switch_width_m']),
                          ng.mos(tag+'SP%d%s'%(lane,side),hold,tag+'kb'+str(lane),out,'bankvdd',pmos=True,w=cfg['secondary_switch_width_m']),
                          '%sCH%d%s (%s 0) capacitor c=%.16g'%(tag,lane,side,hold,cfg['secondary_cap_F']),
                          '%sRH%d%s (%s %s) resistor r=1T'%(tag,lane,side,hold,out)]
                saves.append(hold)
        lines.append('%sRDEG (%sep %sem) resistor r=%.16g'%(tag,tag,tag,cfg['degeneration_ohm']))
        for lane in range(8):
            lines.append('%sCOMP%d (%sh%dp %sh%dm compvdd logicvdd) COMPLOAD'%(tag,lane,tag,lane,tag,lane))
    return secondary_specs


def build_deck(frontend,cfg,symbols,noise_seed=None):
    fc=copy.deepcopy(frontend)
    fc.update(ch=cfg['primary_cap_F'],wn_sw=cfg['primary_switch_width_m'],wp_sw=cfg['primary_switch_width_m'])
    if cfg['primary_switch_copies']!=1: raise ValueError('Clocked integration supports one native primary TG per side')
    original,stop=pi.build_deck(fc,symbols,20.,phase_ui=cfg['phase_UI'],noise=False)
    clocks=[]
    for bank in range(8):
        found=[x for x in original if x.startswith('XCK%d '%bank)]
        if len(found)!=1: raise ValueError('Missing unique native primary clock')
        clocks.append(pulse_parameters(found[0]))
    if any(abs(c['period']-clocks[0]['period'])>1e-20 for c in clocks):
        raise ValueError('Primary clocks have unequal periods')
    lines=[x for x in original if not x.startswith(('saveOptions ','save ','dcOp ','tranResponse '))]
    saves=next(x for x in original if x.startswith('save ')).split()[1:]
    secondary=add_backend(lines,saves,cfg,clocks)
    # Output-only strobing keeps all adaptive Spectre integration steps intact.
    stop += 6*pi.UI
    tran='tranResponse tran stop=%.16g maxstep=200f errpreset=conservative strobeperiod=%.16g strobeoutput=strobeonly'%(stop,STROBE)
    if noise_seed is not None: tran+=' noisefmax=150G noisefmin=500M noiseseed=%d'%noise_seed
    lines += ['saveOptions options save=selected currents=selected','save '+' '.join(dict.fromkeys(saves)),
              'dcOp dc',tran]
    return lines,dict(primary_clocks=clocks,secondary_clocks=secondary,stop_s=stop,strobe_period_s=STROBE)


def extract_records(raw,clock_spec):
    t,v=raw.values[raw.sweep_names[0]],raw.values
    falls=a.crossings(t,v['X_ck0'],.45,False)
    if len(falls)<2: raise ValueError('Insufficient actual primary clock falls')
    masters=clock_spec['primary_clocks']
    first_expected=masters[0]['first_fall_midpoint_s']
    tolerance=STROBE
    if abs(falls[0]-first_expected)>tolerance:
        raise ValueError('Saved first CK0 fall is not primary mastercycle0; branch mapping would be ambiguous')
    period=masters[0]['period']
    extra=clock_spec['secondary_clocks'][0]['first_close_midpoint_s']-first_expected
    primary,secondary=[],[]
    mapping=[]
    cycle_errors=[]
    get=lambda node,time:a.interpolate(t,v[node],time)
    for fall_index,fall in enumerate(falls):
        master_cycle=int(round((fall-falls[0])/period))
        if master_cycle!=fall_index: raise ValueError('Skipped or duplicated primary master cycle')
        cycle_errors.append(abs(fall-falls[0]-master_cycle*period))
        branch=master_cycle%8
        for bank in range(8):
            bank_delay=masters[bank]['first_fall_midpoint_s']-first_expected
            close=fall+bank_delay
            primary_read=close+1.5e-12
            secondary_read=close+extra+1.5e-12
            if close<pi.T0 or secondary_read>t[-1]:continue
            index=int(math.floor((close-pi.T0)/pi.UI+1e-7))
            p=get('X_h%dp'%bank,primary_read)-get('X_h%dm'%bank,primary_read)
            s=get('B%d_h%dp'%(bank,branch),secondary_read)-get('B%d_h%dm'%(bank,branch),secondary_read)
            # Both receive the primary aperture's symbol index. Later backend
            # read time must not be mistaken for a later transmitted symbol.
            primary.append((index,p,primary_read,close,bank))
            secondary.append((index,s,secondary_read,close,bank))
            mapping.append(dict(symbol_time_index=index,master_cycle=master_cycle,bank=bank,
                                secondary_branch=branch,primary_close_s=close,secondary_read_s=secondary_read))
    for records in (primary,secondary):
        records.sort(key=lambda row:row[0])
        if len(records)!=len(set(row[0] for row in records)):
            raise ValueError('Duplicate symbol indices from primary-to-secondary mapping')
        if any(b[0]-a0[0]!=1 for a0,b in zip(records,records[1:])):
            raise ValueError('Missing symbol index from primary-to-secondary mapping')
    if [x[0] for x in primary]!=[x[0] for x in secondary]:raise ValueError('Sample point index coverage differs')
    secondary_audit=[]
    for bank,branch in ((0,0),(0,7),(7,7)):
        spec=next(x for x in clock_spec['secondary_clocks'] if (x['bank'],x['branch'])==(bank,branch))
        sf=a.crossings(t,v['B%d_ck%d'%(bank,branch)],.45,False)
        if not sf:raise ValueError('Missing saved secondary clock falls')
        error=max(abs(f-spec['first_close_midpoint_s']-i*spec['period_s']) for i,f in enumerate(sf))
        if error>tolerance:raise ValueError('Secondary pulse cycle differs from declared mapping')
        secondary_audit.append(dict(bank=bank,branch=branch,fall_count=len(sf),max_expected_fall_error_s=error))
    if max(cycle_errors)>tolerance:raise ValueError('Master cycle mapping exceeds strobe interpolation tolerance')
    audit=dict(first_actual_CK0_fall_s=falls[0],first_expected_CK0_fall_s=first_expected,
               actual_master_period_declared_s=period,master_fall_count=len(falls),
               master_cycle_max_error_s=max(cycle_errors),strobe_period_s=STROBE,
               interpolation_tolerance_s=tolerance,secondary_clock_audit=secondary_audit,
               retained_primary_and_secondary_records=len(primary),
               branch_rule='First actual CK0 fall is mastercycle0. Secondarybranch=mastercycle modulo8, bank=primarylane.',
               label_rule='Primary andsecondary shareprimarycapture symbolindex; secondaryreadtime islater.',
               primary_read_after_fall_midpoint_s=1.5e-12,
               secondary_read_after_primary_fall_midpoint_s=extra+1.5e-12,
               first_mapping=mapping[:8],last_mapping=mapping[-8:])
    if any(row[0]>=pi.WARMUP for row in primary):
        audit['measured_primary_aperture']=opt.measured_aperture_phase(primary)
    return {'primary':primary,'secondary':secondary},audit


def protocol(variant,comparator,training_noise):
    return dict(variant=variant,comparator=comparator,training_data_seed=TRAIN_SEED,
                validation_data_seed=VALID_SEED,training_noise_seed=training_noise,
                validation_conditions=[dict(kind='noiseless',noise_seed=None),dict(kind='noise',noise_seed=VALID_NOISE)],
                training_input_symbols=TRAIN_COUNT,validation_input_symbols=VALID_COUNT,
                phase_UI=PHASE_UI,loss_dB_at_56GHz=20.,complete_ADC_verified=False,
                conditions=dict(temperature_C=25.,supply_V=.9,TX_differential_Vpp=.4,
                                symbol_rate_Hz=112e9,primary_lane_rate_Hz=14e9,
                                secondary_branch_rate_Hz=1.75e9,PN_skew_s=0.,clock_edge_s=1e-12),
                limitations=[
                    'Synthetic20dB-at56GHz channel: two isolated18.6667GHz RCpoles perleg, idealVCVSbuffers andzeroimpedanceTX.',
                    'Real nativeMOS r3AFE,8primaryTGs,8CMLbanks,64secondaryTGs/caps and64resetcomparator gate loads.',
                    'Comparators remainreset; actualcomparison,CDAC,reference,SARlogic andoutputconversion areabsent.',
                    'Ideal7bitquantizer and17tapFFE arefitted independentlyatprimary/secondarypoints usingtrainingonly;8UIFFE latency.',
                    'Noiseless andnoise173 evaluations reuseonefreshdataholdout; theyarenottwoindependentdatasequences.',
                    'Transientnoise150GHz fmax,500MHz fmin includesphysicalchannelresistornoise; finiteband, noaliasconvergenceproof.',
                    'Idealclocks/bias, noPVT/mismatch/jitter/PNskew/PEX validation; no7ENOB orcompleteADC claim.'])


def training_symbols():return opt.random_symbols(TRAIN_SEED,pi.WARMUP+TRAIN_COUNT+pi.GUARD)


def validation_symbols():
    return opt.random_symbols(TRAIN_SEED,pi.WARMUP+TRAIN_COUNT)+opt.random_symbols(VALID_SEED,VALID_COUNT+pi.GUARD)


def identity(frontend,cfg,native):
    scripts={name:a.digest(Path(__file__).with_name(name)) for name in (
        'adc_backend_pam4_r5.py','adc_isolation_r5.py','adc_frontend_load_r5.py','adc_comparator_r5.py',
        'native_geometry_r5.py','pam4_integration.py','optimize_pam4.py','pam4_ffe_diagnostic.py','pam4_metrics.py')}
    return dict(frontend=frontend,backend=cfg,native_geometry_metadata=native,scripts=scripts)


def run_deck(root,name,frontend,cfg,symbols,noise_seed,run,timeout):
    directory=root/name
    if directory.exists():raise ValueError('Refuse to overwrite existing PAM4 run: '+name)
    directory.mkdir(parents=True)
    lines,clock_spec=build_deck(frontend,cfg,symbols,noise_seed)
    deck='\n'.join(lines)+'\n'
    (directory/'bench.scs').write_text(deck)
    record=dict(name=name,status='generated_only',noise_seed=noise_seed,symbol_count=len(symbols),
                deck_sha256=hashlib.sha256(deck.encode()).hexdigest(),
                symbol_sequence_sha256=opt.canonical_hash(symbols),clock_specification=clock_spec,
                complete_ADC_verified=False)
    a.atomic_json(directory/'run_summary.json',record)
    if not run:return None,None,record,directory
    record['run_status']=a.b.run(directory,lines,timeout=timeout)
    if record['run_status']['exit_code']!=0:
        record['status']='simulation_failed'
        a.atomic_json(directory/'run_summary.json',record)
        raise RuntimeError('PAM4 simulation failed: '+name)
    psf_ascii.MAX_FILE_BYTES=512*1024*1024
    raw=a.parse_file(a._raw_file(directory))
    record['raw_transient_sha256']=raw.sha256
    records,record['clock_mapping_audit']=extract_records(raw,clock_spec)
    record['status']='simulation_complete'
    a.atomic_json(directory/'run_summary.json',record)
    return raw,records,record,directory


def power(raw,lo,hi):
    times=raw.values[raw.sweep_names[0]]
    result={name:-.9*a.integral(times,raw.values[node],lo,hi)/(hi-lo) for name,node in (
        ('AFE_and_primary_sampler_W','XVs:p'),('all8_buffer_secondary_banks_W','VBANK:p'),
        ('all64_reset_comparators_W','VCOMP:p'),('all64_reset_output_inverters_W','VLOGIC:p'))}
    result['total_measured_VDD_W']=sum(result.values())
    result['interval_s']=[lo,hi]
    result['scope']='Includes clocked native secondary banks andresetcomparatorload; excludesclock/biasgenerators,CDAC/reference/logic/DSP.'
    return result


def train(root,frontend,cfg,native,declared,run,timeout):
    frozen_path=root/'frozen.json'
    if frozen_path.exists():raise ValueError('Frozen choices already exist; no retraining over used holdout')
    if root.exists() and any(root.iterdir()):raise ValueError('Training requires a new empty study directory')
    root.mkdir(parents=True,exist_ok=True)
    baseline_ledger=a.PROJECT/'results/pam4_validation_usage.json'
    if baseline_ledger.exists():
        old=json.loads(baseline_ledger.read_text())
        if str(VALID_SEED) in json.dumps(old):raise ValueError('Proposed final data seed was used by old frontend study')
    # This protocol is written before any waveform or fitting action.
    ident=identity(frontend,cfg,native)
    a.atomic_json(root/'protocol.json',dict(protocol=declared,identity=ident))
    symbols=training_symbols()
    raw,records,record,directory=run_deck(root,'training',frontend,cfg,symbols,declared['training_noise_seed'],run,timeout)
    if not run:return record
    selections={name:opt.select_training_alignment(values,symbols,TRAIN_COUNT) for name,values in records.items()}
    frozen=dict(schema_version=1,protocol=declared,identity=ident,selections=selections,
                training_run=record,complete_ADC_verified=False,
                freeze_statement='Hardware,phase,integerlags,ADCranges,normalizations,FFEweights/biasandthresholdsfrozen independentlyatbothnodes beforeholdout.')
    a.atomic_json(frozen_path,frozen)
    record['status']='training_complete_frozen'
    record['frozen_file_sha256']=a.digest(frozen_path)
    record['selection_summary']={point:{k:choice[k] for k in (
        'integer_symbol_lag','ADC_fullscale_differential_Vpp','raw_FFE_score','ADC_score')}
                                 for point,choice in selections.items()}
    a.atomic_json(directory/'run_summary.json',record)
    return record


def validate(root,frontend,cfg,native,kind,run,timeout):
    path=root/'frozen.json'
    frozen,sha=opt.read_json_snapshot(path)
    if identity(frontend,cfg,native)!=frozen['identity']:
        raise ValueError('Hardware/nativecards/scripts differ from frozen training identity')
    declared=frozen['protocol']
    if declared['training_data_seed']!=TRAIN_SEED or declared['validation_data_seed']!=VALID_SEED:
        raise ValueError('Frozen seeds differ from fixed study protocol')
    condition=next(x for x in declared['validation_conditions'] if x['kind']==kind)
    ledger=a.PROJECT/'results/adc_backend_pam4_r5_holdout_usage.json'
    used=json.loads(ledger.read_text()) if ledger.exists() else []
    ident=opt.canonical_hash(dict(protocol=declared,identity=frozen['identity'],selections=frozen['selections']))
    for entry in used:
        if entry['validation_data_seed']==VALID_SEED and entry['choice_identity']!=ident:
            raise ValueError('Holdout seed reserved for a different frozen design; require explicitnewstudyandnewseeds')
    reservation=dict(validation_data_seed=VALID_SEED,choice_identity=ident,study=str(root),
                     frozen_file_sha256=sha,predeclared_conditions=declared['validation_conditions'])
    if run and reservation not in used:
        used.append(reservation)
        a.atomic_json(ledger,used)
    symbols=validation_symbols()
    raw,records,record,directory=run_deck(root,'validation_'+kind,frontend,cfg,symbols,condition['noise_seed'],run,timeout)
    record['frozen_file_sha256_before_run']=sha
    if not run:return record
    if a.digest(path)!=sha:raise ValueError('Frozen choices changed duringvalidation')
    result={}
    for point,values in records.items():
        choice=frozen['selections'][point]
        samples,labels,times=pi.aligned_window(values,symbols,choice['integer_symbol_lag'],TRAIN_COUNT,VALID_COUNT)
        ss,ll=samples[TRAIN_COUNT:],labels[TRAIN_COUNT:]
        result[point]=dict(metrics=opt.evaluate_frozen(ss,ll,choice['frozen_detectors']),
                           integer_symbol_lag=choice['integer_symbol_lag'],sample_count=len(ss),
                           held_min_V=min(ss),held_max_V=max(ss),held_Vppd=max(ss)-min(ss),
                           first_read_s=times[TRAIN_COUNT],last_read_s=times[-1])
    # A common fullholdout integration interval allows directpoweraccounting.
    lo=result['primary']['first_read_s']
    hi=result['primary']['last_read_s']+pi.UI
    record.update(status='validation_complete',results=result,VDD_power=power(raw,lo,hi),
                  frozen_file_unchanged=True,complete_ADC_verified=False,validation_fitting_performed=False,
                  fresh_holdout_seed=VALID_SEED,validation_input_symbols=VALID_COUNT,
                  FFE_complete_windows=VALID_COUNT-16,
                  validation_label_index_range=[pi.WARMUP+TRAIN_COUNT,pi.WARMUP+TRAIN_COUNT+VALID_COUNT-1],
                  noise_conditions=dict(noisefmax_Hz=150e9 if condition['noise_seed'] else None,
                                         noisefmin_Hz=500e6 if condition['noise_seed'] else None,
                                         noise_seed=condition['noise_seed']))
    a.atomic_json(directory/'run_summary.json',record)
    return record


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=('train','validate'))
    p.add_argument('--study',required=True)
    p.add_argument('--variant',choices=sorted(VARIANTS),default='cml2_late1')
    p.add_argument('--comparator',choices=sorted(cmp.candidates()),default='in100_tail3')
    p.add_argument('--validation-kind',choices=('noiseless','noise'),default='noise')
    p.add_argument('--no-training-noise',action='store_true')
    p.add_argument('--config',type=Path,default=a.PROJECT/'configs/ctle_selected_r3.json')
    p.add_argument('--cards',type=Path,default=ng.CARD_PATH)
    p.add_argument('--run',action='store_true')
    p.add_argument('--timeout',type=int,default=1800)
    args=p.parse_args()
    if not args.study.replace('_','').isalnum():p.error('Safe studyname required')
    if not 60<=args.timeout<=7200:p.error('Timeout mustbe60..7200seconds')
    if not (a.PROJECT/'.codex_project6_owned').exists():raise ValueError('Projectmarker absent')
    frontend=json.loads(args.config.read_text())
    cfg=configuration(args.variant,args.comparator)
    native=ng.install(args.cards)
    root=a.PROJECT/'runs'/ROOT_NAME/args.study
    declared=protocol(args.variant,args.comparator,None if args.no_training_noise else TRAIN_NOISE)
    if args.mode=='train':result=train(root,frontend,cfg,native,declared,args.run,args.timeout)
    else:result=validate(root,frontend,cfg,native,args.validation_kind,args.run,args.timeout)
    print(json.dumps({k:result[k] for k in ('name','status','selection_summary','results','VDD_power','complete_ADC_verified') if k in result}),flush=True)


if __name__=='__main__':main()
