import hashlib
from pathlib import Path
import tempfile
import unittest

import sar7_fast as fast


class FastPilotTests(unittest.TestCase):
    def test_only_timing_cards_differ_and_early_compare_matches_reviewed_shape(self):
        case, meta = fast.verify()
        observed, _ = fast.build(case)
        slow, previous = fast.offset.build(fast.offset.plan_cases()[0])
        self.assertEqual(hashlib.sha256(slow).hexdigest(), fast.PARENT_DECK_SHA)
        changed = set()
        for left, right in zip(slow.decode('ascii').splitlines(), observed.decode('ascii').splitlines(), strict=True):
            if left == right:
                continue
            label = left.split(maxsplit=1)[0]
            self.assertEqual(label, right.split(maxsplit=1)[0])
            changed.add(label)
        self.assertEqual(changed, set(meta['timing_changed_card_labels']))
        self.assertEqual(len(changed), 25)
        self.assertEqual(meta['wave']['saved_signals'], previous['wave']['saved_signals'])
        self.assertEqual(meta['wave']['period_s'], 1 / 1.75e9)
        for conversion in meta['wave']['conversions']:
            for i, trial in enumerate(conversion['trials']):
                self.assertAlmostEqual((trial['compare_s'] - trial['launch_s']) / fast.native.PS, 21)
                self.assertAlmostEqual((trial['read_s'] - trial['compare_s']) / fast.native.PS, 42)
                slot = conversion['index'] * meta['wave']['period_s']
                self.assertAlmostEqual((trial['launch_s'] - slot) / fast.native.PS, 78 + 66 * i)

    def test_incomplete_bit_stays_blocked(self):
        case, meta = fast.verify()
        rows = []
        for expected in case['pattern_codes']:
            row = dict(scored=True, expected_code=expected, observed_comparator_code=expected,
                       observed_registered_code=expected, final_dac_common_mode_change_from_sample_V=-.004)
            row['trial_results'] = [dict(bit=bit, decision=(expected >> bit) & 1,
                                        compare_to_read_s=42e-12, stable_rail_delay_s=34e-12,
                                        dac_residue_at_read_V=.000205, residue_prelaunch_V=.0002)
                                    for bit in fast.native.BITS]
            rows.append(row)
        report = dict(conversions=rows, tested_conversions=12, slurm_task_id='1', tran_sha256='fixture',
                      solver_seconds=1., raw_bytes=206, max_abs_sample_error_lsb=.1,
                      max_observed_resolve_delay_s=34e-12, execution_files_sha256={}, logic_smoke_pass=True)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            case_dir = root / fast.CASE_ID
            case_dir.mkdir()
            (case_dir / fast.base.MEASUREMENT).write_bytes(b'fixture')
            summary = fast.summarize(report, root, case, meta)
            self.assertTrue(summary['screen_pass'])
            self.assertAlmostEqual(summary['per_bit']['6']['min_buffered_rail_read_margin_ps'], 8)
            rows[0]['trial_results'][0].update(decision=None, stable_rail_delay_s=None)
            rows[0]['observed_comparator_code'] = None
            report['logic_smoke_pass'] = False
            summary = fast.summarize(report, root, case, meta)
            self.assertFalse(summary['screen_pass'])
            self.assertEqual(summary['per_bit']['6']['unresolved'], 1)


if __name__ == '__main__':
    unittest.main()
