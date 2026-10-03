import asyncio
import io
import json
import threading
from dataclasses import replace
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import Mock
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import pytest
from PIL import Image
from config import Config
from register_faces import enroll
from runtime import Supervisor, make_http_handler
from state import RuntimeState
from test_framework import ready_state


def test_only_one_parent_session_can_be_reserved(monkeypatch):
    released=threading.Event()
    class FakeConversation:
        def __init__(self,*args):pass
        async def run(self):await asyncio.to_thread(released.wait,3)
    monkeypatch.setattr('runtime.Conversation',FakeConversation)
    supervisor=Supervisor(Config(),ready_state(),Mock(),Mock(),Mock())
    try:
        assert supervisor.start('father')
        assert not supervisor.start('mother')
        assert supervisor.state.snapshot()['active_user']=='father'
    finally:
        released.set()
        supervisor.worker.join(3)
    assert supervisor.active is None
    assert supervisor.state.snapshot()['session_state']=='standby'


def test_control_api_requires_token_and_valid_parent(tmp_path):
    config=replace(Config(),control_token='test-control-token')
    supervisor=Mock()
    supervisor.start.side_effect=ValueError('unknown_user')
    supervisor.close.return_value=True
    server=ThreadingHTTPServer(('127.0.0.1',0),make_http_handler(Mock(directory=tmp_path),RuntimeState(),supervisor,config))
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    base=f'http://127.0.0.1:{server.server_port}'
    try:
        req=Request(base+'/session/start',data=b'{"user_id":"father"}',method='POST')
        with pytest.raises(HTTPError) as exc:urlopen(req)
        assert exc.value.code==403
        supervisor.start.assert_not_called()
        req.add_header('X-EBO-Control-Token','test-control-token')
        with pytest.raises(HTTPError) as exc:urlopen(req)
        assert exc.value.code==400
        assert json.load(exc.value)=={'error':'unknown_user'}
        req=Request(base+'/session/close',data=b'{}',method='POST',headers={'X-EBO-Control-Token':'test-control-token'})
        with urlopen(req) as result:assert json.load(result)['accepted']
        supervisor.close.assert_called_once()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


def test_face_enrollment_uses_chinese_name_local_frigate_and_ascii_filename(tmp_path):
    photo=tmp_path/'private-family-photo.png'
    Image.new('RGB',(20,20)).save(photo)
    requests=[]
    class Response(io.BytesIO):status=200
    def open_mock(req,timeout):
        requests.append(req)
        return Response(b'{"success":false}' if req.full_url.endswith('/create') else b'{"success":true}')
    assert enroll(Config(),'father',[photo],opener=open_mock)==1
    assert requests[0].full_url=='http://frigate:5000/api/faces/%E7%88%B8%E7%88%B8/create'
    assert requests[1].full_url.endswith('/register')
    assert b'name="file"; filename="face.jpg"' in requests[1].data
    assert photo.name.encode() not in requests[1].data


def test_rejected_face_photo_is_reported_and_not_counted(tmp_path):
    photo=tmp_path/'photo.png'
    Image.new('RGB',(20,20)).save(photo)
    class Response(io.BytesIO):status=200
    with pytest.raises(ValueError,match='usable face'):
        enroll(Config(),'mother',[photo],opener=lambda *args,**kwargs:Response(b'{"success":false}'))
