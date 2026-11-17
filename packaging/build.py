"""Baut die verteilbare App mit PyInstaller – lokal und in .github/workflows/release.yml.

Aufruf: python packaging/build.py [VERSION]
Ergebnis in release/:
  macOS   LZ-Flugsuche-<ver>-mac-<arch>.dmg  (App-Bundle, ad-hoc signiert)
  Windows LZ-Flugsuche-<ver>-win-x64.exe     (eine Datei, ohne Konsolenfenster)
  Linux   LZ-Flugsuche-<ver>-linux-<arch>.tar.gz
"""
from __future__ import annotations

import platform
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
NAME = "LZ-Flugsuche"
AUS = WURZEL / "release"


def version_setzen(v: str) -> None:
    for datei, muster, ersatz in [
        (WURZEL / "lzflug" / "__init__.py", r'__version__ = "[^"]*"', f'__version__ = "{v}"'),
        (WURZEL / "pyproject.toml", r'(?m)^version = "[^"]*"', f'version = "{v}"'),
    ]:
        datei.write_text(re.sub(muster, ersatz, datei.read_text(encoding="utf-8"), count=1), encoding="utf-8")


def lizenzen() -> Path:
    ziel = WURZEL / "build" / "THIRD-PARTY-LICENSES.txt"
    ziel.parent.mkdir(exist_ok=True)
    teile = [
        "Drittanbieter-Komponenten von LZ-Flugsuche / Third-party components\n",
        "Public Sans – SIL Open Font License 1.1 – https://github.com/uswds/public-sans\n",
        "Flughafendaten: OurAirports (gemeinfrei / public domain) – https://ourairports.com/data/\n",
        "Python – PSF License – https://docs.python.org/3/license.html\n\n",
    ]
    r = subprocess.run([sys.executable, "-m", "piplicenses", "--with-license-file", "--no-license-path",
                        "--format=plain-vertical", "--ignore-packages", "lz-flugsuche", "pyinstaller",
                        "pyinstaller-hooks-contrib", "pip-licenses", "pytest"],
                       capture_output=True, text=True, check=True)
    ziel.write_text("".join(teile) + r.stdout, encoding="utf-8")
    return ziel


def main() -> None:
    if len(sys.argv) > 1:
        version_setzen(sys.argv[1].lstrip("v"))
    v = re.search(r'__version__ = "([^"]+)"', (WURZEL / "lzflug" / "__init__.py").read_text()).group(1)

    system = platform.system()
    arch = {"x86_64": "x64", "AMD64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(platform.machine(), platform.machine())
    sep = ";" if system == "Windows" else ":"
    lic = lizenzen()
    shutil.rmtree(WURZEL / "dist", ignore_errors=True)
    AUS.mkdir(exist_ok=True)

    args = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--name", NAME,
        "--add-data", f"{WURZEL / 'lzflug' / 'static'}{sep}lzflug/static",
        "--add-data", f"{WURZEL / 'lzflug' / 'data'}{sep}lzflug/data",
        "--add-data", f"{lic}{sep}.",
        "--add-data", f"{WURZEL / 'LICENSE'}{sep}.",
        "--collect-data", "babel",
        "--collect-all", "curl_cffi",
        "--collect-submodules", "uvicorn",
        "--collect-submodules", "lzflug",
        str(WURZEL / "packaging" / "start.py"),
    ]
    if system == "Darwin":
        args[5:5] = ["--windowed", "--osx-bundle-identifier", "de.zumpelars.flugsuche"]
    elif system == "Windows":
        args[5:5] = ["--onefile", "--noconsole"]
    else:
        args[5:5] = ["--onefile"]
    subprocess.run(args, cwd=WURZEL, check=True)

    if system == "Darwin":
        app = WURZEL / "dist" / f"{NAME}.app"
        subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(app)], check=True)
        dmg = AUS / f"{NAME}-{v}-mac-{arch}.dmg"
        dmg.unlink(missing_ok=True)
        subprocess.run(["hdiutil", "create", "-volname", NAME, "-srcfolder", str(app), "-ov", "-format", "UDZO", str(dmg)], check=True)
        print(dmg)
    elif system == "Windows":
        exe = AUS / f"{NAME}-{v}-win-{arch}.exe"
        shutil.copy2(WURZEL / "dist" / f"{NAME}.exe", exe)
        print(exe)
    else:
        tgz = AUS / f"{NAME}-{v}-linux-{arch}.tar.gz"
        with tarfile.open(tgz, "w:gz") as t:
            t.add(WURZEL / "dist" / NAME, arcname=f"{NAME}/{NAME}")
            t.add(lic, arcname=f"{NAME}/THIRD-PARTY-LICENSES.txt")
            t.add(WURZEL / "LICENSE", arcname=f"{NAME}/LICENSE")
        print(tgz)


if __name__ == "__main__":
    main()
