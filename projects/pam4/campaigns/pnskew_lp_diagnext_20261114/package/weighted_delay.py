"""Evaluate a differential delay from dense complex AC voltage transfers.

Each matrix is in (Hpp, Hpn, Hnp, Hnn) order. Matrix elements may be
complex numbers or [real, imaginary] pairs. H_code and H_bypass map the
launched P/N voltages to the same post-trim observation plane. The third
matrix maps the bypass fixture to the tracked sample nodes and supplies
fixed spectral weights. This is an AC diagnostic without a SER prediction.
"""

import bisect
import cmath
import math


F_NYQUIST_HZ = 56e9
SYMBOL_RATE_BAUD = 112e9
CHANNEL_RC_S = 100.0 * 85.26157665637249e-15
BRANCH_FLOOR_RELATIVE_TO_BYPASS_PEAK = 0.01
ENDPOINT_PS = 0.5e12 / SYMBOL_RATE_BAUD
BANDS_HZ = {"7_to_56_GHz": 7e9, "14_to_56_GHz": 14e9}


def _matrix(row):
    if len(row) != 4:
        raise ValueError("Expected Hpp, Hpn, Hnp, Hnn in each matrix")
    values = tuple(complex(*item) if isinstance(item, (tuple, list)) else complex(item)
                   for item in row)
    if not all(math.isfinite(z.real) and math.isfinite(z.imag) for z in values):
        raise ValueError("Nonfinite matrix element")
    return values


def _sample(frequencies, matrices, f):
    right = bisect.bisect_left(frequencies, f)
    if right < len(frequencies) and frequencies[right] == f:
        return matrices[right]
    left = right - 1
    fraction = math.log(f / frequencies[left]) / math.log(frequencies[right] / frequencies[left])
    return tuple(a + fraction * (b - a) for a, b in zip(matrices[left], matrices[right]))


def _branches(matrix):
    pp, pn, np, nn = matrix
    return pp - pn, nn - np


def _modes(matrix):
    pp, pn, np, nn = matrix
    return (pp - pn - np + nn) / 2, pp + pn - np - nn


def _db(ratio):
    return 20 * math.log10(ratio) if ratio > 0 else None


def _complex_pair(value):
    return [value.real, value.imag] if value is not None else None


def _weights(f, track_bypass_matrix):
    omega_channel = math.tau * f * CHANNEL_RC_S
    nrz_arg = math.pi * f / SYMBOL_RATE_BAUD
    nrz_magnitude = math.sin(nrz_arg) / nrz_arg
    channel_magnitude = 1 / (1 + omega_channel ** 2)
    track_dm, _ = _modes(track_bypass_matrix)
    return (nrz_magnitude * channel_magnitude * abs(track_dm)) ** 2


def _quadrature(frequencies):
    widths = [b - a for a, b in zip(frequencies, frequencies[1:])]
    return [widths[0] / 2, *((a + b) / 2 for a, b in zip(widths, widths[1:])), widths[-1] / 2]


def _relative_phase_series(rows, branch_floors):
    phases = []
    previous = None
    for code, reference, _ in rows:
        p, n = _branches(code)
        rp, rn = _branches(reference)
        if (min(abs(p), abs(rp)) <= branch_floors[0]
                or min(abs(n), abs(rn)) <= branch_floors[1]):
            phases.append(None)
            previous = None
            continue
        angle = cmath.phase((p / n) / (rp / rn))
        if previous is not None:
            angle = previous + math.remainder(angle - previous, math.tau)
        phases.append(angle)
        previous = angle
    return phases


def _band_report(frequencies, rows, phases, low_hz):
    selected = [(f, row, phase) for f, row, phase in zip(frequencies, rows, phases) if f >= low_hz]
    fs = [item[0] for item in selected]
    phase = [item[2] for item in selected]
    report = {"status": "UNRESOLVED", "limits_Hz": [low_hz, F_NYQUIST_HZ], "grid_count": len(fs),
              "tau_effective_ps": None, "weighted_phase_rms_ps": None, "worst_phase_error_ps": None,
              "target_known_diagnostics": {}, "branch_null_frequencies_Hz": [f for f, _, p in selected if p is None]}
    if report["branch_null_frequencies_Hz"]:
        report["reason"] = "Branch transfer is below the bypass-referenced floor inside this band"
        return report
    integration = _quadrature(fs)
    weights = [_weights(f, row[2]) * df for (f, row, _), df in zip(selected, integration)]
    omega = [math.tau * f * 1e-12 for f in fs]
    norm = math.fsum(w * a * a for w, a in zip(weights, omega))
    if norm <= 0:
        report["reason"] = "Bypass track transfer supplies no spectral weight"
        return report
    fitted = -math.fsum(w * a * p for w, a, p in zip(weights, omega, phase)) / norm

    def deviation(compared_delay_ps):
        errors = [p + a * compared_delay_ps for p, a in zip(phase, omega)]
        return {"weighted_phase_rms_ps": math.sqrt(math.fsum(w * e * e for w, e in zip(weights, errors)) / norm),
                "worst_phase_error_ps": max(abs(e / a) for e, a in zip(errors, omega)),
                "signed_phase_delay_error_at_56_GHz_ps": -errors[-1] / omega[-1]}

    local_delay = [-(b - a) / (g - f) for a, b, f, g in zip(phase, phase[1:], omega, omega[1:])]
    equivalent_delay = [-p / a for p, a in zip(phase, omega)]
    report.update(status="MEASURED_AC_ESTIMATE", tau_effective_ps=fitted, **deviation(fitted),
                  phase_delay_span_ps=[min(equivalent_delay), max(equivalent_delay)],
                  local_group_delay_span_ps=[min(local_delay), max(local_delay)])
    for injected in (-ENDPOINT_PS, 0.0, ENDPOINT_PS):
        report["target_known_diagnostics"][format(injected, ".9f")] = {
            "injected_skew_ps": injected,
            "required_correction_ps": -injected,
            "signed_effective_residual_ps": fitted + injected,
            **deviation(-injected),
        }
    return report


