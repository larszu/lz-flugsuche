"""Kerntests ohne Netz: Flughäfen, Zielkandidaten, Bewertung mit Anreisekosten."""
from datetime import date

import pytest

from lzflug.airports import verzeichnis
from lzflug.models import Anfrage, Angebot
from lzflug.search import abflughaefen, bewerten, zielkandidaten, _live_einarbeiten
from lzflug.cli import _ziel


def angebot(von, nach, preis, quelle="google-kalender", hin="2027-01-10"):
    return Angebot(von=von, nach=nach, hin=hin, rueck=None, preis=preis, quelle=quelle, link="x", gepaeck="-")


def test_umkreis_enthaelt_hahn_und_sortiert():
    v = verzeichnis()
    a = Anfrage(start="FRA", ziel_art="ueberall", radius_km=120)
    ab = abflughaefen(v, a)
    assert ab[0].flughafen.iata == "FRA" and ab[0].anreise_eur == 0
    assert "HHN" in [x.flughafen.iata for x in ab]
    assert [x.luftlinie_km for x in ab] == sorted(x.luftlinie_km for x in ab)


def test_anreise_hin_und_rueck_doppelt():
    v = verzeichnis()
    einfach = {x.flughafen.iata: x for x in abflughaefen(v, Anfrage(start="FRA", ziel_art="ueberall", radius_km=120))}
    rund = {x.flughafen.iata: x for x in abflughaefen(v, Anfrage(start="FRA", ziel_art="ueberall", radius_km=120, naechte=3))}
    assert rund["HHN"].anreise_eur == pytest.approx(2 * einfach["HHN"].anreise_eur)


def test_suche_nach_ort_und_umlaut():
    v = verzeichnis()
    assert v.suchen("köln")[0].iata == "CGN"
    assert v.suchen("BCN")[0].iata == "BCN"


@pytest.mark.parametrize("art,ziel,pruef", [
    ("land", "PT", lambda f: f.land == "PT"),
    ("kontinent", "EU", lambda f: f.kontinent == "EU"),
    ("ueberall", "", lambda f: True),
])
def test_zielkandidaten(art, ziel, pruef):
    v = verzeichnis()
    a = Anfrage(start="FRA", ziel_art=art, ziel=ziel)
    k = zielkandidaten(v, a, v.get("FRA"))
    assert k and len(k) <= a.max_ziele and all(pruef(f) for f in k)
    assert "FRA" not in [f.iata for f in k]


def test_unbekannter_flughafen():
    with pytest.raises(ValueError):
        abflughaefen(verzeichnis(), Anfrage(start="XXX", ziel_art="ueberall"))


def test_bewertung_rechnet_anreise_ein():
    v = verzeichnis()
    a = Anfrage(start="FRA", ziel_art="flughafen", ziel="BCN", radius_km=120, eur_pro_km=0.25)
    ab = abflughaefen(v, a)
    hhn = next(x for x in ab if x.flughafen.iata == "HHN")
    e = bewerten(v, a, ab, [angebot("FRA", "BCN", 100), angebot("HHN", "BCN", 30, "ryanair")], {"FRA", "HHN"}, {"BCN"})
    z = e["ziele"][0]
    assert z["abflug"] == "HHN"
    assert z["gesamt"] == pytest.approx(30 + hhn.anreise_eur)
    assert z["ersparnis"] == pytest.approx(100 - z["gesamt"])
    # Wird die Anreise teurer als die Ersparnis, gewinnt der Heimatflughafen.
    a2 = Anfrage(start="FRA", ziel_art="flughafen", ziel="BCN", radius_km=120, eur_pro_km=3)
    ab2 = abflughaefen(v, a2)
    e2 = bewerten(v, a2, ab2, [angebot("FRA", "BCN", 100), angebot("HHN", "BCN", 30, "ryanair")], {"FRA", "HHN"}, {"BCN"})
    assert e2["ziele"][0]["abflug"] == "FRA" and e2["ziele"][0]["ersparnis"] == 0


def test_live_preis_ersetzt_kalenderpreis_auch_wenn_hoeher():
    alt = [angebot("FRA", "OPO", 47), angebot("FRA", "OPO", 60, hin="2027-01-11")]
    live = angebot("FRA", "OPO", 58, "google-live")
    neu = _live_einarbeiten(alt, [live])
    preise = sorted(o.preis for o in neu)
    assert preise == [58, 60]


def test_cli_zielarten():
    assert _ziel("ueberall") == ("ueberall", "")
    assert _ziel("PT") == ("land", "PT")
    assert _ziel("kontinent:eu") == ("kontinent", "EU")
    assert _ziel("bcn") == ("flughafen", "BCN")
