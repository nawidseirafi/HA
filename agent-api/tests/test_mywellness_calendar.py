from backend.agents.mywellness.calendar_service import add_course_to_calendar


class FakeHomeAssistant:
    def __init__(self, events=None):
        self.events = events or []
        self.calls = []

    def get_calendar_events(self, entity_id, start, end):
        self.last_window = {"entity_id": entity_id, "start": start, "end": end}
        return self.events

    def call_service(self, domain, service, payload):
        self.calls.append({"domain": domain, "service": service, "payload": payload})
        return {"ok": True}


def test_add_course_to_calendar_creates_homeassistant_event():
    ha = FakeHomeAssistant()

    result = add_course_to_calendar(
        {
            "title": "Body Workout",
            "startTime": "2026-06-23T18:00:00",
            "endTime": "2026-06-23T19:00:00",
            "studio": "MyWellness",
        },
        ha,
        calendar_entity="calendar.devcal",
    )

    assert result["ok"] is True
    assert result["skipped"] is False
    assert ha.calls == [
        {
            "domain": "calendar",
            "service": "create_event",
            "payload": {
                "entity_id": "calendar.devcal",
                "summary": "Body Workout",
                "start_date_time": "2026-06-23T18:00",
                "end_date_time": "2026-06-23T19:00",
                "description": "Automatisch eingetragen nach MyWellness-Buchung.",
                "location": "MyWellness",
            },
        }
    ]


def test_add_course_to_calendar_skips_existing_event():
    ha = FakeHomeAssistant(events=[
        {"summary": "Body Workout", "start": {"dateTime": "2026-06-23T18:00:00"}},
    ])

    result = add_course_to_calendar(
        {"title": "Body Workout", "startTime": "2026-06-23T18:00:00", "endTime": "2026-06-23T19:00:00"},
        ha,
        calendar_entity="devcal",
    )

    assert result == {"ok": True, "skipped": True, "reason": "already_exists", "entity_id": "calendar.devcal"}
    assert ha.calls == []


def test_add_course_to_calendar_skips_course_without_start_time():
    ha = FakeHomeAssistant()

    result = add_course_to_calendar({"title": "Body Workout"}, ha, calendar_entity="calendar.devcal")

    assert result == {"ok": False, "skipped": True, "reason": "missing_start_time", "entity_id": "calendar.devcal"}
    assert ha.calls == []
