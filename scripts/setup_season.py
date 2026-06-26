#!/usr/bin/env python3
"""
setup_season.py — script de SETUP, se ejecuta a mano una vez por temporada.

Este script NO toca los ficheros que usa el bot semanal
(data/calendar.json, data/drivers_wrc.json, data/drivers_f1.json).

En su lugar, genera tres ficheros "_nueva_temporada" en la misma carpeta:
    data/calendar_nueva_temporada.json
    data/drivers_wrc_nueva_temporada.json
    data/drivers_f1_nueva_temporada.json

para que los revises y corrijas a mano antes de renombrarlos / sustituir
los originales. Este script SÍ usa red (scraping + API), a diferencia de
check_porra.py que es 100% offline con datos estáticos.

Fuentes:
  - F1: API pública de Jolpica (sucesora de Ergast), devuelve JSON.
  - WRC: scraping ligero de la web oficial — es la parte más frágil,
    por eso el resultado SIEMPRE hay que revisarlo a mano.

Uso:
    python3 scripts/setup_season.py --year 2027
"""

import argparse
import json
import re
import sys
import urllib.request
import urllib.error
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"

FIA_F1_CALENDAR_URL = "https://www.fia.com/events/fia-formula-one-world-championship/season-{year}/formula-one"
FIA_F1_ENTRY_LIST_URL = "https://www.fia.com/events/fia-formula-one-world-championship/season-{year}/{year}-fia-formula-one-world-championship-entry"
FIA_WRC_CALENDAR_URL = "https://www.fia.com/events/world-rally-championship/season-{year}/events-calendar"
WRC_DRIVERS_URL = "https://www.wrc.com/en/wrc/standings/drivers/"

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; porra-setup-script/1.0)"}


