"""Verify the handoff payload, exact source pins and case/diff inventory offline."""
from collections import Counter
from pathlib import Path
import sys
import olympus_common as common

ROOT = Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'native'))
import admit


def verify(root):
    manifest = common.read(root/'DELIVERY_MANIFEST.json')
    for name,digest in manifest['files_sha256'].items():
        rel = Path(name)
        common.need(not rel.is_absolute() and '..' not in rel.parts, 'Unsafe manifest entry')
        common.need(common.sha(root/rel)==digest, 'Payload SHA differs: '+name)
    original = root/'r5_original'
    common.need(common.sha(original/'quiet.scs')==admit.DECK_SHA256['noiseless'] and
                common.sha(original/'noise173.scs')==admit.DECK_SHA256['noise'] and
                common.sha(original/'frozen.json')==admit.FROZEN_SHA256, 'Genuine r5 source pins differ')
    frozen = common.read(original/'frozen.json')
    admit.validate_frozen(frozen)
    for name,digest in dict(frozen['identity']['scripts'],**admit.AUXILIARY_SHA256).items():
        common.need(common.sha(original/'source_dir'/name)==digest, 'Original scorer input SHA differs: '+name)
    for path,plan,count in [('portable_skew_decks','skew/skew_plan.json',77),
                           ('portable_pvt_transient','pvt/transient_plan.json',2)]:
        profiles = common.read(root/path/'portable_cases.json')
        cases = common.read(root/plan)['cases']
        common.need(profiles['solver_runs']==0 and len(cases)==len(profiles['cases'])==count and
                    profiles['plan_sha256']==common.sha(root/plan),'Portable source/plan inventory differs')
        for index,(row,case) in enumerate(zip(profiles['cases'],cases)):
            directory = root/path/case['case_id']
            common.need(row['index']==index and row['case_id']==case['case_id'] and
                        common.read(directory/'case.json')==row and
                        common.sha(directory/'bench.scs')==row['portable_deck_sha256'] and
                        common.sha(directory/'stimulus_overlay.diff')==row['diff_sha256'], 'Portable case SHA differs')
    cases = common.read(root/'skew/skew_plan.json')['cases']
    common.need(Counter(x['kind'] for x in cases)=={'pam4_noiseless':9,'pam4_noise':60,'tone_dm':4,'tone_cm':4},'Skew census differs')
    nominal_ac = (root/'pvt/cases/nominal_parent.scs.txt').read_bytes()
    token = b'__pdk_root__'
    common.need(nominal_ac.count(token)==1, 'Expected one original AC model-root token')
    original_ac = nominal_ac.replace(token, admit.ORIGINAL_MODEL_ROOT.encode('utf-8'))
    import hashlib
    common.need(hashlib.sha256(original_ac).hexdigest()==
                'ee2035953b1938121b2c0730206bbff29d2cf05e0a040ea77b281ab354f8a1ca', 'Historical focus55 optimizer deck SHA differs')
    base = root/'pvt/cases'
    pvt = common.read(base/'pvt_ac_matrix.json')['cases']
    common.need(len(pvt)==27 and (base/'case_ids.txt').read_text(encoding='utf-8').splitlines()==
                [case['case_id'] for case in pvt], 'PVT case list differs')
    for case in pvt:
        directory = base/case['case_id']
        common.need(common.read(directory/'case.json')==case and
                    common.sha(directory/'bench.scs')==case['bench_sha256'], 'PVT deck SHA differs')
    return {'status':'OFFLINE_SOURCE_SHA_VERIFIED','files':len(manifest['files_sha256']),
            'decks':len(pvt)+77+2,'private_model_readback':'ON_OLYMPUS_BEFORE_RUN','new_solver_runs':0}


if __name__=='__main__':
    import json
    print(json.dumps(verify(ROOT),indent=2))
