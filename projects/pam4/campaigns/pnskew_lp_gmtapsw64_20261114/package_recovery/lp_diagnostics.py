"""Startup, loop stability and finite-swing XT2 diagnostics for the integrated LP14."""
import argparse
from pathlib import Path
import math
import re

import lp_integrate as integrated
import olympus_common as common
from comp_measure import safe_raw

ROOT = Path(__file__).resolve().parent
PLAN = ROOT/'diagnostic_plan.json'
BASE = integrated.BASE
UI = 1/112e9
TAILS = [f'XT2{leg}{i}' for leg in 'pm' for i in range(8)]
START_NODES = ['GF_VDD','GMSR_REF','GMSR_D','GMSR_BIAS','GMSQBP','GMSQK','GMSQBN',
               'GMSQST','GMSQ_RF','GMSQRS','X_vdd','X_cm','X_vb']
# All 16 directed level transitions once, including identical levels.
WORD = (0,0,1,0,2,0,3,1,1,2,1,3,2,2,3,3,0)


def build_plan():
    cases = []
    controls = [c for c in integrated.build_plan()['cases']
                if c['integration']=='native_direct' and c['drive']=='p']
    def add(c,stage,profile,**kw):
        cases.append(dict(c,case_id=f'lpdiag_{len(cases):02d}_{c["process"]}_{profile}_cb{c["count_b"]}',
                          stage=stage,profile=profile,**kw))
    for c in controls:
        if c['count_b']==0:
            for profile,settle,stop in (('fast',1e-6,500e-6),('slow',100e-6,500e-6),
                                        ('restart',571e-6,1.05e-3)):
                restart = dict(restart_off_s=500e-6,restart_first_settle_s=1e-6) if profile=='restart' else {}
                add(c,'startup',profile,settle_after_s=settle,stop_s=stop,**restart)
    for c in controls:
        for profile in ('replica','beta'):
            add(c,'stb',profile)
    ss = next(c for c in controls if c['process']=='ss' and c['count_b']==2)
    for amplitude in (.4,.2):
        add(ss,'xt2',f'vppd{round(1000*amplitude)}',amplitude_Vppd=amplitude,
            settle_after_s=128*UI,stop_s=256*UI,xt2_paths=TAILS)
    return {'format':'pam4_lp_diagnostics_v1','status':'REVIEW_PENDING',
            'cases':cases}


def replace_save(deck, names):
    old = re.search(r'(?m)^save [^\n]+$',deck).group()
    return BASE.replace_once(deck,old,'save '+' '.join(names))


def startup(deck, case):
    points = {'fast':(('0',0),('1u',1)), 'slow':(('0',0),('100u',1)),
              'restart':(('0',0),('1u',1),('500u',1),('520u',0),('570u',0),('571u',1))}
    ramp = points[case['profile']]
    pattern = r'(?m)^(GFVDD|XVs|XVcm|XVb|GMS[AB]VE\d+) (\([^\n]+?\)) vsource dc=([.\d]+)$'
    def convert(m):
        name,pins,value = m.groups()
        v = float(value)
        if v==0:
            return m[0]
        wave = ' '.join(f'{t} {v*f:.9g}' for t,f in ramp)
        return f'{name} {pins} vsource dc=0 type=pwl wave=[{wave}]'
    deck,count = re.subn(pattern,convert,deck)
    common.need(count==20,'Unexpected rail/control count')
    deck = replace_save(deck,START_NODES+['GFVDD:p'])
    return deck+f'biasStartup tran stop={case["stop_s"]:.12g} maxstep=20n errpreset=moderate\n'


