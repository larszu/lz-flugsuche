"""Google Flights über die Bibliothek fli (PyPI: flights)."""
from __future__ import annotations

import logging
import threading
import time
import urllib.parse
from datetime import date, timedelta

from fli.models import (
    Airport,
    BagsFilter,
    DateSearchFilters,
    FlightSearchFilters,
    FlightSegment,
    MaxStops,
    PassengerInfo,
    SortBy,
    TripType,
)
from fli.search import SearchDates, SearchFlights

from ..models import GEPAECK_TEXT, Anfrage, Angebot

log = logging.getLogger(__name__)

# Google drosselt mit HTTP 429, wenn zu viel gleichzeitig kommt.
GLEICHZEITIG = 2
PAUSE_BEI_429 = 20.0
_ampel = threading.Semaphore(GLEICHZEITIG)
_pause_bis = 0.0
_pause_lock = threading.Lock()
gebremst = 0  # Zähler für Hinweise in der Oberfläche


def _gedrosselt(fn):
    """Führt fn mit begrenzter Gleichzeitigkeit aus; bei 429 Pause und ein zweiter Versuch."""
    global _pause_bis, gebremst
    for versuch in range(2):
        warten = _pause_bis - time.monotonic()
        if warten > 0:
            time.sleep(warten)
        with _ampel:
            try:
                return fn()
            except Exception as e:
                if "429" not in str(e) or versuch:
                    raise
                with _pause_lock:
                    gebremst += 1
                    _pause_bis = max(_pause_bis, time.monotonic() + PAUSE_BEI_429)
                log.info("Google bremst (429) – %s s Pause", PAUSE_BEI_429)
    return None


def _ap(iata: str) -> Airport | None:
    return getattr(Airport, iata, None)


def link(von: str, nach: str, hin: str, rueck: str | None) -> str:
    q = f"Flights from {von} to {nach} on {hin}"
    if rueck:
        q += f" returning {rueck}"
    return "https://www.google.com/travel/flights?hl=de&curr=EUR&q=" + urllib.parse.quote(q)


def _bags(a: Anfrage) -> BagsFilter | None:
    if a.gepaeck == "handgepaeck":
        return BagsFilter(checked_bags=0, carry_on=True)
    if a.gepaeck == "koffer":
        return BagsFilter(checked_bags=1, carry_on=False)
    return None


def _segmente(von: Airport, nach: Airport, hin: date, rueck: date | None) -> list[FlightSegment]:
    seg = [FlightSegment(departure_airport=[[von, 0]], arrival_airport=[[nach, 0]], travel_date=hin.isoformat())]
    if rueck:
        seg.append(FlightSegment(departure_airport=[[nach, 0]], arrival_airport=[[von, 0]], travel_date=rueck.isoformat()))
    return seg


def kalender(von: str, nach: str, a: Anfrage) -> list[Angebot]:
    """Günstigster Preis je Abflugtag im Zeitraum (Google-Preiskalender, zwischengespeichert)."""
    va, na = _ap(von), _ap(nach)
    if not va or not na or von == nach:
        return []
    start = max(a.von_datum, date.today() + timedelta(days=1))
    if start > a.bis_datum:
        return []
    rueck = start + timedelta(days=a.naechte) if a.hin_und_rueck else None
    try:
        f = DateSearchFilters(
            trip_type=TripType.ROUND_TRIP if rueck else TripType.ONE_WAY,
            passenger_info=PassengerInfo(adults=a.erwachsene),
            flight_segments=_segmente(va, na, start, rueck),
            stops=MaxStops.NON_STOP if a.nur_direkt else MaxStops.ANY,
            bags=_bags(a),
            from_date=start.isoformat(),
            to_date=a.bis_datum.isoformat(),
            duration=a.naechte if rueck else None,
        )
        treffer = _gedrosselt(lambda: SearchDates().search(f, currency="EUR")) or []
    except Exception as e:  # Netz, Sperre, geändertes Format
        log.warning("Google-Kalender %s→%s: %s", von, nach, e)
        return []
    ergebnis = []
    for d in treffer:
        hin = d.date[0].date().isoformat()
        zur = d.date[1].date().isoformat() if len(d.date) > 1 else None
        ergebnis.append(Angebot(
            von=von, nach=nach, hin=hin, rueck=zur, preis=float(d.price),
            quelle="google-kalender", link=link(von, nach, hin, zur), gepaeck=GEPAECK_TEXT[a.gepaeck],
        ))
    return ergebnis


def live(von: str, nach: str, hin: str, rueck: str | None, a: Anfrage) -> Angebot | None:
    """Prüft einen Termin live und gibt das günstigste Angebot mit Details zurück."""
    va, na = _ap(von), _ap(nach)
    if not va or not na:
        return None
    try:
        f = FlightSearchFilters(
            trip_type=TripType.ROUND_TRIP if rueck else TripType.ONE_WAY,
            passenger_info=PassengerInfo(adults=a.erwachsene),
            flight_segments=_segmente(va, na, date.fromisoformat(hin), date.fromisoformat(rueck) if rueck else None),
            stops=MaxStops.NON_STOP if a.nur_direkt else MaxStops.ANY,
            bags=_bags(a),
            sort_by=SortBy.CHEAPEST,
        )
        treffer = _gedrosselt(lambda: SearchFlights().search(f, top_n=2, currency="EUR")) or []
    except Exception as e:
        log.warning("Google-Live %s→%s %s: %s", von, nach, hin, e)
        return None
    bestes = None
    for t in treffer:
        teile = t if isinstance(t, tuple) else (t,)
        preis = teile[-1].price
        if preis is None:
            continue
        if bestes is None or preis < bestes[0]:
            bestes = (preis, teile)
    if not bestes:
        return None
    preis, teile = bestes
    hinflug = teile[0]
    beine = [b for x in teile for b in x.legs]
    return Angebot(
        von=von, nach=nach, hin=hin, rueck=rueck, preis=float(preis), quelle="google-live",
        link=link(von, nach, hin, rueck), gepaeck=GEPAECK_TEXT[a.gepaeck], live=True,
        airline=hinflug.primary_airline_name or hinflug.legs[0].airline.name.lstrip("_"),
        flugnummern=[f"{b.airline.name.lstrip('_')} {b.flight_number}" for b in beine],
        stopps=hinflug.stops, dauer_min=hinflug.duration,
        abflug=hinflug.legs[0].departure_datetime.isoformat(),
        ankunft=hinflug.legs[-1].arrival_datetime.isoformat(),
        selbst_umstieg=any(bool(x.self_transfer) for x in teile),
    )
