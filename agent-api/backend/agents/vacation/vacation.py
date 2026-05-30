import yaml
import logging
from backend.paths import API_DIR
from backend.services.llm.factory import create_llm_client
from backend.services.core.ha_client import HomeAssistantClient

import warnings

warnings.filterwarnings("ignore")

LOG_DIR = API_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    filename=LOG_DIR / "vaction.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

def load_config():
    with (API_DIR / "config.yaml").open("r") as f:
        return yaml.safe_load(f)

def main():
    config = load_config()
    llm = create_llm_client(config)
    ha = HomeAssistantClient()

    vacation_mode = ha.get_state(
        "input_boolean.vacation_mode"
    )["state"] == "on"

    logging.info(f"vacation_mode: {vacation_mode}")

    states = ha.get_states()
    logging.info(f"Entities gefunden: {len(states)}")
    for entity in states[:5]:
        logging.info(f"{entity['entity_id']} = {entity['state']}")

    response = llm.generate(
        system="Du bist ein Home-Assistant-Agent. Du darfst ausschließlich gültiges JSON zurückgeben. " \
        "Antwortformat:" \
        "{'actions': [{'type': 'turn_on','entity_id': 'light.xyz'}]}"
        "Regeln:"
        "- Nur JSON"
        "- Keine Erklärung"
        "- Kein Markdown"
        "- Keine zusätzlichen Felder",
        prompt="Situation:"
        "- Es ist dunkel"
        "- Niemand zuhause"
        "- Vacation mode aktiv"
        "Verfügbare Lichter:"
        "- light.wohnzimmer"
        "- light.flur"
        "- light.kueche"
        "Entscheide eine sinnvolle Aktion."
    );

    logging.info(f"LLM Provider: {response.provider}")
    logging.info(f"LLM Model: {response.model}")
    logging.info(f"LLM Antwort: {response.text}")


if __name__ == "__main__":
    main()
