#!/usr/bin/env python3
"""Check private VM model identities and stage path-only PVT files. No simulator."""
import argparse
import hashlib
import json
import re
from pathlib import Path

try:
    from .generate import (CORNER_FILE, CORNER_FILE_SHA256, CORNER_TOKEN, MODEL_TOKEN,
                           REFERENCE, case_id, dump, need, render_case, sha)
except ImportError:
    from generate import (CORNER_FILE, CORNER_FILE_SHA256, CORNER_TOKEN, MODEL_TOKEN,
                          REFERENCE, case_id, dump, need, render_case, sha)

MODEL_TOP = 'pdk_toplevel.scs'
SHRINK = 'pdk_model_shrink_embedded.scs'
CORE = 'pdk_model.scs'
KIT_PINS = {
    MODEL_TOP:(1579,'bd8088e1ea620dcda229d1fd16d5d63a08b594a28e78d24c4db2906cf45a71d1'),
    SHRINK:(41713,'61e73b63b3ff0cd966504939f7249e851872c57a11599b8525106e69fc3c5dea'),
    CORE:(6391681,'002300afbc872cca7c0bab744740eb74ff2cc71e770832c6e6d97c447dbfff78'),
    'res_metal.scs':(24939,'26edcca98492e43948994b72a4ec81f6afcca4b0481e70bf0e86b0c07423a414'),
}
SECTION = re.compile(rb'^\s*section\s+([A-Za-z0-9_]+)(?:\s|$)',re.M)
ROUTE = re.compile(rb'^\s*include\s+"([^"\r\n]+)"\s+section\s*=\s*([A-Za-z0-9_]+)',re.M)


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def isolated_section(data,name):
    target = re.escape(name.encode('ascii'))
    hits = re.findall(rb'(?ims)^[ \t]*section[ \t]+'+target+rb'[ \t]*\r?\n(.*?)^[ \t]*endsection(?:[ \t]+'+target+rb')?[ \t]*(?:\r?$)',data)
    need(len(hits)==1,'Missing or ambiguous model section: '+name)
    return hits[0]


def verify_wrapper(wrapper,process):
    need(sha(wrapper)==CORNER_FILE_SHA256,'Corner wrapper differs from published route bytes')
    routes = ROUTE.findall(isolated_section(wrapper,'top_'+process))
    expected = [process+suffix for suffix in ('macro_mos_moscap','_res_bip_dio_disres','_mom','_r_metal')]
    need([name.decode('ascii') for _,name in routes]==expected and
         all(path == ('{}/models/spectre/{}'.format(CORNER_TOKEN,SHRINK)).encode('ascii') for path,_ in routes),
         'Historical corner routing does not select the shrink wrapper')
    return expected


def check_kit_contents(files,process,wrapper):
    """Return observed route names only. None of the model bodies are exported."""
    required = {name.decode('ascii') for name in SECTION.findall(files[SHRINK])}
    if process=='tt':
        top = isolated_section(files[MODEL_TOP],'tt')
        route = ROUTE.findall(top)
        required_tt = [name.decode('ascii') for path,name in route
                       if path.decode('utf-8').replace('\\','/').rsplit('/',1)[-1]==SHRINK]
        need('ttmacro_mos_moscap' in required_tt,'TT root does not lead to the shrink MOS section')
        selected = required_tt
    else:
        selected = verify_wrapper(wrapper,process)
    need(set(selected)<=required, 'Required named shrink sections are absent: '+str(sorted(set(selected)-required)))
    mos = isolated_section(files[SHRINK],process+'macro_mos_moscap')
    need(re.search(rb'(?mi)\bscalefactor\s*=\s*0?\.9(?:0*)(?![\d.])',mos),
         'Active MOS wrapper does not declare retained scalefactor=0.9')
    inner = ROUTE.findall(mos)
    need(any(path.decode('utf-8').replace('\\','/').rsplit('/',1)[-1]==CORE and section.decode('ascii')==process
             for path,section in inner),'Missing same-corner core-model route')
    need(process.encode('ascii') in SECTION.findall(files[CORE]),'Selected core-model section absent')
    return selected


def verify_private_kit(pdk_root,process,wrapper=None):
    need(process in ('tt','ss','ff'), 'Only historically identified TT/SS/FF are staged')
    pdk_root = Path(pdk_root).resolve(strict=True)
    root_text = str(pdk_root)
    need(not any(c in root_text for c in ('"','\n','\r','\\')) and
         MODEL_TOKEN not in root_text and CORNER_TOKEN not in root_text, 'Unsafe Linux model-root path')
    base = pdk_root/'models'/'spectre'
    files, facts = {}, {}
    for name,(size,digest) in KIT_PINS.items():
        path = (base/name).resolve(strict=True)
        try:
            path.relative_to(pdk_root)
        except ValueError:
            raise ValueError('Model reference escapes selected private VM kit: '+name)
        need(path.is_file() and path.stat().st_size==size,'Wrong private-kit file size: '+name)
        files[name] = path.read_bytes()
        actual = hashlib.sha256(files[name]).hexdigest()
        need(len(files[name])==size and actual==digest,'Wrong private VM model SHA: '+name)
        facts[name] = {'sha256':actual,'bytes':size}
    selected = check_kit_contents(files,process,wrapper)
    return dict(schema='PAM4_PRIVATE_VM_KIT_PREFLIGHT_V1', model_root=root_text,
                process=process, root_section='top_'+process, active_shrink_sections=selected,
                kit_fingerprints=facts, active_static_mos_scale=0.9,
                static_identity_verified=True, actual_spectre_effective_scale='CHECK_ACTUAL_RUN_LOG',
                model_files_written=False, model_bodies_exported=False, simulation_started=False)


