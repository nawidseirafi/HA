from __future__ import annotations

import json
import logging
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.paths import API_DIR
from backend.services.homeassistant_service import HomeAssistantService

DB_PATH = API_DIR / 'data' / 'senior' / 'seniorcare.db'
DISCOVERY_TIMEOUT_SECONDS = 30
DISCOVERY_CONFIDENCE_THRESHOLD = 50
PRESENCE_CLASSES = {'occupancy', 'motion', 'presence'}
CONTACT_CLASSES = {'door', 'window', 'opening', 'contact'}
logger = logging.getLogger(__name__)
ROOM_TERMS = {
    'living_room': ['wohnzimmer', 'living'],
    'kitchen': ['kueche', 'küche', 'kitchen'],
    'bathroom': ['bad', 'bathroom', 'wc'],
    'bedroom': ['schlafzimmer', 'bedroom'],
    'hallway': ['flur', 'hallway', 'diele'],
    'entrance': ['eingang', 'tuer', 'tür', 'door', 'front'],
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


class DeviceMappingService:
    def __init__(self, database_path: Path | None = None, ha: HomeAssistantService | None = None) -> None:
        self.database_path = database_path or DB_PATH
        self.ha = ha or HomeAssistantService()
        self.ensure_schema()

    def connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(self.database_path)
        con.row_factory = sqlite3.Row
        return con

    def ensure_schema(self) -> None:
        with self.connect() as con:
            ensure_schema(con)
            con.commit()

    def home_status(self) -> dict[str, bool]:
        if not self.ha.configured():
            return {'connected': False, 'sensor_ready': False, 'system_ready': False}
        try:
            states = self.ha.get_states()
        except Exception:
            return {'connected': False, 'sensor_ready': False, 'system_ready': False}
        return {'connected': True, 'sensor_ready': isinstance(states, list), 'system_ready': True}

    def roles(self, dev: bool = False, include_state: bool = False) -> list[dict[str, Any]]:
        with self.connect() as con:
            rows = con.execute('select * from sensor_roles where active = 1 order by room, role').fetchall()
        valid_rows = [dict(row) for row in rows if role_candidate_matches(str(row['role'] or ''), dict(row), allow_missing_device_class=True)]
        if include_state:
            valid_rows = self._attach_state(valid_rows)
        return valid_rows if dev else [public_role(row) for row in valid_rows]

    def get_entity_for_role(self, role: str) -> str | None:
        with self.connect() as con:
            rows = con.execute('select * from sensor_roles where role = ? and active = 1 order by id desc', (role,)).fetchall()
        for row in rows:
            data = dict(row)
            if role_candidate_matches(role, data, allow_missing_device_class=True):
                return data['entity_id']
        return None

    def start_pairing(self, role: str, room: str | None, pairing_code: str | None = None) -> dict[str, Any]:
        ha_url = getattr(self.ha, 'base_url', '')
        try:
            baseline = self.snapshot()
            ha_reachable = True
        except Exception:
            logger.exception("SeniorCare discovery baseline failed. ha_url=%s reachable=no", ha_url)
            raise
        started_at = now()
        has_pairing_code = bool(str(pairing_code or '').strip())
        status = 'waiting_for_signal'
        message = 'Bitte aktivieren Sie den Sensor jetzt einmal.'
        detail = None
        if has_pairing_code:
            status = 'pairing_started'
            message = 'Kopplung gestartet. Bitte aktivieren Sie den Sensor danach einmal.'
            detail = self._try_matter_pairing(pairing_code)
            if detail and not detail.get('ok'):
                status = 'pairing_needs_manual_action'
                message = 'Der Sensor konnte nicht verbunden werden. Bitte erneut versuchen.'
        with self.connect() as con:
            cur = con.execute(
                '''insert into sensor_discovery_sessions
                   (target_role, target_room, started_at, status, baseline_snapshot_json, pairing_code_provided, pairing_detail_json)
                   values (?, ?, ?, ?, ?, ?, ?)''',
                (role, room, started_at, status, json.dumps(baseline, ensure_ascii=False), int(has_pairing_code), json.dumps(detail, ensure_ascii=False) if detail else None),
            )
            con.commit()
            session_id = int(cur.lastrowid)
        logger.info(
            "SeniorCare discovery start session=%s role=%s room=%s ha_url=%s reachable=%s baseline_states=%s status=%s",
            session_id,
            role,
            room,
            ha_url,
            "yes" if ha_reachable else "no",
            len(baseline),
            status,
        )
        return {'session_id': session_id, 'status': status, 'message': message, 'detail': detail}

    def start_zigbee_pairing(self, role: str, room: str | None, duration: int = 60) -> dict[str, Any]:
        ha_url = getattr(self.ha, 'base_url', '')
        duration = min(max(int(duration or 60), 10), 300)
        try:
            baseline = self.snapshot()
            ha_reachable = True
        except Exception:
            logger.exception("SeniorCare Zigbee pairing baseline failed. ha_url=%s reachable=no", ha_url)
            raise
        detail = self._open_zigbee_permit_join(duration)
        status = 'pairing_started' if detail.get('ok') else 'pairing_needs_manual_action'
        message = (
            'Sensor-Suche gestartet. Bitte aktivieren Sie den Sensor jetzt.'
            if detail.get('ok')
            else 'Die Sensor-Einrichtung ist noch nicht bereit.'
        )
        with self.connect() as con:
            cur = con.execute(
                '''insert into sensor_discovery_sessions
                   (target_role, target_room, started_at, status, baseline_snapshot_json, pairing_code_provided, pairing_detail_json)
                   values (?, ?, ?, ?, ?, ?, ?)''',
                (role, room, now(), status, json.dumps(baseline, ensure_ascii=False), 0, json.dumps(detail, ensure_ascii=False)),
            )
            con.commit()
            session_id = int(cur.lastrowid)
        logger.info(
            "SeniorCare Zigbee pairing start session=%s role=%s room=%s ha_url=%s reachable=%s baseline_states=%s status=%s provider=%s",
            session_id,
            role,
            room,
            ha_url,
            "yes" if ha_reachable else "no",
            len(baseline),
            status,
            detail.get('provider'),
        )
        if not detail.get('ok'):
            logger.warning("SeniorCare Zigbee pairing unavailable session=%s detail=%s", session_id, detail)
        return {'session_id': session_id, 'status': status, 'message': message, 'detail': detail}

    def candidates(self, session_id: int, dev: bool = False) -> dict[str, Any]:
        with self.connect() as con:
            row = con.execute('select * from sensor_discovery_sessions where id = ?', (session_id,)).fetchone()
        if not row:
            raise ValueError('session not found')
        started_at = parse_time(row['started_at'])
        elapsed_seconds = max((datetime.now(timezone.utc) - started_at).total_seconds(), 0)
        if row['status'] == 'pairing_needs_manual_action':
            logger.info(
                "SeniorCare discovery poll session=%s skipped status=pairing_needs_manual_action ha_url=%s",
                session_id,
                getattr(self.ha, 'base_url', ''),
            )
            return {
                'session_id': session_id,
                'status': 'no_signal_detected',
                'message': 'Der Sensor konnte nicht verbunden werden. Bitte erneut versuchen.',
                'candidate': None,
                'candidates': [],
                'elapsed_seconds': elapsed_seconds,
                'remaining_seconds': 0,
            }
        baseline = json.loads(row['baseline_snapshot_json'] or '[]')
        current = self.snapshot()
        scored = score_candidates(baseline, current, row['target_role'], row['target_room'], row['started_at'])
        changed_count = len(scored)
        best_scored = scored[0] if scored else None
        best = best_scored if best_scored and best_scored['confidence'] >= DISCOVERY_CONFIDENCE_THRESHOLD else None
        timed_out = elapsed_seconds >= DISCOVERY_TIMEOUT_SECONDS
        status = 'signal_detected' if best else 'no_signal_detected' if timed_out else 'waiting_for_signal'
        message = (
            'Sensor-Signal erkannt.'
            if best
            else 'Wir konnten den Sensor nicht eindeutig erkennen. Bitte erneut versuchen.'
            if timed_out
            else 'Wir warten noch auf ein eindeutiges Sensorsignal.'
        )
        with self.connect() as con:
            con.execute(
                '''update sensor_discovery_sessions set ended_at = ?, status = ?, candidate_snapshot_json = ? where id = ?''',
                (now() if best or timed_out else None, status, json.dumps(current, ensure_ascii=False), session_id),
            )
            con.commit()
        logger.info(
            "SeniorCare discovery poll session=%s ha_url=%s baseline_states=%s current_states=%s changed_entities=%s best=%s best_score=%s status=%s elapsed=%.1f",
            session_id,
            getattr(self.ha, 'base_url', ''),
            len(baseline),
            len(current),
            changed_count,
            best_scored.get('entity_id') if best_scored else None,
            best_scored.get('confidence') if best_scored else None,
            status,
            elapsed_seconds,
        )
        if scored:
            logger.info(
                "SeniorCare discovery candidates session=%s candidates=%s",
                session_id,
                [
                    {
                        'entity_id': item.get('entity_id'),
                        'score': item.get('confidence'),
                        'reasons': item.get('reasons', []),
                        'device_class': item.get('device_class'),
                        'domain': item.get('domain'),
                    }
                    for item in scored[:5]
                ],
            )
        public_candidates = [candidate_public(item, dev) for item in scored[:5]] if dev else []
        return {
            'session_id': session_id,
            'status': status,
            'message': message,
            'candidate': candidate_public(best, dev) if best else None,
            'candidates': public_candidates,
            'elapsed_seconds': elapsed_seconds,
            'remaining_seconds': max(DISCOVERY_TIMEOUT_SECONDS - elapsed_seconds, 0),
            'changed_count': changed_count if dev else None,
            'current_state_count': len(current) if dev else None,
            'baseline_state_count': len(baseline) if dev else None,
        }

    def confirm(self, session_id: int, entity_id: str, dev: bool = False) -> dict[str, Any]:
        with self.connect() as con:
            session = con.execute('select * from sensor_discovery_sessions where id = ?', (session_id,)).fetchone()
        if not session:
            raise ValueError('session not found')
        current = json.loads(session['candidate_snapshot_json'] or '[]') or self.snapshot()
        entity = next((item for item in current if item.get('entity_id') == entity_id), None)
        if not entity:
            entity = {'entity_id': entity_id, 'domain': entity_id.split('.')[0], 'attributes': {}}
        attrs = entity.get('attributes') or {}
        payload = {
            'role': session['target_role'],
            'room': session['target_room'],
            'entity_id': entity_id,
            'device_id': attrs.get('device_id') or entity.get('device_id'),
            'friendly_name': attrs.get('friendly_name') or entity.get('friendly_name'),
            'device_class': attrs.get('device_class') or entity.get('device_class'),
            'domain': entity_id.split('.')[0],
            'source': 'wizard',
            'confidence': 100,
        }
        role = self.upsert_role(payload)
        with self.connect() as con:
            con.execute('update sensor_discovery_sessions set status = ?, selected_entity_id = ?, ended_at = ? where id = ?', ('confirmed', entity_id, now(), session_id))
            con.commit()
        return {'status': 'confirmed', 'role': role if dev else public_role(role)}

    def upsert_role(self, data: dict[str, Any]) -> dict[str, Any]:
        role = str(data.get('role') or '').strip()
        entity_id = str(data.get('entity_id') or '').strip()
        if not role or not entity_id:
            raise ValueError('role and entity_id required')
        domain = str(data.get('domain') or entity_id.split('.')[0] if '.' in entity_id else '').strip()
        data = {**data, 'domain': domain}
        if not role_candidate_matches(role, data):
            raise ValueError('entity does not match expected sensor class for role')
        timestamp = now()
        with self.connect() as con:
            con.execute('update sensor_roles set active = 0, updated_at = ? where role = ?', (timestamp, role))
            con.execute(
                '''insert into sensor_roles
                   (role, room, entity_id, device_id, friendly_name, device_class, domain, source, confidence, active, created_at, updated_at)
                   values (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)''',
                (role, data.get('room'), entity_id, data.get('device_id'), data.get('friendly_name'), data.get('device_class'), data.get('domain'), data.get('source'), float(data.get('confidence') or 0), timestamp, timestamp),
            )
            con.commit()
        return self.get_role(role, dev=True) or {}

    def get_role(self, role: str, dev: bool = False) -> dict[str, Any] | None:
        with self.connect() as con:
            row = con.execute('select * from sensor_roles where role = ? and active = 1 limit 1', (role,)).fetchone()
        if not row:
            return None
        data = dict(row)
        return data if dev else public_role(data)

    def delete_role(self, role: str) -> dict[str, Any]:
        with self.connect() as con:
            con.execute('update sensor_roles set active = 0, updated_at = ? where role = ?', (now(), role))
            con.commit()
        return {'deleted': True, 'role': role}

    def _attach_state(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        try:
            states = self.ha.get_states()
        except Exception:
            logger.exception("SeniorCare sensor state refresh failed. ha_url=%s", getattr(self.ha, 'base_url', ''))
            return [{**row, 'reachable': False, 'state': None, 'last_changed': None, 'last_updated': None, 'battery_level': None} for row in rows]
        by_entity = {str(item.get('entity_id') or ''): item for item in states}
        result = []
        for row in rows:
            entity_id = str(row.get('entity_id') or '')
            state = by_entity.get(entity_id)
            attrs = state.get('attributes') if state else {}
            value = state.get('state') if state else None
            reachable = bool(state and value not in {None, '', 'unknown', 'unavailable'})
            result.append({
                **row,
                'state': value,
                'reachable': reachable,
                'last_changed': state.get('last_changed') if state else None,
                'last_updated': state.get('last_updated') if state else None,
                'battery_level': find_battery_level(row, states, attrs or {}),
            })
        return result

    def snapshot(self) -> list[dict[str, Any]]:
        states = self.ha.get_states()
        result = []
        for item in states:
            entity_id = str(item.get('entity_id') or '')
            attrs = item.get('attributes') or {}
            result.append({
                'entity_id': entity_id,
                'domain': entity_id.split('.')[0] if '.' in entity_id else '',
                'state': item.get('state'),
                'friendly_name': attrs.get('friendly_name'),
                'device_class': attrs.get('device_class'),
                'last_changed': item.get('last_changed'),
                'last_updated': item.get('last_updated'),
            })
        return result

    def _try_matter_pairing(self, pairing_code: str) -> dict[str, Any]:
        code = str(pairing_code or '').strip().replace(' ', '')
        if not code:
            return {'ok': False, 'reason': 'missing_code'}
        try:
            response = self.ha.websocket_command({'type': 'matter/commission_with_code', 'code': code}, timeout=90)
        except Exception as exc:
            return {'ok': False, 'reason': 'pairing_call_failed', 'error': str(exc)}
        return {'ok': bool(response.get('success', True)), 'response': response}

    def _open_zigbee_permit_join(self, duration: int) -> dict[str, Any]:
        attempts: list[dict[str, Any]] = []
        try:
            response = self.ha.call_service('zha', 'permit', {'duration': duration})
            logger.info("SeniorCare Zigbee permit_join sent provider=zha duration=%s", duration)
            return {'ok': True, 'provider': 'zha', 'duration': duration, 'response': response}
        except Exception as exc:
            attempts.append({'provider': 'zha', 'error': str(exc)})
            logger.info("SeniorCare Zigbee permit_join failed provider=zha error=%s", exc)
        try:
            response = self.ha.call_service(
                'mqtt',
                'publish',
                {
                    'topic': 'zigbee2mqtt/bridge/request/permit_join',
                    'payload': json.dumps({'value': True, 'time': duration}),
                },
            )
            logger.info("SeniorCare Zigbee permit_join sent provider=zigbee2mqtt duration=%s", duration)
            return {'ok': True, 'provider': 'zigbee2mqtt', 'duration': duration, 'response': response, 'attempts': attempts}
        except Exception as exc:
            attempts.append({'provider': 'zigbee2mqtt', 'error': str(exc)})
            logger.info("SeniorCare Zigbee permit_join failed provider=zigbee2mqtt error=%s", exc)
        return {'ok': False, 'reason': 'zigbee_pairing_unavailable', 'message': 'Zigbee-Anlernen nicht verfuegbar', 'attempts': attempts}


def ensure_schema(con: sqlite3.Connection) -> None:
    con.execute('''create table if not exists setup_state (id integer primary key check (id = 1), current_step text not null default 'welcome', completed_steps text not null default '[]', is_complete integer not null default 0, updated_at text not null)''')
    try:
        con.execute("alter table setup_state add column selected_rooms_json text not null default '[]'")
    except sqlite3.OperationalError:
        pass
    con.execute('''create table if not exists senior_profile (id integer primary key check (id = 1), name text, age integer, notes text, created_at text not null, updated_at text not null)''')
    con.execute('''create table if not exists trusted_contacts (id integer primary key autoincrement, name text not null, relationship text, email text, active integer not null default 1, created_at text not null, updated_at text not null)''')
    con.execute('''create table if not exists notification_preferences (id integer primary key check (id = 1), anomalies integer not null default 1, critical integer not null default 1, daily_summary integer not null default 0, updated_at text not null)''')
    con.execute('''create table if not exists sensor_roles (id integer primary key autoincrement, role text not null, room text, entity_id text not null, device_id text, friendly_name text, device_class text, domain text, source text, confidence real, active integer not null default 1, created_at text not null, updated_at text not null)''')
    con.execute('create unique index if not exists idx_sensor_roles_active_role on sensor_roles(role) where active = 1')
    con.execute('''create table if not exists sensor_discovery_sessions (id integer primary key autoincrement, target_role text not null, target_room text, started_at text not null, ended_at text, status text not null, baseline_snapshot_json text, candidate_snapshot_json text, selected_entity_id text)''')
    for statement in [
        "alter table sensor_discovery_sessions add column pairing_code_provided integer not null default 0",
        "alter table sensor_discovery_sessions add column pairing_detail_json text",
    ]:
        try:
            con.execute(statement)
        except sqlite3.OperationalError:
            pass
    con.execute('insert or ignore into setup_state (id, updated_at) values (1, ?)', (now(),))
    con.execute('insert or ignore into notification_preferences (id, updated_at) values (1, ?)', (now(),))


def score_candidates(baseline: list[dict[str, Any]], current: list[dict[str, Any]], role: str, room: str | None, started_at: str | datetime) -> list[dict[str, Any]]:
    before = {item.get('entity_id'): item for item in baseline}
    started = parse_time(started_at)
    scored = []
    for item in current:
        entity_id = str(item.get('entity_id') or '')
        if not entity_id:
            continue
        if str(item.get('state') or '').lower() in {'unknown', 'unavailable'}:
            continue
        if not role_candidate_matches(role, item, allow_device_class_mismatch=True):
            continue
        old = before.get(entity_id, {})
        is_new = entity_id not in before
        state_changed = bool(old) and item.get('state') != old.get('state')
        last_changed_updated = is_after(item.get('last_changed'), started)
        last_updated_updated = is_after(item.get('last_updated'), started)
        changed = is_new or state_changed or last_changed_updated or last_updated_updated
        if not changed:
            continue
        confidence = 0
        reasons = []
        if state_changed:
            confidence += 40
            reasons.append('state_changed')
        if last_changed_updated or last_updated_updated:
            confidence += 30
            reasons.append('timestamp_updated')
        if class_matches(role, item.get('device_class')):
            confidence += 25
            reasons.append('device_class_match')
        if room_matches(room, entity_id, item.get('friendly_name')):
            confidence += 20
            reasons.append('room_match')
        if domain_matches(role, item.get('domain')):
            confidence += 10
            reasons.append('domain_match')
        if is_new:
            confidence += 10
            reasons.append('new_entity')
        if confidence:
            scored.append({**item, 'confidence': confidence, 'reasons': reasons, 'is_new': is_new})
    return sorted(scored, key=lambda x: x['confidence'], reverse=True)


def domain_matches(role: str, domain: Any) -> bool:
    if role_is_presence(role) or role_is_contact(role):
        return str(domain or '') == 'binary_sensor'
    return bool(domain)


def parse_time(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or '').strip()
        if text.endswith('Z'):
            text = f'{text[:-1]}+00:00'
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            parsed = datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def is_after(value: Any, threshold: datetime) -> bool:
    if not value:
        return False
    return parse_time(value) > threshold


def role_candidate_matches(role: str, item: dict[str, Any], allow_missing_device_class: bool = False, allow_device_class_mismatch: bool = False) -> bool:
    domain = str(item.get('domain') or '')
    device_class = item.get('device_class')
    has_device_class = bool(str(device_class or '').strip())
    if role_is_presence(role):
        return domain == 'binary_sensor' and (allow_device_class_mismatch or class_matches(role, device_class) or (allow_missing_device_class and not has_device_class))
    if role_is_contact(role):
        return domain == 'binary_sensor' and (allow_device_class_mismatch or class_matches(role, device_class) or (allow_missing_device_class and not has_device_class))
    return domain == 'binary_sensor'


def class_matches(role: str, device_class: Any) -> bool:
    dc = str(device_class or '').lower()
    if role_is_presence(role):
        return dc in PRESENCE_CLASSES
    if role_is_contact(role):
        return dc in CONTACT_CLASSES
    return False


def role_is_presence(role: str) -> bool:
    return str(role or '').endswith(('presence', '_motion'))


def role_is_contact(role: str) -> bool:
    value = str(role or '')
    return value in {'main_door', 'window_contact'} or value.endswith(('_door', '_contact'))


def room_matches(room: str | None, entity_id: str, friendly_name: Any) -> bool:
    if not room:
        return False
    haystack = normalize(f'{entity_id} {friendly_name or ""}')
    return any(normalize(term) in haystack for term in ROOM_TERMS.get(room, [room]))


def normalize(value: str) -> str:
    return re.sub(r'[^a-z0-9_]+', '_', value.lower().replace('ü', 'ue').replace('ä', 'ae').replace('ö', 'oe').replace('ß', 'ss'))


def candidate_public(item: dict[str, Any] | None, dev: bool) -> dict[str, Any] | None:
    if not item:
        return None
    data = {'label': item.get('friendly_name') or 'Sensor erkannt', 'confidence': item.get('confidence', 0), 'score': item.get('confidence', 0), 'entity_id': item.get('entity_id')}
    if dev:
        data.update(item)
    return data


def public_role(data: dict[str, Any]) -> dict[str, Any]:
    return {
        'role': data.get('role'),
        'room': data.get('room'),
        'label': data.get('friendly_name') or data.get('role'),
        'configured': bool(data.get('active')),
        'updated_at': data.get('updated_at'),
        'state': data.get('state'),
        'reachable': data.get('reachable'),
        'last_changed': data.get('last_changed'),
        'last_updated': data.get('last_updated'),
        'battery_level': data.get('battery_level'),
        'device_class': data.get('device_class'),
        'domain': data.get('domain'),
    }


def find_battery_level(role: dict[str, Any], states: list[dict[str, Any]], attrs: dict[str, Any]) -> int | None:
    direct = parse_battery(attrs.get('battery_level') or attrs.get('battery') or attrs.get('battery_percentage'))
    if direct is not None:
        return direct
    device_id = str(role.get('device_id') or '').strip()
    friendly = normalize(str(role.get('friendly_name') or role.get('role') or ''))
    role_entity = str(role.get('entity_id') or '')
    role_prefix = role_entity.rsplit('_', 1)[0] if '_' in role_entity else role_entity
    for state in states:
        entity_id = str(state.get('entity_id') or '')
        state_attrs = state.get('attributes') or {}
        if state_attrs.get('device_class') != 'battery' and not entity_id.startswith('sensor.'):
            continue
        if device_id and state_attrs.get('device_id') == device_id:
            parsed = parse_battery(state.get('state'))
            if parsed is not None:
                return parsed
        haystack = normalize(f"{entity_id} {state_attrs.get('friendly_name') or ''}")
        if friendly and friendly in haystack:
            parsed = parse_battery(state.get('state'))
            if parsed is not None:
                return parsed
        if role_prefix and entity_id.startswith(role_prefix):
            parsed = parse_battery(state.get('state'))
            if parsed is not None:
                return parsed
    return None


def parse_battery(value: Any) -> int | None:
    if value is None:
        return None
    try:
        number = float(str(value).replace('%', '').strip())
    except ValueError:
        return None
    if number < 0 or number > 100:
        return None
    return int(round(number))