def fetch_url(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return resp.read().decode(charset, errors="replace")


def fetch_json(url: str, timeout: int = 20) -> dict:
    raw = fetch_url(url, timeout=timeout)
    return json.loads(raw)


# ──────────────────────────────────────────────────────────────────────
# F1 — scraping de las páginas oficiales de la FIA
# ──────────────────────────────────────────────────────────────────────
#
# Igual que el bloque de WRC más abajo: esto es scraping best-effort.
# La FIA es una fuente más estable que la web comercial de F1/WRC, pero
# sigue siendo HTML que puede cambiar de estructura. El resultado SIEMPRE
# se revisa a mano antes de sustituir nada.

def fetch_fia_f1_calendar(year: int) -> list[dict]:
    url = FIA_F1_CALENDAR_URL.format(year=year)
    print(f"[F1] Descargando calendario desde FIA: {url}")
    try:
        html = fetch_url(url)
    except urllib.error.URLError as exc:
        print(f"[F1] AVISO: no se pudo descargar el calendario ({exc}). "
              f"Tendrás que rellenarlo a mano.", file=sys.stderr)
        return []

    # Heurística sobre bloques de evento en la página de temporada de la FIA.
    # Ajustar el patrón si la FIA cambia su HTML.
    pattern = re.compile(
        r'data-event-name="([^"]+)".{0,500}?'
        r'data-country="([^"]+)".{0,500}?'
        r'data-start-date="(\d{4}-\d{2}-\d{2})".{0,200}?'
        r'data-end-date="(\d{4}-\d{2}-\d{2})"',
        re.DOTALL,
    )
    matches = pattern.findall(html)

    calendar = []
    for i, (name, country, start, end) in enumerate(matches, start=1):
        calendar.append({
            "round": i,
            "name": name.strip(),
            "country": country.strip(),
            "flag": "",  # rellenar a mano: emoji de bandera del país
            "start": start,
            "end": end,
            "sprint": False,  # la FIA no siempre marca el sprint con claridad; revisar a mano
        })

    if not calendar:
        print("[F1] AVISO: el patrón de scraping no encontró nada en la web de la FIA. "
              "Rellena el calendario F1 a mano este año.", file=sys.stderr)
    else:
        print(f"[F1] {len(calendar)} carreras encontradas (revisar flag/sprint).")

    return calendar


def fetch_fia_f1_drivers(year: int) -> list[dict]:
    url = FIA_F1_ENTRY_LIST_URL.format(year=year)
    print(f"[F1] Descargando entry list desde FIA: {url}")
    try:
        html = fetch_url(url)
    except urllib.error.URLError as exc:
        print(f"[F1] AVISO: no se pudo descargar la entry list ({exc}). "
              f"Tendrás que rellenarla a mano.", file=sys.stderr)
        return []

    pattern = re.compile(
        r'data-driver-name="([^"]+)".{0,300}?'
        r'data-team-name="([^"]+)".{0,300}?'
        r'data-nationality="([^"]+)"',
        re.DOTALL,
    )
    matches = pattern.findall(html)

    drivers = []
    for name, team, country in matches:
        surname = name.strip().split()[-1]
        suggested_code = surname[:3].upper()  # sugerencia, revisar colisiones a mano
        drivers.append({
            "code": suggested_code,
            "name": name.strip(),
            "team": team.strip(),
            "country": country.strip(),
        })

    if not drivers:
        print("[F1] AVISO: el patrón de scraping no encontró pilotos en la entry list de la FIA. "
              "Rellena la lista F1 a mano este año.", file=sys.stderr)
    else:
        print(f"[F1] {len(drivers)} pilotos encontrados (revisar 'code', "
              "puede haber colisiones entre apellidos repetidos).")

    return drivers


# ──────────────────────────────────────────────────────────────────────
# WRC — scraping ligero (FRÁGIL a propósito: solo da un punto de partida)
# ──────────────────────────────────────────────────────────────────────

def fetch_wrc_calendar(year: int) -> list[dict]:
    """
    Scraping best-effort del calendario WRC, desde la página de la FIA
    (más estable que la web comercial de WRC, pero sigue siendo HTML
    susceptible de cambiar de estructura). Si falla o devuelve poco,
    no pasa nada: el resultado se revisa a mano de todos modos.
    """
    url = FIA_WRC_CALENDAR_URL.format(year=year)
    print(f"[WRC] Descargando calendario desde FIA: {url}")
    try:
        html = fetch_url(url)
    except urllib.error.URLError as exc:
        print(f"[WRC] AVISO: no se pudo descargar el calendario ({exc}). "
              f"Tendrás que rellenarlo a mano.", file=sys.stderr)
        return []

    # Heurística simple: buscamos bloques con nombre de rally + fechas.
    # Esto es deliberadamente tosco -- es un punto de partida, no una
    # fuente de verdad. Ajusta el patrón si la FIA cambia su HTML.
    pattern = re.compile(
        r'data-event-name="([^"]+)".{0,500}?'
        r'data-country="([^"]+)".{0,500}?'
        r'data-start-date="(\d{4}-\d{2}-\d{2})".{0,200}?'
        r'data-end-date="(\d{4}-\d{2}-\d{2})"',
        re.DOTALL,
    )
    matches = pattern.findall(html)

    calendar = []
    for i, (name, country, start, end) in enumerate(matches, start=1):
        calendar.append({
            "round": i,
            "name": name.strip(),
            "country": country.strip(),
            "flag": "",  # rellenar a mano
            "start": start,
            "end": end,
        })

    if not calendar:
        print("[WRC] AVISO: el patrón de scraping no encontró nada en la web de la FIA. "
              "Es probable que haya cambiado de estructura. "
              "Rellena el calendario WRC a mano este año.", file=sys.stderr)
    else:
        print(f"[WRC] {len(calendar)} rallies encontrados (revisar flag).")

    return calendar


def fetch_wrc_drivers() -> list[dict]:
    """
    Scraping best-effort de la tabla de pilotos Rally1 en wrc.com.
    A diferencia del calendario (que usa la FIA, más estable), aquí
    seguimos en la web comercial porque la FIA no publica una entry
    list de pilotos WRC tan clara como la de F1. Igual de frágil que
    el resto de funciones de scraping: solo es un punto de partida.
    """
    print(f"[WRC] Descargando pilotos desde {WRC_DRIVERS_URL} ...")
    try:
        html = fetch_url(WRC_DRIVERS_URL)
    except urllib.error.URLError as exc:
        print(f"[WRC] AVISO: no se pudo descargar pilotos ({exc}). "
              f"Tendrás que rellenarlo a mano.", file=sys.stderr)
        return []

    pattern = re.compile(
        r'data-driver-name="([^"]+)".{0,300}?'
        r'data-team-name="([^"]+)".{0,300}?'
        r'data-nationality="([^"]+)"',
        re.DOTALL,
    )
    matches = pattern.findall(html)

    drivers = []
    for name, team, country in matches:
        # WRC.com no expone un código de 3 letras como tal:
        # se genera una sugerencia a partir del apellido, a revisar a mano.
        surname = name.strip().split()[-1]
        suggested_code = surname[:3].upper()
        drivers.append({
            "code": suggested_code,  # SUGERENCIA, revisar colisiones a mano
            "name": name.strip(),
            "team": team.strip(),
            "country": country.strip(),
        })

    if not drivers:
        print("[WRC] AVISO: el patrón de scraping no encontró pilotos. "
              "Rellena la lista WRC a mano este año.", file=sys.stderr)
    else:
        print(f"[WRC] {len(drivers)} pilotos encontrados (revisar 'code', "
              "puede haber colisiones entre pilotos con mismo apellido).")

    return drivers


# ──────────────────────────────────────────────────────────────────────
# Escritura de ficheros de revisión
# ──────────────────────────────────────────────────────────────────────

def write_review_json(filename: str, payload) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / filename
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"  -> escrito {path}")
    return path


# ──────────────────────────────────────────────────────────────────────
# Excel/Numbers — calendario combinado, ordenado por fecha, con color
# ──────────────────────────────────────────────────────────────────────

