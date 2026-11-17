"""Einstieg der gepackten App: Server starten, Browser öffnen, bei Leerlauf beenden.

Die Oberfläche meldet sich alle 20 s (`/api/lebenszeichen`). Kommt 3 Minuten
lang keine Meldung und läuft keine Suche, beendet sich die App – ein
geschlossener Browser-Tab lässt also keinen Prozess zurück.
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
import webbrowser

PORT = 4201
LEERLAUF_S = 180


def freier_port(wunsch: int) -> int:
    for port in [wunsch, *range(wunsch + 1, wunsch + 20)]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise SystemExit("Kein freier Port zwischen 4201 und 4220 gefunden.")


def laeuft_schon(port: int) -> bool:
    """Läuft bereits eine lz-flugsuche auf dem Port? Dann nur den Browser öffnen."""
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/info", timeout=1) as r:
            return b"kontinente" in r.read()
    except Exception:
        return False


def main() -> None:
    if laeuft_schon(PORT):
        webbrowser.open(f"http://127.0.0.1:{PORT}/")
        return
    import uvicorn

    from . import server

    port = freier_port(PORT)
    url = f"http://127.0.0.1:{port}/"
    config = uvicorn.Config(server.app, host="127.0.0.1", port=port, log_level="warning", log_config=None)
    srv = uvicorn.Server(config)

    def waechter() -> None:
        while not srv.started:
            time.sleep(0.1)
        webbrowser.open(url)
        while True:
            time.sleep(5)
            ruhig = time.monotonic() - server.LEBENSZEICHEN[0] > LEERLAUF_S
            if ruhig and not server.sucht_gerade():
                srv.should_exit = True
                return

    threading.Thread(target=waechter, daemon=True).start()
    if sys.stdout:
        print(f"lz-flugsuche läuft auf {url} – Fenster schließen beendet die App nach {LEERLAUF_S // 60} Minuten.")
    srv.run()
    os._exit(0)


if __name__ == "__main__":
    main()
