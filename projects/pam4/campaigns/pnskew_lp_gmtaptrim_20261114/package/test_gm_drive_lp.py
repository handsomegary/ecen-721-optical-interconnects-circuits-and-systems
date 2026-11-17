"""Offline render, paired AC and operating-point checks for the driver study."""
import re
import unittest

import drive_summary as previous_summary
import gm_drive as previous
import gm_drive_lp as lp
import lp_summary
from replay_pilot import loaded


def mos_instances(deck):
    return {name: (tuple(nodes.split()), model) for name, nodes, model in
            re.findall(r'^(\w+) \(([^\n)]+)\) ([np]mos_lvt) ', deck, re.M)}


def old_short_case(launch, drive='p'):
    return next(case for case in previous.build_plan()['cases']
                if case['stage'] == 'short' and case['launch'] == launch and
                case['probe'] == 'full' and case['drive'] == drive)


class PreviousGMDrive(unittest.TestCase):
    def test_paired_plan_separates_drive_from_physical_configuration(self):
        cases = previous.build_plan()['cases']
        pairs = {}
        self.assertEqual(len({case['case_id'] for case in cases}), len(cases))
        for case in cases:
            pairs.setdefault(previous_summary.key(case), []).append(case['drive'])
        self.assertEqual(len(pairs) * 2, len(cases))
        self.assertTrue(all(sorted(drives) == ['n', 'p'] for drives in pairs.values()))

    def test_legacy_short_ss_index_bindings_are_preserved(self):
        cases = previous.build_plan()['cases']
        for index, launch, probe in [(0, 'bypass', 'full'), (2, 'ideal', 'full'),
                                     (10, 'cs16', 'full'), (14, 'cs12', 'dormant'),
                                     (16, 'ideal', 'dormant')]:
            p, n = cases[index:index+2]
            self.assertEqual((p['case_id'], n['case_id']),
                             (f'gmdrive_{index:03d}_ss_{launch}_p', f'gmdrive_{index+1:03d}_ss_{launch}_n'))
            self.assertEqual((p['probe'], n['probe']), (probe, probe))

    def test_original_cs16_and_ideal_use_same_route_and_restore_polarity(self):
        token = previous.gm.original.base.MODEL_TOKEN
        physical, ideal = (old_short_case(launch) for launch in ('cs16', 'ideal'))
        cs_deck = previous.render(physical, token)[0]
        ideal_deck = previous.render(ideal, token)[0]
        cs_mos, ideal_mos = mos_instances(cs_deck), mos_instances(ideal_deck)
        self.assertEqual(physical['route_thirds'], ideal['route_thirds'])
        self.assertEqual(physical['source_R_ohm'], ideal['source_R_ohm'])
        self.assertEqual(sum(bool(re.fullmatch(r'GMS[AB][PM]CS\d+', name)) for name in cs_mos), 64)
        self.assertFalse(any(re.fullmatch(r'GMS[AB][PM]CS\d+', name) for name in ideal_mos))
        self.assertIn('GMSAPVFG (GMSAPVGB 0) vsource dc=0.53', cs_deck)
        self.assertIn('GMSBPVFG (GMSBPVGB 0) vsource dc=0.1', cs_deck)
        self.assertIn('GMSAPDRV (PNC_PREP GMSAPVIN) vsource dc=0', cs_deck)
        self.assertIn('GMSAPDRV (GMSAPL X_cm PNC_PREP X_cm) vcvs gain=1', ideal_deck)
        self.assertIn('GMSBPDRV (GMSBPL X_cm PNC_PREP X_cm) vcvs gain=0', ideal_deck)
        for name, (nodes, model) in ideal_mos.items():
            if re.fullmatch(r'XM2[pm]\d+', name):
                other_input = 'X_c_m' if nodes[1] == 'X_c_p' else 'X_c_p'
                self.assertEqual(cs_mos[name], ((nodes[0], other_input, *nodes[2:]), model))

    def test_complex_hdd_reference_uses_both_drive_columns(self):
        frequencies = [7e9, 56e9]
        reference = [(1., 0., 0., 1.)] * 2
        switched = [(1j, -.25j, -.5j, .25j)] * 2
        z = previous_summary.hdd(frequencies, switched)
        self.assertEqual(z, 1j)
        self.assertAlmostEqual(previous_summary.ratio(z, previous_summary.hdd(frequencies, reference)), 0.)
        self.assertIsNone(previous_summary.ratio(z, 0j))
        self.assertEqual(previous_summary.column_projection(switched)[0], (1.5j, 0, 0, .5j))

    def test_analog_headroom_excludes_idle_driver_and_bias_switches(self):
        case = old_short_case('cs16')
        deck = '\n'.join((
            'GMSAPCS0 (GMSAPFD GMSAPFG 0 0) nmos_lvt l=30n',
            'GMSBPCS0 (GMSBPFD GMSBPFG 0 0) nmos_lvt l=30n',
            'GMSAIP0 (GMSAEB0 GMSAEN0 GF_VDD GF_VDD) pmos_lvt l=30n',
            'GMSAPM0 (GMSAPD GMSAPG GMSAPS 0) nmos_lvt l=30n',
            'XT2p0 (X_s2_p X_vb 0 0) nmos_lvt l=60n',
        ))
        def op(vds, vdsat):
            return dict(vds=vds, vdsat=vdsat, ids=.001, gm=.005, region=2)
        data = {'saved_mos_oppoint': {
            'GMSAPCS0': op(.25, .1), 'GMSBPCS0': op(0., .1),
            'GMSAIP0': op(-.81, -.08), 'GMSAPM0': op(.4, .12), 'XT2p0': op(.107, .1),
        }}
        result = previous_summary.headroom(case, data, deck)
        self.assertEqual(set(result), {'GMSAPCS0', 'GMSAPM0', 'XT2p0'})
        self.assertEqual(result['GMSAPCS0']['role'], 'CS_enabled')
        self.assertAlmostEqual(result['XT2p0']['margin_V'], .007)
        data['saved_mos_oppoint'].pop('GMSAPCS0')
        with self.assertRaisesRegex(ValueError, 'Incomplete active MOS OP'):
            previous_summary.headroom(case, data, deck)


