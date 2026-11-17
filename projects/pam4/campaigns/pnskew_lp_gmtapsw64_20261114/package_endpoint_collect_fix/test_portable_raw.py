"""Offline tests for historical NFS identity and live collection guards."""
import json
import os
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace
import unittest
from unittest import mock
from uuid import uuid4

import comp_measure
import olympus_common as common
import recover_bias as recovery


ROOT = Path(__file__).resolve().parent


class HistoricalInventory(unittest.TestCase):
    def test_cross_host_comparison_ignores_only_st_dev(self):
        previous = {'path':'raw/dcOp.dc','bytes':30,'sha256':'a'*64,
                    'mtime_ns':12,'inode':100,'device':61}
        live = dict(previous,device=55)
        self.assertTrue(common.matches_historical_inventory([previous],[live]))
        self.assertFalse(common.matches_historical_inventory([previous],[live,live]))
        self.assertFalse(common.matches_historical_inventory([previous],[]))
        for key in ('path','bytes','sha256','mtime_ns','inode'):
            with self.subTest(key=key):
                self.assertFalse(common.matches_historical_inventory([previous],[dict(live, **{key:0})]))

    def test_live_identity_and_retirement_keep_exact_device(self):
        row = {'inode':100,'bytes':30,'mtime_ns':12,'device':61}
        node = SimpleNamespace(st_ino=100,st_size=30,st_mtime_ns=12,st_dev=55)
        self.assertFalse(common.same_identity(node,row))
        self.assertTrue(common.same_identity(node,dict(row,device=55)))


class LocalCase(unittest.TestCase):
    def setUp(self):
        self.root = ROOT/('portable_raw_test_'+uuid4().hex)
        self.root.mkdir()
        self.addCleanup(shutil.rmtree,self.root)
        if not hasattr(os,'getuid'):
            patch = mock.patch.object(os,'getuid',lambda:self.root.stat().st_uid,create=True)
            patch.start()
            self.addCleanup(patch.stop)

    def test_partial_publication_retries_from_new_collector(self):
        report = {'measurement_complete':True,'case_id':self.root.name}
        receipt = {'case_id':self.root.name,'solver_hostname':'n02-hera',
                   'collector_hostname':'n01-zeus'}
        real_link = os.link

        def interrupted_link(source,target):
            if target.name=='completion.json':
                raise OSError('Interrupted before commit')
            return real_link(source,target)

        with mock.patch.object(os,'link',side_effect=interrupted_link):
            with self.assertRaisesRegex(OSError,'Interrupted'):
                recovery.publish(self.root,report,receipt)
        original = (self.root/'recovery.json').read_bytes()
        retry = dict(receipt,collector_hostname='login')
        self.assertEqual(recovery.publish(self.root,report,retry),'recovered')
        self.assertEqual((self.root/'recovery.json').read_bytes(),original)
        self.assertEqual(json.loads(original)['collector_hostname'],'n01-zeus')
        completion = common.read(self.root/'completion.json')
        self.assertEqual(completion['recovery_sha256'],common.sha(self.root/'recovery.json'))

    def test_parse_requires_collector_local_identity(self):
        folder = self.root/'raw'
        folder.mkdir()
        raw = folder/'dcOp.dc'
        raw.write_bytes(b'HEADER\nEND\n')
        row = common.raw_inventory(self.root)[0]
        parser = mock.Mock(return_value=SimpleNamespace(sha256=row['sha256']))
        stale = {'raw_inventory':[dict(row,device=row['device']+1)]}
        with self.assertRaisesRegex(ValueError,'Unattested raw output'):
            comp_measure.safe_raw(self.root,stale,raw.name,parser)
        parser.assert_not_called()
        comp_measure.safe_raw(self.root,{'raw_inventory':[row]},raw.name,parser)
        parser.assert_called_once_with(raw)

        def replace_raw(path):
            replacement = folder/'replacement'
            replacement.write_bytes(path.read_bytes())
            os.utime(replacement,ns=(path.stat().st_atime_ns,path.stat().st_mtime_ns))
            replacement.replace(path)
            return SimpleNamespace(sha256=row['sha256'])

        with self.assertRaisesRegex(ValueError,'Raw changed during parsing'):
            comp_measure.safe_raw(self.root,{'raw_inventory':[row]},raw.name,replace_raw)

    def test_legacy_solver_hostname_comes_from_pinned_log(self):
        (self.root/'spectre.log').write_text('User: test   Host: n02-hera   HostID: A   PID: 1\n',encoding='ascii')
        self.assertEqual(recovery.original_solver_hostname(self.root,{}),'n02-hera')
        self.assertEqual(recovery.original_solver_hostname(self.root,{'solver_hostname':'n01-zeus'}),'n01-zeus')

    def test_same_session_device_change_blocks_publication(self):
        def patch(target, **kwargs):
            context = mock.patch.object(*target, **kwargs)
            self.addCleanup(context.stop)
            return context.start()

        if os.name=='nt':
            lockfile = self.root/'mock-lock'
            lockfile.touch()
            real_open = os.open
            patch((os,'O_DIRECTORY'),new=0,create=True)
            patch((os,'O_NOFOLLOW'),new=0,create=True)
            patch((os,'open'),side_effect=lambda path,flags:real_open(lockfile,os.O_RDONLY))
            modules = mock.patch.dict(sys.modules,{'fcntl':mock.Mock(LOCK_EX=2,LOCK_NB=4)})
            self.addCleanup(modules.stop)
            modules.start()
        (self.root/'bench.scs').write_text('save GMSRIREF:p\n',encoding='ascii')
        case = {'bias_mode':'replica','DC_currents':['GMSRIREF:p'],
                'AC_traces':[],'rail_voltages_V':{}}
        identities = [(case,{'raw_inventory':[{'device':dev}]}) for dev in (55,61)]
        devices = ('GMSRCS0', *(f'GMSH{leg}CS{i}' for leg in 'PM' for i in range(14)))
        report = {'saved_mos_oppoint':{name:{k:1. for k in ('ids','gm','vds','vdsat')}
                                       for name in devices}}
        with mock.patch.object(recovery,'verify_case',side_effect=identities), \
             mock.patch.object(recovery.gm_select,'measure',return_value=report), \
             mock.patch.object(recovery,'reference_current',return_value={}), \
             mock.patch.object(recovery,'publish') as publish:
            with self.assertRaisesRegex(ValueError,'Live raw identity changed'):
                recovery.recover_case(self.root,{})
            publish.assert_not_called()


if __name__ == '__main__':
    unittest.main()
