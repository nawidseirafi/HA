#!/usr/bin/env python3
"""
Home Assistant Abfall-Sensor für AbfallPlus/Remondis PLIST/XML-Daten.
"""

import sys
import sys

# Sofort loggen, bevor etwas anderes passiert
import logging
from pathlib import Path

log_file = Path(__file__).parent / "abfall_ha.log"
logging.basicConfig(
    level=logging.DEBUG,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stderr)
    ]
)
logger = logging.getLogger(__name__)
logger.info(f"=" * 80)
logger.info(f"🚀 SKRIPT START - Python {sys.version}")
logger.info(f"📁 Script Location: {Path(__file__)}")
logger.info(f"📝 Log File: {log_file}")
logger.info(f"=" * 80)

# Jetzt die restlichen Imports
import argparse
import gzip
import json
import os
import plistlib
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

logger.debug(f"✅ Alle Imports erfolgreich")

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
    logger.debug(f"📥 ZIP wird heruntergeladen von {url}")
    logger.debug(f"   App-ID: {app_id}, Client: {client[:10]}...")
    data = urllib.parse.urlencode({"client": client, "app_id": app_id}).encode("utf-8")
    headers = {
        "accept": "*/*",
        "content-type": "application/x-www-form-urlencoded",
        "accept-language": "de-DE,de;q=0.9",
        "accept-encoding": "gzip, deflate",  # Brotli NOT decoded by urllib!
        "user-agent": user_agent,
        "cookie": build_cookie(app_id, client),
    }
    try:
        request = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            logger.debug(f"📥 Raw bytes empfangen: {len(raw)} bytes, Anfang: {raw[:10].hex()}")
            
            # Dekomprimiere gzip/deflate wenn nötig
            # gzip header: 1f 8b
            # deflate: 78 9c oder 78 01
            if raw.startswith(b'\x1f\x8b'):
                logger.debug("🔓 Dekomprimiere gzip...")
                raw = gzip.decompress(raw)
                logger.debug(f"   Nach Dekompression: {len(raw)} bytes")
            elif raw.startswith(b'\x78\x9c') or raw.startswith(b'\x78\x01'):
                logger.debug("🔓 Dekomprimiere deflate...")
                import zlib
                raw = zlib.decompress(raw)
                logger.debug(f"   Nach Dekompression: {len(raw)} bytes")
            
            logger.debug(f"✅ Download erfolgreich ({len(raw)} bytes)")
            return raw
    except Exception as e:
        logger.error(f"❌ Fehler beim Download: {e}")
        raise


def plist_from_zip(raw_zip: bytes) -> Tuple[Dict[str, Any], str]:
    with zipfile.ZipFile(tempfile.SpooledTemporaryFile()) as _:
        pass


def load_plist_from_zip_bytes(raw_zip: bytes) -> Tuple[Dict[str, Any], str]:
    logger.debug(f"📦 Entpacke ZIP ({len(raw_zip)} bytes)...")
    
    # Prüfe ob es wirklich eine ZIP ist
    if raw_zip.startswith(b'PK\x03\x04'):
        logger.debug("   Format: ZIP erkannt")
        with tempfile.NamedTemporaryFile() as tmp:
            tmp.write(raw_zip)
            tmp.flush()
            with zipfile.ZipFile(tmp.name, "r") as zf:
                names = zf.namelist()
                logger.debug(f"   ZIP enthält {len(names)} Dateien: {names}")
                candidates = [
                    name for name in names
                    if name.lower().endswith((".plist", ".xml"))
                    and not name.endswith("/")
                ]
                if not candidates:
                    logger.error(f"❌ ZIP enthält keine .xml/.plist-Datei")
                    raise ValueError(f"ZIP enthält keine .xml/.plist-Datei. Dateien: {names}")

                # struktur.xml bevorzugen, sonst erste XML/PLIST.
                candidates.sort(key=lambda n: ("struktur" not in n.lower(), n))
                chosen = candidates[0]
                logger.debug(f"✅ Nutze {chosen}")
                return load_plist_bytes(zf.read(chosen)), chosen
    
    # Falls nicht ZIP, versuche direkt als XML/PLIST zu parsen
    logger.debug("   Format: XML erkannt (nicht-ZIP)")
    try:
        return load_plist_bytes(raw_zip), "struktur.xml (direkt)"
    except Exception as e:
        logger.error(f"❌ Kann XML nicht parsen: {e}")
        raise ValueError(f"Weder ZIP noch gültige XML/PLIST-Daten: {e}")


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
    logger.debug(f"📊 Daten: {len(dates)} Termine gefunden, {len(categories)} Kategorien")

    now = datetime.now().astimezone()
    until = now + timedelta(days=days_ahead)
    upcoming: List[Dict[str, Any]] = []

    for i, date_entry in enumerate(dates):
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
    logger.debug(f"✅ {len(upcoming)} Termine in den nächsten {days_ahead} Tagen gefunden")
    if upcoming:
        logger.debug(f"   Nächster: {upcoming[0]['type']} am {upcoming[0]['date_de']}")
    return upcoming


