import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional
from backend.config import load_agent_section, resolve_api_path



def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_db_path() -> Path:
    config = load_agent_section("mywellness")
    return resolve_api_path(config.get("database_path"), "data/mywellness/mywellness.db")


def connect() -> sqlite3.Connection:
    database_path = get_db_path()
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path, timeout=30)
    connection.execute("pragma busy_timeout = 30000")
    try:
        connection.execute("pragma journal_mode = WAL")
    except sqlite3.OperationalError:
        pass
    connection.row_factory = sqlite3.Row
    ensure_schema(connection)
    return connection


def ensure_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        create table if not exists courses (
            id text not null,
            partition_date text not null,
            title text not null,
            studio text,
            trainer text,
            start_time text,
            end_time text,
            available_slots integer,
            waiting_list integer,
            booked integer not null default 0,
            bookable integer not null default 0,
            cancellable integer not null default 0,
            status text not null default 'available',
            category text,
            room text,
            booking_user_status text,
            source text not null,
            is_desired integer not null default 0,
            raw_json text,
            updated_at text not null,
            primary key (id, partition_date, source)
        )
        """
    )
    connection.execute(
        """
        create table if not exists agent_runs (
            id integer primary key autoincrement,
            mode text not null,
            status text not null,
            started_at text not null,
            finished_at text,
            message text
        )
        """
    )
    connection.execute(
        """
        create table if not exists health_history (
            id integer primary key autoincrement,
            metric_name text not null,
            metric_value real,
            unit text,
            source text,
            measured_at text not null,
            created_at text not null
        )
        """
    )
    connection.execute(
        """
        create table if not exists health_snapshots (
            id integer primary key autoincrement,
            snapshot_json text not null,
            created_at text not null
        )
        """
    )
    connection.execute(
        """
        create table if not exists course_history (
            id integer primary key autoincrement,
            course_id text,
            course_name text,
            trainer text,
            location text,
            start_time text,
            end_time text,
            status text,
            imported_at text
        )
        """
    )
    connection.execute(
        """
        create table if not exists booking_history (
            id integer primary key autoincrement,
            booking_id text,
            course_id text,
            action text,
            created_at text
        )
        """
    )
    connection.execute(
        """
        create table if not exists recovery_history (
            id integer primary key autoincrement,
            score real,
            status text,
            summary text,
            raw_json text,
            created_at text
        )
        """
    )
    connection.execute(
        """
        create table if not exists ai_recommendations (
            id integer primary key autoincrement,
            recommendation_type text,
            title text,
            recommendation text,
            confidence real,
            raw_context_json text,
            created_at text
        )
        """
    )
    connection.execute(
        "create index if not exists idx_health_history_metric_time on health_history(metric_name, measured_at)"
    )
    connection.execute(
        "create index if not exists idx_course_history_course_time on course_history(course_id, start_time, status)"
    )
    connection.execute(
        "create index if not exists idx_booking_history_created on booking_history(created_at)"
    )
    connection.execute(
        "create index if not exists idx_recovery_history_created on recovery_history(created_at)"
    )
    connection.commit()


def load_agent_settings() -> dict[str, Any]:
    try:
        with connect() as connection:
            row = connection.execute(
                "select days, desired_courses from mywellness_settings where id = 1"
            ).fetchone()
    except sqlite3.Error:
        row = None
    if row is None:
        return {"days": 2, "desired_courses": []}
    try:
        desired_courses = json.loads(row["desired_courses"] or "[]")
    except (TypeError, json.JSONDecodeError):
        desired_courses = []
    return {
        "days": int(row["days"] or 2),
        "desired_courses": [str(course).strip() for course in desired_courses if str(course).strip()],
    }


def replace_prepared_courses(target_date: str, event_items: Iterable[dict[str, Any]], desired_courses: Iterable[str]) -> None:
    desired = [str(course).strip() for course in desired_courses if str(course).strip()]
    courses = [
        course_from_event(item, source="prepare", is_desired=True)
        for item in event_items
        if desired and _matches_desired_course(str(item.get("name") or ""), desired)
    ]
    with connect() as connection:
        connection.execute("delete from courses where source = 'prepare'")
        upsert_courses(connection, courses)
        for course in courses:
            save_course_history(course, connection=connection)
        connection.commit()


def prepared_course_ids(target_date: str) -> dict[str, str]:
    with connect() as connection:
        rows = connection.execute(
            """
            select title, id
            from courses
            where source = 'prepare' and partition_date = ?
            order by start_time, title
            """,
            (target_date,),
        ).fetchall()
    return {row["title"]: row["id"] for row in rows}


def delete_prepared_courses(target_date: str, course_ids: Iterable[str]) -> int:
    ids = [str(course_id).strip() for course_id in course_ids if str(course_id).strip()]
    if not ids:
        return 0
    placeholders = ",".join("?" for _ in ids)
    with connect() as connection:
        cursor = connection.execute(
            f"""
            delete from courses
            where source = 'prepare'
              and partition_date = ?
              and id in ({placeholders})
            """,
            (target_date, *ids),
        )
        connection.commit()
        return int(cursor.rowcount or 0)


def list_prepared_courses(target_date: Optional[str] = None) -> list[dict[str, Any]]:
    with connect() as connection:
        if target_date:
            rows = connection.execute(
                """
                select * from courses
                where source = 'prepare' and partition_date = ?
                order by start_time, title
                """,
                (target_date,),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                select * from courses
                where source = 'prepare'
                order by partition_date desc, start_time, title
                """
            ).fetchall()
    return [course_row_to_api(row) for row in rows]


