import json
import subprocess
import sys
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[2]
PROJECT_DIR = BASE_DIR.parent
AI_AGENT_DIR = PROJECT_DIR / "ai-agent"
AGENT_SCRIPT = AI_AGENT_DIR / "market" / "market.py"

if str(AI_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AI_AGENT_DIR))

from market.report import MarketReportService  # noqa: E402  (sys.path setup above)


store = MarketReportService()


def _run_agent(*args: str) -> dict[str, Any]:
    if not AGENT_SCRIPT.exists():
        raise RuntimeError(f"Market-Agent-Skript nicht gefunden: {AGENT_SCRIPT}")
    command = [sys.executable, str(AGENT_SCRIPT), *args]
    result = subprocess.run(
        command,
        cwd=AI_AGENT_DIR,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Market-Agent fehlgeschlagen (exit {result.returncode}): {result.stderr.strip() or result.stdout.strip()}"
        )
    output = result.stdout.strip()
    if not output:
        raise RuntimeError("Market-Agent lieferte keine Ausgabe")
    try:
        return json.loads(output)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Market-Agent JSON-Antwort ungueltig: {exc}: {output[:500]}") from exc


def run() -> dict[str, Any]:
    return _run_agent("run")


def analyze_symbol(symbol: str) -> dict[str, Any]:
    return _run_agent("analyze", "--symbol", symbol)