def evaluate(f_Hz, H_code, H_bypass, H_track_bypass):
    """Return band fit and dispersion, plus 56 GHz diagnostics for one code.

    For a launched DM input, the sign-normalized leg transfers are
    Hpp-Hpn and Hnn-Hnp. Their complex ratio is divided by the bypass ratio
    before dense-grid phase unwrapping. Fit the phase to a pure delay through
    zero with fixed |sinc(f/UI_rate) H_channel Hdd_track,bypass|^2 weights and
    trapezoidal linear-frequency integration. The sinc assumes rectangular
    112 GBd NRZ pulses and omits the 1 ps PWL edge. The 7 to 56 GHz band is
    primary and 14 to 56 GHz is a sensitivity check.

    A branch magnitude at or below 1% of its bypass peak in 7 to 56 GHz
    makes that frequency unresolved. An in-band unresolved frequency
    disqualifies the band fit so a transfer null cannot improve the score.
    Target-known diagnostics are for offline design review and scoring.
    """
    frequencies = tuple(float(f) for f in f_Hz)
    matrices = tuple(tuple(_matrix(row) for row in series) for series in (H_code, H_bypass, H_track_bypass))
    if (len(frequencies) < 3 or any(len(series) != len(frequencies) for series in matrices)
            or not all(math.isfinite(f) and f > 0 for f in frequencies)
            or any(a >= b for a, b in zip(frequencies, frequencies[1:]))
            or frequencies[0] > min(BANDS_HZ.values()) or frequencies[-1] < F_NYQUIST_HZ):
        raise ValueError("Expected a finite positive increasing grid covering 7 to 56 GHz and matching matrix rows")
    grid = sorted({f for f in frequencies if f <= F_NYQUIST_HZ} | set(BANDS_HZ.values()) | {F_NYQUIST_HZ})
    rows = [tuple(_sample(frequencies, series, f) for series in matrices) for f in grid]
    references = [_branches(row[1]) for f, row in zip(grid, rows) if f >= min(BANDS_HZ.values())]
    branch_floors = [BRANCH_FLOOR_RELATIVE_TO_BYPASS_PEAK * max(abs(pair[index]) for pair in references)
                     for index in (0, 1)]
    phases = _relative_phase_series(rows, branch_floors)
    bands = {label: _band_report(grid, rows, phases, low) for label, low in BANDS_HZ.items()}

    code, reference, _ = rows[-1]
    dm, cm_to_dm = _modes(code)
    dm0, cm_to_dm0 = _modes(reference)
    p, n = _branches(code)
    phase_delay = -phases[-1] / (math.tau * F_NYQUIST_HZ * 1e-12) if phases[-1] is not None else None
    normalized_cm = (cm_to_dm - cm_to_dm0) / abs(dm0) if abs(dm0) > 0 else None
    at_nyquist = {
        "frequency_Hz": F_NYQUIST_HZ,
        "differential_phase_delay_vs_bypass_ps": phase_delay,
        "P_branch_magnitude_V_per_V": abs(p),
        "N_branch_magnitude_V_per_V": abs(n),
        "P_over_N_magnitude_dB": _db(abs(p) / abs(n)) if abs(n) > 0 else None,
        "Hdd_magnitude_V_per_V": abs(dm),
        "Hdd_bypass_magnitude_V_per_V": abs(dm0),
        "Hdd_magnitude_change_vs_bypass_dB": _db(abs(dm) / abs(dm0)) if abs(dm0) > 0 else None,
        "Hdc_complex_V_per_V": _complex_pair(cm_to_dm),
        "Hdc_increment_normalized_complex": _complex_pair(normalized_cm),
        "Hdc_increment_normalized_magnitude": abs(normalized_cm) if normalized_cm is not None else None,
    }
    return {
        "format": "pam4_weighted_differential_delay_v1",
        "primary_band": "7_to_56_GHz",
        "bands": bands,
        "at_56_GHz": at_nyquist,
        "branch_floor_V_per_V": {"P": branch_floors[0], "N": branch_floors[1]},
        "weights": {"TX_power_spectrum": "sinc^2(f/112e9), rectangular-pulse approximation",
                    "channel": "|1+j*2*pi*f*RC|^-4, two independent buffered poles", "channel_RC_s": CHANNEL_RC_S,
                    "fixed_receiver": "|Hdd_track,bypass(f)|^2", "quadrature": "trapezoidal in linear frequency"},
        "scope": "Static AC diagnostic for code comparison. Correlate with independent frozen-FFE transient results.",
    }
