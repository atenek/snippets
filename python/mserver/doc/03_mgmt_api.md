# Management API — интерфейс управления сервером

Management-сервер всегда запущен на `MGMT_PORT` (по умолчанию `62228`).  
Принимает HTTP/1.1, отвечает JSON.

```bash
IP=127.0.0.1
MGMT=62228
```

---

## GET /status — состояние всех сервисов

```bash
curl -s http://$IP:$MGMT/status | python3 -m json.tool
```

Ответ:
```json
{
  "server": {
    "name": "hostname",
    "ip": "192.168.1.10"
  },
  "rulesets_loaded": ["rules_healthy", "rules_degraded", "rules_fileserver"],
  "services": {
    "tcp:62224": {"listening": true,  "mode": "http",       "ruleset": "rules_healthy"},
    "tcp:62225": {"listening": true,  "mode": "tcp_echo"},
    "tcp:62226": {"listening": true,  "mode": "tcp_logger", "log_file": "./logs/tcp_62226_20260602_100000.log"},
    "tcp:62227": {"listening": false, "mode": null},
    "udp:62224": {"listening": true,  "mode": "udp_echo"},
    "udp:62226": {"listening": true,  "mode": "udp_logger", "log_file": "./logs/udp_62226_20260602_100000.log"}
  }
}
```

Поле `services` содержит только порты, которым когда-либо назначался режим. Неиспользованные порты диапазона не отображаются.

---

## GET /rulesets — загруженные ruleset

```bash
curl -s http://$IP:$MGMT/rulesets | python3 -m json.tool
```

```json
{
  "rulesets": [
    {"name": "rules_healthy",    "rules_count": 3},
    {"name": "rules_degraded",   "rules_count": 2},
    {"name": "rules_fileserver", "rules_count": 4}
  ]
}
```

---

## POST /mgmt — назначить режимы сервисам

Тело — JSON-словарь: ключ — сервис (`tcp:NNNNN` / `udp:NNNNN`), значение —
конфигурация или `null` для остановки. Тот же формат, что `startup-config.json`
и поле `services` в `GET /status`. Валидация атомарна: при любой ошибке весь
запрос отклоняется (HTTP 400), сервисы не изменяются.

```bash
curl -s -X POST http://$IP:$MGMT/mgmt \
  -H "Content-Type: application/json" \
  -d '{
    "tcp:62224": {"mode": "http",  "ruleset": "rules_healthy"},
    "tcp:62225": {"mode": "tcp_echo"},
    "tcp:62226": {"mode": "tcp_logger"},
    "udp:62224": {"mode": "udp_echo"},
    "tcp:62227": null
  }'
```

### Формат одной записи

```json
"tcp:62224": {"mode": "http", "ruleset": "rules_healthy"}
```

| Поле | Тип | Обязательный | Описание |
|---|---|---|---|
| `mode` | string \| null | да | Режим работы или `null` для остановки |
| `ruleset` | string | для `mode=http`/`https` | Имя загруженного ruleset |
| `hosts` | array | для `mode=https` | TLS-сертификаты по SNI (см. `doc/05_service_modes.md`) |

Значение записи `null` — краткая форма остановки, эквивалент `{"mode": null}`.
Ключи с префиксом `_` (например `"_comment"`) игнорируются.

### Merge-семантика

Запрос **дополняет и/или изменяет** текущее состояние: затрагиваются только
сервисы, перечисленные в теле. Отсутствие сервиса в запросе означает
«не менять» — работающие сервисы, не упомянутые в запросе, продолжают
работать. Для остановки нужен явный `null`.

### Примеры команд

```bash
# HTTP-сервис с ruleset
curl -s -X POST http://$IP:$MGMT/mgmt \
  -H "Content-Type: application/json" \
  -d '{"tcp:62224": {"mode": "http", "ruleset": "rules_healthy"}}'

# HTTP-сервис с файловым сервером (ruleset rules_fileserver)
curl -s -X POST http://$IP:$MGMT/mgmt \
  -H "Content-Type: application/json" \
  -d '{"tcp:62225": {"mode": "http", "ruleset": "rules_fileserver"}}'

# TCP echo
curl -s -X POST http://$IP:$MGMT/mgmt \
  -H "Content-Type: application/json" \
  -d '{"tcp:62225": {"mode": "tcp_echo"}}'

# TCP logger
curl -s -X POST http://$IP:$MGMT/mgmt \
  -H "Content-Type: application/json" \
  -d '{"tcp:62226": {"mode": "tcp_logger"}}'

# UDP echo
curl -s -X POST http://$IP:$MGMT/mgmt \
  -H "Content-Type: application/json" \
  -d '{"udp:62224": {"mode": "udp_echo"}}'

# UDP logger
curl -s -X POST http://$IP:$MGMT/mgmt \
  -H "Content-Type: application/json" \
  -d '{"udp:62226": {"mode": "udp_logger"}}'

# Остановить сервис
curl -s -X POST http://$IP:$MGMT/mgmt \
  -H "Content-Type: application/json" \
  -d '{"tcp:62227": null}'
```

