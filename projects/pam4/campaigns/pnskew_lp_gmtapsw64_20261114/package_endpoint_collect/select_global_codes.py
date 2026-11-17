"""Select one monotone hardware code map from native SS/TT/FF AC evidence."""
import argparse
import json
import math
from pathlib import Path

from global_codes import ZERO_CODE, codes, decode, seam_aliases


CORNERS = ('ss','tt','ff')
HALF_UI_PS = .5e12/112e9
MAX_STEP_PS = .50
_HARDWARE = {row['hardware_word']:row for row in (*codes(),*seam_aliases())}


def _complete_metric(row):
    return (isinstance(row,dict) and type(row.get('delay_ps')) in (int,float)
            and math.isfinite(row['delay_ps']) and type(row.get('gain_power_pass')) is bool)


def _canonical(row):
    return row['hardware_word']==decode(row['logical_code'])['hardware_word']


def _key(path):
    return (-len(path),-sum(map(_canonical,path)),tuple(row['hardware_word'] for row in path))


def _delays(row):
    return [row['metrics_per_corner'][corner]['delay_ps'] for corner in CORNERS]


def _follows(previous, current):
    return previous['logical_code'] < current['logical_code'] and all(
        0 < b-a <= MAX_STEP_PS+1e-12 for a,b in zip(_delays(previous),_delays(current)))


def _paths(rows, neutral, move):
    """Build longest prefix/suffix paths with goal-reaching outer anchors."""
    center = _delays(neutral)
    paths = []
    for row in rows:
        qualifies = all(move*(delay-zero)>=HALF_UI_PS for delay,zero in zip(_delays(row),center))
        options = [(row,)] if qualifies else []
        for prior,path in paths:
            if move==-1 and _follows(prior,row):
                options.append((*path,row))
            if move==1 and _follows(row,prior):
                options.append((row,*path))
        if options:
            paths.append((row,min(options,key=_key)))
    return [path for row,path in paths if (_follows(row,neutral) if move==-1 else _follows(neutral,row))]


def select(candidates):
    """Return a common AC-verified map or the reason it cannot be published.

    Each input row has logical_code, hardware_word and metrics_per_corner.
    Per-corner metrics required here are delay_ps relative to a common fixed
    reference and gain_power_pass (Boolean). Supply one measurement per
    hardware word for a single hardware design, including the nine aliases.
    Phase, dispersion, and gain diagnostics can accompany each metric.
    """
    measured = {}
    for row in candidates:
        word = row['hardware_word']
        if type(word) is not int or word not in _HARDWARE or word in measured:
            raise ValueError('Unknown or duplicated physical word: '+str(word))
        state = _HARDWARE[word]
        if row['logical_code']!=state['logical_code']:
            raise ValueError('Hardware word does not match its nominal index: '+str(word))
        measured[word] = dict(state,metrics_per_corner=row['metrics_per_corner'])

    missing = [{'hardware_word':word,'corner':corner} for word in sorted(_HARDWARE)
               for corner in CORNERS if not _complete_metric(
                   measured.get(word,{}).get('metrics_per_corner',{}).get(corner))]
    result = {'format':'pam4_lp14_common_code_map_v1','max_step_limit_ps':MAX_STEP_PS,
              'required_span_each_sign_ps':HALF_UI_PS,'missing_metrics':missing,
              'selected':[],'zero_code':None,'endpoints_by_corner':None,'global_code_map_verified':False}
    if missing:
        return dict(result,status='blocked_incomplete')

    valid = sorted((row for row in measured.values() if all(
        row['metrics_per_corner'][c]['gain_power_pass'] for c in CORNERS)),
        key=lambda row:(row['logical_code'],row['hardware_word']))
    result['rejected_gain_power_words'] = sorted(set(measured)-{row['hardware_word'] for row in valid})
    left = [row for row in valid if row['logical_code']<ZERO_CODE]
    right = [row for row in reversed(valid) if row['logical_code']>ZERO_CODE]
    solutions = []
    for neutral in (row for row in valid if row['logical_code']==ZERO_CODE):
        prefixes = _paths(left,neutral,-1)
        suffixes = _paths(right,neutral,1)
        if prefixes and suffixes:
            solutions.append((*min(prefixes,key=_key),neutral,*min(suffixes,key=_key)))
    if not solutions:
        return dict(result,status='blocked_no_common_monotone_path')

    winner = min(solutions,key=_key)
    zero = next(row for row in winner if row['logical_code']==ZERO_CODE)
    neutral_delays = dict(zip(CORNERS,_delays(zero)))
    selected = []
    for addr,row in enumerate(winner):
        metrics = {corner:dict(data,delay_vs_selected_zero_ps=data['delay_ps']-neutral_delays[corner])
                   for corner,data in row['metrics_per_corner'].items() if corner in CORNERS}
        selected.append(dict(row,table_address=addr,metrics_per_corner=metrics))
    endpoints = {}
    for corner in CORNERS:
        fit = [row['metrics_per_corner'][corner]['delay_vs_selected_zero_ps'] for row in selected]
        endpoints[corner] = {'min_delay_ps':fit[0],'max_delay_ps':fit[-1],
                             'largest_adjacent_step_ps':max(b-a for a,b in zip(fit,fit[1:]))}
        for name,target in (('negative',-HALF_UI_PS),('positive',HALF_UI_PS)):
            nearest = min(range(len(selected)),key=lambda addr:(abs(fit[addr]-target),addr))
            endpoints[corner][f'nearest_{name}_target'] = {
                'target_correction_ps':target,'delay_ps':fit[nearest],
                'residual_ps':fit[nearest]-target,'table_address':nearest,
                'hardware_word':selected[nearest]['hardware_word'],
            }

    return dict(result,status='verified_map',global_code_map_verified=True,
                selected=selected,zero_code={'hardware_word':zero['hardware_word'],
                                             'logical_code':ZERO_CODE,'reference_delay_ps':neutral_delays,
                                             'table_address':next(r['table_address'] for r in selected
                                                                  if r['logical_code']==ZERO_CODE)},
                endpoints_by_corner=endpoints)


if __name__=='__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--input',type=Path,required=True,help='JSON array of hardware-state metrics')
    cli.add_argument('--output',type=Path,required=True)
    args = cli.parse_args()
    candidates = json.loads(args.input.read_text(encoding='utf-8'))
    report = select(candidates)
    with args.output.open('x',encoding='utf-8') as out:
        json.dump(report,out,indent=2,allow_nan=False)
        out.write('\n')
