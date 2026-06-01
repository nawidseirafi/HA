import json
import sqlite3
from datetime import date, datetime, timezone
from typing import Any

from .service import MyWellnessService
from .ai_service import MyWellnessAIService
from .store import (
    get_booking_stats,
    get_health_trend,
    get_latest_metrics,
    get_recovery_history,
    save_ai_recommendation,
    save_health_metric,
    save_health_snapshot,
    save_recovery_analysis,
)
from backend.services.homeassistant_service import HomeAssistantService
from backend.services.messaging import MessagingService


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class MyWellnessHealthService:
    entity_fields = (
        "profile_birth_date",
        "profile_supplements",
        "profile_notes",
        "ha_entity_steps",
        "ha_entity_active_calories",
        "ha_entity_resting_heart_rate",
        "ha_entity_hrv",
        "ha_entity_sleep_hours",
        "ha_entity_weight",
        "ha_entity_blood_pressure_systolic",
        "ha_entity_blood_pressure_diastolic",
        "ha_entity_withings_weight",
        "ha_entity_withings_bmi",
        "ha_entity_withings_fat_mass",
        "ha_entity_withings_muscle_mass",
        "ha_entity_withings_body_water",
        "ha_entity_withings_heart_rate",
        "ha_entity_withings_systolic_blood_pressure",
        "ha_entity_withings_diastolic_blood_pressure",
        "ha_entity_withings_sleep_score",
        "ha_entity_withings_sleep_duration",
        "ha_entity_withings_deep_sleep",
        "ha_entity_withings_light_sleep",
        "ha_entity_withings_rem_sleep",
    )

    metric_fields = {
        "steps": "ha_entity_steps",
        "active_calories": "ha_entity_active_calories",
        "resting_heart_rate": "ha_entity_resting_heart_rate",
        "hrv": "ha_entity_hrv",
        "sleep_hours": "ha_entity_sleep_hours",
        "weight": "ha_entity_weight",
        "blood_pressure_systolic": "ha_entity_blood_pressure_systolic",
        "blood_pressure_diastolic": "ha_entity_blood_pressure_diastolic",
    }

    withings_metric_fields = {
        "weight": "ha_entity_withings_weight",
        "bmi": "ha_entity_withings_bmi",
        "fat_mass": "ha_entity_withings_fat_mass",
        "muscle_mass": "ha_entity_withings_muscle_mass",
        "body_water": "ha_entity_withings_body_water",
        "resting_heart_rate": "ha_entity_withings_heart_rate",
        "blood_pressure_systolic": "ha_entity_withings_systolic_blood_pressure",
        "blood_pressure_diastolic": "ha_entity_withings_diastolic_blood_pressure",
        "sleep_score": "ha_entity_withings_sleep_score",
        "sleep_hours": "ha_entity_withings_sleep_duration",
        "deep_sleep_hours": "ha_entity_withings_deep_sleep",
        "light_sleep_hours": "ha_entity_withings_light_sleep",
        "rem_sleep_hours": "ha_entity_withings_rem_sleep",
    }

    default_withings_entities = {
        "ha_entity_withings_weight": "sensor.withings_gewicht",
        "ha_entity_withings_bmi": "sensor.withings_bmi",
        "ha_entity_withings_fat_mass": "sensor.withings_fettmasse",
        "ha_entity_withings_muscle_mass": "sensor.withings_muskelmasse",
        "ha_entity_withings_body_water": "sensor.withings_body_water",
        "ha_entity_withings_heart_rate": "sensor.withings_herzschlag",
        "ha_entity_withings_systolic_blood_pressure": "sensor.withings_systolic_blood_pressure",
        "ha_entity_withings_diastolic_blood_pressure": "sensor.withings_diastolic_blood_pressure",
        "ha_entity_withings_sleep_score": "sensor.withings_sleep_score",
        "ha_entity_withings_sleep_duration": "sensor.withings_sleep_duration",
        "ha_entity_withings_deep_sleep": "sensor.withings_deep_sleep",
        "ha_entity_withings_light_sleep": "sensor.withings_light_sleep",
        "ha_entity_withings_rem_sleep": "sensor.withings_rem_sleep",
    }

    withings_entity_aliases = {
        "ha_entity_withings_weight": ("sensor.withings_gewicht", "sensor.withings_weight"),
        "ha_entity_withings_bmi": ("sensor.withings_bmi",),
        "ha_entity_withings_fat_mass": ("sensor.withings_fettmasse", "sensor.withings_fat_mass"),
        "ha_entity_withings_muscle_mass": ("sensor.withings_muskelmasse", "sensor.withings_muscle_mass"),
        "ha_entity_withings_body_water": ("sensor.withings_korperwasser", "sensor.withings_koerperwasser", "sensor.withings_body_water"),
        "ha_entity_withings_heart_rate": ("sensor.withings_herzschlag", "sensor.withings_heart_rate"),
        "ha_entity_withings_systolic_blood_pressure": (
            "sensor.withings_systolischer_blutdruck",
            "sensor.withings_systolic_blood_pressure",
        ),
        "ha_entity_withings_diastolic_blood_pressure": (
            "sensor.withings_diastolischer_blutdruck",
            "sensor.withings_diastolic_blood_pressure",
        ),
        "ha_entity_withings_sleep_score": ("sensor.withings_schlafscore", "sensor.withings_sleep_score"),
        "ha_entity_withings_sleep_duration": ("sensor.withings_schlafdauer", "sensor.withings_sleep_duration"),
        "ha_entity_withings_deep_sleep": ("sensor.withings_tiefschlaf", "sensor.withings_deep_sleep"),
        "ha_entity_withings_light_sleep": ("sensor.withings_leichtschlaf", "sensor.withings_light_sleep"),
        "ha_entity_withings_rem_sleep": ("sensor.withings_rem_schlaf", "sensor.withings_rem_sleep"),
    }

    def __init__(self) -> None:
        self.ha = HomeAssistantService()
        self.ai = MyWellnessAIService()
        self._ensure_schema()

    def status(self) -> dict[str, Any]:
        settings = self.settings()
        return {
            "enabled": settings["enabled"],
            "ha_configured": self.ha.configured(),
            "settings": settings,
            "latest_metrics": self.latest_metrics(),
            "latest_report": self.latest_report(),
        }

    def settings(self) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute("select * from mywellness_health_settings where id = 1").fetchone()
        if not row:
            return self._default_settings()
        item = dict(row)
        item["enabled"] = bool(item.get("enabled"))
        for field, entity_id in self.default_withings_entities.items():
            if not item.get(field):
                item[field] = entity_id
        return item

    def update_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        allowed = {"enabled", *self.entity_fields}
        updates = {key: payload[key] for key in payload if key in allowed}
        if not updates:
            return self.settings()
        fields = ", ".join(f"{key} = ?" for key in updates)
        values = [1 if value is True else 0 if value is False else str(value or "").strip() for value in updates.values()]
        with self._connect() as connection:
            connection.execute(
                f"update mywellness_health_settings set {fields}, updated_at = ? where id = 1",
                (*values, utc_now()),
            )
            connection.commit()
        return self.settings()

    def import_from_ha(self) -> dict[str, Any]:
        settings = self.settings()
        raw_states: dict[str, Any] = {}
        metrics: dict[str, Any] = {
            "metric_date": date.today().isoformat(),
            "source": "home_assistant",
        }
        errors: list[str] = []
        for metric_name, entity_field in self.metric_fields.items():
            entity_id = settings.get(entity_field)
            try:
                state = self.ha.get_state(entity_id)
            except Exception as exc:
                errors.append(str(exc))
                state = None
            raw_states[entity_field] = {
                "entity_id": entity_id,
                "state": state,
            }
            metrics[metric_name] = self._numeric_state(state)

        item = self._insert_metrics(metrics, raw_states)
        self._save_health_history(item, raw_states, source="homeassistant")
        return {"metrics": item, "errors": errors}

    def withings_entities(self) -> dict[str, Any]:
        settings = self.settings()
        return {
            "entities": {field: settings.get(field) or "" for field in self.withings_metric_fields.values()},
            "configured": any(settings.get(field) for field in self.withings_metric_fields.values()),
        }

    def import_withings_metrics_from_ha(self) -> dict[str, Any]:
        settings = self.settings()
        mapping, mapping_source = self._withings_mapping(settings)
        raw_states: dict[str, Any] = {}
        metrics: dict[str, Any] = {
            "metric_date": date.today().isoformat(),
            "source": "home_assistant_withings",
        }
        missing: list[str] = []
        for metric_name, entity_field in self.withings_metric_fields.items():
            entity_id, state = self._first_available_state(entity_field, mapping.get(entity_field))
            if not state and (mapping.get(entity_field) or self.withings_entity_aliases.get(entity_field)):
                missing.append(entity_field)
            raw_states[entity_field] = self._raw_state(entity_id, state)
            metrics[metric_name] = self._metric_value(state, metric_name)
        raw_states["mapping_source"] = mapping_source
        item = self._insert_metrics(metrics, raw_states)
        self._save_health_history(item, raw_states, source="withings")
        return {"metrics": item, "missing": missing, "mapping_source": mapping_source}

    def latest_withings(self) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                """
                select * from mywellness_health_metrics
                where source = 'home_assistant_withings'
                order by metric_date desc, id desc
                limit 1
                """
            ).fetchone()
        return {"metrics": self._decode_metric(dict(row)) if row else None}

    def discover_withings_entities(self) -> dict[str, Any]:
        try:
            states = self.ha.get_states()
        except Exception as exc:
            return {"candidates": [], "error": str(exc)}
        return {"candidates": self._discover_candidates_from_states(states)}

    def metrics(self, limit: int = 30) -> dict[str, Any]:
        with self._connect() as connection:
            rows = connection.execute(
                "select * from mywellness_health_metrics order by metric_date desc, id desc limit ?",
                (min(max(limit, 1), 365),),
            ).fetchall()
        return {"metrics": [self._decode_metric(dict(row)) for row in rows]}

    def analyze(self) -> dict[str, Any]:
        metrics = self.latest_metrics()
        if metrics is None:
            metrics = self._insert_metrics(
                {"metric_date": date.today().isoformat(), "source": "manual"},
                {"note": "Keine Health-Metriken vorhanden."},
            )
        scores = self._scores(metrics)
        courses = self._recent_courses()
        history_context = self._history_context()
        payload = {
            "user_profile": self._profile_payload(),
            "metrics": self._ai_metrics(metrics),
            "withings": self._withings_payload(metrics),
            "history_context": history_context,
            "recovery_score": scores["recovery_score"],
            "stress_score": scores["stress_score"],
            "training_readiness": scores["training_readiness"],
            "last_mywellness_courses": courses["recent_courses"],
            "desired_courses": courses["desired_courses"],
        }
        ai_raw: dict[str, Any]
        try:
            ai_raw = self.ai.analyze(payload)
            ai_error = ""
        except Exception as exc:
            ai_error = str(exc)
            ai_raw = self.ai.fallback(scores, ai_error)

        report = {
            "report_date": date.today().isoformat(),
            "recovery_score": scores["recovery_score"],
            "stress_score": scores["stress_score"],
            "training_readiness": ai_raw.get("training_readiness", scores["training_readiness"]),
            "recovery_state": ai_raw.get("recovery_state"),
            "stress_level": ai_raw.get("stress_level"),
            "should_train_today": bool(ai_raw.get("should_train_today")),
            "recommended_workout_type": ai_raw.get("recommended_workout_type"),
            "summary": ai_raw.get("summary"),
            "recommendation": ai_raw.get("recommendation"),
            "warnings_json": json.dumps(ai_raw.get("warnings") or [], ensure_ascii=False),
            "ai_raw_json": json.dumps({**ai_raw, "error": ai_error} if ai_error else ai_raw, ensure_ascii=False),
        }
        inserted_report = self._insert_report(report)
        self._save_recovery_history(inserted_report, ai_raw, payload)
        self._create_recovery_message(inserted_report)
        return {"report": inserted_report, "metrics": metrics}

    def latest_report(self) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "select * from mywellness_recovery_reports order by report_date desc, id desc limit 1"
            ).fetchone()
        return self._decode_report(dict(row)) if row else None

    def reports(self, limit: int = 30) -> dict[str, Any]:
        with self._connect() as connection:
            rows = connection.execute(
                "select * from mywellness_recovery_reports order by report_date desc, id desc limit ?",
                (min(max(limit, 1), 365),),
            ).fetchall()
        return {"reports": [self._decode_report(dict(row)) for row in rows]}

    def latest_metrics(self) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "select * from mywellness_health_metrics order by metric_date desc, id desc limit 1"
            ).fetchone()
        return self._decode_metric(dict(row)) if row else None

    def _history_context(self) -> dict[str, Any]:
        latest = get_latest_metrics()
        return {
            "latest_metrics": self._compact_latest_metrics(latest),
            "health_trends": {
                "weight_30d": self._trend_summary("weight", 30),
                "weight_90d": self._trend_summary("weight", 90),
                "hrv_30d": self._trend_summary("hrv", 30),
                "resting_heart_rate_90d": self._trend_summary("resting_heart_rate", 90),
                "sleep_duration_30d": self._trend_summary("sleep_duration", 30),
                "sleep_score_30d": self._trend_summary("sleep_score", 30),
                "steps_30d": self._trend_summary("steps", 30),
            },
            "recovery_30d": self._recovery_summary(30),
            "bookings_90d": self._booking_summary(90),
        }

    def _compact_latest_metrics(self, latest: dict[str, dict[str, Any]]) -> dict[str, Any]:
        compact: dict[str, Any] = {}
        for metric_name, item in latest.items():
            compact[metric_name] = {
                "value": item.get("metric_value"),
                "unit": item.get("unit"),
                "source": item.get("source"),
                "measured_at": item.get("measured_at"),
            }
        return compact

    def _trend_summary(self, metric_name: str, days: int) -> dict[str, Any]:
        rows = get_health_trend(metric_name, days)
        values = [
            {
                "value": self._float(row.get("metric_value")),
                "measured_at": row.get("measured_at"),
                "unit": row.get("unit"),
                "source": row.get("source"),
            }
            for row in rows
        ]
        values = [item for item in values if item["value"] is not None]
        if not values:
            return {"days": days, "count": 0, "status": "insufficient_data"}
        first = values[0]
        last = values[-1]
        numbers = [float(item["value"]) for item in values]
        delta = round(float(last["value"]) - float(first["value"]), 2)
        avg = round(sum(numbers) / len(numbers), 2)
        return {
            "days": days,
            "count": len(values),
            "first": {"value": first["value"], "measured_at": first["measured_at"]},
            "last": {"value": last["value"], "measured_at": last["measured_at"]},
            "delta": delta,
            "average": avg,
            "min": min(numbers),
            "max": max(numbers),
            "unit": last.get("unit") or first.get("unit"),
            "direction": self._trend_direction(delta),
        }

    def _recovery_summary(self, days: int) -> dict[str, Any]:
        rows = get_recovery_history(days)
        if not rows:
            return {"days": days, "count": 0, "status": "insufficient_data"}
        scores = [self._float(row.get("score")) for row in rows]
        scores = [score for score in scores if score is not None]
        status_counts: dict[str, int] = {}
        for row in rows:
            status = str(row.get("status") or "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
        latest = rows[0]
        return {
            "days": days,
            "count": len(rows),
            "average_score": round(sum(scores) / len(scores), 2) if scores else None,
            "min_score": min(scores) if scores else None,
            "max_score": max(scores) if scores else None,
            "status_counts": status_counts,
            "latest": {
                "score": latest.get("score"),
                "status": latest.get("status"),
                "summary": latest.get("summary"),
                "created_at": latest.get("created_at"),
            },
        }

    def _booking_summary(self, days: int) -> dict[str, Any]:
        stats = get_booking_stats(days)
        action_counts = {item["action"]: item["count"] for item in stats.get("actions", [])}
        return {
            "days": days,
            "actions": action_counts,
            "booked_count": action_counts.get("booked", 0),
            "attended_count": action_counts.get("attended", 0),
            "cancelled_count": action_counts.get("cancelled", 0),
            "frequent_courses": stats.get("frequent_courses", [])[:5],
            "preferred_hours": stats.get("by_hour", [])[:5],
        }

    def _trend_direction(self, delta: float) -> str:
        if abs(delta) < 0.01:
            return "stable"
        return "up" if delta > 0 else "down"

    def _save_health_history(self, metrics: dict[str, Any], raw_states: dict[str, Any], source: str) -> None:
        try:
            snapshot = {
                "source": source,
                "metrics": metrics,
                "raw_states": raw_states,
                "created_at": utc_now(),
            }
            save_health_snapshot(snapshot)
            field_by_metric = {**self.metric_fields, **self.withings_metric_fields}
            for metric_name, entity_field in field_by_metric.items():
                if metric_name not in metrics:
                    continue
                raw_state = raw_states.get(entity_field) if isinstance(raw_states, dict) else None
                unit = self._unit_from_raw_state(raw_state)
                measured_at = self._measured_at_from_raw_state(raw_state) or metrics.get("created_at") or utc_now()
                save_health_metric(
                    metric_name=metric_name,
                    metric_value=metrics.get(metric_name),
                    unit=unit,
                    source=source,
                    measured_at=measured_at,
                )
        except Exception:
            return

    def _save_recovery_history(self, report: dict[str, Any], ai_raw: dict[str, Any], payload: dict[str, Any]) -> None:
        try:
            save_recovery_analysis(
                score=report.get("recovery_score"),
                status=report.get("recovery_state"),
                summary=report.get("summary"),
                raw={"report": report, "ai": ai_raw, "context": payload},
                created_at=report.get("created_at"),
            )
            recommendation = report.get("recommendation")
            if recommendation:
                save_ai_recommendation(
                    recommendation_type="recovery",
                    title=report.get("recommended_workout_type") or report.get("recovery_state") or "Recovery Empfehlung",
                    recommendation=recommendation,
                    confidence=report.get("training_readiness"),
                    raw_context={"report": report, "context": payload},
                    created_at=report.get("created_at"),
                )
        except Exception:
            return

    def _create_recovery_message(self, report: dict[str, Any]) -> None:
        score = int(report.get("recovery_score") or 0)
        if score >= 70:
            title = "Recovery verbessert"
            severity = "info"
            message = f"Recovery Score liegt bei {score}. Training nach Plan ist eher möglich."
        elif score < 50:
            title = "Niedrige Recovery"
            severity = "warning"
            message = "Heute eher Regeneration einplanen."
        else:
            return
        try:
            MessagingService().create_message(
                source="mywellness",
                category="mywellness",
                severity=severity,
                title=title,
                message=message,
                payload={"report_id": report.get("id"), "recovery_score": score},
            )
        except Exception:
            return

    def _unit_from_raw_state(self, raw_state: Any) -> str | None:
        if not isinstance(raw_state, dict):
            return None
        if raw_state.get("unit"):
            return raw_state.get("unit")
        state = raw_state.get("state") if isinstance(raw_state.get("state"), dict) else None
        attributes = state.get("attributes") if state and isinstance(state.get("attributes"), dict) else {}
        return attributes.get("unit_of_measurement")

    def _measured_at_from_raw_state(self, raw_state: Any) -> str | None:
        if not isinstance(raw_state, dict):
            return None
        state = raw_state.get("state") if isinstance(raw_state.get("state"), dict) else None
        if not state:
            return None
        return state.get("last_changed") or state.get("last_updated")

    def _connect(self) -> sqlite3.Connection:
        db_path = MyWellnessService.get_db_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(db_path, timeout=30)
        connection.execute("pragma busy_timeout = 30000")
        try:
            connection.execute("pragma journal_mode = WAL")
        except sqlite3.OperationalError:
            pass
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                create table if not exists mywellness_health_metrics (
                    id integer primary key autoincrement,
                    metric_date text not null,
                    source text not null,
                    steps real,
                    active_calories real,
                    resting_heart_rate real,
                    hrv real,
                    sleep_hours real,
                    weight real,
                    blood_pressure_systolic real,
                    blood_pressure_diastolic real,
                    bmi real,
                    fat_mass real,
                    muscle_mass real,
                    body_water real,
                    sleep_score real,
                    deep_sleep_hours real,
                    light_sleep_hours real,
                    rem_sleep_hours real,
                    raw_json text not null default '{}',
                    created_at text not null,
                    updated_at text not null
                )
                """
            )
            connection.execute(
                """
                create table if not exists mywellness_recovery_reports (
                    id integer primary key autoincrement,
                    report_date text not null,
                    recovery_score integer not null,
                    stress_score integer not null,
                    training_readiness integer not null,
                    recovery_state text not null,
                    stress_level text not null,
                    should_train_today integer not null default 0,
                    recommended_workout_type text,
                    summary text,
                    recommendation text,
                    warnings_json text not null default '[]',
                    ai_raw_json text not null default '{}',
                    created_at text not null
                )
                """
            )
            connection.execute(
                """
                create table if not exists mywellness_health_settings (
                    id integer primary key check (id = 1),
                    enabled integer not null default 1,
                    profile_birth_date text,
                    profile_supplements text,
                    profile_notes text,
                    ha_entity_steps text,
                    ha_entity_active_calories text,
                    ha_entity_resting_heart_rate text,
                    ha_entity_hrv text,
                    ha_entity_sleep_hours text,
                    ha_entity_weight text,
                    ha_entity_blood_pressure_systolic text,
                    ha_entity_blood_pressure_diastolic text,
                    ha_entity_withings_weight text,
                    ha_entity_withings_bmi text,
                    ha_entity_withings_fat_mass text,
                    ha_entity_withings_muscle_mass text,
                    ha_entity_withings_body_water text,
                    ha_entity_withings_heart_rate text,
                    ha_entity_withings_systolic_blood_pressure text,
                    ha_entity_withings_diastolic_blood_pressure text,
                    ha_entity_withings_sleep_score text,
                    ha_entity_withings_sleep_duration text,
                    ha_entity_withings_deep_sleep text,
                    ha_entity_withings_light_sleep text,
                    ha_entity_withings_rem_sleep text,
                    updated_at text not null
                )
                """
            )
            self._ensure_columns(
                connection,
                "mywellness_health_metrics",
                {
                    "bmi": "real",
                    "fat_mass": "real",
                    "muscle_mass": "real",
                    "body_water": "real",
                    "sleep_score": "real",
                    "deep_sleep_hours": "real",
                    "light_sleep_hours": "real",
                    "rem_sleep_hours": "real",
                },
            )
            self._ensure_columns(
                connection,
                "mywellness_health_settings",
                {
                    "profile_birth_date": "text",
                    "profile_supplements": "text",
                    "profile_notes": "text",
                    **{field: "text" for field in self.withings_metric_fields.values()},
                },
            )
            connection.execute(
                """
                insert or ignore into mywellness_health_settings
                (id, enabled, updated_at)
                values (1, 1, ?)
                """,
                (utc_now(),),
            )
            connection.commit()

    def _default_settings(self) -> dict[str, Any]:
        return {
            "id": 1,
            "enabled": True,
            "profile_birth_date": "",
            "profile_supplements": "",
            "profile_notes": "",
            "ha_entity_steps": "",
            "ha_entity_active_calories": "",
            "ha_entity_resting_heart_rate": "",
            "ha_entity_hrv": "",
            "ha_entity_sleep_hours": "",
            "ha_entity_weight": "",
            "ha_entity_blood_pressure_systolic": "",
            "ha_entity_blood_pressure_diastolic": "",
            **self.default_withings_entities,
            "updated_at": utc_now(),
        }

    def _numeric_state(self, state: dict[str, Any] | None) -> float | None:
        if not state:
            return None
        value = state.get("state")
        if value in (None, "", "unknown", "unavailable"):
            return None
        try:
            return float(str(value).replace(",", "."))
        except ValueError:
            return None

    def _metric_value(self, state: dict[str, Any] | None, metric_name: str) -> float | None:
        value = self._numeric_state(state)
        if value is None:
            return None
        if metric_name not in {"sleep_hours", "deep_sleep_hours", "light_sleep_hours", "rem_sleep_hours"}:
            return value
        attributes = state.get("attributes") if isinstance(state.get("attributes"), dict) else {}
        unit = str(attributes.get("unit_of_measurement") or "").lower()
        if unit in {"s", "sec", "secs", "second", "seconds", "sek", "sekunden"}:
            return round(value / 3600, 2)
        if unit in {"min", "mins", "minute", "minutes", "minuten"}:
            return round(value / 60, 2)
        return value

    def _insert_metrics(self, values: dict[str, Any], raw: dict[str, Any]) -> dict[str, Any]:
        fields = [
            "metric_date",
            "source",
            "steps",
            "active_calories",
            "resting_heart_rate",
            "hrv",
            "sleep_hours",
            "weight",
            "blood_pressure_systolic",
            "blood_pressure_diastolic",
            "bmi",
            "fat_mass",
            "muscle_mass",
            "body_water",
            "sleep_score",
            "deep_sleep_hours",
            "light_sleep_hours",
            "rem_sleep_hours",
        ]
        item = {field: values.get(field) for field in fields}
        now = utc_now()
        with self._connect() as connection:
            cursor = connection.execute(
                f"""
                insert into mywellness_health_metrics
                ({", ".join(fields)}, raw_json, created_at, updated_at)
                values ({", ".join("?" for _ in fields)}, ?, ?, ?)
                """,
                (*[item[field] for field in fields], json.dumps(raw, ensure_ascii=False), now, now),
            )
            connection.commit()
            row = connection.execute("select * from mywellness_health_metrics where id = ?", (cursor.lastrowid,)).fetchone()
        return self._decode_metric(dict(row))

    def _insert_report(self, report: dict[str, Any]) -> dict[str, Any]:
        fields = [
            "report_date",
            "recovery_score",
            "stress_score",
            "training_readiness",
            "recovery_state",
            "stress_level",
            "should_train_today",
            "recommended_workout_type",
            "summary",
            "recommendation",
            "warnings_json",
            "ai_raw_json",
        ]
        with self._connect() as connection:
            cursor = connection.execute(
                f"""
                insert into mywellness_recovery_reports
                ({", ".join(fields)}, created_at)
                values ({", ".join("?" for _ in fields)}, ?)
                """,
                (*[report[field] for field in fields], utc_now()),
            )
            connection.commit()
            row = connection.execute("select * from mywellness_recovery_reports where id = ?", (cursor.lastrowid,)).fetchone()
        return self._decode_report(dict(row))

    def _scores(self, metrics: dict[str, Any]) -> dict[str, int]:
        sleep = self._float(metrics.get("sleep_hours"))
        hrv = self._float(metrics.get("hrv"))
        rhr = self._float(metrics.get("resting_heart_rate"))
        active = self._float(metrics.get("active_calories"))
        steps = self._float(metrics.get("steps"))
        sleep_score = self._float(metrics.get("sleep_score"))

        recovery = 70
        stress = 30
        if sleep_score is not None:
            if sleep_score < 55:
                recovery -= 15
                stress += 12
            elif sleep_score >= 80:
                recovery += 8
                stress -= 6
        if sleep is not None:
            if sleep < 5.5:
                recovery -= 25
                stress += 25
            elif sleep < 7:
                recovery -= 10
                stress += 10
            elif sleep >= 8:
                recovery += 10
        if hrv is not None:
            if hrv < 30:
                recovery -= 15
                stress += 20
            elif hrv >= 60:
                recovery += 10
                stress -= 10
        if rhr is not None:
            if rhr > 75:
                recovery -= 15
                stress += 18
            elif rhr < 58:
                recovery += 5
                stress -= 5
        if active is not None and active > 900:
            recovery -= 10
            stress += 10
        if steps is not None and steps > 15000:
            recovery -= 8
            stress += 8

        recovery = self._clamp(recovery)
        stress = self._clamp(stress)
        readiness = self._clamp(round(recovery * 0.65 + (100 - stress) * 0.35))
        return {"recovery_score": recovery, "stress_score": stress, "training_readiness": readiness}

    def _recent_courses(self) -> dict[str, Any]:
        with self._connect() as connection:
            prepared = connection.execute(
                """
                select title, start_time, studio, status, source
                from courses
                order by start_time desc
                limit 10
                """
            ).fetchall() if self._table_exists(connection, "courses") else []
            settings = connection.execute("select desired_courses from mywellness_settings where id = 1").fetchone()
        desired: list[str] = []
        if settings:
            try:
                desired = json.loads(settings["desired_courses"] or "[]")
            except json.JSONDecodeError:
                desired = []
        return {
            "recent_courses": [dict(row) for row in prepared],
            "desired_courses": desired,
        }

    def _table_exists(self, connection: sqlite3.Connection, table_name: str) -> bool:
        row = connection.execute(
            "select name from sqlite_master where type = 'table' and name = ?",
            (table_name,),
        ).fetchone()
        return row is not None

    def _ai_metrics(self, metrics: dict[str, Any]) -> dict[str, Any]:
        return {field: metrics.get(field) for field in self.metric_fields}

    def _profile_payload(self) -> dict[str, Any]:
        settings = self.settings()
        supplements_text = str(settings.get("profile_supplements") or "")
        if "\n" in supplements_text:
            supplements = [item.strip(" -\t") for item in supplements_text.splitlines() if item.strip(" -\t")]
        else:
            supplements = [item.strip() for item in supplements_text.split(",") if item.strip()]
        birth_date = settings.get("profile_birth_date") or None
        return {
            "birth_date": birth_date,
            "age": self._age_from_birth_date(birth_date),
            "supplements": supplements,
            "notes": settings.get("profile_notes") or None,
        }

    def _age_from_birth_date(self, value: Any) -> int | None:
        if not value:
            return None
        try:
            born = date.fromisoformat(str(value))
        except ValueError:
            return None
        today = date.today()
        return today.year - born.year - ((today.month, today.day) < (born.month, born.day))

    def _withings_payload(self, metrics: dict[str, Any]) -> dict[str, Any]:
        return {
            "weight": metrics.get("weight"),
            "bmi": metrics.get("bmi"),
            "fat_mass": metrics.get("fat_mass"),
            "muscle_mass": metrics.get("muscle_mass"),
            "body_water": metrics.get("body_water"),
            "resting_heart_rate": metrics.get("resting_heart_rate"),
            "blood_pressure_systolic": metrics.get("blood_pressure_systolic"),
            "blood_pressure_diastolic": metrics.get("blood_pressure_diastolic"),
            "sleep_score": metrics.get("sleep_score"),
            "sleep_hours": metrics.get("sleep_hours"),
            "deep_sleep_hours": metrics.get("deep_sleep_hours"),
            "light_sleep_hours": metrics.get("light_sleep_hours"),
            "rem_sleep_hours": metrics.get("rem_sleep_hours"),
        }

    def _raw_state(self, entity_id: Any, state: dict[str, Any] | None) -> dict[str, Any]:
        attributes = state.get("attributes") if state and isinstance(state.get("attributes"), dict) else {}
        return {
            "entity_id": entity_id,
            "state": state,
            "unit": attributes.get("unit_of_measurement"),
        }

    def _withings_mapping(self, settings: dict[str, Any]) -> tuple[dict[str, str], str]:
        configured = {
            field: str(settings.get(field) or "").strip()
            for field in self.withings_metric_fields.values()
            if str(settings.get(field) or "").strip()
        }
        if configured:
            return configured, "settings"
        defaults = {field: entity_id for field, entity_id in self.default_withings_entities.items() if entity_id}
        if defaults:
            return defaults, "default_withings"
        try:
            states = self.ha.get_states()
        except Exception:
            return {}, "none"
        mapping: dict[str, str] = {}
        for candidate in self._discover_candidates_from_states(states):
            suggested = str(candidate.get("suggested_metric") or "")
            entity_id = str(candidate.get("entity_id") or "")
            if suggested and entity_id and suggested not in mapping:
                mapping[suggested] = entity_id
        return mapping, "auto_discovery" if mapping else "none"

    def _discover_candidates_from_states(self, states: list[dict[str, Any]]) -> list[dict[str, Any]]:
        keywords = (
            "withings",
            "weight",
            "gewicht",
            "bmi",
            "blood_pressure",
            "blood pressure",
            "blutdruck",
            "sleep",
            "schlaf",
            "heart",
            "pulse",
            "puls",
            "fat",
            "fett",
            "muscle",
            "muskel",
            "water",
            "wasser",
        )
        candidates = []
        for state in states:
            entity_id = str(state.get("entity_id") or "")
            attributes = state.get("attributes") if isinstance(state.get("attributes"), dict) else {}
            friendly = str(attributes.get("friendly_name") or "")
            haystack = f"{entity_id} {friendly}".lower()
            if "withings" not in haystack:
                continue
            if not any(keyword in haystack for keyword in keywords):
                continue
            value = state.get("state")
            if value in (None, "", "unknown", "unavailable"):
                continue
            candidates.append(
                {
                    "entity_id": entity_id,
                    "name": friendly,
                    "state": value,
                    "unit": attributes.get("unit_of_measurement"),
                    "device_class": attributes.get("device_class"),
                    "suggested_metric": self._suggest_withings_metric(haystack),
                }
            )
        return candidates

    def _first_available_state(self, entity_field: str, configured_entity: str | None) -> tuple[str | None, dict[str, Any] | None]:
        candidates: list[str] = []
        if configured_entity:
            candidates.append(str(configured_entity).strip())
        candidates.extend(self.withings_entity_aliases.get(entity_field, ()))
        seen: set[str] = set()
        for entity_id in candidates:
            if not entity_id or entity_id in seen:
                continue
            seen.add(entity_id)
            state = self.ha.fetch_entity_state(entity_id)
            if state is not None:
                return entity_id, state
        return (candidates[0] if candidates else None), None

    def _ensure_columns(self, connection: sqlite3.Connection, table_name: str, columns: dict[str, str]) -> None:
        existing = {row["name"] for row in connection.execute(f"pragma table_info({table_name})").fetchall()}
        for column, definition in columns.items():
            if column not in existing:
                connection.execute(f"alter table {table_name} add column {column} {definition}")

    def _suggest_withings_metric(self, value: str) -> str:
        if "bmi" in value:
            return "ha_entity_withings_bmi"
        if "fettmasse" in value or "fat_mass" in value or "fat mass" in value:
            return "ha_entity_withings_fat_mass"
        if "fettanteil" in value:
            return ""
        if "fettfreie" in value:
            return ""
        if "muscle" in value or "muskel" in value:
            return "ha_entity_withings_muscle_mass"
        if "water" in value or "wasser" in value:
            return "ha_entity_withings_body_water"
        if "systolic" in value:
            return "ha_entity_withings_systolic_blood_pressure"
        if "diastolic" in value:
            return "ha_entity_withings_diastolic_blood_pressure"
        if "blood_pressure" in value or "blood pressure" in value or "blutdruck" in value:
            return "ha_entity_withings_systolic_blood_pressure"
        if ("sleep" in value or "schlaf" in value) and "score" in value:
            return "ha_entity_withings_sleep_score"
        if ("deep" in value or "tief" in value) and ("sleep" in value or "schlaf" in value):
            return "ha_entity_withings_deep_sleep"
        if ("light" in value or "leicht" in value) and ("sleep" in value or "schlaf" in value):
            return "ha_entity_withings_light_sleep"
        if "rem" in value and ("sleep" in value or "schlaf" in value):
            return "ha_entity_withings_rem_sleep"
        if "sleep" in value or "schlaf" in value:
            return "ha_entity_withings_sleep_duration"
        if "heart" in value or "pulse" in value or "puls" in value or "herzschlag" in value:
            return "ha_entity_withings_heart_rate"
        if "weight" in value or "gewicht" in value:
            return "ha_entity_withings_weight"
        return ""

    def _decode_metric(self, row: dict[str, Any]) -> dict[str, Any]:
        row["raw_json"] = self._json_value(row.get("raw_json"), {})
        return row

    def _decode_report(self, row: dict[str, Any]) -> dict[str, Any]:
        row["should_train_today"] = bool(row.get("should_train_today"))
        row["warnings"] = self._json_value(row.pop("warnings_json", "[]"), [])
        row["ai_raw_json"] = self._json_value(row.get("ai_raw_json"), {})
        return row

    def _json_value(self, value: Any, default: Any) -> Any:
        try:
            return json.loads(value or "")
        except (TypeError, json.JSONDecodeError):
            return default

    def _float(self, value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _clamp(self, value: float) -> int:
        return max(0, min(100, int(round(value))))
