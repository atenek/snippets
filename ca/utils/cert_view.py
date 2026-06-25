#!/usr/bin/env python3
"""Простая обёртка над openssl для вывода содержимого сертификата в stdout.

Примеры:
    cert_view.py cert.crt                 # полный текст сертификата
    cert_view.py -s cert.crt              # кратко: subject, issuer, сроки
    cert_view.py *.crt                    # несколько файлов подряд
    cat cert.crt | cert_view.py -         # из stdin
"""

import argparse
import subprocess
import sys
from pathlib import Path


def view_cert(source: str, short: bool) -> int:
    """Вывести содержимое одного сертификата. Возвращает код возврата openssl."""
    cmd = ["openssl", "x509", "-noout"]
    if short:
        cmd += ["-subject", "-issuer", "-serial", "-dates", "-fingerprint"]
    else:
        cmd += ["-text"]

    if source == "-":
        cmd += ["-in", "/dev/stdin"]
    else:
        path = Path(source)
        if not path.exists():
            print(f"ERROR: файл не найден: {source}", file=sys.stderr)
            return 1
        cmd += ["-in", str(path)]

    return subprocess.run(cmd).returncode


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Вывести содержимое сертификата(ов) в stdout через openssl.",
    )
    parser.add_argument(
        "files", nargs="+", metavar="CERT",
        help="путь к сертификату (PEM/DER) или '-' для чтения из stdin",
    )
    parser.add_argument(
        "-s", "--short", action="store_true",
        help="краткая сводка (subject/issuer/serial/сроки/отпечаток) вместо полного текста",
    )
    args = parser.parse_args(argv)

    rc = 0
    multiple = len(args.files) > 1
    for src in args.files:
        if multiple:
            print(f"\n===== {src} =====")
        rc |= view_cert(src, args.short)
    return rc


if __name__ == "__main__":
    sys.exit(main())
