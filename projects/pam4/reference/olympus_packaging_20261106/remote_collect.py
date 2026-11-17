import hashlib
import io
import json
import os
import re
import stat
import sys
import tarfile
from pathlib import Path

ROOT = Path('/path/to/local/cadence-home/Desktop/cadence_projects/project6_28nm').resolve(strict=True)
CODE_EXT = {'.py', '.il', '.ocn', '.sh'}
DECK_EXT = {'.scs', '.il', '.ocn'}
SKIP_DIRS = {'raw', 'psf', '__pycache__', '.git'}
SECRET = re.compile(rb'-----BEGIN (?:OPENSSH |RSA |EC |)PRIVATE KEY-----|gh[pous]_[A-Za-z0-9]{20,}')
FOUNDRY_NOTICE = re.compile(rb'(?im)^\s*[/#*;]*\s*(?:copyright.{0,80}foundry|foundry.{0,80}(?:confidential|proprietary))')
MODEL = re.compile(rb'(?im)^\s*(?:model|\.model)\s+')
PDK_SUBCKT = re.compile(rb'(?im)^\s*(?:inline\s+)?subckt\s+(?:nmos|pmos|nmos|pmos)[A-Za-z0-9_]*')

records = []
skipped = []
seen_logical = set()
alias_dirs = []


def within(path):
    try:
        path.relative_to(ROOT)
        return True
    except ValueError:
        return False


def walk(real_dir, logical_dir, mode, ancestors=()):
    real_dir = real_dir.resolve(strict=True)
    if not within(real_dir) or real_dir in ancestors:
        skipped.append({'path': str(logical_dir), 'reason': 'outside_project_or_cycle'})
        return
    next_ancestors = ancestors + (real_dir,)
    with os.scandir(real_dir) as stream:
        entries = sorted(stream, key=lambda e: e.name)
    for entry in entries:
        logical = logical_dir / entry.name
        p = Path(entry.path)
        if entry.name in SKIP_DIRS or entry.name.endswith('.raw'):
            continue
        if entry.is_symlink():
            try:
                target = p.resolve(strict=True)
            except OSError:
                skipped.append({'path': str(logical), 'reason': 'broken_symlink'})
                continue
            if not within(target):
                skipped.append({'path': str(logical), 'reason': 'external_symlink'})
                continue
            if target.is_dir():
                alias_dirs.append(str(logical))
                walk(target, logical, mode, next_ancestors)
            elif target.is_file():
                maybe_add(target, logical, mode)
        elif entry.is_dir(follow_symlinks=False):
            walk(p, logical, mode, next_ancestors)
        elif entry.is_file(follow_symlinks=False):
            maybe_add(p, logical, mode)


def maybe_add(path, logical, mode):
    if mode == 'code' and path.suffix.lower() not in CODE_EXT:
        return
    if mode == 'deck' and path.suffix.lower() not in DECK_EXT:
        return
    if mode == 'library' and (path.name.endswith(('.cdslck', '.lock')) or 'cdslck' in path.name):
        skipped.append({'path': str(logical), 'reason': 'live_lock'})
        return
    if str(logical) in seen_logical:
        raise RuntimeError('duplicate logical path: ' + str(logical))
    actual = path.resolve(strict=True)
    if not within(actual) or not actual.is_file():
        raise RuntimeError('source outside project: ' + str(logical))
    st_before = actual.stat()
    if st_before.st_size > 16_000_000:
        raise RuntimeError('unexpectedly large selected source: ' + str(logical))
    data = actual.read_bytes()
    st_after = actual.stat()
    if st_before.st_size != len(data) or st_before.st_size != st_after.st_size or st_before.st_mtime_ns != st_after.st_mtime_ns:
        raise RuntimeError('file changed during snapshot: ' + str(logical))
    if mode != 'library' and (SECRET.search(data) or FOUNDRY_NOTICE.search(data)):
        skipped.append({'path': str(logical), 'reason': 'sensitive_source_marker'})
        return
    if path.suffix.lower() == '.scs' and (MODEL.search(data) or PDK_SUBCKT.search(data)):
        skipped.append({'path': str(logical), 'reason': 'inline_model_definition'})
        return
    arcname = 'vm_project/' + str(logical).replace(os.sep, '/')
    item = tarfile.TarInfo(arcname)
    item.size = len(data)
    item.mode = 0o755 if st_before.st_mode & stat.S_IXUSR else 0o644
    item.mtime = int(st_before.st_mtime)
    tar.addfile(item, io.BytesIO(data))
    seen_logical.add(str(logical))
    records.append({'path': arcname, 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data), 'category': mode})


with tarfile.open(fileobj=sys.stdout.buffer, mode='w|gz', compresslevel=6) as tar:
    for rel, mode in [('scripts', 'code'), ('p6_224g_lib', 'library'), ('runs', 'deck'), ('simulations', 'deck')]:
        source = ROOT / rel
        if not source.is_dir():
            raise RuntimeError('required project directory missing: ' + str(source))
        walk(source, Path(rel), mode)
    for rel in ['notes/ffe_viva_api_check_20261022/view_sampled_eye.il', 'notes/ffe_viva_api_check_20261022/check.ocn']:
        p = ROOT / rel
        if p.is_file() and not p.is_symlink():
            maybe_add(p, Path(rel), 'deck')
    for rel in ['cds.lib', 'start_virtuoso.sh']:
        p = ROOT / rel
        if p.is_file() and not p.is_symlink():
            maybe_add(p, Path(rel + '.vm-original'), 'library')
    manifest = json.dumps({'schema': 1, 'source_project': str(ROOT), 'records': records,
                           'materialized_alias_directories': alias_dirs, 'skipped': skipped},
                          ensure_ascii=False, indent=2).encode('utf-8') + b'\n'
    item = tarfile.TarInfo('vm_project_snapshot_manifest.json')
    item.size = len(manifest)
    item.mode = 0o644
    tar.addfile(item, io.BytesIO(manifest))
