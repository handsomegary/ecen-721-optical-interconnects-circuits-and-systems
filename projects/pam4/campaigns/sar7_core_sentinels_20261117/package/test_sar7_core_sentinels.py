"""Frozen comparator-input diagnostic: physical scope, controlled inputs, and honest rail evidence."""

from array import array
from bisect import bisect_left, bisect_right
from collections import Counter
from contextlib import ExitStack, nullcontext
from datetime import datetime, timedelta, timezone
import copy
import hashlib
import json
from pathlib import Path
import re
import unittest
from unittest.mock import patch

import sar7_core_sentinels as pilot


def blocks(lines):
    result={};active=None
    for line in lines:
        if line.startswith('subckt '):active=line.split()[1];result[active]=[]
        if active is not None:result[active].append(line)
        if line.startswith('ends '):active=None
    return result


class CoreSentinelTests(unittest.TestCase):
    def test_only_seven_input_ports_two_pwl_sources_and_two_saves_change(self):
        old,_=pilot.parent.build(pilot.parent.case_record());new,meta=pilot.build(pilot.case_record())
        before=old.decode('ascii').splitlines();after=new.decode('ascii').splitlines()
        self.assertTrue(blocks(before)==blocks(after),'Every physical/CDF cell must remain exact')
        oldcmp={row.split()[0]:row for row in before if re.match(r'^XCMP[0-6] ',row)}
        newcmp={row.split()[0]:row for row in after if re.match(r'^XCMP[0-6] ',row)}
        self.assertEqual(set(oldcmp),{f'XCMP{bit}' for bit in range(7)})
        self.assertEqual(set(oldcmp),set(newcmp))
        for name in oldcmp:
            self.assertEqual(newcmp[name],oldcmp[name].replace('(sensep sensen ','(diag_p diag_n ',1))
            self.assertNotEqual(oldcmp[name],newcmp[name])
        oldlabels={row.split()[0] for row in before if row.split()}
        sources=[row for row in after if row.startswith('V') and row.split()[0] not in oldlabels]
        self.assertEqual(len(sources),2)
        self.assertEqual({tuple(row.split('(',1)[1].split(')',1)[0].split()) for row in sources},{('diag_p','0'),('diag_n','0')})
        self.assertTrue(all('type=pwl' in row for row in sources))
        for row in sources:
            side='p' if '(diag_p 0)' in row else 'n'
            serialized=[float(value) for value in re.search(r'wave=\[([^]]+)\]',row).group(1).split()]
            declared=[value for point in pilot.stimulus_points(side) for value in point]
            self.assertEqual(len(serialized),len(declared))
            for index,(actual,expected) in enumerate(zip(serialized,declared,strict=True)):
                self.assertAlmostEqual(actual,expected,delta=1e-20 if index%2==0 else 1e-14)

        oldsave=[row for row in before if row.startswith('save ')]
        newsave=[row for row in after if row.startswith('save ')]
        added=Counter(token for row in newsave for token in row.split()[1:])-Counter(token for row in oldsave for token in row.split()[1:])
        self.assertEqual(added,Counter({'diag_p':1,'diag_n':1}))
        self.assertTrue(set(meta['wave']['saved_signals'])==set(pilot.parent.build(pilot.parent.case_record())[1]['wave']['saved_signals'])|{'diag_p','diag_n'})
        restored=[]
        for row in after:
            if row in sources:continue
            label=row.split()[0] if row.split() else ''
            if label in oldcmp:row=oldcmp[label]
            elif row.startswith('save '):
                tokens=[token for token in row.split() if token not in ('diag_p','diag_n')]
                if tokens==['save']:continue
                row=' '.join(tokens)
            restored.append(row)
        self.assertTrue(restored==before,'A clock/input/physical card/source outside the exact diagnostic delta changed')
        for name in [f'V_{kind}{bit}' for kind in ('trial','clk') for bit in range(7)]:
            self.assertEqual(next(row for row in before if row.startswith(name+' ')),next(row for row in after if row.startswith(name+' ')))

    def test_input_selector_rejects_missing_duplicate_and_wrong_original_port(self):
        source,_=pilot.parent.build(pilot.parent.case_record());lines=source.decode('ascii').splitlines()
        row=next(line for line in lines if line.startswith('XCMP3 '))
        self.assertIn('(sensep sensen ',row)
        missing=lines.copy();missing.remove(row)
        wrong=[line.replace('(sensep sensen ','(sensep inn ',1) if line==row else line for line in lines]
        for name,rows in [('missing',missing),('duplicate',lines+[row]),('wrong_port',wrong)]:
            with self.subTest(mutation=name),self.assertRaises(Exception):
                pilot.input_patch(('\n'.join(rows)+'\n').encode('ascii'))
        _,counts=pilot.input_patch(source)
        self.assertIsInstance(counts,dict)

    def test_frozen_parent_bytes_case_and_all_original_wave_timing(self):
        case=pilot.case_record();source,meta=pilot.build(case)
        again,second=pilot.build(json.loads(json.dumps(case)))
        self.assertEqual(source,again);self.assertEqual(meta,second)
        old,prior=pilot.parent.build(pilot.parent.case_record())
        self.assertEqual(hashlib.sha256(old).hexdigest(),pilot.PARENT_DECK_SHA)
        self.assertEqual(len(meta['wave']['conversions']),12)
        for cv,oldcv in zip(meta['wave']['conversions'],prior['wave']['conversions'],strict=True):
            self.assertEqual(cv,oldcv)
        self.assertEqual(meta['wave']['period_s'],prior['wave']['period_s'])
        self.assertEqual(meta['wave']['stop_s'],prior['wave']['stop_s'])
        self.assertEqual(meta['wave']['strobe_s'],prior['wave']['strobe_s'])
        with self.assertRaises(Exception):pilot.build(dict(case,case_id='unauthorized_other_diagnostic'))
        # Retaining a parent metadata SHA must not hide changed physical bytes.
        rows=old.decode('ascii').splitlines();card=next(row for row in rows if row.startswith('M') and ' w=' in row)
        tampered=('\n'.join(row.replace(' w=',' w=2*',1) if row==card else row for row in rows)+'\n').encode('ascii')
        with patch.object(pilot.parent,'build',return_value=(tampered,prior)),self.assertRaises(Exception):pilot.build(case)

    def test_exact_six_opposite_history_pairs_and_97ps_static_presettling(self):
        self.assertEqual(pilot.LSB,.1/128)
        self.assertEqual(pilot.VCM,.8346351044855786)
        expected=(-pilot.LSB/16,pilot.LSB/16,-pilot.LSB,pilot.LSB,-.005,.005)
        self.assertEqual(tuple(pilot.SENTINELS),expected)
        records=pilot.stimulus_records();self.assertEqual(len(records),12)
        _,meta=pilot.build(pilot.case_record());wave=meta['wave']
        for j,target in enumerate(expected):
            pre,record=records[2*j:2*j+2]
            self.assertEqual(pre['role'],'precondition');self.assertEqual(record['role'],'target')
            self.assertEqual(pre['differential_V'],-.005 if target>0 else .005)
            self.assertEqual(record['differential_V'],target)
            self.assertEqual(record['target_index'],j)
        for index,record in enumerate(records):
            self.assertEqual(record['index'],index)
            self.assertEqual(record['expected_polarity'],int(record['differential_V']>0))
            origin=index*wave['period_s']
            self.assertAlmostEqual(record['change_start_s'],origin+10*pilot.native.PS,places=23)
            self.assertAlmostEqual(record['change_end_s'],origin+11*pilot.native.PS,places=23)
            first=wave['conversions'][index]['trials'][0]
            self.assertAlmostEqual((first['compare_s']-record['change_end_s'])/pilot.native.PS,97.,places=8)
        points_p=pilot.stimulus_points('p');points_n=pilot.stimulus_points('n')
        self.assertEqual([point[0] for point in points_p],[point[0] for point in points_n])
        for at in [record['change_end_s'] for record in records]:
            ip=next(i for i,point in enumerate(points_p) if point[0]==at)
            j=next(i for i,record in enumerate(records) if record['change_end_s']==at)
            self.assertAlmostEqual(points_p[ip][1]-points_n[ip][1],records[j]['differential_V'],places=14)
            self.assertAlmostEqual((points_p[ip][1]+points_n[ip][1])/2,pilot.VCM,places=14)


    @staticmethod
    def synthetic_fixture():
        case=pilot.case_record();_,meta=pilot.build(case);wave=meta['wave'];records=pilot.stimulus_records()
        step=wave['strobe_s'];count=int(wave['stop_s']/step);time=[i*step for i in range(count+1)]
        if time[-1]<wave['stop_s']:time.append(wave['stop_s'])
        vdd=wave['vdd_V'];zero=[0.]*len(time);high=[vdd]*len(time)
        values={node:zero for node in wave['saved_signals']};values['time']=time
        for bit in range(7):
            for node in (f'XCMP{bit}.x',f'XCMP{bit}.y',f'qmid{bit}p',f'qmid{bit}n'):values[node]=high.copy()
            for prefix in ('q','qdecode'):
                for side in 'pn':values[f'{prefix}{bit}{side}']=zero.copy()
            for cv,record in zip(wave['conversions'],records,strict=True):
                trial=next(t for t in cv['trials'] if t['bit']==bit)
                lo=bisect_left(time,trial['compare_s']+20*pilot.native.PS)
                hi=bisect_left(time,cv['index']*wave['period_s']+568*pilot.native.PS)
                expected=record['expected_polarity'];p=vdd if expected else 0.;n=0. if expected else vdd
                for node,value in [(f'q{bit}p',p),(f'q{bit}n',n),(f'qmid{bit}p',n),(f'qmid{bit}n',p),
                    (f'qdecode{bit}p',p),(f'qdecode{bit}n',n),(f'XCMP{bit}.x',n),(f'XCMP{bit}.y',p)]:
                    values[node][lo:hi]=[value]*(hi-lo)
        def interpolate(points,at):
            j=bisect_right([point[0] for point in points],at)-1
            if j<0:return points[0][1]
            if j+1==len(points):return points[-1][1]
            a,b=points[j],points[j+1]
            return a[1]+(b[1]-a[1])*(at-a[0])/(b[0]-a[0])
        for side in 'pn':
            points=pilot.stimulus_points(side);values[f'diag_{side}']=[interpolate(points,at) for at in time]
        return case,meta,wave,records,{node:array('d',trace) for node,trace in values.items()}

    def test_static_polarity_stage_mapping_reset_and_all_84_trials(self):
        case,meta,wave,records,values=self.synthetic_fixture()
        report=pilot.characterize(values,wave,records)
        self.assertEqual(report['status'],'characterized')
        self.assertFalse(report['adc_screen_applicable'])
        self.assertNotIn('screen_pass',report);self.assertNotIn('logic_smoke_pass',report)
        self.assertEqual(len(report['trials']),84)
        self.assertEqual(Counter(row['role'] for row in report['trials']),Counter({'precondition':42,'target':42}))
        self.assertEqual(report['controls']['required'],56)
        self.assertEqual(report['controls']['raw_correct_by_44'],56)
        self.assertEqual(report['controls']['raw_stable_correct_by_44'],56)
        self.assertEqual(report['controls']['reset_valid'],56)
        self.assertTrue(report['controls']['valid'])
        for row in report['trials']:
            expected=records[row['cycle_index']]['expected_polarity']
            self.assertEqual(row['expected_polarity'],expected)
            for at in ('at_original_read','at_44','at_48','at_60'):
                for stage in ('raw','xy','mid','decode'):
                    self.assertEqual(row[at][stage]['class'],expected,(row['cycle_index'],row['bit'],at,stage))
                    self.assertIs(row[at][stage]['correct'],True)
            # The physical XY and mid pair are inverted; returning raw polarity must be explicit.
            self.assertEqual(row['at_44']['xy']['pair_V'],list(reversed(row['at_44']['raw']['pair_V'])))
            self.assertEqual(row['at_44']['mid']['pair_V'],list(reversed(row['at_44']['raw']['pair_V'])))
            self.assertEqual(row['at_44']['decode']['pair_V'],row['at_44']['raw']['pair_V'])
        for group in ('nearzero','one_lsb','five_mV'):self.assertEqual(report['target_groups'][group]['samples'],14)

    def test_stable_rail_is_final_continuous_run_not_first_glitch_or_wrong_rail(self):
        ps=pilot.native.PS;vdd=.9;time=array('d',[t*ps for t in (0,10,20,21,22,30,44,48,60)])
        positive=array('d',[0.,vdd,vdd,.45,.45,vdd,vdd,vdd,vdd])
        negative=array('d',[0.,0.,0.,.45,.45,0.,0.,0.,0.])
        result=pilot.stable_rail(time,positive,negative,0.,60*ps,vdd,1)
        self.assertEqual(result['observed_class'],1)
        self.assertAlmostEqual(result['stable_expected_delay_ps'],30.)
        wrongp=[0.,vdd,vdd,.45,.45,0.,0.,0.,0.]
        wrongn=[0.,0.,0.,.45,.45,vdd,vdd,vdd,vdd]
        wrong=pilot.stable_rail(time,wrongp,wrongn,0.,60*ps,vdd,1)
        self.assertEqual(wrong['observed_class'],0)
        self.assertAlmostEqual(wrong['stable_observed_delay_ps'],30.)
        self.assertIsNone(wrong['stable_expected_delay_ps'])
        unavailable=pilot.stable_rail(time,[.45]*len(time),[.45]*len(time),0.,60*ps,vdd,1)
        self.assertIsNone(unavailable['observed_class']);self.assertIsNone(unavailable['stable_expected_delay_ps'])

    def test_nearzero_raw_unresolved_is_not_rescued_by_internal_or_late_rails(self):
        case,meta,wave,records,values=self.synthetic_fixture()
        cv=wave['conversions'][1];trial=next(t for t in cv['trials'] if t['bit']==1)
        lo=bisect_left(values['time'],trial['compare_s']);hi=min(len(values['time']),bisect_right(values['time'],trial['compare_s']+60*pilot.native.PS)+1)
        # Include the sample above +60 so interpolation cannot mix an unavailable endpoint with a restored rail.
        for side in 'pn':values[f'q1{side}'][lo:hi]=array('d',[.45])*(hi-lo)
        report=pilot.characterize(values,wave,records)
        row=next(r for r in report['trials'] if r['cycle_index']==1 and r['bit']==1)
        self.assertIsNone(row['at_original_read']['raw']['class'])
        self.assertIsNone(row['at_44']['raw']['class']);self.assertIsNone(row['at_60']['raw']['class'])
        self.assertTrue(row['at_44']['xy']['correct']);self.assertTrue(row['at_44']['mid']['correct']);self.assertTrue(row['at_44']['decode']['correct'])
        self.assertIsNone(row['stable']['raw']['stable_expected_delay_ps'])
        self.assertTrue(report['controls']['valid'],'Nearzero failure must remain separate from the5mV controls')
        self.assertEqual(report['target_groups']['nearzero']['raw_stable_correct_by_44'],13)
        self.assertFalse(report['adc_screen_applicable']);self.assertNotIn('screen_pass',report)
        # A failed5mV target is a strict control failure, even when other stages look valid.
        cv=wave['conversions'][9];trial=next(t for t in cv['trials'] if t['bit']==1)
        lo=bisect_left(values['time'],trial['compare_s']);hi=min(len(values['time']),bisect_right(values['time'],trial['compare_s']+60*pilot.native.PS)+1)
        for side in 'pn':values[f'q1{side}'][lo:hi]=array('d',[.45])*(hi-lo)
        self.assertFalse(pilot.characterize(values,wave,records)['controls']['valid'])

    def test_5mv_control_correct_at44_but_later_glitch_cannot_pass(self):
        case,meta,wave,records,values=self.synthetic_fixture()
        cv=wave['conversions'][9];trial=next(t for t in cv['trials'] if t['bit']==1)
        self.assertEqual(records[9]['differential_V'],-.005)
        lo=bisect_left(values['time'],trial['compare_s']+46*pilot.native.PS)
        hi=bisect_left(values['time'],trial['compare_s']+52*pilot.native.PS)
        values['q1p'][lo:hi]=array('d',[wave['vdd_V']])*(hi-lo)
        values['q1n'][lo:hi]=array('d',[0.])*(hi-lo)
        report=pilot.characterize(values,wave,records)
        row=next(r for r in report['trials'] if r['cycle_index']==9 and r['bit']==1)
        self.assertIs(row['at_44']['raw']['correct'],True)
        self.assertIs(row['at_48']['raw']['correct'],False)
        self.assertIs(row['at_60']['raw']['correct'],True)
        self.assertGreater(row['stable']['raw']['stable_expected_delay_ps'],44.)
        self.assertLess(row['stable']['raw']['stable_expected_delay_ps'],53.)
        self.assertEqual(report['controls']['raw_correct_by_44'],56)
        self.assertEqual(report['controls']['raw_stable_correct_by_44'],55)
        self.assertFalse(report['controls']['valid'])
        for label,expected in [('44',13),('48',13),('60',14)]:
            self.assertEqual(report['target_groups']['five_mV']['raw_stable_correct_by_'+label],expected)

    def test_one_lsb_target_reset_failure_invalidates_even_with_56_strong_resets_valid(self):
        case,meta,wave,records,values=self.synthetic_fixture()
        cv=wave['conversions'][5];trial=next(t for t in cv['trials'] if t['bit']==1)
        self.assertEqual(records[5]['differential_V'],-pilot.LSB)
        lo=bisect_left(values['time'],trial['compare_s']-2.5*pilot.native.PS)
        hi=bisect_right(values['time'],trial['compare_s']-1.5*pilot.native.PS)
        values['XCMP1.x'][lo:hi]=array('d',[0.])*(hi-lo)
        report=pilot.characterize(values,wave,records)
        row=next(r for r in report['trials'] if r['cycle_index']==5 and r['bit']==1)
        self.assertFalse(row['reset']['pass'])
        self.assertEqual(report['controls']['reset_valid'],56)
        self.assertEqual(report['reset_valid_trials'],83)
        self.assertFalse(report['controls']['valid'])

    def test_actual_input_mismatch_reset_or_missing_data_are_reported_or_rejected(self):
        case,meta,wave,records,values=self.synthetic_fixture()
        broken=values.copy();broken.pop('diag_n')
        with self.assertRaises(Exception):pilot.characterize(broken,wave,records)
        cv=wave['conversions'][1];trial=next(t for t in cv['trials'] if t['bit']==6)
        j=bisect_left(values['time'],trial['compare_s'])
        values['diag_p'][j]+=1e-4
        with self.assertRaisesRegex(ValueError,'Stiff diagnostic input differs'):
            pilot.characterize(values,wave,records)



    def test_selected_array_parser_is_once_146_nodes_no_adc_scorer(self):
        case,meta,wave,records,values=self.synthetic_fixture()
        self.assertIsInstance(values['time'],array)
        digest='b'*64;inventory=[dict(path=pilot.base.review.RAW_NAME,sha256=digest,bytes=123)]
        status=dict(raw_inventory=inventory,slurm_job_id='761800',spectre_wall_seconds=1.)
        hashes={'bench.scs':'c'*64,'spectre.log':'d'*64};selected_sets=[]
        class Raw:
            sha256=digest;sweep_names=['time']
            def __init__(self,admitted):self.values=admitted
            def unit(self,node):return 's' if node=='time' else 'A' if node.endswith(':p') else 'V'
        def parser(path,required):
            selected_sets.append(set(required))
            return Raw({node:values[node] for node in required})
        def safe_raw(directory,status,name,parser):return parser(Path('synthetic_owned_psf'))
        with ExitStack() as stack:
            stack.enter_context(patch.object(pilot.common,'raw_inventory',return_value=inventory))
            stack.enter_context(patch.object(pilot.common,'sha',return_value='a'*64))
            stack.enter_context(patch.object(pilot.base.review,'parse_selected',side_effect=parser))
            stack.enter_context(patch.object(pilot.base.review,'safe_raw',side_effect=safe_raw))
            stack.enter_context(patch.object(pilot.base,'collect',side_effect=AssertionError('Old ADC collector forbidden')))
            stack.enter_context(patch.object(pilot.score,'measure',side_effect=AssertionError('Old ADC scorer forbidden')))
            report,live=pilot.parse_and_characterize(Path('new_fixture')/pilot.CASE_ID,wave,status,hashes,case,meta)
        self.assertEqual(len(selected_sets),1);self.assertEqual(len(selected_sets[0]),146)
        self.assertEqual(selected_sets[0],{'time',*wave['saved_signals']})
        self.assertEqual(report['psf_parse_count'],1);self.assertEqual(len(report['trials']),84)
        self.assertEqual(report['case_id'],pilot.CASE_ID);self.assertEqual(report['schema'],pilot.SCHEMA)
        self.assertEqual(report['slurm_task_id'],'761800');self.assertEqual(report['tran_sha256'],digest)
        self.assertEqual(report['manifest_sha256'],'a'*64)
        self.assertEqual(report['portable_deck_sha256'],meta['portable_sha256'])
        self.assertEqual(report['parent_manifest_sha256'],pilot.PARENT_MANIFEST_SHA)
        self.assertEqual(report['parent_deck_sha256'],pilot.PARENT_DECK_SHA)
        self.assertEqual(report['execution_files_sha256'],hashes);self.assertEqual(live,inventory)
        self.assertEqual(Counter(row['role'] for row in report['trials']),Counter({'precondition':42,'target':42}))
        self.assertFalse(report['adc_screen_applicable'])

    def test_missing_selected_trace_or_changed_raw_inventory_rejected_before_interpretation(self):
        case,meta,wave,records,values=self.synthetic_fixture();values.pop('qdecode1p')
        digest='b'*64;inventory=[dict(path=pilot.base.review.RAW_NAME,sha256=digest,bytes=123)]
        status=dict(raw_inventory=inventory,slurm_job_id='761800',spectre_wall_seconds=1.)
        class Raw:
            sha256=digest;sweep_names=['time']
            def __init__(self,admitted):self.values=admitted
            def unit(self,node):return 's' if node=='time' else 'V'
        def parser(path,required):return Raw({node:values[node] for node in required})
        def safe_raw(directory,status,name,parser):return parser(Path('synthetic_owned_psf'))
        with patch.object(pilot.common,'raw_inventory',return_value=inventory),patch.object(pilot.base.review,'parse_selected',side_effect=parser),patch.object(pilot.base.review,'safe_raw',side_effect=safe_raw):
            with self.assertRaises(KeyError):pilot.parse_and_characterize(Path('new')/pilot.CASE_ID,wave,status,{},case,meta)
        changed=[dict(inventory[0],sha256='f'*64)]
        with patch.object(pilot.common,'raw_inventory',return_value=changed),patch.object(pilot.base.review,'safe_raw') as parse:
            with self.assertRaises(Exception):pilot.parse_and_characterize(Path('new')/pilot.CASE_ID,wave,status,{},case,meta)
            parse.assert_not_called()

    def test_collection_checks_evidence_and_raw_before_writing_only_own_measurement(self):
        case,meta,wave,records,values=self.synthetic_fixture();root=Path('unit_new_sentinel_root').absolute()
        inventory=[dict(path=pilot.base.review.RAW_NAME,sha256='b'*64,bytes=123)]
        status=dict(raw_inventory=inventory);hashes={'bench.scs':'c'*64}
        for mutation in ('hashes','status','wave','raw','none'):
            after_wave=copy.deepcopy(wave);after_status=copy.deepcopy(status);after_hashes=hashes.copy();after_raw=copy.deepcopy(inventory)
            if mutation=='hashes':after_hashes['bench.scs']='e'*64
            if mutation=='status':after_status['status']='changed'
            if mutation=='wave':after_wave['vdd_V']=1.
            if mutation=='raw':after_raw[0]['sha256']='e'*64
            with self.subTest(mutation=mutation),ExitStack() as stack:
                stack.enter_context(patch.object(pilot.base,'lock_case',return_value=nullcontext()))
                evidence=stack.enter_context(patch.object(pilot,'evidence',side_effect=[(wave,status,hashes),(after_wave,after_status,after_hashes)]))
                stack.enter_context(patch.object(pilot,'build',return_value=(b'fixture',meta)))
                parse=stack.enter_context(patch.object(pilot,'parse_and_characterize',return_value=({'schema':pilot.SCHEMA},inventory)))
                stack.enter_context(patch.object(pilot.common,'raw_inventory',return_value=after_raw))
                write=stack.enter_context(patch.object(pilot.common,'write_new'))
                stack.enter_context(patch.object(pilot.base,'collect',side_effect=AssertionError('Old ADC collector forbidden')))
                if mutation=='none':
                    result=pilot.collect_diagnostic(root,case)
                    self.assertTrue(result['source_unchanged_during_parse'])
                    write.assert_called_once_with(root/pilot.CASE_ID/pilot.MEASUREMENT,result)
                else:
                    with self.assertRaisesRegex(ValueError,'Execution evidence/raw changed'):pilot.collect_diagnostic(root,case)
                    write.assert_not_called()
                self.assertEqual(evidence.call_count,2);parse.assert_called_once()
                self.assertEqual(parse.call_args.args[0],root/pilot.CASE_ID)

    def test_cloned_execution_namespace_owns_collector_and_never_mutates_parent_globals(self):
        names=('build','PLAN','MANIFEST','SCHEMA','collect','stage','evidence')
        saved={name:pilot.base.run.__globals__[name] for name in names}
        context=pilot.execution_namespace()
        self.assertIs(context['build'],pilot.build);self.assertIs(context['collect'],pilot.collect_diagnostic)
        self.assertEqual(context['PLAN'],pilot.PLAN);self.assertEqual(context['MANIFEST'],pilot.MANIFEST)
        self.assertEqual(context['SCHEMA'],pilot.SCHEMA)
        self.assertIs(context['stage'].__globals__,context);self.assertIs(context['evidence'].__globals__,context)
        for name in names:self.assertIs(pilot.base.run.__globals__[name],saved[name],name)

    def test_open_ended_fresh_authorization_and_exact_submission_after_start(self):
        self.assertFalse(hasattr(pilot,'EXPIRES'))
        self.assertEqual(pilot.STARTS,datetime(2026,11,17,13,55,tzinfo=timezone.utc))
        self.assertTrue(pilot.AUTH_RECORD['no_expiry'])
        self.assertEqual(pilot.AUTH_RECORD['source_note'],'20261117T0755_user_delegates_sar7_papers_direction.md')
        self.assertEqual(pilot.AUTH_RECORD['source_note_sha256'],'d9491abfb1429caf097c1c798d763d6529264fb3fa9cbbf2b82cd78b0d4183ea')
        self.assertEqual(pilot.AUTH_RECORD['max_solver_cases_this_packet'],1)
        self.assertEqual(pilot.AUTH_RECORD['max_accepted_slurm_jobs'],1)
        self.assertEqual(pilot.AUTH_RECORD['cpus_this_job'],1)
        self.assertEqual(pilot.AUTH_RECORD['max_concurrent_sar7_jobs'],1)
        self.assertEqual(pilot.AUTH_RECORD['c2_temporary_throttle'],dict(original=5,temporary=4,restore=5))
        with self.assertRaises(Exception):pilot.check_started(pilot.STARTS-timedelta(seconds=1))
        now=pilot.STARTS+timedelta(days=2);pilot.check_started(now);job='761800'
        def receipt(at):return f'JobId={job} SubmitTime={int(at.timestamp())}'
        record=pilot.validate_submission(receipt(now-timedelta(minutes=1)),job,now)
        self.assertEqual(record['slurm_job_id'],job)
        self.assertEqual(record['authorization_source_sha256'],pilot.AUTH_RECORD['source_note_sha256'])
        for at in (pilot.STARTS-timedelta(seconds=1),now+timedelta(seconds=1)):
            with self.assertRaises(Exception):pilot.validate_submission(receipt(at),job,now)
        for text in ('JobId=1 SubmitTime=1794900000',f'JobId={job} SubmitTime=Unknown',f'JobId={job} JobId={job} SubmitTime=0'):
            with self.assertRaises(Exception):pilot.validate_submission(text,job,now)

    def test_every_run_queries_actual_slurm_id_with_readonly_epoch_receipt(self):
        now=pilot.STARTS+timedelta(days=2);at=now-timedelta(minutes=1)
        class Receipt:stdout=f'JobId=761800 SubmitTime={int(at.timestamp())}'
        with patch.dict(pilot.os.environ,{'SLURM_JOB_ID':'761800'}),patch.object(pilot.subprocess,'run',return_value=Receipt()) as rpc:
            record=pilot.query_submission(now)
            self.assertEqual(record['slurm_job_id'],'761800')
            args,kw=rpc.call_args;self.assertEqual(args[0],['scontrol','--oneliner','show','job','761800'])
            self.assertEqual(kw['env']['SLURM_TIME_FORMAT'],'%s');self.assertEqual(kw['timeout'],15)
            self.assertTrue(kw['check'] and kw['capture_output'] and kw['text']);rpc.assert_called_once()
        for bad in ('','761800_0','one;command'):
            with patch.dict(pilot.os.environ,{'SLURM_JOB_ID':bad}),patch.object(pilot.subprocess,'run') as rpc:
                with self.assertRaises(Exception):pilot.query_submission(now)
                rpc.assert_not_called()
        # There is no pre-expiry local shortcut: run always requires the current Slurm receipt.
        root=Path('unit_new_sentinel_run').absolute();events=[];receipt={'slurm_job_id':'761800'}
        def proof(now):events.append('proof');return receipt
        def stage(*args):events.append('stage')
        with patch.object(pilot,'query_submission',side_effect=proof) as query,patch.object(pilot,'existing_stage',side_effect=stage),patch.object(pilot.common,'write_new') as write,patch.object(pilot,'FunctionType',return_value=lambda *args:'diagnostic_complete'):
            self.assertEqual(pilot.run(root,{'case_id':pilot.CASE_ID},Path('private'),root/'approval.json'),'diagnostic_complete')
            self.assertEqual(events,['proof','stage']);query.assert_called_once()
            write.assert_called_once_with(root/'submission_proof.json',receipt)

    def test_verify_own_manifest_and_new_payload_lf(self):
        case,meta=pilot.verify()
        self.assertEqual(case['case_id'],pilot.CASE_ID)
        self.assertFalse(meta['adc_scoring_applicable'])
        self.assertEqual(meta['authorization'],pilot.AUTH_RECORD)
        for name in sorted(pilot.FILES|{'SHA256SUMS.txt'}):
            content=(pilot.ROOT/name).read_bytes();self.assertNotIn(b'\r',content,name)
            self.assertTrue(content.endswith(b'\n'),name)



if __name__=='__main__':unittest.main()
