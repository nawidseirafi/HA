import logging
from core.ha_client import HomeAssistantClient
import warnings

warnings.filterwarnings("ignore")

logging.basicConfig(
    filename="logs/agent.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

logging.info("=== HA Client Test gestartet ===")

ha = HomeAssistantClient()

states = ha.get_states()
logging.info(f"Entities gefunden: {len(states)}")

for entity in states[:5]:
    logging.info(f"{entity['entity_id']} = {entity['state']}")