def replace_live_courses(courses: Iterable[dict[str, Any]]) -> None:
    items = list(courses)
    with connect() as connection:
        connection.execute("delete from courses where source = 'live'")
        upsert_courses(connection, [course_from_api(item, source="live") for item in items])
        for item in items:
            save_course_history(item, connection=connection)
        connection.commit()


def upsert_courses(connection: sqlite3.Connection, courses: Iterable[dict[str, Any]]) -> None:
    now = utc_now()
    for course in courses:
        connection.execute(
            """
            insert into courses (
                id, partition_date, title, studio, trainer, start_time, end_time,
                available_slots, waiting_list, booked, bookable, cancellable,
                status, category, room, booking_user_status, source, is_desired,
                raw_json, updated_at
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(id, partition_date, source) do update set
                title = excluded.title,
                studio = excluded.studio,
                trainer = excluded.trainer,
                start_time = excluded.start_time,
                end_time = excluded.end_time,
                available_slots = excluded.available_slots,
                waiting_list = excluded.waiting_list,
                booked = excluded.booked,
                bookable = excluded.bookable,
                cancellable = excluded.cancellable,
                status = excluded.status,
                category = excluded.category,
                room = excluded.room,
                booking_user_status = excluded.booking_user_status,
                is_desired = excluded.is_desired,
                raw_json = excluded.raw_json,
                updated_at = excluded.updated_at
            """,
            (
                course["id"],
                course["partition_date"],
                course["title"],
                course.get("studio"),
                course.get("trainer"),
                course.get("start_time"),
                course.get("end_time"),
                course.get("available_slots"),
                int(bool(course.get("waiting_list"))),
                int(bool(course.get("booked"))),
                int(bool(course.get("bookable"))),
                int(bool(course.get("cancellable"))),
                course.get("status") or "available",
                course.get("category"),
                course.get("room"),
                course.get("booking_user_status"),
                course.get("source") or "live",
                int(bool(course.get("is_desired"))),
                json.dumps(course.get("raw") or {}, ensure_ascii=False, sort_keys=True),
                now,
            ),
        )
    connection.commit()


def course_from_event(item: dict[str, Any], source: str, is_desired: bool = False) -> dict[str, Any]:
    partition_date = str(item.get("partitionDate") or item.get("dateStart") or "")
    start_time = _course_start_time(item, partition_date)
    end_time = _course_end_time(item, start_time)
    available_slots = item.get("availablePlaces")
    booked = bool(item.get("isParticipant"))
    waiting_list = bool(item.get("bookingHasWaitingList") or item.get("isInWaitingList"))
    status = _course_status(item, booked, available_slots, waiting_list)
    return {
        "id": str(item.get("id", "")),
        "partition_date": partition_date,
        "title": item.get("name", "Unbekannter Kurs"),
        "studio": item.get("facilityName") or "",
        "trainer": item.get("assignedTo"),
        "start_time": start_time,
        "end_time": end_time,
        "available_slots": available_slots,
        "waiting_list": waiting_list,
        "booked": booked,
        "bookable": bool(item.get("bookingAvailable")) and status in {"available", "waitlist"},
        "cancellable": False,
        "status": status,
        "category": item.get("calendarEventType") or item.get("eventTypeId"),
        "room": item.get("room"),
        "booking_user_status": item.get("bookingUserStatus"),
        "source": source,
        "is_desired": is_desired,
        "raw": item,
    }


