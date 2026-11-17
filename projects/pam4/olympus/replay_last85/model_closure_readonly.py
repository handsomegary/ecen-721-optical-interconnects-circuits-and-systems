"""Hash literal transitive model includes without exporting model contents."""
import argparse
import hashlib
import json
from pathlib import Path
import re


def file_stamp(path):
    value=path.stat()
    return (value.st_dev,value.st_ino,value.st_size,value.st_mtime_ns,value.st_ctime_ns)


def strip_block_comments(text):
    r"""Exactly re.sub(r'/\*.*?\*/', '', text, flags=re.S), in linear scans.

    An unmatched opener leaves its entire tail untouched, as the old regex did.
    Repeated unmatched openers must not cause a full-tail search for each one.
    """
    pieces=[];cursor=0
    while True:
        start=text.find('/*',cursor)
        if start<0:
            pieces.append(text[cursor:]);break
        end=text.find('*/',start+2)
        if end<0:
            pieces.append(text[cursor:]);break
        pieces.append(text[cursor:start]);cursor=end+2
    return ''.join(pieces)


def canonical(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def closure(deck, roots):
    resolved={};hashed_stamps={}
    def resolve(path):
        path=Path(path)
        if not path.is_absolute():path=Path.cwd()/path
        key=str(path)
        if key not in resolved:
            target=path.resolve(strict=True)
            resolved[key]=target
            # Repeated include sections commonly resolve the same few files.
            # Cache both the literal spelling and its canonical alias.
            resolved.setdefault(str(target),target)
        return resolved[key]
    deck=resolve(deck)
    roots={tag:resolve(path) for tag,path in roots.items()}
    nodes={};visiting=set();edges=[]
    def normalized_path(path):
        if path==deck:return '@DECK@'
        matches=[]
        for tag,root in roots.items():
            try:matches.append((len(root.parts),'@'+tag+'@/'+path.relative_to(root).as_posix()))
            except ValueError:pass
        if not matches:raise RuntimeError('Dependency outside explicit allowed roots: '+str(path))
        return max(matches)[1]
    def visit(path):
        path=resolve(path);key=normalized_path(path)
        if key in nodes:return
        if key in visiting:return
        visiting.add(key)
        if path.is_symlink() or not path.is_file():raise RuntimeError('Non-regular dependency')
        before=file_stamp(path);data=path.read_bytes();after=file_stamp(path)
        if before!=after:raise RuntimeError('Model changed during hashing')
        hashed_stamps[path]=after
        norm=data
        for tag,root in sorted(roots.items(),key=lambda pair:len(str(pair[1])),reverse=True):
            norm=norm.replace(str(root).encode(),('@'+tag+'@').encode())
        nodes[key]=dict(path=str(path),bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),
            normalized_sha256=hashlib.sha256(norm).hexdigest())
        text=strip_block_comments(data.decode('utf-8',errors='replace'))
        for raw in text.splitlines():
            line=raw.split('//',1)[0].strip()
            if not line or line.startswith('*'):continue
            if line.startswith('#') and not re.match(r'^#include\s+',line,re.I):continue
            match=re.match(r'^(include|\.include|#include|ahdl_include)\s+(?:"([^"]+)"|\x27([^\x27]+)\x27|(\S+))(.*)$',line,re.I)
            if not match:continue
            name=next(value for value in match.group(2,3,4) if value is not None)
            if any(char in name for char in '$`{}'):raise RuntimeError('Nonliteral include requires human checkpoint')
            target=Path(name) if Path(name).is_absolute() else path.parent/name
            target=resolve(target);targetkey=normalized_path(target)
            edges.append(dict(source=key,target=targetkey,directive=match.group(1).lower(),options=match.group(5).strip()))
            visit(target)
        visiting.remove(key)
    visit(deck)
    # Do not trust a cached resolution after an alias or source has changed.
    # Recheck each unique mapping/file once, rather than once per graph edge.
    for explicit,target in resolved.items():
        if Path(explicit).resolve(strict=True)!=target:
            raise RuntimeError('Dependency path mapping changed during closure hashing')
    for path,expected in hashed_stamps.items():
        if file_stamp(path)!=expected:
            raise RuntimeError('Model changed after hashing; closure is invalid')
    identity=dict(nodes={key:value['normalized_sha256'] for key,value in sorted(nodes.items())},
                  edges=sorted(edges,key=lambda row:json.dumps(row,sort_keys=True)))
    return dict(status='literal_transitive_include_closure_hashed',deck=str(deck),nodes=nodes,edges=edges,
        normalized_closure_sha256=canonical(identity),normalization='Only explicitly declared platform-root prefixes replaced; all other bytes preserved',
        model_contents_exported=False,limitations=['Literal include graph covers all parsed branches, not condition evaluation. Dynamic includes are rejected. Simulator builtin implementation/version is recorded separately.'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--deck',required=True)
    parser.add_argument('--root',action='append',required=True,help='TAG=absolute root; use matching TAGs on VM and Olympus')
    args=parser.parse_args();roots=dict(value.split('=',1) for value in args.root)
    print(json.dumps(closure(args.deck,roots),sort_keys=True))
