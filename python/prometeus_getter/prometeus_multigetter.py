#!/usr/bin/env python3
"""
Асинхронный сборщик Prometheus-метрик с нескольких endpoint'ов в рамках одного
запуска (теста).

Скрипт параллельно (asyncio + aiohttp, один процесс) опрашивает несколько
серверных узлов/endpoint'ов, описанных в settings.json, и для каждого endpoint'а
сохраняет:
  - <...>.csv                 — метрики в табличном виде (timestamp + колонки);
  - <...>.raw.txt             — все сырые тела HTTP-ответов с временем запроса/ответа;
  - <...>.run_summary.txt     — параметры запуска (человекочитаемо);
  - <...>.metrics_summary.csv — статистику по каждой метрике
                                (hits, is_zero, is_const, min, max).

Все файлы запуска складываются во вложенную папку с именем, содержащим RUN_ID,
а также опциональные --prefix / --suffix.

Завершение (с сохранением данных) — по сигналам SIGINT (Ctrl-C), SIGTERM или по
EOF в stdin (Ctrl-D).

Подробности — см. wiki/todo/task_001_spec.md.
"""

import argparse
import asyncio
import csv
import json
import re
import signal
import sys
from collections import Counter
from datetime import datetime as dt
from pathlib import Path

import aiohttp


# --------------------------------------------------------------------------- #
# Константы
# --------------------------------------------------------------------------- #

TS_FMT = "%Y-%m-%d %H:%M:%S.%f"           # формат меток времени в данных
RUN_ID = dt.now().strftime("%Y-%m-%d_%Hh%Mm%S-%f")

DEFAULT_INTERVAL = 0.5                      # с, если не задано в settings
DEFAULT_TIMEOUT = 1.0                       # с, если не задано в settings


# --------------------------------------------------------------------------- #
# Парсинг Prometheus
# --------------------------------------------------------------------------- #

_METRIC_RE = re.compile(
    r"^(?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)"
    r"(?:\{(?P<labels>[^}]*)\})?"
    r"\s+"
    r"(?P<value>NaN|[+-]?Inf|[0-9.eE+-]+)"
)
_LABEL_RE = re.compile(r'(\w+)="((?:[^"\\]|\\.)*)"')


def parse_metrics(text: str) -> dict:
    """
    Парсит текстовое представление Prometheus метрик.
    Возвращает словарь {metric_name{labels}: value_str}.
    """
    metrics = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = _METRIC_RE.match(line)
        if not m:
            continue
        name = m.group("name")
        labels_str = m.group("labels")
        value = m.group("value")

        if labels_str:
            pairs = _LABEL_RE.findall(labels_str)
            pairs.sort(key=lambda x: x[0])
            label_parts = [f'{k}="{v}"' for k, v in pairs]
            key = f"{name}{{{','.join(label_parts)}}}"
        else:
            key = name
        metrics[key] = value
    return metrics


# --------------------------------------------------------------------------- #
# Имена файлов
# --------------------------------------------------------------------------- #

def join_name(*parts: str) -> str:
    """Склеивает непустые части через '_' (без висящих разделителей)."""
    return "_".join(p for p in parts if p)


# --------------------------------------------------------------------------- #
# Статистика по отдельной метрике
# --------------------------------------------------------------------------- #