def course_from_api(item: dict[str, Any], source: str) -> dict[str, Any]:
    partition_date = str(item.get("partitionDate") or _partition_from_start(item.get("startTime") or item.get("starts_at")))
    return {
        "id": str(item.get("id", "")),
        "partition_date": partition_date,
        "title": item.get("title") or item.get("name") or "Unbekannter Kurs",
        "studio": item.get("studio") or item.get("location") or "",
        "trainer": item.get("trainer"),
        "start_time": item.get("startTime") or item.get("starts_at"),
        "end_time": item.get("endTime") or item.get("ends_at"),
        "available_slots": item.get("availableSlots"),
        "waiting_list": item.get("waitingList"),
        "booked": item.get("booked") or item.get("is_participant"),
        "bookable": item.get("bookable"),
        "cancellable": item.get("cancellable"),
        "status": item.get("status") or item.get("booking_status") or "available",
        "category": item.get("category"),
        "room": item.get("room"),
        "booking_user_status": item.get("bookingUserStatus"),
        "source": source,
        "is_desired": item.get("is_desired"),
        "raw": item,
    }


def course_row_to_api(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "title": row["title"],
        "studio": row["studio"] or "",
        "trainer": row["trainer"],
        "startTime": row["start_time"],
        "endTime": row["end_time"],
        "availableSlots": row["available_slots"],
        "waitingList": bool(row["waiting_list"]),
        "booked": bool(row["booked"]),
        "bookable": bool(row["bookable"]),
        "cancellable": bool(row["cancellable"]),
        "status": row["status"],
        "category": row["category"],
        "partitionDate": row["partition_date"],
        "bookingUserStatus": row["booking_user_status"],
        "room": row["room"],
        "name": row["title"],
        "starts_at": row["start_time"],
        "ends_at": row["end_time"],
        "location": row["studio"],
        "booking_status": row["status"],
        "is_desired": bool(row["is_desired"]),
        "is_participant": bool(row["booked"]),
        "source": row["source"],
    }


def _normalize_course_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _matches_desired_course(course_name: str, desired_courses: Iterable[str]) -> bool:
    normalized_name = _normalize_course_name(course_name)
    if not normalized_name:
        return False
    return any(_normalize_course_name(desired) in normalized_name for desired in desired_courses)


def record_run(mode: str, status: str, started_at: str, finished_at: Optional[str] = None, message: str = "") -> None:
    with connect() as connection:
        connection.execute(
            """
            insert into agent_runs (mode, status, started_at, finished_at, message)
            values (?, ?, ?, ?, ?)
            """,
            (mode, status, started_at, finished_at, message),
        )
        connection.commit()


