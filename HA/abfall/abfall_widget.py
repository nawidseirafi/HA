#!/usr/bin/env python3
"""
Abfall Widget für Home Assistant
Liest die PLIST-Datei und extrahiert die nächsten Abfalltermine
"""

import plistlib
from datetime import datetime, timedelta
from pathlib import Path
import json

def get_next_appointments(plist_file_path, days_ahead=14):
    """
    Liest Abfalltermine aus der PLIST-Datei
    Gibt die nächsten Termine zurück
    """
    with open(plist_file_path, 'rb') as f:
        plist_data = plistlib.load(f)
    
    # Hole die Termine
    dates = plist_data.get('dates', [])
    categories = {item['id']: item['name'] for item in plist_data.get('categories', [])}
    
    # Heutige Datum
    today = datetime.now()
    future_date = today + timedelta(days=days_ahead)
    
    # Filtere Termine für die nächsten Tage
    upcoming = []
    for date_entry in dates:
        pickup_str = date_entry.get('pickup_date', '')
        if pickup_str:
            try:
                pickup_date = datetime.fromisoformat(pickup_str.replace('Z', '+00:00'))
                if today <= pickup_date <= future_date:
                    category_name = categories.get(date_entry.get('category_id'), 'Abfall')
                    upcoming.append({
                        'date': pickup_date.strftime('%d.%m.%Y'),
                        'time': pickup_date.strftime('%H:%M'),
                        'day': pickup_date.strftime('%A'),
                        'category': category_name,
                        'title': date_entry.get('widget_title', ''),
                        'location': date_entry.get('widget_subtitle', ''),
                        'timestamp': pickup_date.isoformat()
                    })
            except:
                pass
    
    # Sortiere nach Datum
    upcoming.sort(key=lambda x: x['timestamp'])
    
    return upcoming

def get_next_appointment(plist_file_path):
    """
    Gibt den nächsten Abfalltermin zurück
    """
    upcoming = get_next_appointments(plist_file_path, days_ahead=14)
    if upcoming:
        return upcoming[0]
    return None

def format_for_ha(appointment):
    """
    Formatiert einen Termin für Home Assistant
    """
    if not appointment:
        return "Keine Termine in den nächsten 14 Tagen"
    
    return f"{appointment['title']}"

if __name__ == '__main__':
    plist_path = Path(__file__).parent / 'abfall.plist'
    
    # Nächster Termin
    next_apt = get_next_appointment(str(plist_path))
    if next_apt:
        print("Nächster Termin:")
        print(f"  Datum: {next_apt['date']}")
        print(f"  Uhrzeit: {next_apt['time']}")
        print(f"  Kategorie: {next_apt['category']}")
        print(f"  Beschreibung: {next_apt['title']}")
        print(f"  Ort: {next_apt['location']}")
    
    # Alle Termine in den nächsten 14 Tagen
    print("\nAlle Termine (14 Tage):")
    upcoming = get_next_appointments(str(plist_path))
    for apt in upcoming:
        print(f"  - {apt['title']} ({apt['date']})")
    
    # JSON-Output für HA
    print("\nJSON für HA:")
    print(json.dumps(upcoming[:5], ensure_ascii=False, indent=2))
