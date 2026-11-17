"""Decode the static LP14 global tap selectors and eight tail units.

Each RF ladder offers taps 6 through 16. Bank A reaches the even taps;
bank B reaches the odd taps. A selector ordinal sets the P tap and its
complementary N tap together. The right-hand interpolation weight is a
logical weight and can belong to either physical bank.
"""

EVEN_TAPS = (6, 8, 10, 12, 14, 16)
ODD_TAPS = (7, 9, 11, 13, 15)
UNITS = 8
ZERO_CODE = 40
MAX_CODE = 80


def _configuration(logical_code, left_tap, right_weight):
    if left_tap in EVEN_TAPS:
        a_p, b_p = left_tap, left_tap + 1
        count_b = right_weight
    else:
        a_p, b_p = left_tap + 1, left_tap
        count_b = UNITS - right_weight
    selector_a = EVEN_TAPS.index(a_p)
    selector_b = ODD_TAPS.index(b_p)
    section_delta = 2 * (left_tap + right_weight / UNITS) - 22
    return {
        'logical_code':logical_code,
        'segment':left_tap,
        'left_tap':left_tap,
        'right_weight':right_weight,
        'tap_a_p':a_p,
        'tap_a_n':22-a_p,
        'tap_b_p':b_p,
        'tap_b_n':22-b_p,
        'selector_a':selector_a,
        'selector_b':selector_b,
        'count_b':count_b,
        'tail_mask_a':(1<<(UNITS-count_b))-1,
        'tail_mask_b':(1<<count_b)-1,
        'hardware_word':selector_a<<7 | selector_b<<4 | count_b,
        'direction':(section_delta > 0) - (section_delta < 0),
        'target_nominal_sections_delta':section_delta,
    }


def decode(logical_code):
    """Return the canonical candidate state for one nominal logical index.

    At a shared anchor, prefer the preceding segment's terminating state.
    Zero uses tap 11 on bank B with A's mux on the following tap 12.
    The alternate loaded setting at each anchor is available via
    seam_aliases() for measured pruning before publishing the final LUT.
    """
    if type(logical_code) is not int or not 0 <= logical_code <= MAX_CODE:
        raise ValueError('Logical index must be an integer from 0 through 80')
    if logical_code in (0,ZERO_CODE):
        return _configuration(logical_code,6+logical_code//UNITS,0)
    segment,weight = divmod(logical_code-1,UNITS)
    return _configuration(logical_code,6+segment,weight+1)


def codes():
    """List nominally ordered code candidates from negative to positive delay."""
    return [decode(code) for code in range(MAX_CODE+1)]


def seam_aliases():
    """Return the nine other RF loading states at the nine interior anchors."""
    return [_configuration(code,6+code//UNITS-int(code==ZERO_CODE),
                           UNITS if code==ZERO_CODE else 0)
            for code in range(UNITS,MAX_CODE,UNITS)]
