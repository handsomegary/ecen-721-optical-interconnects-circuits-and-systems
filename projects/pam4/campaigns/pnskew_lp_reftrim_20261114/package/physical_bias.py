"""Stage and run transistor-level LP14 bias feasibility AC cases."""
import argparse
from pathlib import Path
import re

import lp_bias as old
import olympus_common as common
from recover_bias import validate_save_currents

ROOT = Path(__file__).resolve().parent
PLAN = ROOT/'physical_case_plan.json'
TARGET = 4.35


def build_plan():
    old_plan = old.build_plan()['cases']
    cases = []

    def append(c,stage,hardware,r=1800,cm=2.0):
        mode = c['bias_mode'] if hardware=='reference' else 'replica'
        cases.append(dict(c,case_id=f'lpphy_{len(cases):03d}_{c["process"]}_{hardware}_{c["drive"]}',
                          stage=stage,bias_mode=mode,hardware=hardware,ref_R_ohm=r,miller_pF=cm,
                          target_mA_per_leg=TARGET if mode=='replica' else None))

    controls = old_plan[:30]
    drivers = [c for c in controls if c['bias_mode']=='fixed_v']
    for c in controls:
        if c['bias_mode']=='reference':
            append(c,'core','reference')
    for hw in ('ideal','native_ref','native_ota','native_both'):
        for c in drivers:
            append(c,'core',hw)
    for r in (1200,1500,2100,2400):
        for c in drivers:
            if c['count_b']==0:
                append(c,'trim','native_both',r)
    for cm in (1.0,4.0):
        for c in drivers:
            if c['count_b']==0:
                append(c,'comp','native_both',1800,cm)
    return {'format':'pam4_lp_physical_bias_v1','status':'REVIEW_PENDING',
            'scope':'Zero-skew AC, OP and stationary output noise',
            'target_mA_per_leg':TARGET,'cases':cases}


def native_blocks(case, original, r5):
    _,_,tail,_ = old.DRIVE.gm.frontend_parts(original)
    pcard = old.DRIVE.gm.original.base.device_cards(r5)['P']
    lines = []
    def n(name,d,g,s='0',count=1):
        for i in range(count):
            lines.append(old.DRIVE.gm.geometry(tail['XT1p0'],f'GMSQ{name}{i}',(d,g,s,'0')))
    def p(name,d,g,s='GF_VDD',count=1):
        for i in range(count):
            lines.append(f'GMSQ{name}{i} ({d} {g} {s} GF_VDD) {pcard}')
    if case['hardware'] in ('native_ref','native_both'):
        # A beta multiplier with native 1:4 NMOS and native PMOS mirror.
        p('RPD','GMSQBP','GMSQBP',count=2)
        p('RPM','GMSQBN','GMSQBP',count=2)
        n('RND','GMSQBN','GMSQBN')
        n('RNS','GMSQBP','GMSQBN','GMSQRS',count=4)
        lines.append(f'GMSQRR (GMSQRS 0) resistor r={case["ref_R_ohm"]}')
        n('RNM','GMSR_REF','GMSQBN',count=10)
        # At zero reference current the resistor pulls the startup gate high.
        # Once BN conducts, the pull-down releases the weak mirror kick.
        lines += ['GMSQSTPU (GF_VDD GMSQST) resistor r=500K',
                  'GMSQSTL (GMSQBP GMSQK) resistor r=50K']
        n('STOFF','GMSQST','GMSQBN')
        n('STON','GMSQK','GMSQST')
    if case['hardware'] in ('native_ota','native_both'):
        # A separate modest tail reference keeps the OTA alive for the
        # native-OTA / ideal-current diagnostic arm as well.
        lines.append('GMSQOR (GF_VDD GMSQOB) resistor r=33K')
        n('OBD','GMSQOB','GMSQOB')
        n('OT','GMSQOS','GMSQOB')
        n('OID','GMSQO1','GMSR_D','GMSQOS')
        n('OIR','GMSQOM','GMSR_REF','GMSQOS')
        p('OPD','GMSQOM','GMSQOM',count=2)
        p('OPM','GMSQO1','GMSQOM',count=2)
        p('OP2','GMSR_BIAS','GMSQO1',count=3)
        n('ON2','GMSR_BIAS','GMSQOB',count=2)
        lines += ['GMSQOZ (GMSQO1 GMSQMC) resistor r=3K',
                  f'GMSQOC (GMSQMC GMSR_BIAS) capacitor c={case["miller_pF"]:g}p',
                  'GMSQORF (GMSR_BIAS GMSQ_RF) resistor r=100K',
                  'GMSQOCF (GMSQ_RF 0) capacitor c=10p']
    return lines


