"""Flughafendaten: Umkreis, Länder, Kontinente, Namenssuche."""
from __future__ import annotations

import json
import math
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATEN = Path(__file__).resolve().parent.parent / "data" / "airports.json"

KONTINENTE = {
    "EU": "Europa",
    "AS": "Asien",
    "AF": "Afrika",
    "NA": "Nordamerika",
    "SA": "Südamerika",
    "OC": "Ozeanien",
    "AN": "Antarktis",
}

# Straßenkilometer sind im Mittel etwa 1,3-mal die Luftlinie.
STRASSENFAKTOR = 1.3


@dataclass(frozen=True)
class Flughafen:
    iata: str
    name: str
    ort: str
    land: str
    kontinent: str
    lat: float
    lon: float
    groesse: int  # 3 groß, 2 mittel, 1 klein

    def als_dict(self, laender: dict | None = None) -> dict:
        d = self.__dict__.copy()
        if laender is not None:
            d["land_name"] = laender.get(self.land, {}).get("name", self.land)
        return d


def km(a: Flughafen, b: Flughafen) -> float:
    """Luftlinie in km (Haversine)."""
    r = 6371.0
    p1, p2 = math.radians(a.lat), math.radians(b.lat)
    dp = p2 - p1
    dl = math.radians(b.lon - a.lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in text if not unicodedata.combining(c))


class Verzeichnis:
    def __init__(self, daten: dict):
        self.laender: dict[str, dict] = daten["laender"]
        self.alle: list[Flughafen] = [Flughafen(**f) for f in daten["flughaefen"]]
        self.nach_iata: dict[str, Flughafen] = {f.iata: f for f in self.alle}

    def get(self, iata: str) -> Flughafen | None:
        return self.nach_iata.get(iata.strip().upper())

    def im_umkreis(self, mitte: Flughafen, radius_km: float, mindestgroesse: int = 2) -> list[tuple[Flughafen, float]]:
        treffer = []
        for f in self.alle:
            if f.groesse < mindestgroesse and f.iata != mitte.iata:
                continue
            d = km(mitte, f)
            if d <= radius_km:
                treffer.append((f, d))
        return sorted(treffer, key=lambda t: t[1])

    def in_land(self, land: str, mindestgroesse: int = 2) -> list[Flughafen]:
        land = land.upper()
        return sorted((f for f in self.alle if f.land == land and f.groesse >= mindestgroesse), key=lambda f: -f.groesse)

    def in_kontinent(self, kontinent: str, mindestgroesse: int = 3) -> list[Flughafen]:
        kontinent = kontinent.upper()
        return [f for f in self.alle if f.kontinent == kontinent and f.groesse >= mindestgroesse]

    def suchen(self, text: str, grenze: int = 10) -> list[Flughafen]:
        """Findet Flughäfen über IATA, Ort oder Namen."""
        q = _norm(text.strip())
        if not q:
            return []
        exakt = self.get(text) if len(q) == 3 else None
        bewertet = []
        for f in self.alle:
            ort, name = _norm(f.ort), _norm(f.name)
            if ort.startswith(q):
                rang = 1
            elif q in ort or q in name:
                rang = 2
            else:
                continue
            bewertet.append((rang, -f.groesse, f.iata, f))
        bewertet.sort(key=lambda t: t[:3])
        ergebnis = [t[3] for t in bewertet]
        if exakt:
            ergebnis = [exakt] + [f for f in ergebnis if f.iata != exakt.iata]
        return ergebnis[:grenze]

    def laender_suchen(self, text: str) -> list[tuple[str, str]]:
        q = _norm(text.strip())
        return [(code, l["name"]) for code, l in self.laender.items() if q and (_norm(l["name"]).startswith(q) or code.casefold() == q)]


@lru_cache(maxsize=1)
def verzeichnis() -> Verzeichnis:
    return Verzeichnis(json.loads(DATEN.read_text(encoding="utf-8")))
