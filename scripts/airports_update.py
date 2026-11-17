"""Erzeugt lzflug/data/airports.json aus den OurAirports-Daten (gemeinfrei).

Aufruf: python scripts/airports_update.py [airports.csv countries.csv]
Ohne Argumente werden die CSVs von davidmegginson.github.io geladen.
Nur Flughäfen mit Linienverkehr und IATA-Code bleiben übrig.
"""
import csv
import io
import json
import sys
import urllib.request
from pathlib import Path

BASIS = "https://davidmegginson.github.io/ourairports-data/"
ZIEL = Path(__file__).resolve().parent.parent / "lzflug" / "data" / "airports.json"
GROESSE = {"large_airport": 3, "medium_airport": 2, "small_airport": 1}


def lesen(pfad_oder_name: str) -> list[dict]:
    if Path(pfad_oder_name).exists():
        text = Path(pfad_oder_name).read_text(encoding="utf-8")
    else:
        with urllib.request.urlopen(BASIS + pfad_oder_name, timeout=60) as r:
            text = r.read().decode("utf-8")
    return list(csv.DictReader(io.StringIO(text)))


def main() -> None:
    a_quelle, c_quelle = (sys.argv[1:3] if len(sys.argv) >= 3 else ("airports.csv", "countries.csv"))
    try:
        from babel import Locale
        de = Locale("de").territories
    except Exception:  # babel optional
        de = {}
    laender = {}
    for c in lesen(c_quelle):
        laender[c["code"]] = {"name": de.get(c["code"], c["name"]), "kontinent": c["continent"]}
    flughaefen = []
    for a in lesen(a_quelle):
        iata = (a.get("iata_code") or "").strip()
        if len(iata) != 3 or a["scheduled_service"] != "yes" or a["type"] not in GROESSE:
            continue
        flughaefen.append({
            "iata": iata,
            "name": a["name"],
            "ort": a["municipality"],
            "land": a["iso_country"],
            "kontinent": a["continent"],
            "lat": round(float(a["latitude_deg"]), 4),
            "lon": round(float(a["longitude_deg"]), 4),
            "groesse": GROESSE[a["type"]],
        })
    flughaefen.sort(key=lambda f: f["iata"])
    ZIEL.parent.mkdir(exist_ok=True)
    ZIEL.write_text(json.dumps({"laender": laender, "flughaefen": flughaefen}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(flughaefen)} Flughäfen, {len(laender)} Länder → {ZIEL}")


if __name__ == "__main__":
    main()
