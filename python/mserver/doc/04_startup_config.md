# startup-config.json и управление сервером — конфигурация, команды, сценарии

## Назначение

`startup-config.json` содержит состояние сервисов, которое применяется автоматически при старте сервера. Это позволяет сохранить рабочую конфигурацию и восстанавливать её после перезапуска без ручных вызовов `/mgmt`.

Тот же формат словаря используется в `POST /mgmt` и в поле `services` ответа `GET /status` — единая схема для файла и API (подробный справочник API — [03_mgmt_api.md](03_mgmt_api.md)).

---

## Формат файла

```json
{
  "tcp:62224": {"mode": "http",       "ruleset": "rules_healthy"},
  "tcp:40000": {"mode": "https",      "ruleset": "rules_healthy",
                "hosts": [
                  {"sni": "app.example.com", "crt": "app.crt", "key": "app.key"},
                  {"sni": "*",               "crt": "default.crt", "key": "default.key"}
                ]},
  "tcp:62225": {"mode": "tcp_echo"},
  "tcp:62226": {"mode": "tcp_logger"},
  "udp:62224": {"mode": "udp_echo"},
  "udp:62226": {"mode": "udp_logger"},
  "tcp:62227": null
}
```

| Ключ | Значение | Описание |
|---|---|---|
| `"tcp:NNNNN"` / `"udp:NNNNN"` | объект или `null` | Сервис и его конфигурация |
| `mode` | string | Режим сервиса (см. [05_service_modes.md](05_service_modes.md)) |
| `ruleset` | string | Имя ruleset — для `mode: "http"` и `"https"` |
| `hosts` | array | Список сертификатов по SNI — только для `mode: "https"` (непустой) |
| `hosts[].sni` | string | Имя хоста (SNI) или `"*"`; последняя запись — default |
| `hosts[].crt` / `hosts[].key` | string | Пути к сертификату/ключу (от `certs/` либо абсолютные) |
| `hosts[].ruleset` | string | Опц. ruleset для этого SNI (иначе — `ruleset` порта) |
| `null` | — | Сервис остановлен |

Ключи с префиксом `_` (например `"_comment"`) игнорируются.

Директория сертификатов задаётся флагом `--certs-dir` (по умолчанию `./certs`).
Относительные пути `crt`/`key` резолвятся от неё; абсолютные используются как есть.

---

## Автозагрузка при старте

Если файл `startup-config.json` существует, сервер применяет его сразу после загрузки rulesets:

```
INFO  Loaded ruleset 'rules_healthy' (3 rules) from ./rulesets/ruleset001.json
INFO  Config loaded from ./startup-config.json
INFO  HTTPService started: http://192.168.1.10:62224 ruleset=rules_healthy
INFO  TCPEchoService started on port 62225
```

Файл валидируется целиком до применения. Если он невалиден (битый JSON,
несуществующий ruleset и т.п.) — процесс **не падает**: сервер стартует без
сервисов, ошибка видна в логе, `/status` и `POST /config/load` доступны.

Если файл отсутствует — все сервисы стартуют в состоянии `null` (не слушают).

---

## Сохранить текущее состояние

```bash
curl -s -X POST http://127.0.0.1:62228/config/save | python3 -m json.tool
```

```json
{"status": "success", "message": "Saved to ./startup-config.json"}
```

Команда записывает текущее состояние **всех** сервисов, которым когда-либо назначался режим. Сервисы с `mode=null` сохраняются как `null`.

---

## Применить конфиг без перезапуска

```bash
curl -s -X POST http://127.0.0.1:62228/config/load | python3 -m json.tool
```

```json
{"status": "success", "message": "Loaded from ./startup-config.json", "results": {"...": {}}}
```

Применяет конфиг к живому серверу. Файл сначала валидируется целиком (при любой
ошибке — HTTP 400, ни один сервис не изменяется), затем записи применяются
merge-семантикой: изменяются только сервисы, перечисленные в файле.

> **Удаление ключа из файла ≠ остановка сервиса.** Сервис, отсутствующий в файле,
> после `config/load` продолжает работать как работал. Чтобы остановить сервис
> через конфиг, нужна явная запись `"tcp:NNNNN": null`.

