#!/usr/bin/env python3
"""Простая обёртка над openssl для вывода содержимого сертификата в stdout.

Примеры:
    cert_view.py cert.crt                 # полный текст сертификата
    cert_view.py -s cert.crt              # кратко: subject, issuer, сроки
    cert_view.py *.crt                    # несколько файлов подряд
    cat cert.crt | cert_view.py           # из stdin: тип определяется автоматически
    cert_view.py --gost gost_cert.crt     # GOST-сертификат (через gost-engine)

GOST-объекты (ГОСТ Р 34.10/34.11-2012) системный openssl не разбирает:
--gost выполняет openssl под GOST-окружением (GOST_TLS/gost/, см. ca_lib.gost_env);
без флага при ошибке разбора GOST-окружение пробуется автоматически.
"""

import argparse
import subprocess
import sys
from pathlib import Path

# gost_env() живёт в общей библиотеке проекта: utils/ -> <project>/lib
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

import ca_lib  # noqa: E402

# Сопоставление заголовка PEM с типом объекта и подкомандой openssl.
# Для каждого типа задаём:
#   openssl-команду (без -text/-noout),
#   набор опций для краткого режима (-s).
PEM_TYPES = {
    "CERTIFICATE": (
        "сертификат X.509",
        ["x509"],
        ["-subject", "-issuer", "-serial", "-dates", "-fingerprint"],
    ),
    "CERTIFICATE REQUEST": (
        "запрос на сертификат (CSR)",
        ["req"],
        ["-subject"],
    ),
    "NEW CERTIFICATE REQUEST": (
        "запрос на сертификат (CSR)",
        ["req"],
        ["-subject"],
    ),
    "X509 CRL": (
        "список отзыва (CRL)",
        ["crl"],
        ["-issuer", "-lastupdate", "-nextupdate"],
    ),
    "PRIVATE KEY": (
        "приватный ключ",
        ["pkey"],
        ["-noout"],
    ),
    "RSA PRIVATE KEY": (
        "приватный ключ RSA",
        ["rsa"],
        ["-noout"],
    ),
    "EC PRIVATE KEY": (
        "приватный ключ EC",
        ["ec"],
        ["-noout"],
    ),
    "ENCRYPTED PRIVATE KEY": (
        "зашифрованный приватный ключ",
        ["pkey"],
        ["-noout"],
    ),
    "PUBLIC KEY": (
        "публичный ключ",
        ["pkey", "-pubin"],
        ["-noout"],
    ),
}


def detect_type(data: bytes):
    """Определить тип объекта по заголовку PEM.

    Возвращает кортеж (человекочитаемое имя, openssl-команда, опции краткого
    режима) или None, если заголовок не распознан.
    """
    for line in data.splitlines():
        line = line.strip()
        if line.startswith(b"-----BEGIN ") and line.endswith(b"-----"):
            label = line[len(b"-----BEGIN "):-len(b"-----")].decode(
                "ascii", "replace"
            ).strip()
            if label in PEM_TYPES:
                return PEM_TYPES[label]
            return None
    return None


def _gost_env_or_none():
    """GOST-окружение для автоопределения; None, если gost-engine недоступен."""
    try:
        return ca_lib.gost_env()
    except SystemExit:  # die() внутри gost_env — для авто-режима не фатально
        return None


def run_openssl(cmd, short: bool, short_opts, infile, data: bytes = None,
                gost: bool = False) -> int:
    """Запустить openssl с нужными опциями отображения.

    gost=True — сразу под GOST-окружением; иначе при ошибке разбора команда
    автоматически повторяется под GOST-окружением (GOST-сертификаты системный
    openssl не разбирает).
    """
    full = ["openssl"] + cmd + ["-noout"]
    if short:
        # для ключей -noout уже задаёт стандартный краткий вывод
        full += [o for o in short_opts if o != "-noout"]
    else:
        full += ["-text"]

    if infile is not None:
        full += ["-in", str(infile)]
        data = None

    env = ca_lib.gost_env() if gost else None
    res = subprocess.run(full, input=data, capture_output=True, env=env)
    if res.returncode != 0 and not gost:
        genv = _gost_env_or_none()
        if genv is not None:
            retry = subprocess.run(full, input=data, capture_output=True, env=genv)
            if retry.returncode == 0:
                print("(автоопределение: объект разобран под GOST-окружением)")
                sys.stdout.flush()
                res = retry
    sys.stdout.buffer.write(res.stdout)
    sys.stdout.flush()
    sys.stderr.buffer.write(res.stderr)
    sys.stderr.flush()
    return res.returncode


def view_file(source: str, short: bool, gost: bool = False) -> int:
    """Вывести содержимое сертификата из файла. Возвращает код возврата openssl."""
    path = Path(source)
    if not path.exists():
        print(f"ERROR: файл не найден: {source}", file=sys.stderr)
        return 1
    # из файла, как и раньше, считаем что это сертификат X.509
    _, cmd, short_opts = PEM_TYPES["CERTIFICATE"]
    return run_openssl(cmd, short, short_opts, infile=path, gost=gost)


def view_stdin(short: bool, gost: bool = False) -> int:
    """Прочитать объект из stdin (до Ctrl+D), определить тип и вывести."""
    data = sys.stdin.buffer.read()
    if not data.strip():
        print("ERROR: пустой ввод на stdin", file=sys.stderr)
        return 1

    detected = detect_type(data)
    if detected is None:
        print(
            "ERROR: не удалось определить тип объекта на stdin "
            "(ожидается PEM с заголовком -----BEGIN ...-----)",
            file=sys.stderr,
        )
        return 1

    name, cmd, short_opts = detected
    print(f"===== тип: {name} =====")
    sys.stdout.flush()
    return run_openssl(cmd, short, short_opts, infile=None, data=data, gost=gost)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Вывести содержимое сертификата(ов) в stdout через openssl.",
    )
    parser.add_argument(
        "files", nargs="*", metavar="CERT",
        help="путь к сертификату (PEM/DER); без аргумента читается stdin",
    )
    parser.add_argument(
        "-s", "--short", action="store_true",
        help="краткая сводка вместо полного текста",
    )
    parser.add_argument(
        "--gost", action="store_true",
        help="выполнять openssl под GOST-окружением (GOST_TLS/gost); "
             "без флага GOST-режим пробуется автоматически при ошибке разбора",
    )
    args = parser.parse_args(argv)

    if not args.files:
        return view_stdin(args.short, gost=args.gost)

    rc = 0
    multiple = len(args.files) > 1
    for src in args.files:
        if multiple:
            print(f"\n===== {src} =====")
        rc |= view_file(src, args.short, gost=args.gost)
    return rc


if __name__ == "__main__":
    sys.exit(main())