def stability(deck,case):
    if case['profile']=='replica':
        deck = BASE.replace_once(deck,'GMSRCS0 (GMSR_D GMSR_BIAS 0 0)',
                                 'GMSQLOOP (GMSR_BIAS GMSQ_REPG) iprobe\n'
                                 'GMSRCS0 (GMSR_D GMSQ_REPG 0 0)')
        analysis,probe = 'replicaSTB','GMSQLOOP'
    else:
        deck,count = re.subn(r'(?m)^(GMSQRPM[01] \(GMSQBN )GMSQBP ',r'\g<1>GMSQPB_GATE ',deck)
        common.need(count==2,'Expected both reference mirror gates')
        deck = BASE.replace_once(deck,'// END GMFINE','GMSQREFLOOP (GMSQBP GMSQPB_GATE) iprobe\n// END GMFINE')
        analysis,probe = 'betaSTB','GMSQREFLOOP'
    nodes = START_NODES+(['GMSQ_REPG'] if case['profile']=='replica' else ['GMSQPB_GATE'])
    return replace_save(deck,nodes+['GFVDD:p'])+f'{analysis} stb start=1 stop=1G dec=50 probe={probe}\n'


def swing(deck, case):
    _,r5 = BASE.load_inputs()
    peak = case['amplitude_Vppd']/2
    levels = [-peak,-peak/3,peak/3,peak]
    for leg,source,pre,sign in (('p','XVin','PNC_PREP',1),('m','PNCVN','PNC_PREN',-1)):
        points = [(0.,0.),(16*UI,0.),(16*UI+1e-12,sign*levels[WORD[0]]/2)]
        for i in range(1,240):
            a,b = WORD[(i-1)%16],WORD[i%16]
            if a!=b:
                start = (16+i)*UI
                points.extend(((start,sign*levels[a]/2),(start+1e-12,sign*levels[b]/2)))
        wave = ' '.join(f'{t:.12g} {v:.12g}' for t,v in points)
        old = re.search(rf'(?m)^{source} \({pre} X_cm\) vsource [^\n]+$',deck).group()
        channel = (f'{source} (TX_{leg} X_cm) vsource type=pwl wave=[{wave}]\n'
                   f'XTCH1{leg} (TX_{leg} TXA_{leg}) resistor r=100\n'
                   f'XTCC1{leg} (TXA_{leg} X_cm) capacitor c=85.26157665637249f\n'
                   f'XTCB1{leg} (TXB_{leg} X_cm TXA_{leg} X_cm) vcvs gain=1\n'
                   f'XTCH2{leg} (TXB_{leg} TXC_{leg}) resistor r=100\n'
                   f'XTCC2{leg} (TXC_{leg} X_cm) capacitor c=85.26157665637249f\n'
                   f'XTCB2{leg} ({pre} X_cm TXC_{leg} X_cm) vcvs gain=1')
        deck = BASE.replace_once(deck,old,channel)
    clocks = []
    for i in range(8):
        for stem,node in (('XCK','X_ck'),('XKB','X_kb')):
            line = re.search(rf'(?m)^{stem}{i} [^\n]+$',r5).group()
            line = line.replace('val0=0.9','val0=0.81').replace('val1=0.9','val1=0.81')
            clocks.append(line)
        for leg in 'pm':
            for sw,gate in (('XSN',f'X_ck{i}'),('XSP',f'X_kb{i}')):
                name = sw+str(i)+leg
                original = re.search(rf'(?m)^{name} [^\n]+$',deck).group()
                new = re.sub(rf'^(\w+ \(X_h{i}{leg} )\S+ ',rf'\g<1>{gate} ',original,count=1)
                deck = BASE.replace_once(deck,original,new)
    deck = BASE.replace_once(deck,'saveOptions options','\n'.join(clocks)+'\nsaveOptions options')
    signal = ['TX_p','TX_m','PNC_PREP','PNC_PREN','X_c_p','X_c_m','X_o_p','X_o_m',
              'X_s2_p','X_s2_m','X_vb','GF_VDD','GMSR_REF','GMSR_D']
    signal.extend(f'X_h{i}{leg}' for i in range(8) for leg in 'pm')
    signal.extend(f'X_ck{i}' for i in range(8))
    names = signal+[f'{d}:{x}' for d in case['xt2_paths'] for x in ('vds','vdsat','region')]
    return replace_save(deck,names)+f'xt2Swing tran stop={case["stop_s"]:.12g} maxstep=0.25p errpreset=conservative\n'


