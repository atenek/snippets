# Тестовые фикстуры и вспомогательные файлы

## Статические файлы для static_serve (`static/`)

Директория: `static/`

| Файл | Размер | Назначение |
|---|---|---|
| `test_text.txt` | 440 байт | Текстовый файл (ASCII). Проверка: text/plain Content-Type, точное совпадение контента |
| `test_binary.bin` | 20480 байт | Бинарный файл (байты 0–255 × 80). Проверка: бинарный контент без искажений при передаче |

**Создание файлов:**

```python
# test_text.txt
txt = ("This is a test file for static_serve download testing.\n" * 8)
with open("static/test_text.txt", "w") as f:
    f.write(txt)

# test_binary.bin
data = bytes(range(256)) * 80
with open("static/test_binary.bin", "wb") as f:
    f.write(data)
```

Тест `test_list_contains_expected_files` автоматически сверяет содержимое директории с ответом `/files`, поэтому добавление файлов в `static/` не требует изменений в тестах.

---

## Рулесет для static_serve (`rulesets/rules_static_serve.json`)

```json
{
  "name": "rules_static_serve",
  "rules": [
    {
      "method": "GET",
      "path": "/download/*",
      "response": {
        "service": "static_serve",
        "files_dir": "./static",
        "default_rate_kb": 100,
        "max_rate_kb": 500
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

Параметры для тестов берутся прямо из этого файла:
- `default_rate_kb = 100` → тест проверяет X-Rate-Limit: 100 KB/s без ?rate=
- `max_rate_kb = 500` → тест проверяет что ?rate=99999 обрезается до 500

---

## Фикстура сервера (`server`)

Scope: **session** — сервер запускается один раз на весь прогон.

```python
@pytest.fixture(scope="session")
def server():
    proc = subprocess.Popen(
        [sys.executable, str(SERVER_SCRIPT), "--ip", SERVER_IP],
        ...
        cwd=str(PROJECT_DIR),
    )
    # Ожидание готовности: попытка подключиться к MGMT_PORT
    # Таймаут: SERVER_STARTUP_TIMEOUT = 4.0 сек
    yield proc
    proc.terminate()
```

Сервер стартует без `--startup-config` (точнее, использует дефолтный путь `./startup-config.json`). Если файл существует, он будет применён при старте.

---

## Хелперы

### `_req(method, url, **kwargs)`

Обёртка над `requests.request` с логированием запроса и ответа.

```python
resp = _req("GET", f"http://{SERVER_IP}:{MGMT_PORT}/status")
resp = _req("POST", f"http://{SERVER_IP}:{MGMT_PORT}/mgmt",
            json=[{"service": "tcp:62224", "mode": "tcp_echo"}])
```

Все вызовы логируются в `runs/tests/run_<RUN_ID>.log`.

### `_apply_service(svc, mode, ruleset_name=None)`

Применяет режим через POST /mgmt и ждёт 0.15с для завершения старта.

```python
_apply_service("tcp:62224", "http", "rules_hc-text_200_ok")
_apply_service("tcp:62225", "tcp_echo")
_apply_service("tcp:62226", None)  # остановить
```

### `_resolve_ruleset(ref)`

Приводит ссылку на ruleset к чистому имени:
- `"rulesets/rules_hc-text_200_ok.json"` → `"rules_hc-text_200_ok"`
- `"rules_hc-text_200_ok"` → `"rules_hc-text_200_ok"`

---

## Константы

| Константа | Значение | Назначение |
|---|---|---|
| `SERVER_IP` | `"127.0.0.1"` | IP для всех соединений |
| `MGMT_PORT` | `62228` | Порт management API |
| `SERVER_STARTUP_TIMEOUT` | `4.0` сек | Ожидание готовности сервера |
| `SOCKET_TIMEOUT` | `5.0` сек | Таймаут для большинства HTTP-запросов |

Для операций, затрагивающих остановку множества сервисов (`/config/load`, `/mgmt` с 5+ сервисами), таймаут масштабируется: `max(5.0, N*2+3)`.
