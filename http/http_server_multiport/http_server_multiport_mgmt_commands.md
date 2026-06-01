# HTTP Server Multiport Management — команды и примеры

## Конфигурация по умолчанию

| Параметр           | Значение               |
|--------------------|------------------------|
| `MGMT_PORT`        | `62228`                |
| `PORT_RANGE`       | `62224–62228`          |
| Управляемые порты  | `62224–62227`          |
| `--rulesets-dir`   | `./rulesets`           |
| `--startup-config` | `./startup-config.json`|
| `--logs-dir`       | `./logs`               |

```bash
IP=127.0.0.1
MGMT=62228
```

---

## Запуск сервера

### По умолчанию (автоопределение IP)

```bash
python3 http_server_multiport_mgmt.py
```

### С явным IP

```bash
python3 http_server_multiport_mgmt.py --ip 127.0.0.1
```

### Другой диапазон портов и порт управления

```bash
python3 http_server_multiport_mgmt.py \
  --ip 127.0.0.1 \
  --port-range 62001 62005 \
  --mgmt-port 62005
```

### Нестандартные пути к файлам

```bash
python3 http_server_multiport_mgmt.py \
  --ip 127.0.0.1 \
  --rulesets-dir ./my_rulesets \
  --startup-config ./configs/prod.json \
  --logs-dir /var/log/mpsrv
```

---

## Термины

| Термин       | Описание                                                  |
|--------------|-----------------------------------------------------------|
| **service**  | Конкретный порт + протокол: `tcp:62224`, `udp:62225`      |
| **mode**     | Режим работы сервиса                                      |
| **ruleset**  | Именованный набор правил HTTP-ответов (только для `http`) |

### Допустимые режимы

| Протокол | Режимы                              |
|----------|-------------------------------------|
| `tcp`    | `http`, `tcp_echo`, `tcp_logger`    |
| `udp`    | `udp_echo`, `udp_logger`            |
| любой    | `null` — остановить сервис          |

---

## Состояние и мониторинг

### GET /status — текущее состояние всех сервисов

```bash
curl -s http://$IP:$MGMT/status | python3 -m json.tool
```

Пример ответа:

```json
{
  "server": {
    "name": "hostname",
    "ip": "192.168.1.10"
  },
  "rulesets_loaded": ["rules_001", "rules_healthy", "rules_degraded"],
  "services": {
    "tcp:62224": {"listening": true,  "mode": "http",       "ruleset": "rules_healthy"},
    "tcp:62225": {"listening": true,  "mode": "tcp_echo"},
    "tcp:62226": {"listening": true,  "mode": "tcp_logger", "log_file": "./logs/tcp_62226_20260529_143022.log"},
    "tcp:62227": {"listening": false, "mode": null},
    "udp:62224": {"listening": true,  "mode": "udp_echo"},
    "udp:62226": {"listening": true,  "mode": "udp_logger", "log_file": "./logs/udp_62226_20260529_143022.log"}
  }
}
```

### GET /rulesets — загруженные наборы правил

```bash
curl -s http://$IP:$MGMT/rulesets | python3 -m json.tool
```

```json
{
  "rulesets": [
    {"name": "rules_001",      "rules_count": 4},
    {"name": "rules_healthy",  "rules_count": 3},
    {"name": "rules_degraded", "rules_count": 2}
  ]
}
```

---

## Управление режимами (POST /mgmt)

Тело запроса — JSON-массив. Все изменения применяются немедленно.

### Формат запроса

```json
[
  {"service": "tcp:62224", "mode": "http",       "ruleset": "rules_healthy"},
  {"service": "tcp:62225", "mode": "tcp_echo"},
  {"service": "tcp:62226", "mode": "tcp_logger"},
  {"service": "udp:62224", "mode": "udp_echo"},
  {"service": "udp:62226", "mode": "udp_logger"},
  {"service": "tcp:62227", "mode": null}
]
```

