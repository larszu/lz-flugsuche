"""Web-Oberfläche und API. Start: lzflug server  →  http://127.0.0.1:4201"""
from __future__ import annotations

import threading
import uuid
from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__, db
from .airports import KONTINENTE, verzeichnis
from .models import Anfrage
from .search import Fortschritt, suchen

STATIC = Path(__file__).resolve().parent / "static"
app = FastAPI(title="lz-flugsuche", version=__version__)


class SuchEingabe(BaseModel):
    start: str = Field(min_length=3, max_length=3)
    ziel_art: Literal["flughafen", "land", "kontinent", "ueberall"]
    ziel: str = ""
    von_datum: date
    bis_datum: date
    naechte: int | None = Field(default=None, ge=1, le=60)
    radius_km: int = Field(default=200, ge=0, le=600)
    erwachsene: int = Field(default=1, ge=1, le=9)
    gepaeck: Literal["keins", "handgepaeck", "koffer"] = "keins"
    nur_direkt: bool = False
    eur_pro_km: float = Field(default=0.25, ge=0, le=3)
    live_pruefen: int = Field(default=8, ge=0, le=20)


class Auftrag:
    def __init__(self, a: Anfrage):
        self.anfrage = a
        self.fp = Fortschritt()
        self.stopp = threading.Event()
        self.ergebnis: dict | None = None
        self.fertig = False
        self.fehler: str | None = None


AUFTRAEGE: dict[str, Auftrag] = {}


def _ausfuehren(auftrag: Auftrag) -> None:
    def zwischen(e: dict) -> None:
        auftrag.ergebnis = e

    try:
        e = suchen(auftrag.anfrage, auftrag.fp, auftrag.stopp, zwischen)
        db.verlauf_ergaenzen(e)
        db.speichern(e)
        auftrag.ergebnis = e
    except Exception as ex:  # Fehler sichtbar machen statt still abbrechen
        auftrag.fehler = str(ex)
    finally:
        auftrag.fertig = True


@app.get("/api/info")
def info():
    return {"version": __version__, "kontinente": KONTINENTE}


@app.get("/api/flughaefen")
def flughaefen(q: str):
    v = verzeichnis()
    return [f.als_dict(v.laender) for f in v.suchen(q)]


@app.get("/api/laender")
def laender():
    v = verzeichnis()
    belegt = {f.land for f in v.alle if f.groesse >= 2}
    return sorted(({"code": c, "name": l["name"], "kontinent": l["kontinent"]} for c, l in v.laender.items() if c in belegt),
                  key=lambda x: x["name"])


@app.post("/api/suche")
def suche_starten(e: SuchEingabe):
    if e.bis_datum < e.von_datum:
        raise HTTPException(400, "Das Ende des Zeitraums liegt vor dem Anfang.")
    if (e.bis_datum - e.von_datum).days > 120:
        raise HTTPException(400, "Der Zeitraum darf höchstens 120 Tage lang sein.")
    v = verzeichnis()
    if not v.get(e.start):
        raise HTTPException(400, f"Abflughafen {e.start} ist unbekannt.")
    a = Anfrage(**{**e.model_dump(), "start": e.start.upper(), "ziel": e.ziel.upper()})
    auftrag = Auftrag(a)
    kennung = uuid.uuid4().hex[:12]
    AUFTRAEGE[kennung] = auftrag
    threading.Thread(target=_ausfuehren, args=(auftrag,), daemon=True).start()
    return {"id": kennung}


@app.get("/api/suche/{kennung}")
def suche_stand(kennung: str):
    auftrag = AUFTRAEGE.get(kennung)
    if not auftrag:
        raise HTTPException(404, "Suche nicht gefunden.")
    fp = auftrag.fp
    return {
        "fertig": auftrag.fertig,
        "fehler": auftrag.fehler,
        "fortschritt": {"schritt": fp.schritt, "erledigt": fp.erledigt, "gesamt": fp.gesamt},
        "ergebnis": auftrag.ergebnis,
    }


@app.delete("/api/suche/{kennung}")
def suche_stoppen(kennung: str):
    auftrag = AUFTRAEGE.get(kennung)
    if auftrag:
        auftrag.stopp.set()
    return {"ok": True}


@app.get("/")
def start():
    return FileResponse(STATIC / "index.html")


app.mount("/", StaticFiles(directory=STATIC), name="static")
