# HTTP Client — руководство

## Общее описание

`http_client_multiport_mgmt.py` — многопоточный HTTP-клиент для тестирования
трафика, проходящего через Load Balancer.

Каждый **endpoint** (пара DST\_IP:DST\_PORT + path) работает в отдельном
потоке и отправляет запросы с заданной частотой TPS (transactions per second).
Для каждого запроса открывается **новая TCP-сессия** — соединения не
переиспользуются. Клиент биндится к указанному source IP и порту, что
позволяет управлять тем, какой интерфейс и какой src-port видит LB.

Все запросы и ответы пишутся в **CSV-файл**, который содержит одновременно
данные сессии со стороны клиента (`Cl_*`) и данные, которые RealServer
сообщил о сессии (`RS_*`). Расхождение между ними показывает, как LB
транслирует адреса (SNAT).

```
                  ┌──────────────────────────────────────────┐
                  │           client host                    │
  ┌─────────┐     │  ┌──────────┐        ┌────────────────┐  │
  │ config  │────►│  │ worker 1 │──────► │                │  │
  │ .json   │     │  │ tps=12   │        │  CSV writer    │──►│── CSV
  └─────────┘     │  └──────────┘        │  (thread-safe) │  │
                  │  ┌──────────┐        └────────────────┘  │
                  │  │ worker 2 │──────►                     │
                  │  │ tps=8    │        ┌────────────────┐  │
                  │  └──────────┘        │    log file    │  │
                  └──────────────────────┴────────────────┴──┘
                         │
          новая TCP-сессия на каждый запрос
          bind(SRC_IP, random(SRC_PORT_MIN..SRC_PORT_MAX))
                         │
                    ┌────▼────┐
                    │   LB    │  ← DST_IP = VIP
                    └────┬────┘
                ┌────────┴────────┐
           ┌────▼────┐       ┌────▼────┐
           │   RS1   │       │   RS2   │
           └─────────┘       └─────────┘
```

---

## Запуск

```bash
# Запустить бесконечно, Ctrl+C для остановки
python http_client_multiport_mgmt.py --config profiles/client-config.json

# Запустить ровно 60 секунд
python http_client_multiport_mgmt.py --config profiles/client-config.json \
    --duration 60

# Указать файл вывода явно
python http_client_multiport_mgmt.py --config profiles/client-config.json \
    --output /tmp/results/lb_test.csv

# Глобальный таймаут 3 сек + подробный лог в stdout
python http_client_multiport_mgmt.py --config profiles/client-config.json \
    --timeout 3 --verbose
```

### Аргументы CLI

| Аргумент | Сокращение | По умолчанию | Описание |
|----------|-----------|--------------|----------|
| `--config FILE` | `-c` | обязателен | Путь к JSON-конфигу с описанием эндпоинтов |
| `--output FILE` | `-o` | `./runs/client/client_run_<RUN_ID>.csv` | Файл CSV для записи |
| `--duration SEC` | `-d` | ∞ (до Ctrl+C) | Сколько секунд работать |
| `--timeout SEC` | `-t` | `10.0` | Глобальный таймаут сокета (переопределяется в конфиге) |
| `--verbose` | `-v` | выключен | DEBUG-лог в stdout (в файл пишется всегда) |

### Выходные файлы

Оба файла создаются автоматически в `./runs/client/`:

```
runs/client/
├── run_2026-05-31_14-30-22.123.log      # подробный лог процесса
└── client_run_2026-05-31_14-30-22.123.csv  # данные запросов/ответов
```

`RUN_ID` формируется как `YYYY-MM-DD_HH-MM-SS.mmm` на момент запуска.

---

## Формат конфига

Конфиг — JSON-массив объектов, по одному на endpoint.
Каждый endpoint работает независимо в своём потоке.

### Все поля

