"""Read retained compact r3 results and the two original-detector corner transients."""
import argparse
from pathlib import Path
import sys
import olympus_common as common

PACKAGE = Path(__file__).resolve().parent
sys.path.insert(0,str(PACKAGE/'native'))
import readback_guard
from run_case import verify_compact
from skew.summarize_skew import measured_points, effect


def aggregate(root, admission):
    root = root.resolve()
    matrix = common.read(PACKAGE/'pvt/cases/pvt_ac_matrix.json')
    transient = common.read(PACKAGE/'pvt/transient_plan.json')
    skew = common.read(PACKAGE/'skew/skew_plan.json')
    nominal = next(case for case in skew['cases'] if case['case_id']==transient['nominal_reference_case_id'])
    ac_rows, time_rows, pending = {}, {}, {}
    for case in matrix['cases']:
        key = case['case_id']
        directory = root/key
        if not (directory/'completion.json').is_file():
            pending[key] = 'Missing compact completion'
            continue
        try:
            report = common.read(directory/'measurements.json')
            verify_compact(directory,report)
            completion = common.read(directory/'completion.json')
            common.need(completion['measurement_complete'] is True and completion['measurement_sha256']==
                        common.sha(directory/'measurements.json') and report['case_id']==key and
                        all(report[k]==case[k] for k in ('process','temperature_C','vdd_V')), 'PVT case/retention mismatch')
            ac_rows[key] = report
        except (OSError, ValueError, KeyError, TypeError) as error:
            pending[key] = str(error)
    for case in [nominal]+transient['cases']:
        key = case['case_id']
        directory = root/key
        try:
            plan = PACKAGE/('pvt/transient_plan.json' if case.get('pvt_corner') else 'skew/skew_plan.json')
            report = readback_guard.verify_run(directory,expected_case=case,
                         expected_plan_sha256=common.sha(plan),admission_path=admission)
            status = common.read(directory/'run_status.json')
            common.need(status.get('solver_mode')=='classic' and status.get('cpus_allocated')==1, 'Different solver or allocation')
            time_rows[key] = {'points':measured_points(directory,report),'case':case}
        except (OSError, ValueError, KeyError, TypeError) as error:
            pending[key] = str(error)
    if nominal['case_id'] in time_rows:
        reference = time_rows[nominal['case_id']]['points']
        for row in time_rows.values():
            row['difference_vs_nominal'] = {name:effect(point,reference[name]) for name,point in row['points'].items()}
    return {'status':'INCOMPLETE' if pending else 'PVT_CHARACTERIZATION_COMPLETE',
            'AC_DC_and_track_noise':ac_rows,'fixed_FFE_endpoint_transient':time_rows,'unavailable':pending,
            'transient_noise_PVT_measured':False,'course_pass':None}


if __name__=='__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-root',type=Path,required=True)
    p.add_argument('--admission',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a = p.parse_args()
    common.write_new(a.output,aggregate(a.run_root,a.admission))
