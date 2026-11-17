"""Ryanair-Preisfinder (farfnd): günstigster Preis zu allen Zielen ab einem Flughafen."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

import httpx

from ..models import Anfrage, Angebot

log = logging.getLogger(__name__)

BASIS = "https://www.ryanair.com/api/farfnd/v4/"
KOPF = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)", "Accept": "application/json"}


def link(von: str, nach: str, hin: str, rueck: str | None, erwachsene: int) -> str:
    s = (f"https://www.ryanair.com/de/de/trip/flights/select?adults={erwachsene}&teens=0&children=0&infants=0"
         f"&dateOut={hin}&originIata={von}&destinationIata={nach}&isReturn={'true' if rueck else 'false'}")
    if rueck:
        s += f"&dateIn={rueck}"
    return s


def _stand(ms: int | None) -> str | None:
    if not ms:
        return None
    return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat(timespec="seconds")


def ueberall(von: str, a: Anfrage, client: httpx.Client | None = None) -> list[Angebot]:
    """Ein Angebot je Ziel (günstigstes im Zeitraum). Preis ohne Gepäck, für einen Erwachsenen × Anzahl."""
    start = max(a.von_datum, date.today() + timedelta(days=1))
    if start > a.bis_datum:
        return []
    p = {
        "departureAirportIataCode": von,
        "outboundDepartureDateFrom": start.isoformat(),
        "outboundDepartureDateTo": a.bis_datum.isoformat(),
        "currency": "EUR",
        "market": "de-de",
        "adultPaxCount": a.erwachsene,
    }
    if a.hin_und_rueck:
        endpunkt = "roundTripFares"
        p.update({
            "inboundDepartureDateFrom": (start + timedelta(days=a.naechte)).isoformat(),
            "inboundDepartureDateTo": (a.bis_datum + timedelta(days=a.naechte)).isoformat(),
            "durationFrom": a.naechte,
            "durationTo": a.naechte,
        })
    else:
        endpunkt = "oneWayFares"
    eigener = client is None
    client = client or httpx.Client(timeout=25, headers=KOPF)
    try:
        r = client.get(BASIS + endpunkt, params=p)
        r.raise_for_status()
        fares = r.json().get("fares") or []
    except Exception as e:
        log.warning("Ryanair %s: %s", von, e)
        return []
    finally:
        if eigener:
            client.close()
    ergebnis = []
    for f in fares:
        hin = f["outbound"]
        zur = f.get("inbound")
        nach = hin["arrivalAirport"]["iataCode"]
        hin_d = hin["departureDate"][:10]
        zur_d = zur["departureDate"][:10] if zur else None
        preis = float(f["summary"]["price"]["value"]) * a.erwachsene
        ergebnis.append(Angebot(
            von=von, nach=nach, hin=hin_d, rueck=zur_d, preis=round(preis, 2), quelle="ryanair",
            link=link(von, nach, hin_d, zur_d, a.erwachsene),
            gepaeck="nur kleine Tasche (Ryanair-Basistarif)",
            preis_stand=_stand(hin.get("priceUpdated")),
            airline="Ryanair", flugnummern=[x["flightNumber"] for x in (hin, zur) if x],
            stopps=0, abflug=hin["departureDate"], ankunft=hin.get("arrivalDate"),
        ))
    return ergebnis