| Поле | Тип | Обязателен | Описание |
|------|-----|-----------|----------|
| `SRC_IP` | string | да | Source IP для биндинга сокета. Должен быть назначен на интерфейс хоста |
| `SRC_PORT` | string или int | да | Source port или диапазон. Форматы: `"1024..4096"` или `8080` |
| `DST_IP` | string | да | Destination IP (VIP Load Balancer-а или прямой IP сервера) |
| `DST_PORT` | int | да | Destination port |
| `path` | string | да | HTTP path (`/health`, `/data`, `/ready` и т.п.) |
| `tps` | float | да | Количество запросов в секунду для данного endpoint |
| `method` | string | нет | HTTP метод (по умолчанию `GET`) |
| `timeout` | float | нет | Таймаут сокета в секундах для данного endpoint (переопределяет `--timeout`) |

### Формат SRC\_PORT

```
"1024..4096"   — диапазон: для каждого нового соединения выбирается случайный порт
"8080"         — фиксированный порт (одинаковый для всех запросов данного endpoint)
1024           — то же что "1024"
```

При использовании **фиксированного порта** запросы идут строго последовательно —
следующее соединение открывается только после закрытия предыдущего.
При большом TPS и медленном сервере возможна ситуация TIME\_WAIT;
`SO_REUSEADDR` + `SO_REUSEPORT` установлены, чтобы минимизировать этот эффект.

---

## Примеры конфигов

### Минимальный — один endpoint

```json
[
  {
    "SRC_IP":   "192.168.2.15",
    "SRC_PORT": "1024..4096",
    "DST_IP":   "192.168.10.5",
    "DST_PORT": 62224,
    "path":     "/health",
    "tps":      1
  }
]
```

### Стандартная пара hc + data через LB

```json
[
  {
    "SRC_IP":   "192.168.2.15",
    "SRC_PORT": "1024..4096",
    "DST_IP":   "10.0.0.100",
    "DST_PORT": 62224,
    "path":     "/health",
    "tps":      5,
    "timeout":  3.0
  },
  {
    "SRC_IP":   "192.168.2.15",
    "SRC_PORT": "1024..4096",
    "DST_IP":   "10.0.0.100",
    "DST_PORT": 62225,
    "path":     "/data",
    "tps":      5,
    "timeout":  3.0
  }
]
```

### Два src-IP — имитация трафика с разных хостов

```json
[
  {
    "SRC_IP":   "192.168.2.15",
    "SRC_PORT": "1024..4096",
    "DST_IP":   "10.0.0.100",
    "DST_PORT": 62224,
    "path":     "/health",
    "tps":      10
  },
  {
    "SRC_IP":   "192.168.2.16",
    "SRC_PORT": "1024..4096",
    "DST_IP":   "10.0.0.100",
    "DST_PORT": 62224,
    "path":     "/health",
    "tps":      10
  }
]
```

> Оба IP должны быть назначены на интерфейсы хоста, с которого запускается клиент.

### Четыре порта — все пары hc+data на двух RS напрямую

```json
[
  {
    "SRC_IP": "192.168.2.15", "SRC_PORT": "2000..4000",
    "DST_IP": "192.168.10.11", "DST_PORT": 62224,
    "path": "/health", "tps": 4, "timeout": 5.0
  },
  {
    "SRC_IP": "192.168.2.15", "SRC_PORT": "2000..4000",
    "DST_IP": "192.168.10.11", "DST_PORT": 62225,
    "path": "/data", "tps": 4, "timeout": 5.0
  },
  {
    "SRC_IP": "192.168.2.15", "SRC_PORT": "2000..4000",
    "DST_IP": "192.168.10.12", "DST_PORT": 62224,
    "path": "/health", "tps": 4, "timeout": 5.0
  },
  {
    "SRC_IP": "192.168.2.15", "SRC_PORT": "2000..4000",
    "DST_IP": "192.168.10.12", "DST_PORT": 62225,
    "path": "/data", "tps": 4, "timeout": 5.0
  }
]
```

### Фиксированный src-port — тест персистентности LB-сессии

```json
[
  {
    "SRC_IP":   "192.168.2.15",
    "SRC_PORT": "50100",
    "DST_IP":   "10.0.0.100",
    "DST_PORT": 62225,
    "path":     "/data",
    "tps":      1,
    "timeout":  5.0
  }
]
```

