# prometeus_multigetter

Асинхронный сборщик Prometheus-метрик с нескольких endpoint'ов.
Cохраняет CSV с метриками, сырые тела ответов и человекочитаемую статистику.


## 1. Установка

Требуется Python 3.10+. Зависимость — `aiohttp`.

```bash
# из корня проекта
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install aiohttp
```

## 2. Быстрый старт

1. Задать endpoint'ы в `prometeus_multigetter_conf.json` (файл рядом со скриптом — берётся
   по умолчанию).
2. Запустите сбор:

```bash
./.venv/bin/python prometeus_multigetter.py --suffix smoke_test
```

3. Завершите сбор, когда нужно: **Ctrl-C**, **Ctrl-D** (в интерактивном терминале)
   или `kill -TERM <pid>`. Все данные сохранятся.

Результат появится в `storage/<RUN_ID>_smoke_test/`.

---

## 3. Настройки (settings.json)

По умолчанию используется файл `<имя_скрипта>_conf.json` рядом со скриптом
(`prometeus_multigetter_conf.json`). Другой путь — через `--settings`.

```json
{
  "storage": "data",
  "defaults": {
    "interval": 0.5,
    "timeout": 1.0
  },
  "endpoints": [
    { "name": "lb_os",  "ip": "127.0.0.1", "port": 8731, "path": "/metrics",   "interval": 0.5, "timeout": 1.0 },
    { "name": "lb_kd",  "ip": "127.0.0.1", "port": 8731, "path": "/keepalive", "interval": 0.5 },
    { "name": "lb_bgp", "ip": "127.0.0.1", "port": 8731, "path": "/bgp" }
  ]
}
```

| Поле | Уровень | Назначение |
|------|---------|------------|
| `storage` | корень | базовая папка для результатов |
| `defaults.interval` | корень | интервал опроса по умолчанию, с |
| `defaults.timeout` | корень | таймаут запроса по умолчанию, с |
| `endpoints[].name` | endpoint | уникальное имя (попадает в имена файлов) |
| `endpoints[].ip` / `port` / `path` | endpoint | адрес: URL = `http://<ip>:<port><path>` |
| `endpoints[].interval` | endpoint | переопределяет `defaults.interval` |
| `endpoints[].timeout` | endpoint | переопределяет `defaults.timeout` |

Если у endpoint'а не заданы `interval` / `timeout`, берутся значения из
`defaults`, а при их отсутствии — встроенные (0.5 с и 1.0 с).

---

## 4. Ключи командной строки

| Ключ | По умолчанию | Назначение |
|------|--------------|------------|
| `--settings <path>` | `<имя_скрипта>_conf.json` рядом | путь к JSON с настройками |
| `--prefix <PREFIX>` | пусто | префикс имён папки и файлов |
| `--suffix <SUFFIX>` | пусто | суффикс имён папки и файлов |

`--prefix` и `--suffix` опциональны. Если не заданы — соответствующая часть
имени и её разделитель `_` опускаются (без висящих подчёркиваний).

---

## 5. Структура результатов

Разделитель компонентов имени — `_`. `RUN_ID` формируется один раз на запуск
(`ГГГГ-ММ-ДД_ЧЧhММmСС-микросекунды`).

```
<storage>/<PREFIX>_<RUN_ID>_<SUFFIX>/
    <PREFIX>_<RUN_ID>_<name>_<SUFFIX>.csv                  # метрики (временной ряд)
    <PREFIX>_<RUN_ID>_<name>_<SUFFIX>.raw.txt              # сырые ответы
    <PREFIX>_<RUN_ID>_<name>_<SUFFIX>.run_summary.txt      # параметры запуска
    <PREFIX>_<RUN_ID>_<name>_<SUFFIX>.metrics_summary.csv  # статистика по метрикам
```

Пример (`--prefix bench --suffix run1`):

```
data/bench_2026-06-05_14h30m00-123456_run1/
    bench_2026-06-05_14h30m00-123456_lb_os_run1.csv
    bench_2026-06-05_14h30m00-123456_lb_os_run1.raw.txt
    bench_2026-06-05_14h30m00-123456_lb_os_run1.run_summary.txt
    bench_2026-06-05_14h30m00-123456_lb_os_run1.metrics_summary.csv
    bench_2026-06-05_14h30m00-123456_lb_kd_run1.csv
    ...
```

