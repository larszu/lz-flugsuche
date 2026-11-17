# lz-flugsuche

Findet den günstigsten Flug – nicht nur ab dem Heimatflughafen, sondern ab **allen Flughäfen im Umkreis**, und rechnet die **Anreise** mit ein. Ziel kann ein Flughafen, ein **Land**, ein **Kontinent** oder **überallhin** sein.

![Ergebnisliste](docs/ergebnis.png)

## Was es anders macht

| Problem bei üblichen Portalen | Lösung hier |
|---|---|
| Nahe Flughäfen nur mit starrem Radius, Anreise zählt nicht | Jeder Abflughafen im Umkreis wird durchsucht; sortiert wird nach **Flugpreis + Anreise** (km × €/km, Hin- und Rückweg) mit Fahrzeit |
| „Überallhin“ nur ab einem Flughafen | Ryanair-Ziele ab **jedem** Abflughafen, Google-Preise für den Hauptflughafen jedes Landes; die günstigsten Ziele werden ab allen Abflughäfen nachgefragt |
| Kalender- und Kartenpreise sind veraltet | Die besten Treffer werden **live** nachgeprüft; Ryanair-Preise zeigen ihren Stand |
| Billigflieger fehlen | Ryanair wird direkt abgefragt, Buchungslink geht zur Airline |
| Endpreis ohne Gepäck | Gepäckwahl fließt in Google-Preise ein; bei Ryanair-Basistarifen steht „Gepäck kommt dazu“ |
| Sponsored-Treffer | Keine Werbung, keine Provision, Sortierung nur nach Preis |
| Man weiß nicht, was durchsucht wurde | Abflughäfen und Anzahl der abgefragten Ziele stehen über der Liste |

Jeder gefundene Preis wird lokal gespeichert (`~/.lz-flugsuche/preise.sqlite`); die Karte zeigt, ob er der tiefste bisher gesehene ist.

Grundlage ist die Recherche in `~/reports/Günstigste Flüge finden.md`: Preise steigen nicht durch wiederholtes Suchen, sondern weil Buchungsklassen ausverkaufen und Portale alte Cache-Preise zeigen. VPN bringt ab der EU praktisch nichts.

## Starten

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e ".[test]"
.venv/bin/lzflug server          # http://127.0.0.1:4201
```

Kommandozeile:

```bash
.venv/bin/lzflug suche FRA --ziel PT --von 2027-01-10 --bis 2027-01-31 --naechte 4
.venv/bin/lzflug suche FRA --ziel kontinent:EU --radius 250
.venv/bin/lzflug suche FRA --ziel ueberall --personen 2 --gepaeck handgepaeck
```

## Ablauf einer Suche

1. **Abflughäfen:** Heimatflughafen plus bis zu 7 weitere im Umkreis (mittlere und große Flughäfen mit Linienverkehr). Straßenkilometer = Luftlinie × 1,3.
2. **Grobsuche:** Google-Preiskalender (günstigster Preis je Tag im Zeitraum) vom Heimatflughafen zu jedem Zielkandidaten, dazu Ryanair „überallhin“ ab jedem Abflughafen.
3. **Ausweiten:** Die 8 günstigsten Ziele werden ab allen anderen Abflughäfen im Kalender abgefragt.
4. **Live-Prüfung:** Die besten Google-Kalenderpreise werden mit einer echten Suche nachgeprüft (Uhrzeit, Airline, Umstiege, Selbst-Umstieg).
5. **Bewertung:** Gesamt = Flug + Anreise; „spart X €“ vergleicht mit dem Heimatflughafen.

Zwischenergebnisse erscheinen in der Oberfläche schon während der Suche.

## Datenquellen

| Quelle | Wie | Grenzen |
|---|---|---|
| Google Flights | Bibliothek [`fli`](https://github.com/punitarani/fli) (PyPI `flights`), inoffiziell | Google bremst bei vielen Anfragen (HTTP 429); hier höchstens 2 gleichzeitig, bei 429 20 s Pause. Kann bei Formatänderungen ausfallen |
| Ryanair | `farfnd/v4` oneWayFares / roundTripFares, inoffiziell | Basistarif ohne Gepäck, Preis pro Person × Anzahl |
| Flughäfen | [OurAirports](https://ourairports.com/data/) (gemeinfrei) → `data/airports.json` | Aktualisieren: `python scripts/airports_update.py` |

Nicht angebunden (Stand 11/2026): Amadeus Self-Service ist abgeschaltet, Kiwi Tequila und Skyscanner nur für Partner. Wizz Air und easyJet erscheinen über Google.

Die Abfragen sind für den privaten Gebrauch gedacht: wenige, gedrosselte Anfragen, keine Umgehung von Schutzmaßnahmen.

## Entwicklung

```bash
.venv/bin/pytest -q
```

| Pfad | Inhalt |
|---|---|
| `lzflug/search.py` | Suchablauf und Bewertung |
| `lzflug/sources/` | Google und Ryanair |
| `lzflug/airports.py` | Umkreis, Länder, Kontinente, Namenssuche |
| `lzflug/server.py` | FastAPI, Suche als Hintergrundauftrag mit Fortschritt |
| `lzflug/static/` | Oberfläche (LZM-Web-Stil, hell und dunkel) |

## Noch offen

- Preisalarm für ein ganzes Suchprofil (Mail/Telegram)
- Bahn als Anreise (Preis und Fahrzeit) statt nur Auto-Kilometer
- Flexible Nächte-Spanne (heute: feste Anzahl)
- Weitere Billigflieger direkt (Wizz Air, easyJet)
