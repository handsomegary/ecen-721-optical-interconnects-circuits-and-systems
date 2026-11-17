"""Verify exact r5 geometry, sense polarity, and matched acquisition timing."""

from unittest import TestCase

import sar7_cml_rdeg as pilot


class CmlTest(TestCase):
    def test_native_cards_have_explicit_body_and_inversion(self):
        cells = pilot.reused_cml()
        self.assertEqual(len(cells),9)
        self.assertTrue(any(s.startswith('MSENSE_P (sensen mp sem 0) nmos_lvt l=30n w=2u ') for s in cells))
        self.assertTrue(any(s.startswith('MSENSE_N (sensep mn sep 0) nmos_lvt l=30n w=2u ') for s in cells))
        self.assertTrue(any(s.startswith('MTAIL_P (sem sbias 0 0) nmos_lvt l=60n w=2u ') for s in cells))
        self.assertTrue(any(s.startswith('MTAIL_N (sep sbias 0 0) nmos_lvt l=60n w=2u ') for s in cells))
        self.assertIn('V_SENSE_B (sbias 0) vsource dc=0.5',cells)
        self.assertIn('RSENSE_P (svdd sensen) resistor r=500',cells)
        self.assertIn('RSENSE_DEG (sem sep) resistor r=250',cells)

    def test_cml_does_not_modify_cdac_or_comparison_events(self):
        old = pilot.common.read(pilot.relaxed.PLAN)['cases'][0]
        case = pilot.common.read(pilot.PLAN)['cases'][0]
        raw,old_meta = pilot.relaxed.build(old)
        bench,new_meta = pilot.build(case)
        lines = [line for line in bench.decode('ascii').splitlines() if line not in pilot.reused_cml()]
        deltas = [(a,b) for a,b in zip(raw.decode('ascii').splitlines(),lines,strict=True) if a!=b]
        self.assertEqual(len(deltas),8)
        self.assertTrue(all(a.replace('(mp mn ','(sensep sensen ')==b for a,b in deltas if a.startswith('XCMP')))
        for a,b in zip(old_meta['wave']['conversions'],new_meta['wave']['conversions'],strict=True):
            self.assertEqual(a['trials'],b['trials'])
            self.assertEqual(a['sample_s'],b['sample_s'])
            self.assertAlmostEqual((b['end_s']-a['end_s'])/1e-12,3)


    def test_only_source_bridge_differs_from_760254_portable_bench(self):
        import importlib.util
        import os
        from pathlib import Path
        prior_root = Path(os.environ.get('PAM4_SAR7_CML_PACKAGE',
            pilot.ROOT.parent/'PAM4_SAR7_CML_SENSE_20261115')).resolve()
        spec = importlib.util.spec_from_file_location('_prior_cml_sense', prior_root/'sar7_cml_sense.py')
        prior = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(prior)
        old_case, old_meta = prior.verify()
        self.assertEqual(old_meta['portable_sha256'],
            '7c11149e689033d9a754ba0c08f8e9100a7f5c30fadea5e6c3280c1b63d1e170')
        old_bench, _ = prior.build(old_case)
        case, = pilot.common.read(pilot.PLAN)['cases']
        bench, meta = pilot.build(case)
        lines = bench.decode('ascii').splitlines()
        bridge = 'RSENSE_DEG (sem sep) resistor r=250'
        self.assertEqual(lines.count(bridge), 1)
        self.assertEqual([line for line in lines if line != bridge],
                         old_bench.decode('ascii').splitlines())
        self.assertEqual(meta['wave'], old_meta['wave'])
