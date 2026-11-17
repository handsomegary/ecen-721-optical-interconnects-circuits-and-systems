"""Regress the two native collection failures and beta-specific scoring."""
import cmath
import math
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4

import lp_diagnostics as diag
import recover_diag as repair
from beta_metrics import beta_metrics
from diag_metrics import stb_metrics
from pvt.reference.psf_ascii import PsfData, parse_text


class NativeCollection(unittest.TestCase):
    def test_double_tran_suffix_is_recognized_but_duplicate_is_rejected(self):
        row = {'path':'raw/biasStartup.tran.tran'}
        pattern = r'raw/biasStartup\.tran(?:\.tran)?'
        with patch.object(diag,'safe_raw',return_value=object()) as read:
            s = {'raw_inventory':[row,{'path':'raw/logFile'}]}
            self.assertIsNotNone(diag.raw_psf(Path('.'),s,pattern))
            read.assert_called_once_with(Path('.'),s,'biasStartup.tran.tran')
            with self.assertRaisesRegex(ValueError,'Unexpected native PSF'):
                diag.raw_psf(Path('.'),{'raw_inventory':[row,{'path':'raw/biasStartup.tran'}]},pattern)

    def test_native_shaped_psf_uses_reported_replica_margin_sign(self):
        points = [(1,-451.17+0.1j),(1.0336e7,cmath.rect(1,math.radians(84.034))),
                  (5.1316e8,complex(10**(-19.625/20),0)),(1e9,.05-.01j)]
        raw = ['HEADER','"analysis type" "stb"','TYPE','"sweep" FLOAT DOUBLE',
               '"complex" COMPLEX DOUBLE','SWEEP','"freq" "sweep" PROP("units" "Hz")',
               'TRACE','"loopGain" "complex"','VALUE']
        for f,z in points:
            raw.extend((f'"freq" {f:.12g}',f'"loopGain" ({z.real:.17g} {z.imag:.17g})'))
        trace = parse_text('\n'.join([*raw,'END']))
        native = parse_text('''TYPE
"Deg" FLOAT DOUBLE
"dB" FLOAT DOUBLE
"Hz" FLOAT DOUBLE
"string" STRING
VALUE
"phaseMargin" "Deg" 84.034
"gainMargin" "dB" 19.625
"phaseMarginFreq" "Hz" 10336000
"gainMarginFreq" "Hz" 513160000
"stb_state" "string" "The circuit is stable. Gain and phase margin are both found."
END
''')
        result = stb_metrics(trace,native)
        self.assertTrue(result['passed'],result.get('reason'))
        self.assertEqual(result['phase_margin_deg'],84.034)
        self.assertEqual(result['gain_margin_db'],19.625)

    def test_beta_no_crossing_only_passes_the_sampled_screen(self):
        freq = [10**(k/50) for k in range(451)]
        data = PsfData()
        data.sweep_types = {'freq':'Hz'}
        data.values = {'freq':freq,'loopGain':[.25/(1+1j*f/1e4) for f in freq]}
        result = beta_metrics(data,None)
        self.assertTrue(result['sampled_screen_pass'])
        self.assertIsNone(result['passed'])
        self.assertIsNone(result['phase_margin_deg'])
        self.assertGreater(result['min_distance_to_critical'],.74)
        data.values['loopGain'] = [.5/(1+1j*f/1e4) for f in freq]
        result = beta_metrics(data,None)
        self.assertFalse(result['sampled_screen_pass'])
        self.assertAlmostEqual(result['sampled_gain_reserve_dB'],6.0206,places=3)

    def test_recovery_sidecars_preserve_the_original_review(self):
        root = Path(__file__).resolve().parent/('diag_recovery_test_'+uuid4().hex)
        root.mkdir()
        try:
            old = root/'measurements.json'
            old.write_bytes(b'{"status":"review"}\n')
            report = {'case_id':'lpdiag_11_ss_replica_cb2','passed':True}
            receipt = {'collector_hostname':'fixture'}
            with patch.object(repair.common,'owned_file',side_effect=lambda parent,p:(p,p.stat())):
                repair.publish(root,report,receipt)
                repair.publish(root,report,receipt)
                self.assertEqual(old.read_bytes(),b'{"status":"review"}\n')
                done = repair.common.read(root/repair.NAMES[2])
                self.assertEqual(done['measurement_sha256'],repair.common.sha(root/repair.NAMES[0]))
                self.assertEqual(done['receipt_sha256'],repair.common.sha(root/repair.NAMES[1]))
                with self.assertRaisesRegex(ValueError,'Recovery sidecar differs'):
                    repair.publish(root,dict(report,passed=False),receipt)
        finally:
            for child in root.iterdir():
                child.unlink()
            root.rmdir()