def write_calendar_xlsx(wrc_calendar: list[dict], f1_calendar: list[dict], year: int) -> Path:
    """
    Genera un .xlsx (importable en Excel o Numbers) con columnas
    "FECHA" (fecha de la carrera, formato "MMM - dd") y "PRUEBA"
    (bandera + nombre), ordenado por fecha de inicio ascendente.
    Filas WRC en azul/blanco/negrita, filas F1 en rojo/blanco/negrita.
    """
    from datetime import date as date_cls
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment

    rows = []
    for race in wrc_calendar:
        rows.append({
            "categoria": "WRC",
            "fecha": date_cls.fromisoformat(race["start"]),
            "prueba": f"{race.get('flag', '')} {race['name']}".strip(),
        })
    for race in f1_calendar:
        rows.append({
            "categoria": "F1",
            "fecha": date_cls.fromisoformat(race["start"]),
            "prueba": f"{race.get('flag', '')} {race['name']}".strip(),
        })

    rows.sort(key=lambda r: r["fecha"])

    wb = Workbook()
    sheet = wb.active
    sheet.title = f"Calendario {year}"

    sheet["A1"] = "FECHA"
    sheet["B1"] = "PRUEBA"
    sheet["A1"].font = Font(bold=True)
    sheet["B1"].font = Font(bold=True)
    sheet.column_dimensions["A"].width = 14
    sheet.column_dimensions["B"].width = 45

    wrc_fill = PatternFill("solid", start_color="1F4E96", end_color="1F4E96")  # azul
    f1_fill = PatternFill("solid", start_color="C00000", end_color="C00000")   # rojo
    white_bold = Font(bold=True, color="FFFFFF")

    for i, row in enumerate(rows, start=2):
        fill = wrc_fill if row["categoria"] == "WRC" else f1_fill

        fecha_cell = sheet.cell(row=i, column=1, value=row["fecha"])
        fecha_cell.font = white_bold
        fecha_cell.fill = fill
        fecha_cell.alignment = Alignment(vertical="center")
        fecha_cell.number_format = "MMM - dd"

        prueba_cell = sheet.cell(row=i, column=2, value=row["prueba"])
        prueba_cell.font = white_bold
        prueba_cell.fill = fill
        prueba_cell.alignment = Alignment(vertical="center")

    path = DATA_DIR / f"calendario_{year}.xlsx"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    print(f"  -> escrito {path} ({len(rows)} pruebas, ordenadas por fecha)")
    return path


def main():
    parser = argparse.ArgumentParser(
        description="Genera ficheros _nueva_temporada para revisión manual."
    )
    parser.add_argument("--year", type=int, required=True,
                         help="Año de la nueva temporada, p.ej. 2027")
    parser.add_argument("--skip-wrc", action="store_true",
                         help="No intentar el scraping de WRC (solo F1)")
    parser.add_argument("--skip-f1", action="store_true",
                         help="No consultar la API de F1 (solo WRC)")
    args = parser.parse_args()

    print(f"=== Setup temporada {args.year} ===\n")

    if not args.skip_f1:
        try:
            f1_calendar = fetch_fia_f1_calendar(args.year)
            f1_drivers = fetch_fia_f1_drivers(args.year)
        except (urllib.error.URLError, json.JSONDecodeError) as exc:
            print(f"[F1] ERROR obteniendo datos: {exc}", file=sys.stderr)
            f1_calendar, f1_drivers = [], []
    else:
        print("[F1] Saltado por --skip-f1")
        f1_calendar, f1_drivers = [], []

    print()

    if not args.skip_wrc:
        wrc_calendar = fetch_wrc_calendar(args.year)
        wrc_drivers = fetch_wrc_drivers()
    else:
        print("[WRC] Saltado por --skip-wrc")
        wrc_calendar, wrc_drivers = [], []

    print("\n=== Escribiendo ficheros de revisión ===")

    calendar_payload = {
        "wrc": wrc_calendar,
        "f1": f1_calendar,
        "_notes": (
            f"Generado por setup_season.py para {args.year} a partir de las páginas "
            "de la FIA (fia.com). REVISAR A MANO antes de sustituir data/calendar.json: "
            "comprobar fechas, banderas, países, y cualquier carrera "
            "cancelada/aplazada (sponsors, conflictos, etc. no se detectan "
            "automáticamente)."
        ),
    }
    write_review_json("calendar_nueva_temporada.json", calendar_payload)
    write_review_json("drivers_wrc_nueva_temporada.json", wrc_drivers)
    write_review_json("drivers_f1_nueva_temporada.json", f1_drivers)

    write_calendar_xlsx(wrc_calendar, f1_calendar, args.year)

    print(
        "\nListo. Revisa y corrige a mano los 3 ficheros en data/*_nueva_temporada.json.\n"
        "Cuando estén correctos, renómbralos (quitando '_nueva_temporada') para "
        "sustituir a los que usa el bot semanal:\n"
        "    data/calendar_nueva_temporada.json   -> data/calendar.json\n"
        "    data/drivers_wrc_nueva_temporada.json -> data/drivers_wrc.json\n"
        "    data/drivers_f1_nueva_temporada.json  -> data/drivers_f1.json\n"
    )


if __name__ == "__main__":
    main()
