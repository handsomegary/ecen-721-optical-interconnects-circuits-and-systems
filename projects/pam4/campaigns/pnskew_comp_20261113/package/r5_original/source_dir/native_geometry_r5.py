#!/usr/bin/env python3
"""CDF-derived geometry library. Model-bearing cards are VM-only, Python3.6."""
import argparse
import hashlib
import json
import math
import re
from pathlib import Path
import oa_manifest as o
import p6_bench as b
from pam4_integration import _spectre_number
import psf_ascii

PROJECT=Path(o.PROJECT)
CARD_PATH=PROJECT/'configs/native_geometry_cards_r5.json'
WIDTHS=(.24e-6,.5e-6,1e-6,2e-6,3e-6)
LENGTHS=(30e-9,60e-9)
CELL='tb_p6_native_geometry_r5'
CARDS={}


def key(pmos,w,l):
    return '%s_w%d_l%d'%('p' if pmos else 'n',round(w*1e9),round(l*1e9))


def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def geometries():
    for pmos in (False,True):
        for length in LENGTHS:
            for width in WIDTHS:
                yield key(pmos,width,length),pmos,width,length


def literal(params,name):
    m=re.search(r'(?<!\w)'+re.escape(name)+r'\s*=\s*\(?\s*([^\s()]+)',params)
    if not m: raise ValueError('Missing native parameter '+name)
    return _spectre_number(m.group(1))


def validate(cards):
    expected={k for k,p,w,l in geometries()}
    if set(cards)!=expected: raise ValueError('Native geometry set differs from requested twenty cards')
    for k,pmos,w,l in geometries():
        card=cards[k]
        if card['model']!=('pmos_lvt' if pmos else 'nmos_lvt'):
            raise ValueError('Wrong model polarity '+k)
        for name,value in [('w',w),('l',l),('nf',1.),('multi',1.),('_ccoflag',1.),('_rcoflag',1.),('_rgflag',1.)]:
            if not math.isclose(literal(card['parameters'],name),value,rel_tol=1e-9,abs_tol=1e-18):
                raise ValueError('Native geometry/flag mismatch '+k+' '+name)


def install(path=CARD_PATH):
    global CARDS
    data=json.loads(Path(path).read_text())
    validate(data['cards'])
    CARDS=data['cards']
    b.mos=mos
    psf_ascii.MAX_FILE_BYTES=256*1024*1024
    return {'native_cards_sha256':digest(path),'source_netlist_sha256':data['source_netlist_sha256'],
            'native_geometry_keys':sorted(CARDS),'native_CDF_saved_reopened_verified':data['native_CDF_saved_reopened_verified']}


def mos(name,d,g,s,bulk,pmos=False,w=3e-6,l=30e-9):
    if not CARDS: raise ValueError('Install CDF-derived geometry cards before constructing MOS')
    k=key(pmos,w,l)
    if k not in CARDS: raise ValueError('Unsupported native geometry '+k)
    c=CARDS[k]
    if not math.isclose(c['w_m'],w,rel_tol=1e-9,abs_tol=1e-18) or not math.isclose(c['l_m'],l,rel_tol=1e-9,abs_tol=1e-18):
        raise ValueError('Requested geometry differs from available native card')
    return '%s (%s %s %s %s) %s %s'%(name,d,g,s,bulk,c['model'],c['parameters'])


