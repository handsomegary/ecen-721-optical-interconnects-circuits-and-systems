import unittest

from global_codes import EVEN_TAPS, ODD_TAPS, codes, decode, seam_aliases


class GlobalCodes(unittest.TestCase):
    def test_nominal_order_and_hardware_distinct(self):
        book = codes()
        self.assertEqual([r['logical_code'] for r in book],list(range(81)))
        self.assertEqual([r['target_nominal_sections_delta'] for r in book],
                         [i/4 for i in range(-40,41)])
        all_states = book+seam_aliases()
        self.assertEqual(len({r['hardware_word'] for r in all_states}),90)
        for row in all_states:
            self.assertEqual(EVEN_TAPS[row['hardware_word']>>7],row['tap_a_p'])
            self.assertEqual(ODD_TAPS[(row['hardware_word']>>4)&7],row['tap_b_p'])
            self.assertEqual(row['hardware_word']&15,row['count_b'])
            self.assertEqual(row['tap_a_p']+row['tap_a_n'],22)
            self.assertEqual(row['tap_b_p']+row['tap_b_n'],22)
            self.assertEqual(abs(row['tap_a_p']-row['tap_b_p']),1)
            self.assertEqual(row['tail_mask_a'].bit_count()+row['tail_mask_b'].bit_count(),8)
            self.assertEqual(row['tail_mask_b'].bit_count(),row['count_b'])

    def test_anchor_aliases_keep_active_tap(self):
        for other in seam_aliases():
            primary = decode(other['logical_code'])
            self.assertEqual(primary['count_b'],other['count_b'])
            bank = 'b' if primary['count_b'] else 'a'
            self.assertEqual(primary[f'tap_{bank}_p'],other[f'tap_{bank}_p'])
            self.assertNotEqual(primary['hardware_word'],other['hardware_word'])
        zero = decode(40)
        self.assertEqual((zero['tap_b_p'],zero['tap_b_n'],zero['count_b'],zero['direction']),
                         (11,11,8,0))

    def test_invalid_indices(self):
        for code in (-1,81,True,4.0,'4'):
            with self.assertRaises(ValueError):
                decode(code)


if __name__=='__main__':
    unittest.main()
