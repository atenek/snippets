#!/usr/bin/env python3
"""Получение wrapped-token из Vault.

Последовательно выполняет два запроса:
  1) POST /v1/auth/approle/login  -> client_token
  2) POST /v1/sys/wrapping/wrap    -> wrap_info.token (wrapped token)
"""

import json
import logging
import os
import ssl
import sys
import urllib.request
import urllib.error
from datetime import datetime

# ---------------------------------------------------------------------------
# Конфигурация (hardcode)
# ---------------------------------------------------------------------------
url = "https://my_vault.com"
vault_namespace = "ZONE_AREA_SEGMENT"
role_id = "the_role_id"
secret_id = "the-secret_id"

wrap_ttl = "100000"  # TTL для wrapped-token (в секундах)
verbose = False # stdout подробный вывод обмена / только wrapped token

verify_tls = True # Проверять ли TLS-сертификат сервера

log_dir = "log"

os.makedirs(log_dir, exist_ok=True)
timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
log_path = os.path.join(log_dir, "run{}.log".format(timestamp))

logger = logging.getLogger("vault_get_wrap")
logger.setLevel(logging.DEBUG)

_file_handler = logging.FileHandler(log_path, encoding="utf-8")
_file_handler.setLevel(logging.DEBUG)
_file_handler.setFormatter(
    logging.Formatter("%(asctime)s %(levelname)s %(message)s")
)
logger.addHandler(_file_handler)

_stdout_handler = logging.StreamHandler(sys.stdout)
_stdout_handler.setLevel(logging.DEBUG if verbose else logging.CRITICAL)
_stdout_handler.setFormatter(logging.Formatter("%(message)s"))
logger.addHandler(_stdout_handler)

def _ssl_context():
    if verify_tls:
        return ssl.create_default_context()
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def http_post(path, headers, payload):
    full_url = url + path
    body = json.dumps(payload).encode("utf-8")

    logger.info("=== REQUEST ===")
    logger.info("POST %s", full_url)
    for key, value in headers.items():
        logger.info("Header: %s: %s", key, value)
    logger.info("Body: %s", json.dumps(payload, ensure_ascii=False))

    request = urllib.request.Request(
        full_url, data=body, headers=headers, method="POST"
    )

    try:
        with urllib.request.urlopen(request, context=_ssl_context()) as response:
            status = response.status
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        status = exc.code
        raw = exc.read().decode("utf-8")
        logger.error("=== RESPONSE (HTTPError) ===")
        logger.error("Status: %s", status)
        logger.error("Body: %s", raw)
        raise
    except urllib.error.URLError as exc:
        logger.error("=== RESPONSE (URLError) ===")
        logger.error("Reason: %s", exc.reason)
        raise

    logger.info("=== RESPONSE ===")
    logger.info("Status: %s", status)
    logger.info("Body: %s", raw)

    return json.loads(raw)


def main():
    logger.info("Запуск скрипта получения wrapped-token. Лог: %s", log_path)

    # --- Запрос 1:  client_token ---
    login_headers = {
        "Content-Type": "application/json",
        "X-Vault-Namespace": vault_namespace,
    }
    login_payload = {"role_id": role_id, "secret_id": secret_id}
    login_resp = http_post("/v1/auth/approle/login", login_headers, login_payload)

    client_token = login_resp.get("auth", {}).get("client_token")
    if not client_token:
        logger.error("Не удалось получить client_token из ответа login")
        sys.exit(1)
    logger.info("Получен client_token (длина %d)", len(client_token))

    # --- Запрос 2: wrapped-token ---
    wrap_headers = {
        "Content-Type": "application/json",
        "X-Vault-Namespace": vault_namespace,
        "X-Vault-Token": client_token,
        "X-Vault-Wrap-TTL": wrap_ttl,
    }
    wrap_payload = {"secret_id": secret_id}
    wrap_resp = http_post("/v1/sys/wrapping/wrap", wrap_headers, wrap_payload)

    wrapped_token = wrap_resp.get("wrap_info", {}).get("token") if wrap_resp.get("wrap_info") else None
    if not wrapped_token:
        logger.error("Не удалось получить wrapped token из ответа wrap")
        sys.exit(1)

    logger.info("WRAPPED_TOKEN: %s", wrapped_token)
    print(wrapped_token)


if __name__ == "__main__":
    main()
