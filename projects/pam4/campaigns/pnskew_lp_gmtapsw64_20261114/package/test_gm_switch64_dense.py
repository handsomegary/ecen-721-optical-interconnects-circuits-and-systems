import cmath
import math
import unittest

import gm_gmtap_common as common_design
import gm_switch64_dense as dense


def control_case(profile, group='divider', code=1):
    original = next(c for c in common_design.build_plan()['cases']
                    if c['group']==group and c['process']=='ff' and c['code']==code and c['drive']=='p')
    return dict(original,dense_profile=profile,stage='dense')


def grid(density):
    return [1000*10**(i/density) for i in range(math.floor(density*math.log10(150e9/1000))+1)]


def decisions(values):
    return {name:{'steps_ps':dict(zip(dense.EDGES,(.263,value,value,.263))),
                  'by_code':{0:{'XT2_static_pass':True}}}
            for name,value in zip(dense.PROFILES,values)}


class DenseSwitchTests(unittest.TestCase):
    def test_grid_and_solver_profiles_keep_circuit_topology(self):
        decks = {}
        for profile in dense.PROFILES:
            deck,*_ = dense.render(control_case(profile),common_design.BASE.MODEL_TOKEN)
            decks[profile] = deck
        for profile in ('grid200','grid400'):
            self.assertEqual(decks[profile],decks['base100'].replace(
                dense.AC_PREFIX+'100',dense.AC_PREFIX+str(dense.DENSITY[profile])))
        self.assertEqual(decks['tight400'],decks['grid400'].replace(
            'reltol=1e-4 vabstol=1u iabstol=1p','reltol=1e-5 vabstol=0.1u iabstol=0.1p'))
        self.assertIn('GMSKVRU (GMSKVDIVIN GMSKV1RAW) resistor r=375',decks['base100'])
        self.assertIn('GMSKVRD (GMSKV1RAW 0) resistor r=14125',decks['base100'])
        self.assertIn('GMSKVC1 (GMSKVBIAS 0) capacitor c=2p',decks['base100'])
        base,*_ = dense.render(control_case('tight400','baseline',0),common_design.BASE.MODEL_TOKEN)
        self.assertIn(dense.AC_PREFIX+'400',base)

    def test_grid_verifies_density_and_full_band(self):
        dense.check_grid(grid(200),'grid200')
        with self.assertRaisesRegex(ValueError,'400-point'):
            dense.check_grid(grid(200),'grid400')
        with self.assertRaisesRegex(ValueError,'200-point'):
            dense.check_grid(grid(200)[12:],'grid200')

    def test_match_both_signed_steps_using_historical_weight_definition(self):
        fs = grid(200)
        op = {tag:{'region':2,'vds':.4,'vdsat':.2} for tag in dense.trim.XT2_INSTANCES}
        pair = {side:{'frequency_Hz':fs,'DC_voltage_V':{'X_vb':.58,'GMSKVBIAS':.5648},
                      'DC_supply_power_W':{'XVb:p':0},'saved_mos_oppoint':op,
                      'traces':{'X_h0p':[[int(side=='p'),0.]]*len(fs),
                                'X_h0m':[[int(side=='n'),0.]]*len(fs)}}
                for side in 'pn'}
        states = {code:(dict(bias_kind='divider_lowz',vb1_V=.565),pair,
                         [[cmath.exp(-1j*math.tau*f*code*.24e-12),0,0,1] for f in fs],{})
                  for code in dense.CODES}
        outcome = dense.evaluate_family('grid200',({},pair,None,{}),states)
        self.assertTrue(all(row['XT2_static_pass'] for row in outcome['by_code'].values()))
        for step in outcome['steps_ps'].values():
            self.assertAlmostEqual(step,.24,delta=1e-7)

    def test_resolved_margin_retains_full_unrounded_nominal_result(self):
        status,steps = dense.decide(decisions((.4947919156883,.49501,.49502,.49503)))
        self.assertEqual(status,'passes_nominal_dense_recheck')
        self.assertAlmostEqual(steps[0,1]['tight400_margin_to_0p50_fs'],4.97)
        self.assertAlmostEqual(steps[-1,0]['observed_refinement_proxy_fs'],.02)
        self.assertAlmostEqual(steps[0,1]['tight400_minus_base100_fs'],.2380843117)

    def test_fails_above_spec_and_distinguishes_unresolved_numerics(self):
        self.assertEqual(dense.decide(decisions((.4948,.495,.496,.501)))[0],
                         'fails_nominal_step_screen')
        self.assertEqual(dense.decide(decisions((.4948,.495,.497,.498)))[0],
                         'numerical_margin_unresolved')
        self.assertEqual(dense.decide(decisions((.4948,.4995,.4997,.4999)))[0],
                         'numerical_margin_unresolved')

    def test_missing_grid_or_xt2_status_cannot_pass(self):
        valid = decisions((.4948,.4949,.495,.4951))
        valid['grid400']['by_code'][0]['XT2_static_pass'] = None
        self.assertEqual(dense.decide(valid)[0],'XT2_static_screen_unresolved_or_failed')
        del valid['tight400']
        self.assertEqual(dense.decide(valid)[0],'incomplete_dense_evidence')
