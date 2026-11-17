"""Exercise fixed-window training with the reported lag and sign pattern."""

import copy
import json
import math
import os
from pathlib import Path
import random
import re
from contextlib import nullcontext
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import c0_rescore  # Load the pinned original runner before the overlay.
import c0_align as align


class Alignment(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        review = align.review
        cls.frozen = review.pinned_r5()
        cls.functions = align.scoring_functions()
        cls.symbols = cls.functions.r5.validation_symbols()
        cls.cases = review.common.read(align.PLAN)['cases']
        cls.observed = json.loads(Path(__file__).with_name('CASE0_OBSERVED.json').read_text(encoding='utf-8'))

    def records(self):
        review = align.review
        rng = random.Random(757899)
        result = {}
        # Reconstruct a synthetic low-pass/ISI case using the actual feedback's
        # peak lags and negative secondary correlation as regression landmarks.
        # This model contains no Olympus waveform values.
        for point, amplitude in (('primary', .006), ('secondary', .003)):
            reported = self.observed['observed_full_window_lag_scan_for_diagnosis_only'][point]
            target = reported['peak_r']
            sign = math.copysign(1, target)
            error_scale = math.sqrt((1 / target**2 - 1) * 1.25)
            rows = []
            for index in range(1542):
                tx = max(1, index - reported['peak_lag'])
                label = self.symbols[tx] - 1.5
                isi = .85*(self.symbols[tx-1]-1.5) + rng.gauss(0,.5)
                sample = sign*amplitude*(label + error_scale*isi)
                read = .2e-9 + (index+(.5 if point=='primary' else 4.25))*review.UI
                rows.append((index,sample,read,read,index%8))
            result[point] = rows
        return result

    def score(self, index, records, calibration=None):
        with patch.object(self.functions.r5,'extract_records',return_value=(records,{})):
            return align.score_records(self.functions,SimpleNamespace(sha256='a'*64),self.frozen,
                                       self.cases[index],'b'*64,calibration)

    def test_training_handles_reported_lag_and_sign(self):
        score = self.score(0,self.records())
        for point, expected_sign in align.EXPECTED_POLARITY.items():
            choice = score['calibration']['selections'][point]
            self.assertEqual(choice['lag'],self.observed['observed_full_window_lag_scan_for_diagnosis_only'][point]['peak_lag'])
            self.assertEqual(choice['detectors']['raw_three_threshold']['polarity'],expected_sign)
            self.assertTrue(choice['correlation_sign_matches_circuit'])
            self.assertLess(choice['last_training_read_s'],align.review.FIRST_PAYLOAD_S)
            metrics = score['metrics'][point]['metrics']
            self.assertEqual(metrics['ADC_validation_input_count'],256)
            self.assertEqual(metrics['FFE_validation_output_count'],240)
            self.assertFalse(metrics['validation_fitting_performed'])
            self.assertLess(metrics['ideal7bit_ADC_then_FFE']['SER'],.65)
        self.assertEqual(score['scoring']['ffe_center_tx_indices'],[1160,1400])

    def test_payload_cannot_change_alignment_or_ffe(self):
        original = self.records()
        altered = {name:[(i,-v,t,c,b) if t>=align.review.FIRST_PAYLOAD_S else (i,v,t,c,b)
                         for i,v,t,c,b in rows] for name,rows in original.items()}
        baseline = self.score(0,original)
        changed = self.score(0,altered)
        self.assertEqual(changed['calibration'],baseline['calibration'])
        self.assertNotEqual(changed['metrics'],baseline['metrics'])
        expected = copy.deepcopy(baseline['calibration'])
        with patch.object(align,'calibrate',side_effect=AssertionError('Treatment case fitted a detector')):
            for index in range(1,5):
                result = self.score(index,altered,baseline['calibration'])
                self.assertEqual(result['calibration'],expected)
                self.assertEqual(result['scoring']['payload_tx_indices'],[1152,1408])

    def test_native_parser_and_clock_mapping_feed_the_revised_score(self):
        review = align.review
        records = self.records()
        clocks = self.frozen['training_run']['clock_specification']
        master = clocks['primary_clocks'][0]
        first = master['first_fall_midpoint_s']
        extra = clocks['secondary_clocks'][0]['first_close_midpoint_s'] - first
        origin = first - math.floor((first-.2e-9)/review.UI)*review.UI + 1.5e-12
        pulses = {'X_ck0':(master['first_rise_midpoint_s'],first,master['period'])}
        names = review.save_names((review.R5/'quiet.scs').read_text('ascii'))
        for entry in clocks['secondary_clocks']:
            name = f"B{entry['bank']}_ck{entry['branch']}"
            if name in names:
                pulses[name] = (entry['first_open_midpoint_s'],entry['first_close_midpoint_s'],entry['period_s'])
        primary = [n for n in names if re.fullmatch(r'X_h\dp',n)]
        secondary = [n for n in names if re.fullmatch(r'B\d_h\dp',n)]
        static = ''.join(f'"{n}" 0.21\n' for n in names if n not in {*primary,*secondary,*pulses})
        with TemporaryDirectory(prefix='c0-align-native-') as temp:
            root = Path(temp).resolve()
            (root/'raw').mkdir()
            with (root/review.RAW_NAME).open('x',encoding='ascii',newline='\n',buffering=1024**2) as stream:
                stream.write('TYPE\n"seconds" FLOAT DOUBLE PROP("units" "s")\n"real" FLOAT DOUBLE\n'
                             'SWEEP\n"time" "seconds"\nTRACE\n')
                stream.write(''.join(f'"{n}" "real"\n' for n in names)+'VALUE\n')
                for i in range(round(review.STOP_S/(review.UI/8))+1):
                    time = i*review.UI/8
                    stream.write(f'"time" {time:.17g}\n'+static)
                    for name,(opened,closed,period) in pulses.items():
                        value = .9 if time>=opened and (time-opened)%period<closed-opened else 0.
                        stream.write(f'"{name}" {value}\n')
                    for point,nodes,offset in (('primary',primary,0),('secondary',secondary,extra)):
                        index = round((time-origin-offset)/review.UI)
                        index = min(len(records[point])-1,max(0,index))
                        value = .21 + records[point][index][1]
                        stream.write(''.join(f'"{n}" {value:.8g}\n' for n in nodes))
                stream.write('END\n')
            uid_context = (patch.object(os,'getuid',return_value=root.stat().st_uid,create=True)
                           if os.name=='nt' else nullcontext())
            with uid_context:
                review.common.write_new(root/'run_status.json',dict(case_id=align.BASELINE,
                                           raw_inventory=review.common.raw_inventory(root)))
                report = align.measure(root)
            for point,sign in align.EXPECTED_POLARITY.items():
                self.assertEqual(report['metrics'][point]['lag'],3)
                self.assertGreater(sign*report['calibration']['selections'][point]['pearson'],.65)
                self.assertLess(report['metrics'][point]['metrics']['ideal7bit_ADC_then_FFE']['SER'],.65)
            self.assertGreater(report['clock_audit']['retained_primary_and_secondary_records'],1408)


if __name__ == '__main__':
    unittest.main()
