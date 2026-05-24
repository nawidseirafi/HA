import yaml
import logging
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from llm import create_llm_client
from shared.ha_client import HomeAssistantClient

import warnings

warnings.filterwarnings("ignore")

LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    filename=LOG_DIR / "agent.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

def load_config():
    with (BASE_DIR / "config.yaml").open("r") as f:
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
