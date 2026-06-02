# Запуск сервера — ключи и примеры

## Зависимости

Сервер использует только стандартную библиотеку Python (3.8+). Дополнительных пакетов не требуется.

---

## Команда запуска

```bash
python3 http_server_multiport_mgmt.py [OPTIONS]
```

---

## Параметры командной строки

| Параметр | По умолчанию | Описание |
|---|---|---|
| `--ip IP` | автоопределение | IP-адрес, на котором слушают все сервисы |
| `--port-range START END` | `62224 62228` | Диапазон управляемых портов (включительно) |
| `--mgmt-port PORT` | `62228` | Порт management-сервера (должен входить в `--port-range`) |
| `--rulesets-dir PATH` | `./rulesets` | Директория с ruleset JSON-файлами |
| `--startup-config PATH` | `./startup-config.json` | Путь к файлу автозагрузки конфигурации |
| `--logs-dir PATH` | `./logs` | Директория для лог-файлов tcp_logger / udp_logger |
| `--verbose` / `-v` | выключен | Подробный вывод (DEBUG-уровень) |

---

## Определение IP

Если `--ip` не указан, сервер определяет IP автоматически через UDP-сокет (connect к `3.4.5.6:80`, без реальной отправки). Это возвращает IP основного сетевого интерфейса.

Исключение: на хосте `CAB-WSN-0054280` жёстко прописан `127.0.0.1` (dev-машина).

---

## Примеры запуска

### Минимальный (все умолчания)

```bash
python3 http_server_multiport_mgmt.py
```

Сервер поднимается на авто-IP, порты 62224–62228, management на 62228.

### С явным IP

```bash
python3 http_server_multiport_mgmt.py --ip 127.0.0.1
```

### Нестандартный диапазон портов

```bash
python3 http_server_multiport_mgmt.py \
  --ip 127.0.0.1 \
  --port-range 62001 62005 \
  --mgmt-port 62005
```

Управляемые порты: 62001–62004. Management: 62005.

### Нестандартные пути к файлам

```bash
python3 http_server_multiport_mgmt.py \
  --ip 192.168.1.10 \
  --rulesets-dir /etc/mpsrv/rulesets \
  --startup-config /etc/mpsrv/startup-config.json \
  --logs-dir /var/log/mpsrv
```

### С подробным выводом

```bash
python3 http_server_multiport_mgmt.py -v
```

---

## Вывод при старте

```
2026-06-02 10:00:00  INFO     Log: ./runs/server/run_2026-06-02_10-00-00.000.log
2026-06-02 10:00:00  INFO     MultiPortHTTPServer
2026-06-02 10:00:00  INFO       Management : http://192.168.1.10:62228
2026-06-02 10:00:00  INFO       Port range : 62224-62228
2026-06-02 10:00:00  INFO       Rulesets   : ./rulesets
2026-06-02 10:00:00  INFO       Config     : ./startup-config.json
2026-06-02 10:00:00  INFO       Logs       : ./logs
2026-06-02 10:00:00  INFO     Loaded ruleset 'rules_healthy' (3 rules) from ./rulesets/ruleset001.json
2026-06-02 10:00:00  INFO     Ready. Management: http://192.168.1.10:62228
```

---

## Остановка

`Ctrl+C` или `SIGTERM` — сервер корректно останавливает все запущенные сервисы.

```bash
kill -TERM <pid>
```

---

## Запуск в фоне (screen)

```bash
screen -dmS mpsrv python3 http_server_multiport_mgmt.py --ip 127.0.0.1
screen -r mpsrv        # подключиться к сессии
```

> **Важно:** не использовать `nohup &` — asyncssh и некоторые socket-операции зависают при старте через systemd-scope без терминала. `screen` решает проблему.
