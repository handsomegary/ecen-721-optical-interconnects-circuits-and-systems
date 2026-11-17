"""Stream Spectre's switch transient PSF ASCII and retain the measured channels."""

from array import array
from collections import Counter
import hashlib
from io import StringIO
import math
from pathlib import Path

from pvt.reference.psf_ascii import (
    PsfError, SECTIONS, TOKEN, Tokens, parse_datum, parse_properties, parse_text, text_value
)


MAX_BYTES = 512 * 1024**2  # Same limit as comp_measure.safe_raw.
MAX_METADATA_BYTES = 8 * 1024**2
MAX_LINE_BYTES = 1024**2


def _lines(stream, digest, max_bytes):
    size = 0
    while raw := stream.readline(MAX_LINE_BYTES + 1):
        size += len(raw)
        if len(raw) > MAX_LINE_BYTES or size > max_bytes or b'\0' in raw:
            raise PsfError('Oversized or binary code-switch PSF ASCII')
        digest.update(raw)
        try:
            yield raw.decode('utf-8-sig' if size == len(raw) else 'utf-8')
        except UnicodeDecodeError as error:
            raise PsfError('Invalid UTF-8 in code-switch PSF ASCII') from error


def _value_tokens(lines):
    for line in lines:
        body = line.strip()
        if not body:
            continue
        if body == 'END':
            if any(rest.strip() for rest in lines):
                raise PsfError('Unexpected content after PSF END')
            return
        if body in SECTIONS:
            raise PsfError(f'Unexpected PSF section {body} inside VALUE')
        end = 0
        for match in TOKEN.finditer(body):
            if end != match.start():
                raise PsfError('Malformed PSF VALUE token')
            yield match.group(1)
            end = match.end()
        if end != len(body):
            raise PsfError('Malformed PSF VALUE record')
    raise PsfError('Missing terminal PSF END section')


class _ValueTokens(Tokens):
    def __init__(self, lines):
        self.iterator = _value_tokens(lines)
        self.next_token = next(self.iterator, None)


def parse_selected(path, required, *, max_bytes=MAX_BYTES):
    """Return PSF metadata, the file SHA256, and synchronized selected scalar traces."""
    path = Path(path)
    if not 0 < path.stat().st_size <= max_bytes:
        raise PsfError('Missing or oversized code-switch PSF ASCII')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        lines = _lines(stream, digest, max_bytes)
        metadata = StringIO()
        metadata_bytes = 0
        for line in lines:
            if line.strip() == 'VALUE':
                break
            if line.strip() == 'END':
                raise PsfError('Premature PSF END section')
            metadata_bytes += len(line.encode('utf-8'))
            if metadata_bytes > MAX_METADATA_BYTES:
                raise PsfError('Code-switch PSF metadata exceeds its bound')
            metadata.write(line)
        else:
            raise PsfError('Missing PSF VALUE section')
        metadata.write('VALUE\nEND\n')
        result = parse_text(metadata.getvalue(), source=str(path))
        if result.sweep_names != ['time']:
            raise PsfError('Code-switch PSF must declare exactly the time sweep')
        declarations = {**result.trace_types, **result.sweep_types}
        missing = required - declarations.keys()
        if missing:
            raise PsfError('Missing switch PSF trace declarations: ' + ', '.join(sorted(missing)))
        result.values = {name: array('d') for name in required}
        _read_values(_ValueTokens(lines), result, declarations)
    result.sha256 = digest.hexdigest()
    return result


def _read_values(tokens, result, declarations):
    decoded_names = {}
    counts = Counter()
    region_labels = {}
    while tokens.peek() is not None:
        token = tokens.pop()
        binding = decoded_names.get(token)
        if binding is None:
            name = text_value(token)
            if name not in declarations:
                raise PsfError(f'Undeclared PSF transient trace {name[:120]}')
            binding = (name, result.types.get(declarations[name]))
            decoded_names[token] = binding
        name, descriptor = binding
        next_token = tokens.peek()
        if next_token and next_token.startswith('"'):
            kind = text_value(tokens.pop())
            if kind not in result.types:
                raise PsfError(f'Unknown PSF value type: {kind[:120]}')
            descriptor = result.types[kind]
        value = parse_datum(tokens, descriptor)
        counts[name] += 1
        if name in result.values:
            series = result.values[name]
            if isinstance(value, str) and name.endswith(':region') and value.strip():
                if isinstance(series, array):
                    series = result.values[name] = list(series)
                value = region_labels.setdefault(value, value)
            else:
                if isinstance(value, complex) and value.imag == 0:
                    value = value.real
                if not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise PsfError(f'Expected finite real value in PSF trace {name}')
            series.append(value)
        if tokens.peek() == 'PROP':
            result.value_properties[name] = parse_properties(tokens)
    total = counts['time']
    inconsistent = {name: counts[name] for name in counts.keys() | result.values.keys()
                    if counts[name] != total}
    if not total or inconsistent:
        raise PsfError(f'Incomplete PSF time sweep: {total} samples, inconsistent traces {inconsistent}')
