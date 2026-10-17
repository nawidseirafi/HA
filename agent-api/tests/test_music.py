import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from pydantic import ValidationError
from backend.agents.music.engine import render
from backend.agents.music.protocol import Frame
from backend.agents.music.session import MusicSession, matches
from backend.agents.music.store import Store

class FakeBackend:
    def __init__(self):
        self.states = {'light.one': {'state': 'on', 'attributes': {'brightness': 100, 'hs_color': [30, 65], 'color_mode': 'hs', 'supported_color_modes': ['hs']}}, 'light.two': {'state': 'off', 'attributes': {'supported_color_modes': ['brightness']}}, 'media_player.sonos': {'state': 'playing', 'attributes': {}}}
        self.calls = []
        self.fail = False
    def state(self, entity):
        if self.fail: raise RuntimeError('offline')
        return copy.deepcopy(self.states[entity])
    def apply(self, entity, payload):
        self.calls.append(('apply', entity, copy.deepcopy(payload)))
        self.states[entity]['state'] = 'on'
        self.states[entity]['attributes'].update({k: v for k, v in payload.items() if k != 'transition'})
    def restore(self, entity, state):
        if self.fail: raise RuntimeError('offline')
        self.calls.append(('restore', entity, state))
        self.states[entity] = copy.deepcopy(state)

class MusicTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.clock = 100.
        self.backend = FakeBackend()
        self.store = Store(Path(directory.name))
        self.music = MusicSession(self.backend, self.store, lambda: self.clock)
        self.music.configure({'lights': ['light.one'], 'player': 'media_player.sonos'})
    def start(self):
        self.music.start()
        return self.frame()
    def frame(self, seq=0):
        frame = Frame(session=self.music.session, seq=seq, bass=.8, mid=.4, high=.2, level=.5, beat=True)
        self.music.receive(frame)
        return frame
    def test_engine(self):
        frame = self.start()
        first, smooth = render(frame, 'ambient', .5)
        self.assertEqual((first, smooth), render(frame, 'ambient', .5))
        self.assertNotEqual(first, render(frame, 'party', .5)[0])
        self.assertTrue(20 <= first['brightness'] <= 200)
    def test_schema(self):
        good = self.start().model_dump()
        for data in ({'bass': float('nan')}, {'high': 2}, {'audio': 'raw'}, {'seq': -1}):
            with self.assertRaises(ValidationError): Frame.model_validate({**good, **data})

    def test_party_responds_to_low_room_audio_without_clipping(self):
        frame = self.start().model_copy(update={'bass': .18, 'mid': .08, 'high': .04, 'level': .1, 'beat': False})
        ambient, _ = render(frame, 'ambient', 1)
        party, smooth = render(frame, 'party', 1)
        self.assertGreater(party['brightness'], ambient['brightness'] + 30)
        louder = frame.model_copy(update={'bass': .3, 'mid': .15, 'high': .08})
        brighter, _ = render(louder, 'party', 1, smooth)
        self.assertGreater(brighter['brightness'], party['brightness'] + 20)
        self.assertLess(brighter['brightness'], 200)

    def test_profile_intensity_silence_and_output_limits(self):
        frame = self.start()
        for profile in ('ambient', 'dynamic', 'party'):
            silence = frame.model_copy(update={'bass': 0, 'mid': 0, 'high': 0, 'level': 0, 'beat': True})
            self.assertEqual(render(silence, profile, 1)[0]['brightness'], 20)
            self.assertEqual(render(frame, profile, 0)[0]['brightness'], 20)
            for energy in (0, .05, .15, .5, 1):
                sample = frame.model_copy(update={'bass': energy, 'mid': energy, 'high': energy})
                output, _ = render(sample, profile, 1, energy)
                self.assertTrue(20 <= output['brightness'] <= 200)
                self.assertTrue(0 <= output['hs_color'][0] < 360)
                self.assertGreaterEqual(output['transition'], .25)

    def test_party_beat_is_visible_and_ambient_remains_gentle(self):
        frame = self.start().model_copy(update={'bass': .18, 'mid': .08, 'high': .04, 'beat': False})
        beat = frame.model_copy(update={'beat': True})
        self.assertGreaterEqual(render(beat, 'party', 1)[0]['brightness'] - render(frame, 'party', 1)[0]['brightness'], 30)
        self.assertEqual(render(beat, 'ambient', 1), render(frame, 'ambient', 1))
    def test_snapshot_and_idempotent_stop(self):
        original = copy.deepcopy(self.backend.states['light.one'])
        self.start()
        self.assertEqual(self.store.read('journal', {})['light.one']['original'], original)
        self.assertEqual(self.backend.calls, [])
        self.music.tick(); self.music.stop(); self.music.tick()
        self.assertEqual(self.backend.states['light.one'], original)
        self.assertEqual(self.music.phase, 'idle')
        self.assertEqual(self.store.read('journal', {}), {})
        self.music.stop(); self.music.tick()
        self.assertEqual(len(self.backend.calls), 2)
    def test_rate(self):
        self.start(); self.music.tick(); self.clock += .1; self.frame(1); self.music.tick()
        self.assertEqual(len(self.backend.calls), 1)
        self.clock += .4; self.music.tick()
        self.assertEqual(len(self.backend.calls), 2)
    def test_sequence_and_ownership(self):
        frame = self.start()
        with self.assertRaises(ValueError): self.music.receive(frame)
        with self.assertRaises(ValueError): self.music.receive(frame.model_copy(update={'seq': 1, 'session': 'x' * 24}))
        with self.assertRaises(ValueError): self.music.start()
    def test_manual_release(self):
        self.start(); self.music.tick(); self.music.release(['light.one'])
        self.backend.states['light.one']['attributes']['brightness'] = 240
        self.music.tick()
        self.assertEqual(len(self.backend.calls), 1)
        self.assertEqual(self.backend.states['light.one']['attributes']['brightness'], 240)
    def test_external_change(self):
        self.start(); self.music.tick()
        self.backend.states['light.one']['state'] = 'off'
        self.clock += .6; self.frame(1); self.music.tick(); self.music.stop(); self.music.tick()
        self.assertEqual(len(self.backend.calls), 1)
        self.assertEqual(self.backend.states['light.one']['state'], 'off')
    def test_watchdog_and_player_pause(self):
        self.start(); self.music.tick(); self.clock += 4; self.music.tick()
        self.assertEqual(self.music.phase, 'idle')
        self.assertEqual(self.music.reason, 'audio_timeout')
        self.start(); self.backend.states['media_player.sonos']['state'] = 'paused'
        self.clock += 2; self.music.tick()
        self.assertEqual(self.music.phase, 'idle')
        self.assertEqual(self.music.reason, 'player_paused')
    def test_recovery(self):
        self.start(); self.music.tick(); self.backend.fail = True
        self.music.stop(); self.music.tick()
        self.assertEqual(self.music.phase, 'recovery_pending')
        restarted = MusicSession(self.backend, self.store, lambda: self.clock)
        self.assertEqual(restarted.phase, 'recovery_pending')
        restarted.tick()
        self.assertEqual(len(self.backend.calls), 1)
        self.backend.fail = False
        restarted.recover(); restarted.tick()
        self.assertEqual(restarted.phase, 'idle')
        self.assertEqual(self.backend.calls[-1][0], 'restore')
    def test_validation_and_monitor(self):
        self.music.configure({'lights': [], 'player': ''})
        with self.assertRaises(ValueError): self.music.start()
        with self.assertRaises(ValueError): self.music.configure({'lights': ['switch.bad']})
        self.music.configure({'lights': ['light.one'], 'player': 'media_player.sonos'})
        with patch.dict('os.environ', {'ROBOTERSTEVE_MONITOR_ONLY': '1'}):
            with self.assertRaises(ValueError): self.music.start()
        self.assertEqual(self.backend.calls, [])
    def test_incomplete_snapshot(self):
        self.music.configure({'lights': ['light.one', 'light.missing'], 'player': 'media_player.sonos'})
        with self.assertRaises(KeyError): self.music.start()
        self.assertEqual(self.backend.calls, [])
        self.assertEqual(self.store.read('journal', {}), {})
    def test_dimmable(self):
        self.music.configure({'lights': ['light.two'], 'player': 'media_player.sonos'})
        self.start(); self.music.tick()
        self.assertNotIn('hs_color', self.backend.calls[0][2])

    def test_beat_between_light_ticks_is_consumed_once(self):
        self.music.configure({'lights': ['light.one'], 'player': 'media_player.sonos', 'profile': 'party', 'intensity': 1})
        beat = self.start()
        quiet = beat.model_copy(update={'seq': 1, 'beat': False})
        self.music.receive(quiet)
        self.music.tick()
        expected, smooth = render(beat, 'party', 1)
        self.assertEqual(self.backend.calls[-1][2], expected)
        self.clock += .6
        self.music.receive(quiet.model_copy(update={'seq': 2}))
        self.music.tick()
        self.assertEqual(self.backend.calls[-1][2], render(quiet, 'party', 1, smooth)[0])
        telemetry = self.music.status()['telemetry']
        self.assertEqual(telemetry['commands'], 2)
        self.assertEqual(telemetry['audio_seq'], 2)
        self.assertEqual(telemetry['last_command']['brightness'], self.backend.calls[-1][2]['brightness'])

    def test_failed_command_not_counted_as_success(self):
        self.start()
        with patch.object(self.backend, 'apply', side_effect=RuntimeError('offline')):
            self.music.tick()
        self.assertEqual(self.music.status()['telemetry']['commands'], 0)
        self.assertIsNone(self.music.status()['telemetry']['last_command'])

    def test_off_hue_with_null_attributes_can_start_and_restore(self):
        light = self.backend.states['light.one']
        light.update(state='off')
        light['attributes'].update(brightness=None, hs_color=None)
        original = copy.deepcopy(light)
        self.start(); self.music.tick()
        self.assertEqual(self.music.phase, 'running')
        self.assertEqual(self.backend.calls[0][0], 'apply')
        self.assertEqual(self.music.released, [])
        self.music.stop(); self.music.tick()
        self.assertEqual(self.backend.states['light.one'], original)

    def test_null_color_is_not_a_manual_change(self):
        state = {'state': 'on', 'attributes': {'brightness': 100, 'hs_color': None}}
        self.assertTrue(matches(state, copy.deepcopy(state)))
        self.assertFalse(matches({'state': 'off'}, state))

    def test_delayed_echo_waits_without_more_writes_then_resumes(self):
        previous = copy.deepcopy(self.backend.states['light.one'])
        self.start(); self.music.tick()
        applied = copy.deepcopy(self.backend.states['light.one'])
        self.backend.states['light.one'] = previous
        self.clock += .6; self.frame(1); self.music.tick()
        self.assertEqual(len(self.backend.calls), 1)
        self.assertEqual(self.music.released, [])
        self.backend.states['light.one'] = applied
        self.clock += .6; self.frame(2); self.music.tick()
        self.assertEqual(len(self.backend.calls), 2)
        self.assertEqual(self.music.phase, 'running')

    def test_missing_echo_releases_after_bounded_wait(self):
        previous = copy.deepcopy(self.backend.states['light.one'])
        self.start(); self.music.tick()
        self.backend.states['light.one'] = previous
        self.clock += 2.1; self.frame(1); self.music.tick()
        self.assertEqual(self.music.reason, 'manual_override')
        self.assertEqual(len(self.backend.calls), 1)

    def test_explicit_release_bypasses_echo_wait(self):
        self.start(); self.music.tick()
        self.music.release(['light.one'])
        self.assertEqual(self.music.reason, 'manual_override')
        self.assertEqual(self.music.pending_since, {})

class MusicIntegrationTests(unittest.TestCase):
    def test_manual_wall_command_waits_for_release(self):
        from backend.api.homeassistant_routes import ServicePayload, call_homeassistant_service
        events = []
        with patch('backend.agents.music.service.music_service.release', side_effect=lambda ids: events.append(('release', ids))), patch('backend.api.homeassistant_routes.ha_service.call_service', side_effect=lambda *args: events.append(('ha', args)) or {'ok': True}):
            call_homeassistant_service(ServicePayload(domain='light', service='turn_off', entity_id=['light.one']))
        self.assertEqual([e[0] for e in events], ['release', 'ha'])
    def test_failed_release_does_not_race_manual_command(self):
        from backend.api.homeassistant_routes import ServicePayload, call_homeassistant_service
        from fastapi import HTTPException
        with patch('backend.agents.music.service.music_service.release', side_effect=RuntimeError('busy')), patch('backend.api.homeassistant_routes.ha_service.call_service') as command:
            with self.assertRaises(HTTPException):
                call_homeassistant_service(ServicePayload(domain='light', service='turn_off', entity_id='light.one'))
            command.assert_not_called()
    def test_update_refuses_outstanding_light_ownership(self):
        from backend.services.update_service import UpdateService
        with patch('backend.agents.music.store.Store.read', return_value={'light.one': {}}):
            with self.assertRaisesRegex(RuntimeError, 'Musiklicht'):
                UpdateService.install_update(object())

class MusicDiagnosticTests(unittest.TestCase):
    def test_network_diagnostic_has_code_but_no_sensitive_message(self):
        import errno
        import socket
        from backend.agents.music.session import failure_detail
        for exc, code in [(OSError(errno.ECONNREFUSED, 'secret URL/token'), 'ECONNREFUSED'),
                          (socket.gaierror(socket.EAI_NONAME, 'secret hostname'), 'EAI_NONAME')]:
            outer = RuntimeError('secret configuration')
            outer.__cause__ = exc
            detail = failure_detail(outer)
            self.assertIn(code, detail)
            self.assertNotIn('secret', detail)