---

## Полный workflow: настройка → сохранение → восстановление

```bash
IP=127.0.0.1
MGMT=62228

# 1. Настроить сервисы
curl -s -X POST http://$IP:$MGMT/mgmt \
  -H "Content-Type: application/json" \
  -d '{
    "tcp:62224": {"mode": "http", "ruleset": "rules_healthy"},
    "tcp:62225": {"mode": "tcp_echo"},
    "udp:62224": {"mode": "udp_echo"}
  }'

# 2. Проверить состояние
curl -s http://$IP:$MGMT/status | python3 -m json.tool

# 3. Сохранить
curl -s -X POST http://$IP:$MGMT/config/save

# 4. После перезапуска — конфиг применится автоматически
#    Или применить вручную без перезапуска:
curl -s -X POST http://$IP:$MGMT/config/load
```

---

## Быстрые проверки управляемых портов

Удобно вынести адреса в переменные и подставлять их в команды:

```bash
IP=127.0.0.1
MGMT=62228
PORT=62224
ENDPOINT=health
```

```bash
# Код ответа
curl -s -o /dev/null -w "%{http_code}\n" http://$IP:$PORT/$ENDPOINT

# Тело ответа
curl -s http://$IP:$PORT/$ENDPOINT

# Заголовки + тело
curl -si http://$IP:$PORT/$ENDPOINT

# Наблюдать за эндпоинтом в реальном времени (например, во время смены ruleset)
watch -n 1 "curl -s -o /dev/null -w '%{http_code}' http://$IP:$PORT/$ENDPOINT"
```

Проверить несколько путей одного порта:

```bash
for EP in /health /ready /; do
  CODE=$(curl -s -o /dev/null -w "%{http_code}" http://$IP:$PORT$EP)
  BODY=$(curl -s http://$IP:$PORT$EP)
  echo "  $EP → $CODE  $BODY"
done
```

Сводка по всем сервисам одной командой:

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

---

## Типичные сценарии

### Имитация healthy / degraded бэкенда

```bash
# Все порты — healthy
curl -s -X POST http://$IP:$MGMT/mgmt \
  -H "Content-Type: application/json" \
  -d '{
    "tcp:62224": {"mode": "http", "ruleset": "rules_healthy"},
    "tcp:62225": {"mode": "http", "ruleset": "rules_healthy"},
    "tcp:62226": {"mode": "http", "ruleset": "rules_healthy"}
  }'

# Порт 62225 — degraded (hot-swap, сокет не пересоздаётся)
curl -s -X POST http://$IP:$MGMT/mgmt \
  -H "Content-Type: application/json" \
  -d '{"tcp:62225": {"mode": "http", "ruleset": "rules_degraded"}}'

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
  -d '{"tcp:62224": {"mode": "tcp_logger"}}'

# Отправить тестовые данные
echo "GET /health HTTP/1.0" | nc -q1 $IP 62224

# Посмотреть лог (имя файла видно в ответе /status или /mgmt)
tail -f logs/tcp_62224_*.log

# Вернуть порт в HTTP-режим
curl -s -X POST http://$IP:$MGMT/mgmt \
  -H "Content-Type: application/json" \
  -d '{"tcp:62224": {"mode": "http", "ruleset": "rules_healthy"}}'
```

---

## Ручное редактирование

Файл можно редактировать вручную, пока сервер не запущен. При следующем старте он применится. При работающем сервере изменения вступят в силу только после `POST /config/load`.

```bash
# Пример ручного создания startup-config.json
cat > startup-config.json << 'EOF'
{
  "tcp:62224": {"mode": "http", "ruleset": "rules_fileserver"},
  "tcp:62225": {"mode": "http", "ruleset": "rules_healthy"},
  "tcp:62226": null
}
EOF
```

---

## Расположение файла

По умолчанию: `./startup-config.json` (относительно CWD при запуске сервера).

Изменить путь:
```bash
python3 mserver.py --startup-config /etc/mserver/prod.json
```
