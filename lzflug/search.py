"""Suchablauf: Abflughäfen im Umkreis × Zielkandidaten × Zeitraum.

1. Grobsuche: Ryanair „überallhin“ ab jedem Abflughafen und Google-Preiskalender
   vom Heimatflughafen zu jedem Zielkandidaten.
2. Ausweiten: Für die günstigsten Ziele Google-Kalender auch ab allen anderen
   Abflughäfen im Umkreis.
3. Live-Prüfung: Die besten Treffer werden bei Google live nachgefragt.
4. Bewertung: Flugpreis + Anreise zum Abflughafen = Gesamtkosten.
"""
from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Callable

from .airports import KONTINENTE, STRASSENFAKTOR, Flughafen, Verzeichnis, km, verzeichnis
from .models import Anfrage, Angebot
from .sources import google, ryanair

log = logging.getLogger(__name__)

MAX_ABFLUGHAEFEN = 8
AUSWEITEN_TOP = 8
PARALLEL = 16


@dataclass
class Fortschritt:
    schritt: str = "Vorbereiten"
    erledigt: int = 0
    gesamt: int = 0
    hinweise: list[str] = field(default_factory=list)


@dataclass
class Abflug:
    flughafen: Flughafen
    luftlinie_km: float
    strasse_km: float
    fahrzeit_min: int
    anreise_eur: float


def abflughaefen(v: Verzeichnis, a: Anfrage) -> list[Abflug]:
    heim = v.get(a.start)
    if not heim:
        raise ValueError(f"Unbekannter Flughafen: {a.start}")
    fahrten = 2 if a.hin_und_rueck else 1  # hin zum Flughafen und nach der Reise zurück
    liste = []
    for f, d in v.im_umkreis(heim, a.radius_km)[:MAX_ABFLUGHAEFEN]:
        strasse = d * STRASSENFAKTOR
        liste.append(Abflug(
            flughafen=f, luftlinie_km=round(d), strasse_km=round(strasse),
            fahrzeit_min=round(strasse / a.kmh * 60),
            anreise_eur=round(strasse * a.eur_pro_km * fahrten, 2),
        ))
    return liste


def _hauptflughaefen_je_land(v: Verzeichnis, kontinent: str | None = None) -> list[Flughafen]:
    """Größter Flughafen je Land (bei Gleichstand der erste) – für „überallhin“."""
    beste: dict[str, Flughafen] = {}
    for f in v.alle:
        if kontinent and f.kontinent != kontinent:
            continue
        if f.groesse < 2:
            continue
        b = beste.get(f.land)
        if b is None or f.groesse > b.groesse:
            beste[f.land] = f
    return list(beste.values())


def zielkandidaten(v: Verzeichnis, a: Anfrage, heim: Flughafen) -> list[Flughafen]:
    if a.ziel_art == "flughafen":
        f = v.get(a.ziel)
        if not f:
            raise ValueError(f"Unbekannter Zielflughafen: {a.ziel}")
        return [f]
    if a.ziel_art == "land":
        kandidaten = v.in_land(a.ziel)
        if not kandidaten:
            raise ValueError(f"Keine Flughäfen im Land {a.ziel}")
    elif a.ziel_art == "kontinent":
        if a.ziel.upper() not in KONTINENTE:
            raise ValueError(f"Unbekannter Kontinent: {a.ziel}")
        kontinent = a.ziel.upper()
        kandidaten = _hauptflughaefen_je_land(v, kontinent)
        bekannt = {f.iata for f in kandidaten}
        kandidaten += [f for f in v.in_kontinent(kontinent) if f.iata not in bekannt]
    else:
        kandidaten = _hauptflughaefen_je_land(v)
    # Erst die Hauptflughäfen je Land, dann nach Entfernung – nahe Ziele sind meist billiger.
    haupt = {f.iata for f in _hauptflughaefen_je_land(v)}
    kandidaten = [f for f in kandidaten if f.iata != heim.iata]
    kandidaten.sort(key=lambda f: (f.iata not in haupt, km(heim, f)))
    return kandidaten[: a.max_ziele]


