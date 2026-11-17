"""Read existing training-only diagnostic metadata and current VM capacity."""
import json,subprocess
import control_ffe_phase_resume2_20261022 as c
code=c.PRELUDE+r'''
frozen=json.loads(original.FROZEN_PATH.read_text())
d=P/'runs/adc_backend_pam4_r5_20261013/r5_late1/training_diagnostic_v1.json'
value=json.loads(d.read_text()) if d.exists() else {}
fits={}
for point,selection in frozen['selections'].items():
 f=selection['frozen_detectors']['ADC_FFE'];norm=f['normalization_training_centered_RMS_V']
 fits[point]=dict(fixed_lag=selection['integer_symbol_lag'],range_Vpp=selection['frozen_detectors']['ADC_fullscale_differential_Vpp'],training_centered_RMS_V=norm,FFE_l2_normalized=(sum(x*x for x in f['weights_on_normalized_input']))**.5,FFE_l2_target_units_per_V=(sum(x*x for x in f['equivalent_weights_per_input_V']))**.5,white_input_noise_gain_caveat='L2 tapnorm is only a white uncorrelated sample-noise reference, not integrated actual correlated device noise.')
stats=value.get('statistics',{})
print(json.dumps(dict(observed_utc=now(),boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),actual_simulators=actual(),frozen_sha256=sha(original.FROZEN_PATH),training_diagnostic_sha256=sha(d) if d.exists() else None,training_only_stats={k:stats[k] for k in ('global_aperture_transfer','physical_summary','buffer0_and7_summary') if k in stats},fixed_detector_diagnostics=fits,free_bytes=os.statvfs(str(P)).f_bavail*os.statvfs(str(P)).f_frsize)))
'''
cmd=['C:/Windows/System32/OpenSSH/ssh.exe','-i',str(c.LOCAL/'work/ssh/vm_pdk_access_ed25519'),'-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes','-o','HostKeyAlias=192.0.2.1','user@192.0.2.1','python3 -']
r=subprocess.run(cmd,input=code,text=True,encoding='utf-8',capture_output=True,timeout=40)
if r.returncode:raise RuntimeError(r.stderr or r.stdout)
v=json.loads(r.stdout)
(c.LOCAL/'work/secondary_r7_readonly_training_review_20261022.json').write_text(json.dumps(v,indent=2)+'\n',encoding='utf-8')
print(json.dumps(v,indent=2))
