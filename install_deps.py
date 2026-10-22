"""Installiert alle Pakete einzeln:  python install_deps.py
(Ein Paket, das nicht klappt, blockiert die anderen nicht.)"""
import subprocess
import sys


def main():
    lines = [l.strip() for l in open("requirements.txt", encoding="utf-8") if l.strip() and not l.startswith("#")]
    ok, failed = [], []
    for line in lines:
        spec, _, marker = line.partition(";")
        if marker.strip():
            try:
                from pip._vendor.packaging.markers import Marker
                if not Marker(marker.strip()).evaluate():
                    print("-- uebersprungen (nicht fuer diese Python-Version): %s" % spec.strip())
                    continue
            except Exception:
                pass
        print("== installiere %s" % spec.strip())
        r = subprocess.run([sys.executable, "-m", "pip", "install", "--prefer-binary", spec.strip()])
        (ok if r.returncode == 0 else failed).append(spec.strip())
    print("\nFertig. OK: %d   Fehlgeschlagen: %d" % (len(ok), len(failed)))
    for f in failed:
        print("  FEHLER bei: %s" % f)
    if failed:
        print("Tipp: Python 3.11 oder 3.12 verwenden - dort gibt es fuer alle Pakete fertige Installer.")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
