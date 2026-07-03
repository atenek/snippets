# Static file serving с rate limit

## Назначение

Режим `static_serve` позволяет раздавать статические файлы из директории. Включается как тип правила в ruleset — без изменения service mode, который остаётся `http`.

Возможности:
- **Скачивание файлов** — `GET /download/<file>`. По умолчанию **без ограничения скорости**.
- **Опциональное ограничение скорости** — только по явному запросу `?rate=<KB/s>` (см. ниже).
- **Просмотр содержимого папки** — `GET /download/` (корень префикса) отдаёт стандартный HTML-листинг (autoindex) с кликабельными ссылками на файлы.
- **Задержка ответа** — параметр `?delay=<ms>` работает на любом запросе к серверу (см. раздел «Задержка ответа»).

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
        "files_dir": "./static"
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
| `default_rate_kb` | — (нет) | *Опционально.* Скорость по умолчанию, KB/s. Если не задано — скачивание **без лимита** |
| `max_rate_kb` | — (нет) | *Опционально.* Верхний предел скорости. Если не задано — `?rate=` не обрезается |

> **Важно:** по умолчанию ограничения скорости **не устанавливаются**. Лимит включается только при явном `?rate=<KB/s>` в запросе. Поля `default_rate_kb` / `max_rate_kb` оставлены как опциональные — указывать их в ruleset не требуется и по умолчанию не нужно.

---

## Скачивание файла

```bash
# Скачать без ограничения скорости (поведение по умолчанию)
curl -o file.bin http://$IP:62224/download/file.bin

# Скачать со скоростью 50 KB/s (лимит включается только этим параметром)
curl -o file.bin "http://$IP:62224/download/file.bin?rate=50"

# Скачать со скоростью 500 KB/s
curl -o file.bin "http://$IP:62224/download/file.bin?rate=500"

# Если в ruleset задан max_rate_kb — ?rate обрезается до него; иначе применяется как есть
curl -o file.bin "http://$IP:62224/download/file.bin?rate=9999"

# rate=0 (или отрицательное) трактуется как «без лимита»
curl -o file.bin "http://$IP:62224/download/file.bin?rate=0"
```

Заголовки ответа без `?rate` (без лимита):
```
HTTP/1.1 200 OK
Content-Type: application/octet-stream
Content-Length: 10485760
Content-Disposition: attachment; filename="file.bin"
X-Rate-Limit: unlimited
```

Заголовки ответа с `?rate=50`:
```
HTTP/1.1 200 OK
Content-Type: application/octet-stream
Content-Length: 10485760
Content-Disposition: attachment; filename="file.bin"
X-Rate-Limit: 50 KB/s
```

---

## Просмотр содержимого папки (HTML-индекс)

Запрос корня префикса `static_serve` (`/download/` или `/download`) возвращает стандартный HTML-листинг директории `files_dir` с кликабельными ссылками на файлы — как autoindex у `python -m http.server` или nginx.

```bash
curl http://$IP:62224/download/
```

```html
<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>Index of /download/</title></head>
<body>
<h1>Index of /download/</h1>
<ul>
    <li><a href="/download/archive.tar.gz">archive.tar.gz</a> <span class="size">(10485760 bytes)</span></li>
    <li><a href="/download/report.pdf">report.pdf</a> <span class="size">(524288 bytes)</span></li>
</ul>
</body></html>
```

- Ссылки ведут на скачивание соответствующего файла через тот же префикс.
- Показываются только обычные файлы (без подкаталогов).
- Если `files_dir` не существует — HTTP 404.

Для машинно-читаемого списка используйте `static_list` (JSON, см. ниже).

---

## Задержка ответа (`?delay`)

Параметр `?delay=<ms>` добавляет искусственную задержку перед отправкой ответа. Работает на **любом** HTTP-запросе к серверу (не только `static_serve`): обычные правила, `static_serve`, `static_list`, HTML-индекс.

| Параметр | Единицы | Диапазон | Описание |
|---|---|---|---|
| `delay` | миллисекунды | `0`…`60000` | Задержка перед ответом. Значения выше потолка обрезаются до `60000` мс; некорректные/отрицательные игнорируются (0) |

```bash
# Ответ с задержкой 2 секунды
curl "http://$IP:62224/download/file.bin?delay=2000"

# delay сочетается с другими параметрами
curl "http://$IP:62224/download/file.bin?rate=100&delay=500"

# delay работает и на обычных правилах
curl "http://$IP:62224/health?delay=1500"
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

> Throttling включается, **только** когда скорость задана (`?rate=` или `default_rate_kb` в ruleset). Без лимита файл отдаётся на полной скорости, соединение в `BandwidthLimiter` не регистрируется, заголовок `X-Rate-Limit: unlimited`.

**Логика на одно соединение (когда лимит задан):**

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
- **Ограничение скорости:** если в ruleset задан `max_rate_kb`, клиент не может запросить скорость выше него; если не задан — `?rate=` применяется без верхнего предела.

---

## Несколько static-эндпоинтов в одном ruleset

Можно иметь разные директории для разных путей. При необходимости (опционально) для конкретного пути можно задать дефолтную/максимальную скорость через `default_rate_kb` / `max_rate_kb`:

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
