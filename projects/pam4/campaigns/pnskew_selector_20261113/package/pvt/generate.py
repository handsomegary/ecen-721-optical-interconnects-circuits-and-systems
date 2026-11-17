#!/usr/bin/env python3
"""Render the frozen focus55 AFE PVT grid. This program performs no simulation."""
import argparse
import difflib
import hashlib
import itertools
import json
import math
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REFERENCE = HERE / 'reference'
sys.path.insert(0, str(REFERENCE))
import p6_bench as bench

MODEL_TOKEN = '__pdk_root__'
CORNER_TOKEN = '@pdk_28nm_root@'
CORNER_FILE = 'la5_foundry_corners.scs'
BASELINE_DECK_SHA256 = '44c3fe504753a4db479c861797ee8fbe09d3e70ab9fedf273272870c9a6e9bfc'
CORNER_FILE_SHA256 = 'd2f7ce6fde421a0be9c25663e32a8e00be6a79c2caef45452eb038eccce5b297'
REFERENCE_SHA256 = {
    'p6_bench.py': 'ebdd8b406b63d347122ccc387ff934be867e48bcbcacfbcab88ed79a1d87f5e5',
    'psf_ascii.py': '8875a6b7c89ade6b419a196aa0d772b3798fa17af3cf4090a1807bce768db0e1',
}
CONFIG = dict(arch='cml', nc=8, nv=8, rc=50, rv=50, cm=.7, vb=.58,
              rdeg=250, rdeg2=250, cdeg=100e-15, cdeg2=100e-15,
              ch=5e-15, wn_sw=3e-6, wp_sw=3e-6, vdd=.9)
ANALYSIS = ('dcOp dc', 'dcOpInfo info what=oppoint where=rawfile',
            'acResponse ac start=1K stop=150G dec=50',
            'noiseResponse (X_h0p X_h0m) noise start=1M stop=56G dec=40 iprobe=XVin')
HISTORICAL_R2 = {'tt_t25_v090':21.83, 'ss_t85_v081':16.64, 'ff_tm40_v099':24.78}
PVT_POINTS = tuple(itertools.product(('tt','ss','ff'), (-40,25,85), (.81,.90,.99)))
NOMINAL = ('tt',25,.90)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def need(condition, message):
    if not condition:
        raise ValueError(message)


def dump(path, obj):
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, allow_nan=False) + '\n', encoding='utf-8')


def model_include(process):
    need(process in ('tt','ss','ff'), 'Unsupported PVT section')
    source = MODEL_TOKEN + '/models/spectre/pdk_toplevel.scs' if process == 'tt' else CORNER_FILE
    return 'include "{}" section=top_{}'.format(source, process)


def case_id(process, temperature, vdd):
    label = 'm{}'.format(-temperature) if temperature < 0 else str(temperature)
    return 'r3_pvt_ac_{}_t{}_v{:03d}'.format(process, label, round(vdd*100))


def extract_geometry(source):
    """Select the three shared exact instance tails in the frozen r3 export."""
    need(sha(source) == BASELINE_DECK_SHA256, 'Expected pinned focus55 candidate.scs bytes')
    text = source.decode('utf-8')
    patterns = {'n_l30': (r'X(?:M[12][pm][0-9]+|SN[0-7][pm])', 48),
                'n_l60': (r'XT[12][pm][0-9]+', 32),
                'p_l30': (r'XSP[0-7][pm]', 16)}
    cards = {}
    for label, (name, count) in patterns.items():
        hits = re.findall(r'^'+name+r' \([^\r\n)]*\) ([^\r\n]+)$', text, re.M)
        need(len(hits)==count and len(set(hits))==1, 'Unexpected native instance inventory: '+label)
        cards[label] = hits[0]
    return cards


def render_nominal(cards):
    for name, digest in REFERENCE_SHA256.items():
        need(sha((REFERENCE/name).read_bytes())==digest, 'Frozen generator source mismatch: '+name)
    need(set(cards)=={'n_l30','n_l60','p_l30'}, 'Wrong native card set')
    for name, tail in cards.items():
        model = 'pmos_lvt' if name=='p_l30' else 'nmos_lvt'
        length = '60n' if name=='n_l60' else '30n'
        need(tail.startswith(model+' ') and all(re.search(r'(?:^| )'+re.escape(word)+r'(?: |$)',tail)
             for word in ('l='+length,'w=3u','nf=1','multi=1','_ccoflag=1','_rcoflag=1','_rgflag=1')),
             'Geometry/parasitic flags differ: '+name)

    def native_mos(name, d, g, s, b, pmos=False, w=3e-6, l=30e-9):
        need(math.isclose(w,3e-6,rel_tol=1e-10), 'Unexpected width')
        if math.isclose(l,30e-9,rel_tol=1e-10):
            key = 'p_l30' if pmos else 'n_l30'
        else:
            need(not pmos and math.isclose(l,60e-9,rel_tol=1e-10), 'Unexpected channel length')
            key = 'n_l60'
        return '{} ({} {} {} {}) {}'.format(name,d,g,s,b,cards[key])

    original_mos = bench.mos
    try:
        bench.mos = native_mos
        circuit, saves = bench.circuit(CONFIG,'X')
    finally:
        bench.mos = original_mos
    need(sum(' nmos_lvt ' in line or ' pmos_lvt ' in line for line in circuit)==96,
         'R3 fixed-track bench must contain 96 native devices')
    head = bench.header(temp=25)
    head[1] = model_include('tt')
    lines = head+circuit+['saveOptions options save=selected currents=selected',
                         'save '+' '.join(dict.fromkeys(saves))]+list(ANALYSIS)
    return ('\n'.join(lines)+'\n').encode('ascii')