> При `tps: 1` и `SRC_PORT` фиксированном порт освобождается до следующего запроса.
> Каждый раз клиент переподключается с тем же src-port, что позволяет проверить,
> всегда ли LB направляет сессию на тот же RS.

---

## Поля CSV

Разделитель — `;`. Кодировка UTF-8.

```
req_timestamp ; resp_timestamp ; timedelta_ms ;
path ;
Cl_SRC_IP ; Cl_SRC_PORT ; Cl_DST_IP ; Cl_DST_PORT ;
RS_SRC_IP ; RS_SRC_PORT ; RS_DST_IP ; RS_DST_PORT ;
status_code ; Content-Type ; Body ;
conn_event
```

### Тайминг

| Поле | Описание |
|------|----------|
| `req_timestamp` | Момент отправки запроса (ISO 8601, мс) |
| `resp_timestamp` | Момент получения полного ответа (или момент ошибки) |
| `timedelta_ms` | Время транзакции в миллисекундах (float) |

### Сессия на стороне клиента (Cl\_)

Данные, которые клиент задаёт сам при открытии сокета.

| Поле | Описание |
|------|----------|
| `Cl_SRC_IP` | Source IP клиента (из конфига) |
| `Cl_SRC_PORT` | Source port клиента (случайный из диапазона или фиксированный) |
| `Cl_DST_IP` | Destination IP (VIP LB или прямой IP сервера) |
| `Cl_DST_PORT` | Destination port |

### Сессия на стороне RealServer (RS\_)

Данные, которые сервер видит у себя и сообщает в теле JSON-ответа.
Заполняются только если ответ `Content-Type: application/json`.

| Поле | Описание |
|------|----------|
| `RS_SRC_IP` | IP клиента, который видит RS (может быть SNAT-IP LB) |
| `RS_SRC_PORT` | Port клиента, который видит RS (может быть SNAT-port LB) |
| `RS_DST_IP` | Собственный IP RS (реальный, не VIP) |
| `RS_DST_PORT` | Собственный port RS |

> Если `Cl_SRC_IP ≠ RS_SRC_IP` — LB делает SNAT.
> Если `Cl_DST_IP ≠ RS_DST_IP` — LB делает DNAT (что и ожидается при VIP).

### Ответ

| Поле | Описание |
|------|----------|
| `path` | HTTP path из конфига (`/health`, `/data` и т.д.) |
| `status_code` | HTTP статус-код (`200`, `500`, …) или `ERROR` при сетевой ошибке |
| `Content-Type` | Заголовок `Content-Type` из ответа |
| `Body` | Тело ответа (для JSON — как строка) |

### Событие соединения (conn\_event)

Заполняется только при ошибке; при успехе — пусто.

| Значение | Причина |
|----------|---------|
| `REFUSED` | Порт не слушает — ядро ответило RST на SYN (`ECONNREFUSED`) |
| `TIMEOUT` | Нет ответа в течение `timeout` секунд (`socket.timeout` / `ETIMEDOUT`) |
| `RST` | TCP RST получен после установки соединения (`ECONNRESET`, `EPIPE`, `BrokenPipeError`) |
| `FIN` | Сервер закрыл соединение (FIN) до завершения HTTP-ответа (`RemoteDisconnected`) |
| `ERROR` | Прочие исключения: маршрутизация, DNS и т.п. |

### Пример строк CSV

**Успешный text/plain ответ (hc-endpoint):**
```
2026-05-31T14:30:22.169;2026-05-31T14:30:22.170;0.973;/health;
192.168.2.15;3791;10.0.0.100;62224;
;;;;
200;text/plain;ok;
```
RS-поля пустые — сервер ответил text/plain, в нём нет сессионных данных.

**Успешный application/json ответ (data-endpoint) через LB с SNAT:**
```
2026-05-31T14:30:22.169;2026-05-31T14:30:22.171;1.381;/data;
192.168.2.15;2048;10.0.0.100;62225;
10.1.0.1;34567;192.168.10.11;62225;
200;application/json;{"body":{...}};
```
`Cl_SRC_IP=192.168.2.15` ≠ `RS_SRC_IP=10.1.0.1` — LB транслирует src-адрес.
`Cl_DST_IP=10.0.0.100` (VIP) ≠ `RS_DST_IP=192.168.10.11` (реальный IP RS).

