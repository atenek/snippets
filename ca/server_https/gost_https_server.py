#!/usr/bin/env python3
# --------------------------------------------------------------------------- #
#  gost_https_server.py — тестовый HTTPS-сервер с GOST-TLS (user_story_003).
#
#  Поднимает HTTPS на сертификате, выпущенном этим CA (криптопрофили
#  gost-256 / gost-512 — сервер их не различает, алгоритм задан самим
#  сертификатом), и отвечает 200 OK на GET /health.
#
#  Запуск (сертификат по умолчанию — свежайший ee из gost-хранилища):
#      python3 server_https/gost_https_server.py
#      python3 server_https/gost_https_server.py --cert <ee.crt> --key <ee.key>
#      python3 server_https/gost_https_server.py --host 0.0.0.0 --port 8443
#
#  Проверка и curl-команды — см. server_https/README.md.
# --------------------------------------------------------------------------- #
import argparse
import os
import sys
from getpass import getpass
from http import HTTPStatus
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "lib"))
import ca_lib

# GOST-окружение обязано попасть в os.environ ДО import ssl: python
# инициализирует libcrypto (и читает OPENSSL_CONF с регистрацией engine)
# при импорте модуля ssl, позже поменять его уже нельзя.
os.environ.update(
    (k, v) for k, v in ca_lib.gost_env().items()
    if k in ("OPENSSL_CONF", "OPENSSL_ENGINES", "OPENSSL_MODULES")
)
ca_lib.check_gost_engine(dict(os.environ))
# Питон со статическим OpenSSL (uv-сборка) на этом import ssl падает
# с segfault — проба в дочернем процессе даёт вместо краха внятный die().
ca_lib.check_gost_inprocess(dict(os.environ))

import ssl  # noqa: E402
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer  # noqa: E402

# gost-дерево ee-хранилища; общее для gost-256 и gost-512.
EE_CERTS = ca_lib.CERT_BASE / "gost" / "ee" / "endentity_cert" / "certs"


def find_default_cert() -> Path:
    """Свежайший (по номеру NN в имени) ee-сертификат gost-хранилища."""
    if not EE_CERTS.is_dir():
        ca_lib.die(f"Нет gost-хранилища конечных сертификатов: {EE_CERTS}\n"
                   f"Сначала выпустите цепочку: rootCA_init.py / imCA_init.py / "
                   f"endentity_init.py с --profile gost-256|gost-512.")
    certs = sorted(p for p in EE_CERTS.glob("*.crt")
                   if not p.stem.endswith("-chain"))
    if not certs:
        ca_lib.die(f"В {EE_CERTS} нет ни одного сертификата.")
    return certs[-1]


def resolve_cert_key(cert_arg: str | None,
                     key_arg: str | None) -> tuple[Path, Path, Path]:
    """(файл для предъявления, ee-сертификат, ключ).

    Предъявляется цепочка <stem>-chain.crt (ee+im+root), если она лежит рядом:
    тогда клиенту для проверки достаточно одного корневого сертификата.
    Ключ — по конвенции хранилища: private/<stem>.key от имени ee-сертификата.
    """
    cert = Path(cert_arg).resolve() if cert_arg else find_default_cert()
    if not cert.is_file():
        ca_lib.die(f"Сертификат не найден: {cert}")
    stem = cert.stem.removesuffix("-chain")
    ee_cert = cert.with_name(f"{stem}.crt")
    chain = cert.with_name(f"{stem}-chain.crt")
    present = chain if chain.is_file() else cert
    if key_arg:
        key = Path(key_arg).resolve()
    else:
        key = cert.parent.parent / "private" / f"{stem}.key"
    if not key.is_file():
        ca_lib.die(f"Приватный ключ не найден: {key}\n"
                   f"Укажите его явно: --key <файл>.")
    return present, ee_cert, key


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            body = b"200 ok\n"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            # message идёт в статусную строку HTTP (latin-1) — только ASCII;
            # русский текст допустим лишь в explain (тело ответа, UTF-8).
            self.send_error(HTTPStatus.NOT_FOUND,
                            explain="Единственный endpoint — /health")

    def log_message(self, fmt, *args):
        cipher = self.connection.cipher()
        suite = cipher[0] if cipher else "?"
        print(f"[{self.address_string()}] {fmt % args}  (cipher: {suite})")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Тестовый HTTPS-сервер с GOST-TLS: 200 OK на GET /health.")
    parser.add_argument("--cert", help="серверный сертификат (по умолчанию — "
                        f"свежайший ee из {EE_CERTS})")
    parser.add_argument("--key", help="приватный ключ (по умолчанию — "
                        "private/<имя сертификата>.key рядом с хранилищем)")
    parser.add_argument("--host", default="127.0.0.1",
                        help="адрес прослушивания (по умолчанию 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8443,
                        help="порт (по умолчанию 8443)")
    args = parser.parse_args()

    # Построчная буферизация: лог виден сразу и при выводе в файл/pipe.
    sys.stdout.reconfigure(line_buffering=True)

    present, ee_cert, key = resolve_cert_key(args.cert, args.key)

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    # GOST-ciphersuites у engine есть только для TLS 1.2 (см. GOST_TLS/).
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.maximum_version = ssl.TLSVersion.TLSv1_2
    # GOST-шифры перечислены явно: в дефолт python (сборки CPython с
    # --with-ssl-default-suites=python) и в DEFAULT новых OpenSSL (3.2+)
    # они не входят; @SECLEVEL=0 — у GOST-suites Au=unknown, и security
    # level иначе отсекает их на новых OpenSSL.
    ctx.set_ciphers(
        "GOST2012-KUZNYECHIK-KUZNYECHIKOMAC:GOST2012-MAGMA-MAGMAOMAC:"
        "LEGACY-GOST2012-GOST8912-GOST8912:IANA-GOST2012-GOST8912-GOST8912:"
        "DEFAULT:@SECLEVEL=0")
    ctx.load_cert_chain(
        present, key,
        password=lambda: getpass(f"Passphrase ключа {key.name}: "))

    subject = ca_lib._subject(ee_cert, dict(os.environ))
    server = ThreadingHTTPServer((args.host, args.port), HealthHandler)
    server.socket = ctx.wrap_socket(server.socket, server_side=True)

    ca_lib.banner("GOST-TLS HTTPS сервер")
    print(f"Сертификат : {present}")
    print(f"Subject    : {subject}")
    print(f"Ключ       : {key}")
    print(f"Endpoint   : https://{args.host}:{args.port}/health")
    print("Остановка  : Ctrl+C")
    server.serve_forever()


if __name__ == "__main__":
    ca_lib.guard(main)
