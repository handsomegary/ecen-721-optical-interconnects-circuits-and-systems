from pathlib import Path
from datetime import datetime, timezone
import json
import tempfile
import unittest
from unittest.mock import patch

import c0_plate_m60 as app
from c0_offset_audit import compare_residuals, stimulus_audit


class PlateM60Tests(unittest.TestCase):
    def test_deck_only_changes_expected_control_voltages(self):
        meta = app.deck_delta()
        self.assertEqual(meta['case_id'],'c0f_payload_a_cm60_phm1')
        self.assertEqual(len(app.CHANGED),32)
        self.assertEqual(app.formal.deck.SKEW_PS['a'],4.464285714285714)

    def test_approval_binds_manifest_case_selections_and_prior_rescore(self):
        pins = {'selected_phase.json':'fixture phase','selected_codes.json':'fixture codes'}
        approval = app.authorization(pins,'fixture rescore',Path.cwd())
        self.assertEqual(approval['case_id'],'c0f_payload_a_cm60_phm1')
        self.assertEqual(approval['deck_sha256'],app.CANDIDATE_SHA)
        self.assertEqual(approval['selection_files_sha256'],pins)
        self.assertEqual(approval['baseline_rescore_sha256'],'fixture rescore')
        self.assertEqual(approval['max_new_solves'],1)
        self.assertEqual(approval['authorized_new_run_root'],str(Path.cwd()))

    def test_unauthorized_approval_cannot_stage_or_run(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            approval = root/'approval.json'
            expected = app.authorization({},'fixture rescore',root)
            approval.write_text(json.dumps(dict(expected,approved=False)),encoding='ascii')
            with patch.object(app.formal,'stage_case') as stage:
                with self.assertRaises(ValueError):
                    app.run(root,{}, {}, root/'models',approval,expected)
                stage.assert_not_called()

    def test_bound_run_can_collect_again_without_a_second_solver(self):
        class Clock(datetime):
            @classmethod
            def now(cls, tz):
                return cls(2026,11,15,tzinfo=timezone.utc).astimezone(tz)

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            approval = root/'approval.json'
            expected = app.authorization({},'fixture rescore',root)
            approval.write_text(json.dumps(expected),encoding='ascii')
            case = root/expected['case_id']
            case.mkdir()
            for name in ('bench.scs','case.json'):
                (case/name).write_text('fixture',encoding='ascii')

            def run_stub(directory, deck_sha, metadata, timeout, solver, env):
                self.assertEqual(timeout,4200)
                self.assertEqual(metadata['extension_approval_sha256'],app.common.sha(approval))
                (directory/'execution_intent.json').write_text(json.dumps(metadata),encoding='ascii')
                (directory/'run_status.json').write_text('{}',encoding='ascii')

            with (patch.object(app,'datetime',Clock),
                  patch.dict(app.os.environ,SLURM_JOB_ID='fixture'),
                  patch.object(app.common,'checked_root',return_value=root),
                  patch.object(app.common,'environment',return_value=('spectre',{})),
                  patch.object(app.common,'run_classic',side_effect=run_stub) as solver,
                  patch.object(app.formal,'stage_case',return_value=(case,app.deck_delta())),
                  patch.object(app.formal,'collect') as collect):
                for _ in range(2):
                    app.run(root,{}, {}, root/'models',approval,expected)
                self.assertEqual(solver.call_count,1)
                self.assertEqual(collect.call_count,2)

    def test_pair_preserves_same_payload_centers_at_both_sample_counts(self):
        def fixture(errors):
            return {'planes':{plane:{window:dict(sample_count=count,symbol_errors=errors,
                ffe_center_tx_indices=[632-count,632],SER=errors/count,
                prediction_RMSE_in_target_symbol_units=.3) for window,count in (('full',496),('late_rescore',176))}
                for plane in app.score.aligned.PLANES}}
        baseline,candidate = fixture(12),fixture(2)
        result = app.paired(baseline,candidate)
        for plane in result.values():
            self.assertEqual(plane['full']['delta_symbol_errors'],-10)
            self.assertAlmostEqual(plane['late_rescore']['delta_SER'],-10/176)
        candidate['planes']['primary']['full']['ffe_center_tx_indices'] = [137,633]
        with self.assertRaises(ValueError):
            app.paired(baseline,candidate)

    def test_stimulus_identity_and_separate_label_mix(self):
        stimulus = stimulus_audit()
        self.assertTrue(stimulus['non_stimulus_deck_identical'])
        self.assertAlmostEqual(stimulus['training_initial_differential_V'],.2/3)
        self.assertAlmostEqual(stimulus['payload_initial_differential_V'],-.2)
        train = dict(frozen_intercept_target_units=.2,mean_tap_linear_contributions_target_units=[.1],
            mean_true_target_units=-.1,mean_quantization_contribution_target_units=.001,
            center_symbol_histogram=[5,5,5,5],mean_residual_by_true_level=[.1,.2,.3,.4])
        payload = dict(train, center_symbol_histogram=[2,8,8,2],
                       mean_residual_by_true_level=[.3,.4,.5,.6])
        shift = compare_residuals(train,payload)
        self.assertEqual(shift['delta_frozen_intercept'],0)
        self.assertAlmostEqual(shift['residual_delta_from_label_mix_at_training_residuals'],0.)
        self.assertAlmostEqual(shift['residual_delta_within_true_levels_at_payload_mix'],.2)
        self.assertAlmostEqual(shift['equal_class_weight_delta'],.2)


if __name__=='__main__':
    unittest.main()
