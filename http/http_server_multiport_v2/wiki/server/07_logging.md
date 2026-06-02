# Логирование

Сервер ведёт два типа логов: **лог запуска** (server run log) и **логи сервисов** (service logs).

---

## Лог запуска (server run log)

### Расположение

```
./runs/server/run_<YYYY-MM-DD_HH-MM-SS.mmm>.log
```

Пример: `./runs/server/run_2026-06-02_10-00-00.123.log`

Директория создаётся автоматически при старте. Каждый запуск сервера создаёт новый файл.

### Что пишется

- Все INFO/DEBUG/ERROR сообщения самого сервера и management API
- Загрузка rulesets (`Loaded ruleset 'X' (N rules)`)
- Старт/стоп каждого сервиса
- Все входящие запросы к MGMT API (уровень DEBUG)
- Все ошибки сервисов

### Формат строки

```
2026-06-02 10:00:00  INFO     Log: ./runs/server/run_2026-06-02_10-00-00.123.log
2026-06-02 10:00:01  INFO     Loaded ruleset 'rules_healthy' (3 rules) from ./rulesets/ruleset001.json
2026-06-02 10:00:01  INFO     Config loaded from ./startup-config.json
2026-06-02 10:00:01  INFO     HTTPService started: http://192.168.1.10:62224 ruleset=rules_healthy
2026-06-02 10:00:01  INFO     TCPEchoService started on port 62225
2026-06-02 10:00:01  INFO     Ready. Management: http://192.168.1.10:62228
2026-06-02 10:05:32  DEBUG    [MGMT] [127.0.0.1] "POST /mgmt HTTP/1.1" 200 -
2026-06-02 10:05:32  INFO     HTTPService started: http://192.168.1.10:62224 ruleset=rules_degraded
```

### Уровни

| Уровень | Когда |
|---|---|
| `INFO` | Старт/стоп сервисов, загрузка конфигов, критические события |
| `DEBUG` | HTTP-запросы к управляемым портам, MGMT-запросы |
| `WARNING` | Не удалось загрузить ruleset-файл |
| `ERROR` | Исключения в сервисах |

Уровень DEBUG видим при запуске с флагом `-v` / `--verbose`.

### Одновременный вывод

Лог пишется **и в файл, и в stdout** одновременно. Это позволяет мониторить сервер через `journalctl` или `screen -r` и одновременно иметь персистентный лог.

---

## Логи сервисов (tcp_logger / udp_logger)

### Расположение

```
./logs/<proto>_<port>_<YYYYMMDD_HHMMSS>.log
```

Примеры:
```
./logs/tcp_62226_20260602_100000.log
./logs/udp_62226_20260602_100500.log
```

Директория создаётся автоматически. Каждый старт сервиса в режиме `*_logger` создаёт новый файл.

Изменить директорию:
```bash
python3 http_server_multiport_mgmt.py --logs-dir /var/log/mpsrv
```

### Формат tcp_logger

```
=== CONNECT 2026-06-02T10:00:01 src=192.168.1.5:51234 ===
GET /health HTTP/1.0
Host: 192.168.1.10
Connection: close

=== DISCONNECT 2026-06-02T10:00:01 ===
=== CONNECT 2026-06-02T10:00:05 src=192.168.1.5:51235 ===
POST /api HTTP/1.1
Content-Length: 42

{"key": "value"}
=== DISCONNECT 2026-06-02T10:00:05 ===
```

Файл открывается в **бинарном режиме** (`ab`) — данные пишутся как есть, без конвертации. Несколько соединений пишут в один файл (append), разделяясь заголовками `=== CONNECT ... ===`.

### Формат udp_logger

```
2026-06-02T10:00:01 src=192.168.1.5:51234 len=5 data=68656c6c6f
2026-06-02T10:00:02 src=192.168.1.5:51235 len=9 data=64617461677261
```

Каждая датаграмма — отдельная строка. Поле `data` — hex-представление байт.

---

## Просмотр логов

```bash
# Server run log (последний запуск)
tail -f runs/server/run_*.log | tail -1 | xargs tail -f

# Все логи tcp_logger
ls -lt logs/tcp_*.log

# Следить за активным tcp-логом
tail -f logs/tcp_62226_*.log

# Hex → читаемый текст для udp_logger
python3 -c "
import re, sys
for line in sys.stdin:
    m = re.search(r'data=([0-9a-f]+)', line)
    if m:
        print(line.rstrip(), '|', bytes.fromhex(m.group(1)).decode('utf-8', errors='replace'))
    else:
        print(line.rstrip())
" < logs/udp_62226_*.log
```

---

## Имя файла и run_id

При старте сервиса `*_logger` фиксируется `run_id = YYYYMMDD_HHMMSS`. Это же значение возвращается в ответе `/mgmt` и отображается в `/status`:

```bash
curl -s http://127.0.0.1:62228/status | python3 -c "
import json, sys
d = json.load(sys.stdin)
for svc, info in d['services'].items():
    if 'log_file' in info:
        print(svc, '->', info['log_file'])
"
```

```
tcp:62226 -> ./logs/tcp_62226_20260602_100000.log
udp:62226 -> ./logs/udp_62226_20260602_100500.log
```
