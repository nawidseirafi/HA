import time
import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from backend.agents.music import routes

SESSION = 's' * 24

class MusicWebSocketTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(routes.router)
        self.client = TestClient(app)
        routes._tickets.clear()
        routes._connections.clear()
        self.calls = []
        def runtime(method, path, payload=None):
            self.calls.append((method, path, payload))
            return {'session': SESSION, 'status': 'preparing'} if path == '/status' else {'ok': True}
        for target, replacement in [('runtime_request', runtime), ('verify_token', lambda token: {'sub': 'owner'}), ('enforce_presence_reauth', lambda payload: None)]:
            patcher = patch.object(routes, target, replacement)
            patcher.start(); self.addCleanup(patcher.stop)
        patcher = patch.dict('os.environ', {'MUSIC_ALLOWED_ORIGIN': 'https://ai-agent.local', 'ROBOTERSTEVE_MONITOR_ONLY': '0'})
        patcher.start(); self.addCleanup(patcher.stop)
    def ticket(self):
        response = self.client.post('/api/music/ticket', headers={'Authorization': 'Bearer fake'})
        self.assertEqual(response.status_code, 200)
        return response.json()['ticket']
    def test_cross_origin_and_monitor_rejected(self):
        for origin in ('https://evil.example', ''):
            with self.assertRaises(WebSocketDisconnect):
                with self.client.websocket_connect('/api/music/audio', headers={'origin': origin}): pass
        with patch.dict('os.environ', {'ROBOTERSTEVE_MONITOR_ONLY': '1'}):
            with self.assertRaises(WebSocketDisconnect):
                with self.client.websocket_connect('/api/music/audio', headers={'origin': 'https://ai-agent.local'}): pass
    def test_ticket_single_use_and_disconnect_stops(self):
        ticket = self.ticket()
        with self.client.websocket_connect('/api/music/audio', headers={'origin': 'https://ai-agent.local'}) as ws:
            ws.send_json({'ticket': ticket, 'session': SESSION})
            self.assertEqual(ws.receive_json(), {'ready': True})
            ws.send_json({'version': 1, 'session': SESSION, 'seq': 0, 'bass': .5, 'mid': .3, 'high': .1, 'level': .3})
        self.assertTrue(any(path == '/command/stop' for _, path, _ in self.calls))
        with self.client.websocket_connect('/api/music/audio', headers={'origin': 'https://ai-agent.local'}) as ws:
            ws.send_json({'ticket': ticket, 'session': SESSION})
            with self.assertRaises(WebSocketDisconnect): ws.receive_json()
    def test_expired_ticket_and_malformed_handshake(self):
        ticket = self.ticket()
        routes._tickets[ticket] = (time.monotonic() - 1, 'fake')
        for hello in ({'ticket': ticket, 'session': SESSION}, [], {'ticket': []}):
            with self.client.websocket_connect('/api/music/audio', headers={'origin': 'https://ai-agent.local'}) as ws:
                ws.send_json(hello)
                with self.assertRaises(WebSocketDisconnect): ws.receive_json()
        self.assertFalse(any(path == '/command/stop' for _, path, _ in self.calls))
    def test_audio_payload_rejected(self):
        with self.client.websocket_connect('/api/music/audio', headers={'origin': 'https://ai-agent.local'}) as ws:
            ws.send_json({'ticket': self.ticket(), 'session': SESSION})
            ws.receive_json()
            ws.send_json({'session': SESSION, 'audio': 'base64'})
            with self.assertRaises(WebSocketDisconnect): ws.receive_json()
        self.assertFalse(any(path == '/frame' for _, path, _ in self.calls))
    def test_second_connection_cannot_stop_owner(self):
        routes._connections.add(SESSION)
        with self.client.websocket_connect('/api/music/audio', headers={'origin': 'https://ai-agent.local'}) as ws:
            ws.send_json({'ticket': self.ticket(), 'session': SESSION})
            with self.assertRaises(WebSocketDisconnect): ws.receive_json()
        self.assertFalse(any(path == '/command/stop' for _, path, _ in self.calls))

class MusicRuntimeTests(unittest.TestCase):
    def test_old_disconnect_cannot_stop_new_session(self):
        from unittest.mock import Mock
        from backend.agents.music.runtime import create_app
        session = Mock()
        session.session = 'new-session'
        session.stop.return_value = {'status': 'stopping'}
        session.status.return_value = {'status': 'running', 'session': 'new-session'}
        with TestClient(create_app(session)) as client:
            response = client.post('/command/stop', json={'session': 'old-session'})
            self.assertEqual(response.status_code, 200)
            session.stop.assert_not_called()
            client.post('/command/stop', json={'session': 'new-session'})
            session.stop.assert_called_once_with('manual')
