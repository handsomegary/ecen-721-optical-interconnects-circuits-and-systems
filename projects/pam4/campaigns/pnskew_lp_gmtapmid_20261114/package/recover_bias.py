"""Recover LP_BIAS measurements from the original, pinned Olympus PSF."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import socket
import tempfile

import gm_select
import lp_bias
import olympus_common as common
from bias_reference import reference_current

ROOT = Path(__file__).resolve().parent
ORIGINAL_PLAN_SHA = 'e1431e2c4787ba03af5369d376ca6bfc5efe8f51207ab0341317f2256b523aec'
ORIGINAL_MANIFEST_SHA = 'c12278bc3628d1be9dd468af7be8fc50dfb3074532d28f3b9cf8612de98d7fe6'
PREVIOUS_RECOVERY_MANIFEST_SHA = '606db7a3e08da4033841f08d45778ff3c5052b23d13b0b945602b0399986f172'
PINS = ROOT/'RECOVERY_INPUTS.json'
INVALID = 'GMSRIREF:p'
COHORT = range(30,78)


def validate_save_currents(deck, record):
    """Lint the save/record contract for these generated top-level decks."""
    devices = dict(re.findall(r'(?m)^(\w+) \([^\n)]+\) (\w+)\b',deck))
    saves = set(' '.join(re.findall(r'(?m)^save[ \t]+([^\n]+)$',deck)).split())
    expected = set(record['AC_traces']+record['DC_nodes']+record['DC_currents']+
                   list(record['rail_voltages_V']))
    common.need(expected<=saves,'Missing required save: '+', '.join(sorted(expected-saves)))
    for token in sorted(saves):
        if ':' in token:
            name,suffix = token.split(':',1)
            common.need(suffix=='p' and devices.get(name) in ('vsource','vcvs'),
                        'Unsupported terminal save in LP_BIAS: '+token)


def fixed_render(case, model_root):
    deck,rails,ac,dc,currents,_ = lp_bias.render(case,model_root)
    # GMSR_REF already carries the required observation. Remove the disconnected
    # inherited control source together with its bookkeeping and terminal save.
    if case['bias_mode']=='replica':
        currents.remove(INVALID)
        deck,count = re.subn(r'(?m)^GFVCTL \(GF_CTL 0\) vsource dc=[^\n]+\n','',deck)
        common.need(count==1,'Unexpected control source')
        del rails['GFVCTL:p']
        save = re.search(r'(?m)^save PNC_PREP [^\n]+$',deck)
        common.need(save is not None,'Missing expected save line')
        deck = deck[:save.start()]+'save '+' '.join(dict.fromkeys(ac+dc+currents+list(rails)))+deck[save.end():]
    base = lp_bias.DRIVE.gm.original.base
    parent,_ = base.load_inputs()
    diff = base.unified(parent.replace(base.MODEL_TOKEN,model_root),deck)
    validate_save_currents(deck,dict(AC_traces=ac,DC_nodes=dc,DC_currents=currents,rail_voltages_V=rails))
    return deck,rails,ac,dc,currents,diff


def payload(value):
    return (json.dumps(value,indent=2,ensure_ascii=True,allow_nan=False)+'\n').encode('ascii')


def publish(case_dir, report, receipt):
    measurement = payload(report)
    digest = hashlib.sha256(measurement).hexdigest()
    receipt = dict(receipt,measurement_sha256=digest)
    receipt_file = case_dir/'recovery.json'
    if 'collector_hostname' in receipt and os.path.lexists(receipt_file):
        path,_ = common.owned_file(case_dir,receipt_file)
        existing = common.read(path)
        hostname = existing.get('collector_hostname')
        # A retry on another host can finish publishing the same measurement.
        # Keep the provenance of the collector that first published the receipt.
        if isinstance(hostname,str) and hostname:
            receipt['collector_hostname'] = hostname
    completion = {'measurement_complete':True,'measurement_sha256':digest,
                  'recovery_sha256':hashlib.sha256(payload(receipt)).hexdigest(),
                  'mode':'collect-only'}
    files = {'measurements.json':measurement,'recovery.json':payload(receipt),
             'completion.json':payload(completion)}
    # Check conflicts before writing any file. The last link commits the pair.
    for name,data in files.items():
        target = case_dir/name
        if os.path.lexists(target):
            common.need(target.is_file() and not target.is_symlink() and
                        target.stat().st_nlink==1 and target.read_bytes()==data,
                        'Existing output conflicts: '+name)
    if (case_dir/'completion.json').exists():
        common.need(all((case_dir/n).is_file() for n in files),'Incomplete committed recovery')
        return 'already_recovered'
    for name,data in files.items():
        target = case_dir/name
        if target.exists():
            continue
        with tempfile.NamedTemporaryFile(dir=case_dir,prefix='.lpbias-recovery-',delete=False) as stream:
            temp = Path(stream.name)
            try:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
                stream.close()
                os.link(temp,target)
            finally:
                temp.unlink()
        if os.name=='posix':
            directory = os.open(case_dir,os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    return 'recovered'


def verify_case(case_dir, pin):
    for name,digest in pin['files'].items():
        path,_ = common.owned_file(case_dir,case_dir/name)
        common.need(common.sha(path)==digest,'Historical SHA differs: '+name)
    case = common.read(case_dir/'case.json')
    status = common.read(case_dir/'run_status.json')
    intent = common.read(case_dir/'execution_intent.json')
    common.need(case_dir.name==case['case_id']==status['case_id']==pin['case_id'] and
                status['plan_sha256']==ORIGINAL_PLAN_SHA and status['status']=='spectre_completed' and
                status['exit_code']==status['solver_completion_errors']==0 and
                all(status[k]==v for k,v in intent.items()) and
                (case_dir/'.study_owned').read_text().strip()==status['slurm_job_id'],
                'Historical run provenance differs')
    common.need(status['case_sha256']==pin['files']['case.json'] and
                status['spectre_log_sha256']==pin['files']['spectre.log'] and
                status['input_deck_sha256_before']==status['input_deck_sha256_after']==pin['files']['bench.scs'] and
                all(pin['files'].get(n)==h for n,h in case['staged_source_sha256'].items()),
                'Original input binding differs')
    expected = {'raw/acResponse.ac','raw/dcOp.dc','raw/dcOpInfo.info','raw/logFile'}
    if case['drive']=='p':
        expected.add('raw/noiseResponse.noise')
    inventory = status['raw_inventory']
    live = common.raw_inventory(case_dir)
    common.need(len(inventory)==len(expected) and {r['path'] for r in inventory}==expected and
                common.matches_historical_inventory(inventory,live),'Historical raw inventory differs')
    return case,dict(status,raw_inventory=live)


def original_solver_hostname(case_dir, status):
    if status.get('solver_hostname'):
        return status['solver_hostname']
    log = (case_dir/'spectre.log').read_text(encoding='utf-8',errors='replace')
    header = re.search(r'(?m)^\s*User:[^\n]*?\bHost:\s+([A-Za-z0-9_.-]+)\s+HostID:', log)
    return header[1] if header else None


def verify_existing_completion(case_dir, pin):
    """Idempotent when old raw has subsequently been retired after approval."""
    names = ('measurements.json','recovery.json','completion.json')
    if not all((case_dir/name).exists() for name in names):
        return False
    for name,digest in pin['files'].items():
        path,_ = common.owned_file(case_dir,case_dir/name)
        common.need(common.sha(path)==digest,'Historical SHA differs: '+name)
    files = {n:common.owned_file(case_dir,case_dir/n)[0] for n in names}
    report,receipt,done = [common.read(files[n]) for n in names]
    common.need(report['case_id']==receipt['case_id']==pin['case_id'] and
                report['recovery_mode']==done['mode']=='collect-only' and
                report['measurement_complete'] is done['measurement_complete'] is True and
                report['bench_sha256']==pin['files']['bench.scs'] and
                report['run_status_sha256']==pin['files']['run_status.json'] and
                receipt['source_files_sha256']==pin['files'] and
                receipt['original_plan_sha256']==ORIGINAL_PLAN_SHA and
                receipt['original_manifest_sha256']==ORIGINAL_MANIFEST_SHA and
                receipt['collector_manifest_sha256'] in
                (common.sha(ROOT/'SHA256SUMS.txt'),PREVIOUS_RECOVERY_MANIFEST_SHA) and
                common.sha(files['measurements.json'])==receipt['measurement_sha256']==done['measurement_sha256'] and
                common.sha(files['recovery.json'])==done['recovery_sha256'],
                'Existing completion provenance differs')
    return True


def recover_case(case_dir, pin):
    import fcntl
    common.need(case_dir.is_dir() and case_dir.resolve()==case_dir,'Invalid original case directory')
    fd = os.open(case_dir,os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX | fcntl.LOCK_NB)
        if verify_existing_completion(case_dir,pin):
            return 'already_recovered'
        case,status = verify_case(case_dir,pin)
        deck = (case_dir/'bench.scs').read_text(encoding='ascii')
        common.need(case['bias_mode']=='replica' and case['DC_currents'].count(INVALID)==1 and
                    INVALID in deck and INVALID not in case['AC_traces'] and INVALID not in case['rail_voltages_V'],
                    'Case does not have the pinned legacy save issue')
        projected = dict(case,DC_currents=[n for n in case['DC_currents'] if n!=INVALID])
        report = gm_select.measure(case_dir,projected,status)
        report['reference_current'] = reference_current(deck,case,report)
        for instance in ('GMSRCS0',*[f'GMSH{leg}CS{i}' for leg in 'PM' for i in range(14)]):
            device = report['saved_mos_oppoint'].get(instance,{})
            common.need(all(isinstance(device.get(k),(int,float)) and math.isfinite(device[k])
                            for k in ('ids','gm','vds','vdsat')),'Incomplete driver OP: '+instance)
        # Keep the verified legacy input/status binding, with the derived
        # quantity at a new field rather than as a native PSF trace.
        report['recovery_mode'] = 'collect-only'
        _, final_status = verify_case(case_dir,pin)
        common.need(status['raw_inventory']==final_status['raw_inventory'],
                    'Live raw identity changed during collection')
        receipt = {'format':'lp_bias_recovery_v1','case_id':case['case_id'],
                   'source_files_sha256':pin['files'],'original_plan_sha256':ORIGINAL_PLAN_SHA,
                   'original_manifest_sha256':ORIGINAL_MANIFEST_SHA,
                   'collector_manifest_sha256':common.sha(ROOT/'SHA256SUMS.txt'),
                   'raw_files_verified':len(status['raw_inventory']),
                   'original_slurm_job_id':status['slurm_job_id'],
                   'solver_hostname':original_solver_hostname(case_dir,status),
                   'collector_hostname':socket.gethostname()}
        return publish(case_dir,report,receipt)
    finally:
        os.close(fd)


def approval_ok(approval, selected, index):
    authorized = approval.get('case_ids',[])
    return (approval.get('approved') is True and approval.get('platform')=='Olympus'
            and approval.get('mode')=='collect-only'
            and approval.get('original_plan_sha256')==ORIGINAL_PLAN_SHA
            and approval.get('original_manifest_sha256')==ORIGINAL_MANIFEST_SHA
            and approval.get('recovery_manifest_sha256')==common.sha(ROOT/'SHA256SUMS.txt')
            and approval.get('recovery_inputs_sha256')==common.sha(PINS)
            and isinstance(authorized,list) and len(authorized)==len(set(authorized))
            and set(selected)<=set(authorized)<=set(index))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',required=True,choices=('verify','collect-only','stage-fixed'))
    parser.add_argument('--root',type=Path)
    parser.add_argument('--approval',type=Path)
    parser.add_argument('--index',action='append',type=int)
    args = parser.parse_args()
    lp_bias.DRIVE.gm.original.verify_package()
    common.need(common.sha(lp_bias.PLAN)==ORIGINAL_PLAN_SHA,'Original plan SHA differs')
    plan = common.read(lp_bias.PLAN)['cases']
    pins = common.read(PINS)['cases']
    by_index = {p['index']:p for p in pins}
    common.need(set(by_index)==set(COHORT) and all(plan[i]['case_id']==p['case_id'] for i,p in by_index.items()),
                'Pinned cases differ from historical cohort')
    if args.mode=='verify':
        for case in plan:
            fixed_render(case,lp_bias.DRIVE.gm.original.base.MODEL_TOKEN)
        print('Historical plan, 48-case index, package and fixed save names verified')
        return
    requested = args.index or []
    common.need(requested and len(requested)==len(set(requested)) and args.root,'Select explicit unique indices and root')
    if args.mode=='stage-fixed':
        common.need(all(i in COHORT for i in requested),'Stage a historical sweep index for review')
        for i in requested:
            case = plan[i]
            lp_bias.DRIVE.gm.stage(case,args.root.resolve()/case['case_id'],
                                   renderer=fixed_render)
        return
    common.need(os.name=='posix' and args.approval and all(i in by_index for i in requested),
                'Collect-only needs the original Olympus root, approved indices and approval file')
    selected = [by_index[i]['case_id'] for i in requested]
    common.need(approval_ok(common.read(args.approval),selected,{p['case_id'] for p in pins}),
                'Approval does not bind the recovery inputs and requested cases')
    root = args.root.absolute()
    allowed = (Path.home()/'ecen720_28nm'/'runs').resolve(strict=True)
    common.need(root==root.resolve(strict=True) and allowed in root.parents,
                'Expected the original campaign under ~/ecen720_28nm/runs')
    errors = {}
    for i in requested:
        pin = by_index[i]
        try:
            print(pin['case_id'],recover_case(root/pin['case_id'],pin),flush=True)
        except (KeyError,ValueError,OSError,RuntimeError) as error:
            errors[pin['case_id']] = str(error)
            print(pin['case_id'],'collection blocked:',error,flush=True)
    if errors:
        raise SystemExit(1)


if __name__=='__main__':
    main()
