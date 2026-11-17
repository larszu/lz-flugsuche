"""Gemeinsame Datentypen."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from typing import Literal

Gepaeck = Literal["keins", "handgepaeck", "koffer"]
ZielArt = Literal["flughafen", "land", "kontinent", "ueberall"]

GEPAECK_TEXT = {
    "keins": "nur kleine Tasche",
    "handgepaeck": "inkl. Handgepäck-Koffer",
    "koffer": "inkl. 1 Aufgabegepäck",
}


def jetzt() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Angebot:
    von: str
    nach: str
    hin: str  # ISO-Datum
    rueck: str | None
    preis: float  # Gesamtpreis für alle Reisenden, EUR
    quelle: str  # google-kalender | google-live | ryanair
    link: str
    gepaeck: str  # was im Preis enthalten ist, Klartext
    abgerufen: str = field(default_factory=jetzt)
    preis_stand: str | None = None  # wann die Quelle den Preis zuletzt aktualisiert hat
    live: bool = False
    airline: str | None = None
    flugnummern: list[str] | None = None
    stopps: int | None = None
    dauer_min: int | None = None
    abflug: str | None = None  # ISO-Zeit
    ankunft: str | None = None
    selbst_umstieg: bool | None = None

    def als_dict(self) -> dict:
        return asdict(self)


@dataclass
class Anfrage:
    start: str  # IATA des Heimatflughafens
    ziel_art: ZielArt
    ziel: str = ""  # IATA, Ländercode oder Kontinentcode; leer bei "ueberall"
    von_datum: date = field(default_factory=date.today)
    bis_datum: date = field(default_factory=date.today)
    naechte: int | None = None  # None = nur Hinflug
    radius_km: int = 200
    erwachsene: int = 1
    gepaeck: Gepaeck = "keins"
    nur_direkt: bool = False
    eur_pro_km: float = 0.25  # Anreise mit dem Auto, Hin- und Rückweg
    kmh: float = 85.0  # Durchschnitt für die Fahrzeit
    live_pruefen: int = 8  # wie viele der besten Treffer live nachgeprüft werden
    max_ziele: int = 60  # Obergrenze für Zielkandidaten aus Google

    @property
    def hin_und_rueck(self) -> bool:
        return self.naechte is not None
