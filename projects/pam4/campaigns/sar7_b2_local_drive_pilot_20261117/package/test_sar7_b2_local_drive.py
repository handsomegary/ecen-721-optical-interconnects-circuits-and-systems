"""One bounded b2-only drive change, fixed timing budget, and original scoring gates."""

from collections import Counter
from datetime import timedelta
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import re
import unittest
from unittest.mock import patch

import sar7_b2_local_drive as pilot


def blocks(lines):
    result={};name=None
    for line in lines:
        if line.startswith('subckt '):name=line.split()[1];result[name]=[]
        if name is not None:result[name].append(line)
        if line.startswith('ends '):name=None
    return result


class B2LocalDriveTests(unittest.TestCase):
    @staticmethod
    def top_rows(source):
        result={};inside=False
        for line in source.decode('ascii').splitlines():
            if line.startswith('subckt '):inside=True
            elif line.startswith('ends '):inside=False
            elif not inside and line.startswith('X'):result[line.split()[0]]=line
        return result

    def test_only_ten_b2_instances_and_thirteen_pulses_change(self):
        old,_=pilot.parent.build(pilot.parent.case_record());new,meta=pilot.build(pilot.case_record())
        a,b=self.top_rows(old),self.top_rows(new)
        expected={f'XNDO{s}2' for s in 'pn'}|{f'XNDZ{s}2' for s in 'pn'}
        expected|={f'XNDI{k}{s}2' for k in 'OZ' for s in 'pn'}|{f'XQOUT2{s}' for s in 'pn'}
        self.assertEqual(set(pilot.TARGETS),expected)
        self.assertEqual(set(a),set(b))
        self.assertEqual({name for name in a if a[name]!=b[name]},expected)
        for name in expected:
            oldcell,newcell,ports,kind=pilot.TARGETS[name]
            self.assertEqual(a[name].rsplit(' ',1)[1],oldcell)
            self.assertEqual(b[name].rsplit(' ',1)[1],newcell)
            self.assertEqual(a[name].rsplit(' ',1)[0],b[name].rsplit(' ',1)[0])
            self.assertEqual(tuple(a[name].split('(',1)[1].split(')',1)[0].split()),tuple(ports))
        self.assertEqual(sum(name.startswith('XQIN') and row.endswith(' SAR_INV') for name,row in b.items()),14)
        self.assertTrue(all(a[name]==b[name] for name in a if name.startswith('XQIN')))
        oldlines=old.decode('ascii').splitlines();newlines=new.decode('ascii').splitlines()
        self.assertEqual([x for x in oldlines if x.startswith('save ')],[x for x in newlines if x.startswith('save ')])
        before,after=blocks(oldlines),blocks(newlines)
        for name in before:self.assertTrue(before[name]==after[name],'Original cell changed: '+name)
        oldp={x.split()[0]:x for x in oldlines if x.startswith('V_')}
        newp={x.split()[0]:x for x in newlines if x.startswith('V_')}
        changed={name for name in oldp if oldp[name]!=newp[name]}
        self.assertEqual(changed,{f'V_trial{bit}' for bit in range(7)}|{f'V_clk{bit}' for bit in range(6)})
        # Remove only new cell definitions and restore the ten cell selectors and thirteen pulse rows.
        restored=[];inside_new=False
        for line in newlines:
            if line.startswith('subckt '):inside_new=line.split()[1] not in before
            if inside_new:
                if line.startswith('ends '):inside_new=False
                continue
            label=line.split()[0] if line.split() else ''
            if label in expected:line=a[label]
            elif label in changed:line=oldp[label]
            restored.append(line)
        self.assertTrue(restored==oldlines,'An unapproved card, instance, port, source or save changed')

    def test_complete_cdf_replication_and_both_polarities(self):
        old,_=pilot.parent.build(pilot.parent.case_record())
        patched,counts=pilot.physical_patch(old)
        self.assertEqual(counts,{'oai':2,'nor':2,'decoder_inv':4,'qbuffer_second':2})
        a,b=blocks(old.decode('ascii').splitlines()),blocks(patched.decode('ascii').splitlines())
        pairs={'SAR_OAI21_X2':'SAR_B2_OAI21_X4','SAR_NOR3_P3':'SAR_B2_NOR3_P6','SAR_NDINV2':'SAR_B2_INV4'}
        self.assertEqual(set(b)-set(a),set(pairs.values()))
        for original,scaled in pairs.items():
            oldcards=Counter(line.split(' ',1)[1] for line in a[original][1:-1])
            newcards=Counter(line.split(' ',1)[1] for line in b[scaled][1:-1])
            self.assertTrue(newcards==Counter({card:2*n for card,n in oldcards.items()}),'Replica card body/ports changed')
            labels=[line.split()[0] for line in b[scaled][1:-1]]
            self.assertEqual(len(labels),len(set(labels)))
        for name in a:self.assertTrue(a[name]==b[name],'Original cell definition changed')
        # This independent comparison includes every reference TG, raw-q first inverter and other-bit device.
        before,after=self.top_rows(old),self.top_rows(patched)
        for name in before:
            if name not in pilot.TARGETS:self.assertEqual(before[name],after[name],name)

    def test_missing_duplicate_wrong_cell_and_wrong_port_are_rejected(self):
        source,_=pilot.parent.build(pilot.parent.case_record());lines=source.decode('ascii').splitlines()
        row=next(x for x in lines if x.startswith('XNDOp2 '))
        def payload(rows):return ('\n'.join(rows)+'\n').encode('ascii')
        no_target=lines.copy();no_target.remove(row)
        duplicate=lines+[row]
        wrong_cell=[x.rsplit(' ',1)[0]+' SAR_INV' if x==row else x for x in lines]
        wrong_port=[x.replace(' qdecode2p ',' qdecode1p ',1) if x==row else x for x in lines]
        self.assertNotEqual(wrong_port,lines,'Fixture must mutate a real selected q port')
        for name,rows in [('missing',no_target),('duplicate',duplicate),('wrong_cell',wrong_cell),('wrong_port',wrong_port)]:
            with self.subTest(mutation=name),self.assertRaises(Exception):pilot.physical_patch(payload(rows))
        # A same-shape other-bit source change must fail the parent pin before a case can be built.
        other=next(x for x in lines if x.startswith('XNDOp1 '))
        tampered=payload([x.rsplit(' ',1)[0]+' SAR_INV' if x==other else x for x in lines])
        original_meta=pilot.parent.build(pilot.parent.case_record())[1]
        with patch.object(pilot.parent,'build',return_value=(tampered,original_meta)),self.assertRaises(Exception):
            pilot.build(pilot.case_record())

    def test_finite_trial_edges_and_exact_budget(self):
        source,meta=pilot.build(pilot.case_record());schedule=pilot.timing_schedule()
        expected={6:(78,108,145,147),5:(145.5,190.5,234.5,236.5),4:(235,260,300,302),
            3:(300.5,326.5,366.5,368.5),2:(367,398,445,447),1:(445.5,453.5,497.5,499.5),0:(498,504,552,554)}
        self.assertEqual(pilot.WAITS,(30,45,25,26,31,8,6))
        self.assertEqual(pilot.EVALS,(37,44,40,40,47,44,48))
        self.assertEqual(schedule,expected)
        self.assertEqual(sum(pilot.WAITS)+sum(pilot.EVALS)+6*pilot.GUARD_PS,474)
        lines=source.decode('ascii').splitlines()
        for bit in range(6):
            row=next(line for line in lines if line.startswith(f'V_trial{bit} '))
            fields=dict(re.findall(r'\b(delay|rise|fall|width|period)=([^ ]+)',row))
            self.assertAlmostEqual(float(fields['delay'])/pilot.native.PS,schedule[bit+1][2])
            self.assertEqual(float(fields['rise']),pilot.native.EDGE)
            self.assertAlmostEqual(schedule[bit+1][3]-schedule[bit][0],1.5)
        self.assertEqual(meta['primary_readout_ps'],565)
        self.assertEqual(meta['wave']['conversions'][0]['trials'][-1]['read_s'],pilot.native.timing(552))
        self.assertEqual(meta['wave']['conversions'][0]['trials'][-1]['trial_release_s'],pilot.native.timing(554))

    def test_roundtrip_parent_pins_and_only_trial_wave_metadata_changes(self):
        case=pilot.case_record();first,meta=pilot.build(case)
        second,again=pilot.build(json.loads(json.dumps(case)))
        self.assertEqual(first,second);self.assertEqual(meta,again)
        old,prior=pilot.parent.build(pilot.parent.case_record())
        self.assertEqual(hashlib.sha256(old).hexdigest(),pilot.PARENT_DECK_SHA)
        restored=json.loads(json.dumps(meta['wave']))
        for cv,oldcv in zip(restored['conversions'],prior['wave']['conversions'],strict=True):cv['trials']=oldcv['trials']
        self.assertEqual(restored,json.loads(json.dumps(prior['wave'])))
        self.assertEqual(meta['authorization']['max_solver_cases_this_packet'],1)
        self.assertEqual(meta['authorization']['cpus_this_job'],1)
        self.assertEqual(meta['authorization']['max_concurrent_sar7_cpus'],2)
        self.assertEqual(meta['parent_job'],'761674')
        self.assertEqual(meta['changed_pulse_rows'],13)
        self.assertEqual(meta['circuit_change']['instance_counts'],{'oai':2,'nor':2,'decoder_inv':4,'qbuffer_second':2})
        self.assertTrue(meta['circuit_change']['tg_unchanged'])
        self.assertTrue(meta['circuit_change']['all14_first_qbuffer_inv1_unchanged'])

    def test_renewed_deadline_allows_now_after_old_expiry(self):
        now=pilot.STARTS+timedelta(minutes=5)
        pilot.check_stage_deadline(now)
        with patch.object(pilot,'query_preexpiry_slurm_submission') as query,patch.object(pilot.parent,'check_run_submission',side_effect=AssertionError('Old deadline called')):
            self.assertIsNone(pilot.check_run_submission(now));query.assert_not_called()
        for bad in (pilot.STARTS-timedelta(seconds=1),pilot.EXPIRES):
            with self.assertRaises(Exception):pilot.check_stage_deadline(bad)

    def test_queued_submit_time_exact_job_and_new_cutoff(self):
        now=pilot.EXPIRES+timedelta(minutes=5);job='761600'
        def receipt(at):return f'JobId={job} SubmitTime={int(at.timestamp())} Other=value'
        record=pilot.validate_submission(receipt(pilot.EXPIRES-timedelta(seconds=1)),job,now)
        self.assertEqual(record['slurm_job_id'],job)
        for at in (pilot.STARTS-timedelta(seconds=1),pilot.EXPIRES,pilot.EXPIRES+timedelta(seconds=1)):
            with self.assertRaises(Exception):pilot.validate_submission(receipt(at),job,now)
        for text in ('JobId=1 SubmitTime=1794890000',f'JobId={job} SubmitTime=Unknown',f'JobId={job} JobId={job} SubmitTime=0'):
            with self.assertRaises(Exception):pilot.validate_submission(text,job,now)

    def test_postexpiry_queries_once_and_only_reads_existing_stage(self):
        root=Path('newroot').absolute();case={'case_id':pilot.CASE_ID};now=pilot.EXPIRES+timedelta(seconds=1)
        with patch.object(pilot,'query_preexpiry_slurm_submission',return_value={'ok':True}) as query,patch.object(pilot,'existing_stage',return_value=root/pilot.CASE_ID) as existing,patch.object(pilot.base,'stage') as stage:
            self.assertEqual(pilot.stage_for_run(root,case,Path('private'),now),root/pilot.CASE_ID)
            query.assert_called_once_with(now);existing.assert_called_once();stage.assert_not_called()
        with patch.dict(pilot.os.environ,{'SLURM_JOB_ID':''}),patch.object(pilot.subprocess,'run') as rpc:
            with self.assertRaises(Exception):pilot.query_preexpiry_slurm_submission(now)
            rpc.assert_not_called()

    def test_rpc_is_one_readonly_call_with_epoch_format(self):
        now=pilot.EXPIRES+timedelta(seconds=1);at=pilot.EXPIRES-timedelta(seconds=10)
        class Receipt:stdout=f'JobId=761600 SubmitTime={int(at.timestamp())}'
        with patch.dict(pilot.os.environ,{'SLURM_JOB_ID':'761600'}),patch.object(pilot.subprocess,'run',return_value=Receipt()) as rpc:
            pilot.query_preexpiry_slurm_submission(now)
            args,kw=rpc.call_args;self.assertEqual(args[0],['scontrol','--oneliner','show','job','761600'])
            self.assertEqual(kw['env']['SLURM_TIME_FORMAT'],'%s');self.assertEqual(kw['timeout'],15)
            self.assertTrue(kw['check'] and kw['capture_output'] and kw['text']);rpc.assert_called_once()

    def test_nested_verify_after_binding_and_summary_own_directory(self):
        saved=pilot.base.build,pilot.base.PLAN,pilot.base.MANIFEST,pilot.base.SCHEMA
        try:
            pilot.base.build,pilot.base.PLAN,pilot.base.MANIFEST,pilot.base.SCHEMA=pilot.build,pilot.PLAN,pilot.MANIFEST,pilot.SCHEMA
            case,meta=pilot.verify();self.assertEqual(case['case_id'],pilot.CASE_ID)
            parent_id=pilot.parent.CASE_ID
            with patch.object(pilot.base,'evidence',side_effect=RuntimeError('stop before raw parse')) as evidence:
                with self.assertRaises(RuntimeError):pilot.summarize({},Path('root'),case,meta)
                self.assertEqual(evidence.call_args.args[1],Path('root')/pilot.CASE_ID)
            self.assertEqual(pilot.parent.CASE_ID,parent_id)
        finally:pilot.base.build,pilot.base.PLAN,pilot.base.MANIFEST,pilot.base.SCHEMA=saved

    def test_command_polarity_and_physical_gate_not_relaxed(self):
        self.assertEqual(pilot.parent.parent.rail_command([.9,0.,0.,.9],.9),'O')
        self.assertEqual(pilot.parent.parent.rail_command([0.,.9,.9,0.],.9),'Z')
        measured={'screen_pass':True,'logic_smoke_pass':True}
        self.assertFalse(pilot.parent.parent.parent.apply_physical_screen(measured,True,False)['screen_pass'])
        self.assertTrue(pilot.parent.parent.parent.apply_physical_screen(measured,True,False)['logic_smoke_pass'])

    def test_original_completeness_error_and_agreement_gates(self):
        rows=[dict(expected_code=64,observed_comparator_code=64,observed_registered_code=64,
            trial_results=[dict(decision=1) for _ in range(7)]) for _ in range(12)]
        observed=[dict(expected_code=64,observed_registered_code=64) for _ in range(12)]; cm=[0.,0.]
        self.assertTrue(pilot.Q_PARENT.screen(rows,observed,cm)['screen_pass'])
        bad=json.loads(json.dumps(rows));bad[0]['trial_results'][0]['decision']=None
        self.assertFalse(pilot.Q_PARENT.screen(bad,observed,cm)['screen_pass'])
        bad=json.loads(json.dumps(rows));bad[0]['observed_comparator_code']=None
        self.assertFalse(pilot.Q_PARENT.screen(bad,observed,cm)['screen_pass'])
        bad=json.loads(json.dumps(rows));bad[0]['observed_comparator_code']=63
        self.assertFalse(pilot.Q_PARENT.screen(bad,observed,cm)['screen_pass'])
        seven_wrong=[65]*7+[64]*5
        bad=json.loads(json.dumps(rows))
        for row,value in zip(bad,seven_wrong,strict=True):row['observed_comparator_code']=value
        bad_registered=[dict(expected_code=64,observed_registered_code=value) for value in seven_wrong]
        self.assertFalse(pilot.Q_PARENT.screen(bad,bad_registered,cm)['screen_pass'])
        one_2lsb=[66]+[64]*11
        bad=json.loads(json.dumps(rows));bad[0]['observed_comparator_code']=66
        bad_registered=[dict(expected_code=64,observed_registered_code=value) for value in one_2lsb]
        self.assertFalse(pilot.Q_PARENT.screen(bad,bad_registered,cm)['screen_pass'])
        self.assertFalse(pilot.Q_PARENT.screen(rows,observed,[10.0001,0.])['screen_pass'])

    def test_all_new_payload_and_manifest_are_lf(self):
        for name in ('sar7_b2_local_drive.py','sar7_b2_local_drive.sbatch','test_sar7_b2_local_drive.py','AUTHORIZATION.json','PLAN.json','HANDOFF_zh_TW.md','SHA256SUMS.txt'):
            content=(pilot.ROOT/name).read_bytes()
            self.assertNotIn(b'\r',content,name)
            self.assertTrue(content.endswith(b'\n'),name)

    def test_full_case20_selected_parser_144_nodes_84_trials_72_boundaries(self):
        case=pilot.case_record();_,meta=pilot.build(case);wave=meta['wave']
        step=wave['strobe_s'];count=int(wave['stop_s']/step)
        time=[i*step for i in range(count+1)]
        if time[-1]<wave['stop_s']:time.append(wave['stop_s'])
        zero=[0.]*len(time);high=[wave['vdd_V']]*len(time);cm=[.45]*len(time)
        values={node:zero for node in wave['saved_signals']};values['time']=time
        for node in wave['saved_signals']:
            if node.startswith('clk') or (node.startswith('bit') and not node.endswith('b')):values[node]=high
            if node.startswith('qmid') and node.endswith('n'):values[node]=high
            if node.startswith('q') and not node.startswith('qmid') and node.endswith('p'):values[node]=high
            if node.startswith('XCMP') and node.endswith('.y'):values[node]=high
            if node in wave['dac_pair'] or node in ('sensep','sensen'):values[node]=cm
            if node.startswith('c') and not node.startswith('cb') and node.endswith('o') or node.startswith('cb') and node.endswith('z'):values[node]=high
        # Deliberately unassessable prior-b6 polarity checks that None is not reported as stable.
        values['XCMP6.x']=cm;values['XCMP6.y']=cm
        digest='b'*64;inventory=[dict(path=pilot.base.review.RAW_NAME,sha256=digest,bytes=123)]
        hashes={'bench.scs':'c'*64,'spectre.log':'d'*64};status=dict(raw_inventory=inventory)
        rows=[]
        for cv in wave['conversions']:
            trials=[dict(bit=t['bit'],decision=1,stable_rail_delay_s=20*pilot.native.PS,
                compare_to_read_s=t['read_s']-t['compare_s']) for t in cv['trials']]
            rows.append(dict(index=cv['index'],scored=True,expected_code=cv['expected_code'],
                observed_comparator_code=127,observed_registered_code=127,sample_dac_common_mode_V=.45,trial_results=trials))
        report=dict(conversions=rows,tested_conversions=12,execution_files_sha256=hashes,tran_sha256=digest,
            max_abs_sample_error_lsb=0.,max_observed_resolve_delay_s=20e-12,slurm_task_id='fixture',solver_seconds=1.,raw_bytes=123)
        selected_sets=[]
        class Raw:
            sha256=digest;sweep_names=['time']
            def __init__(self,admitted):self.values=admitted
            def unit(self,key):return 's' if key=='time' else 'A' if key.endswith(':p') else 'V'
        def selected(path,required):
            selected_sets.append(set(required));self.assertTrue(set(required)<=set(values))
            return Raw({key:values[key] for key in required})
        def safe_raw(directory,status,name,parser):return parser(Path('existing_fixture'))
        q_parent=pilot.Q_PARENT;original_extras=q_parent.summarize.__globals__['EXTRA_SAVES']
        original_parent=pilot.SUMMARY_PARENT.summarize.__globals__['parent']
        with ExitStack() as stack:
            stack.enter_context(patch.object(pilot.base,'evidence',return_value=(wave,status,hashes)))
            stack.enter_context(patch.object(pilot.common,'raw_inventory',return_value=inventory))
            stack.enter_context(patch.object(pilot.common,'sha',return_value='a'*64))
            stack.enter_context(patch.object(pilot.base.review,'parse_selected',side_effect=selected))
            stack.enter_context(patch.object(pilot.base.review,'safe_raw',side_effect=safe_raw))
            stack.enter_context(patch.object(pilot.base,'collect',side_effect=AssertionError('Summary must not recollect')))
            with self.assertRaisesRegex(KeyError,'trial6'):
                pilot.child_summary_function(q_parent.summarize)(report,Path('case20_root'),case,meta)
            self.assertNotIn('trial6',selected_sets[-1]);selected_sets.clear()
            result=pilot.summarize(report,Path('case20_root'),case,meta)
        self.assertEqual(len(selected_sets),1)
        self.assertEqual(len(selected_sets[0]),144)
        self.assertEqual(result['selected_parser']['summary_psf_parse_count'],1)
        self.assertIn('Separate inherited measurement',result['selected_parser']['basic_measurement_parse'])
        self.assertTrue(set(wave['saved_signals'])<=selected_sets[0])
        self.assertEqual(result['case_id'],pilot.CASE_ID)
        self.assertEqual(result['schema'],pilot.SCHEMA)
        self.assertEqual(len(result['timing']),84)
        self.assertEqual(result['overlap_diagnostic']['observed_within_conversion_boundaries'],72)
        self.assertEqual(result['overlap_diagnostic']['polarity_assessed_boundaries'],60)
        self.assertEqual(result['overlap_diagnostic']['polarity_unassessable_boundaries'],12)
        self.assertEqual(result['overlap_diagnostic']['prior_latch_opposite_rail_boundaries'],0)
        self.assertIn('active_last_read_cm_pass',result['readout_565'])
        self.assertIs(q_parent.summarize.__globals__['EXTRA_SAVES'],original_extras)
        self.assertIs(pilot.SUMMARY_PARENT.summarize.__globals__['parent'],original_parent)



if __name__=='__main__':unittest.main()
