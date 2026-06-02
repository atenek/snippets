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

## POST /mgmt — назначить режим сервису

Тело — JSON-массив команд. Все применяются атомарно (без частичного отката).

```bash
curl -s -X POST http://$IP:$MGMT/mgmt \
  -H "Content-Type: application/json" \
  -d '[...]'
```

### Формат одной команды

```json
{"service": "tcp:62224", "mode": "http", "ruleset": "rules_healthy"}
```

| Поле | Тип | Обязательный | Описание |
|---|---|---|---|
| `service` | string | да | `tcp:NNNNN` или `udp:NNNNN` |
| `mode` | string \| null | да | Режим работы или `null` для остановки |
| `ruleset` | string | для `mode=http` | Имя загруженного ruleset |

### Примеры команд

```bash
# HTTP-сервис с ruleset
curl -s -X POST http://$IP:$MGMT/mgmt \
  -H "Content-Type: application/json" \
  -d '[{"service": "tcp:62224", "mode": "http", "ruleset": "rules_healthy"}]'

# HTTP-сервис с файловым сервером (ruleset rules_fileserver)
curl -s -X POST http://$IP:$MGMT/mgmt \
  -H "Content-Type: application/json" \
  -d '[{"service": "tcp:62225", "mode": "http", "ruleset": "rules_fileserver"}]'

# TCP echo
curl -s -X POST http://$IP:$MGMT/mgmt \
  -H "Content-Type: application/json" \
  -d '[{"service": "tcp:62225", "mode": "tcp_echo"}]'

# TCP logger
curl -s -X POST http://$IP:$MGMT/mgmt \
  -H "Content-Type: application/json" \
  -d '[{"service": "tcp:62226", "mode": "tcp_logger"}]'

# UDP echo
curl -s -X POST http://$IP:$MGMT/mgmt \
  -H "Content-Type: application/json" \
  -d '[{"service": "udp:62224", "mode": "udp_echo"}]'

# UDP logger
curl -s -X POST http://$IP:$MGMT/mgmt \
  -H "Content-Type: application/json" \
  -d '[{"service": "udp:62226", "mode": "udp_logger"}]'

# Остановить сервис
curl -s -X POST http://$IP:$MGMT/mgmt \
  -H "Content-Type: application/json" \
  -d '[{"service": "tcp:62227", "mode": null}]'

# Несколько сервисов одним запросом
curl -s -X POST http://$IP:$MGMT/mgmt \
  -H "Content-Type: application/json" \
  -d '[
    {"service": "tcp:62224", "mode": "http",       "ruleset": "rules_healthy"},
    {"service": "tcp:62225", "mode": "tcp_echo"},
    {"service": "tcp:62226", "mode": "tcp_logger"},
    {"service": "udp:62224", "mode": "udp_echo"}
  ]'
```

### Ответ при успехе

```json
{
  "status": "success",
  "results": [
    {"service": "tcp:62224", "status": "applied", "mode": "http", "ruleset": "rules_healthy"},
    {"service": "tcp:62225", "status": "applied", "mode": "tcp_echo"},
    {"service": "tcp:62226", "status": "applied", "mode": "tcp_logger", "log_file": "./logs/tcp_62226_20260602_100000.log"},
    {"service": "tcp:62227", "status": "stopped"}
  ]
}
```

### Переключение ruleset (hot-swap)

Смена ruleset не требует остановки сервиса — старый поток завершается, новый стартует мгновенно:

```bash
curl -s -X POST http://$IP:$MGMT/mgmt \
  -H "Content-Type: application/json" \
  -d '[{"service": "tcp:62224", "mode": "http", "ruleset": "rules_degraded"}]'
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
{"status": "success", "message": "Loaded from ./startup-config.json"}
```

Читает `startup-config.json` и немедленно применяет все режимы. Эквивалентно перезапуску, но без остановки сервера.

---

## Валидация POST /mgmt

Запрос отклоняется целиком (HTTP 400) при любой ошибке валидации. Сервисы не изменяются.

| Ошибка | Условие |
|---|---|
| `Request body must be a JSON array` | Тело не массив |
| `Service must be a string` | `service` не строка |
| `Invalid service format` | Не формат `tcp:NNNNN` / `udp:NNNNN` |
| `Port not in allowed range` | Порт не в `PORT_RANGE` |
| `Cannot configure management port` | Порт совпадает с `MGMT_PORT` |
| `Duplicate service` | Один `service` встречается дважды в массиве |
| `Invalid mode for protocol` | Режим недопустим для протокола (tcp/udp) |
| `Ruleset required for http mode` | `mode=http` без `ruleset` |
| `Ruleset not found` | Ruleset не загружен при старте |
| `Invalid JSON in request body` | Тело не является валидным JSON |

Ответ при ошибке:
```json
{
  "status": "error",
  "message": "Validation failed",
  "errors": [
    {"service": "tcp:62224", "error": "Ruleset not found", "details": "Ruleset 'rules_unknown' is not loaded"}
  ]
}
```

---

## Допустимые режимы по протоколу

| Протокол | Допустимые режимы |
|---|---|
| `tcp` | `http`, `tcp_echo`, `tcp_logger` |
| `udp` | `udp_echo`, `udp_logger` |
| любой | `null` — остановить сервис |
