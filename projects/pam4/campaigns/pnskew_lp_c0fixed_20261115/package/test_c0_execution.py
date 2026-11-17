"""Exercise C0's real execution/collection path using synthetic native-shaped PSF.

Only the external simulator, private-kit preflight, wall clock and platform
primitives are substituted. No stored Olympus waveform is needed or claimed.
"""

from contextlib import ExitStack, nullcontext
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import c0_review as review


MODEL_ROOT = '/synthetic/private-kit'
SOLVER = '/synthetic/bin/spectre'
CLEAN_LOG = b'scalefactor = 0.900\nSpectre completes with 0 errors, 0 warnings.\n'
FATAL_LOG = b'ERROR (USIMUWI-20006): not enough virtual memory\nFATAL: simulation terminated\n'


class AuthorizedClock(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2026,11,15,12,tzinfo=timezone.utc).astimezone(tz)


def private_kit_fixture(model_root, process, wrapper=None):
    from pvt import model_preflight
    return dict(schema='PAM4_PRIVATE_VM_KIT_PREFLIGHT_V1', model_root=MODEL_ROOT,
                process=process, root_section='top_'+process,
                active_shrink_sections=['ttmacro_mos_moscap'],
                kit_fingerprints={name:{'bytes':size,'sha256':sha}
                                  for name,(size,sha) in model_preflight.KIT_PINS.items()},
                active_static_mos_scale=.9, static_identity_verified=True,
                actual_spectre_effective_scale='CHECK_ACTUAL_RUN_LOG',
                model_files_written=False, model_bodies_exported=False, simulation_started=False)


def write_native_psf(path):
    """Keep original strobe grid and real r5 clock schedule for both sampling levels."""
    frozen = review.pinned_r5()
    clock = frozen['training_run']['clock_specification']
    names = review.save_names((review.R5/'quiet.scs').read_text('ascii'))
    master = clock['primary_clocks'][0]
    pulses = {'X_ck0':(master['first_rise_midpoint_s'],master['first_fall_midpoint_s'],master['period'])}
    for entry in clock['secondary_clocks']:
        name = f"B{entry['bank']}_ck{entry['branch']}"
        if name in names:
            pulses[name] = (entry['first_open_midpoint_s'],entry['first_close_midpoint_s'],entry['period_s'])
    static = ''.join(f'"{name}" 0.21\n' for name in names if name not in pulses).encode('ascii')
    with path.open('xb', buffering=1024**2) as stream:
        stream.write(b'TYPE\n"seconds" FLOAT DOUBLE PROP("units" "s")\n"real" FLOAT DOUBLE\n'
                     b'SWEEP\n"time" "seconds"\nTRACE\n')
        for name in names:
            stream.write(f'"{name}" "real"\n'.encode('ascii'))
        stream.write(b'VALUE\n')
        for index in range(round(review.STOP_S/(review.UI/8))+1):
            time = index*review.UI/8
            rows = f'"time" {time:.17g}\n'
            for name, (opened, closed, period) in pulses.items():
                value = .9 if time>=opened and (time-opened)%period<closed-opened else 0.
                rows += f'"{name}" {value}\n'
            stream.write(rows.encode('ascii')+static)
        stream.write(b'END\n')
    return len(names)


def exclusive_copy(source, target):
    # The Windows sandbox denies os.link. Keep real publisher control flow,
    # conflict detection and receipt hashing with an exclusive-create primitive.
    with Path(source).open('rb') as src, Path(target).open('xb') as dst:
        shutil.copyfileobj(src,dst)