def render(case, model_root):
    deck,_,_,_,_,_ = integrated.render(case,model_root)
    deck = re.sub(r'(?m)^(?:acResponse|noiseResponse) [^\n]+\n','',deck)
    if case['stage']=='startup':
        deck = startup(deck,case)
    elif case['stage']=='stb':
        deck = stability(deck,case)
    else:
        deck = swing(deck,case)
    parent,_ = BASE.load_inputs()
    return deck,{},[],[],[],BASE.unified(parent.replace(BASE.MODEL_TOKEN,model_root),deck)


def stage(case,destination,model_root=None):
    return integrated.mirror.prior.gm.stage(case,destination,model_root,renderer=render)


def raw_psf(root,status,pattern,required=True):
    names = [r['path'].removeprefix('raw/') for r in status['raw_inventory']
             if re.fullmatch(pattern,r['path'])]
    common.need(len(names)==1 or not names and not required,'Unexpected native PSF files for '+pattern)
    return safe_raw(root,status,names[0]) if names else None


def swing_amplitudes(data,case):
    time = [v.real for v in data.values['time']]
    use = [i for i,t in enumerate(time) if t>=case['settle_after_s']]
    common.need(len(use)>1,'No settled signal trace')
    def value(node):
        vec = data.values[node]
        common.need(len(vec)==len(time) and all(math.isfinite(z.real) and z.imag==0 for z in vec),
                    'Incomplete swing trace: '+node)
        return vec
    output = {}
    for a,b in (('PNC_PREP','PNC_PREN'),('X_c_p','X_c_m'),('X_o_p','X_o_m')):
        p,n = value(a),value(b)
        diff = [p[i].real-n[i].real for i in use]
        cm = [(p[i].real+n[i].real)/2 for i in use]
        output[a+'__'+b] = {'difference_Vpp':max(diff)-min(diff),'common_mode_min_V':min(cm),
                             'common_mode_max_V':max(cm)}
    held = []
    for lane in range(8):
        clock = value(f'X_ck{lane}')
        p,n = value(f'X_h{lane}p'),value(f'X_h{lane}m')
        falls = [i for i in use if i>0 and clock[i-1].real>.405>=clock[i].real]
        common.need(bool(falls),'No track-to-hold edge for lane '+str(lane))
        for i in falls:
            before,after = clock[i-1].real,clock[i].real
            fraction = (before-.405)/(before-after)
            a,b = p[i-1].real-n[i-1].real,p[i].real-n[i].real
            held.append(a+(b-a)*fraction)
    output['held_at_clock_fall'] = {'samples':len(held),'difference_Vpp':max(held)-min(held)}
    return output


