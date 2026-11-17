"""Common execution and evidence helpers for one new Olympus classic case."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import time

BUILD = '23.1.0.722.isr15'
GIB = 1024**3


def need(condition, message):
    if not condition:
        raise ValueError(message)


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024**2), b''):
            digest.update(block)
    return digest.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write_new(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=True, allow_nan=False)
        stream.write('\n')


def checked_root(run_root):
    path = Path(run_root).absolute()
    root = path.resolve(strict=True)
    allowed = (Path.home()/'ecen720_28nm'/'runs').resolve(strict=True)
    need(path == root and root != allowed and allowed in root.parents and root.is_dir(),
         'Use a real new campaign directory under ~/ecen720_28nm/runs')
    need(shutil.disk_usage(root).free >= 2*GIB, 'Less than 2 GiB filesystem free. Also check user quota separately.')
    return root


def environment():
    need(os.name == 'posix' and bool(os.environ.get('SLURM_JOB_ID')) and
         os.environ.get('SLURM_CPUS_PER_TASK') == '1', 'Use a reviewed one-CPU Olympus Slurm job')
    spectre = shutil.which('spectre')
    need(spectre is not None, 'Load the reviewed Spectre executable in the Slurm environment')
    env = dict(os.environ, SPECTRE_DEFAULTS='-E', PYTHONIOENCODING='utf-8')
    version = subprocess.run([spectre, '-W'], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
    need(version.returncode == 0 and BUILD in (version.stdout+version.stderr).decode('utf-8',errors='replace'),
         'Spectre build differs from historical Olympus classic build')
    return spectre, env


def classic_log(text):
    need(bool(re.search(r'(?mi)^\s*spectre completes with\s+0\s+errors\b',text)), 'No clean Spectre completion in log')
    need(not re.search(r'(?mi)^\s*(?:(?:Fast\s+)?APS\s+Enabled|Spectre\s+X\s+Enabled)\b',text),
         'Log reports a different solver mode')
    thread_counts = [int(n) for n in re.findall(r'(?mi)^\s*Multithreading Enabled:\s*(\d+)\s+threads?\b',text)]
    need(not any(n != 1 for n in thread_counts), 'Unexpected effective thread count in classic log')
    single = bool(thread_counts or re.search(r'(?mi)^.*limited to the maximum allowed number of\s+1\s+with Spectre mode\b',text))
    return {'requested_threads':1,'explicit_effective_threads':1 if single else None,
            'classic_no_acceleration_banner':True, 'solver_completion_errors':0}


def owned_file(root, path):
    path = Path(path).absolute()
    need(root in path.parents and path.resolve(strict=True) == path, 'Path escapes case or uses a symlink')
    info = path.lstat()
    need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == os.getuid(),
         'Expected a regular single-link file owned by this user')
    return path, info


def raw_inventory(root):
    raw = root/'raw'
    need(raw.is_dir() and raw.resolve(strict=True) == raw, 'Missing or redirected new raw directory')
    rows = []
    for folder, directories, files in os.walk(raw, followlinks=False):
        need(not any((Path(folder)/d).is_symlink() for d in directories), 'Raw subtree contains a symlink')
        for name in sorted(files):
            path, info = owned_file(root, Path(folder)/name)
            rows.append({'path':path.relative_to(root).as_posix(),'bytes':info.st_size,'sha256':sha(path),
                         'mtime_ns':info.st_mtime_ns,'inode':info.st_ino,'device':info.st_dev})
    need(bool(rows), 'Empty new raw directory')
    return sorted(rows,key=lambda row:row['path'])


def run_classic(directory, deck_sha, metadata, timeout_s, spectre, env):
    """Exactly one solver child. The caller supplies the already staged new case."""
    import resource
    need(sha(directory/'bench.scs') == deck_sha, 'Staged deck SHA differs before solver')
    for name in ('raw', 'run_status.json', 'execution_intent.json', 'spectre.log', 'runner_stdout.log', 'completion.json'):
        need(not (directory/name).exists(), 'Existing run evidence: '+name)
    argv = [spectre,'-64','+mt=1','bench.scs','-format','psfascii','-raw','raw','+log','spectre.log','+lqtimeout','30']
    start = time.monotonic()
    intent = dict(metadata, actual_argv=argv, started_utc=utc(), cpus_allocated=1, requested_threads=1,
                  simulator_build=BUILD, input_deck_sha256_before=deck_sha, SPECTRE_DEFAULTS='-E',
                  slurm_job_id=os.environ['SLURM_JOB_ID'], solver_mode='classic', max_solver_file_bytes=512*1024**2)
    write_new(directory/'execution_intent.json', intent)

    def child_limit():
        bound = intent['max_solver_file_bytes']
        resource.setrlimit(resource.RLIMIT_FSIZE,(bound,bound))

    with (directory/'runner_stdout.log').open('xb') as log:
        try:
            child = subprocess.run(argv,cwd=directory,env=env,stdout=log,stderr=subprocess.STDOUT,
                                   timeout=timeout_s,check=False,preexec_fn=child_limit)
            result = dict(intent, exit_code=child.returncode)
        except subprocess.TimeoutExpired:
            result = dict(intent, exit_code=124, timeout=True)
    result.update(finished_utc=utc(),spectre_wall_seconds=time.monotonic()-start,
                  child_peak_rss_KiB_after_solver=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
                  input_deck_sha256_after=sha(directory/'bench.scs'))
    if result['exit_code'] != 0 or result['input_deck_sha256_after'] != deck_sha:
        write_new(directory/'run_status.json',dict(result,status='spectre_failed_or_source_changed'))
        raise ValueError('Solver failed or deck changed. Preserve this run.')
    try:
        proof = classic_log((directory/'spectre.log').read_text(encoding='utf-8',errors='replace'))
        result.update(proof, spectre_log_sha256=sha(directory/'spectre.log'), raw_inventory=raw_inventory(directory))
    except (OSError, ValueError):
        write_new(directory/'run_status.json',dict(result,status='spectre_evidence_incomplete'))
        raise
    write_new(directory/'run_status.json',dict(result,status='spectre_completed'))
    return result


def same_identity(info, row):
    return (info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns) == (
        row['device'],row['inode'],row['bytes'],row['mtime_ns'])


def raw_in_use(rows):
    wanted = {(row['device'],row['inode']) for row in rows}
    for process in Path('/proc').iterdir():
        if not process.name.isdigit() or int(process.name) == os.getpid():
            continue
        try:
            if process.stat().st_uid != os.getuid():
                continue
            for fd in (process/'fd').iterdir():
                try:
                    info = fd.stat()
                    if (info.st_dev,info.st_ino) in wanted:
                        return True
                except FileNotFoundError:
                    continue
        except (FileNotFoundError, ProcessLookupError):
            continue
    return False


class RawRetirementDeferred(RuntimeError):
    """The case is measured, but safe removal of the remaining raw is unverified."""


def require_raw_unused(rows):
    try:
        active = raw_in_use(rows)
    except PermissionError as error:
        # A same-UID or unknown-UID process may have the file open. Keep the raw.
        raise RawRetirementDeferred('Cannot inspect process descriptors: ' + str(error)) from error
    if active:
        raise RawRetirementDeferred('A process has one or more raw files open')


def retire_case_raw(root, keepers):
    """Retire only the current Slurm case files after exact compact readback."""
    import fcntl
    need((root/'.study_owned').read_text(encoding='utf-8').strip() == os.environ['SLURM_JOB_ID'], 'Different case owner/job')
    status = read(root/'run_status.json')
    need(status['slurm_job_id'] == os.environ['SLURM_JOB_ID'] and status['status']=='spectre_completed' and
         read(root/'completion.json')['measurement_complete'] is True, 'Incomplete or foreign run')
    rows = status['raw_inventory']
    need(raw_inventory(root) == rows, 'Raw inventory changed')
    proof = {}
    required = ['bench.scs','case.json','run_status.json','spectre.log','completion.json','measurements.json']
    for name in required+list(keepers):
        rel = Path(name)
        need(not rel.is_absolute() and rel.parts and '..' not in rel.parts and rel.parts[0] != 'raw', 'Unsafe keeper')
        path,_ = owned_file(root,root/rel)
        proof[str(path)] = sha(path)
    need(proof[str(root/'measurements.json')] == read(root/'completion.json')['measurement_sha256'], 'Measurement changed')
    need(not (root/'raw_retirement.json').exists() and not (root/'raw_retirement.jsonl').exists(),
         'Existing retirement evidence; review before retry')
    removed = []
    reason = None
    try:
        require_raw_unused(rows)
        with (root/'raw_retirement.jsonl').open('x',encoding='utf-8') as journal:
            for row in rows:
                relative = Path(row['path'])
                need(relative.parts[0] == 'raw' and '..' not in relative.parts, 'Invalid raw path')
                path, info = owned_file(root,root/relative)
                need(same_identity(info,row), 'New raw identity changed')
                require_raw_unused(rows)
                need(all(sha(name)==digest for name,digest in proof.items()), 'Retained evidence changed')
                with os.fdopen(os.open(str(path),os.O_RDONLY | os.O_NOFOLLOW),'rb') as stream:
                    try:
                        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError as error:
                        raise RawRetirementDeferred('A raw file could not be locked: ' + row['path']) from error
                    digest = hashlib.sha256()
                    for block in iter(lambda:stream.read(1024**2),b''):
                        digest.update(block)
                    _, current = owned_file(root,path)
                    need(same_identity(os.fstat(stream.fileno()),row) and same_identity(current,row) and
                         digest.hexdigest()==row['sha256'], 'Raw changed before retirement')
                    path.unlink()
                event = dict(row,removed_utc=utc(),retained_measurement_sha256=proof[str(root/'measurements.json')])
                journal.write(json.dumps(event)+'\n')
                journal.flush()
                os.fsync(journal.fileno())
                removed.append(event)
    except RawRetirementDeferred as error:
        reason = str(error)
    receipt = {
        'status': 'deferred' if reason else 'completed',
        'removed': removed,
        'retained': proof,
        'removed_logical_bytes': sum(row['bytes'] for row in removed),
        'VM_or_original_study_deletion': False,
    }
    if reason:
        removed_paths = {row['path'] for row in removed}
        receipt['reason'] = reason
        receipt['remaining_raw_paths'] = [row['path'] for row in rows if row['path'] not in removed_paths]
    write_new(root/'raw_retirement.json', receipt)
    return receipt
