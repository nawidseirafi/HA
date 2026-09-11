import unittest

from backend.api.homeassistant_routes import _wall_household_summary


class WallCalendarTests(unittest.TestCase):
    def test_wall_retains_electrical_sensors_alongside_primary_switch(self):
        from backend.api.homeassistant_routes import _wall_device_groups, _wall_state_is_primary, _simple_item

        for device_id in (None, "washing-machine-plug"):
            states = [{"entity_id": "switch.laundry_room_washing_machine_plug", "state": "on", "attributes": {}}]
            for suffix, device_class, unit, value in [("power", "power", "W", "97"), ("current", "current", "A", "0.63")]:
                states.append({
                    "entity_id": f"sensor.laundry_room_washing_machine_plug_{suffix}",
                    "state": value,
                    "attributes": {"device_class": device_class, "unit_of_measurement": unit},
                })
            if device_id:
                for state in states:
                    state["attributes"]["device_id"] = device_id
            groups = _wall_device_groups(states)
            self.assertTrue(_wall_state_is_primary(states[0], groups, "switch"))
            sensors = [_simple_item(state) for state in states if _wall_state_is_primary(state, groups, "sensor")]
            self.assertEqual([(item["state"], item["unit"]) for item in sensors], [("97", "W"), ("0.63", "A")])

    def test_wall_household_summary_keeps_calendar_events(self):
        calendar = {
            "ok": True,
            "today_count": 1,
            "next_event": {"title": "Zahnarzt", "start": "2026-08-06T15:00:00+02:00"},
            "upcoming": [{"title": "Zahnarzt", "start": "2026-08-06T15:00:00+02:00"}],
            "source": "homeassistant:calendar.devcal",
        }

        summary = _wall_household_summary([], calendar)

        self.assertEqual(summary["calendar"], calendar)
        self.assertEqual(summary["counts"]["calendar_events_today"], 1)
        self.assertEqual(summary["state"]["next_calendar_event"]["title"], "Zahnarzt")

    def test_wall_household_summary_marks_smoke_alarm_critical(self):
        states = [{
            "entity_id": "binary_sensor.flur_rauchmelder",
            "state": "on",
            "attributes": {"friendly_name": "Flur Rauchmelder", "device_class": "smoke"},
            "last_updated": "2026-08-21T07:00:00+00:00",
        }]

        summary = _wall_household_summary(states, {"ok": True, "today_count": 0, "next_event": None, "upcoming": []})

        self.assertFalse(summary["ok"])
        self.assertEqual(summary["safety"]["active_alerts"][0]["name"], "Flur Rauchmelder")
        self.assertTrue(any(item["priority"] == "critical" for item in summary["reminders"]))

    def test_wall_household_summary_links_smoke_detector_test_button(self):
        states = [
            {
                "entity_id": "binary_sensor.flur_rauchmelder",
                "state": "off",
                "attributes": {"friendly_name": "Flur Rauchmelder", "device_class": "smoke"},
                "last_updated": "2026-08-21T07:00:00+00:00",
            },
            {
                "entity_id": "button.flur_test",
                "state": "unknown",
                "attributes": {"friendly_name": "Flur Rauchmelder Test"},
                "last_updated": "2026-08-21T07:00:00+00:00",
            },
        ]

        summary = _wall_household_summary(states, {"ok": True, "today_count": 0, "next_event": None, "upcoming": []})

        self.assertEqual(summary["safety"]["detectors"][0]["test_entity_id"], "button.flur_test")

    def test_wall_smoke_alerts_only_include_smoke_alarm_binary_sensors(self):
        from backend.api.homeassistant_routes import _is_smoke_detector_smoke_item, _safety_item

        states = [
            {
                "entity_id": "binary_sensor.living_room_smoke_detector_smoke",
                "state": "off",
                "attributes": {"friendly_name": "Living Room Smoke Detector Smoke", "device_class": "smoke"},
            },
            {
                "entity_id": "binary_sensor.living_room_smoke_detector_gas",
                "state": "off",
                "attributes": {"friendly_name": "Living Room Smoke Detector Gas", "device_class": "gas"},
            },
            {
                "entity_id": "binary_sensor.living_room_smoke_detector_problem",
                "state": "off",
                "attributes": {"friendly_name": "Living Room Smoke Detector Problem", "device_class": "problem"},
            },
        ]
        items = [_safety_item(state, states) for state in states]

        smoke_items = [item for item in items if _is_smoke_detector_smoke_item(item)]

        self.assertEqual([item["entity_id"] for item in smoke_items], ["binary_sensor.living_room_smoke_detector_smoke"])

    def test_wall_temperature_items_ignore_device_internal_temperatures(self):
        from backend.api.homeassistant_routes import _temperature_items

        states = [
            {
                "entity_id": "sensor.wohnzimmer_temperatur",
                "state": "22.4",
                "attributes": {"friendly_name": "Wohnzimmer Temperatur", "device_class": "temperature", "unit_of_measurement": "°C"},
            },
            {
                "entity_id": "sensor.fritzbox_router_temperature",
                "state": "61",
                "attributes": {"friendly_name": "FritzBox Router Temperature", "device_class": "temperature", "unit_of_measurement": "°C"},
            },
            {
                "entity_id": "sensor.server_cpu_temperature",
                "state": "72",
                "attributes": {"friendly_name": "Server CPU Temperature", "device_class": "temperature", "unit_of_measurement": "°C"},
            },
            {
                "entity_id": "sensor.hobby_room_water_leak_sensor_left_device_temperature",
                "state": "29",
                "attributes": {"friendly_name": "Hobby Room Water Leak", "device_class": "temperature", "unit_of_measurement": "°C"},
            },
        ]

        items = _temperature_items(states)

        self.assertEqual([item["entity_id"] for item in items], ["sensor.wohnzimmer_temperatur"])

    def test_wall_lights_ignore_auxiliary_dnd_entities(self):
        from backend.api.homeassistant_routes import _wall_device_groups, _wall_state_is_primary

        states = [
            {
                "entity_id": "light.powder_room_guest_wc_roller_shutter_dnd",
                "state": "off",
                "attributes": {
                    "friendly_name": "Guest WC Roller Shutter Dnd",
                    "device_class": "DNDMode",
                    "supported_color_modes": ["onoff"],
                },
            },
            {
                "entity_id": "light.powder_room_wc",
                "state": "on",
                "attributes": {
                    "friendly_name": "WC",
                    "supported_color_modes": ["color_temp"],
                    "brightness": 144,
                },
            },
        ]
        groups = _wall_device_groups(states)

        self.assertFalse(_wall_state_is_primary(states[0], groups, "light"))
        self.assertTrue(_wall_state_is_primary(states[1], groups, "light"))

    def test_wall_opening_area_uses_full_room_prefix_from_entity_id(self):
        from backend.api.homeassistant_routes import _simple_item

        item = _simple_item({
            "entity_id": "binary_sensor.laundry_room_window_contact_contact",
            "state": "on",
            "attributes": {"friendly_name": "Fenster", "device_class": "window"},
        })

        self.assertEqual(item["area"], "Laundry Room")

    def test_wall_opening_area_collapses_repeated_device_prefix(self):
        from backend.api.homeassistant_routes import _simple_item

        item = _simple_item({
            "entity_id": "binary_sensor.office_office_skylight_contact_tur",
            "state": "on",
            "attributes": {"friendly_name": "Office Skylight Contact Tür", "device_class": "window"},
        })

        self.assertEqual(item["area"], "Office")

    def test_unavailable_devices_are_grouped_and_unknown_states_are_ignored(self):
        from backend.api.homeassistant_routes import _unavailable_device_items

        states = [
            {
                "entity_id": "binary_sensor.bad_fenster_contact",
                "state": "unavailable",
                "device_id": "window-1",
                "attributes": {"friendly_name": "Bad Fensterkontakt", "device_class": "window"},
            },
            {
                "entity_id": "sensor.bad_fenster_battery",
                "state": "unavailable",
                "device_id": "window-1",
                "attributes": {"friendly_name": "Bad Fensterkontakt Batterie", "device_class": "battery"},
            },
            {
                "entity_id": "button.bad_fenster_identify",
                "state": "unknown",
                "attributes": {"friendly_name": "Bad Fenster identifizieren"},
            },
        ]

        items = _unavailable_device_items(states)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["device_key"], "device:window-1")
        self.assertEqual(items[0]["entity_count"], 2)
        self.assertEqual(items[0]["state"], "unavailable")

    def test_unavailable_zigbee_entities_group_without_device_id(self):
        from backend.api.homeassistant_routes import _unavailable_device_items

        states = [
            {"entity_id": "binary_sensor.bathroom_window_contact_contact", "state": "unavailable", "attributes": {"friendly_name": "Bathroom Window Contact"}},
            {"entity_id": "sensor.bathroom_window_contact_battery", "state": "unavailable", "attributes": {"friendly_name": "Bathroom Window Contact Battery"}},
            {"entity_id": "sensor.garden_bodenfeuchte_rasen_soil_moisture", "state": "unavailable", "attributes": {"friendly_name": "Garden Bodenfeuchte Rasen"}},
            {"entity_id": "sensor.garden_bodenfeuchte_rasen_battery", "state": "unavailable", "attributes": {"friendly_name": "Garden Bodenfeuchte Rasen Battery"}},
        ]

        items = _unavailable_device_items(states)

        self.assertEqual(len(items), 2)
        self.assertEqual({item["name"] for item in items}, {"Bathroom Window Contact", "Garden Bodenfeuchte Rasen"})

    def test_unavailable_devices_use_registry_names_and_only_zigbee2mqtt(self):
        from backend.api.homeassistant_routes import _unavailable_device_items

        states = [
            {"entity_id": "light.bad_spot_1", "state": "unavailable", "attributes": {"friendly_name": "Bath spot 1"}},
            {"entity_id": "binary_sensor.bathroom_window_contact_contact", "state": "unavailable", "attributes": {"friendly_name": "Fenster"}},
            {"entity_id": "binary_sensor.bathroom_window_contact_tamper", "state": "unavailable", "attributes": {"friendly_name": "Bathroom Window Contact Manipulation"}},
            {"entity_id": "sensor.garden_bodenfeuchte_rasen_battery", "state": "unavailable", "attributes": {"friendly_name": "Garden Bodenfeuchte Rasen Batterie"}},
        ]
        lookup = {
            "light.bad_spot_1": {"device_id": "hue-1", "name": "Bath spot 1", "is_zigbee2mqtt": False},
            "binary_sensor.bathroom_window_contact_contact": {"device_id": "contact-1", "name": "Bathroom Window Contact", "is_zigbee2mqtt": True},
            "binary_sensor.bathroom_window_contact_tamper": {"device_id": "contact-1", "name": "Bathroom Window Contact", "is_zigbee2mqtt": True},
            "sensor.garden_bodenfeuchte_rasen_battery": {"device_id": "soil-1", "name": "Garden Bodenfeuchte Rasen", "is_zigbee2mqtt": True},
        }

        items = _unavailable_device_items(states, lookup)

        self.assertEqual(len(items), 2)
        self.assertEqual({item["name"] for item in items}, {"Bathroom Window Contact", "Garden Bodenfeuchte Rasen"})
        self.assertNotIn("Bath spot 1", {item["name"] for item in items})

    def test_unavailable_opening_uses_device_name_without_changing_state(self):
        from backend.api.homeassistant_routes import _opening_item

        state = {
            "entity_id": "binary_sensor.bathroom_window_contact_contact",
            "state": "unavailable",
            "attributes": {"friendly_name": "Fenster", "device_class": "window"},
        }
        lookup = {
            state["entity_id"]: {
                "device_id": "contact-1",
                "name": "Bathroom Window Contact",
                "is_zigbee2mqtt": True,
            },
        }

        item = _opening_item(state, lookup)

        self.assertEqual(item["name"], "Bathroom Window Contact")
        self.assertEqual(item["state"], "unavailable")


if __name__ == "__main__":
    unittest.main()
