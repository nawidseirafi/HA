import unittest
from datetime import datetime, timedelta, timezone

from backend.agents.mywellness.service import MyWellnessService


class MyWellnessBookingsRefreshTest(unittest.TestCase):
    def test_bookings_refreshes_live_data_by_default(self):
        service = MyWellnessService.__new__(MyWellnessService)
        writes = []

        service._db_live_cache_ttl = timedelta(minutes=15)
        service._read_status = lambda: {}
        service._write_status = writes.append
        service._courses_from_db_cache = lambda max_age=None: [
            {"id": "course-1", "title": "Alter Kurs", "is_participant": True}
        ]
        service._fetch_courses = lambda force_refresh=False: [
            {"id": "course-1", "title": "Alter Kurs", "is_participant": False}
        ]

        result = service.bookings()

        self.assertEqual(result["bookings"], [])
        self.assertEqual(writes[-1]["current_bookings"], [])
        self.assertIsNone(writes[-1]["last_error"])

    def test_bookings_can_use_cache_when_refresh_is_disabled(self):
        service = MyWellnessService.__new__(MyWellnessService)
        updated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

        service._db_live_cache_ttl = timedelta(minutes=15)
        service._read_status = lambda: {}
        service._write_status = lambda state: None
        service._courses_from_db_cache = lambda max_age=None: [
            {"id": "course-1", "title": "Frischer Kurs", "is_participant": True, "updated_at": updated_at}
        ]
        service._fetch_courses = lambda force_refresh=False: self.fail("Live refresh should not run")

        result = service.bookings(force_refresh=False)

        self.assertEqual([item["id"] for item in result["bookings"]], ["course-1"])

    def test_stale_cache_is_ignored_when_refresh_is_disabled(self):
        service = MyWellnessService.__new__(MyWellnessService)

        service._db_live_cache_ttl = timedelta(minutes=15)
        service._read_status = lambda: {}
        service._write_status = lambda state: None
        service._courses_from_db_cache = lambda max_age=None: []
        service._fetch_courses = lambda force_refresh=False: [
            {"id": "course-1", "title": "Aktueller Kurs", "is_participant": False}
        ]

        result = service.bookings(force_refresh=False)

        self.assertEqual(result["bookings"], [])


if __name__ == "__main__":
    unittest.main()
