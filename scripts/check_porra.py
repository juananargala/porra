#!/usr/bin/env python3
"""
check_porra.py — versión simplificada (datos estáticos, sin dependencias externas)

En vez de:
  - parsear feeds ICS de Google Calendar
  - scrapear la web oficial de WRC
  - llamar a la API de Jolpica para pilotos de F1

Este script lee tres ficheros estáticos del propio repo:
  - data/calendar.json      -> calendario de la temporada (WRC + F1)
  - data/drivers_wrc.json   -> pilotos Rally1 vigentes
  - data/drivers_f1.json    -> pilotos F1 vigentes

Y genera data/week.json con las carreras del domingo siguiente (hora de Madrid),
disparando una notificación push vía ntfy.sh para que el Shortcut de iOS
arranque el flujo de selección.

Estos JSON de datos se generan/actualizan una vez por temporada con un script
de "setup" aparte (manual o semi-automático) — este script NO los modifica.

Sin dependencias externas: usa solo la librería estándar (urllib en vez de requests).
"""

import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timedelta, date
from pathlib import Path
from zoneinfo import ZoneInfo

# Estructura del repo (colgando de main):
#   scripts/check_porra.py  (este fichero)
#   data/calendar.json
#   data/drivers_wrc.json
#   data/drivers_f1.json
#   data/week.json          (salida)
REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"

CALENDAR_FILE = DATA_DIR / "calendar.json"
DRIVERS_WRC_FILE = DATA_DIR / "drivers_wrc.json"
DRIVERS_F1_FILE = DATA_DIR / "drivers_f1.json"
WEEK_OUTPUT_FILE = DATA_DIR / "week.json"

MADRID_TZ = ZoneInfo("Europe/Madrid")

NTFY_TOPIC = os.environ.get("NTFY_TOPIC")  # configurado como secret/variable en GitHub Actions
NTFY_URL = f"https://ntfy.sh/{NTFY_TOPIC}" if NTFY_TOPIC else None


def load_json(path: Path):
    if not path.exists():
        print(f"ERROR: no existe {path}", file=sys.stderr)
        sys.exit(1)
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def next_sunday(today: date) -> date:
    """Domingo siguiente. Si hoy ya es domingo, devuelve hoy mismo."""
    days_ahead = (6 - today.weekday()) % 7  # weekday(): lunes=0 ... domingo=6
    return today + timedelta(days=days_ahead)


def race_covers_date(race: dict, target: date) -> bool:
    start = date.fromisoformat(race["start"])
    end = date.fromisoformat(race["end"])
    return start <= target <= end


def build_driver_lookup(drivers: list[dict]) -> dict:
    return {d["code"]: d for d in drivers}


# El workflow dispara dos cron en UTC (19:30 y 20:30) para cubrir tanto CET
# como CEST sin tener que cambiar el workflow dos veces al año. Solo UNA de
# las dos ejecuciones coincide con la hora local deseada en Madrid; la otra
# debe descartarse aquí para no duplicar la notificación.
TARGET_WEEKDAY_MADRID = 0   # lunes (datetime.weekday(): lunes=0)
TARGET_HOUR_MADRID = 20     # ejecución deseada ~20:30 hora de Madrid


def should_run(now_madrid: datetime) -> bool:
    if os.environ.get("FORCE_RUN", "").lower() in ("1", "true", "yes"):
        print("FORCE_RUN activo: se salta la comprobación de día/hora (ejecución manual de prueba).")
        return True
    return (
        now_madrid.weekday() == TARGET_WEEKDAY_MADRID
        and now_madrid.hour == TARGET_HOUR_MADRID
    )


def main():
    now_madrid = datetime.now(MADRID_TZ)

    print(f"Fecha/hora Madrid: {now_madrid.isoformat()}")

    if not should_run(now_madrid):
        print(
            "Ejecución descartada: no es la franja horaria objetivo en Madrid "
            f"(lunes ~{TARGET_HOUR_MADRID}:30). Esto es normal para el cron "
            "que no coincide con la temporada CET/CEST actual."
        )
        return

    today = now_madrid.date()
    target_sunday = next_sunday(today)
    print(f"Domingo objetivo: {target_sunday.isoformat()}")

    calendar = load_json(CALENDAR_FILE)
    drivers_wrc = load_json(DRIVERS_WRC_FILE)
    drivers_f1 = load_json(DRIVERS_F1_FILE)

    wrc_lookup = build_driver_lookup(drivers_wrc)
    f1_lookup = build_driver_lookup(drivers_f1)

    races_this_week = []

    for race in calendar.get("wrc", []):
        if race_covers_date(race, target_sunday):
            races_this_week.append({
                "category": "WRC",
                "round": race["round"],
                "name": race["name"],
                "country": race["country"],
                "flag": race["flag"],
                "date": target_sunday.isoformat(),
                "drivers": sorted(wrc_lookup.keys()),
            })

    for race in calendar.get("f1", []):
        if race_covers_date(race, target_sunday):
            races_this_week.append({
                "category": "F1",
                "round": race["round"],
                "name": race["name"],
                "country": race["country"],
                "flag": race["flag"],
                "date": target_sunday.isoformat(),
                "sprint": race.get("sprint", False),
                "drivers": sorted(f1_lookup.keys()),
            })

    week_payload = {
        "generated_at": now_madrid.isoformat(),
        "target_sunday": target_sunday.isoformat(),
        "races": races_this_week,
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with WEEK_OUTPUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(week_payload, f, ensure_ascii=False, indent=2)

    print(f"Escrito {WEEK_OUTPUT_FILE} con {len(races_this_week)} carrera(s).")

    if races_this_week:
        notify(races_this_week, target_sunday)
    else:
        print("No hay carreras WRC ni F1 el domingo objetivo. No se notifica.")


def notify(races_this_week: list[dict], target_sunday: date):
    if not NTFY_URL:
        print("AVISO: NTFY_TOPIC no configurado, no se envía notificación.", file=sys.stderr)
        return

    labels = []
    for r in races_this_week:
        sprint_tag = " (sprint)" if r.get("sprint") else ""
        labels.append(f"{r['flag']} {r['category']}{sprint_tag}: {r['name']}")

    title = f"Porra - domingo {target_sunday.strftime('%d/%m')}"
    message = "\n".join(labels)

    req = urllib.request.Request(
        NTFY_URL,
        data=message.encode("utf-8"),
        method="POST",
        headers={
            # ntfy acepta UTF-8 en el body sin problema; para la cabecera Title
            # nos quedamos en ASCII seguro (sin emoji) para evitar problemas de
            # codificación en las cabeceras HTTP.
            "Title": title,
            "Priority": "default",
            "Tags": "checkered_flag",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            print(f"Notificación ntfy enviada (status {resp.status}).")
    except urllib.error.URLError as exc:
        print(f"ERROR enviando notificación ntfy: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