| Поле      | Тип    | Обязательный | Описание                                           |
|-----------|--------|--------------|---------------------------------------------------|
| `service` | string | да           | Идентификатор: `tcp:NNNNN` или `udp:NNNNN`        |
| `mode`    | string\|null | да     | Режим работы или `null` для остановки             |
| `ruleset` | string | для `http`   | Имя ruleset (должен быть загружен из `rulesets/`) |

### Запустить HTTP-сервис с ruleset

```bash
curl -s -X POST http://$IP:$MGMT/mgmt \
  -H "Content-Type: application/json" \
  -d '[{"service": "tcp:62224", "mode": "http", "ruleset": "rules_healthy"}]'
```

### Переключить ruleset (hot-swap)

```bash
curl -s -X POST http://$IP:$MGMT/mgmt \
  -H "Content-Type: application/json" \
  -d '[{"service": "tcp:62224", "mode": "http", "ruleset": "rules_degraded"}]'
```

### Запустить TCP echo

```bash
curl -s -X POST http://$IP:$MGMT/mgmt \
  -H "Content-Type: application/json" \
  -d '[{"service": "tcp:62225", "mode": "tcp_echo"}]'
```

Проверка через `nc`:

```bash
echo "hello" | nc -q1 $IP 62225
```

### Запустить TCP logger

```bash
curl -s -X POST http://$IP:$MGMT/mgmt \
  -H "Content-Type: application/json" \
  -d '[{"service": "tcp:62226", "mode": "tcp_logger"}]'
```

Имя лог-файла возвращается в ответе:

```json
{
  "service": "tcp:62226",
  "status": "applied",
  "mode": "tcp_logger",
  "log_file": "./logs/tcp_62226_20260529_143022.log"
}
```

Проверка:

```bash
echo "test data" | nc -q1 $IP 62226
cat logs/tcp_62226_*.log
```

### Запустить UDP echo

```bash
curl -s -X POST http://$IP:$MGMT/mgmt \
  -H "Content-Type: application/json" \
  -d '[{"service": "udp:62224", "mode": "udp_echo"}]'
```

Проверка:

```bash
echo "hello" | nc -u -q1 $IP 62224
```

### Запустить UDP logger

```bash
curl -s -X POST http://$IP:$MGMT/mgmt \
  -H "Content-Type: application/json" \
  -d '[{"service": "udp:62226", "mode": "udp_logger"}]'
```

Проверка:

```bash
echo "datagram" | nc -u -q1 $IP 62226
cat logs/udp_62226_*.log
```

### Остановить сервис

```bash
curl -s -X POST http://$IP:$MGMT/mgmt \
  -H "Content-Type: application/json" \
  -d '[{"service": "tcp:62227", "mode": null}]'
```

Ответ:

```json
{"service": "tcp:62227", "status": "stopped"}
```

### Настроить несколько сервисов одним запросом

```bash
curl -s -X POST http://$IP:$MGMT/mgmt \
  -H "Content-Type: application/json" \
  -d '[
    {"service": "tcp:62224", "mode": "http",       "ruleset": "rules_healthy"},
    {"service": "tcp:62225", "mode": "tcp_echo"},
    {"service": "tcp:62226", "mode": "tcp_logger"},
    {"service": "udp:62224", "mode": "udp_echo"},
    {"service": "udp:62226", "mode": "udp_logger"},
    {"service": "tcp:62227", "mode": null}
  ]'
```

---

## Конфигурация (save / load)

### Сохранить текущее состояние в startup-config.json

```bash
curl -s -X POST http://$IP:$MGMT/config/save | python3 -m json.tool
```

```json
{"status": "success", "message": "Saved to ./startup-config.json"}
```

### Загрузить и применить startup-config.json

```bash
curl -s -X POST http://$IP:$MGMT/config/load | python3 -m json.tool
```

```json
{"status": "success", "message": "Loaded from ./startup-config.json"}
```

