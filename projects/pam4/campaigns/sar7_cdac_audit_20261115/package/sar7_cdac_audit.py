"""Estimate held CDAC weights and the b0 readout timing from two retained PSFs."""

import argparse
from bisect import bisect_left,bisect_right
from functools import partial
import hashlib
import math
import os
from pathlib import Path
import statistics
import sys


ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT/'SHA256SUMS.txt'
ISOLATION = Path(os.environ.get('PAM4_SAR7_ISOLATE_PACKAGE',ROOT.parent/
    'PAM4_SAR7_SENSE_ISOLATION_20261115')).resolve()
if hashlib.sha256((ISOLATION/'SHA256SUMS.txt').read_bytes()).hexdigest()!= (
        'b03999e42015500ff178ffeec7303d47e1d73b79930c112f607d18428ccc7dc7'):
    raise ValueError('Unexpected isolation package')
sys.path.insert(0,str(ISOLATION))
import sar7_isolate as iso


base,common,scorer = iso.base,iso.common,iso.scorer


def coefficients(rows):
    """Fit constant, sampled input, and seven independently observed DAC bits."""
    size = 9
    design = [x for _,x,_ in rows]
    targets = [y for _,_,y in rows]
    common.need(len(rows)>size,'Too few independently observed DAC states')
    matrix = [[sum(x[i]*x[j] for x in design) for j in range(size)]+[
               sum(x[i]*y for x,y in zip(design,targets,strict=True))] for i in range(size)]
    for i in range(size):
        pivot = max(range(i,size),key=lambda j:abs(matrix[j][i]))
        common.need(abs(matrix[pivot][i])>1e-9,'Observed control words do not identify every weight')
        matrix[i],matrix[pivot] = matrix[pivot],matrix[i]
        scale = matrix[i][i]
        matrix[i] = [x/scale for x in matrix[i]]
        for row in matrix[i+1:]:
            factor = row[i]
            row[i:] = [a-factor*b for a,b in zip(row[i:],matrix[i][i:],strict=True)]
    result = [0.]*size
    for i in reversed(range(size)):
        result[i] = matrix[i][-1]-sum(matrix[i][j]*result[j] for j in range(i+1,size))
    return result


def gain_record(rows):
    coeffs = coefficients(rows)
    heldout = []
    for index in sorted({idx for idx,_,_ in rows}):
        subset = [row for row in rows if row[0]!=index]
        try:
            fitted = coefficients(subset)
        except ValueError:
            continue
        heldout.extend(y-sum(a*b for a,b in zip(fitted,x,strict=True)) for i,x,y in rows if i==index)
    weights = [-value for value in coeffs[2:]]
    return dict(usable_points=len(rows),heldout_points=len(heldout),
                offset_lsb=coeffs[0],sample_gain=coeffs[1]/64,weight_b6_to_b0_lsb=weights,
                full_code_span_lsb=sum(weights),ideal_full_code_span_lsb=127,
                heldout_rmse_lsb=math.sqrt(statistics.mean(x*x for x in heldout)) if heldout else None)


def collect_metrics(values,wave):
    times = values['time']
    fit = []
    rails = []
    lsb = wave['lsb_V']
    vdd = wave['vdd_V']

    def voltage(nodes,at):
        return [scorer.interpolate(times,values[n],at) for n in nodes]

    for row in wave['conversions']:
        index = row['index']
        pairs = row['code_pairs']
        a,b = voltage(wave['dac_pair'],row['sample_s'])
        input_lsb = (a-b)/lsb
        for trial in row['trials']:
            at = trial['pre_s']
            bits = [scorer.classify(*voltage(pair,at),vdd) for pair in pairs]
            if None not in bits:
                p,n = voltage(wave['dac_pair'],at)
                fit.append((index,[1.,input_lsb/64,*bits],(p-n)/lsb))
        last = row['trials'][-1]
        pair = pairs[-1]
        end = row['end_s']
        release = last['trial_release_s']
        # Compare only through 3.5 ps after the original end, before conv goes low.
        latest = end+3.5e-12
        cmp = scorer.classify(*voltage(last['cmp_pair'],last['read_s']),vdd)
        first = None
        schedule = [*times[bisect_left(times,release):bisect_right(times,latest)],latest]
        for instant in reversed(schedule):
            if cmp is None or scorer.classify(*voltage(pair,instant),vdd)!=cmp:
                break
            first = instant
        rails.append(dict(index=index,comparator_b0=cmp,output_end_V=voltage(pair,end),
                          output_latest_V=voltage(pair,latest),
                          valid_before_conv_off=first is not None,
                          rail_delay_after_trial_release_ps=None if first is None else 1e12*(first-release)))
    try:
        weights = dict(status='identified',**gain_record(fit))
    except ValueError as error:
        weights = dict(status='underdetermined',reason=str(error),usable_points=len(fit))
    return dict(weight_fit=weights,omitted_state_points=84-len(fit),b0_rail=rails)


def measure(root,case,job):
    directory = root/case['case_id']
    with base.lock_case(directory):
        wave,status,hashes = base.evidence(case,directory)
        common.need(status['slurm_job_id']==job,'Unexpected recorded comparator job')
        native, = [entry for entry in status['raw_inventory'] if entry['path'] in
                   ('raw/tranResponse.tran',iso.review.RAW_NAME)]
        live = common.raw_inventory(directory)
        common.need(common.matches_historical_inventory(status['raw_inventory'],live),'Changed native trace inventory')
        source = iso.review.safe_raw(directory,dict(status,raw_inventory=live),native['path'].removeprefix('raw/'),
                     parser=partial(iso.review.parse_selected,required=scorer.required_traces(wave)))
        common.need(source.unit('time')=='s','Expected native seconds')
        result = collect_metrics(source.values,wave)
        common.need(base.evidence(case,directory)[2]==hashes,'Evidence changed during read-only analysis')
        return dict(job_id=job,tran_sha256=source.sha256,**result)


def verify():
    original,isolated,_ = iso.verify()
    for line in MANIFEST.read_text(encoding='ascii').splitlines():
        digest,name = line.split('  ',1)
        file = ROOT/name
        common.need(file.resolve().is_relative_to(ROOT) and common.sha(file)==digest,'Package differs: '+name)
    return original,isolated


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('verify','audit'))
    parser.add_argument('--relaxed-root',type=Path)
    parser.add_argument('--isolation-root',type=Path)
    parser.add_argument('--output-root',type=Path)
    args = parser.parse_args()
    primary,isolated = verify()
    if args.mode=='verify':
        print('Verified original runs and held CDAC analysis package')
        return
    common.need(all(path is not None for path in (args.relaxed_root,args.isolation_root,args.output_root)),
                'Supply both original run roots and the new output root')
    relaxed = iso.relaxed
    iso.bind(relaxed.build,relaxed.PLAN,relaxed.MANIFEST,relaxed.SCHEMA)
    direct = measure(args.relaxed_root.resolve(strict=True),primary,'760091')
    iso.bind(iso.build,iso.PLAN,iso.MANIFEST,iso.SCHEMA)
    buffered = measure(args.isolation_root.resolve(strict=True),isolated,'760132')
    output = common.checked_root(args.output_root)/'sar7_cdac_weight_audit.json'
    iso.save(output,dict(status='measured',direct=direct,isolated=buffered))
    print(output)


if __name__=='__main__':
    main()
