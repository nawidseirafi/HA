import json
import os
from typing import Any
import yaml
from backend.services.llm.factory import create_llm_client
from backend.paths import API_DIR

SYSTEM_PROMPT = """You are an AI wellness and recovery assistant.
Analyze structured fitness and wellness data.
Do not diagnose diseases.
Do not provide medical advice.
Do not diagnose blood pressure, body composition, sleep, or cardiovascular conditions.
Do not prescribe supplements or change supplement dosage.
Focus only on wellness, recovery, sleep, stress, training load, and fitness readiness.
Mention blood pressure only carefully as an observed value.
If blood pressure values are repeatedly unusual, only say: "Bitte bei wiederholt auffälligen Werten ärztlich abklären."
Base conclusions strictly on the provided data.
If data is insufficient, say so.
Output valid JSON only."""


class MyWellnessAIService:
    def __init__(self) -> None:
        pass

    def analyze(self, payload: dict[str, Any]) -> dict[str, Any]:
        client = self._client()
        prompt = (
            "Analyze this normalized MyWellness health payload.\n"
            "Return valid JSON only, with exactly this flat shape and no wrapper object:\n"
            "{\n"
            '  "recovery_state": "low|medium|high",\n'
            '  "training_readiness": 0,\n'
            '  "stress_level": "low|medium|high",\n'
            '  "summary": "...",\n'
            '  "recommendation": "...",\n'
            '  "should_train_today": true,\n'
            '  "recommended_workout_type": "...",\n'
            '  "warnings": []\n'
            "}\n"
            "Do not return nested keys like wellness, recovery, sleep, or stress.\n\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
        )
        response = client.generate(prompt=prompt, system=SYSTEM_PROMPT)
        return self.validate_json(response.text)

    def validate_json(self, raw: str) -> dict[str, Any]:
        data = self._parse_json(raw)
        data = self._coerce_flat_response(data)
        recovery_state = self._level(data.get("recovery_state"), field_name="recovery_state")
        stress_level = self._level(data.get("stress_level"), field_name="stress_level")
        warnings = data.get("warnings")
        if not isinstance(warnings, list):
            warnings = []
        return {
            "recovery_state": recovery_state,
            "training_readiness": self._int_range(data.get("training_readiness")),
            "stress_level": stress_level,
            "summary": str(data.get("summary") or "").strip(),
            "recommendation": str(data.get("recommendation") or "").strip(),
            "should_train_today": bool(data.get("should_train_today")),
            "recommended_workout_type": str(data.get("recommended_workout_type") or "").strip(),
            "warnings": [str(item) for item in warnings if str(item).strip()],
        }

    def fallback(self, scores: dict[str, Any], reason: str = "") -> dict[str, Any]:
        recovery_score = int(scores.get("recovery_score") or 0)
        stress_score = int(scores.get("stress_score") or 0)
        readiness = int(scores.get("training_readiness") or 0)
        recovery_state = "high" if recovery_score >= 75 else "medium" if recovery_score >= 50 else "low"
        stress_level = "high" if stress_score >= 70 else "medium" if stress_score >= 40 else "low"
        should_train = readiness >= 55 and stress_score < 75
        workout = "Kraft oder Kurs nach Plan" if should_train and recovery_score >= 70 else "leichtes Mobility- oder Zone-2-Training"
        if not should_train:
            workout = "Regeneration, Spaziergang oder Mobility"
        warnings = ["KI-Analyse nicht verfuegbar; regelbasierter Fallback aktiv."]
        if reason:
            warnings.append(reason[:240])
        return {
            "recovery_state": recovery_state,
            "training_readiness": readiness,
            "stress_level": stress_level,
            "summary": "Die Einschaetzung basiert auf den importierten Health-Metriken und einfachen Recovery-Regeln.",
            "recommendation": "Achte auf Schlaf, Belastung und Ruhepuls. Passe die Kursintensitaet an die heutige Readiness an.",
            "should_train_today": should_train,
            "recommended_workout_type": workout,
            "warnings": warnings,
        }

    def _client(self) -> Any:
        config_path = API_DIR / "config.yaml"
        with config_path.open("r", encoding="utf-8") as handle:
            config = yaml.safe_load(handle) or {}
        provider = config.get("llm", {}).get("provider", "")
        provider_config = config.get("llm", {}).get(provider, {})
        api_key_name = provider_config.get("api_key")
        if api_key_name and not os.getenv(api_key_name):
            raise RuntimeError(f"{api_key_name} ist nicht konfiguriert.")
        return create_llm_client()

    def _parse_json(self, raw: str) -> dict[str, Any]:
        text = (raw or "").strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:].strip()
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("KI-Antwort ist kein JSON-Objekt.")
        return data

    def _coerce_flat_response(self, data: dict[str, Any]) -> dict[str, Any]:
        if "recovery_state" in data and "stress_level" in data:
            return data
        recovery = data.get("recovery") if isinstance(data.get("recovery"), dict) else {}
        stress = data.get("stress") if isinstance(data.get("stress"), dict) else {}
        sleep = data.get("sleep") if isinstance(data.get("sleep"), dict) else {}
        wellness = data.get("wellness") if isinstance(data.get("wellness"), dict) else {}
        training = data.get("training_load") if isinstance(data.get("training_load"), dict) else {}
        readiness = self._int_range(data.get("training_readiness") or recovery.get("training_readiness"))
        recovery_score = self._int_range(data.get("recovery_score") or recovery.get("recovery_score"))
        stress_score = self._int_range(data.get("stress_score") or stress.get("stress_score") or wellness.get("stress_score"))
        summary_parts = [
            str(item).strip()
            for item in (
                wellness.get("summary") or wellness.get("note"),
                sleep.get("sleep_quality_note"),
                stress.get("note"),
                training.get("last_mywellness_courses_status"),
            )
            if str(item or "").strip()
        ]
        return {
            "recovery_state": data.get("recovery_state") or self._state_from_score(recovery_score),
            "training_readiness": readiness,
            "stress_level": data.get("stress_level") or self._state_from_score(stress_score),
            "summary": data.get("summary") or " ".join(summary_parts) or "Die KI hat die Health-Daten ausgewertet.",
            "recommendation": data.get("recommendation") or "Passe die Trainingsintensitaet an Readiness, Schlafdaten und Belastung an.",
            "should_train_today": data.get("should_train_today") if "should_train_today" in data else readiness >= 55 and stress_score < 70,
            "recommended_workout_type": data.get("recommended_workout_type") or ("leichtes Training" if readiness >= 55 else "Regeneration oder Mobility"),
            "warnings": data.get("warnings") if isinstance(data.get("warnings"), list) else [],
        }

    def _state_from_score(self, score: int) -> str:
        if score >= 70:
            return "high"
        if score >= 40:
            return "medium"
        return "low"

    def _int_range(self, value: Any) -> int:
        try:
            number = int(float(value))
        except (TypeError, ValueError):
            number = 0
        return max(0, min(100, number))

    def _level(self, value: Any, field_name: str) -> str:
        text = str(value or "").strip().lower()
        aliases = {
            "low": "low",
            "niedrig": "low",
            "gering": "low",
            "weak": "low",
            "medium": "medium",
            "moderate": "medium",
            "normal": "medium",
            "mittel": "medium",
            "moderat": "medium",
            "high": "high",
            "hoch": "high",
            "strong": "high",
            "gut": "high",
        }
        normalized = aliases.get(text)
        if not normalized:
            raise ValueError(f"KI-Antwort enthaelt ungueltigen {field_name}: {text or 'leer'}.")
        return normalized