def _im_ziel(v: Verzeichnis, a: Anfrage, iata: str) -> bool:
    f = v.get(iata)
    if not f:
        return False
    if a.ziel_art == "flughafen":
        return f.iata == a.ziel.upper()
    if a.ziel_art == "land":
        return f.land == a.ziel.upper()
    if a.ziel_art == "kontinent":
        return f.kontinent == a.ziel.upper()
    return True


def _parallel(aufgaben: list[Callable[[], list[Angebot] | Angebot | None]], fp: Fortschritt, stopp: threading.Event) -> list[Angebot]:
    fp.erledigt, fp.gesamt = 0, len(aufgaben)
    ergebnis: list[Angebot] = []
    with ThreadPoolExecutor(max_workers=PARALLEL) as pool:
        futs = [pool.submit(t) for t in aufgaben]
        for fut in as_completed(futs):
            fp.erledigt += 1
            if stopp.is_set():
                continue
            try:
                r = fut.result()
            except Exception as e:  # eine Quelle darf die Suche nicht beenden
                log.warning("Teilsuche fehlgeschlagen: %s", e)
                continue
            if isinstance(r, list):
                ergebnis.extend(r)
            elif r is not None:
                ergebnis.append(r)
    return ergebnis


def _billigstes(angebote: list[Angebot]) -> dict[tuple[str, str], Angebot]:
    beste: dict[tuple[str, str], Angebot] = {}
    for o in angebote:
        k = (o.von, o.nach)
        if k not in beste or o.preis < beste[k].preis:
            beste[k] = o
    return beste


def suchen(a: Anfrage, fp: Fortschritt | None = None, stopp: threading.Event | None = None,
           zwischenstand: Callable[[dict], None] | None = None) -> dict:
    v = verzeichnis()
    gebremst_vorher = google.gebremst
    fp = fp or Fortschritt()
    stopp = stopp or threading.Event()
    abfluege = abflughaefen(v, a)
    heim = abfluege[0].flughafen
    nach_iata = {x.flughafen.iata: x for x in abfluege}
    ziele = zielkandidaten(v, a, heim)
    ziel_iatas = {f.iata for f in ziele}

    if a.ziel_art == "flughafen":
        # Ein Ziel: gleich alle Abflughäfen abfragen.
        fp.schritt = "Preiskalender aller Abflughäfen"
        aufgaben = [lambda x=x: google.kalender(x.flughafen.iata, a.ziel.upper(), a) for x in abfluege]
    else:
        fp.schritt = f"Grobsuche: {len(ziele)} Ziele ab {heim.iata}, Ryanair ab {len(abfluege)} Flughäfen"
        aufgaben = [lambda z=z: google.kalender(heim.iata, z.iata, a) for z in ziele]
    aufgaben += [lambda x=x: ryanair.ueberall(x.flughafen.iata, a) for x in abfluege]
    alle = _parallel(aufgaben, fp, stopp)
    alle = [o for o in alle if _im_ziel(v, a, o.nach)]
    if a.nur_direkt:
        alle = [o for o in alle if o.stopps in (None, 0)]
    if zwischenstand:
        zwischenstand(bewerten(v, a, abfluege, alle, {heim.iata}, ziel_iatas))

    if a.ziel_art != "flughafen" and len(abfluege) > 1 and not stopp.is_set():
        beste_ziele = sorted({o.nach: o.preis for o in sorted(alle, key=lambda o: -o.preis)}.items(), key=lambda t: t[1])
        top = [z for z, _ in beste_ziele[:AUSWEITEN_TOP]]
        fp.schritt = f"Ausweiten: {len(top)} günstigste Ziele ab {len(abfluege) - 1} weiteren Abflughäfen"
        aufgaben = [lambda x=x, z=z: google.kalender(x.flughafen.iata, z, a) for x in abfluege[1:] for z in top]
        alle += _parallel(aufgaben, fp, stopp)
        if zwischenstand:
            zwischenstand(bewerten(v, a, abfluege, alle, set(nach_iata), ziel_iatas))

    if a.live_pruefen and not stopp.is_set():
        vorlaeufig = bewerten(v, a, abfluege, alle, set(nach_iata), ziel_iatas)
        pruefen = []
        # Ryanair-Preise kommen direkt von der Airline (mit Preisstand); live geprüft werden Google-Kalenderpreise.
        for z in vorlaeufig["ziele"]:
            o = z["bestes"]
            if o["quelle"] == "google-kalender":
                pruefen.append((o["von"], o["nach"], o["hin"], o["rueck"]))
            if len(pruefen) >= a.live_pruefen:
                break
        fp.schritt = f"Live-Prüfung der {len(pruefen)} besten Treffer"
        aufgaben = [lambda p=p: google.live(*p, a) for p in pruefen]
        geprueft = _parallel(aufgaben, fp, stopp)
        if len(geprueft) < len(pruefen):
            fp.hinweise.append(f"{len(pruefen) - len(geprueft)} Treffer ließen sich nicht live prüfen.")
        alle = _live_einarbeiten(alle, geprueft)

    if google.gebremst > gebremst_vorher:
        fp.hinweise.append("Google hat zwischendurch gebremst (zu viele Anfragen). Einzelne Strecken können fehlen – später erneut suchen.")
    fp.schritt = "Fertig"
    ergebnis = bewerten(v, a, abfluege, alle, set(nach_iata), ziel_iatas)
    ergebnis["hinweise"] = fp.hinweise
    return ergebnis