def materialize_corner(wrapper, root_text):
    token, target = CORNER_TOKEN.encode('ascii'), root_text.encode('utf-8')
    need(wrapper.count(token)==16,'Unexpected corner wrapper root token count')
    resolved = wrapper.replace(token,target)
    need(resolved.replace(target,token)==wrapper,'Corner wrapper rewrite is not byte reversible')
    return resolved


def stage_corner(process, pdk_root):
    """Return authenticated corner routing bytes and private-kit identity evidence."""
    need(process in ('ss','ff'), 'Use only the staged SS and FF routes')
    wrapper = (REFERENCE/CORNER_FILE).read_bytes()
    proof = verify_private_kit(pdk_root,process,wrapper)
    resolved = materialize_corner(wrapper,proof['model_root'])
    proof.update(corner_wrapper_sha256=sha(resolved),portable_corner_wrapper_sha256=sha(wrapper),
                 root_substitution_reversible=True)
    return resolved,proof


def read_portable_case(case_dir):
    case_dir = Path(case_dir)
    case = load(case_dir/'case.json')
    need(case.get('schema')=='PAM4_FOCUS55_PVT_AC_CASE_V1','Wrong portable PVT case schema')
    process,temp,vdd = case['process'],case['temperature_C'],case['vdd_V']
    need(case['case_id']==case_id(process,temp,vdd) and case['model_section']=='top_'+process,'PVT identity mismatch')
    deck = (case_dir/'bench.scs').read_bytes()
    parent = (case_dir.parent/'nominal_parent.scs.txt').read_bytes()
    rendered, delta = render_case(parent,process,temp,vdd)
    need(deck==rendered and sha(parent)==case['nominal_parent_sha256'] and sha(deck)==case['bench_sha256'] and
         delta==case['modified_deck_lines_one_based'], 'Portable PVT case does not match frozen delta')
    expected = {'bench.scs':sha(deck)}
    wrapper = None
    if process!='tt':
        wrapper = (case_dir/CORNER_FILE).read_bytes()
        verify_wrapper(wrapper,process)
        expected[CORNER_FILE] = sha(wrapper)
    need(case['inputs_sha256']==expected,'Portable PVT input hashes differ')
    return case,deck,wrapper


def stage(case_dir,pdk_root,runtime_dir=None):
    case_dir = Path(case_dir)
    case, portable, wrapper = read_portable_case(case_dir)
    proof = verify_private_kit(pdk_root,case['process'],wrapper)
    target = proof['model_root'].encode('utf-8')
    if case['process']=='tt':
        token = MODEL_TOKEN.encode('ascii')
        need(portable.count(token)==1,'TT deck must have exactly one portable model-root token')
        bench = portable.replace(token,target)
        need(bench.replace(target,token)==portable,'TT root rewrite is not byte reversible')
        resolved_wrapper = None
    else:
        resolved_wrapper = materialize_corner(wrapper,proof['model_root'])
        bench = portable
    hashes = {'bench.scs':sha(bench)}
    if resolved_wrapper is not None:
        hashes[CORNER_FILE] = sha(resolved_wrapper)
    proof.update(case_id=case['case_id'], portable_case_sha256=sha((case_dir/'case.json').read_bytes()),
                 portable_bench_sha256=case['bench_sha256'], runtime_bench_sha256=hashes['bench.scs'],
                 runtime_inputs_sha256=hashes, root_substitution_reversible=True)
    if runtime_dir is not None:
        runtime_dir = Path(runtime_dir)
        runtime_dir.mkdir(parents=True,exist_ok=False)
        (runtime_dir/'bench.scs').write_bytes(bench)
        (runtime_dir/'portable_bench.scs.txt').write_bytes(portable)
        (runtime_dir/'delta.diff').write_bytes((case_dir/'delta.diff').read_bytes())
        if resolved_wrapper is not None:
            (runtime_dir/CORNER_FILE).write_bytes(resolved_wrapper)
        dump(runtime_dir/'model_preflight.json',proof)
        case.update(portable_bench_sha256=case['bench_sha256'], bench_sha256=hashes['bench.scs'],
                    inputs_sha256=hashes, preflight_sha256=sha((runtime_dir/'model_preflight.json').read_bytes()),
                    execution_state='PRIVATE_KIT_PREFLIGHT_VERIFIED_AWAITING_SPECTRE')
        dump(runtime_dir/'case.json',case)
    return proof


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case-dir',type=Path,required=True)
    parser.add_argument('--pdk-root',type=Path,required=True)
    parser.add_argument('--runtime-dir',type=Path)
    args = parser.parse_args()
    print(json.dumps(stage(args.case_dir,args.pdk_root,args.runtime_dir),sort_keys=True))
