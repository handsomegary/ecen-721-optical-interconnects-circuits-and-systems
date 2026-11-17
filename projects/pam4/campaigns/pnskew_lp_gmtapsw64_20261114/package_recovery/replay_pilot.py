"""Verify GMDRIVE pilot evidence and estimate finite-source loss from its 2-port Y."""
import argparse
import json
from pathlib import Path
import tarfile

from audit_gmfine_op import apply_diff, sha
from comp_measure import at
import drive_summary as old
import gm_drive
import lp_summary as lp
import olympus_common as common
import summarize_acnext as modal

ROOT = Path(__file__).resolve().parent
PILOT_SHA = '84da22428a6263135d6dd3d8a836f05895df72017dd14432bfcf27acc2d4c108'
BASELINE_PLAN = ROOT/'baseline_case_plan.json'


def loaded(h, y, resistance):
    a,b,c,d = (resistance*z for z in y)
    a,d = 1+a,1+d
    det = a*d-b*c
    common.need(abs(det)>0,'Singular loaded-source matrix')
    e,f,g,k = h
    return [(e*d-f*c)/det,(-e*b+f*a)/det,(g*d-k*c)/det,(-g*b+k*a)/det]


def replay(path):
    common.need(common.sha(path)==PILOT_SHA,'Compact SHA differs')
    cases = common.read(BASELINE_PLAN)['cases'][:18]
    template, _ = gm_drive.gm.original.base.load_inputs()
    pairs, raw_files, raw_bytes = {},0,0
    with tarfile.open(path) as archive:
        wanted = {'run/'+c['case_id']+'/'+name for c in cases for name in
                  ('case.json','measurements.json','run_status.json','completion.json',
                   'spectre.log','parent_diff.txt','raw_retirement_manual_20261113.json')}
        files = {m.name:archive.extractfile(m).read() for m in archive.getmembers()
                 if m.isfile() and m.name in wanted}
    for case in cases:
        case_id = case['case_id']
        prefix = 'run/'+case_id+'/'
        def get(name):
            return files[prefix+name]
        stored, report, status, done, receipt = [json.loads(get(n)) for n in
            ('case.json','measurements.json','run_status.json','completion.json',
             'raw_retirement_manual_20261113.json')]
        common.need(all(stored[k]==v for k,v in case.items()) and status['case_id']==report['case_id']==case_id
                    and report['measurement_complete'] is done['measurement_complete'] is True
                    and status['status']=='spectre_completed' and status['exit_code']==0
                    and sha(get('case.json'))==status['case_sha256']
                    and sha(get('run_status.json'))==report['run_status_sha256']
                    and sha(get('measurements.json'))==done['measurement_sha256']==receipt['measurement_sha256']
                    and sha(get('spectre.log'))==status['spectre_log_sha256']
                    and sha(get('parent_diff.txt'))==stored['staged_source_sha256']['parent_diff.txt']
                    and status['plan_sha256']==common.sha(BASELINE_PLAN),'Evidence SHA differs: '+case_id)
        bench = apply_diff(template.replace(gm_drive.gm.original.base.MODEL_TOKEN,
                          stored['model_preflight']['model_root']),get('parent_diff.txt').decode('ascii'))
        common.need(sha(bench.encode('ascii'))==report['bench_sha256']==status['input_deck_sha256_after']
                    ==status['input_deck_sha256_before']==stored['staged_source_sha256']['bench.scs'],
                    'Reconstructed bench differs')
        raw = {(r['path'],r['sha256'],r['bytes']) for r in receipt['removed']}
        common.need(raw=={(r['path'],r['sha256'],r['bytes']) for r in status['raw_inventory']},
                    'Raw receipts differ')
        raw_files += len(raw)
        raw_bytes += sum(r[2] for r in raw)
        pairs.setdefault((case['launch'],case['probe']),{})[case['drive']] = report
    h = {key:old.matrix_at(pair['p']['frequency_Hz'],modal.matrix(pair,('X_o_p','X_o_m')),56e9)
         for key,pair in pairs.items()}
    out = []
    for (name,probe), pair in pairs.items():
        if probe!='full':
            continue
        y = lp.pair_y(pair)
        p = pair['p']
        fs = p['frequency_Hz']
        row = {'launch':name,'P_rail_mW':{rail:v*1000 for rail,v in p['DC_supply_power_W'].items()},
               'total_mW':sum(p['DC_supply_power_W'].values())*1000,'input_Y_56GHz_S':lp.complex_list(y)}
        cs = [d for n,d in p['saved_mos_oppoint'].items() if n.startswith('GMSAPCS')]
        if cs:
            fg, fd = (at(fs,[complex(*z) for z in p['traces'][n]],56e9)
                      for n in ('GMSAPFG','GMSAPFD'))
            row['active_P_leg'] = {'gm_S':sum(d['gm'] for d in cs),'Id_A':sum(d['ids'] for d in cs),
                                   'gate_to_drain_56GHz':lp.complex_list([fd/fg])[0]}
        loaded_rows = {}
        for r in (0,25):
            def get_h(key):
                return modal.modes(loaded(h[key],lp.pair_y(pairs[key]),r))[0]
            physical = get_h((name,'full'))
            loaded_rows[str(r)] = {'vs_independent_ideal_dB':old.ratio(physical,get_h(('ideal','full'))),
                                     'vs_matched_bypass_dB':old.ratio(physical,get_h(('bypass','full')))}
        row['reference_comparisons_by_external_R_ohm'] = loaded_rows
        if (name,'dormant') in h:
            off = modal.modes(h[(name,'dormant')])[0]
            full = modal.modes(h[(name,'full')])[0]
            row['OFF_over_selected_56GHz_dBc'] = old.ratio(off,full-off)
        out.append(row)
    return {'format':'gmdrive_lp_pilot_replay_v1','verified_cases':len(cases),
            'compact_sha256':PILOT_SHA,'raw_files':raw_files,'raw_bytes':raw_bytes,
            'source_R_0':'observed', 'source_R_25':'linear projection from two complex input Y columns',
            'rows':out}


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compact',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    common.write_new(args.output,replay(args.compact))