def render(case,model_root):
    from recover_bias import fixed_render
    deck,rails,ac,dc,currents,diff = fixed_render(case,model_root)
    hw = case['hardware']
    if hw in ('reference','ideal'):
        return deck,rails,ac,dc,currents,diff
    base = old.DRIVE.gm.original.base
    original,r5 = base.load_inputs()
    save = re.search(r'^save PNC_PREP [^\n]+$',deck,re.M).group()
    if hw in ('native_ref','native_both'):
        deck,count = re.subn(r'(?m)^GMSRIREF \(GMSR_REF 0\) isource dc=[^\n]+\n','',deck)
        common.need(count==1,'Missing original current reference')
        dc.extend(('GMSQBP','GMSQBN','GMSQRS','GMSQST','GMSQK'))
    if hw in ('native_ota','native_both'):
        deck,count = re.subn(r'(?m)^GMSR(?:AMP|RF|CF) \([^\n]+\n','',deck)
        common.need(count==3,'Missing original servo')
        deck = deck.replace('FG GMSR_BIAS) resistor r=10K','FG GMSQ_RF) resistor r=10K')
        dc.extend(('GMSQOB','GMSQOS','GMSQO1','GMSQOM','GMSQ_RF'))
    deck = base.replace_once(deck,'// END GMFINE','\n'.join(native_blocks(case,original,r5))+'\n// END GMFINE')
    dc = list(dict.fromkeys(dc))
    deck = base.replace_once(deck,save,'save '+' '.join(dict.fromkeys(ac+dc+currents+list(rails))))
    validate_save_currents(deck,dict(AC_traces=ac,DC_nodes=dc,DC_currents=currents,rail_voltages_V=rails))
    return deck,rails,ac,dc,currents,base.unified(original.replace(base.MODEL_TOKEN,model_root),deck)


def stage(case,destination,model_root=None):
    return old.DRIVE.gm.stage(case,destination,model_root,renderer=render)


def diagnostic(case, model_root, kind):
    """Materialize separate startup or replica-loop review decks."""
    common.need(case['hardware']=='native_both','Choose an integrated native case')
    deck = render(case,model_root)[0]
    replace = old.DRIVE.gm.original.base.replace_once
    deck = re.sub(r'(?m)^(?:acResponse|noiseResponse) [^\n]+\n','',deck)
    if kind=='stb':
        deck = replace(deck,'GMSRCS0 (GMSR_D GMSR_BIAS 0 0)',
                       'GMSQLOOP (GMSR_BIAS GMSQ_REPG) iprobe\nGMSRCS0 (GMSR_D GMSQ_REPG 0 0)')
        return deck+'replicaSTB stb start=10 stop=1G dec=40 probe=GMSQLOOP\n'
    common.need(kind in ('startup_slow','startup_fast'),'Unknown diagnostic')
    ramp = '100u' if kind=='startup_slow' else '1u'
    vdd = case['vdd_V']
    deck = replace(deck,f'GFVDD (GF_VDD 0) vsource dc={vdd:.9g}',
                   f'GFVDD (GF_VDD 0) vsource dc=0 type=pwl wave=[0 0 {ramp} {vdd:.9g}]')
    return deck+'biasStartup tran stop=500u maxstep=100n errpreset=moderate\n'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode',choices=('verify','stage','run','diagnostic'),required=True)
    p.add_argument('--index',type=int,action='append')
    p.add_argument('--root',type=Path)
    p.add_argument('--approval',type=Path)
    p.add_argument('--model-root',type=Path)
    p.add_argument('--diagnostic',choices=('stb','startup_slow','startup_fast'))
    a = p.parse_args()
    old.DRIVE.gm.original.verify_package()
    plan = common.read(PLAN)
    common.need(plan==build_plan(),'Physical bias plan differs')
    if a.mode=='verify':
        print('Physical bias plan and manifest verified')
        return
    common.need(a.root and a.index and len(set(a.index))==len(a.index) and
                all(0<=i<len(plan['cases']) for i in a.index),'Use explicit distinct indices')
    if a.mode=='stage':
        for i in a.index:
            case = plan['cases'][i]
            stage(case,a.root.resolve()/case['case_id'],a.model_root)
        return
    if a.mode=='diagnostic':
        common.need(a.diagnostic is not None,'Select diagnostic type')
        token = old.DRIVE.gm.original.base.MODEL_TOKEN
        for i in a.index:
            case = plan['cases'][i]
            dest = a.root.resolve()/(case['case_id']+'_'+a.diagnostic)
            dest.mkdir()
            (dest/'bench.scs').write_bytes(diagnostic(case,token,a.diagnostic).encode('ascii'))
            if case['process']!='tt':
                wrapper = ROOT/'pvt/reference/la5_foundry_corners.scs'
                (dest/wrapper.name).write_bytes(wrapper.read_bytes())
        return
    common.need(len(a.index)==1 and a.approval and a.model_root,'Supply one approved case and private model root')
    old.DRIVE.run(plan['cases'][a.index[0]],a.root,a.model_root,common.read(a.approval),
                  plan=PLAN,stage_case=stage)


if __name__=='__main__':
    main()
