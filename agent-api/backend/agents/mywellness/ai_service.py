import json
import os
from typing import Any
import yaml
from backend.services.llm.factory import create_llm_client
from backend.paths import API_DIR

SYSTEM_PROMPT = """You are the personal wellness and recovery assistant of RoboterSteve.

Your task is to evaluate:

- recovery
- training readiness
- sleep quality
- stress
- wellness trends
- fitness consistency

You are NOT a doctor.

You must NOT:
- diagnose diseases
- diagnose cardiovascular conditions
- diagnose sleep disorders
- diagnose blood pressure conditions
- prescribe medication
- prescribe supplements
- replace professional medical advice

You MAY:
- explain health and fitness trends
- identify positive developments
- identify recovery problems
- identify possible overtraining
- identify insufficient recovery
- recommend workout intensity
- recommend rest days
- recommend recovery activities

IMPORTANT:

Historical trends are more important than single measurements.

Always evaluate:

- recovery trends
- sleep trends
- HRV trends
- resting heart rate trends
- training consistency

before evaluating today's readiness.

If data is insufficient, clearly say so.

If values appear repeatedly unusual, state:

"Bitte bei wiederholt auffälligen Werten ärztlich abklären."

Return valid JSON only."""


class MyWellnessAIService:
    def __init__(self) -> None:
        pass

    def analyze(self, payload: dict[str, Any]) -> dict[str, Any]:
        client = self._client()
        prompt = (
            "Analyze this normalized MyWellness health payload.\n"
            "Interpret trend data first.\n"
            "Then evaluate current readiness.\n"
            "Explain WHY you reached your conclusion.\n"
            "Prioritize long-term trends over isolated values.\n"
            "The payload may contain current_metrics, trend_context, history_context, metrics, and withings data.\n"
            "For trend, use stable when historical data is insufficient and explain the limitation in recovery_reasoning or risk_signals.\n"
            "Return valid JSON only, with exactly this flat shape and no wrapper object:\n"
            "{\n"
            '  "recovery_state": "low|medium|high",\n'
            '  "training_readiness": 0,\n'
            '  "stress_level": "low|medium|high",\n'
            '  "trend": "improving|stable|declining",\n'
            '  "energy_level": "low|medium|high",\n'
            '  "summary": "...",\n'
            '  "recommendation": "...",\n'
            '  "should_train_today": true,\n'
            '  "recommended_workout_type": "...",\n'
            '  "recovery_reasoning": [],\n'
            '  "positive_signals": [],\n'
            '  "risk_signals": [],\n'
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
        trend = self._trend(data.get("trend"))
        energy_level = self._level(data.get("energy_level"), field_name="energy_level")
        return {
            "recovery_state": recovery_state,
            "training_readiness": self._int_range(data.get("training_readiness")),
            "stress_level": stress_level,
            "trend": trend,
            "energy_level": energy_level,
            "summary": str(data.get("summary") or "").strip(),
            "recommendation": str(data.get("recommendation") or "").strip(),
            "should_train_today": bool(data.get("should_train_today")),
            "recommended_workout_type": str(data.get("recommended_workout_type") or "").strip(),
            "recovery_reasoning": self._string_list(data.get("recovery_reasoning")),
            "positive_signals": self._string_list(data.get("positive_signals")),
            "risk_signals": self._string_list(data.get("risk_signals")),
            "warnings": self._string_list(data.get("warnings")),
        }

    def fallback(self, scores: dict[str, Any], reason: str = "") -> dict[str, Any]:
        recovery_score = int(scores.get("recovery_score") or 0)
        stress_score = int(scores.get("stress_score") or 0)
        readiness = int(scores.get("training_readiness") or 0)
        recovery_state = "high" if recovery_score >= 75 else "medium" if recovery_score >= 50 else "low"
        stress_level = "high" if stress_score >= 70 else "medium" if stress_score >= 40 else "low"
        trend = "improving" if recovery_score >= 70 and stress_score < 45 else "declining" if recovery_score < 50 or stress_score >= 70 else "stable"
        energy_level = "high" if readiness >= 75 else "medium" if readiness >= 50 else "low"
        should_train = readiness >= 55 and stress_score < 75
        workout = "Kraft oder Kurs nach Plan" if should_train and recovery_score >= 70 else "leichtes Mobility- oder Zone-2-Training"
        if not should_train:
            workout = "Regeneration, Spaziergang oder Mobility"
        recovery_reasoning = [
            f"Recovery Score: {recovery_score}",
            f"Stress Score: {stress_score}",
            f"Training Readiness: {readiness}",
        ]
        positive_signals = []
        if recovery_score >= 70:
            positive_signals.append("Recovery Score ist im guten Bereich.")
        if stress_score < 45:
            positive_signals.append("Stress Score ist niedrig bis moderat.")
        risk_signals = []
        if recovery_score < 50:
            risk_signals.append("Recovery Score ist niedrig.")
        if stress_score >= 70:
            risk_signals.append("Stress Score ist hoch.")
        warnings = ["KI-Analyse nicht verfuegbar; regelbasierter Fallback aktiv."]
        if reason:
            warnings.append(reason[:240])
        return {
            "recovery_state": recovery_state,
            "training_readiness": readiness,
            "stress_level": stress_level,
            "trend": trend,
            "energy_level": energy_level,
            "summary": "Die Einschaetzung basiert auf den importierten Health-Metriken und einfachen Recovery-Regeln.",
            "recommendation": "Achte auf Schlaf, Belastung und Ruhepuls. Passe die Kursintensitaet an die heutige Readiness an.",
            "should_train_today": should_train,
            "recommended_workout_type": workout,
            "recovery_reasoning": recovery_reasoning,
            "positive_signals": positive_signals,
            "risk_signals": risk_signals,
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
            readiness = self._int_range(data.get("training_readiness"))
            recovery_score = self._int_range(data.get("recovery_score") or readiness)
            stress_score = self._int_range(data.get("stress_score"))
            data.setdefault("trend", self._trend_from_score(recovery_score, stress_score))
            data.setdefault("energy_level", self._state_from_score(readiness))
            data.setdefault("recovery_reasoning", [])
            data.setdefault("positive_signals", [])
            data.setdefault("risk_signals", [])
            data.setdefault("warnings", [])
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
            "trend": data.get("trend") or self._trend_from_score(recovery_score, stress_score),
            "energy_level": data.get("energy_level") or self._state_from_score(readiness),
            "summary": data.get("summary") or " ".join(summary_parts) or "Die KI hat die Health-Daten ausgewertet.",
            "recommendation": data.get("recommendation") or "Passe die Trainingsintensitaet an Readiness, Schlafdaten und Belastung an.",
            "should_train_today": data.get("should_train_today") if "should_train_today" in data else readiness >= 55 and stress_score < 70,
            "recommended_workout_type": data.get("recommended_workout_type") or ("leichtes Training" if readiness >= 55 else "Regeneration oder Mobility"),
            "recovery_reasoning": data.get("recovery_reasoning") if isinstance(data.get("recovery_reasoning"), list) else summary_parts,
            "positive_signals": data.get("positive_signals") if isinstance(data.get("positive_signals"), list) else [],
            "risk_signals": data.get("risk_signals") if isinstance(data.get("risk_signals"), list) else [],
            "warnings": data.get("warnings") if isinstance(data.get("warnings"), list) else [],
        }

    def _trend_from_score(self, recovery_score: int, stress_score: int) -> str:
        if recovery_score >= 70 and stress_score < 45:
            return "improving"
        if recovery_score < 50 or stress_score >= 70:
            return "declining"
        return "stable"

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

    def _trend(self, value: Any) -> str:
        text = str(value or "").strip().lower()
        aliases = {
            "improving": "improving",
            "better": "improving",
            "up": "improving",
            "verbessert": "improving",
            "stable": "stable",
            "flat": "stable",
            "gleich": "stable",
            "stabil": "stable",
            "insufficient_data": "stable",
            "insufficient data": "stable",
            "not_enough_data": "stable",
            "unknown": "stable",
            "unclear": "stable",
            "declining": "declining",
            "worse": "declining",
            "down": "declining",
            "verschlechtert": "declining",
        }
        normalized = aliases.get(text)
        if not normalized:
            raise ValueError(f"KI-Antwort enthaelt ungueltigen trend: {text or 'leer'}.")
        return normalized

    def _string_list(self, value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if value is None or value == "":
            return []
        return [str(value).strip()]
