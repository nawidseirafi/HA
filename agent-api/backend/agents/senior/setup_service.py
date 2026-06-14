from __future__ import annotations

import json
from typing import Any
from .device_mapping_service import DeviceMappingService, now

ROOMS = ['living_room', 'kitchen', 'bathroom', 'bedroom', 'hallway', 'entrance']

class SeniorSetupService:
    def __init__(self, mapping: DeviceMappingService) -> None:
        self.mapping = mapping

    def status(self) -> dict[str, Any]:
        with self.mapping.connect() as con:
            row = con.execute('select * from setup_state where id = 1').fetchone()
            profile = con.execute('select * from senior_profile where id = 1').fetchone()
            contacts = con.execute('select * from trusted_contacts where active = 1 order by id').fetchall()
            notifications = con.execute('select * from notification_preferences where id = 1').fetchone()
        profile_data = dict(profile) if profile else None
        contact_data = [dict(contact) for contact in contacts]
        notification_data = dict(notifications) if notifications else None
        return {
            'current_step': row['current_step'],
            'completed_steps': json.loads(row['completed_steps'] or '[]'),
            'selected_rooms': json.loads(row['selected_rooms_json'] or '[]'),
            'is_complete': bool(row['is_complete']),
            'home': self.mapping.home_status(),
            'has_profile': bool(profile),
            'profile': profile_data,
            'trusted_contacts_count': len(contact_data),
            'trusted_contacts': contact_data,
            'notifications': notification_data,
            'sensor_roles': self.mapping.roles(include_state=True),
            'updated_at': row['updated_at'],
        }

    def set_step(self, current_step: str, completed_step: str | None = None, complete: bool | None = None) -> dict[str, Any]:
        with self.mapping.connect() as con:
            row = con.execute('select completed_steps from setup_state where id = 1').fetchone()
            completed = set(json.loads(row['completed_steps'] or '[]')) if row else set()
            if completed_step:
                completed.add(completed_step)
            con.execute('update setup_state set current_step = ?, completed_steps = ?, is_complete = coalesce(?, is_complete), updated_at = ? where id = 1', (current_step, json.dumps(sorted(completed)), None if complete is None else int(complete), now()))
            con.commit()
        return self.status()

    def profile(self, payload: dict[str, Any]) -> dict[str, Any]:
        timestamp = now()
        with self.mapping.connect() as con:
            con.execute('''insert into senior_profile (id, name, age, notes, created_at, updated_at) values (1, ?, ?, ?, ?, ?) on conflict(id) do update set name = excluded.name, age = excluded.age, notes = excluded.notes, updated_at = excluded.updated_at''', (payload.get('name'), payload.get('age'), payload.get('notes'), timestamp, timestamp))
            con.commit()
        return self.set_step('prepare_home', 'profile')

    def rooms(self, rooms: list[str]) -> dict[str, Any]:
        clean_rooms = []
        for room in rooms:
            value = str(room or '').strip()
            if value and value not in clean_rooms:
                clean_rooms.append(value[:80])
        with self.mapping.connect() as con:
            con.execute('update setup_state set selected_rooms_json = ?, updated_at = ? where id = 1', (json.dumps(clean_rooms), now()))
            con.commit()
        return self.set_step('sensors', 'rooms')

    def sensors(self) -> dict[str, Any]:
        return self.set_step('contacts', 'sensors')

    def contact(self, payload: dict[str, Any]) -> dict[str, Any]:
        timestamp = now()
        with self.mapping.connect() as con:
            con.execute('insert into trusted_contacts (name, relationship, email, active, created_at, updated_at) values (?, ?, ?, 1, ?, ?)', (payload.get('name'), payload.get('relationship'), payload.get('email'), timestamp, timestamp))
            con.commit()
        return self.set_step('notifications', 'contacts')

    def delete_contact(self, contact_id: int) -> dict[str, Any]:
        with self.mapping.connect() as con:
            con.execute('update trusted_contacts set active = 0, updated_at = ? where id = ?', (now(), contact_id))
            con.commit()
        return self.status()

    def notifications(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.mapping.connect() as con:
            con.execute('''insert into notification_preferences (id, anomalies, critical, daily_summary, updated_at) values (1, ?, ?, ?, ?) on conflict(id) do update set anomalies = excluded.anomalies, critical = excluded.critical, daily_summary = excluded.daily_summary, updated_at = excluded.updated_at''', (int(bool(payload.get('anomalies', True))), int(bool(payload.get('critical', True))), int(bool(payload.get('daily_summary', False))), now()))
            con.commit()
        return self.set_step('complete', 'notifications')