### CSV
- Первый столбец `timestamp` (`%Y-%m-%d %H:%M:%S.%f`).
- Далее — все метрики, встреченные у этого endpoint'а **хотя бы раз** за запуск
  (по одному столбцу на ключ `name{labels}`).
- Где метрика в конкретном опросе отсутствовала — значение `None`.

### raw.txt
- Все тела HTTP-ответов подряд, каждое в визуально выделенном блоке с временем
  запроса, временем ответа и HTTP-статусом. Удобно для разбора не-Prometheus
  ответов (когда CSV пустой).

### run_summary.txt
Параметры запуска по endpoint'у (без данных по конкретным метрикам):
- время начала/завершения и длительность запуска;
- параметры endpoint'а (name, URL, interval, timeout);
- число успешных/ошибочных опросов;
- число уникальных метрик за запуск.

### metrics_summary.csv
Статистика по каждой метрике, по строке на метрику, **сортировка по имени**.
Колонки:

| Колонка | Значение |
|---------|----------|
| `name` | имя метрики (`metric{labels}`) |
| `hits` | сколько раз метрика была получена за запуск |
| `is_zero` | `T`/`F` — значение всё время было постоянным и строго равным нулю |
| `is_const` | `T`/`F` — значение всё время было постоянным |
| `is_num` | `T`/`F` — все значения были числовыми (`F` — было хотя бы одно нечисловое: NaN/мусор) |
| `min` | минимальное числовое значение за запуск (пусто, если числовых не было) |
| `max` | максимальное числовое значение за запуск |

`min`/`max` всегда считаются только по числовым значениям. Числовыми считаются и
значения в экспоненциальной форме (`1e-3`, `1.5E+10`), и `±Inf`; `NaN` и
нераспознанный текст — нечисловые и опускают `is_num` в `F`.

---

## 6. Завершение

Сбор останавливается с сохранением данных по любому из событий:

- **Ctrl-C** (SIGINT);
- **SIGTERM** (`kill -TERM <pid>`);
- **Ctrl-D** (EOF в stdin) — только в интерактивном терминале. При запуске с
  перенаправленным/закрытым stdin (`</dev/null`, pipe, `nohup`) EOF игнорируется,
  и выход выполняется только по сигналам.

---

## 7. Примеры запуска

```bash
# Настройки по умолчанию (prometeus_multigetter_conf.json рядом со скриптом)
./.venv/bin/python prometeus_multigetter.py

# С префиксом и суффиксом
./.venv/bin/python prometeus_multigetter.py --prefix bench --suffix run1

# Свой файл настроек
./.venv/bin/python prometeus_multigetter.py --settings /path/to/my_settings.json --suffix night

# В фоне, остановка по сигналу
nohup ./.venv/bin/python prometeus_multigetter.py --suffix soak </dev/null > getter.log 2>&1 &
# ... позже:
kill -TERM <pid>
```

---

## 8. Локальное тестирование

В папке [test_server/](test_server/) есть полноценный mock Prometheus-сервер,
который эмулирует «плавающий» набор метрик: каждый третий запрос исключает ~10%
метрик (детерминированно, для воспроизводимости).

```bash
# 1) Поднять mock-сервер (в отдельном терминале)
./.venv/bin/python test_server/mock_prometheus_server.py --port 8731 \
    --metrics 40 --drop-every 3 --drop-fraction 0.10

# 2) Запустить сбор против него
./.venv/bin/python prometeus_multigetter.py \
    --settings test_server/test_settings.json --prefix bench --suffix demo
# остановить через kill -TERM <pid> или Ctrl-C
```

### Автотесты (pytest)

```bash
./.venv/bin/python -m pytest tests/ -v
```

Покрывают парсинг метрик, формирование имён, статистику метрик (`MetricStat`:
is_zero / is_const / min / max), а также интеграционный сценарий: реальный
подъём mock-сервера, опрос, проверка CSV (включая `None` на месте выпавших
метрик), маркеров raw.txt, run_summary.txt и metrics_summary.csv.