**Ошибка — порт не отвечает:**
```
2026-05-31T14:30:23.500;2026-05-31T14:30:23.501;0.841;/health;
192.168.2.15;1880;10.0.0.100;62224;
;;;;
ERROR;;[Errno 111] Connection refused;
REFUSED
```

---

## Сценарии использования

### Сценарий 1 — Базовая проверка доступности

Убедиться, что LB и серверы отвечают корректно перед началом теста.

```json
[
  {
    "SRC_IP": "192.168.2.15", "SRC_PORT": "1024..4096",
    "DST_IP": "10.0.0.100",   "DST_PORT": 62224,
    "path": "/health", "tps": 1, "timeout": 3.0
  }
]
```

```bash
python http_client_multiport_mgmt.py \
    --config profiles/client-hc-check.json \
    --duration 5
```

Смотрим: все строки в CSV имеют `status_code=200`, `conn_event` — пусто,
`timedelta_ms` — в пределах ожидаемого.

---

### Сценарий 2 — Тест LB Failover (переключение ruleset)

Клиент работает непрерывно. В процессе работы на одном из RS меняется
ruleset через management API. В CSV видно, как меняется `Body` и `status_code`
в ответах — ровно в момент применения нового ruleset.

```json
[
  {
    "SRC_IP": "192.168.2.15", "SRC_PORT": "1024..4096",
    "DST_IP": "10.0.0.100",   "DST_PORT": 62224,
    "path": "/health", "tps": 5, "timeout": 3.0
  },
  {
    "SRC_IP": "192.168.2.15", "SRC_PORT": "1024..4096",
    "DST_IP": "10.0.0.100",   "DST_PORT": 62225,
    "path": "/data", "tps": 5, "timeout": 3.0
  }
]
```

```bash
# Запускаем клиент в фоне
python http_client_multiport_mgmt.py \
    --config profiles/client-lb-failover.json \
    --duration 120 \
    --output /tmp/failover_test.csv &

# Через 30 секунд переключаем RS1 в состояние "fail"
sleep 30
curl -X POST http://192.168.10.11:62228/mgmt \
  -H "Content-Type: application/json" \
  -d '[{"service":"tcp:62224","mode":"http","ruleset":"rules_hc-text_500_fail"},
       {"service":"tcp:62225","mode":"http","ruleset":"rules_data-json_500_fail"}]'
```

**Что анализировать в CSV:**
- Момент изменения `status_code` с `200` на `500` — latency реакции LB
- Наличие `RS_DST_IP` — видно, продолжает ли LB отдавать трафик на упавший RS
- `timedelta_ms` — нет ли роста задержек в момент переключения

---

### Сценарий 3 — Проверка SNAT поведения LB

Выявить, делает ли LB SNAT и какие адреса он подставляет.

```json
[
  {
    "SRC_IP": "192.168.2.15", "SRC_PORT": "5001",
    "DST_IP": "10.0.0.100",   "DST_PORT": 62225,
    "path": "/data", "tps": 1, "timeout": 5.0
  }
]
```

```bash
python http_client_multiport_mgmt.py \
    --config profiles/client-snat-check.json \
    --duration 10
```

**Что смотреть в CSV:**

| Ситуация | Cl\_SRC\_IP | RS\_SRC\_IP |
|----------|------------|------------|
| Без SNAT | 192.168.2.15 | 192.168.2.15 |
| SNAT | 192.168.2.15 | 10.1.0.1 (IP LB) |

---

### Сценарий 4 — Тест персистентности (sticky sessions)

Проверить, всегда ли LB с sticky sessions направляет конкретный src-IP
на один и тот же RS.

```json
[
  {
    "SRC_IP": "192.168.2.15", "SRC_PORT": "1024..4096",
    "DST_IP": "10.0.0.100",   "DST_PORT": 62225,
    "path": "/data", "tps": 2, "timeout": 5.0
  }
]
```

```bash
python http_client_multiport_mgmt.py \
    --config profiles/client-sticky.json \
    --duration 30
```

