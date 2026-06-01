import json
from typing import Any

from backend.services.llm.factory import create_llm_client


SYSTEM_PROMPT = """Du bist ein intelligenter Urlaubs- und Abwesenheitsassistent.

Deine Aufgabe:

Analysiere den aktuellen Zustand des Hauses vor oder während einer Abwesenheit.

Du darfst:

- Risiken erkennen
- Empfehlungen geben
- Aufgaben priorisieren
- Checklisten erzeugen

Du darfst NICHT:

- Geräte steuern
- Home Assistant Aktionen ausführen
- Licht schalten
- Jalousien schalten
- Alarmanlagen steuern

Formuliere verständliche Hinweise für den Bewohner.

Beziehe dich ausschließlich auf die bereitgestellten Daten.

Wenn keine Risiken vorliegen, sage das ausdrücklich.

Antworte ausschließlich als JSON."""


class VacationAIService:
    def analyze(self, payload: dict[str, Any]) -> dict[str, Any]:
        prompt = (
            "Analysiere diese strukturierten Vacation-Agent-Daten.\n"
            "Erzeuge ausschließlich Hinweise, Empfehlungen, Warnungen und eine Zusammenfassung.\n"
            "Du darfst keine Aktionen, Service Calls, Automationen oder Home-Assistant-Kommandos erzeugen.\n"
            "Return valid JSON only, with exactly this shape and no wrapper object:\n"
            "{\n"
            '  "summary": "...",\n'
            '  "risk_level": "low|medium|high",\n'
            '  "recommendations": [],\n'
            '  "warnings": [],\n'
            '  "travel_preparation_score": 0\n'
            "}\n\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
        )
        response = create_llm_client().generate(prompt=prompt, system=SYSTEM_PROMPT)
        return self.validate_json(response.text)

    def validate_json(self, raw: str) -> dict[str, Any]:
        data = self._parse_json(raw)
        return {
            "summary": str(data.get("summary") or "").strip() or "Die Urlaubsvorbereitung wurde analysiert.",
            "risk_level": self._risk_level(data.get("risk_level")),
            "recommendations": self._string_list(data.get("recommendations")),
            "warnings": self._string_list(data.get("warnings")),
            "travel_preparation_score": self._score(data.get("travel_preparation_score")),
        }

    def fallback(self, payload: dict[str, Any], reason: str = "") -> dict[str, Any]:
        reminders = payload.get("reminders") if isinstance(payload.get("reminders"), list) else []
        warning_items = [
            str(item.get("message") or item.get("title") or "").strip()
            for item in reminders
            if isinstance(item, dict) and str(item.get("severity") or "info").lower() in {"warning", "critical"}
        ]
        warning_items = [item for item in warning_items if item]
        critical_count = sum(
            1
            for item in reminders
            if isinstance(item, dict) and str(item.get("severity") or "info").lower() == "critical"
        )
        risk_level = "high" if critical_count else "medium" if warning_items else "low"
        score = 95 if risk_level == "low" else 72 if risk_level == "medium" else 45
        recommendations = warning_items[:6]
        if not recommendations:
            recommendations = ["Aktuell liegen keine dringenden offenen Punkte aus den bereitgestellten Daten vor."]
        warnings = warning_items[:6] if warning_items else []
        if reason:
            warnings.append(f"KI-Analyse nicht verfügbar; regelbasierter Fallback aktiv: {reason[:180]}")
        return {
            "summary": (
                "Vor der Reise sollten noch einige Punkte geprüft werden."
                if warning_items
                else "Aus den bereitgestellten Daten ergeben sich aktuell keine größeren Risiken."
            ),
            "risk_level": risk_level,
            "recommendations": recommendations,
            "warnings": warnings,
            "travel_preparation_score": score,
        }

    def _parse_json(self, raw: str) -> dict[str, Any]:
        text = (raw or "").strip()
        if text.startswith("```"):
            text = text.strip("`").strip()
            if text.lower().startswith("json"):
                text = text[4:].strip()
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("KI-Antwort ist kein JSON-Objekt.")
        return data

    def _risk_level(self, value: Any) -> str:
        text = str(value or "").strip().lower()
        return text if text in {"low", "medium", "high"} else "low"

    def _score(self, value: Any) -> int:
        try:
            score = int(float(value))
        except (TypeError, ValueError):
            score = 0
        return max(0, min(100, score))

    def _string_list(self, value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item or "").strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []
