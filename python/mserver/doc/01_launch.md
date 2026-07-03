# Запуск сервера — ключи и примеры

## Зависимости

Сервер использует только стандартную библиотеку Python (3.8+). Дополнительных пакетов не требуется.

---

## Команда запуска

```bash
python3 mserver.py [OPTIONS]
```

---

## Параметры командной строки

| Параметр | По умолчанию | Описание |
|---|---|---|
| `--ip IP` | автоопределение | IP-адрес, на котором слушают все сервисы |
| `--mgmt-port PORT` | `62032` | Порт management-сервера |
| `--rulesets-dir PATH` | `./rulesets` | Директория с ruleset JSON-файлами |
| `--certs-dir PATH` | `./certs` | Директория с TLS-сертификатами (для режима `https`) |
| `--startup-config PATH` | `./startup-config.json` | Путь к файлу автозагрузки конфигурации |
| `--logs-dir PATH` | `./logs` | Директория для лог-файлов tcp_logger / udp_logger |
| `--verbose` / `-v` | выключен | Дополнительная отладочная строка `IP: ...` при старте |
| `--rst-every-n N` | `0` (выкл.) | Отладочная RST-инъекция: каждая N-я https-сессия закрывается аварийно (клиент получает ответ, затем FIN→RST). `0` — выключено. Env-эквивалент `MSERVER_RST_EVERY_N`; CLI приоритетнее |

Фиксированного диапазона управляемых портов нет: управляемые порты создаются
динамически по ключам сервисов (`tcp:PORT` / `udp:PORT`) из startup-config
или запросов `POST /mgmt`.

> Замечание про `--verbose`: уровень логирования DEBUG включён всегда
> (и в файл, и в stdout), флаг лишь добавляет одну отладочную строку с IP при старте.

---

## Определение IP

Если `--ip` не указан, сервер определяет IP автоматически через UDP-сокет (connect к `3.4.5.6:80`, без реальной отправки). Это возвращает IP основного сетевого интерфейса. Если определить не удалось — используется `0.0.0.0`.

---

## Примеры запуска

### Минимальный (все умолчания)

```bash
python3 mserver.py
```

Сервер поднимается на авто-IP, management на 62032. Управляемые порты — из `./startup-config.json` (если файл есть).

### С явным IP

```bash
python3 mserver.py --ip 127.0.0.1
```

### Нестандартный management-порт

```bash
python3 mserver.py --ip 127.0.0.1 --mgmt-port 62005
```

### Нестандартные пути к файлам

```bash
python3 mserver.py \
  --ip 192.168.1.10 \
  --rulesets-dir /etc/mpsrv/rulesets \
  --certs-dir /etc/mpsrv/certs \
  --startup-config /etc/mpsrv/startup-config.json \
  --logs-dir /var/log/mpsrv
```

### Отладочная RST-инъекция

```bash
python3 mserver.py --rst-every-n 3
```

Каждая 3-я https-сессия закрывается аварийно: клиент штатно получает ответ,
после чего соединение сбрасывается (FIN→RST). Режим воспроизводит дефект из
дампа `tcp_stream7` (RST на запоздавший TLS `close_notify`) для отладки
клиентов. Инъекция действует только на `https`-сессии; счётчик глобальный на
процесс. Значение меняется только рестартом (в `POST /mgmt` и startup-config
не входит). Эквивалент — env `MSERVER_RST_EVERY_N=3`.

---

## Вывод при старте

```
2026-07-02 10:00:00,015  INFO     Log: ./runs/server/run_2026-07-02_10-00-00.012345.log
2026-07-02 10:00:00,020  INFO     MultiPortHTTPServer
2026-07-02 10:00:00,020  INFO       Management : http://192.168.1.10:62032
2026-07-02 10:00:00,020  INFO       Rulesets   : ./rulesets
2026-07-02 10:00:00,020  INFO       Config     : ./startup-config.json
2026-07-02 10:00:00,021  INFO       Logs       : ./logs
2026-07-02 10:00:00,022  INFO     Loaded ruleset 'rules_healthy' (3 rules) from ./rulesets/ruleset001.json
2026-07-02 10:00:00,130  INFO     HTTPService started: http://192.168.1.10:62224 ruleset=rules_healthy
2026-07-02 10:00:00,131  INFO     Config loaded from ./startup-config.json
2026-07-02 10:00:00,132  INFO     Management server started: http://192.168.1.10:62032
2026-07-02 10:00:00,132  INFO     Ready. Management: http://192.168.1.10:62032
```

При запуске с `--rst-every-n N` (N > 0) в блок старта после строки
`Management : ...` добавляется строка вида:

```
2026-07-02 10:00:00,020  INFO       RST-inject : every 3 https session(s)
```

Без ключа (значение по умолчанию `0`) эта строка не выводится.

---

## Остановка

`Ctrl+C` или `SIGTERM` — сервер корректно останавливает все запущенные сервисы.

```bash
kill -TERM <pid>
```

---

## Запуск в фоне (screen)

```bash
screen -dmS mpsrv python3 mserver.py --ip 127.0.0.1
screen -r mpsrv        # подключиться к сессии
```