def generate():
    rows=[o.row('VDD','analogLib','vdc',-15,30,{'PLUS':'vdd','MINUS':'gnd!'},{'vdc':'.9'}),
          o.row('VGN','analogLib','vdc',-15,22,{'PLUS':'gn','MINUS':'gnd!'},{'vdc':'.6','acm':'1'}),
          o.row('VGP','analogLib','vdc',-15,14,{'PLUS':'gp','MINUS':'gnd!'},{'vdc':'.3','acm':'1'}),
          o.row('GND','analogLib','gnd',-15,0,{'gnd!':'gnd!'})]
    for i,(k,pmos,w,l) in enumerate(geometries()):
        ws,ls='%.12gu'%(w*1e6),'%dn'%round(l*1e9)
        x,y=(i%5)*16,60-(i//5)*22
        r=o.mos('M'+k,x,y,'d'+k,'gp' if pmos else 'gn','vdd' if pmos else 'gnd!',
                'vdd' if pmos else 'gnd!',pmos=pmos,tail=l>45e-9)
        r[8]=[[n,ls if n=='l' else ws if n=='Wfg' else v] for n,v in r[8]]
        r[9]=[[n,ws if n in ('w','Wfg') else ls if n=='lgb' else v] for n,v in r[9]]
        rows.append(r)
        rows.append(o.row('VD'+k,'analogLib','vdc',x+7,y,{'PLUS':'d'+k,'MINUS':'gnd!'},{'vdc':'.45'}))
    cells=[[CELL,rows,[],[[0,70,'PROJECT6 r5 / NATIVE GEOMETRY CARD FIXTURE',.25],
                         [0,66,'CDF callbacks; widths0.24/0.5/1/2/3um; lengths30/60nm; N/P LVT',.125]]]]
    data=['; Native geometry probe, new cell only; no PDK alteration.',
          'laOaProject='+o.skill(o.PROJECT),'laOaLibrary='+o.skill(o.LIBRARY),
          'laOaCells='+o.skill(cells),'laOaNetlistCell='+o.skill(CELL),
          'laOaModels='+o.skill([[o.MODEL,'tt']]),'laOaVariables=list()','']
    out=PROJECT/'scripts/p6_oa_geometry_r5.il'
    if out.exists(): raise ValueError('Refuse to overwrite geometry intent')
    out.write_text('\n'.join(data))
    print(json.dumps({'intent':str(out),'cell':CELL,'native_geometries':20,'primitives':len(rows)}),flush=True)


def extract(source):
    source=Path(source).resolve()
    if (PROJECT/'runs').resolve() not in source.parents: raise ValueError('Require own native netlist')
    run=next((p for p in source.parents if (p/'OA_BUILD_VERIFIED').exists()),None)
    if run is None: raise ValueError('Saved/reopened CDF verification marker absent')
    text=source.read_text().replace('\\\n',' ')
    cards={}
    for k,pmos,w,l in geometries():
        m=re.search(r'^M'+re.escape(k)+r'\s+\([^)]*\)\s+(\S+)\s+(.+)$',text,re.M)
        if not m: raise ValueError('Native representative absent '+k)
        cards[k]={'model':m.group(1),'parameters':' '.join(m.group(2).split()),'w_m':w,'l_m':l,'pmos':pmos}
    validate(cards)
    data={'schema_version':1,'native_CDF_saved_reopened_verified':True,'native_OA_cell':o.LIBRARY+'/'+CELL+'/schematic',
          'source_netlist_sha256':digest(source),'source_netlist_VM_path':str(source),'cards':cards}
    if CARD_PATH.exists(): raise ValueError('Refuse to replace existing r5 native geometry cards')
    CARD_PATH.write_text(json.dumps(data,indent=2)+'\n')
    native=install(CARD_PATH)
    lines=source.read_text().split('simulatorOptions options')[0].splitlines()
    saves=['VD'+k+':p' for k,pmos,w,l in geometries()]+['VGN:p','VGP:p']
    lines+=['simulatorOptions options temp=25 tnom=25 reltol=1e-4 vabstol=1u iabstol=1p',
            'saveOptions options save=selected currents=selected','save '+' '.join(saves),
            'dcOp dc','acResponse ac start=1G stop=56G lin=2']
    directory=PROJECT/'runs/native_geometry_r5_20261013/native_fixture'
    if directory.exists(): raise ValueError('Native fixture run exists')
    status=b.run(directory,lines,timeout=120)
    if status['exit_code']!=0: raise RuntimeError('Native fixture DC/AC execution failed')
    dc=psf_ascii.parse_file(directory/'raw/dcOp.dc')
    currents={k:dc.values['VD'+k+':p'][0] for k,p,w,l in geometries()}
    if any(abs(v)<1e-9 or abs(v)>.05 for v in currents.values()): raise ValueError('Unexpected native DC current')
    result={'native':native,'native_CDF_saved_reopened_verified':True,'run_status':status,
            'geometry_count':20,'native_fixture_dc_currents_A':currents,
            'raw_sha256':{'dc':dc.sha256,'ac':digest(directory/'raw/acResponse.ac')},
            'scope':'Geometry card generation and native fixture DC/AC execution; not ADC qualification.'}
    (PROJECT/'results/native_geometry_r5_summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=['generate','extract'])
    p.add_argument('--input',type=Path)
    args=p.parse_args()
    if args.mode=='generate': generate()
    else:
        if not args.input: p.error('--input required')
        extract(args.input)
