"""Verify the 54 LP NEXT power cases and extract measured driver operating points."""
import argparse
import json
from pathlib import Path
import tarfile

from audit_gmfine_op import apply_diff, sha
import bias_summary as bias
import lp_bias as design
import lp_summary as lp
import olympus_common as common

POWER_PLAN = design.ROOT/'lp_next_power_plan.json'
COMPACT_SHA = 'a67d91f420ba598f874665ef4537419f56108ca23f0286e252e5188fa1ca3639'


def audit(path):
    common.need(common.sha(path)==COMPACT_SHA,'Power compact SHA differs')
    cases = common.read(POWER_PLAN)['cases'][:54]
    template,_ = design.DRIVE.gm.original.base.load_inputs()
    names = ('case.json','measurements.json','run_status.json','completion.json',
             'raw_retirement_manual_20261113.json','parent_diff.txt','spectre.log')
    wanted = {'run/'+c['case_id']+'/'+n for c in cases for n in names}
    with tarfile.open(path) as archive:
        files = {m.name:archive.extractfile(m).read() for m in archive.getmembers()
                 if m.isfile() and m.name in wanted}
    common.need(set(files)==wanted,'Missing compact power evidence')
    pairs, raw_count, raw_bytes = {},0,0
    for c in cases:
        case_id = c['case_id']
        items = {n:files['run/'+case_id+'/'+n] for n in names}
        stored,rec,status,done,retired = [json.loads(items[n]) for n in names[:5]]
        common.need(all(stored[k]==v for k,v in c.items()) and
                    status['case_id']==rec['case_id']==case_id and status['exit_code']==0 and
                    status['status']=='spectre_completed' and status['plan_sha256']==common.sha(POWER_PLAN) and
                    rec['measurement_complete'] is done['measurement_complete'] is True and
                    sha(items['case.json'])==status['case_sha256'] and
                    sha(items['run_status.json'])==rec['run_status_sha256'] and
                    sha(items['measurements.json'])==done['measurement_sha256']==retired['measurement_sha256']
                    and sha(items['spectre.log'])==status['spectre_log_sha256'] and
                    sha(items['parent_diff.txt'])==stored['staged_source_sha256']['parent_diff.txt'],
                    'Power evidence SHA differs: '+case_id)
        parent = template.replace(design.DRIVE.gm.original.base.MODEL_TOKEN,
                                  stored['model_preflight']['model_root'])
        deck = apply_diff(parent,items['parent_diff.txt'].decode('ascii'))
        common.need(sha(deck.encode('ascii'))==status['input_deck_sha256_before']
                    ==status['input_deck_sha256_after']==rec['bench_sha256']
                    ==stored['staged_source_sha256']['bench.scs'],'Power deck SHA differs')
        inv = {(r['path'],r['bytes'],r['sha256']) for r in status['raw_inventory']}
        removed = {(r['path'],r['bytes'],r['sha256']) for r in retired['removed']}
        common.need(inv==removed and len(inv)==len(status['raw_inventory'])==len(retired['removed']),
                    'Power receipt inventory differs')
        raw_count += len(inv)
        raw_bytes += sum(r[1] for r in inv)
        pairs.setdefault((c['process'],c['launch'],c['count_b']),{})[c['drive']] = rec
    rows = []
    for (corner,launch,cb),pair in pairs.items():
        if launch!=design.SHARED:
            continue
        p = pair['p']
        fs = p['frequency_Hz']
        ports = ('X_o_p','X_o_m')
        z = lp.hdd_at(fs,lp.modal.matrix(pair,ports),56e9)
        ideal = pairs[corner,'idealz50',cb]
        ref = lp.hdd_at(fs,lp.modal.matrix(ideal,ports),56e9)
        bypass = pairs[corner,'bypass',0]['p']
        rows.append({'corner':corner,'count_b':cb,
                     'main_leg_mA':[bias.summed_ids(p,'GMSH'+l+'CS') for l in 'PM'],
                     'delta_vs_same_route_ideal_dB':lp.inherited.ratio(z,ref),
                     'main_rail_mW':1000*p['DC_supply_power_W']['GFVDD:p'],
                     'total_increment_mW':1000*(sum(p['DC_supply_power_W'].values())
                                                -sum(bypass['DC_supply_power_W'].values())),
                     'XT2p0':p['saved_mos_oppoint']['XT2p0'],
                     'ideal_XT2p0':ideal['p']['saved_mos_oppoint']['XT2p0']})
    return {'format':'lp_bias_prior_power_audit_v1','verified_cases':len(cases),
            'compact_sha256':COMPACT_SHA,'raw_files':raw_count,'raw_bytes':raw_bytes,'rows':rows}


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compact',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    common.write_new(args.output,audit(args.compact))
