"""Diagnostic only: rerun Switch64 summary with check_grid ignoring the final
(stop-truncated) interval. The package itself is not modified."""
import sys, math
sys.path.insert(0, sys.argv[1])
import gm_switch64_dense as dn, olympus_common as common
orig = dn.check_grid
def check_grid(grid, profile):
    den = dn.DENSITY[profile]
    lim = 10**(1.001/den)
    common.need(len(grid) >= math.floor(den*math.log10(145e9/1000)) and grid[-1] >= 145e9
                and all(0 < x < y <= x*lim for x, y in zip(grid[:-2], grid[1:-1]))
                and grid[-2] < grid[-1] <= grid[-2]*10**(3.001/den), 'grid')
dn.check_grid = check_grid
import gm_switch64
sys.argv = ['gm_switch64.py'] + sys.argv[2:]
gm_switch64.main()
