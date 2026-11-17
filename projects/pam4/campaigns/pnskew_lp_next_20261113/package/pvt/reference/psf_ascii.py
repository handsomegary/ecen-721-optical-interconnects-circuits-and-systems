#!/usr/bin/env python3
"""Standard-library reader for Spectre PSF ASCII scalar/complex/OP results.

API: data = parse_file(path); data.values[name] is a list of floats, complex
numbers, or dictionaries for structured operating-point records.
Never use on deviceInfo/model parameter dumps. This reader does not simulate.
"""

import argparse
import hashlib
import json
import math
import re
from pathlib import Path

MAX_FILE_BYTES = 64 * 1024 * 1024
SECTIONS = {'HEADER', 'TYPE', 'SWEEP', 'TRACE', 'VALUE', 'END'}
TOKEN = re.compile(r'\s*("(?:\\.|[^"\\])*"|[()]|[^\s()"]+)')


class PsfError(ValueError):
    pass


class Tokens:
    def __init__(self, text):
        self.iterator = (match.group(1) for match in TOKEN.finditer(text))
        self.next_token = next(self.iterator, None)

    def peek(self):
        return self.next_token

    def pop(self):
        token = self.next_token
        if token is None:
            raise PsfError('Unexpected end of PSF ASCII section')
        self.next_token = next(self.iterator, None)
        return token

    def expect(self, expected):
        actual = self.pop()
        if actual != expected:
            raise PsfError('Expected %r, received %r' % (expected, actual[:120]))


def text_value(token):
    if token.startswith('"'):
        try:
            return json.loads(token)
        except json.JSONDecodeError:
            return token[1:-1].replace('\\"', '"').replace('\\\\', '\\')
    return token


def numeric_value(token):
    try:
        return float(token.replace('D', 'e').replace('d', 'e'))
    except ValueError as error:
        raise PsfError('Expected a numeric simulation result, received %r' % token[:120]) from error


def parse_properties(tokens):
    tokens.expect('PROP')
    tokens.expect('(')
    properties = {}
    while tokens.peek() != ')':
        key = text_value(tokens.pop())
        token = tokens.pop()
        properties[key] = text_value(token) if token.startswith('"') else numeric_value(token)
    tokens.expect(')')
    return properties


def parse_descriptor(tokens):
    kind = tokens.pop()
    descriptor = {'kind': kind, 'properties': {}}
    if kind == 'STRUCT':
        tokens.expect('(')
        fields = []
        while tokens.peek() != ')':
            name = text_value(tokens.pop())
            field = parse_descriptor(tokens)
            field['name'] = name
            fields.append(field)
        tokens.expect(')')
        descriptor['fields'] = fields
    else:
        modifiers = []
        while tokens.peek() is not None and tokens.peek() not in ('PROP', ')') and not tokens.peek().startswith('"'):
            modifiers.append(tokens.pop())
        descriptor['modifiers'] = modifiers
    if tokens.peek() == 'PROP':
        descriptor['properties'] = parse_properties(tokens)
    return descriptor


def parse_datum(tokens, descriptor=None):
    kind = descriptor.get('kind') if descriptor else None
    if kind == 'STRUCT':
        tokens.expect('(')
        value = {}
        for field in descriptor['fields']:
            value[field['name']] = parse_datum(tokens, field)
        tokens.expect(')')
        return value
    if tokens.peek() == '(':
        tokens.expect('(')
        components = []
        while tokens.peek() != ')':
            components.append(numeric_value(tokens.pop()))
        tokens.expect(')')
        if kind == 'COMPLEX' or len(components) == 2:
            if len(components) != 2:
                raise PsfError('Complex value must have exactly two components')
            return complex(*components)
        return components
    token = tokens.pop()
    if token.startswith('"'):
        return text_value(token)
    return numeric_value(token)


class PsfData:
    def __init__(self, source=None):
        self.source = source
        self.sha256 = None
        self.header = {}
        self.types = {}
        self.trace_types = {}
        self.sweep_types = {}
        self.sweep_names = []
        self.values = {}
        self.value_properties = {}

    def trace(self, name):
        return self.values[name]

    def unit(self, name):
        props = self.value_properties.get(name, {})
        if 'units' in props:
            return props['units']
        typename = self.trace_types.get(name) or self.sweep_types.get(name)
        return self.types.get(typename, {}).get('properties', {}).get('units')


def split_sections(text):
    result = {}
    current = None
    for line in text.lstrip('\ufeff').splitlines():
        stripped = line.strip()
        if stripped in SECTIONS:
            current = stripped
            result.setdefault(current, [])
        elif current:
            result[current].append(line)
    if 'VALUE' not in result:
        raise PsfError('Missing VALUE section; file is not supported PSF ASCII results')
    return {name: '\n'.join(lines) for name, lines in result.items()}


