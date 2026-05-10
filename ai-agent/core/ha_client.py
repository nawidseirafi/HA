import requests
import yaml
import logging


class HomeAssistantClient:
    def __init__(self, config_path="config.yaml"):
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        if not config:
            raise ValueError("config.yaml ist leer oder ungültig")

        self.base_url = config["home_assistant"]["url"].rstrip("/")
        self.token = config["home_assistant"]["token"]

        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def get_states(self):
        url = f"{self.base_url}/api/states"
        r = requests.get(url, headers=self.headers, timeout=10)
        r.raise_for_status()
        return r.json()

    def get_state(self, entity_id):
        url = f"{self.base_url}/api/states/{entity_id}"
        r = requests.get(url, headers=self.headers, timeout=10)
        r.raise_for_status()
        return r.json()

    def call_service(self, domain, service, data):
        url = f"{self.base_url}/api/services/{domain}/{service}"
        r = requests.post(url, headers=self.headers, json=data, timeout=10)
        r.raise_for_status()
        return r.json()

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