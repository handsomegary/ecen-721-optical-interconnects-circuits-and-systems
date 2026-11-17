"""Apply exactly three PVT edits to the admitted zero-skew quiet r5 deck."""
import re

try:
    from .generate import CORNER_FILE, need, one_replace, sha
    from .model_preflight import stage_corner
except ImportError:
    from generate import CORNER_FILE, need, one_replace, sha
    from model_preflight import stage_corner

ENDPOINTS = {('ss',85,.81), ('ff',-40,.99)}


def apply_pvt(deck, case, model_root):
    process,temp,vdd = case['process'],case['temperature_C'],case['vdd_V']
    need((process,temp,vdd) in ENDPOINTS, 'Unknown quiet r3 PVT transient endpoint')
    need(case['kind']=='pam4_noiseless' and case['delta_ui']==0 and
         not re.search(rb'\bnoisefmax=',deck), 'Use admitted quiet, zero-skew original only')
    model_root = str(model_root)
    need(not any(c in model_root for c in ('"','\n','\r','\\')), 'Unsafe private Linux model root')
    tt_include = ('include "'+model_root+'/models/spectre/pdk_toplevel.scs" section=tt').encode('utf-8')
    pvt_include = ('include "'+CORNER_FILE+'" section=top_'+process).encode('ascii')
    result = one_replace(deck,rb'(?m)^'+re.escape(tt_include)+rb'(?=\r?$)',pvt_include,'admitted TT include')
    result = one_replace(result,rb'(?m)^simulatorOptions options temp=25(?= tnom=25 )',
                         ('simulatorOptions options temp='+str(temp)).encode('ascii'),'temperature')
    result = one_replace(result,rb'(?m)^XVs \(X_vdd 0\) vsource dc=0\.9(?=\r?$)',
                         ('XVs (X_vdd 0) vsource dc={:g}'.format(vdd)).encode('ascii'),'AFE supply')
    original,changed = deck.splitlines(keepends=True),result.splitlines(keepends=True)
    need(len(original)==len(changed),'Transient PVT changed row count')
    differences = [a for a,b in zip(original,changed) if a!=b]
    need(len(differences)==3 and all(a.startswith((b'include ',b'simulatorOptions ',b'XVs ')) for a in differences),
         'Transient PVT changed bytes outside the three approved rows')
    return result