### Ответ при успехе

`results` — словарь по тем же ключам-сервисам:

```json
{
  "status": "success",
  "results": {
    "tcp:62224": {"status": "applied", "mode": "http", "ruleset": "rules_healthy"},
    "tcp:62225": {"status": "applied", "mode": "tcp_echo"},
    "tcp:62226": {"status": "applied", "mode": "tcp_logger", "log_file": "./logs/tcp_62226_20260602_100000.log"},
    "tcp:62227": {"status": "stopped"}
  }
}
```

### Переключение ruleset и сертификатов (hot-swap)

Пока `mode` не меняется, применение конфига не пересоздаёт слушающий сокет:
для `http`/`https` горячо подменяется ruleset (порта и per-host), для `https` —
также TLS `hosts`/сертификаты. Новые значения действуют со следующего
запроса/TLS-handshake; открытые соединения не прерываются. Пересоздание сокета
происходит только при смене `mode`.

```bash
curl -s -X POST http://$IP:$MGMT/mgmt \
  -H "Content-Type: application/json" \
  -d '{"tcp:62224": {"mode": "http", "ruleset": "rules_degraded"}}'
```

---

## POST /config/save — сохранить текущее состояние

```bash
curl -s -X POST http://$IP:$MGMT/config/save | python3 -m json.tool
```

```json
{"status": "success", "message": "Saved to ./startup-config.json"}
```

Записывает текущее состояние всех сервисов в `startup-config.json`.

---

## POST /config/load — загрузить и применить конфиг

```bash
curl -s -X POST http://$IP:$MGMT/config/load | python3 -m json.tool
```

```json
{
  "status": "success",
  "message": "Loaded from ./startup-config.json",
  "results": {
    "tcp:62224": {"status": "applied", "mode": "http", "ruleset": "rules_healthy"},
    "tcp:62227": {"status": "stopped"}
  }
}
```

Читает `startup-config.json`, валидирует его целиком (та же схема, что `POST /mgmt` —
см. «Валидация» ниже; при ошибке — HTTP 400, ни один сервис не изменяется) и применяет
все записи. Применение merge-семантикой: сервисы, отсутствующие в файле, не затрагиваются.

---

## Валидация POST /mgmt

Запрос отклоняется целиком (HTTP 400) при любой ошибке валидации. Сервисы не изменяются.
Та же валидация выполняется для `POST /config/load` и startup-config при старте сервера.

| Ошибка | Условие |
|---|---|
| `Request body must be a JSON object` | Тело не JSON-объект |
| `Invalid service format` | Ключ не формата `tcp:NNNNN` / `udp:NNNNN` |
| `Cannot configure management port` | Порт совпадает с `MGMT_PORT` |
| `Service config must be an object or null` | Значение записи не объект и не `null` |
| `Invalid mode for protocol` | Режим недопустим для протокола (tcp/udp) |
| `Ruleset required for http mode` | `mode=http`/`https` без `ruleset` |
| `Ruleset not found` | Ruleset (порта или per-host) не загружен |
| `hosts (non-empty list) required for https mode` | `mode=https` без `hosts` |
| `sni required in hosts entry` | Запись `hosts` без `sni` |
| `crt and key required in hosts entry` | Запись `hosts` без `crt`/`key` |
| `Certificate file not found` / `Key file not found` | Файл crt/key не существует |
| `Invalid certificate/key pair` | Пара crt/key не загружается (битый/несовместимый материал) |
| `Invalid JSON in request body` | Тело не является валидным JSON |

Ответ при ошибке — `errors` словарём по сервису:
```json
{
  "status": "error",
  "message": "Validation failed",
  "errors": {
    "tcp:62224": {"error": "Ruleset not found", "details": "Ruleset 'rules_unknown' is not loaded"}
  }
}
```

---

## Допустимые режимы по протоколу

| Протокол | Допустимые режимы |
|---|---|
| `tcp` | `http`, `tcp_echo`, `tcp_logger` |
| `udp` | `udp_echo`, `udp_logger` |
| любой | `null` — остановить сервис |
