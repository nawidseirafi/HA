#!/usr/bin/env python3
"""
Home Assistant Abfall-Sensor für AbfallPlus/Remondis PLIST/XML-Daten.

Kann entweder eine lokale PLIST/XML-Datei lesen oder die aktuelle struktur.xml.zip
von der App-Schnittstelle herunterladen.

Beispiele:
  python3 /config/scripts/abfall_ha_api.py --file /config/scripts/abfall.plist --days 60 --limit 20

  python3 /config/scripts/abfall_ha_api.py \
    --url https://app.abfallplus.de/struktur.xml.zip \
    --app-id de.remondis.rheinland \
    --client "$ABFALLPLUS_CLIENT" \
    --days 60 --limit 20

Optionaler Cache:
  --cache /config/scripts/abfall_cache.plist
"""

import argparse
import json
import os
import plistlib
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_URL = "https://app.abfallplus.de/struktur.xml.zip"
DEFAULT_USER_AGENT = "RE:MINDER/25.1.0.0 iOS/26.4.2 Device/iPhone Screen/1179x2556"


def parse_dt(value: Any) -> Optional[datetime]:
    """Parse ISO datetime strings, including trailing Z."""
    if not value:
        return None
    try:
        text = str(value).strip()
        # Manche Quellen liefern reine Daten statt Datetime.
        if len(text) == 10 and text[4] == "-" and text[7] == "-":
            text = f"{text}T00:00:00"
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone()
    except Exception:
        return None


def clean_text(value: Any) -> str:
    """Clean whitespace and odd CDATA leftovers from plist strings."""
    if value is None:
        return ""
    text = str(value)
    text = " ".join(text.split())
    return text.replace("] ]>", "").strip()


def load_plist_bytes(raw: bytes) -> Dict[str, Any]:
    return plistlib.loads(raw)


def load_plist(path: Path) -> Dict[str, Any]:
    with path.open("rb") as f:
        return plistlib.load(f)


def build_cookie(app_id: str, client: str) -> str:
    # Name aus deinem curl. Der Wert ist URL-encodiert: app_id|client
    cookie_name = "b1737207d4988cfaf08370df05cfd18c"
    cookie_value = urllib.parse.quote(f"{app_id}|{client}", safe="")
    return f"{cookie_name}={cookie_value}"


def download_structure_zip(
    url: str,
    app_id: str,
    client: str,
    user_agent: str = DEFAULT_USER_AGENT,
    timeout: int = 30,
) -> bytes:
    data = urllib.parse.urlencode({"client": client, "app_id": app_id}).encode("utf-8")
    headers = {
        "accept": "*/*",
        "content-type": "application/x-www-form-urlencoded",
        "accept-language": "de-DE,de;q=0.9",
        "user-agent": user_agent,
        "cookie": build_cookie(app_id, client),
    }
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def plist_from_zip(raw_zip: bytes) -> Tuple[Dict[str, Any], str]:
    with zipfile.ZipFile(tempfile.SpooledTemporaryFile()) as _:
        pass


def load_plist_from_zip_bytes(raw_zip: bytes) -> Tuple[Dict[str, Any], str]:
    with tempfile.NamedTemporaryFile() as tmp:
        tmp.write(raw_zip)
        tmp.flush()
        with zipfile.ZipFile(tmp.name, "r") as zf:
            names = zf.namelist()
            candidates = [
                name for name in names
                if name.lower().endswith((".plist", ".xml"))
                and not name.endswith("/")
            ]
            if not candidates:
                raise ValueError(f"ZIP enthält keine .xml/.plist-Datei. Dateien: {names}")

            # struktur.xml bevorzugen, sonst erste XML/PLIST.
            candidates.sort(key=lambda n: ("struktur" not in n.lower(), n))
            chosen = candidates[0]
            return load_plist_bytes(zf.read(chosen)), chosen


def build_category_map(plist_data: Dict[str, Any]) -> Dict[Any, str]:
    categories: Dict[Any, str] = {}
    for item in plist_data.get("categories", []):
        cid = item.get("id") or item.get("uid") or item.get("uuid")
        name = clean_text(item.get("name")) or clean_text(item.get("title")) or clean_text(item.get("widget_title")) or "Abfall"
        if cid is not None:
            categories[cid] = name
            categories[str(cid)] = name
    return categories


def extract_waste_type(title: str, fallback: str = "Abfall") -> str:
    title = clean_text(title)
    if "," in title:
        return clean_text(title.split(",")[-1]) or fallback
    return title or fallback


