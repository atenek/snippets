# Тест-сюит — обзор

## Расположение

| Путь | Назначение |
|---|---|
| `tests/test_http_server_multiport_mgmt.py` | Единственный тест-файл, весь сюит |
| `test_config/test-config.json` | Сценарии тестирования (`tests_configs`) |
| `test_config/startup/` | Тестовые startup-конфиги (6 файлов) |
| `rulesets/` | Рулесеты, загружаемые сервером при старте |
| `static/` | Файлы для тестирования static_serve |
| `runs/tests/` | Логи тест-прогонов (`run_<RUN_ID>.log`) |

---

## Запуск

```bash
# Все тесты
python3 -m pytest tests/

# С подробным выводом
python3 -m pytest tests/ -v

# Конкретный класс
python3 -m pytest tests/ -v -k TestStaticServe

# Конкретный тест
python3 -m pytest tests/ -v -k test_download_existing_file

# Быстрый: прервать при первом падении
python3 -m pytest tests/ -x

# Без захвата stdout
python3 -m pytest tests/ -s
```

---

## Архитектура сюита

Сервер запускается **один раз на сессию** (`scope="session"`) через `subprocess.Popen`. Каждый тест применяет нужный ему режим через `POST /mgmt` непосредственно перед проверкой. Это исключает зависимость от порядка тестов.

```
server fixture (scope=session)
│
├── TestMgmtAPI         ← тесты API управления
├── TestHTTPRules       ← тесты HTTP-ответов по rulesets
├── TestStaticServe     ← тесты static_serve (скачивание)
├── TestStaticList      ← тесты static_list (листинг)
├── TestTCPEcho         ← тесты TCP echo
├── TestTCPLogger       ← тесты TCP logger
├── TestUDPEcho         ← тесты UDP echo
├── TestUDPLogger       ← тесты UDP logger
├── TestNullServices    ← тесты остановки сервисов
├── TestStartupConfigs  ← тесты применимости startup-конфигов
└── TestConfigSaveLoad  ← тесты save/load roundtrip
```

---

## Параметризация

Большинство тестов параметризованы: каждый тест-метод запускается по одному разу на каждую комбинацию сценарий × сервис.

| Параметр-множество | Откуда берётся |
|---|---|
| `_HTTP_RULE_PARAMS` | Все обычные правила (response.code) из всех HTTP-сервисов всех сценариев |
| `_STATIC_SERVE_PARAMS` | HTTP-сервисы со static_serve правилами |
| `_STATIC_LIST_PARAMS` | HTTP-сервисы со static_list правилами |
| `_TCP_ECHO_PARAMS` | Все tcp_echo сервисы из всех сценариев |
| `_TCP_LOGGER_PARAMS` | Все tcp_logger сервисы |
| `_UDP_ECHO_PARAMS` | Все udp_echo сервисы |
| `_UDP_LOGGER_PARAMS` | Все udp_logger сервисы |
| `_NULL_PARAMS` | Все mode=null/off сервисы |
| `_STARTUP_CFG_PARAMS` | Файлы из `test_config/startup/` |

Если подходящих сервисов нет — тест пропускается (`pytest.mark.skip`) вместо ошибки.

---

## Лог тест-прогона

Каждый прогон пишет лог в `runs/tests/run_<YYYY-MM-DD_HH-MM-SS.mmm>.log`:

```
2026-06-02 10:00:00  INFO     >>> GET  http://127.0.0.1:62228/status
2026-06-02 10:00:00  INFO     <<< 200  body='{"server": ...'
```

Все HTTP-запросы к серверу (через `_req()`) логируются с методом, URL и телом ответа.

---

## Итоги последнего прогона

```
104 passed in 119.50s
```

| Класс | Кол-во тестов |
|---|---|
| TestMgmtAPI | 14 |
| TestHTTPRules | 34 |
| TestStaticServe | 10 |
| TestStaticList | 3 |
| TestTCPEcho | 12 |
| TestTCPLogger | 6 |
| TestUDPEcho | 8 |
| TestUDPLogger | 4 |
| TestNullServices | 3 |
| TestStartupConfigs | 6 |
| TestConfigSaveLoad | 3 |