Формат `startup-config.json`:

```json
{
  "tcp:62224": {"mode": "http",       "ruleset": "rules_healthy"},
  "tcp:62225": {"mode": "tcp_echo"},
  "tcp:62226": {"mode": "tcp_logger"},
  "udp:62224": {"mode": "udp_echo"},
  "udp:62226": {"mode": "udp_logger"},
  "tcp:62227": null
}
```

---

## Работа с rulesets

Rulesets — JSON-файлы в директории `rulesets/`. Загружаются при старте сервера.
Для добавления или изменения правил нужен перезапуск сервера.

### Формат файла ruleset

```json
{
  "name": "rules_healthy",
  "rules": [
    {
      "method": "GET",
      "path": "/health",
      "response": {"code": 200, "body": "healthy", "headers": {}}
    },
    {
      "method": "*",
      "path": "*",
      "response": {"code": 200, "body": "OK", "headers": {}}
    }
  ]
}
```

| Поле              | Описание                                       |
|-------------------|------------------------------------------------|
| `method`          | HTTP-метод (`GET`, `POST`, ...) или `*` — любой|
| `path`            | Путь запроса (`/health`) или `*` — любой       |
| `response.code`   | HTTP-код ответа (100–599)                      |
| `response.body`   | Тело ответа                                    |
| `response.headers`| Дополнительные заголовки ответа (необязательно)|

Правила проверяются **сверху вниз**, побеждает первое совпадение.
Если ничего не совпало — HTTP 404.

### Проверить HTTP-ответ управляемого порта

```bash
# Код ответа
curl -s -o /dev/null -w "%{http_code}\n" http://$IP:62224/health

# Тело ответа
curl -s http://$IP:62224/health

# Заголовки + тело
curl -si http://$IP:62224/health
```

### Проверить несколько путей

```bash
for EP in /health /ready /; do
  CODE=$(curl -s -o /dev/null -w "%{http_code}" http://$IP:62224$EP)
  BODY=$(curl -s http://$IP:62224$EP)
  echo "  $EP → $CODE  $BODY"
done
```

---

## Валидация POST /mgmt

| Ошибка                        | Условие                                    |
|-------------------------------|--------------------------------------------|
| `Service must be a string`    | `service` не строка                        |
| `Invalid service format`      | Не формат `tcp:NNNNN` / `udp:NNNNN`        |
| `Port not in allowed range`   | Порт не в PORT_RANGE                        |
| `Cannot configure management port` | Порт совпадает с MGMT_PORT           |
| `Duplicate service`           | Один service встречается дважды в запросе  |
| `Invalid mode for protocol`   | Режим недопустим для протокола              |
| `Ruleset required for http mode` | `mode=http` без поля `ruleset`          |
| `Ruleset not found`           | Ruleset не загружен                         |
| `Invalid JSON in request body`| Тело не является валидным JSON             |

### Примеры ошибочных запросов

```bash
# Неверный формат service
curl -s -X POST http://$IP:$MGMT/mgmt \
  -H "Content-Type: application/json" \
  -d '[{"service": "62224", "mode": "tcp_echo"}]'

# Порт вне диапазона
curl -s -X POST http://$IP:$MGMT/mgmt \
  -H "Content-Type: application/json" \
  -d '[{"service": "tcp:9999", "mode": "tcp_echo"}]'

# Попытка настроить MGMT_PORT
curl -s -X POST http://$IP:$MGMT/mgmt \
  -H "Content-Type: application/json" \
  -d '[{"service": "tcp:62228", "mode": "tcp_echo"}]'

# Дублирующийся service
curl -s -X POST http://$IP:$MGMT/mgmt \
  -H "Content-Type: application/json" \
  -d '[{"service": "tcp:62224", "mode": "tcp_echo"}, {"service": "tcp:62224", "mode": "tcp_logger"}]'

# Режим http без ruleset
curl -s -X POST http://$IP:$MGMT/mgmt \
  -H "Content-Type: application/json" \
  -d '[{"service": "tcp:62224", "mode": "http"}]'

# Несуществующий ruleset
curl -s -X POST http://$IP:$MGMT/mgmt \
  -H "Content-Type: application/json" \
  -d '[{"service": "tcp:62224", "mode": "http", "ruleset": "rules_unknown"}]'

# HTTP-режим на UDP-порту
curl -s -X POST http://$IP:$MGMT/mgmt \
  -H "Content-Type: application/json" \
  -d '[{"service": "udp:62224", "mode": "http", "ruleset": "rules_healthy"}]'

# Невалидный JSON
curl -s -X POST http://$IP:$MGMT/mgmt \
  -H "Content-Type: application/json" \
  -d 'not a json'
```