class MetricStat:
    """
    Накапливает статистику значений одной метрики за весь прогон:
      hits     — сколько раз метрика была получена;
      is_const — значение было постоянным всё время;
      is_zero  — значение было постоянным и строго равным нулю;
      is_num   — все значения были числовыми (F — было хотя бы одно нечисловое,
                 например NaN или нераспознанный текст);
      min/max  — минимальное/максимальное числовое значение.

    Числовыми считаются в т.ч. значения в экспоненциальной форме (1e-3, 1.5E+10)
    и ±Inf. NaN и нераспознанные значения считаются нечисловыми.
    """

    def __init__(self):
        self.hits = 0
        self.min = None
        self.max = None
        self._num_count = 0          # сколько раз значение было числом (без NaN)
        self._nonnum = set()         # различающиеся НЕ-числовые значения
        self._all_zero = True        # все числовые значения == 0

    def update(self, value_str: str) -> None:
        self.hits += 1
        try:
            v = float(value_str)
        except ValueError:
            self._nonnum.add(value_str)
            self._all_zero = False
            return
        if v != v:                   # NaN: в min/max не учитываем
            self._nonnum.add("NaN")
            self._all_zero = False
            return
        self._num_count += 1
        if self.min is None or v < self.min:
            self.min = v
        if self.max is None or v > self.max:
            self.max = v
        if v != 0.0:
            self._all_zero = False

    @property
    def is_const(self) -> bool:
        if self._nonnum:
            # Постоянство при наличии не-числовых значений — только если все
            # значения одинаковы и не было числовых.
            return self._num_count == 0 and len(self._nonnum) == 1
        return self.min == self.max   # все значения числовые

    @property
    def is_zero(self) -> bool:
        return self.hits > 0 and self._all_zero and self.is_const

    @property
    def is_num(self) -> bool:
        """T, если все полученные значения были числовыми (без NaN/мусора)."""
        return self.hits > 0 and not self._nonnum


# --------------------------------------------------------------------------- #
# Состояние одного endpoint'а
# --------------------------------------------------------------------------- #

class EndpointCollector:
    """Накапливает данные опроса одного endpoint'а в памяти."""

    def __init__(self, cfg: dict, defaults: dict):
        self.name = cfg["name"]
        self.ip = cfg["ip"]
        self.port = cfg["port"]
        self.path = cfg.get("path", "/metrics")
        self.interval = float(cfg.get("interval", defaults.get("interval", DEFAULT_INTERVAL)))
        self.timeout = float(cfg.get("timeout", defaults.get("timeout", DEFAULT_TIMEOUT)))
        self.url = f"http://{self.ip}:{self.port}{self.path}"

        # Накопители
        self.all_metrics = set()           # все встреченные ключи метрик
        self.metric_counts = Counter()     # сколько раз получена каждая метрика
        self.metric_stats = {}             # ключ метрики -> MetricStat
        self.rows = []                     # список dict для CSV
        self.raw_blocks = []               # сырые тела ответов (тексты блоков)

        # Статистика опросов
        self.ok_count = 0
        self.err_count = 0
        self.started_at = None
        self.finished_at = None


# --------------------------------------------------------------------------- #
# Опрос endpoint'а
# --------------------------------------------------------------------------- #

RAW_SEP = "=" * 70


def _raw_block(collector_name: str, req_ts: str, resp_ts: str,
               status, body: str) -> str:
    """Формирует визуально выделенный блок одного ответа для raw.txt."""
    head = (
        f"\n{RAW_SEP}\n"
        f">>> BEGIN  endpoint={collector_name}\n"
        f"           request  = {req_ts}\n"
        f"           response = {resp_ts}\n"
        f"           status   = {status}\n"
        f"{RAW_SEP}\n"
    )
    tail = (
        f"\n{RAW_SEP}\n"
        f"<<< END    endpoint={collector_name}  request={req_ts}\n"
        f"{RAW_SEP}\n"
    )
    return head + body + tail


async def poll_endpoint(collector: EndpointCollector,
                        session: aiohttp.ClientSession,
                        stop_event: asyncio.Event) -> None:
    """Цикл опроса одного endpoint'а до установки stop_event."""
    collector.started_at = dt.now()
    timeout = aiohttp.ClientTimeout(total=collector.timeout)

    while not stop_event.is_set():
        loop_start = asyncio.get_event_loop().time()
        req_ts = dt.now().strftime(TS_FMT)

        status = "ERROR"
        body = ""
        try:
            async with session.get(collector.url, timeout=timeout) as resp:
                status = resp.status
                body = await resp.text()
                ok = resp.status == 200
        except Exception as e:               # noqa: BLE001 - логируем любую ошибку
            body = f"[request error] {e!r}"
            ok = False
            print(f"[{collector.name}] Ошибка запроса: {e}", file=sys.stderr)

        resp_ts = dt.now().strftime(TS_FMT)

        # Сырой ответ — всегда в raw
        collector.raw_blocks.append(
            _raw_block(collector.name, req_ts, resp_ts, status, body)
        )

        if ok:
            collector.ok_count += 1
            current = parse_metrics(body)
            collector.all_metrics.update(current.keys())
            collector.metric_counts.update(current.keys())
            for key, value in current.items():
                collector.metric_stats.setdefault(key, MetricStat()).update(value)

            row = {"timestamp": req_ts}
            row.update(current)              # отсутствующие колонки -> restval='None'
            collector.rows.append(row)
        else:
            collector.err_count += 1

        # Выдерживаем интервал с учётом времени запроса
        elapsed = asyncio.get_event_loop().time() - loop_start
        delay = max(0.0, collector.interval - elapsed)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=delay)
        except asyncio.TimeoutError:
            pass

    collector.finished_at = dt.now()