**Что смотреть в CSV:**
- Поле `RS_DST_IP` должно быть одинаковым для всех строк.
  Если значения разные — LB не соблюдает персистентность.

---

### Сценарий 5 — Нагрузочный тест с несколькими src-IP

Симулировать трафик от нескольких клиентов через один хост.
Все src-IP должны быть настроены на интерфейсах хоста.

```bash
# Добавить виртуальные IP на интерфейс (Linux)
ip addr add 192.168.2.16/24 dev eth0
ip addr add 192.168.2.17/24 dev eth0
```

```json
[
  {
    "SRC_IP": "192.168.2.15", "SRC_PORT": "1024..4096",
    "DST_IP": "10.0.0.100",   "DST_PORT": 62225,
    "path": "/data", "tps": 20, "timeout": 5.0
  },
  {
    "SRC_IP": "192.168.2.16", "SRC_PORT": "1024..4096",
    "DST_IP": "10.0.0.100",   "DST_PORT": 62225,
    "path": "/data", "tps": 20, "timeout": 5.0
  },
  {
    "SRC_IP": "192.168.2.17", "SRC_PORT": "1024..4096",
    "DST_IP": "10.0.0.100",   "DST_PORT": 62225,
    "path": "/data", "tps": 20, "timeout": 5.0
  }
]
```

**Что смотреть в CSV:**
- Распределение по `RS_DST_IP` — видно как LB балансирует нагрузку
- `timedelta_ms` при высоком TPS — нет ли деградации

---

### Сценарий 6 — Мониторинг реакции на maintenance

Проверить, что LB корректно выводит RS из ротации при переходе
в состояние `maint`.

```bash
# 1. Запустить клиент
python http_client_multiport_mgmt.py \
    --config profiles/client-lb-failover.json \
    --duration 90 \
    --output /tmp/maint_test.csv &

# 2. Через 30с переключить RS1 в maintenance
sleep 30
curl -X POST http://192.168.10.11:62228/mgmt \
  -H "Content-Type: application/json" \
  -d '[{"service":"tcp:62224","mode":"http","ruleset":"rules_hc-text_200_maint"},
       {"service":"tcp:62225","mode":"http","ruleset":"rules_data-json_200_maint"}]'

# 3. Через 60с вернуть RS1 в строй
sleep 30
curl -X POST http://192.168.10.11:62228/mgmt \
  -H "Content-Type: application/json" \
  -d '[{"service":"tcp:62224","mode":"http","ruleset":"rules_hc-text_200_ok"},
       {"service":"tcp:62225","mode":"http","ruleset":"rules_data-json_200_ok"}]'
```

**Что смотреть в CSV:**
- В период maintenance: `Body` содержит `maint`, трафик data должен идти
  только на RS2 (`RS_DST_IP` = IP только второго сервера)
- После возврата: `RS_DST_IP` снова разнообразны (оба RS в ротации)

---

## Ограничения и замечания

**TPS и последовательность запросов.**  
Каждый endpoint — один поток. Запросы идут последовательно: следующий
начинается только после закрытия предыдущего TCP-соединения.
При `tps > 1/(задержка сервера)` клиент пропускает тики, чтобы
не накапливать отставание, и реальный TPS будет ниже заданного.

**Фиксированный src-port и TIME\_WAIT.**  
Ядро может удерживать порт в состоянии TIME\_WAIT до ~60 секунд.
`SO_REUSEADDR` + `SO_REUSEPORT` сокращают проблему, но при высоком TPS
(>10) с фиксированным портом возможны ошибки `REFUSED` или `RST`.
Для нагрузки используйте диапазон портов.

**RS\_\* поля при text/plain ответах.**  
Серверные `/health` endpoints отвечают `text/plain` — в них нет сессионных
данных, поэтому `RS_*` поля в CSV будут пустыми. Для анализа SNAT
используйте `/data` endpoint (ruleset `rules_data-json_*`).

**Несколько экземпляров клиента.**  
Можно запускать несколько экземпляров с разными конфигами и разными
`--output` файлами одновременно — они не конфликтуют.
