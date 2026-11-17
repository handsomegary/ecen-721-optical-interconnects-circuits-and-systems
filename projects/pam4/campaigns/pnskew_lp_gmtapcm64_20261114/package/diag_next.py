"""Extended beta STB and staged LP14 startup and tail diagnostics."""
import argparse
import math
from pathlib import Path
import re

import lp_diagnostics as prior
from beta_metrics import beta_metrics
import olympus_common as common

ROOT = Path(__file__).resolve().parent
PLAN = ROOT/'next_diagnostic_plan.json'
BASE = prior.BASE


def build_plan():
    previous = prior.build_plan()['cases']
    cases = []
    for i in (12,10,14,16,18,20,9,13,15,17,19,3,4,5,6,7,8,21,22):
        c = previous[i]
        stage = 'beta20' if c['profile']=='beta' else c['stage']
        cases.append(dict(c,case_id=f'lpnextdiag_{len(cases):02d}_{c["process"]}_{c["profile"]}_cb{c["count_b"]}',
                          stage=stage,prior_index=i))
    for i in (12,16,20):
        c = previous[i]
        cases.append(dict(c,case_id=f'lpnextdiag_{len(cases):02d}_{c["process"]}_kick_cb2',
                          stage='kick',profile='kick',prior_index=i))
    return {'format':'lp14_diag_next_v1','status':'REVIEW_PENDING','cases':cases}


def render(case,model_root):
    old = dict(case,stage='stb') if case['stage'] in ('beta20','kick') else case
    deck,rails,ac,dc,currents,diff = prior.render(old,model_root)
    if case['stage']=='beta20':
        deck = BASE.replace_once(deck,'betaSTB stb start=1 stop=1G dec=50',
                                 'betaSTB stb start=1 stop=20G dec=100')
    elif case['stage']=='kick':
        deck = prior.integrated.render(case,model_root)[0]
        deck = re.sub(r'(?m)^(?:acResponse|noiseResponse) [^\n]+\n','',deck)
        stimulus = ('GMSQKTEST (GMSR_REF 0) isource type=pwl dc=0 '
                    'wave=[0 0 5u 0 5.01u 5u 5.21u 5u 5.22u 0 15u 0 '
                    '15.01u -5u 15.21u -5u 15.22u 0 25u 0]')
        deck = BASE.replace_once(deck,'saveOptions options',stimulus+'\nsaveOptions options')
        deck = prior.replace_save(deck,prior.START_NODES+['GFVDD:p'])
        deck += 'betaKick tran stop=25u maxstep=5n errpreset=moderate\n'
    else:
        return deck,rails,ac,dc,currents,diff
    parent,_ = BASE.load_inputs()
    return deck,rails,ac,dc,currents,BASE.unified(parent.replace(BASE.MODEL_TOKEN,model_root),deck)


def stage(case,dest,model_root=None):
    return prior.integrated.mirror.prior.gm.stage(case,dest,model_root,renderer=render)


def beta_extended(trace,margins):
    result = beta_metrics(trace,margins)
    f = result.get('frequency_Hz',[])
    vectors = result.get('loopGain_real_imag',[])
    if not f or len(f)!=len(vectors):
        return result
    gain = [complex(*z) for z in vectors]
    if not all(math.isfinite(z.real) and math.isfinite(z.imag) for z in gain):
        return result
    size = list(map(abs,gain))
    complete = (f[0]<=1.01 and f[-1]>=19.8e9 and
                all(0<a<b<=a*10**.0101 for a,b in zip(f,f[1:])))
    last_octave = max(v for w,v in zip(f,size) if w>=f[-1]/2)
    last_decade = max(v for w,v in zip(f,size) if w>=f[-1]/10)
    tail = last_octave<=.10 and (last_octave<=.01 or size[-1]<=last_octave*.9)
    # Small-gain is a sufficient screen over the sampled range. A finite
    # grid does not certify opened-system poles or unmeasured frequencies.
    supports = (complete and tail and result.get('low_frequency_plateau') is True and
                result.get('peak_abs_return') is not None and
                max(size)<1 and not result.get('unity_crossings_Hz') and
                not result.get('native_instability_reported'))
    result.update(screen='beta_extended_band_evidence',
                  legacy_10dB_screen_pass=result.get('sampled_screen_pass'),
                  sampled_screen_pass=supports,extended_frequency_grid=complete,
                  high_frequency_rolloff=tail,last_octave_peak_abs_return=last_octave,
                  last_decade_peak_abs_return=last_decade,end_abs_return=size[-1],
                  status='screen_pass' if supports else result['status'] if result['passed'] is False else 'review')
    if supports:
        result['reason']='Extended sampled return supports local stability; corroborate with closed-circuit perturbation'
    elif result['passed'] is not False:
        result['reason']='Extended band or small-gain evidence unresolved'
    return result