def _live_einarbeiten(alle: list[Angebot], geprueft: list[Angebot]) -> list[Angebot]:
    """Live-Preise ersetzen Kalenderpreise desselben Termins (auch wenn sie höher sind)."""
    schluessel = {(g.von, g.nach, g.hin, g.rueck) for g in geprueft}
    behalten = [o for o in alle if o.quelle == "ryanair" or (o.von, o.nach, o.hin, o.rueck) not in schluessel]
    return behalten + geprueft


def bewerten(v: Verzeichnis, a: Anfrage, abfluege: list[Abflug], angebote: list[Angebot],
             durchsuchte_abfluege: set[str], ziel_iatas: set[str]) -> dict:
    nach_iata = {x.flughafen.iata: x for x in abfluege}
    beste = _billigstes(angebote)
    je_ziel: dict[str, list[dict]] = {}
    for (von, nach), o in beste.items():
        ab = nach_iata.get(von)
        if not ab:
            continue
        gesamt = round(o.preis + ab.anreise_eur, 2)
        je_ziel.setdefault(nach, []).append({
            "angebot": o.als_dict(), "abflug": von, "anreise_eur": ab.anreise_eur,
            "fahrzeit_min": ab.fahrzeit_min, "strasse_km": ab.strasse_km, "gesamt": gesamt,
        })
    heim = abfluege[0].flughafen.iata
    ziele = []
    for nach, optionen in je_ziel.items():
        optionen.sort(key=lambda x: x["gesamt"])
        ab_heim = next((x for x in optionen if x["abflug"] == heim), None)
        bester = optionen[0]
        f = v.get(nach)
        ziele.append({
            "ziel": f.als_dict(v.laender) if f else {"iata": nach},
            "bestes": bester["angebot"],
            "gesamt": bester["gesamt"],
            "abflug": bester["abflug"],
            "ab_heim": ab_heim["gesamt"] if ab_heim else None,
            "ersparnis": round(ab_heim["gesamt"] - bester["gesamt"], 2) if ab_heim and bester is not ab_heim else 0,
            "optionen": optionen,
        })
    ziele.sort(key=lambda z: z["gesamt"])
    return {
        "anfrage": {**a.__dict__, "von_datum": a.von_datum.isoformat(), "bis_datum": a.bis_datum.isoformat()},
        "abflughaefen": [{**x.flughafen.als_dict(v.laender), "luftlinie_km": x.luftlinie_km, "strasse_km": x.strasse_km,
                          "fahrzeit_min": x.fahrzeit_min, "anreise_eur": x.anreise_eur,
                          "durchsucht": x.flughafen.iata in durchsuchte_abfluege or a.ziel_art == "flughafen"}
                         for x in abfluege],
        "ziele_durchsucht": len(ziel_iatas),
        "ziele_mit_preis": len(ziele),
        "ziele": ziele,
    }
