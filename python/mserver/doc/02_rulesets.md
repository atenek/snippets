# Rulesets — формат и типы правил

## Что такое ruleset

Ruleset — именованный набор правил, по которым HTTP-сервис отвечает на запросы.  
Хранится в JSON-файле в директории `rulesets/` (по умолчанию `./rulesets`).  
Загружается при старте сервера. Для добавления нового ruleset нужен перезапуск.

Один файл может содержать **один ruleset** (объект) или **массив ruleset** (массив объектов).

---

## Структура файла

```json
{
  "name": "имя_ruleset",
  "rules": [ ... ]
}
```

| Поле | Тип | Описание |
|---|---|---|
| `name` | string | Уникальный идентификатор ruleset |
| `rules` | array | Список правил; проверяются сверху вниз, побеждает первое совпадение |

---

## Логика сопоставления (Rule.match)

Для каждого правила проверяется:

1. **method** — HTTP-метод запроса (`GET`, `POST`, …) или `*` (любой)
2. **path** — путь запроса, три варианта:
   - `"*"` — любой путь
   - `"/exact/path"` — точное совпадение
   - `"/prefix/*"` — prefix-match: путь начинается с `/prefix/`

Если ни одно правило не совпало — HTTP 404 `Not Found`.

---

## Тип 1: обычный HTTP-ответ (`response.code`)

```json
{
  "method": "GET",
  "path": "/health",
  "response": {
    "code": 200,
    "body": "healthy",
    "headers": {}
  }
}
```

| Поле | Тип | Описание |
|---|---|---|
| `response.code` | int | HTTP-код ответа (100–599) |
| `response.body` | string \| object | Тело ответа. Строка → `text/plain`; объект → `application/json` |
| `response.headers` | object | Дополнительные HTTP-заголовки ответа |
| `response.Content-Type` | string | Явно задать Content-Type (опционально) |

### Подстановка переменных сессии

В полях `body` и `headers` можно использовать переменные:

| Переменная | Значение |
|---|---|
| `$SRC_IP` / `${SRC_IP}` | IP-адрес клиента |
| `$SRC_PORT` / `${SRC_PORT}` | Порт клиента |
| `$DST_IP` / `${DST_IP}` | IP сервера (порта) |
| `$DST_PORT` / `${DST_PORT}` | Порт сервера |

Пример:
```json
{
  "method": "*",
  "path": "/whoami",
  "response": {
    "code": 200,
    "body": {"client": "$SRC_IP:$SRC_PORT", "server": "$DST_IP:$DST_PORT"}
  }
}
```

---

## Тип 2: раздача файлов (`response.service = "static_serve"`)

```json
{
  "method": "GET",
  "path": "/download/*",
  "response": {
    "service": "static_serve",
    "files_dir": "./static"
  }
}
```

| Поле | Тип | По умолчанию | Описание |
|---|---|---|---|
| `response.service` | `"static_serve"` | — | Активирует раздачу файлов |
| `response.files_dir` | string | `"./static"` | Директория с файлами (относительно CWD) |
| `response.default_rate_kb` | int | — (нет) | *Опционально.* Скорость по умолчанию, KB/s. Без него — **без лимита** |
| `response.max_rate_kb` | int | — (нет) | *Опционально.* Потолок для `?rate=`. Без него — `?rate=` не обрезается |

**Как работает:**
- Путь в правиле должен быть `"/prefix/*"` (prefix-match)
- Имя файла извлекается из пути: `/download/file.bin` → `file.bin`
- **По умолчанию скорость не ограничена.** Лимит включается только query-параметром `?rate=<KB/s>`:  
  `GET /download/file.bin?rate=50` — скачать со скоростью 50 KB/s
- Если в правиле задан `max_rate_kb` — `rate` из запроса обрезается сверху до него; иначе применяется как есть. `rate=0` (или отрицательное) → без лимита
- Запрос корня префикса (`GET /download/`) возвращает **HTML-листинг** директории (autoindex со ссылками на файлы)
- Если файл не найден — HTTP 404
- Защита от path traversal: `os.path.basename()` на имени файла

Ответ при успехе (без `?rate`):
```
HTTP 200
Content-Type: <по расширению файла>
Content-Disposition: attachment; filename="file.bin"
X-Rate-Limit: unlimited
Content-Length: <размер файла>
```

> **Параметр `?delay=<ms>`** работает на любом запросе к серверу (не только `static_serve`) и добавляет задержку перед ответом (0…60000 мс). Подробнее — [06_static_serve.md](06_static_serve.md#задержка-ответа-delay).

---

## Тип 3: листинг файлов (`response.service = "static_list"`)

```json
{
  "method": "GET",
  "path": "/files",
  "response": {
    "service": "static_list",
    "files_dir": "./static"
  }
}
```

Возвращает JSON со списком файлов в директории:

```json
{
  "files": [
    {
      "name": "archive.tar.gz",
      "size": 10485760,
      "type": "application/x-tar",
      "modified": "2026-05-30T14:22:01"
    }
  ],
  "count": 1
}
```

Если директория не существует — возвращает `{"files": [], "count": 0, "error": "..."}`.

---

## Полный пример ruleset с несколькими типами правил

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

---

## Несколько ruleset в одном файле

```json
[
  {
    "name": "rules_healthy",
    "rules": [
      {"method": "GET", "path": "/health", "response": {"code": 200, "body": "healthy", "headers": {}}}
    ]
  },
  {
    "name": "rules_degraded",
    "rules": [
      {"method": "GET", "path": "/health", "response": {"code": 503, "body": "degraded", "headers": {}}}
    ]
  }
]
```

---

## Проверка загруженных ruleset

```bash
curl -s http://127.0.0.1:62228/rulesets | python3 -m json.tool
```

```json
{
  "rulesets": [
    {"name": "rules_healthy",    "rules_count": 3},
    {"name": "rules_fileserver", "rules_count": 4}
  ]
}
```