def kick_metrics(data,case):
    from diag_metrics import _vector, TARGET_IREF_UA
    times = _vector(data,'time')
    common.need(times[0]<=1e-12 and abs(times[-1]-25e-6)<1e-10 and
                all(a<b for a,b in zip(times,times[1:])),'Incomplete perturbation time grid')
    nodes = {n:_vector(data,n,len(times)) for n in ('GF_VDD','GMSR_REF','GMSR_D','GMSQBP','GMSQK')}
    ref = [(v-r)*1e6/462 for v,r in zip(nodes['GF_VDD'],nodes['GMSR_REF'])]
    rep = [(v-r)*1e6/462 for v,r in zip(nodes['GF_VDD'],nodes['GMSR_D'])]
    kick = [(a-b)*1e6/50e3 for a,b in zip(nodes['GMSQBP'],nodes['GMSQK'])]
    target = TARGET_IREF_UA[case['process']]
    def window(lo,hi):
        ids = [i for i,t in enumerate(times) if lo<=t<hi]
        common.need(len(ids)>=2,'Missing perturbation window')
        maximum = max(abs(ref[i]/target-1) for i in ids)
        servo = max(abs(rep[i]/ref[i]-1) if ref[i]>0 else 1 for i in ids)
        release = max(abs(kick[i]) for i in ids)
        return {'max_ref_error_fraction':maximum,'max_servo_error_fraction':servo,
                'max_kick_uA':release,'pass':maximum<=.02 and servo<=.02 and release<.01}
    base = window(4e-6,5e-6)
    pos = window(14e-6,15e-6)
    neg = window(24e-6,25e-6)
    passed = all(x['pass'] for x in (base,pos,neg))
    return {'status':'pass' if passed else 'fail','passed':passed,
            'pre_pulse':base,'after_positive':pos,'after_negative':neg,
            'reference_min_uA':min(ref),'reference_max_uA':max(ref)}


def collect(root,case,status):
    if case['stage'] not in ('beta20','kick'):
        return prior.collect(root,case,status)
    log = (root/'spectre.log').read_text(encoding='utf-8',errors='replace')
    common.need(not re.search(r'SPECTRE-(8059|8061|8282|8287)\b',log),'Spectre skipped a required save')
    if case['stage']=='kick':
        result = kick_metrics(prior.raw_psf(root,status,r'raw/betaKick\.tran(?:\.tran)?'),case)
    else:
        trace = prior.raw_psf(root,status,r'raw/betaSTB(?:[-.]stb)?\.stb')
        margins = prior.raw_psf(root,status,r'raw/betaSTB[-.]margin\.stb',required=False)
        result = beta_extended(trace,margins)
        dc = prior.raw_psf(root,status,r'raw/dcOp\.dc')
        from diag_metrics import TARGET_IREF_UA, _vector
        volt = {n:_vector(dc,n,1)[0] for n in ('GF_VDD','GMSR_REF','GMSR_D','GMSQBP','GMSQK')}
        iref = (volt['GF_VDD']-volt['GMSR_REF'])*1e6/462
        kick = (volt['GMSQBP']-volt['GMSQK'])*1e6/50e3
        result.update(dc_iref_uA=iref,dc_startup_kick_uA=kick,
                      dc_replica_error_fraction=(volt['GMSR_REF']-volt['GMSR_D'])/
                      (volt['GF_VDD']-volt['GMSR_REF']) if iref>0 else None,
                      dc_iref_matches_integrated=abs(iref/TARGET_IREF_UA[case['process']]-1)<=.02)
        if (not result['dc_iref_matches_integrated'] or re.search(r'SPECTRE-16922\b',log)):
            result.update(status='fail',passed=False,sampled_screen_pass=False,reason='Invalid nonzero OP or native instability')
        elif abs(kick)>=.01:
            result.update(status='review',passed=None,sampled_screen_pass=False,reason='Startup kick still active')
    common.need(all(common.sha(root/n)==h for n,h in case['staged_source_sha256'].items()) and
                common.sha(root/'spectre.log')==status['spectre_log_sha256'],'Input or log SHA differs')
    report = dict(result,format='lp14_extended_diag_v1',case_id=case['case_id'],measurement_complete=True,
                  bench_sha256=common.sha(root/'bench.scs'),run_status_sha256=common.sha(root/'run_status.json'))
    common.write_new(root/'measurements.json',report)
    common.write_new(root/'completion.json',{'measurement_complete':True,
        'measurement_sha256':common.sha(root/'measurements.json'),'completed_utc':common.utc()})


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode',required=True,choices=('verify','stage','run'))
    p.add_argument('--index',type=int,action='append')
    p.add_argument('--root',type=Path)
    p.add_argument('--model-root',type=Path)
    p.add_argument('--approval',type=Path)
    a=p.parse_args()
    prior.integrated.mirror.prior.gm.original.verify_package()
    plan=common.read(PLAN)
    common.need(plan==build_plan(),'Plan differs')
    if a.mode=='verify':
        for c in plan['cases']:
            render(c,BASE.MODEL_TOKEN)
        print('Extended diagnosis manifest and plan verified')
        return
    cases=plan['cases']
    common.need(a.root and a.index and len(set(a.index))==len(a.index) and
                all(0<=i<len(cases) for i in a.index),'Select distinct explicit indices')
    if a.mode=='stage':
        for i in a.index:
            stage(cases[i],a.root.resolve()/cases[i]['case_id'],a.model_root)
        return
    common.need(len(a.index)==1 and a.model_root and a.approval,'Supply approved case and model root')
    approval=common.read(a.approval)
    common.need(approval.get('retire_new_raw') is not True,'Keep diagnostic raw')
    prior.integrated.phy.old.DRIVE.run(cases[a.index[0]],a.root,a.model_root,approval,
                                      plan=PLAN,stage_case=stage,collect_case=collect)


if __name__=='__main__':
    main()
