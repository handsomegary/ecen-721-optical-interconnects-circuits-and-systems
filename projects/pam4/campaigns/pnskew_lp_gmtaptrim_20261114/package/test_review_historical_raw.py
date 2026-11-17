"""Exercise the historical inventory audit without altering the source run."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import olympus_common as common
import review_historical_raw as review


class HistoricalReview(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.case = {'case_id':'case_00','process':'tt','stage':'ac'}
        self.plan = self.root/'smoke_plan.json'
        common.write_new(self.plan,{'cases':[self.case]})
        self.run = self.root/self.case['case_id']
        self.raw = self.run/'raw'/'acResponse.ac'
        self.raw.parent.mkdir(parents=True)
        own = patch.object(common.os,'getuid',return_value=self.root.stat().st_uid,create=True)
        own.start()
        self.addCleanup(own.stop)
        self.raw.write_bytes(b'common synthetic raw contents')
        (self.run/'bench.scs').write_bytes(b'bench')
        (self.run/'parent_diff.txt').write_bytes(b'diff')
        (self.run/'spectre.log').write_bytes(b'log')
        (self.run/'.study_owned').write_text('100\n',encoding='ascii')
        staged = {name:self.digest(name) for name in ('bench.scs','parent_diff.txt')}
        common.write_new(self.run/'case.json',dict(self.case,staged_source_sha256=staged))
        intent = {'case_id':'case_00','slurm_job_id':'100','plan_sha256':common.sha(self.plan)}
        common.write_new(self.run/'execution_intent.json',intent)
        status = dict(intent,status='spectre_completed',exit_code=0,case_sha256=self.digest('case.json'),
                      input_deck_sha256_before=self.digest('bench.scs'),
                      input_deck_sha256_after=self.digest('bench.scs'),
                      spectre_log_sha256=self.digest('spectre.log'),
                      simulator_build=common.BUILD,raw_inventory=common.raw_inventory(self.run))
        status['raw_inventory'][0]['device'] += 1  # Same mounted volume may differ by host.
        common.write_new(self.run/'run_status.json',status)
        self.measurement = {'measurement_complete':True,'case_id':'case_00',
                            'run_status_sha256':self.digest('run_status.json'),
                            'bench_sha256':self.digest('bench.scs')}
        self.write_compact()

    def digest(self, name):
        return common.sha(self.run/name)

    def snapshot(self):
        return {p.relative_to(self.run):common.sha(p) for p in self.run.rglob('*') if p.is_file()}

    def write_compact(self):
        with (self.run/'measurements.json').open('w',encoding='utf-8') as stream:
            import json
            json.dump(self.measurement,stream)
        completion = {'measurement_complete':True,'measurement_sha256':self.digest('measurements.json')}
        with (self.run/'completion.json').open('w',encoding='utf-8') as stream:
            json.dump(completion,stream)

    def test_verified_inventory_leaves_the_source_run_intact(self):
        before = self.snapshot()
        value = review.review(self.root,self.plan)
        self.assertEqual(self.snapshot(),before)
        self.assertFalse(value['raw_deleted'])
        candidate, = value['inventory_candidates']
        raw, = candidate['raw_files']
        self.assertEqual(raw['sha256'],common.sha(self.raw))
        self.assertEqual(raw['bytes'],self.raw.stat().st_size)

    def test_raw_sha_or_active_diagnostics_are_blocked(self):
        self.measurement['status'] = 'review'
        self.write_compact()
        value = review.review(self.root,self.plan)
        self.assertIn('Unresolved diagnostic',value['blocked'][0]['reason'])
        self.measurement.pop('status')
        self.write_compact()
        self.raw.write_bytes(b'changed raw')
        value = review.review(self.root,self.plan)
        self.assertFalse(value['inventory_candidates'])
        self.assertIn('Raw inventory differs',value['blocked'][0]['reason'])

    def test_outside_case_selection_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'outside the selected campaign'):
            review.review(self.root,self.plan,['other'])