# --------------------------------------------------------------------------- #
# Сохранение результатов
# --------------------------------------------------------------------------- #

def save_csv(collector: EndpointCollector, path: Path) -> None:
    columns = ["timestamp"] + sorted(collector.all_metrics)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns, restval="None")
        writer.writeheader()
        writer.writerows(collector.rows)


def save_raw(collector: EndpointCollector, path: Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"RAW responses — endpoint '{collector.name}' — URL {collector.url}\n")
        f.writelines(collector.raw_blocks)


def save_run_summary(collector: EndpointCollector, path: Path) -> None:
    """Параметры запуска по endpoint'у (без данных по конкретным метрикам)."""
    started = collector.started_at.strftime(TS_FMT) if collector.started_at else "—"
    finished = collector.finished_at.strftime(TS_FMT) if collector.finished_at else "—"
    if collector.started_at and collector.finished_at:
        duration = (collector.finished_at - collector.started_at).total_seconds()
        duration_s = f"{duration:.3f} с"
    else:
        duration_s = "—"

    sep = "=" * 72
    sub = "-" * 72
    lines = []
    lines.append(sep)
    lines.append(f"  RUN SUMMARY — endpoint: {collector.name}")
    lines.append(sep)
    lines.append("")
    lines.append("  Время запуска")
    lines.append(sub)
    lines.append(f"    Начало     : {started}")
    lines.append(f"    Завершение : {finished}")
    lines.append(f"    Длительность: {duration_s}")
    lines.append("")
    lines.append("  Параметры endpoint")
    lines.append(sub)
    lines.append(f"    name     : {collector.name}")
    lines.append(f"    url      : {collector.url}")
    lines.append(f"    interval : {collector.interval} с")
    lines.append(f"    timeout  : {collector.timeout} с")
    lines.append("")
    lines.append("  Статистика опросов")
    lines.append(sub)
    lines.append(f"    Успешных (HTTP 200) : {collector.ok_count}")
    lines.append(f"    С ошибкой           : {collector.err_count}")
    lines.append(f"    Всего               : {collector.ok_count + collector.err_count}")
    lines.append("")
    lines.append("  Метрики")
    lines.append(sub)
    lines.append(f"    Уникальных метрик за запуск : {len(collector.all_metrics)}")
    lines.append("    (детали по каждой метрике — см. *.metrics_summary.csv)")
    lines.append("")
    lines.append(sep)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _fmt_num(v) -> str:
    """Числовое значение для CSV; пусто, если значения не было."""
    if v is None:
        return ""
    return repr(v)