def save_health_metric(
    metric_name: str,
    metric_value: Any,
    unit: str | None = None,
    source: str | None = None,
    measured_at: str | None = None,
    *,
    connection: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    name = _history_metric_name(metric_name)
    if not name:
        return None
    value = _float_or_none(metric_value)
    if value is None:
        return None
    normalized_source = _history_source(source)
    measured = measured_at or utc_now()
    close_connection = connection is None
    db = connection or connect()
    try:
        latest = db.execute(
            """
            select * from health_history
            where metric_name = ? and coalesce(source, '') = coalesce(?, '')
            order by measured_at desc, id desc
            limit 1
            """,
            (name, normalized_source),
        ).fetchone()
        if latest and _float_or_none(latest["metric_value"]) == value:
            return None
        cursor = db.execute(
            """
            insert into health_history (metric_name, metric_value, unit, source, measured_at, created_at)
            values (?, ?, ?, ?, ?, ?)
            """,
            (name, value, unit, normalized_source, measured, utc_now()),
        )
        if close_connection:
            db.commit()
        row = db.execute("select * from health_history where id = ?", (cursor.lastrowid,)).fetchone()
        return dict(row) if row else None
    finally:
        if close_connection:
            db.close()


def save_health_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    with connect() as connection:
        cursor = connection.execute(
            """
            insert into health_snapshots (snapshot_json, created_at)
            values (?, ?)
            """,
            (json.dumps(snapshot, ensure_ascii=False, sort_keys=True), utc_now()),
        )
        connection.commit()
        row = connection.execute("select * from health_snapshots where id = ?", (cursor.lastrowid,)).fetchone()
    item = dict(row)
    item["snapshot_json"] = _json_value(item.get("snapshot_json"), {})
    return item


def save_course_history(course: dict[str, Any], *, connection: sqlite3.Connection | None = None) -> dict[str, Any] | None:
    imported_at = utc_now()
    course_id = str(course.get("id") or course.get("course_id") or "").strip() or None
    start_time = course.get("startTime") or course.get("starts_at") or course.get("start_time")
    status = _course_history_status(course)
    close_connection = connection is None
    db = connection or connect()
    try:
        latest = None
        if course_id:
            latest = db.execute(
                """
                select * from course_history
                where course_id = ? and coalesce(start_time, '') = coalesce(?, '')
                order by imported_at desc, id desc
                limit 1
                """,
                (course_id, start_time),
            ).fetchone()
        if latest and latest["status"] == status:
            return None
        cursor = db.execute(
            """
            insert into course_history (
                course_id, course_name, trainer, location, start_time, end_time, status, imported_at
            )
            values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                course_id,
                course.get("title") or course.get("name") or course.get("course_name"),
                course.get("trainer"),
                course.get("studio") or course.get("location") or course.get("room"),
                start_time,
                course.get("endTime") or course.get("ends_at") or course.get("end_time"),
                status,
                imported_at,
            ),
        )
        if close_connection:
            db.commit()
        row = db.execute("select * from course_history where id = ?", (cursor.lastrowid,)).fetchone()
        return dict(row) if row else None
    finally:
        if close_connection:
            db.close()


def save_booking_history(
    booking_id: str | None = None,
    course_id: str | None = None,
    action: str = "booked",
    created_at: str | None = None,
) -> dict[str, Any]:
    timestamp = created_at or utc_now()
    with connect() as connection:
        cursor = connection.execute(
            """
            insert into booking_history (booking_id, course_id, action, created_at)
            values (?, ?, ?, ?)
            """,
            (booking_id, course_id, _booking_action(action), timestamp),
        )
        connection.commit()
        row = connection.execute("select * from booking_history where id = ?", (cursor.lastrowid,)).fetchone()
    return dict(row)


def save_recovery_analysis(
    score: Any,
    status: str | None,
    summary: str | None,
    raw: dict[str, Any] | str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    raw_json = raw if isinstance(raw, str) else json.dumps(raw or {}, ensure_ascii=False, sort_keys=True)
    with connect() as connection:
        cursor = connection.execute(
            """
            insert into recovery_history (score, status, summary, raw_json, created_at)
            values (?, ?, ?, ?, ?)
            """,
            (_float_or_none(score), status, summary, raw_json, created_at or utc_now()),
        )
        connection.commit()
        row = connection.execute("select * from recovery_history where id = ?", (cursor.lastrowid,)).fetchone()
    return _decode_json_row(dict(row), "raw_json", {})


def save_ai_recommendation(
    recommendation_type: str | None,
    title: str | None,
    recommendation: str | None,
    confidence: Any = None,
    raw_context: dict[str, Any] | str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    raw_json = raw_context if isinstance(raw_context, str) else json.dumps(raw_context or {}, ensure_ascii=False, sort_keys=True)
    with connect() as connection:
        cursor = connection.execute(
            """
            insert into ai_recommendations (
                recommendation_type, title, recommendation, confidence, raw_context_json, created_at
            )
            values (?, ?, ?, ?, ?, ?)
            """,
            (recommendation_type, title, recommendation, _float_or_none(confidence), raw_json, created_at or utc_now()),
        )
        connection.commit()
        row = connection.execute("select * from ai_recommendations where id = ?", (cursor.lastrowid,)).fetchone()
    return _decode_json_row(dict(row), "raw_context_json", {})


def get_health_trend(metric_name: str, days: int = 30) -> list[dict[str, Any]]:
    since = _since(days)
    with connect() as connection:
        rows = connection.execute(
            """
            select * from health_history
            where metric_name = ? and measured_at >= ?
            order by measured_at asc, id asc
            """,
            (_history_metric_name(metric_name), since),
        ).fetchall()
    return [dict(row) for row in rows]


def get_latest_metrics() -> dict[str, dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            """
            select h.*
            from health_history h
            join (
                select metric_name, max(measured_at || printf('%012d', id)) as latest_key
                from health_history
                group by metric_name
            ) latest
              on latest.metric_name = h.metric_name
             and latest.latest_key = h.measured_at || printf('%012d', h.id)
            order by h.metric_name
            """
        ).fetchall()
    return {row["metric_name"]: dict(row) for row in rows}


def get_recovery_history(days: int = 30) -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            """
            select * from recovery_history
            where created_at >= ?
            order by created_at desc, id desc
            """,
            (_since(days),),
        ).fetchall()
    return [_decode_json_row(dict(row), "raw_json", {}) for row in rows]


def get_booking_stats(days: int = 30) -> dict[str, Any]:
    since = _since(days)
    with connect() as connection:
        by_action = connection.execute(
            """
            select action, count(*) as count
            from booking_history
            where created_at >= ?
            group by action
            order by action
            """,
            (since,),
        ).fetchall()
        frequent_courses = connection.execute(
            """
            select coalesce(ch.course_name, bh.course_id, bh.booking_id, 'unknown') as course_name,
                   count(*) as count
            from booking_history bh
            left join (
                select course_id, course_name
                from course_history
                where id in (select max(id) from course_history group by course_id)
            ) ch on ch.course_id = bh.course_id
            where bh.created_at >= ?
              and bh.action in ('booked', 'attended')
            group by course_name
            order by count desc, course_name
            limit 20
            """,
            (since,),
        ).fetchall()
        by_hour = connection.execute(
            """
            select substr(coalesce(ch.start_time, bh.created_at), 12, 2) as hour,
                   count(*) as count
            from booking_history bh
            left join (
                select course_id, start_time
                from course_history
                where id in (select max(id) from course_history group by course_id)
            ) ch on ch.course_id = bh.course_id
            where bh.created_at >= ?
              and bh.action in ('booked', 'attended')
            group by hour
            order by hour
            """,
            (since,),
        ).fetchall()
    return {
        "days": days,
        "actions": [dict(row) for row in by_action],
        "frequent_courses": [dict(row) for row in frequent_courses],
        "by_hour": [dict(row) for row in by_hour if row["hour"]],
    }


def _course_start_time(item: dict[str, Any], partition_date: str) -> Optional[str]:
    if item.get("startDateTime"):
        return str(item["startDateTime"])
    if not partition_date:
        return None
    hour = int(item.get("startHour") or 0)
    minute = int(item.get("startMinutes") or 0)
    if len(partition_date) == 8 and partition_date.isdigit():
        start = datetime(int(partition_date[:4]), int(partition_date[4:6]), int(partition_date[6:8]), hour, minute)
        return start.isoformat(timespec="minutes")
    return partition_date


def _course_end_time(item: dict[str, Any], start_time: Optional[str]) -> Optional[str]:
    if item.get("endDateTime"):
        return str(item["endDateTime"])
    if not start_time:
        return None
    try:
        start = datetime.fromisoformat(start_time)
    except ValueError:
        return None
    end = start.replace(hour=int(item.get("endHour") or start.hour), minute=int(item.get("endMinutes") or start.minute))
    if end < start:
        end += timedelta(days=1)
    return end.isoformat(timespec="minutes")


def _course_status(item: dict[str, Any], booked: bool, available_slots: Any, waiting_list: bool) -> str:
    if booked:
        return "booked"
    if item.get("isInWaitingList"):
        return "waitlist"
    if available_slots is not None and int(available_slots) <= 0:
        return "waitlist" if waiting_list else "full"
    if item.get("bookingAvailable") is False:
        return "full"
    return "available"


def _partition_from_start(value: Any) -> str:
    text = str(value or "")
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10].replace("-", "")
    if len(text) >= 8 and text[:8].isdigit():
        return text[:8]
    return ""


def _history_metric_name(value: Any) -> str:
    aliases = {
        "sleep_hours": "sleep_duration",
        "withings_heart_rate": "resting_heart_rate",
        "heart_rate": "heart_rate",
    }
    name = str(value or "").strip()
    return aliases.get(name, name)


def _history_source(value: Any) -> str:
    source = str(value or "").strip().lower()
    if source in {"home_assistant", "home-assistant", "ha"}:
        return "homeassistant"
    if source in {"home_assistant_withings", "homeassistant_withings"}:
        return "withings"
    return source


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _json_value(value: Any, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except (TypeError, json.JSONDecodeError):
        return default


def _decode_json_row(row: dict[str, Any], field: str, default: Any) -> dict[str, Any]:
    row[field] = _json_value(row.get(field), default)
    return row


def _since(days: int) -> str:
    bounded_days = min(max(int(days or 30), 1), 3650)
    return (datetime.now(timezone.utc) - timedelta(days=bounded_days)).isoformat(timespec="seconds")


def _course_history_status(course: dict[str, Any]) -> str:
    status = str(course.get("status") or course.get("booking_status") or "available").strip().lower()
    if course.get("booked") or course.get("is_participant"):
        return "booked"
    if status in {"cancelled", "canceled"}:
        return "cancelled"
    if status in {"attended", "missed", "booked"}:
        return status
    return "available"


def _booking_action(action: str) -> str:
    normalized = str(action or "").strip().lower()
    return {
        "book": "booked",
        "booking": "booked",
        "unbook": "cancelled",
        "cancel": "cancelled",
        "canceled": "cancelled",
    }.get(normalized, normalized or "booked")
