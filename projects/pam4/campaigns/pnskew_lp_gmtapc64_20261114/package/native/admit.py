#!/usr/bin/env python3
"""Hash-only admission of the original r5 inputs. Never runs a simulator.

Run this ON the machine holding the private inputs. No model/card/license
contents are included in the output. Public sanitized source snapshots and R7
detectors are deliberately insufficient for admission.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

FORMAT = 'pn_skew_native_r5_admission_v1'
ORIGINAL_MODEL_ROOT = '<PDK_ROOT>'
FROZEN_SHA256 = '4cda4c9ec967f2af4bf4f89eacdd1beae372668877c358cf6aa26092597482eb'
DECK_SHA256 = {
    'noiseless': 'c9f576a9dbfb1afd6f8fdcb39a52039329231c3696bed01368c335c49b35e6d3',
    'noise': '3109f222211963fe5fcadbbb96b6605f8c4c7a8d32aa35bae178678f1d927fa2',
}
SCRIPT_NAMES = (
    'adc_backend_pam4_r5.py', 'adc_isolation_r5.py',
    'adc_frontend_load_r5.py', 'adc_comparator_r5.py',
    'native_geometry_r5.py', 'pam4_integration.py', 'optimize_pam4.py',
    'pam4_ffe_diagnostic.py', 'pam4_metrics.py',
)
# Metadata only, from historical r7 dependency_spec.json private_model_nodes.
# These are the original VM shrink files, NOT the site-default model variant.
MODEL_FILES = {
    'models/spectre/pdk_model.scs': {
        'bytes': 6391681, 'sha256': '002300afbc872cca7c0bab744740eb74ff2cc71e770832c6e6d97c447dbfff78'},
    'models/spectre/pdk_model_shrink_embedded.scs': {
        'bytes': 41713, 'sha256': '61e73b63b3ff0cd966504939f7249e851872c57a11599b8525106e69fc3c5dea'},
    'models/spectre/res_metal.scs': {
        'bytes': 24939, 'sha256': '26edcca98492e43948994b72a4ec81f6afcca4b0481e70bf0e86b0c07423a414'},
    'models/spectre/pdk_toplevel.scs': {
        'bytes': 1579, 'sha256': 'bd8088e1ea620dcda229d1fd16d5d63a08b594a28e78d24c4db2906cf45a71d1'},
}
AUXILIARY_NAMES = ('psf_ascii.py', 'adc_comparator_probe.py')
AUXILIARY_SHA256 = {
    'psf_ascii.py': '8875a6b7c89ade6b419a196aa0d772b3798fa17af3cf4090a1807bce768db0e1',
    'adc_comparator_probe.py': 'd66e31333aa75f2ec7c625c67aa143eff33e620aab8095fb15a302ca5e2b250c',
}
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_DECK_BYTES = 16 * 1024 * 1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def regular_file(path):
    path = Path(path).expanduser().absolute()
    require(path.is_file(), 'Required file missing: ' + str(path))
    require(not path.is_symlink(), 'Input must be a regular non-symlink file: ' + str(path))
    return path.resolve()


def read_json(path):
    path = regular_file(path)
    require(path.stat().st_size <= MAX_JSON_BYTES, 'JSON exceeds bound')
    def reject_constant(value):
        raise ValueError('Nonfinite JSON constant: ' + value)
    return json.loads(path.read_text(encoding='utf-8'), parse_constant=reject_constant)


def is_sha(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def inside(path, root):
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except ValueError:
        return False


def validate_frozen(frozen):
    """Validate the original protocol, never select/refit coefficients."""
    p = frozen['protocol']
    wanted = {'variant': 'cml2_late1', 'training_data_seed': 2026101301,
              'validation_data_seed': 2026101302, 'training_noise_seed': 157,
              'training_input_symbols': 1024, 'validation_input_symbols': 2048,
              'phase_UI': .25, 'loss_dB_at_56GHz': 20., 'complete_ADC_verified': False}
    for name, value in wanted.items():
        require(p.get(name) == value, 'Original r5 protocol mismatch: ' + name)
    require(p['validation_conditions'] == [
        {'kind': 'noiseless', 'noise_seed': None}, {'kind': 'noise', 'noise_seed': 173}],
        'Original noiseless/noise173 conditions required')
    require(frozen.get('complete_ADC_verified') is False, 'r5 is not a complete ADC')
    scripts = frozen['identity']['scripts']
    require(set(scripts) == set(SCRIPT_NAMES), 'All nine original identity scripts required')
    require(all(is_sha(value) for value in scripts.values()), 'Invalid script SHA256')
    for point, lag, fullscale in [('primary', 1, .1), ('secondary', 3, .075)]:
        selection = frozen['selections'][point]
        require(selection['integer_symbol_lag'] == lag, 'Frozen lag mismatch: ' + point)
        require(selection['ADC_fullscale_differential_Vpp'] == fullscale, 'Frozen fullscale mismatch: ' + point)
        detector = selection['frozen_detectors']
        require(detector['ADC_fullscale_differential_Vpp'] == fullscale, 'Detector fullscale mismatch')
        for name in ('raw_FFE', 'ADC_FFE'):
            fit = detector[name]
            require(fit['tap_count'] == 17 and fit['tap_offsets_UI'] == list(range(-8, 9)), 'Original 17 taps required')
            require(fit['decision_latency_UI'] == 8 and fit['ridge_lambda'] == .001, 'Original FFE protocol required')
            weights = fit['weights_on_normalized_input']
            require(len(weights) == 17 and all(math.isfinite(x) for x in weights), 'Invalid frozen coefficients')
            require(math.isfinite(fit['normalization_training_mean_V']) and
                    math.isfinite(fit['normalization_training_centered_RMS_V']) and
                    fit['normalization_training_centered_RMS_V'] > 0 and
                    math.isfinite(fit['bias_in_target_symbol_units']), 'Invalid frozen normalization')
    clock = frozen['training_run']['clock_specification']
    require(len(clock['primary_clocks']) == 8 and len(clock['secondary_clocks']) == 64,
            'Eight primary clocks and all 64 secondary branches required')
    require(frozen['training_run']['noise_seed'] == 157, 'Original noisy training required')
    return p


def deck_proof(path, kind, model_root):
    path = regular_file(path)
    require(path.stat().st_size <= MAX_DECK_BYTES, 'Input deck exceeds bound')
    data = path.read_bytes()
    actual = hashlib.sha256(data).hexdigest()
    original = DECK_SHA256[kind]
    root_bytes = str(model_root).replace('\\', '/').rstrip('/').encode('utf-8')
    old_bytes = ORIGINAL_MODEL_ROOT.encode('utf-8')
    substitutions = 0
    restored = data
    if actual != original:
        require(root_bytes != old_bytes and root_bytes in data, 'Deck is not original or solely root-rebased')
        require(old_bytes not in data and old_bytes not in root_bytes and root_bytes not in old_bytes,
                'Ambiguous mixed or overlapping model roots')
        substitutions = data.count(root_bytes)
        restored = data.replace(root_bytes, old_bytes)
        require(restored.replace(old_bytes, root_bytes) == data, 'Model-root substitution is not reversible')
    require(hashlib.sha256(restored).hexdigest() == original,
            'Original r5 deck SHA mismatch; no arbitrary normalization is accepted')
    return {'path': str(path), 'sha256': actual, 'bytes': len(data),
            'original_vm_sha256': original, 'model_root_inverse_substitutions': substitutions}


def build_admission(noiseless_deck, noise_deck, frozen_r5, source_dir, model_root):
    source_dir, model_root = Path(source_dir).resolve(), Path(model_root).resolve()
    require(source_dir.is_dir() and model_root.is_dir(), 'Source/model roots must already exist')
    frozen_path = regular_file(frozen_r5)
    require(sha256_file(frozen_path) == FROZEN_SHA256,
            'Original r5 frozen SHA required; R7 frozen detectors cannot substitute')
    frozen = read_json(frozen_path)
    validate_frozen(frozen)
    scripts = {}
    for name, expected in frozen['identity']['scripts'].items():
        source = regular_file(source_dir / name)
        require(source.parent == source_dir, 'Script escaped source directory')
        actual = sha256_file(source)
        require(actual == expected, 'Original identity script mismatch: ' + name)
        scripts[name] = actual
    auxiliary = {}
    for name in AUXILIARY_NAMES:
        source = regular_file(source_dir / name)
        require(source.parent == source_dir, 'Auxiliary script escaped source directory')
        auxiliary[name] = sha256_file(source)
        require(auxiliary[name] == AUXILIARY_SHA256[name], 'Original parser/helper mismatch: ' + name)
    models = {}
    for relative, expected in MODEL_FILES.items():
        path = regular_file(model_root / relative)
        require(inside(path, model_root), 'Model file escaped model root')
        actual = {'bytes': path.stat().st_size, 'sha256': sha256_file(path)}
        require(actual == expected, 'Private model metadata mismatch: ' + relative)
        models[relative] = actual
    decks = {kind: deck_proof(path, kind, model_root) for kind, path in
             [('noiseless', noiseless_deck), ('noise', noise_deck)]}
    return {'format': FORMAT, 'admission_complete': True, 'source_decks': decks,
            'frozen_r5': {'path': str(frozen_path), 'sha256': FROZEN_SHA256},
            'source_dir': str(source_dir), 'source_scripts': scripts, 'auxiliary_scripts': auxiliary,
            'model_root': str(model_root), 'original_model_root': ORIGINAL_MODEL_ROOT,
            'model_files': models, 'protocol_lineage': {
                'study': 'r5_late1', 'variant': 'cml2_late1',
                'training_data_seed': 2026101301, 'validation_data_seed': 2026101302,
                'training_noise_seed': 157, 'validation_noise_seed': 173,
                'training_symbols': 1024, 'validation_symbols': 2048, 'FFE_windows': 2032,
                'primary_lag': 1, 'secondary_lag': 3,
                'primary_fullscale_differential_Vpp': .1, 'secondary_fullscale_differential_Vpp': .075,
                'clock_and_labels_unchanged': True, 'mean_input_delay_s': 0.,
                'complete_ADC_verified': False},
            'tool_scripts': {'admit.py': sha256_file(__file__)}}


def recheck_admission(document):
    require(document.get('format') == FORMAT and document.get('admission_complete') is True,
            'Complete original r5 admission required')
    fresh = build_admission(document['source_decks']['noiseless']['path'],
                            document['source_decks']['noise']['path'],
                            document['frozen_r5']['path'], document['source_dir'], document['model_root'])
    # Tool-file checksum is recorded, but moving this same bundle is supported.
    for name in ('source_decks', 'frozen_r5', 'source_dir', 'source_scripts', 'auxiliary_scripts',
                 'model_root', 'original_model_root', 'model_files', 'protocol_lineage'):
        require(document[name] == fresh[name], 'Admission changed or stale: ' + name)
    require(document['tool_scripts']['admit.py'] == sha256_file(__file__), 'Admission tool changed')
    return read_json(document['frozen_r5']['path'])


def read_admission(path, verify=True):
    document = read_json(path)
    require(document.get('format') == FORMAT and document.get('admission_complete') is True,
            'Complete original r5 admission required')
    if verify:
        recheck_admission(document)
    return document


def write_new_json(path, value):
    path = Path(path)
    require(path.parent.is_dir(), 'Output parent must already exist')
    encoded = json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n'
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(encoded)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('noiseless-deck', 'noise-deck', 'frozen-r5', 'source-dir', 'model-root', 'out'):
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args()
    try:
        result = build_admission(args.noiseless_deck, args.noise_deck, args.frozen_r5,
                                 args.source_dir, args.model_root)
        write_new_json(args.out, result)
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(2, 'Admission refused: ' + str(error) + '\n')
    print('Original r5 admission written: ' + str(args.out))


if __name__ == '__main__':
    main()
