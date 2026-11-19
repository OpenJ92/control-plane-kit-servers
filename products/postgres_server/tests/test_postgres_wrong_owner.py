"""Negative-fixture evidence laws; real interpretation stays in the owning gate."""
import io
import json
import os
import signal
import socket
import struct
import threading
import time
from contextlib import redirect_stderr
import unittest
from unittest.mock import Mock, patch

import control_plane_kit_servers_postgres_server.process as process

with patch.dict(os.environ, CPK_POSTGRES_TEST_RUN='cpk-postgres-unit', CPK_POSTGRES_HOST_RECORDS='/tmp/cpk-postgres-unit'):
    import live_postgres_image as witness

IMAGE = 'sha256:' + 'a' * 64
VOLUME = witness.RUN + '-wrong-owner-data'
PATH = '/var/lib/postgresql/data'
OBSERVATION = dict(runtime_uid=70, runtime_gid=70, uid=0, gid=0, mode=0o755,
                   is_directory=True, empty=True, guard_refused=True)
REFUSAL = (process.LIFECYCLE_PREFIX + '{"native_exit_code":null,"reason":"startup_failure"}\n'
           'postgres-server startup or lifecycle failure\n').encode()


def container_attrs(inspection=False):
    return dict(Image=IMAGE, Config=dict(User='70:70', Entrypoint=[],
        Cmd=['python3','-c',getattr(witness,'WRONG_OWNER_INSPECTION','fixed probe')] if inspection else ['python3','-m','control_plane_kit_servers_postgres_server.process']),
        HostConfig=dict(Mounts=[dict(Type='volume',Source=VOLUME,Target=PATH,
            ReadOnly=inspection,VolumeOptions={'NoCopy':True})], ReadonlyRootfs=inspection,
            NetworkMode='none' if inspection else 'test-network'),
        Mounts=[dict(Type='volume',Name=VOLUME,Destination=PATH,RW=not inspection)])