def find_pickup_date(date_entry: Dict[str, Any]) -> Optional[datetime]:
    for key in ("pickup_date", "pickupDate", "date", "datetime", "timestamp", "day"):
        pickup_date = parse_dt(date_entry.get(key))
        if pickup_date is not None:
            return pickup_date

    # Fallback aus UUID, z. B. 247_20260508_247011496_17
    uuid = clean_text(date_entry.get("uuid"))
    parts = uuid.split("_")
    for part in parts:
        if len(part) == 8 and part.isdigit():
            try:
                return datetime.strptime(part, "%Y%m%d").astimezone()
            except Exception:
                pass
    return None


def find_category_id(date_entry: Dict[str, Any]) -> Any:
    for key in ("category_id", "categoryId", "category", "cat", "type_id", "typeId"):
        if key in date_entry:
            return date_entry.get(key)

    uuid = clean_text(date_entry.get("uuid"))
    if "_" in uuid:
        return uuid.split("_")[-1]
    return None


def get_appointments(plist_data: Dict[str, Any], days_ahead: int = 30) -> List[Dict[str, Any]]:
    dates = plist_data.get("dates", [])
    categories = build_category_map(plist_data)

    now = datetime.now().astimezone()
    until = now + timedelta(days=days_ahead)
    upcoming: List[Dict[str, Any]] = []

    for date_entry in dates:
        if not isinstance(date_entry, dict):
            continue

        pickup_date = find_pickup_date(date_entry)
        if pickup_date is None:
            continue

        if not (now.date() <= pickup_date.date() <= until.date()):
            continue

        category_id = find_category_id(date_entry)
        category_name = categories.get(category_id) or categories.get(str(category_id), "")

        title = clean_text(
            date_entry.get("widget_title")
            or date_entry.get("title")
            or date_entry.get("name")
        )
        waste_type = category_name or extract_waste_type(title)
        location = clean_text(date_entry.get("widget_subtitle") or date_entry.get("subtitle") or date_entry.get("location"))

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
                "days_until": max(0, (pickup_date.date() - now.date()).days),
            }
        )

    upcoming.sort(key=lambda item: (item["date"], item["type"]))
    return upcoming


def next_by_type(appointments: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    for item in appointments:
        waste_type = item.get("type") or "Abfall"
        if waste_type not in result:
            result[waste_type] = item
    return result


def load_data(args: argparse.Namespace) -> Tuple[Dict[str, Any], str]:
    if args.url:
        raw_zip = download_structure_zip(
            url=args.url,
            app_id=args.app_id,
            client=args.client,
            user_agent=args.user_agent,
            timeout=args.timeout,
        )
        plist_data, zip_member = load_plist_from_zip_bytes(raw_zip)

        if args.cache:
            cache_path = Path(args.cache)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(plistlib.dumps(plist_data))

        return plist_data, f"{args.url}#{zip_member}"

    plist_path = Path(args.file)
    return load_plist(plist_path), str(plist_path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default=str(Path(__file__).parent / "abfall.plist"), help="Lokale PLIST/XML-Datei lesen")
    parser.add_argument("--url", default="", help="ZIP-Schnittstelle lesen, z. B. https://app.abfallplus.de/struktur.xml.zip")
    parser.add_argument("--client", default=os.environ.get("ABFALLPLUS_CLIENT", ""), help="Client-ID; alternativ ENV ABFALLPLUS_CLIENT")
    parser.add_argument("--app-id", default=os.environ.get("ABFALLPLUS_APP_ID", "de.remondis.rheinland"), help="App-ID; alternativ ENV ABFALLPLUS_APP_ID")
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--cache", default="", help="Optional: geladene PLIST lokal speichern")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    try:
        if args.url and (not args.client or not args.app_id):
            raise ValueError("Bei --url müssen --client und --app-id gesetzt sein.")

        plist_data, source = load_data(args)
        appointments = get_appointments(plist_data, days_ahead=args.days)
        next_item = appointments[0] if appointments else None

        output = {
            "state": next_item["title"] if next_item else "Keine Termine",
            "next": next_item,
            "appointments": appointments[: args.limit],
            "next_by_type": next_by_type(appointments),
            "count": len(appointments),
            "source": source,
            "lastchanged": plist_data.get("lastchanged"),
            "timestamp": plist_data.get("timestamp"),
            "last_run": datetime.now().astimezone().isoformat(),
        }
    except urllib.error.HTTPError as exc:
        output = {
            "state": "Fehler",
            "error": f"HTTP {exc.code}: {exc.reason}",
            "appointments": [],
            "next": None,
            "next_by_type": {},
            "count": 0,
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