def next_by_type(appointments: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    for item in appointments:
        waste_type = item.get("type") or "Abfall"
        if waste_type not in result:
            result[waste_type] = item
    return result


def should_update_plist(plist_path: Path) -> bool:
    """Prüft ob die PLIST-Datei aktualisiert werden soll (Jahreswechsel)."""
    if not plist_path.exists():
        logger.info(f"📄 {plist_path.name} existiert nicht → wird erstellt")
        return True
    
    # Prüfe ob das Jahr unterschiedlich ist
    file_year = plist_path.stat().st_mtime
    file_date = datetime.fromtimestamp(file_year).year
    current_year = datetime.now().year
    
    if file_date != current_year:
        logger.info(f"📅 Jahreswechsel erkannt: Datei von {file_date}, aktuell {current_year} → Update")
        return True
    
    logger.debug(f"✅ {plist_path.name} ist aktuell (Jahr {current_year})")
    return False


def download_and_cache_plist(
    url: str,
    app_id: str,
    client: str,
    plist_path: Path,
    user_agent: str = DEFAULT_USER_AGENT,
    timeout: int = 30,
) -> Dict[str, Any]:
    """Lädt abfall.plist von der API herunter und speichert es lokal."""
    logger.info(f"🌐 Lade abfall.plist von API...")
    raw_zip = download_structure_zip(
        url=url,
        app_id=app_id,
        client=client,
        user_agent=user_agent,
        timeout=timeout,
    )
    plist_data, zip_member = load_plist_from_zip_bytes(raw_zip)
    
    # Speichere lokal für nächste Mal
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_bytes(plistlib.dumps(plist_data))
    logger.info(f"💾 abfall.plist gespeichert: {plist_path}")
    
    return plist_data


def main() -> None:
    logger.info(f"=" * 60)
    logger.info(f"🚀 START: Abfall-API Skript aufgerufen")
    logger.info(f"=" * 60)
    
    try:
        parser = argparse.ArgumentParser()
        parser.add_argument("--file", default=str(Path(__file__).parent / "abfall.plist"), help="Lokale PLIST-Datei (wird auto-erstellt/erneuert bei Jahreswechsel)")
        parser.add_argument("--url", default=DEFAULT_URL, help="ZIP-URL für Jahres-Update; leer lassen um nur lokal zu nutzen")
        parser.add_argument("--client", default=os.environ.get("ABFALLPLUS_CLIENT", "MjQzMjg3RTgtMzU2MS00MENELTk3RjEtOTJFMjUwMUY4MzE0"), help="Client-ID")
        parser.add_argument("--app-id", default=os.environ.get("ABFALLPLUS_APP_ID", "de.remondis.rheinland"), help="App-ID")
        parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
        parser.add_argument("--timeout", type=int, default=30)
        parser.add_argument("--days", type=int, default=30)
        parser.add_argument("--limit", type=int, default=10)
        
        logger.debug("📋 Parser erstellt")
        args = parser.parse_args()
        
        plist_path = Path(args.file)
        logger.info(f"✅ Argumente geparst:")
        logger.info(f"   Days: {args.days}, Limit: {args.limit}")
        logger.info(f"   PLIST: {plist_path}")

        # Prüfe ob Update nötig ist (Jahreswechsel oder nicht vorhanden)
        if should_update_plist(plist_path) and args.url:
            logger.info(f"🔄 Versuche Aktualisierung von der API...")
            try:
                plist_data = download_and_cache_plist(
                    url=args.url,
                    app_id=args.app_id,
                    client=args.client,
                    plist_path=plist_path,
                    user_agent=args.user_agent,
                    timeout=args.timeout,
                )
                source = f"API ({args.url})"
            except Exception as e:
                logger.warning(f"⚠️  API-Update fehlgeschlagen ({e}), nutze lokale Datei")
                if not plist_path.exists():
                    raise ValueError(f"❌ Weder API noch lokale Datei verfügbar!")
                plist_data = load_plist(plist_path)
                source = f"Lokal (Fallback) - {plist_path}"
        else:
            # Nutze lokale Datei
            if not plist_path.exists():
                raise FileNotFoundError(f"❌ {plist_path} existiert nicht und --url nicht gesetzt oder Update überflüssig")
            logger.info(f"📂 Nutze lokale Datei: {plist_path}")
            plist_data = load_plist(plist_path)
            source = f"Lokal - {plist_path}"
        
        logger.info(f"🔄 Verarbeite Termine...")
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
        logger.info(f"✅ Erfolgreich: state='{output['state']}' ({output['count']} Termine)")
    except Exception as exc:
        logger.error(f"❌ Fehler: {exc}", exc_info=True)
        output = {
            "state": "Fehler",
            "error": str(exc),
            "appointments": [],
            "next": None,
            "next_by_type": {},
            "count": 0,
            "last_run": datetime.now().astimezone().isoformat(),
        }

    logger.debug(f"📤 JSON Output ({len(json.dumps(output, ensure_ascii=False))} bytes)")
    logger.info(f"=" * 60)
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