def save_metrics_summary(collector: EndpointCollector, path: Path) -> None:
    """Статистика по каждой метрике в CSV, сортировка по имени метрики."""
    columns = ["name", "hits", "is_zero", "is_const", "is_num", "min", "max"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        for name in sorted(collector.metric_stats):
            st = collector.metric_stats[name]
            writer.writerow([
                name,
                st.hits,
                "T" if st.is_zero else "F",
                "T" if st.is_const else "F",
                "T" if st.is_num else "F",
                _fmt_num(st.min),
                _fmt_num(st.max),
            ])


def save_all(collectors, run_dir: Path, prefix: str, suffix: str) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    for c in collectors:
        base = join_name(prefix, RUN_ID, c.name, suffix)
        csv_path = run_dir / f"{base}.csv"
        raw_path = run_dir / f"{base}.raw.txt"
        run_sum_path = run_dir / f"{base}.run_summary.txt"
        met_sum_path = run_dir / f"{base}.metrics_summary.csv"

        save_csv(c, csv_path)
        save_raw(c, raw_path)
        save_run_summary(c, run_sum_path)
        save_metrics_summary(c, met_sum_path)

        print(
            f"[{c.name}] сохранено: {csv_path.name}, {raw_path.name}, "
            f"{run_sum_path.name}, {met_sum_path.name} "
            f"(строк: {len(c.rows)}, метрик: {len(c.all_metrics)})",
            file=sys.stderr,
        )


# --------------------------------------------------------------------------- #
# Загрузка settings
# --------------------------------------------------------------------------- #

def load_settings(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        settings = json.load(f)

    if "storage" not in settings:
        raise ValueError("В settings отсутствует обязательное поле 'storage'")
    endpoints = settings.get("endpoints")
    if not endpoints:
        raise ValueError("В settings отсутствует непустой список 'endpoints'")

    names = [e.get("name") for e in endpoints]
    if None in names:
        raise ValueError("У каждого endpoint должно быть поле 'name'")
    if len(names) != len(set(names)):
        raise ValueError("Имена endpoint'ов ('name') должны быть уникальными")

    return settings


# --------------------------------------------------------------------------- #
# Основной асинхронный цикл
# --------------------------------------------------------------------------- #

async def run(collectors) -> None:
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    # Сигналы SIGINT / SIGTERM
    def _request_stop():
        if not stop_event.is_set():
            print("\nЗавершение работы...", file=sys.stderr)
            stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_stop)
        except NotImplementedError:          # на случай нестандартных платформ
            signal.signal(sig, lambda *_: _request_stop())

    # Слушатель EOF в stdin (Ctrl-D)
    async def stdin_watcher():
        try:
            while not stop_event.is_set():
                line = await loop.run_in_executor(None, sys.stdin.readline)
                if line == "":               # EOF
                    print("\nEOF в stdin — завершение...", file=sys.stderr)
                    stop_event.set()
                    break
        except Exception:                    # noqa: BLE001
            pass

    async with aiohttp.ClientSession() as session:
        tasks = [
            asyncio.create_task(poll_endpoint(c, session, stop_event))
            for c in collectors
        ]
        # EOF (Ctrl-D) отслеживаем только в интерактивном режиме; при
        # перенаправлении stdin (/dev/null, pipe, nohup) выходим только по сигналам.
        watcher = None
        if sys.stdin and sys.stdin.isatty():
            watcher = asyncio.create_task(stdin_watcher())
        await asyncio.gather(*tasks)
        if watcher is not None:
            watcher.cancel()


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #

def parse_args(argv=None) -> argparse.Namespace:
    script = Path(__file__)
    default_settings = script.with_name(f"{script.stem}_conf.json")
    parser = argparse.ArgumentParser(
        description="Асинхронный сбор Prometheus-метрик с нескольких endpoint'ов."
    )
    parser.add_argument(
        "--settings", type=Path, default=default_settings,
        help=f"путь к JSON с настройками (по умолчанию: {default_settings.name})",
    )
    parser.add_argument("--prefix", default="", help="префикс имён папки/файлов")
    parser.add_argument("--suffix", default="", help="суффикс имён папки/файлов")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)

    if not args.settings.exists():
        print(f"Файл настроек не найден: {args.settings}", file=sys.stderr)
        return 2

    try:
        settings = load_settings(args.settings)
    except (ValueError, json.JSONDecodeError) as e:
        print(f"Ошибка в settings: {e}", file=sys.stderr)
        return 2

    defaults = settings.get("defaults", {})
    collectors = [EndpointCollector(cfg, defaults) for cfg in settings["endpoints"]]

    storage = Path(settings["storage"])
    run_dir = storage / join_name(args.prefix, RUN_ID, args.suffix)

    print(
        f"RUN_ID={RUN_ID}  endpoints={len(collectors)}  -> {run_dir}",
        file=sys.stderr,
    )
    for c in collectors:
        print(f"  • {c.name}: {c.url} (interval={c.interval}s, timeout={c.timeout}s)",
              file=sys.stderr)

    try:
        asyncio.run(run(collectors))
    except KeyboardInterrupt:
        pass
    finally:
        save_all(collectors, run_dir, args.prefix, args.suffix)

    return 0


if __name__ == "__main__":
    sys.exit(main())