---

## Типичные сценарии

### Имитация healthy / degraded бэкенда

```bash
# Все порты — healthy
curl -s -X POST http://$IP:$MGMT/mgmt \
  -H "Content-Type: application/json" \
  -d '[
    {"service": "tcp:62224", "mode": "http", "ruleset": "rules_healthy"},
    {"service": "tcp:62225", "mode": "http", "ruleset": "rules_healthy"},
    {"service": "tcp:62226", "mode": "http", "ruleset": "rules_healthy"}
  ]'

# Порт 62225 — degraded
curl -s -X POST http://$IP:$MGMT/mgmt \
  -H "Content-Type: application/json" \
  -d '[{"service": "tcp:62225", "mode": "http", "ruleset": "rules_degraded"}]'

# Проверить /health на всех портах
for PORT in 62224 62225 62226; do
  CODE=$(curl -s -o /dev/null -w "%{http_code}" http://$IP:$PORT/health)
  BODY=$(curl -s http://$IP:$PORT/health)
  echo "tcp:$PORT /health → $CODE  $BODY"
done
```

### Захват трафика через tcp_logger

```bash
# Переключить порт в режим логирования
curl -s -X POST http://$IP:$MGMT/mgmt \
  -H "Content-Type: application/json" \
  -d '[{"service": "tcp:62224", "mode": "tcp_logger"}]'

# Отправить тестовые данные
echo "GET /health HTTP/1.0" | nc -q1 $IP 62224

# Посмотреть лог (имя файла видно в ответе /status или /mgmt)
tail -f logs/tcp_62224_*.log

# Вернуть порт в HTTP-режим
curl -s -X POST http://$IP:$MGMT/mgmt \
  -H "Content-Type: application/json" \
  -d '[{"service": "tcp:62224", "mode": "http", "ruleset": "rules_healthy"}]'
```

### Полный цикл: настройка → сохранение → перезапуск

```bash
# 1. Настроить сервисы
curl -s -X POST http://$IP:$MGMT/mgmt \
  -H "Content-Type: application/json" \
  -d '[
    {"service": "tcp:62224", "mode": "http",    "ruleset": "rules_healthy"},
    {"service": "tcp:62225", "mode": "tcp_echo"},
    {"service": "udp:62224", "mode": "udp_echo"}
  ]'

# 2. Сохранить в startup-config.json
curl -s -X POST http://$IP:$MGMT/config/save

# 3. После перезапуска сервера конфиг применится автоматически
#    или применить вручную:
curl -s -X POST http://$IP:$MGMT/config/load

# 4. Убедиться в состоянии
curl -s http://$IP:$MGMT/status | python3 -m json.tool
```

### Проверка всех сервисов одной командой

```bash
curl -s http://$IP:$MGMT/status \
  | python3 -c "
import json, sys
d = json.load(sys.stdin)
for svc, info in d['services'].items():
    mode = info.get('mode') or 'null'
    listen = 'UP  ' if info['listening'] else 'DOWN'
    extra = info.get('ruleset') or info.get('log_file') or ''
    print(f'  {listen}  {svc:<16}  {mode:<14}  {extra}')
"
```