def parse_text(text, source=None):
    sections = split_sections(text)
    result = PsfData(source)
    header = Tokens(sections.get('HEADER', ''))
    while header.peek() is not None:
        name = text_value(header.pop())
        token = header.pop()
        result.header[name] = text_value(token) if token.startswith('"') else numeric_value(token)
    types = Tokens(sections.get('TYPE', ''))
    while types.peek() is not None:
        name = text_value(types.pop())
        result.types[name] = parse_descriptor(types)
    for section_name, destination in [('SWEEP', result.sweep_types), ('TRACE', result.trace_types)]:
        stream = Tokens(sections.get(section_name, ''))
        while stream.peek() is not None:
            name_token = stream.pop()
            if not name_token.startswith('"'):
                raise PsfError('Unsupported grouped trace declaration: ' + name_token[:80])
            name = text_value(name_token)
            typename = text_value(stream.pop())
            if typename == 'GROUP':
                raise PsfError('Grouped PSF traces are not supported')
            destination[name] = typename
            if stream.peek() == 'PROP':
                parse_properties(stream)
    result.sweep_names = list(result.sweep_types)
    stream = Tokens(sections['VALUE'])
    while stream.peek() is not None:
        name = text_value(stream.pop())
        typename = result.trace_types.get(name) or result.sweep_types.get(name)
        if stream.peek() and stream.peek().startswith('"'):
            # Non-swept DC and OP records include the type in each value row.
            explicit_type = text_value(stream.pop())
            if explicit_type not in result.types:
                raise PsfError('Unknown PSF value type: ' + explicit_type)
            typename = explicit_type
            result.trace_types.setdefault(name, typename)
        value = parse_datum(stream, result.types.get(typename))
        result.values.setdefault(name, []).append(value)
        if stream.peek() == 'PROP':
            result.value_properties[name] = parse_properties(stream)
    if result.sweep_names:
        axis_lengths = {name: len(result.values.get(name, [])) for name in result.sweep_names}
        if len(result.sweep_names) == 1:
            length = axis_lengths[result.sweep_names[0]]
            inconsistent = {name: len(values) for name, values in result.values.items() if len(values) != length}
            if inconsistent:
                raise PsfError('Swept trace lengths differ from the axis: ' + repr(inconsistent))
    return result


def parse_file(path):
    path = Path(path)
    if path.stat().st_size > MAX_FILE_BYTES:
        raise PsfError('Result file exceeds the 64 MiB reader bound')
    raw = path.read_bytes()
    if b'\x00' in raw:
        raise PsfError('Binary PSF is unsupported; request simulator psfascii output')
    result = parse_text(raw.decode('utf-8-sig'), source=str(path))
    result.sha256 = hashlib.sha256(raw).hexdigest()
    return result


def derivative(x, y):
    """Second-order local derivative for distinct nonuniform three-point grids."""
    if len(x) != len(y) or len(x) < 2:
        raise ValueError('Derivative needs equally sized vectors with at least two points')
    if len(x) == 2:
        slope = (y[1] - y[0]) / (x[1] - x[0])
        return [slope, slope]
    result = []
    for index, at in enumerate(x):
        indices = (0, 1, 2) if index == 0 else (len(x) - 3, len(x) - 2, len(x) - 1) if index == len(x) - 1 else (index - 1, index, index + 1)
        total = 0.0
        for j in indices:
            others = [k for k in indices if k != j]
            denominator = (x[j] - x[others[0]]) * (x[j] - x[others[1]])
            if denominator == 0:
                raise ValueError('Derivative grid contains duplicate points')
            total += y[j] * (2 * at - x[others[0]] - x[others[1]]) / denominator
        result.append(total)
    return result


def integrate_noise(frequency, density, *, density_kind):
    """Trapezoidal noise integration on the supplied frequency grid.

    density_kind='psd': power density in units such as V^2/Hz.
    density_kind='asd': amplitude density in units such as V/sqrt(Hz).
    Returns integrated variance and RMS. No guessed convention or band extrapolation.
    """
    if len(frequency) != len(density) or len(frequency) < 2:
        raise ValueError('Noise integration needs two or more matching samples')
    if density_kind not in ('psd', 'asd'):
        raise ValueError('Explicit density_kind must be psd or asd')
    psd = [abs(value) ** 2 if density_kind == 'asd' else float(value) for value in density]
    if any(value < 0 or not math.isfinite(value) for value in psd):
        raise ValueError('Noise PSD must be finite and nonnegative')
    variance = 0.0
    for index in range(len(frequency) - 1):
        width = frequency[index + 1] - frequency[index]
        if width <= 0:
            raise ValueError('Frequency grid must be strictly increasing')
        variance += width * (psd[index] + psd[index + 1]) / 2
    return {'variance': variance, 'rms': math.sqrt(variance),
            'band_hz': [frequency[0], frequency[-1]], 'method': 'trapezoid_on_provided_grid'}


def json_number(value):
    if isinstance(value, complex):
        return {'real': value.real, 'imag': value.imag}
    raise TypeError('Unsupported JSON value: ' + type(value).__name__)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', type=Path)
    parser.add_argument('--trace', action='append', help='Emit only explicitly selected trace(s), plus sweep axes.')
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    data = parse_file(args.path)
    names = list(dict.fromkeys(data.sweep_names + (args.trace or [])))
    report = {'source': data.source, 'sha256': data.sha256, 'header': data.header,
              'sweep_names': data.sweep_names, 'available_trace_names': list(data.values),
              'selected_values': {name: data.values[name] for name in names}}
    encoded = json.dumps(report, default=json_number, indent=2, allow_nan=False) + '\n'
    if args.out:
        args.out.write_text(encoded, encoding='utf-8')
    else:
        print(encoded, end='')


if __name__ == '__main__':
    main()
