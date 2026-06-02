# Static file serving с rate limit

## Назначение

Режим `static_serve` позволяет раздавать статические файлы из директории с ограничением скорости скачивания на уровне отдельного соединения. Включается как тип правила в ruleset — без изменения service mode, который остаётся `http`.

---

## Как включить

1. Создать ruleset-файл в `./rulesets/` с правилом `response.service = "static_serve"`.
2. Назначить этот ruleset на TCP-порт через `POST /mgmt` с `mode: "http"`.

### Пример ruleset (`rulesets/rules_fileserver.json`)

```json
{
  "name": "rules_fileserver",
  "rules": [
    {
      "method": "GET",
      "path": "/download/*",
      "response": {
        "service": "static_serve",
        "files_dir": "./static",
        "default_rate_kb": 100,
        "max_rate_kb": 1024
      }
    },
    {
      "method": "GET",
      "path": "/files",
      "response": {
        "service": "static_list",
        "files_dir": "./static"
      }
    },
    {
      "method": "GET",
      "path": "/health",
      "response": {"code": 200, "body": "OK", "headers": {}}
    },
    {
      "method": "*",
      "path": "*",
      "response": {"code": 404, "body": "Not Found", "headers": {}}
    }
  ]
}
```

### Назначить на порт

```bash
# Перезапустить сервер (rulesets загружаются при старте), затем:
curl -s -X POST http://127.0.0.1:62228/mgmt \
  -H "Content-Type: application/json" \
  -d '[{"service": "tcp:62224", "mode": "http", "ruleset": "rules_fileserver"}]'
```

---

## Параметры static_serve

| Поле | По умолчанию | Описание |
|---|---|---|
| `files_dir` | `"./static"` | Директория с файлами (относительно CWD сервера) |
| `default_rate_kb` | `100` | Скорость по умолчанию, KB/s |
| `max_rate_kb` | `1024` | Верхний предел скорости (клиент не может запросить выше) |

---

## Скачивание файла

```bash
# Скачать с дефолтной скоростью (default_rate_kb из ruleset)
curl -o file.bin http://$IP:62224/download/file.bin

# Скачать со скоростью 50 KB/s
curl -o file.bin "http://$IP:62224/download/file.bin?rate=50"

# Скачать со скоростью 500 KB/s (если max_rate_kb=1024 — будет 500)
curl -o file.bin "http://$IP:62224/download/file.bin?rate=500"

# Превышение max_rate_kb — скорость обрезается до max_rate_kb
curl -o file.bin "http://$IP:62224/download/file.bin?rate=9999"
```

Заголовки ответа:
```
HTTP/1.1 200 OK
Content-Type: application/octet-stream
Content-Length: 10485760
Content-Disposition: attachment; filename="file.bin"
X-Rate-Limit: 100 KB/s
```

---

## Листинг файлов (static_list)

```bash
curl -s http://$IP:62224/files | python3 -m json.tool
```

```json
{
  "files": [
    {
      "name": "archive.tar.gz",
      "size": 10485760,
      "type": "application/x-tar",
      "modified": "2026-05-30T14:22:01"
    },
    {
      "name": "report.pdf",
      "size": 524288,
      "type": "application/pdf",
      "modified": "2026-06-01T09:15:00"
    }
  ],
  "count": 2
}
```

---

## Алгоритм rate limit (BandwidthLimiter)

Реализован через **token bucket** без внешних зависимостей (чистый Python + `time.sleep`).

**Логика на одно соединение:**

1. При старте скачивания — регистрируется соединение с заданной скоростью `rate` (B/s).
2. После отправки каждого чанка (8 KB) вызывается `throttle()`:
   - Считается, сколько байт разрешено за прошедшее время: `allowed = rate × elapsed`
   - Если отправлено больше разрешённого — вычисляется задержка: `wait = excess / rate`
   - `wait` ограничивается сверху `1.0` сек (защита от накопленного долга)
   - Если `wait > 10 мс` — вызывается `time.sleep(wait)`
3. При завершении (или ошибке) — соединение снимается с учёта.

**Thread-safety:** общий `threading.Lock` на словарь соединений; `time.sleep()` вызывается вне лока, не блокируя другие соединения.

**Несколько одновременных скачиваний** работают независимо — каждое соединение throttle-ится отдельно.

---

## Безопасность

- **Path traversal защита:** имя файла из URL обрабатывается через `os.path.basename()`. Запросы вида `/download/../etc/passwd` вернут 404.
- **Файлы только из `files_dir`:** сервер не выходит за пределы указанной директории.
- **Ограничение скорости:** клиент не может запросить скорость выше `max_rate_kb`.

---

## Несколько static-эндпоинтов в одном ruleset

Можно иметь разные директории и разные скорости для разных путей:

```json
{
  "name": "rules_multi_static",
  "rules": [
    {
      "method": "GET",
      "path": "/fast/*",
      "response": {
        "service": "static_serve",
        "files_dir": "./public",
        "default_rate_kb": 1024,
        "max_rate_kb": 10240
      }
    },
    {
      "method": "GET",
      "path": "/slow/*",
      "response": {
        "service": "static_serve",
        "files_dir": "./restricted",
        "default_rate_kb": 50,
        "max_rate_kb": 100
      }
    }
  ]
}
```
