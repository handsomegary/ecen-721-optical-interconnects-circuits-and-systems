"""Render exact r5 skew decks and diffs from admitted original inputs, offline."""
import argparse
import difflib
from pathlib import Path
import sys
import olympus_common as common

PACKAGE = Path(__file__).resolve().parent
sys.path.insert(0,str(PACKAGE/'native'))
import admit
import pn_stage
from skew.prepare_skew import check_channel, deployment_baseline, write_diff


def portable_decks(plan_path, output, indices):
    """Make review copies with a PDK token; no admission record is manufactured."""
    admission = {'model_root':'__pdk_root__','original_model_root':admit.ORIGINAL_MODEL_ROOT,
                 'source_decks':{key:{'sha256':digest,'original_vm_sha256':digest}
                                 for key,digest in admit.DECK_SHA256.items()}}
    original = PACKAGE/'r5_original'
    sources = {'noiseless':(original/'quiet.scs').read_bytes(), 'noise':(original/'noise173.scs').read_bytes()}
    for data in sources.values():
        check_channel(data)
    plan = common.read(plan_path)
    output.mkdir()
    rows = []
    for index in indices:
        case = plan['cases'][index]
        source = sources['noise' if case['kind']=='pam4_noise' else 'noiseless']
        deck, profile = pn_stage.render_deck(source,admission,case)
        baseline_case = dict(case)
        baseline_case.pop('pvt_corner',None)
        base = deployment_baseline(source,admission,baseline_case)
        path = output/case['case_id']
        common.need(path.resolve().parent==output.resolve(), 'Invalid portable case path')
        path.mkdir()
        (path/'bench.scs').write_bytes(deck)
        if case.get('pvt_corner') is True:
            (path/'la5_foundry_corners.scs').write_bytes((PACKAGE/'pvt/reference/la5_foundry_corners.scs').read_bytes())
        diff = ''.join(difflib.unified_diff(base.decode('ascii').splitlines(keepends=True),
                  deck.decode('ascii').splitlines(keepends=True),'r5_parent_path_only.scs','bench.scs'))
        (path/'stimulus_overlay.diff').write_bytes(diff.encode('ascii'))
        row = dict(case,index=index,portable_deck_sha256=profile['staged_deck_sha256'],
                   diff_sha256=common.sha(path/'stimulus_overlay.diff'))
        common.write_new(path/'case.json',row)
        rows.append(row)
    common.write_new(output/'portable_cases.json',{'status':'REVIEW_COPY_REQUIRES_RUNTIME_MODEL_ADMISSION',
        'placeholder':'__pdk_root__','plan_sha256':common.sha(plan_path),'cases':rows,'solver_runs':0})


def stage(admission, plan_path, output, indices):
    plan = common.read(plan_path)
    rows = []
    common.need(indices and len(indices)==len(set(indices)) and all(0<=i<len(plan['cases']) for i in indices),
                'Invalid or repeated case index')
    output.mkdir()
    for index in indices:
        case = plan['cases'][index]
        case_dir = output/case['case_id']
        common.need(case_dir.resolve().parent == output.resolve(), 'Invalid case path')
        profile = pn_stage.prepare(admission,plan_path,index,case_dir)
        common.write_new(case_dir/'case.json',case)
        proof = write_diff(admission,case_dir)
        rows.append({'case_id':case['case_id'],'index':index,'deck_sha256':profile['staged_deck_sha256'],
                     'diff_sha256':proof['diff_sha256']})
    common.write_new(output/'staged_cases.json',{'plan_sha256':common.sha(plan_path),'cases':rows,'solver_runs':0})


if __name__=='__main__':
    p = argparse.ArgumentParser(description=__doc__)
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument('--admission',type=Path)
    source.add_argument('--portable',action='store_true')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--index',type=int,action='append')
    p.add_argument('--pvt-transient',action='store_true')
    a = p.parse_args()
    plan = PACKAGE/('pvt/transient_plan.json' if a.pvt_transient else 'skew/skew_plan.json')
    indices = a.index if a.index is not None else list(range(len(common.read(plan)['cases'])))
    if a.portable:
        portable_decks(plan,a.output,indices)
    else:
        stage(a.admission,plan,a.output,indices)
