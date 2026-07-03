# Режимы сервисов

Каждый управляемый порт работает в одном из режимов. Режим задаётся через `POST /mgmt` или `startup-config.json`.

---

## Обзор режимов

| Режим | Протокол | Описание |
|---|---|---|
| `http` | TCP | HTTP-сервер, отвечает по правилам ruleset |
| `https` | TCP | HTTP-сервис поверх TLS; сертификат по SNI (список `hosts`) |
| `tcp_echo` | TCP | Эхо-сервер: возвращает принятые байты обратно |
| `tcp_logger` | TCP | Логирует весь входящий трафик в файл |
| `udp_echo` | UDP | UDP эхо: возвращает датаграмму отправителю |
| `udp_logger` | UDP | Логирует входящие UDP-датаграммы в файл |
| `null` | любой | Сервис остановлен, порт не слушается |

---

## http — HTTP-сервис с ruleset

**Только TCP.** Запускает HTTP/1.1 сервер на порту. Ответы определяются ruleset.

```bash
curl -s -X POST http://$IP:$MGMT/mgmt \
  -H "Content-Type: application/json" \
  -d '{"tcp:62224": {"mode": "http", "ruleset": "rules_healthy"}}'
```

- Требует указания `ruleset` — имени загруженного ruleset-файла.
- Поддерживает все HTTP-методы: GET, POST, PUT, DELETE, PATCH, HEAD, OPTIONS.
- Ruleset может содержать правила типа `response.code` (статический ответ) и `response.service` (static_serve, static_list).
- **Hot-swap**: повторный вызов с другим ruleset переключает поведение без прерывания порта.
- Обрабатывает несколько соединений одновременно (ThreadingMixIn).

Проверка:
```bash
curl -s http://$IP:62224/health
curl -si http://$IP:62224/health     # с заголовками
```

---

## https — HTTP-сервис поверх TLS с выбором сертификата по SNI

**Только TCP.** То же, что `http`, но слушающий сокет обёрнут в TLS. Сертификат
выбирается по SNI (имени хоста из ClientHello). Несколько сертификатов на одном
порту задаются списком `hosts`.

```bash
curl -s -X POST http://$IP:$MGMT/mgmt \
  -H "Content-Type: application/json" \
  -d '{"tcp:40000": {"mode": "https", "ruleset": "rules_200_ok",
        "hosts": [
          {"sni": "app.example.com", "crt": "app.crt", "key": "app.key"},
          {"sni": "*", "crt": "default.crt", "key": "default.key"}
        ]}}'
```

- Требует `ruleset` (default-ruleset порта) и непустой `hosts`.
- Каждая запись `hosts`: `sni`, `crt`, `key` (обязательны), `ruleset` (опционально —
  переопределяет ruleset порта для этого SNI).
- **Выбор сертификата**: первая запись, где `sni` равен запрошенному имени или
  равен `"*"`; если ни одна не совпала — **последняя запись** (default). `"*"` в
  последней записи рекомендуется, но необязательно (соглашение для читаемости).
- Пути `crt`/`key` — относительно `certs/` (`--certs-dir`); абсолютные — как есть.
- В `ServiceConfig` `hosts` хранится «как написано» (round-trip `config/save`/`load`).
- Только серверный TLS (`ssl.PROTOCOL_TLS_SERVER`), без mTLS.
- **Hot-swap**: горячая подмена ruleset(-ов) **и** TLS `hosts`/сертификатов —
  без пересоздания сокета; новый сертификат действует со следующего TLS-handshake.
  Пересоздание сокета происходит только при смене `mode`.

Сгенерировать самоподписанный сертификат для теста:
```bash
openssl req -x509 -newkey rsa:2048 -nodes -days 365 \
  -keyout certs/test.key -out certs/test.crt -subj "/CN=localhost"
```

Проверка (`-k` — не проверять самоподписанный сертификат; `--resolve` задаёт SNI):
```bash
curl -sk https://app.example.com:40000/health --resolve app.example.com:40000:$IP
curl -sk https://$IP:40000/health      # SNI не совпал → сертификат последней записи
```

---

## tcp_echo — TCP echo

**Только TCP.** Принимает байты — отправляет их обратно. Без интерпретации содержимого.

```bash
curl -s -X POST http://$IP:$MGMT/mgmt \
  -H "Content-Type: application/json" \
  -d '{"tcp:62225": {"mode": "tcp_echo"}}'
```

Проверка:
```bash
echo "hello world" | nc -q1 $IP 62225
```

Применение: проверка TCP-связности, тестирование балансировщиков, измерение RTT.

---

## tcp_logger — TCP logger

**Только TCP.** Принимает соединения и записывает весь входящий трафик в лог-файл. Соединение не закрывается принудительно.

```bash
curl -s -X POST http://$IP:$MGMT/mgmt \
  -H "Content-Type: application/json" \
  -d '{"tcp:62226": {"mode": "tcp_logger"}}'
```

Имя лог-файла возвращается в ответе и отображается в `/status`:
```json
{"tcp:62226": {"status": "applied", "mode": "tcp_logger",
 "log_file": "./logs/tcp_62226_20260602_100000.log"}}
```

Формат лог-файла:
```
=== CONNECT 2026-06-02T10:00:01 src=192.168.1.5:51234 ===
GET /health HTTP/1.0
Host: 192.168.1.10

=== DISCONNECT 2026-06-02T10:00:01 ===
```

Проверка:
```bash
echo "GET /health HTTP/1.0" | nc -q1 $IP 62226
cat logs/tcp_62226_*.log
tail -f logs/tcp_62226_*.log
```

---

## udp_echo — UDP echo

**Только UDP.** Принимает датаграммы и отправляет их обратно отправителю.

```bash
curl -s -X POST http://$IP:$MGMT/mgmt \
  -H "Content-Type: application/json" \
  -d '{"udp:62224": {"mode": "udp_echo"}}'
```

Проверка:
```bash
echo "hello" | nc -u -q1 $IP 62224
```

---

## udp_logger — UDP logger

**Только UDP.** Записывает каждую входящую датаграмму в лог-файл в текстовом виде (hex + метаданные).

```bash
curl -s -X POST http://$IP:$MGMT/mgmt \
  -H "Content-Type: application/json" \
  -d '{"udp:62226": {"mode": "udp_logger"}}'
```

Формат записи в лог:
```
2026-06-02T10:00:01 src=192.168.1.5:51234 len=5 data=68656c6c6f
```

Проверка:
```bash
echo "datagram" | nc -u -q1 $IP 62226
cat logs/udp_62226_*.log
```

---

## null — остановить сервис

Останавливает запущенный сервис. Порт освобождается немедленно.

```bash
curl -s -X POST http://$IP:$MGMT/mgmt \
  -H "Content-Type: application/json" \
  -d '{"tcp:62227": null}'
```

Ответ:
```json
{"tcp:62227": {"status": "stopped"}}
```

---

## Ограничения и правила назначения

- **Один порт — один режим**: нельзя одновременно запустить `tcp_echo` и `udp_echo` на одном и том же номере порта через разные протоколы из одного запроса (но можно в двух отдельных командах: `tcp:62224` и `udp:62224` — разные сервисы).
- **UDP-режимы только на UDP**: `udp_echo`, `udp_logger` нельзя назначить на `tcp:NNNNN`.
- **TCP-режимы только на TCP**: `http`, `https`, `tcp_echo`, `tcp_logger` нельзя назначить на `udp:NNNNN`.
- **MGMT_PORT недоступен**: нельзя переназначить порт management-сервера.
