# startup-config.json — автозагрузка конфигурации

## Назначение

`startup-config.json` содержит состояние сервисов, которое применяется автоматически при старте сервера. Это позволяет сохранить рабочую конфигурацию и восстанавливать её после перезапуска без ручных вызовов `/mgmt`.

---

## Формат файла

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

| Ключ | Значение | Описание |
|---|---|---|
| `"tcp:NNNNN"` / `"udp:NNNNN"` | объект или `null` | Сервис и его конфигурация |
| `mode` | string | Режим сервиса (см. [05_service_modes.md](05_service_modes.md)) |
| `ruleset` | string | Имя ruleset — только для `mode: "http"` |
| `null` | — | Сервис остановлен |

---

## Автозагрузка при старте

Если файл `startup-config.json` существует, сервер применяет его сразу после загрузки rulesets:

```
INFO  Loaded ruleset 'rules_healthy' (3 rules) from ./rulesets/ruleset001.json
INFO  Config loaded from ./startup-config.json
INFO  HTTPService started: http://192.168.1.10:62224 ruleset=rules_healthy
INFO  TCPEchoService started on port 62225
```

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
{"status": "success", "message": "Loaded from ./startup-config.json"}
```

Применяет конфиг к живому серверу: останавливает текущие сервисы и запускает новые по файлу.

---

## Полный workflow: настройка → сохранение → восстановление

```bash
IP=127.0.0.1
MGMT=62228

# 1. Настроить сервисы
curl -s -X POST http://$IP:$MGMT/mgmt \
  -H "Content-Type: application/json" \
  -d '[
    {"service": "tcp:62224", "mode": "http",    "ruleset": "rules_healthy"},
    {"service": "tcp:62225", "mode": "tcp_echo"},
    {"service": "udp:62224", "mode": "udp_echo"}
  ]'

# 2. Проверить состояние
curl -s http://$IP:$MGMT/status | python3 -m json.tool

# 3. Сохранить
curl -s -X POST http://$IP:$MGMT/config/save

# 4. После перезапуска — конфиг применится автоматически
#    Или применить вручную без перезапуска:
curl -s -X POST http://$IP:$MGMT/config/load
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
python3 http_server_multiport_mgmt.py --startup-config /etc/mpsrv/prod.json
```
