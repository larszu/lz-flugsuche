"""Preisverlauf in SQLite (~/.lz-flugsuche/preise.sqlite oder LZFLUG_DB)."""
from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path

_lock = threading.Lock()


def pfad() -> Path:
    p = Path(os.environ.get("LZFLUG_DB", Path.home() / ".lz-flugsuche" / "preise.sqlite"))
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _verbinden() -> sqlite3.Connection:
    con = sqlite3.connect(pfad())
    con.execute("""CREATE TABLE IF NOT EXISTS preise (
        zeit TEXT NOT NULL, von TEXT NOT NULL, nach TEXT NOT NULL, hin TEXT NOT NULL,
        rueck TEXT, preis REAL NOT NULL, quelle TEXT NOT NULL)""")
    con.execute("CREATE INDEX IF NOT EXISTS strecke ON preise (von, nach)")
    return con


def speichern(ergebnis: dict) -> None:
    zeilen = []
    for z in ergebnis.get("ziele", []):
        for o in z["optionen"]:
            a = o["angebot"]
            zeilen.append((a["abgerufen"], a["von"], a["nach"], a["hin"], a["rueck"], a["preis"], a["quelle"]))
    if not zeilen:
        return
    with _lock, _verbinden() as con:
        con.executemany("INSERT INTO preise VALUES (?,?,?,?,?,?,?)", zeilen)


def verlauf_ergaenzen(ergebnis: dict) -> None:
    """Ergänzt je Ziel den bisher tiefsten gesehenen Preis derselben Strecke (vor dieser Suche)."""
    with _lock, _verbinden() as con:
        for z in ergebnis.get("ziele", []):
            a = z["bestes"]
            row = con.execute(
                "SELECT MIN(preis), COUNT(*), MIN(zeit) FROM preise WHERE von=? AND nach=? AND zeit<?",
                (a["von"], a["nach"], a["abgerufen"]),
            ).fetchone()
            z["verlauf"] = {"tiefst": row[0], "anzahl": row[1], "seit": row[2]} if row and row[1] else None