class C0Execution(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.storage = TemporaryDirectory(prefix='c0-native-fixture-')
        cls.addClassCleanup(cls.storage.cleanup)
        cls.native_path = Path(cls.storage.name)/'tranResponse.tran.tran'
        cls.trace_count = write_native_psf(cls.native_path)

    def setUp(self):
        import c0_run
        from pvt import model_preflight
        self.runner = c0_run
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(TemporaryDirectory(prefix='c0-execution-'))).resolve()
        self.cases = review.common.read(c0_run.PLAN)['cases']
        self.stack.enter_context(patch.object(review.common,'checked_root',side_effect=lambda path:Path(path).resolve()))
        self.stack.enter_context(patch.object(review.common,'environment',return_value=(SOLVER,{})))
        self.stack.enter_context(patch.object(c0_run,'datetime',AuthorizedClock))
        self.stack.enter_context(patch.object(model_preflight,'verify_private_kit',side_effect=private_kit_fixture))
        self.limits = []
        fake_resource = SimpleNamespace(RLIMIT_FSIZE=1,RUSAGE_CHILDREN=2,
                                        setrlimit=lambda _,limit:self.limits.append(limit),
                                        getrusage=lambda _:SimpleNamespace(ru_maxrss=404000))
        self.stack.enter_context(patch.dict(sys.modules,{'resource':fake_resource}))
        self.stack.enter_context(patch.dict(os.environ,{'SLURM_CPUS_PER_TASK':'1'}))
        if os.name=='nt':
            self.stack.enter_context(patch.object(os,'getuid',return_value=self.root.stat().st_uid,create=True))
            self.stack.enter_context(patch.object(c0_run,'lock_case',side_effect=lambda _:nullcontext()))
            self.stack.enter_context(patch.object(os,'link',side_effect=exclusive_copy))
        manifest = self.root/'test-manifest.txt'
        manifest.write_bytes(b'C0 executable test approval binding\n')
        self.stack.enter_context(patch.object(c0_run,'MANIFEST',manifest))
        self.approval = dict(approved=True,platform='Olympus',plan_sha256=review.common.sha(c0_run.PLAN),
                             design_source_sha256=review.common.sha(manifest),
                             case_ids=[case['case_id'] for case in self.cases],
                             stages=[c0_run.STAGE],retire_new_raw=False)
        self.solvers = 0

    def solver(self, argv, *, cwd, preexec_fn, timeout, **kwargs):
        self.solvers += 1
        self.assertEqual(argv[:4],[SOLVER,'-64','+mt=1','bench.scs'])
        self.assertEqual(timeout,3300)
        preexec_fn()
        raw = cwd/'raw'
        raw.mkdir()
        shutil.copyfile(self.native_path,raw/'tranResponse.tran.tran')
        (cwd/'spectre.log').write_bytes(CLEAN_LOG)
        return SimpleNamespace(returncode=0)

    def test_five_native_collections_make_paired_summary_and_preserve_solver_records(self):
        self.assertEqual(self.trace_count,178)
        # These are individual task IDs, deliberately different from array IDs.
        jobs = ('757730','757729','757812','757813','757814')
        with patch.object(review.common.subprocess,'run',side_effect=self.solver):
            for case, job in zip(self.cases,jobs,strict=True):
                with patch.dict(os.environ,{'SLURM_JOB_ID':job}):
                    self.runner.run(case,self.root,Path(MODEL_ROOT),self.approval)
                case_dir = self.root/case['case_id']
                status = review.common.read(case_dir/'run_status.json')
                self.assertEqual(status['status'],'spectre_completed')
                self.assertEqual(status['slurm_job_id'],job)
                self.assertEqual(status['exit_code'],0)
                self.assertEqual(status['max_solver_file_bytes'],512*1024**2)
                measured = review.common.read(case_dir/'measurements.json')
                self.assertEqual(measured['run_status_sha256'],review.common.sha(case_dir/'run_status.json'))
                self.assertTrue(all(entry['metrics']['ADC_validation_input_count']==256 and
                                    entry['metrics']['FFE_validation_output_count']==240
                                    for entry in measured['metrics'].values()))
        self.assertEqual(self.solvers,5)
        summary = self.runner.summarize(self.root)
        self.assertEqual(summary['paired_delta_SER'],{'P_late':{'primary':0.,'secondary':0.},
                                                     'N_late':{'primary':0.,'secondary':0.}})
        self.assertEqual(len(summary['metrics']),5)
        self.assertEqual(summary['completed_cases'],5)
        for case, job in zip(self.cases,jobs,strict=True):
            resource = summary['resources'][case['case_id']]
            self.assertEqual(resource['slurm_task_id'],job)
            self.assertEqual(resource['raw_bytes'],self.native_path.stat().st_size)
            self.assertEqual(resource['solver_peak_RSS_KiB'],404000)
            self.assertGreaterEqual(resource['solver_wall_seconds'],0.)
        self.assertEqual(self.limits,[(512*1024**2,)*2]*5)
        first = self.root/self.cases[0]['case_id']
        before = {path:review.common.sha(path) for path in first.iterdir() if path.is_file()}
        with patch.object(review.common.subprocess,'run',side_effect=AssertionError('Completed case reran a solver')):
            self.runner.collect(self.cases[0],first,self.approval)
        self.assertTrue(all(review.common.sha(path)==sha for path,sha in before.items()))

    def test_collect_only_recovers_a_post_solver_failure(self):
        case = self.cases[0]
        with (patch.dict(os.environ,{'SLURM_JOB_ID':'757730'}),
              patch.object(review.common.subprocess,'run',side_effect=self.solver),
              patch.object(review,'measure_existing',side_effect=RuntimeError('Synthetic collector interruption'))):
            with self.assertRaisesRegex(RuntimeError,'collector interruption'):
                self.runner.run(case,self.root,Path(MODEL_ROOT),self.approval)
        directory = self.root/case['case_id']
        status_sha = review.common.sha(directory/'run_status.json')
        self.assertFalse((directory/'completion.json').exists())
        with patch.object(review.common.subprocess,'run',side_effect=AssertionError('Recovery ran solver')):
            self.runner.collect(case,directory,self.approval)
        self.assertEqual(review.common.sha(directory/'run_status.json'),status_sha)
        self.assertTrue((directory/'completion.json').is_file())
        self.assertEqual(self.solvers,1)

    def test_fatal_zero_exit_stays_incomplete_and_cannot_be_scored(self):
        case = self.cases[0]
        def fatal(argv, *, cwd, preexec_fn, **kwargs):
            preexec_fn()
            (cwd/'spectre.log').write_bytes(FATAL_LOG)
            return SimpleNamespace(returncode=0)
        with (patch.dict(os.environ,{'SLURM_JOB_ID':'757710'}),
              patch.object(review.common.subprocess,'run',side_effect=fatal)):
            with self.assertRaisesRegex(ValueError,'No clean Spectre completion'):
                self.runner.run(case,self.root,Path(MODEL_ROOT),self.approval)
        directory = self.root/case['case_id']
        status = review.common.read(directory/'run_status.json')
        self.assertEqual(status['status'],'spectre_evidence_incomplete')
        self.assertEqual(status['exit_code'],0)
        self.assertFalse((directory/'measurements.json').exists())
        with self.assertRaises((ValueError,FileNotFoundError,KeyError)):
            self.runner.collect(case,directory,self.approval)
        with self.assertRaises((ValueError,FileNotFoundError)):
            self.runner.summarize(self.root)

    def test_nonzero_exit_with_clean_log_cannot_be_collected(self):
        case = self.cases[0]
        def failed(argv, *, cwd, preexec_fn, **kwargs):
            preexec_fn()
            (cwd/'spectre.log').write_bytes(CLEAN_LOG)
            return SimpleNamespace(returncode=1)
        with (patch.dict(os.environ,{'SLURM_JOB_ID':'757711'}),
              patch.object(review.common.subprocess,'run',side_effect=failed)):
            with self.assertRaisesRegex(ValueError,'Solver failed or deck changed'):
                self.runner.run(case,self.root,Path(MODEL_ROOT),self.approval)
        directory = self.root/case['case_id']
        status = review.common.read(directory/'run_status.json')
        self.assertEqual(status['status'],'spectre_failed_or_source_changed')
        self.assertEqual(status['exit_code'],1)
        with self.assertRaises((ValueError,FileNotFoundError,KeyError)):
            self.runner.collect(case,directory,self.approval)
        with self.assertRaises((ValueError,FileNotFoundError)):
            self.runner.summarize(self.root)
        self.assertFalse((directory/'measurements.json').exists())

    def test_clean_zero_exit_without_native_arrays_is_not_a_valid_first_case(self):
        case = self.cases[0]
        def empty(argv, *, cwd, preexec_fn, **kwargs):
            preexec_fn()
            (cwd/'raw').mkdir()
            (cwd/'spectre.log').write_bytes(CLEAN_LOG)
            return SimpleNamespace(returncode=0)
        with (patch.dict(os.environ,{'SLURM_JOB_ID':'757730'}),
              patch.object(review.common.subprocess,'run',side_effect=empty)):
            with self.assertRaises((ValueError,FileNotFoundError)):
                self.runner.run(case,self.root,Path(MODEL_ROOT),self.approval)
        directory = self.root/case['case_id']
        self.assertFalse((directory/'measurements.json').exists())
        self.assertFalse((directory/'completion.json').exists())
        with self.assertRaises((ValueError,FileNotFoundError)):
            self.runner.summarize(self.root)

    def test_fatal_marker_overrides_a_clean_footer_and_zero_exit(self):
        case = self.cases[0]
        def contradictory(argv, *, cwd, preexec_fn, **kwargs):
            preexec_fn()
            (cwd/'raw').mkdir()
            (cwd/'raw'/'tranResponse.tran.tran').write_bytes(b'END\n')
            (cwd/'spectre.log').write_bytes(FATAL_LOG+CLEAN_LOG)
            return SimpleNamespace(returncode=0)
        with (patch.dict(os.environ,{'SLURM_JOB_ID':'757730'}),
              patch.object(review.common.subprocess,'run',side_effect=contradictory)):
            with self.assertRaisesRegex(ValueError,'fatal simulation'):
                self.runner.run(case,self.root,Path(MODEL_ROOT),self.approval)
        directory = self.root/case['case_id']
        self.assertFalse((directory/'measurements.json').exists())
        self.assertFalse((directory/'completion.json').exists())
        with self.assertRaisesRegex(ValueError,'fatal simulation'):
            self.runner.summarize(self.root)


if __name__=='__main__':
    unittest.main()