def one_replace(data, pattern, replacement, label):
    updated, hits = re.subn(pattern, lambda _: replacement, data)
    need(hits==1, 'Expected exactly one '+label)
    return updated


def render_case(nominal, process, temperature, vdd):
    need((process,temperature,vdd) in PVT_POINTS, 'Case outside the frozen PVT grid')
    changed = one_replace(nominal,rb'(?m)^'+re.escape(model_include('tt').encode('ascii'))+rb'$',
                          model_include(process).encode('ascii'),'model include')
    changed = one_replace(changed,rb'(?m)^simulatorOptions options temp=25(?= tnom=25 )',
                          ('simulatorOptions options temp='+str(temperature)).encode('ascii'),'temperature card')
    changed = one_replace(changed,rb'(?m)^XVs \(X_vdd 0\) vsource dc=0\.9$',
                          ('XVs (X_vdd 0) vsource dc={:g}'.format(vdd)).encode('ascii'),'AFE rail card')
    lines_before, lines_after = nominal.splitlines(), changed.splitlines()
    need(len(lines_before)==len(lines_after),'Unexpected deck row count')
    delta = [i+1 for i,(a,b) in enumerate(zip(lines_before,lines_after)) if a!=b]
    permitted = [i+1 for i,line in enumerate(lines_before)
                 if line.startswith((b'include ',b'simulatorOptions ',b'XVs '))]
    need(set(delta)<=set(permitted),'PVT transformation modified a non-approved row')
    return changed,delta


def generate(output, source=None):
    output = Path(output)
    cards = json.loads((REFERENCE/'native_geometry.json').read_text(encoding='utf-8'))
    need(cards['source_deck_sha256']==BASELINE_DECK_SHA256,'Wrong card provenance')
    if source is not None:
        need(extract_geometry(Path(source).read_bytes())==cards['cards'],'Original geometry mismatch')
    wrapper = (REFERENCE/CORNER_FILE).read_bytes()
    need(sha(wrapper)==CORNER_FILE_SHA256,'Published corner route template changed')
    nominal = render_nominal(cards['cards'])
    output.mkdir(parents=True,exist_ok=False)
    (output/'nominal_parent.scs.txt').write_bytes(nominal)
    case_list = []
    for process,temp,vdd in PVT_POINTS:
        identifier = case_id(process,temp,vdd)
        directory = output/identifier
        directory.mkdir()
        deck,delta = render_case(nominal,process,temp,vdd)
        (directory/'bench.scs').write_bytes(deck)
        inputs = {'bench.scs':sha(deck)}
        if process!='tt':
            (directory/CORNER_FILE).write_bytes(wrapper)
            inputs[CORNER_FILE]=sha(wrapper)
        historical = HISTORICAL_R2.get(identifier[len('r3_pvt_ac_'):])
        case = dict(schema='PAM4_FOCUS55_PVT_AC_CASE_V1', case_id=identifier, analysis_kind='pvt_ac',
                    process=process, temperature_C=temp, vdd_V=vdd, model_section='top_'+process,
                    bench_sha256=sha(deck), inputs_sha256=inputs,
                    nominal_parent_sha256=sha(nominal), nominal_parent_relative='../nominal_parent.scs.txt',
                    source_deck_sha256=BASELINE_DECK_SHA256, analysis_statements=list(ANALYSIS),
                    modified_deck_lines_one_based=delta, historical_r2_56GHz_vs_1kHz_dB=historical,
                    estimate=dict(classic_cpus=1, typical_wall_s_range=[10,120],
                                  solver_timeout_minutes=20, requested_wall_minutes=30, estimated_maximum_peak_RSS_MiB=1024,
                                  requested_memory_MiB=4096, status='PLANNING_ESTIMATE_UNMEASURED_R3'),
                    raw_files=['acResponse.ac','dcOp.dc','dcOpInfo.info','noiseResponse.noise'],
                    execution_state='PREPARED_PORTABLE_REQUIRES_PRIVATE_KIT_PREFLIGHT')
        dump(directory/'case.json',case)
        diff = ''.join(difflib.unified_diff(nominal.decode('ascii').splitlines(keepends=True),
                        deck.decode('ascii').splitlines(keepends=True),'r3_nominal/bench.scs',identifier+'/bench.scs'))
        (directory/'delta.diff').write_bytes(diff.encode('ascii'))
        case_list.append(case)
    dump(output/'pvt_ac_matrix.json',dict(schema='PAM4_FOCUS55_PVT_AC_MATRIX_V1', cases=case_list,
         runtime_requirements='Use exact private VM shrink model tree; verify with model_preflight.py',
         boundary='Standalone r3 AFE with 4 track and 4 hold primary TG loads; absolute clocked RX and layout are separate',
         historical_r2_only=HISTORICAL_R2, unsupported_processes=['SF','FS'],
         no_corner_results_measured=True))
    return case_list


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--source',type=Path,help='Optional independent readback of exact frozen published candidate.scs')
    args = parser.parse_args()
    print(json.dumps(dict(prepared_cases=len(generate(args.output,args.source)), simulation_started=False)))
