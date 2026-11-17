"""API ohne Netz: Flughafensuche, Länder, Eingabeprüfung, Lebenszeichen."""
from fastapi.testclient import TestClient

from lzflug import server

c = TestClient(server.app)


def test_flughafensuche_und_laender():
    assert c.get("/api/flughaefen", params={"q": "hahn"}).json()[0]["iata"] == "HHN"
    laender = c.get("/api/laender").json()
    assert {"code": "PT", "name": "Portugal", "kontinent": "EU"} in laender


def test_zeitraum_wird_geprueft():
    r = c.post("/api/suche", json={"start": "FRA", "ziel_art": "ueberall", "von_datum": "2027-02-01", "bis_datum": "2027-01-01"})
    assert r.status_code == 400
    r = c.post("/api/suche", json={"start": "XXX", "ziel_art": "ueberall", "von_datum": "2027-01-01", "bis_datum": "2027-01-05"})
    assert r.status_code == 400


def test_lebenszeichen_und_startseite():
    vorher = server.LEBENSZEICHEN[0]
    assert c.post("/api/lebenszeichen").json() == {"ok": True}
    assert server.LEBENSZEICHEN[0] >= vorher
    assert "<title>Flugsuche</title>" in c.get("/").text
