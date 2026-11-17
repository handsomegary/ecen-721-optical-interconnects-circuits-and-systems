"""Recompute the previous follower's 56 GHz stage losses from compact evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile

from comp_measure import at
import olympus_common as common
import summarize_acnext as modal


def evidence(archive):
    common.need(common.sha(archive) ==
                '396e2102c89464e65994d5e546a9c1f60afa4d1b7ba2e30157ffce7cb85bb2e9',
                'Original compact archive SHA differs')
    prefix = 'run/fine_tt_p25_v090_driver_short_p_0_full_p/'
    with tarfile.open(archive, 'r:gz') as tar:
        payload = tar.extractfile(prefix+'measurements.json').read()
        completion = json.load(tar.extractfile(prefix+'completion.json'))
    digest = hashlib.sha256(payload).hexdigest()
    common.need(digest == completion['measurement_sha256'], 'Measurement SHA differs')
    record = json.loads(payload)
    fs = record['frequency_Hz']
    stages = ['PNC_PREP', 'GMSAPVIN', 'GMSAPFG', 'GMSAPFO', 'GMSAPL', 'GMSAPI', 'GMSAPG']
    values = [at(fs, [complex(*z) for z in record['traces'][n]], 56e9) for n in stages]
    values = dict(zip(stages, values))
    rows = []
    for left, right in list(zip(stages, stages[1:])) + [(stages[0], stages[-1])]:
        z = values[right]/values[left]
        rows.append({'from': left, 'to': right, 'H_complex': [z.real, z.imag],
                     'gain_dB': modal.db(abs(z))})
    op = [record['saved_mos_oppoint'][f'GMSAPF{k}'] for k in range(8)]
    return {'case_id': record['case_id'], 'measurement_sha256': digest, 'Hz': 56e9,
            'stage_gains': rows, 'follower_gm_S': sum(d['gm'] for d in op),
            'follower_drain_current_A': sum(d['ids'] for d in op)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compact', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    common.write_new(args.output, evidence(args.compact))
