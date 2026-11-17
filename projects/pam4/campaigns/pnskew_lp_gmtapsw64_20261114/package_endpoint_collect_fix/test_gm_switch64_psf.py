"""Exercise the streaming reader with native-format ASCII and attestations."""

from array import array
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import gm_switch64_metrics as metrics
from gm_switch64_psf import MAX_BYTES, PsfError, parse_selected
from pvt.reference.psf_ascii import parse_text
from test_gm_switch64_metrics import fixtures


SMALL = '''HEADER
"PSFversion" "1.00"
TYPE
"sweep" FLOAT DOUBLE PROP("units" "s")
"scalar" FLOAT DOUBLE
"enum" STRING
SWEEP
"time" "sweep"
TRACE
"voltage" "scalar" PROP("units" "V")
"tail:region" "enum"
"unused" "scalar"
VALUE
"time" 0
"voltage"
  1.1D-01
"tail:region" "enum" "2.0"
"unused" 99
"time" 1d-12 PROP("units" "sec")
"voltage" ( 2.2e-01 0 )
"tail:region" "enum" "1"
"unused" 98
END
'''
REQUIRED = frozenset(('time', 'voltage', 'tail:region'))


class NativeSwitchPsfReader(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'codeSwitch.tran.tran'

    def read(self, body, **kwargs):
        self.path.write_bytes(body)
        return parse_selected(self.path, REQUIRED, **kwargs)

    def test_native_multiline_values_units_digest_and_compact_retention(self):
        raw = ('\ufeff' + SMALL.replace('\n', '\r\n') + ' \r\n').encode('utf-8')
        parsed = self.read(raw)
        reference = parse_text(SMALL)
        self.assertEqual(parsed.sha256, hashlib.sha256(raw).hexdigest())
        self.assertEqual(parsed.sweep_names, ['time'])
        self.assertEqual(parsed.unit('time'), 'sec')
        self.assertEqual(parsed.unit('voltage'), 'V')
        self.assertEqual(parsed.header, reference.header)
        self.assertIsInstance(parsed.values['voltage'], array)
        self.assertEqual(set(parsed.values), REQUIRED)
        for name in REQUIRED:
            self.assertEqual(list(parsed.values[name]), reference.values[name])

    def test_truncation_binary_unknown_and_incomplete_traces_are_rejected(self):
        failures = {
            'Missing terminal': SMALL.removesuffix('END\n'),
            'after PSF END': SMALL + 'TRAILER\n',
            'binary': SMALL + '\x00',
            'Invalid UTF-8': SMALL.encode() + b'\xff',
            'inside VALUE': SMALL.replace('"unused" 98', 'TRACE'),
            'Malformed PSF': SMALL.replace('"unused" 98', '"unused" 98 "'),
            'Incomplete PSF': SMALL.replace('"unused" 98', ''),
            'Undeclared PSF': SMALL.replace('"unused" 98', '"shadow" 98'),
            'Missing switch PSF': SMALL.replace('"voltage" "scalar" PROP("units" "V")\n', ''),
            'time sweep': SMALL.replace('"time" "sweep"', '"other" "sweep"'),
            'finite real': SMALL.replace('2.2e-01 0', '2.2e-01 1'),
        }
        for message, body in failures.items():
            with self.subTest(message=message):
                with self.assertRaisesRegex(PsfError, message):
                    self.read(body.encode() if isinstance(body, str) else body)

    def test_bound_covers_both_native_smoke_files_and_is_enforced(self):
        self.assertGreaterEqual(MAX_BYTES, 378504236)
        raw = SMALL.encode()
        self.read(raw, max_bytes=len(raw))
        with self.assertRaisesRegex(PsfError, 'oversized'):
            self.read(raw, max_bytes=len(raw) - 1)

    def test_all_measurements_match_the_existing_fixture(self):
        data, case, _ = fixtures()
        with self.path.open('w', encoding='ascii', newline='\n') as stream:
            stream.write('TYPE\n"scalar" FLOAT DOUBLE\nSWEEP\n'
                         '"time" "scalar" PROP("units" "s")\nTRACE\n')
            for name in data.values.keys() - {'time'}:
                stream.write(f'"{name}" "scalar"\n')
            stream.write('VALUE\n')
            for samples in zip(*data.values.values()):
                for name, value in zip(data.values, samples):
                    stream.write(f'"{name}" {value!r}\n')
            stream.write('END\n')
        streamed = metrics.parse_transient(self.path)
        data.sha256 = streamed.sha256
        self.assertEqual(metrics.measurement(streamed, case), metrics.measurement(data, case))


if __name__ == '__main__':
    unittest.main()
