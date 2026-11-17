"""Reconstruct and verify the 28 LP pilot cases from compact Olympus evidence."""
import argparse
import json
from pathlib import Path
import tarfile

from audit_gmfine_op import apply_diff, sha
import gm_drive_lp as prior
import lp_summary as lp
import olympus_common as common

ROOT = Path(__file__).resolve().parent
PLAN = ROOT/'lp_pilot_plan.json'
COMPACT_SHA = '3332651d46c5b1d52fe8953ba9f79e25dae30fe625f731c0054a07a4ab8b73d5'
RECEIPT = 'raw_retirement_manual_20261113.json'


def audit(path):
    common.need(common.sha(path)==COMPACT_SHA,'Compact LP pilot SHA differs')
    cases = common.read(PLAN)['cases'][:28]
    template,_ = prior.parent.gm.original.base.load_inputs()
    n_raw, raw_bytes, checks, pairs = 0,0,[],{}
    names = ('case.json','measurements.json','run_status.json','completion.json',RECEIPT,
             'parent_diff.txt','spectre.log')
    wanted = {'run/'+case['case_id']+'/'+name for case in cases for name in names}
    with tarfile.open(path) as archive:
        files = {m.name:archive.extractfile(m).read() for m in archive.getmembers()
                 if m.isfile() and m.name in wanted}
    common.need(set(files)==wanted,'Incomplete compact LP pilot')
    for case in cases:
        case_id = case['case_id']
        records = {n:files['run/'+case_id+'/'+n] for n in names}
        stored,rec,status,done,receipt = [json.loads(records[n]) for n in names[:5]]
        common.need(all(stored[k]==v for k,v in case.items()) and
                    status['case_id']==rec['case_id']==case_id and status['exit_code']==0 and
                    status['status']=='spectre_completed' and status['plan_sha256']==common.sha(PLAN) and
                    rec['measurement_complete'] is done['measurement_complete'] is True and
                    sha(records['case.json'])==status['case_sha256'] and
                    sha(records['run_status.json'])==rec['run_status_sha256'] and
                    sha(records['measurements.json'])==done['measurement_sha256']==receipt['measurement_sha256']
                    and sha(records['spectre.log'])==status['spectre_log_sha256'] and
                    sha(records['parent_diff.txt'])==stored['staged_source_sha256']['parent_diff.txt'],
                    'Evidence SHA differs: '+case_id)
        deck = apply_diff(template.replace(prior.parent.gm.original.base.MODEL_TOKEN,
                          stored['model_preflight']['model_root']),records['parent_diff.txt'].decode('ascii'))
        deck_sha = sha(deck.encode('ascii'))
        common.need(deck_sha==status['input_deck_sha256_before']==status['input_deck_sha256_after']
                    ==rec['bench_sha256']==stored['staged_source_sha256']['bench.scs'],'Deck SHA differs')
        inventory = {(r['path'],r['sha256'],r['bytes']) for r in status['raw_inventory']}
        removed = {(r['path'],r['sha256'],r['bytes']) for r in receipt['removed']}
        common.need(inventory==removed and len(inventory)==len(receipt['removed'])
                    ==len(status['raw_inventory']),'Raw receipt differs')
        n_raw += len(removed)
        raw_bytes += sum(r[2] for r in removed)
        checks.append({'case_id':case_id,'bench_sha256':deck_sha,
                       'measurement_sha256':done['measurement_sha256']})
        pairs.setdefault((case['launch'],case['source_R_ohm'],case['probe']),{})[case['drive']] = rec

    afe = ('X_o_p','X_o_m')
    chosen = pairs['lp14lo120',25,'full']
    p = chosen['p']
    fs = p['frequency_Hz']
    ideal = pairs['ideal',25,'full']
    z = lp.hdd_at(fs,lp.modal.matrix(chosen,afe),56e9)
    z0 = lp.hdd_at(fs,lp.modal.matrix(ideal,afe),56e9)
    off = lp.hdd_at(fs,lp.modal.matrix(pairs['lp14lo120',0,'dormant'],afe),56e9)
    full = lp.hdd_at(fs,lp.modal.matrix(pairs['lp14lo120',0,'full'],afe),56e9)
    dc = p['saved_mos_oppoint']
    i_on = sum(dc[f'GMSAPCS{i}']['ids'] for i in range(14))
    i_off = sum(dc[f'GMSBPCS{i}']['ids'] for i in range(14))
    return {'format':'lp_next_prior_audit_v1','compact_sha256':COMPACT_SHA,'verified_cases':len(checks),
            'raw_files':n_raw,'raw_bytes':raw_bytes,'case_checks':checks,
            'lp14_SS_25ohm_loss_vs_same_route_ideal_dB':lp.inherited.ratio(z,z0),
            'lp14_SS_added_total_mW':1000*(sum(p['DC_supply_power_W'].values())
                                         -sum(ideal['p']['DC_supply_power_W'].values())),
            'lp14_SS_0ohm_dormant_over_selected_dBc':lp.modal.db(abs(off/(full-off))),
            'lp14_SS_one_active_leg_A':i_on,'lp14_SS_one_off_leg_A':i_off,
            'lp14_SS_dual_driver_mW_fixed_bias_estimate':4*.81*i_on*1000}


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compact',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    common.write_new(args.output,audit(args.compact))