class WrongOwnerEvidenceTests(unittest.TestCase):
    def function(self, name):
        function=getattr(witness,name,None)
        self.assertTrue(callable(function),name+' behavior is missing')
        return function

    def test_observation_requires_closed_complete_wrong_owner_empty_evidence(self):
        parse=self.function('wrong_owner_observation')
        self.assertEqual(parse(json.dumps(OBSERVATION).encode()),OBSERVATION)
        for key,value in [('runtime_uid',0),('runtime_gid',0),('uid',70),('gid',70),('mode',0o777),
                          ('is_directory',False),('empty',False),('guard_refused',False),('uid',False)]:
            with self.subTest(key=key,value=value):
                with self.assertRaises(AssertionError): parse(json.dumps(dict(OBSERVATION,**{key:value})).encode())
        for raw in (b'{}', b'x'+json.dumps(OBSERVATION).encode(),json.dumps(OBSERVATION).encode()+b'\n{}',
                    b' ' * 4097, json.dumps(dict(OBSERVATION,extra=True)).encode(),
                    json.dumps(OBSERVATION).replace('"uid": 0','"uid": 70, "uid": 0').encode()):
            with self.subTest(raw=raw[:50]):
                with self.assertRaises(AssertionError):parse(raw)

    def test_refusal_rejects_generic_exit_or_native_extra_output(self):
        validate=self.function('wrong_owner_refusal')
        validate(REFUSAL)
        for raw in (b'',b'failed\n',REFUSAL+b'initdb started\n',b'native output\n'+REFUSAL,
                    REFUSAL+REFUSAL,REFUSAL.replace(b'startup_failure',b'native_exit'),
                    REFUSAL.replace(b'null',b'1'), b'x'*4097):
            with self.subTest(raw=raw[:50]):
                with self.assertRaises(AssertionError):validate(raw)

    def test_log_capture_is_complete_bounded_and_never_tail_based(self):
        read=self.function('read_wrong_owner_logs')
        container=Mock();response=Mock(raw=io.BytesIO(struct.pack('>B3sI',2,b'\0'*3,len(REFUSAL))+REFUSAL))
        container.client.api._get.return_value=response
        self.assertEqual(read(container),REFUSAL)
        self.assertEqual(container.client.api._get.call_args.kwargs,dict(params={'stdout':1,'stderr':1,'follow':0},stream=True))
        response.close.assert_called_once()
        for raw in (b'\x02',struct.pack('>B3sI',2,b'\0'*3,10)+b'short',
                    struct.pack('>B3sI',2,b'\0'*3,4097),struct.pack('>B3sI',3,b'\0'*3,0),
                    struct.pack('>B3sI',2,b'\0'*3,len(REFUSAL)+1)+REFUSAL,
                    struct.pack('>B3sI',2,b'\0'*3,len(REFUSAL))+REFUSAL+struct.pack('>B3sI',2,b'\0'*3,1)):
            response=Mock(raw=io.BytesIO(raw));container.client.api._get.return_value=response
            with self.assertRaises(AssertionError):read(container)
            response.close.assert_called_once()
        response=Mock();response.raw.read.side_effect=OSError('private sentinel')
        container.client.api._get.return_value=response
        with self.assertRaises(AssertionError) as caught:read(container)
        self.assertNotIn('sentinel',str(caught.exception));response.close.assert_called_once()

    def test_stalled_header_and_body_reads_are_interrupted_and_closed(self):
        read=self.function('read_wrong_owner_logs')
        for prefix in (b'',struct.pack('>B3sI',2,b'\0'*3,10)+b'partial'):
            with self.subTest(prefix=prefix):
                reader,writer=socket.socketpair();raw=reader.makefile('rb')
                response=Mock(raw=raw)
                def close():raw.close();reader.close()
                response.close.side_effect=close
                container=Mock();container.client.api._get.return_value=response
                if prefix:writer.sendall(prefix)
                # Test-only escape hatch; the implementation has no worker thread.
                watchdog=threading.Timer(2,writer.close);watchdog.start()
                previous=signal.getsignal(signal.SIGALRM);started=time.monotonic()
                try:
                    with patch.object(witness,'WRONG_OWNER_LOG_SECONDS',0.05):
                        with self.assertRaises(AssertionError):read(container)
                    self.assertLess(time.monotonic()-started,1)
                    response.close.assert_called_once();self.assertEqual(reader.fileno(),-1)
                    self.assertIs(signal.getsignal(signal.SIGALRM),previous)
                    self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.0,0.0))
                finally:
                    watchdog.cancel();watchdog.join(timeout=1);writer.close();raw.close();reader.close()

    def test_existing_timer_refuses_before_log_request(self):
        read=self.function('read_wrong_owner_logs');container=Mock()
        try:
            signal.setitimer(signal.ITIMER_REAL,30)
            with self.assertRaises(AssertionError):read(container)
            container.client.api._get.assert_not_called()
            self.assertGreater(signal.getitimer(signal.ITIMER_REAL)[0],0)
        finally:signal.setitimer(signal.ITIMER_REAL,0)

    def test_log_acquisition_is_within_deadline_and_error_is_not_eof(self):
        read=self.function('read_wrong_owner_logs');container=Mock()
        reader,writer=socket.socketpair()
        container.client.api._get.side_effect=lambda *_args,**_kwargs:reader.recv(1)
        watchdog=threading.Timer(2,writer.close);watchdog.start()
        started=time.monotonic()
        try:
            with patch.object(witness,'WRONG_OWNER_LOG_SECONDS',0.05):
                with self.assertRaises(AssertionError):read(container)
            self.assertLess(time.monotonic()-started,1)
            self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.0,0.0))
        finally:watchdog.cancel();watchdog.join(timeout=1);writer.close();reader.close()
        container.client.api._get.side_effect=OSError('private sentinel')
        with self.assertRaises(AssertionError) as caught:read(container)
        self.assertNotIn('sentinel',str(caught.exception))

    def test_actual_mount_identity_nocopy_rw_and_runtime_uid_are_required(self):
        verify=self.function('verify_wrong_owner_container')
        for inspection in (False,True):
            container=Mock();container.attrs=container_attrs(inspection)
            verify(container,IMAGE,VOLUME,inspection=inspection)
            for mutation in ('image','uid','nocopy','source','runtime_source','rw','bind'):
                with self.subTest(inspection=inspection,mutation=mutation):
                    container.attrs=container_attrs(inspection)
                    if mutation=='image':container.attrs['Image']='foreign'
                    elif mutation=='uid':container.attrs['Config']['User']='0:0'
                    elif mutation=='nocopy':container.attrs['HostConfig']['Mounts'][0]['VolumeOptions']['NoCopy']=False
                    elif mutation=='source':container.attrs['HostConfig']['Mounts'][0]['Source']='foreign'
                    elif mutation=='runtime_source':container.attrs['Mounts'][0]['Name']='foreign'
                    elif mutation=='rw':container.attrs['Mounts'][0]['RW']=inspection
                    else:container.attrs['Mounts'][0]['Type']='bind'
                    with self.assertRaises(AssertionError):verify(container,IMAGE,VOLUME,inspection=inspection)

    def test_negative_volume_cleanup_requires_poststate_not_just_exit1(self):
        exercise=self.function('exercise_wrong_owner')
        for outcome in ('pass','nonempty','generic-exit','unknown'):
            with self.subTest(outcome=outcome):
                client=Mock();image=Mock(id=IMAGE);volume=Mock(name=VOLUME)
                volume.name=VOLUME
                volume.attrs=dict(Name=VOLUME,Driver='local',Options=None,Labels=witness.LABELS)
                client.volumes.list.return_value=[];client.volumes.create.return_value=volume
                refused=Mock();refused.labels=witness.LABELS
                post=dict(OBSERVATION,empty=False) if outcome=='nonempty' else OBSERVATION
                observations=[OBSERVATION,RuntimeError('unknown') if outcome=='unknown' else post]
                with patch.object(witness,'inspect_wrong_owner_fixture',side_effect=observations), \
                     patch.object(witness,'create',return_value=refused), \
                     patch.object(witness,'verify_wrong_owner_container'), \
                     patch.object(witness,'wait_exit'), \
                     patch.object(witness,'read_wrong_owner_logs',return_value=b'failed' if outcome=='generic-exit' else REFUSAL):
                    if outcome=='pass':exercise(client,image,'network')
                    else:
                        with self.assertRaises((AssertionError,RuntimeError)):exercise(client,image,'network')
                refused.remove.assert_called_once_with(force=True)
                if outcome=='pass':volume.remove.assert_called_once_with()
                else:volume.remove.assert_not_called()

    def test_main_pgdata_guard_stops_before_password_configuration_and_native(self):
        output=io.StringIO()
        with patch.object(process.os,'getuid',return_value=70),patch.object(process.os,'getgid',return_value=70), \
             patch.object(process,'validate_pgdata',side_effect=process.PostgresProcessError('RAW_SENTINEL')), \
             patch.object(process,'read_password') as password, \
             patch.object(process,'read_postgres_control_configuration') as configuration, \
             patch.object(process,'create_management_server') as server, \
             patch.object(process,'PostgresCoordinator') as coordinator, \
             patch.object(process,'_spawn_native') as native,redirect_stderr(output):
            self.assertEqual(process.main(),1)
        for call in (password,configuration,server,coordinator,native):call.assert_not_called()
        self.assertEqual(output.getvalue().encode(),REFUSAL)
