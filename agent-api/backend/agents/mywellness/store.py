import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional
import yaml
from backend.paths import API_DIR



def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_db_path() -> Path:
    config_path = API_DIR / "config.yaml"
    with config_path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    db_path = config.get("agents", {}).get("my_wellness", {}).get("database_path", "data/mywellness/mywellness.db")
    return (API_DIR / db_path).resolve()


def connect() -> sqlite3.Connection:
    database_path = get_db_path()
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
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
