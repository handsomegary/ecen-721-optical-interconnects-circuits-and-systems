#!/usr/bin/env python3
"""At most three short read-in diagnostics; no fitting or holdout completion."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time
import types

P = Path('/path/to/local/cadence-home/Desktop/cadence_projects/project6_28nm')
R = P/'runs/project6_readin_diagnostic_20261020'
S = P/'runs/adc_backend_pam4_r5_20261013/r5_late1'
SOURCE = S/'validation_noise/bench.scs'
SPECTRE = '/opt/eda/cadence/SPECTRE181/bin/spectre'
HELPER_SHA = '0c02120d0a049f22b52f5fa08392cb1498f13718c6a6a410f35c263416b25b16'
DECK_SHA = '3109f222211963fe5fcadbbb96b6605f8c4c7a8d32aa35bae178678f1d927fa2'
NOISELESS_SHA = 'ff8a466c80549cc476e8c768e56aea64cdab4ed4abb8a6b5d2709769519f716f'
MIN_FREE = 8*1024**3
CASE_LIMIT = 30
ENV_KEYS = ('PATH', 'LD_LIBRARY_PATH', 'LD_PRELOAD', 'SPECTRE_DEFAULTS',
            'CDS_AUTO_64BIT', 'CDS_Netlisting_Mode', 'LANG', 'LC_ALL',
            'CDS_LIC_FILE', 'LM_LICENSE_FILE')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def boot_id():
    return Path('/proc/sys/kernel/random/boot_id').read_text().strip()


def save(state):
    state['updated_UTC'] = datetime.datetime.utcnow().isoformat()+'Z'
    tmp = R/'status.tmp'
    with tmp.open('w') as f:
        json.dump(state, f, indent=2, sort_keys=True)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(R/'status.json')


def load_helper():
    path = Path(__file__).with_name('run_r5_reboot_resume.py')
    source = path.read_bytes()
    if hashlib.sha256(source).hexdigest() != HELPER_SHA:
        raise RuntimeError('Immutable source verifier changed')
    module = types.ModuleType('immutable_verifier')
    module.__file__ = str(path)
    exec(compile(source, str(path), 'exec'), module.__dict__)
    return module


def dependencies(text):
    """Reject relative/dynamic dependencies; never modify referenced files."""
    # Collapse continuation lines without changing bytes used by the simulator.
    text = re.sub(r'\\\r?\n', ' ', text)
    inputs = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('//') or line.startswith('*'):
            continue
        # C preprocessor dependency resolution is intentionally not reconstructed.
        if re.match(r'#\s*include\b', line):
            raise RuntimeError('CPP include requires separate dependency review')
        inc = re.match(r'(?:include|ahdl_include)\s+(.+)', line, re.I)
        if inc:
            m = re.match(r'"([^"]+)"(?:\s|$)', inc.group(1))
            if not m:
                raise RuntimeError('Unquoted or dynamic include dependency')
            inputs.append(m.group(1))
        # Input filename forms include source file, initial conditions and restart.
        for m in re.finditer(r'\b(file|wavefile|pwlfile|readic|readns|recover|restart|statefile|sparamfile|datafile)\s*=\s*("[^"]*"|[^\s]+)', line, re.I):
            value = m.group(2)
            if not (value.startswith('"') and value.endswith('"')):
                raise RuntimeError('Unquoted or dynamic input filename: '+m.group(1))
            inputs.append(value[1:-1])
        # Catch path-like strings beyond the known filename names conservatively.
        for value in re.findall(r'"([^"]*)"', line):
            if '/' in value or '\\' in value or re.search(r'\.(?:scs|sp|spi|cir|va|vams|pwl|dat|csv|txt|s\d+p)$', value, re.I):
                if value not in inputs:
                    inputs.append(value)
    for value in inputs:
        if not value.startswith('/') or any(x in value for x in ('$', '~', '`', '{', '}')):
            raise RuntimeError('Relative/dynamic path dependency: '+value)
    return sorted(set(inputs))


def rows():
    result = []
    for d in Path('/proc').iterdir():
        if not d.name.isdigit():
            continue
        try:
            fields = (d/'stat').read_text().rsplit(')', 1)[1].split()
            if fields[0] == 'Z':
                continue
            args = [x.decode('utf8', 'replace') for x in (d/'cmdline').read_bytes().split(b'\0') if x]
            try:
                cwd = os.readlink(str(d/'cwd'))
                exe = os.readlink(str(d/'exe'))
            except OSError:
                cwd, exe = None, None
            result.append(dict(pid=int(d.name), ppid=int(fields[1]), pgid=int(fields[2]),
                               sid=int(fields[3]), start=fields[19], cwd=cwd, exe=exe, args=args))
        except (FileNotFoundError, ProcessLookupError):
            pass
    return result


def under(path, root):
    if path is None:
        return False
    path, root = Path(path).resolve(), Path(root).resolve()
    return path == root or root in path.parents


def actual_spectre(row):
    return bool(row['exe'] and Path(row['exe']).name.lower() in ('spectre', 'spectre.exe'))


def gate(helper, expected_boot):
    if boot_id() != expected_boot or float(Path('/proc/uptime').read_text().split()[0]) < 600:
        raise RuntimeError('Boot changed or uptime below 600 seconds')
    if shutil.disk_usage(str(P)).free < MIN_FREE:
        raise RuntimeError('Guest free space below 8 GiB')
    memory = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
    if int(memory['MemAvailable'].split()[0]) < 2*1024**2:
        raise RuntimeError('Guest available memory below 2 GiB')
    snapshot = rows()
    spectres = [r for r in snapshot if actual_spectre(r)]
    # An unclassifiable process naming spectre must not be silently ignored.
    if any(r['exe'] is None and any(Path(a).name == 'spectre' for a in r['args'][:2]) for r in snapshot):
        raise RuntimeError('Cannot classify a possible Spectre process')
    if len(spectres) >= 2:
        raise RuntimeError('No global Spectre capacity')
    for row in snapshot:
        if row['pid'] == os.getpid():
            continue
        script = helper.script_path(row)
        if (script and under(script, P/'scripts')) or (actual_spectre(row) and under(row['cwd'], P)):
            raise RuntimeError('Another owned worker or simulator exists')
        if under(row['cwd'], P) and row['exe'] and 'python' in Path(row['exe']).name.lower():
            raise RuntimeError('Unclassified project Python worker exists')
    return len(spectres)


def members(snapshot, identity, current_boot):
    if current_boot != identity['boot_id'] or not identity.get('start'):
        raise RuntimeError('Cannot verify created session boot/start')
    found = [r for r in snapshot if r['sid'] == identity['sid'] or r['pgid'] == identity['pgid']]
    for row in found:
        if (row['sid'] != identity['sid'] or row['pgid'] != identity['pgid'] or
                not under(row['cwd'], identity['cwd']) or int(row['start']) < int(identity['start']) or
                (row['pid'] == identity['pid'] and row['start'] != identity['start'])):
            raise RuntimeError('Unsafe/unverified session member; no signal allowed')
    return found


def cleanup(identity):
    receipt = dict(signals=[], remaining=[])
    if identity is None:
        return receipt
    for sig, grace in ((signal.SIGINT, 3), (signal.SIGTERM, 5), (signal.SIGKILL, 2)):
        before = members(rows(), identity, boot_id())
        if not before:
            return receipt
        fresh = members(rows(), identity, boot_id())
        previous = {r['pid']: r['start'] for r in before}
        if any(r['pid'] in previous and previous[r['pid']] != r['start'] for r in fresh):
            raise RuntimeError('Session PID reused before cleanup')
        if not fresh:
            return receipt
        os.killpg(identity['pgid'], sig)
        receipt['signals'].append(dict(signal=int(sig), verified_members=fresh))
        end = time.monotonic()+grace
        while time.monotonic() < end:
            if not members(rows(), identity, boot_id()):
                return receipt
            time.sleep(.1)
    receipt['remaining'] = members(rows(), identity, boot_id())
    if receipt['remaining']:
        raise RuntimeError('Created session remains after bounded cleanup')
    return receipt


def phases(text):
    return dict(
        edb_visiting='Time for EDB Visiting:' in text,
        circuit_inventory='Circuit inventory:' in text,
        transient_started=bool(re.search(r'Transient Analysis|during transient analysis', text, re.I)),
        spectre18=bool(re.search(r'(?:FATAL|ERROR)\s*\(SPECTRE-18\)', text)),
        error_codes=sorted(set(re.findall(r'\b(?:SPECTRE|SFE|VACOMP)-\d+\b', text))))


def verify(helper):
    source_hashes = helper.verify_sources()
    if digest(SOURCE) != DECK_SHA or digest(S/'validation_noiseless/run_summary.json') != NOISELESS_SHA:
        raise RuntimeError('Frozen deck/noiseless reference identity changed')
    return source_hashes


def run_case(name, cleaned, helper, state):
    state['source_sha256'] = verify(helper)
    count = gate(helper, state['boot_id'])
    directory = R/name
    directory.mkdir()
    data = SOURCE.read_bytes()
    if hashlib.sha256(data).hexdigest() != DECK_SHA:
        raise RuntimeError('Source deck changed before copy')
    dep_paths = dependencies(data.decode('utf8'))
    deps = {p: digest(p) for p in dep_paths}
    (directory/'bench.scs').write_bytes(data)
    if digest(directory/'bench.scs') != DECK_SHA:
        raise RuntimeError('Copy identity mismatch')
    env = os.environ.copy()
    env['CDS_LIC_FILE'] = '<LICENSE_FILE>'
    env['LM_LICENSE_FILE'] = env['CDS_LIC_FILE']
    if cleaned:
        env.pop('LD_LIBRARY_PATH', None)
        env.pop('LD_PRELOAD', None)
    command = [SPECTRE, '-64', 'bench.scs', '-format', 'psfascii', '-raw', 'raw',
               '+log', 'spectre.log', '+lqtimeout', '30']
    record = dict(name=name, command=command, cwd=str(directory), deck_sha256=DECK_SHA,
                  dependency_sha256=deps, env_allowlist={k: env.get(k) for k in ENV_KEYS},
                  removed_environment_keys=['LD_LIBRARY_PATH', 'LD_PRELOAD'] if cleaned else [],
                  admitted_actual_spectres=count, performance_result=None, max_seconds=CASE_LIMIT)
    state['cases'].append(record)
    state['stage'] = 'dispatching_'+name
    save(state)
    child, identity = None, None
    started = time.monotonic()
    try:
        gate(helper, state['boot_id'])
        with (directory/'console.log').open('xb') as output:
            child = subprocess.Popen(command, cwd=str(directory), env=env, stdout=output,
                                     stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
            observed = next((r for r in rows() if r['pid'] == child.pid), None)
            if observed is None:
                if child.poll() is None:
                    raise RuntimeError('Cannot verify diagnostic child identity')
            else:
                if observed['sid'] != child.pid or observed['pgid'] != child.pid:
                    raise RuntimeError('New child is not isolated')
                identity = dict(pid=child.pid, start=observed['start'], sid=child.pid,
                                pgid=child.pid, boot_id=state['boot_id'], cwd=str(directory))
                record['child'] = identity
            state['stage'] = 'running_'+name
            save(state)
            while child.poll() is None and time.monotonic()-started < CASE_LIMIT:
                if boot_id() != state['boot_id'] or shutil.disk_usage(str(P)).free < MIN_FREE:
                    raise RuntimeError('Boot/free-space safety gate changed')
                time.sleep(.2)
            record['cutoff_reached'] = child.poll() is None
            record['cleanup'] = cleanup(identity)
            record['exit_code'] = child.wait(timeout=3)
    except Exception as error:
        record['runner_error'] = repr(error)
        try:
            record['cleanup'] = cleanup(identity)
        except Exception as cleanup_error:
            record['cleanup_error'] = repr(cleanup_error)
        raise
    finally:
        record['elapsed_s'] = round(time.monotonic()-started, 3)
        record['log_sha256'] = {p.name: digest(p) for p in directory.glob('*.log')}
        log = '\n'.join(p.read_text(errors='replace') for p in directory.glob('*.log'))
        record['phases'] = phases(log)
        record['readin_progressed'] = any(record['phases'][k] for k in ('edb_visiting', 'circuit_inventory', 'transient_started'))
        record['same_early_fault'] = record['phases']['spectre18'] and not record['readin_progressed']
        if digest(directory/'bench.scs') != DECK_SHA:
            record['runner_error'] = 'Copied deck bytes changed'
        save(state)
    verify(helper)
    if any(digest(p) != sha for p, sha in deps.items()):
        raise RuntimeError('Direct dependency bytes changed during diagnostic')
    if record.get('runner_error'):
        raise RuntimeError(record['runner_error'])
    return record


def run():
    import fcntl
    helper = load_helper()
    if not (P/'.codex_project6_owned').exists():
        raise RuntimeError('Project ownership marker absent')
    R.mkdir(exist_ok=True)
    lock = (R/'runner.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if (R/'status.json').exists():
        raise RuntimeError('Existing one-shot state; no replay')
    study_lock = (S/'queue.lock').open('a')
    fcntl.flock(study_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    state = dict(status='running', stage='preflight', boot_id=boot_id(),
                 pid=os.getpid(), wrapper_sha256=digest(__file__), cases=[],
                 scope='At most 3 x 30-second read-in diagnostics; no waveform parsing/fitting or holdout completion',
                 automatic_retry_permitted=False, complete_ADC_verified=False)
    save(state)
    try:
        state['source_sha256'] = verify(helper)
        dependencies(SOURCE.read_text())
        gate(helper, state['boot_id'])
        a = run_case('A_original', False, helper, state)
        if a['same_early_fault']:
            b = run_case('B_without_LD_overrides', True, helper, state)
            if b['readin_progressed'] and not b['phases']['spectre18']:
                a2 = run_case('A2_original_confirmation', False, helper, state)
                state['interpretation'] = ('Environment-dependent read-in difference reproduced; exact library cause unproven'
                                           if a2['same_early_fault'] else 'Difference not reproduced; cause remains unknown')
            else:
                state['interpretation'] = 'No successful clean-LD contrast; cause remains unknown'
        else:
            state['interpretation'] = ('Original environment progressed beyond read-in; historical fault not reproduced'
                                       if a['readin_progressed'] else 'Original outcome differs from target fault; inspect logs')
        state.update(status='complete', stage='diagnostics_complete')
    except Exception as error:
        state.update(status='needs_attention', stage='diagnostic_failure', error=repr(error))
        raise
    finally:
        save(state)
        (R/'summary.json').write_text(json.dumps(state, indent=2, sort_keys=True)+'\n')


def self_test():
    root = P/'runs/test_case'
    identity = dict(pid=10, start='123', sid=10, pgid=10, boot_id='boot', cwd=str(root))
    good = dict(pid=11, start='124', sid=10, pgid=10, cwd=str(root))
    assert members([good], identity, 'boot') == [good]
    assert members([], identity, 'boot') == []
    for change, boot in (({'cwd':str(P/'other')}, 'boot'), ({'cwd':None}, 'boot'),
                         ({'sid':12}, 'boot'), ({'pgid':12}, 'boot'),
                         ({'start':'122'}, 'boot'), ({'pid':10,'start':'125'}, 'boot'), ({}, 'different')):
        try:
            members([dict(good, **change)], identity, boot)
        except RuntimeError:
            pass
        else:
            raise AssertionError('Unsafe cleanup accepted')
    assert dependencies('include "/absolute/model.scs" section=tt\nV(x 0) vsource type=pwl wave=[0 0 1n 1]') == ['/absolute/model.scs']
    for text in ('include "relative.scs"', 'include MODEL', '#include "/foo"',
                 'V(x 0) vsource file="foo.pwl"', 'include "$HOME/foo.scs"'):
        try:
            dependencies(text)
        except RuntimeError:
            pass
        else:
            raise AssertionError('Unsafe dependency accepted')
    p = phases('FATAL (SPECTRE-18): Segmentation fault. Time for Elaboration: 1 ms')
    assert p['spectre18'] and not p['edb_visiting'] and not p['transient_started']
    assert phases('Time for EDB Visiting: CPU = 1ms')['edb_visiting']
    assert phases('Transient Analysis `tran\'')['transient_started']
    print('PASS: synthetic dependency rejection, phase parsing and exact-session cleanup gates; no signals or VM access')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--run', action='store_true')
    mode.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    self_test() if args.self_test else run()
