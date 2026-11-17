"""Kommandozeile: lzflug server | lzflug suche …"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta

from .models import Anfrage
from .search import Fortschritt, suchen

PORT = 4201


def _ziel(text: str) -> tuple[str, str]:
    t = text.strip()
    if t.lower() in ("", "ueberall", "überall", "anywhere"):
        return "ueberall", ""
    if t.lower().startswith("kontinent:"):
        return "kontinent", t.split(":", 1)[1].upper()
    if len(t) == 2:
        return "land", t.upper()
    return "flughafen", t.upper()


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="lzflug", description="Günstigste Flüge ab allen Flughäfen in der Umgebung")
    sub = p.add_subparsers(dest="befehl", required=True)

    s = sub.add_parser("server", help="Weboberfläche starten")
    s.add_argument("--port", type=int, default=PORT)
    s.add_argument("--host", default="127.0.0.1")

    q = sub.add_parser("suche", help="Suche in der Kommandozeile")
    q.add_argument("start", help="Heimatflughafen (IATA), z. B. FRA")
    q.add_argument("--ziel", default="ueberall",
                   help="IATA (BCN), Ländercode (PT), kontinent:EU oder ueberall")
    q.add_argument("--von", type=date.fromisoformat, default=date.today() + timedelta(days=14))
    q.add_argument("--bis", type=date.fromisoformat)
    q.add_argument("--naechte", type=int, help="Nächte vor Ort; ohne = nur Hinflug")
    q.add_argument("--radius", type=int, default=200)
    q.add_argument("--personen", type=int, default=1)
    q.add_argument("--gepaeck", choices=["keins", "handgepaeck", "koffer"], default="keins")
    q.add_argument("--direkt", action="store_true")
    q.add_argument("--eur-pro-km", type=float, default=0.25)
    q.add_argument("--anzahl", type=int, default=15)

    argv = sys.argv[1:] if argv is None else argv
    if not argv:  # Doppelklick / ohne Befehl: App-Modus mit Browser
        from .app import main as app_main
        app_main()
        return
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    if a.befehl == "server":
        import uvicorn
        print(f"lz-flugsuche läuft auf http://{a.host}:{a.port}")
        uvicorn.run("lzflug.server:app", host=a.host, port=a.port, log_level="warning")
        return

    art, ziel = _ziel(a.ziel)
    anfrage = Anfrage(start=a.start.upper(), ziel_art=art, ziel=ziel, von_datum=a.von,
                      bis_datum=a.bis or a.von + timedelta(days=30), naechte=a.naechte, radius_km=a.radius,
                      erwachsene=a.personen, gepaeck=a.gepaeck, nur_direkt=a.direkt, eur_pro_km=a.eur_pro_km)
    fp = Fortschritt()
    e = suchen(anfrage, fp)
    print(f"{e['ziele_mit_preis']} von {e['ziele_durchsucht']} Zielen mit Preis · Abflughäfen: "
          + ", ".join(x["iata"] for x in e["abflughaefen"]))
    for z in e["ziele"][: a.anzahl]:
        b = z["bestes"]
        rueck = f" – {b['rueck']}" if b["rueck"] else ""
        spar = f"  spart {z['ersparnis']:.0f} € ggü. {anfrage.start}" if z["ersparnis"] > 0 else ""
        print(f"{z['gesamt']:8.2f} €  {b['von']}→{b['nach']} {z['ziel'].get('ort', '')[:18]:18} {b['hin']}{rueck}"
              f"  Flug {b['preis']:.2f} € ({b['quelle']}){spar}")
    for h in e.get("hinweise", []):
        print("Hinweis:", h, file=sys.stderr)


if __name__ == "__main__":
    main()
