"""Machine-readable follow-up plan. Cases do not dispatch from this package."""
import json


def build():
    return {'format':'pam4_gmfine_future_transient_v1','status':'PENDING_AC_AND_USER_APPROVAL',
            'short_pilot':{'deltas_UI':[0,-.5,.5,-.25,.25],'cpus':1,'memory_GiB':6,
                           'wall_cap_hours':2,'scope':'Validate bias settling, common timing and blind code search.'},
            'quiet_nominal':{'first_UI':[0,-.25,.25,-.5,.5],
                             'additional_UI':[-.375,-.125,.125,.375]},
            'quiet_corners':{'corners':[['SS',85,.81],['FF',-40,.99]],'UI':[0,-.5,.5]},
            'paired_noise_cases':[{'seed':s,'injected_UI':d,
                                  'wave':'first_nine' if s<=1003 else 'remaining_51'}
                                 for s in range(1001,1021) for d in (0,-.5,.5)],
            'full_frame_resource':{'classic_cpus':1,'memory_GiB':8,'wall_cap_hours':6,
                                   'estimated_solver_hours':[1,4],'user_per_job_limit_hours':12},
            'reference_cases':['same new hardware zero skew (one frozen common phase)',
                               'r1 uncorrected matched seed (verify configuration and label mask)',
                               'zero-skew mathematical inverse reference'],
            'detector':'Genuine r5 frozen primary and secondary; ideal numerical 7 bit; 2048 held, 2032 scored.',
            'retirement':'Original raw stays on Olympus; new compact measurement, clip and SHA precede retirement.'}


if __name__=='__main__':
    print(json.dumps(build(),indent=2))