def measure(root,case,status):
    from diag_metrics import startup_metrics,stb_metrics,xt2_metrics
    log = (root/'spectre.log').read_text(encoding='utf-8',errors='replace')
    common.need(not re.search(r'SPECTRE-(8059|8061|8282|8287)\b',log),'Spectre skipped a required save')
    if case['stage']=='startup':
        result = startup_metrics(raw_psf(root,status,r'raw/biasStartup\.tran(?:\.tran)?'),case)
    elif case['stage']=='xt2':
        data = raw_psf(root,status,r'raw/xt2Swing\.tran(?:\.tran)?')
        result = xt2_metrics(data,case)
        if result.get('status')=='measured':
            result['finite_swing_planes'] = swing_amplitudes(data,case)
    else:
        name = 'replicaSTB' if case['profile']=='replica' else 'betaSTB'
        trace = raw_psf(root,status,rf'raw/{name}(?:[-.]stb)?\.stb')
        margins = raw_psf(root,status,rf'raw/{name}[-.]margin\.stb',required=False)
        if case['profile']=='beta':
            from beta_metrics import beta_metrics
            result = beta_metrics(trace,margins)
            if re.search(r'SPECTRE-16922\b',log):
                result.update(status='fail',passed=False,sampled_screen_pass=False,
                              reason='Spectre flags positive-feedback instability')
        else:
            result = stb_metrics(trace,margins)
        dc = raw_psf(root,status,r'raw/dcOp\.dc')
        result['dc_OP_V'] = {n:dc.values[n][0].real for n in ('GF_VDD','GMSR_REF','GMSR_D','GMSR_BIAS','GMSQBN')}
        result['dc_iref_uA'] = 1e6*(result['dc_OP_V']['GF_VDD']-result['dc_OP_V']['GMSR_REF'])/462
        expected = {'ss':338.3,'tt':324.8,'ff':307.1}[case['process']]
        result['dc_iref_matches_integrated'] = abs(result['dc_iref_uA']/expected-1)<=.02
        result['dc_startup_kick_uA'] = 1e6*(dc.values['GMSQBP'][0].real-dc.values['GMSQK'][0].real)/50e3
        result['dc_startup_released'] = abs(result['dc_startup_kick_uA'])<.01
        if case['profile']=='beta' and not result['dc_startup_released'] and result.get('passed') is not False:
            result.update(status='review',passed=None,sampled_screen_pass=False,
                          reason='Startup kick remains active at the beta STB operating point')
        if not result['dc_iref_matches_integrated']:
            result['passed'] = False
            result['status'] = 'fail'
            result['reason'] = 'STB linearized away from the established operating point'
            if case['profile']=='beta':
                result['sampled_screen_pass'] = False
    common.need(all(common.sha(root/n)==h for n,h in case['staged_source_sha256'].items()) and
                common.sha(root/'spectre.log')==status['spectre_log_sha256'],'Input or log SHA differs')
    return dict(result,format='pam4_lp_diagnostic_v1',case_id=case['case_id'],
                  measurement_complete=True,bench_sha256=common.sha(root/'bench.scs'),
                  run_status_sha256=common.sha(root/'run_status.json'))


def collect(root,case,status):
    report = measure(root,case,status)
    common.write_new(root/'measurements.json',report)
    common.write_new(root/'completion.json',{'measurement_complete':True,
        'measurement_sha256':common.sha(root/'measurements.json'),'completed_utc':common.utc()})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode',choices=('verify','stage','run'),required=True)
    p.add_argument('--index',type=int,action='append')
    p.add_argument('--root',type=Path)
    p.add_argument('--model-root',type=Path)
    p.add_argument('--approval',type=Path)
    a = p.parse_args()
    integrated.mirror.prior.gm.original.verify_package()
    plan = common.read(PLAN)
    common.need(plan==build_plan(),'Diagnostic plan differs')
    cases = plan['cases']
    if a.mode=='verify':
        for case in cases:
            render(case,BASE.MODEL_TOKEN)
        print('Diagnostics manifest, plan and decks verified')
        return
    common.need(a.root and a.index and len(set(a.index))==len(a.index) and
                all(0<=i<len(cases) for i in a.index),'Use distinct explicit indices')
    if a.mode=='stage':
        for i in a.index:
            stage(cases[i],a.root.resolve()/cases[i]['case_id'],a.model_root)
        return
    common.need(len(a.index)==1 and a.model_root and a.approval,'Supply an approved case and private model root')
    approval = common.read(a.approval)
    common.need(approval.get('retire_new_raw') is not True,'Keep diagnostic raw for review')
    integrated.phy.old.DRIVE.run(cases[a.index[0]],a.root,a.model_root,approval,
                                 plan=PLAN,stage_case=stage,collect_case=collect)


if __name__=='__main__':
    main()
