import logging

from backend.services.homeassistant_service import HomeAssistantService


class HomeAssistantClient:
    def __init__(self, config_path="config.yaml"):
        self.service = HomeAssistantService()
        self.base_url = self.service.base_url
        self.token = self.service.token
        self._validate_config()

        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def _validate_config(self):
        if not self.service.configured():
            raise ValueError("Home Assistant URL oder Token fehlt. Setze HA_URL und HA_TOKEN in agent-api/.env oder config.yaml.")

    def get_states(self):
        return self.service.get_states()

    def get_state(self, entity_id):
        return self.service.get_state(entity_id)

    def get_calendars(self):
        return self.service.get_calendars()

    def get_calendar_events(self, entity_id, start, end):
        return self.service.get_calendar_events(entity_id, start, end)

    def call_service(self, domain, service, data):
        response = self.service.call_service(domain, service, data)
        return response.get("result", response)

    def persistent_notification(self, title, message, notification_id=None):
        data = {
            "title": title,
            "message": message,
        }
        if notification_id:
            data["notification_id"] = notification_id
        logging.info("Sende Home-Assistant-Benachrichtigung: %s", title)
        return self.call_service("persistent_notification", "create", data)

    def notify(self, service, title, message, data=None):
        service_name = service.replace("notify.", "")
        payload = {
            "title": title,
            "message": message,
        }
        if data:
            payload["data"] = data
        logging.info("Sende Home-Assistant-Mobile-Notification: %s", title)
        return self.call_service("notify", service_name, payload)

    def turn_on(self, entity_id):
        domain = entity_id.split(".")[0]
        logging.info(f"Schalte ein: {entity_id}")
        return self.call_service(domain, "turn_on", {"entity_id": entity_id})

    def turn_off(self, entity_id):
        domain = entity_id.split(".")[0]
        logging.info(f"Schalte aus: {entity_id}")
        return self.call_service(domain, "turn_off", {"entity_id": entity_id})

    def set_cover_position(self, entity_id, position):
        logging.info(f"Setze Jalousie: {entity_id} auf {position}%")
        return self.call_service(
            "cover",
            "set_cover_position",
            {
                "entity_id": entity_id,
                "position": position,
            },
        )
