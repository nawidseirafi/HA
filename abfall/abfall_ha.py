#!/usr/bin/env python3
"""
Home Assistant Abfall-Sensor für Remondis/AWB PLIST/XML-Daten.

Erwartung:
- Die PLIST-Datei liegt standardmäßig neben diesem Script als abfall.plist
- Ausgabe ist IMMER genau ein JSON-Objekt, damit Home Assistant value_json nutzen kann

Beispiel:
  python3 /config/scripts/abfall_ha.py
  python3 /config/scripts/abfall_ha.py --file /config/scripts/abfall.plist --days 30
"""

import argparse
import json
import plistlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional


def parse_dt(value: str) -> Optional[datetime]:
    """Parse ISO datetime strings, including trailing Z."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def clean_text(value: Any) -> str:
    """Clean whitespace and odd CDATA leftovers from plist strings."""
    if value is None:
        return ""
    text = str(value)
    # Normalize heavy whitespace from plist/CDATAs
    text = " ".join(text.split())
    # Remove occasional trailing bracket artifacts seen in the captured file
    return text.replace("] ]>", "").strip()


def load_plist(path: Path) -> Dict[str, Any]:
    with path.open("rb") as f:
        return plistlib.load(f)


def build_category_map(plist_data: Dict[str, Any]) -> Dict[Any, str]:
    categories: Dict[Any, str] = {}
    for item in plist_data.get("categories", []):
        cid = item.get("id")
        name = clean_text(item.get("name")) or clean_text(item.get("title")) or "Abfall"
        if cid is not None:
            categories[cid] = name
            categories[str(cid)] = name
    return categories


def extract_waste_type(title: str, fallback: str = "Abfall") -> str:
    """Extract waste type from titles like 'Fr. 08.05., Gelber Sack'."""
    title = clean_text(title)
    if "," in title:
        return clean_text(title.split(",")[-1]) or fallback
    return title or fallback


def normalize_waste_type(waste_type: str) -> str:
    """Normalize provider-specific waste type names to stable Home Assistant keys."""
    waste_type = clean_text(waste_type)

    if waste_type.startswith("Restabfall") or waste_type in ("Restmüll", "Restmuell"):
        return "Restabfall"
    if waste_type in ("Biomüll", "Biomuell", "Bio"):
        return "Bioabfall"
    if waste_type in ("Gelbe Tonne", "Leichtverpackungen"):
        return "Gelber Sack"
    if waste_type in ("Papierabfall", "Altpapier", "Blaue Tonne"):
        return "Papier"

    return waste_type or "Abfall"


def get_appointments(plist_file_path: Path, days_ahead: int = 30) -> List[Dict[str, Any]]:
    plist_data = load_plist(plist_file_path)
    dates = plist_data.get("dates", [])
    categories = build_category_map(plist_data)

    now = datetime.now().astimezone()
    today = now.date()
    until_date = today + timedelta(days=days_ahead)

    upcoming: List[Dict[str, Any]] = []

    for date_entry in dates:
        # Common field from your current script
        pickup_str = date_entry.get("pickup_date", "")
        pickup_date = parse_dt(pickup_str)

        # Fallback: some plist structures store date-like values under other names
        if pickup_date is None:
            for key in ("date", "datetime", "timestamp"):
                pickup_date = parse_dt(date_entry.get(key, ""))
                if pickup_date is not None:
                    break

        if pickup_date is None:
            continue

        pickup_day = pickup_date.date()
        if not (today <= pickup_day <= until_date):
            continue

        category_id = date_entry.get("category_id")
        category_name = categories.get(category_id) or categories.get(str(category_id), "")

        title = clean_text(date_entry.get("widget_title"))
        if not title:
            title = clean_text(date_entry.get("title"))

        waste_type = normalize_waste_type(category_name or extract_waste_type(title))
        location = clean_text(date_entry.get("widget_subtitle") or date_entry.get("subtitle"))

        upcoming.append(
            {
                "date": pickup_date.date().isoformat(),
                "date_de": pickup_date.strftime("%d.%m.%Y"),
                "time": pickup_date.strftime("%H:%M"),
                "weekday": pickup_date.strftime("%A"),
                "type": waste_type,
                "category": waste_type,
                "category_id": category_id,
                "title": title or waste_type,
                "location": location,
                "timestamp": pickup_date.isoformat(),
                "days_until": max(0, (pickup_day - today).days),
            }
        )

    upcoming.sort(key=lambda item: item["timestamp"])
    return upcoming


def next_by_type(appointments: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    for item in appointments:
        waste_type = item.get("type") or "Abfall"
        if waste_type not in result:
            result[waste_type] = item
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default=str(Path(__file__).parent / "abfall.plist"))
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    plist_path = Path(args.file)

    try:
        appointments = get_appointments(plist_path, days_ahead=args.days)
        next_item = appointments[0] if appointments else None

        output = {
            "state": next_item["title"] if next_item else "Keine Termine",
            "next": next_item,
            "appointments": appointments[: args.limit],
            "next_by_type": next_by_type(appointments),
            "count": len(appointments),
            "source_file": str(plist_path),
            "last_run": datetime.now().astimezone().isoformat(),
        }
    except Exception as exc:
        output = {
            "state": "Fehler",
            "error": str(exc),
            "appointments": [],
            "next": None,
            "next_by_type": {},
            "count": 0,
            "last_run": datetime.now().astimezone().isoformat(),
        }

    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