class LowPowerGMDrive(unittest.TestCase):
    def setUp(self):
        self.cases = lp.build_plan()['cases']
        self.token = previous.gm.original.base.MODEL_TOKEN

    def case(self, launch, *, source_r=0, count_b=0):
        return next(case for case in self.cases if case['launch'] == launch and
                    case['drive'] == 'p' and case['count_b'] == count_b and
                    case['source_R_ohm'] == source_r and case['probe'] == 'full')

    def render(self, launch, *, source_r=0, count_b=0):
        case = self.case(launch, source_r=source_r, count_b=count_b)
        deck, rails, ac, dc, currents, difference = lp.render(case, self.token)
        self.assertFalse(re.search(r'^\w+ tran\b', deck, re.M))
        self.assertIn('--- parent.scs\n+++ bench.scs\n', difference)
        return case, deck, rails, ac, dc, currents

    def test_plan_pairs_share_all_physical_parameters(self):
        by_config = {}
        for case in self.cases:
            cfg = tuple(sorted((name, repr(value)) for name, value in case.items()
                               if name not in ('case_id', 'drive')))
            by_config.setdefault(cfg, []).append(case['drive'])
        self.assertEqual(len({case['case_id'] for case in self.cases}), len(self.cases))
        self.assertTrue(all(sorted(drives) == ['n', 'p'] for drives in by_config.values()))
        self.assertEqual({case['topology'] for case in self.cases},
                         {'branch', 'shared', 'direct', 'reference'})

    def test_shared_fanout_uses_one_cs_bank_per_leg(self):
        case, deck, rails, ac, dc, currents = self.render('shared16', source_r=25)
        self.assertEqual(case['topology'], 'shared')
        devices = mos_instances(deck)
        for leg in 'PM':
            self.assertEqual(sum(bool(re.fullmatch(r'GMSH'+leg+r'CS\d+', name)) for name in devices), 16)
            self.assertIn('GMSH'+leg+'FD', ac)
            self.assertIn('GMSH'+leg+'FD', dc)
            for bank in 'AB':
                self.assertIn(f'GMS{bank}{leg}DRV (GMSH{leg}L GMS{bank}{leg}L) vsource dc=0', deck)
                self.assertIn(f'GMS{bank}{leg}RT (GMS{bank}{leg}G X_cm) resistor r=25', deck)
        self.assertFalse(any(re.fullmatch(r'GMS[AB][PM]CS\d+', name) for name in devices))
        self.assertEqual(devices['XM2p0'][0][1], 'X_c_m')
        self.assertEqual(devices['XM2m0'][0][1], 'X_c_p')
        self.assertIn('GMSAPVD:p', ac)

    def test_shared_amp_op_is_active_even_when_one_branch_has_no_tail(self):
        case = self.case('shared16', source_r=25)
        self.assertEqual(case['count_b'], 0)
        deck = ('GMSHPCS0 (GMSHPFD GMSHPFG 0 0) nmos_lvt l=30n\n'
                'GMSHMCS0 (GMSHMFD GMSHMFG 0 0) nmos_lvt l=30n\n'
                'GMSBPM0 (GMSBPD GMSBPG GMSBPS 0) nmos_lvt l=30n\n')
        op = dict(vds=.25, vdsat=.1, ids=.001, gm=.005, region=2)
        data = {'saved_mos_oppoint': {'GMSHPCS0': op, 'GMSHMCS0': op}}
        result = previous_summary.headroom(case, data, deck)
        self.assertEqual(set(result), {'GMSHPCS0', 'GMSHMCS0'})
        self.assertTrue(all(row['role'] == 'CS_enabled' for row in result.values()))
        data['saved_mos_oppoint'].pop('GMSHPCS0')
        with self.assertRaisesRegex(ValueError, 'Incomplete active MOS OP: GMSHPCS0'):
            previous_summary.headroom(case, data, deck)

    def test_low_power_branch_uses_declared_peaking_and_preserves_tail_code(self):
        case, deck, _, _, _, _ = self.render('lp14lo120')
        self.assertEqual(case['topology'], 'branch')
        devices = mos_instances(deck)
        self.assertEqual(sum(bool(re.fullmatch(r'GMS[AB][PM]CS\d+', name)) for name in devices), 56)
        for bank in 'AB':
            for leg in 'PM':
                prefix = 'GMS' + bank + leg
                self.assertIn(f'{prefix}RD ({prefix}FD {prefix}LP) resistor r=33', deck)
                self.assertIn(f'{prefix}LPK ({prefix}LP GF_VDD) inductor l=120p', deck)
        self.assertEqual(devices['XM2p0'][0][1], 'X_c_m')
        self.assertIn('GMSAVE0 (GMSAEN0 0) vsource dc=%.9g' % case['vdd_V'], deck)
        self.assertIn('GMSBVE0 (GMSBEN0 0) vsource dc=0', deck)

    def test_direct_exposes_physical_input_load_and_preserves_polarity(self):
        case, deck, rails, ac, _, _ = self.render('direct')
        self.assertEqual(case['topology'], 'direct')
        self.assertIn('LPRP (PNC_PREP LP2P) resistor r=100', deck)
        self.assertIn('LPRN (PNC_PREN LP2N) resistor r=100', deck)
        self.assertRegex(deck, r'(?m)^LPCP \(LP2P X_cm\) capacitor c=85\.26157[0-9]*f$')
        self.assertRegex(deck, r'(?m)^LPCN \(LP2N X_cm\) capacitor c=85\.26157[0-9]*f$')
        self.assertNotRegex(deck, r'(?m)^GDR[PN] ')
        self.assertNotRegex(deck, r'(?m)^GMS[ABH][PM]CS\d+ ')
        devices = mos_instances(deck)
        self.assertEqual(devices['XM2p0'][0][1], 'X_c_p')
        self.assertEqual(devices['XM2m0'][0][1], 'X_c_m')
        self.assertIn('GMSAPVD:p', ac)
        self.assertIn('GMSAPRT (GMSAPG X_cm) resistor r=25', deck)
        for bank in 'AB':
            self.assertIn(f'GMS{bank}PDRV (LP2P GMS{bank}PL) vsource dc=0', deck)
            self.assertIn(f'GMS{bank}MDRV (LP2N GMS{bank}ML) vsource dc=0', deck)
            self.assertIn(f'GMS{bank}PDRV:p', ac)
            self.assertIn(f'GMS{bank}MDRV:p', ac)

    def test_source_resistance_comparison_uses_distinct_current_planes(self):
        _, ideal0, *_ = self.render('ideal')
        _, ideal25, *_ = self.render('ideal', source_r=25)
        _, bypass25, *_ = self.render('bypass', source_r=25)
        self.assertNotRegex(ideal0, r'(?m)^GDR[PN] ')
        self.assertIn('GDRP (PNC_PREP GDRPINP) resistor r=25', ideal25)
        self.assertIn('GMSAPDRV (GMSAPL X_cm GDRPINP X_cm) vcvs gain=1', ideal25)
        self.assertIn('LPBRP (PNC_PREP LPBPP) resistor r=25', bypass25)
        self.assertIn('ACNPRS (LPBPP X_ip) resistor r=25', bypass25)

    def test_direct_ideal_reference_keeps_matching_ladder_without_rc_boundary(self):
        direct, physical, *_ = self.render('direct', count_b=2)
        ideal, reference, *_ = self.render('direct_ideal', count_b=2)
        for field in ('route_thirds', 'process', 'count_b', 'source_R_ohm'):
            self.assertEqual(direct[field], ideal[field])
        self.assertNotRegex(reference, r'(?m)^LP[RC][PN] ')
        for prefix in ('GMSAP', 'GMSAM', 'GMSBP', 'GMSBM'):
            def ladder(deck):
                return re.findall(r'(?m)^'+prefix+r'\d\d(?:LA|LB|RA|RB|C) [^\n]+$', deck)
            self.assertTrue(ladder(physical))
            self.assertEqual(ladder(physical), ladder(reference))
            self.assertIn(f'{prefix}RS ({prefix}L {prefix}I) resistor r=1m', reference)

    def test_shared_50_ohm_scales_l_and_c_and_far_termination(self):
        _, reference, *_ = self.render('shared16', source_r=25)
        _, scaled, *_ = self.render('shared16z50', source_r=25)
        self.assertIn('GMSAP00LA (GMSAPI GMSAP00A) inductor l=6.5p', reference)
        self.assertIn('GMSAP00C (GMSAP00M 0) capacitor c=20.8f', reference)
        self.assertIn('GMSAP00LA (GMSAPI GMSAP00A) inductor l=13p', scaled)
        self.assertIn('GMSAP00C (GMSAP00M 0) capacitor c=10.4f', scaled)
        self.assertIn('GMSAPRT (GMSAPG X_cm) resistor r=50', scaled)
        self.assertIn('GMSAPRT (GMSAPG X_cm) resistor r=25', reference)

    def test_summary_keys_pair_each_case_exactly_once(self):
        keys = {(lp_summary.config(case), case['drive']) for case in self.cases}
        self.assertEqual(len(keys), len(self.cases))
        self.assertEqual({case['stage'] for case in self.cases[:28]}, {'pilot'})
        self.assertEqual(self.cases[28]['stage'], 'architecture')

    def test_source_loading_solves_full_two_port(self):
        identity = [1, 0, 0, 1]
        admittance = [.01+.01j, -.002j, .003j, .015+.01j]
        self.assertEqual(loaded(identity, admittance, 0), identity)
        a,b,c,d = loaded(identity, admittance, 25)
        e,f,g,h = [25*v for v in admittance]
        self.assertAlmostEqual(a*(1+e)+b*g, 1)
        self.assertAlmostEqual(a*f+b*(1+h), 0)
        self.assertAlmostEqual(c*(1+e)+d*g, 0)
        self.assertAlmostEqual(c*f+d*(1+h), 1)

    def test_direct_50_ohm_ideal_control_exists_at_both_codes(self):
        for code in (0,2):
            direct = self.case('directz50', count_b=code)
            ref = self.case('direct_idealz50', count_b=code)
            self.assertEqual(direct['route_thirds'], ref['route_thirds'])
            self.assertEqual(direct['Z0_ohm'], ref['Z0_ohm'])


if __name__ == '__main__':
    unittest.main()
