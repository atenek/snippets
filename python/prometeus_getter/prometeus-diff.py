#!/usr/bin/env python3
"""
Однократное сравнение Prometheus-метрик двух endpoint'ов.

Скрипт одновременно (asyncio + aiohttp) опрашивает два endpoint'а, заданных в
settings.json (по умолчанию `prometeus-diff_conf.json` рядом со скриптом),
парсит ответы в формате Prometheus и сравнивает полученные метрики:

  - метрика есть только на одном endpoint'е -> строка с её значением и "-";
  - метрика есть на обоих, но значения отличаются -> строка с двумя значениями.

Какие метрики вообще участвуют в сравнении, определяют `white_list` и
`black_list` — списки шаблонов **регулярных выражений** (`re.fullmatch` по
имени метрики без label'ов). Шаблоны в списке проверяются по порядку, до
первого совпадения — как только один шаблон совпал, остальные в этом же
списке уже не проверяются.

  - если `white_list` непустой — сравниваются только метрики, совпавшие
    хотя бы с одним его шаблоном; остальные считаются "замаскированы
    white_list'ом" и в сравнении не участвуют;
  - если `white_list` пуст/отсутствует — в сравнение попадают все метрики;
  - к тому, что осталось после `white_list`, применяется `black_list`:
    метрики, совпавшие хотя бы с одним его шаблоном, исключаются
    ("замаскированы black_list'ом").

Первой строкой выводится summary: сколько метрик получено с каждого
endpoint'а, сколько совпало/отличается/замаскировано white_list'ом/
замаскировано black_list'ом.

Скрипт выполняет одно сравнение за запуск; многократность обеспечивается
внешней утилитой, например `watch -n 1 'python3 prometeus-diff.py'`.

Результат выводится на экран (stdout) и дублируется в лог. По умолчанию
каждый запуск создаёт свой файл
`log/run_<ГГГГ-ММ-ДД>_<ЧЧ>h<ММ>m<СС>-<микросекунды>.log`. Чтобы при
многократном запуске (например, под `watch`) все прогоны одной серии
писались в один файл, а не плодили файл на каждый тик, передайте
`--log-datetime <метка>` с единой меткой времени, зафиксированной один раз
в начале серии (см. пример в prometeus-diff.md) — тогда лог будет
`log/run_<метка>.log`, и каждый запуск дописывается в него отдельным
блоком.

[Подробности](prometeus-diff.md)
"""

import argparse
import asyncio
import json
import re
import sys
from datetime import datetime as dt
from pathlib import Path
from typing import NamedTuple, Optional

import aiohttp


DEFAULT_TIMEOUT = 5.0        # с, если не задано в settings


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


def base_name(key: str) -> str:
    """Имя метрики без label'ов: часть ключа до первой '{'."""
    idx = key.find("{")
    return key if idx == -1 else key[:idx]


# --------------------------------------------------------------------------- #
# white_list / black_list
# --------------------------------------------------------------------------- #

def matches_any(name: str, patterns) -> bool:
    """
    True, если `name` совпадает хотя бы с одним regexp из `patterns`
    (`re.fullmatch` — шаблон должен совпасть с именем целиком).

    Шаблоны проверяются последовательно, по порядку списка; при первом
    совпадении проверка останавливается и результат считается найденным
    (остальные шаблоны не проверяются).
    """
    for pattern in patterns:
        if re.fullmatch(pattern, name):
            return True
    return False


# --------------------------------------------------------------------------- #
# Сравнение значений
# --------------------------------------------------------------------------- #

def values_equal(v1: Optional[str], v2: Optional[str]) -> bool:
    """Совпадение значений: сперва как строки, затем — как числа (42 == 42.0)."""
    if v1 == v2:
        return True
    if v1 is None or v2 is None:
        return False
    try:
        return float(v1) == float(v2)
    except ValueError:
        return False


class DiffRow(NamedTuple):
    name: str
    value1: Optional[str]      # None, если метрика отсутствует на endpoint1
    value2: Optional[str]      # None, если метрика отсутствует на endpoint2


class CompareResult(NamedTuple):
    n1: int                          # метрик получено от endpoint1
    n2: int                          # метрик получено от endpoint2
    matched: int                     # совпало (прошли white_list и black_list)
    masked_by_white_list: int        # не совпали с white_list (если он непуст)
    masked_by_black_list: int        # совпали с black_list
    diffs: list                      # list[DiffRow], отсортировано по имени


def compare_metrics(metrics1: dict, metrics2: dict, white_list, black_list) -> CompareResult:
    all_keys = set(metrics1) | set(metrics2)

    # white_list непустой -> сравниваем только совпавшие с ним метрики;
    # white_list пустой -> сравниваем все.
    if white_list:
        allowed_keys = {k for k in all_keys if matches_any(base_name(k), white_list)}
    else:
        allowed_keys = set(all_keys)
    masked_by_white_list = len(all_keys) - len(allowed_keys)

    # black_list применяется поверх того, что осталось после white_list.
    masked_keys = {k for k in allowed_keys if matches_any(base_name(k), black_list)}
    compared_keys = allowed_keys - masked_keys

    matched = 0
    diffs = []
    for key in sorted(compared_keys):
        v1 = metrics1.get(key)
        v2 = metrics2.get(key)
        if values_equal(v1, v2):
            matched += 1
        else:
            diffs.append(DiffRow(key, v1, v2))

    return CompareResult(
        n1=len(metrics1),
        n2=len(metrics2),
        matched=matched,
        masked_by_white_list=masked_by_white_list,
        masked_by_black_list=len(masked_keys),
        diffs=diffs,
    )


# --------------------------------------------------------------------------- #
# Отчёт
# --------------------------------------------------------------------------- #

def format_report(result: CompareResult, errors) -> str:
    lines = [
        f'SUMMARY: total: ({result.n1:5}  /{result.n2:5} ); '
        f'"eq": {result.matched:5}; "diff": {len(result.diffs):5}; '
        f'"match_white_list": {result.masked_by_white_list:5}; '
        f'"filter_black_list":{result.masked_by_black_list:5}.' ]
    for row in result.diffs:
        v1 = row.value1 if row.value1 is not None else "-"
        v2 = row.value2 if row.value2 is not None else "-"
        lines.append(f"{row.name:80}: {v1} <-vs-> {v2}")
    if errors:
        lines.append("")
        lines.append("ERRORS:")
        lines.extend(f"  {e}" for e in errors)
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Опрос endpoint'ов
# --------------------------------------------------------------------------- #

async def fetch_metrics(session: aiohttp.ClientSession, url: str, timeout: float):
    """Возвращает (metrics_dict, error_str_or_None)."""
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            body = await resp.text()
            if resp.status != 200:
                return {}, f"{url}: HTTP {resp.status}"
            return parse_metrics(body), None
    except Exception as e:                   # noqa: BLE001 - любая ошибка запроса
        return {}, f"{url}: {e!r}"


async def fetch_both(url1: str, url2: str, timeout: float):
    async with aiohttp.ClientSession() as session:
        (m1, e1), (m2, e2) = await asyncio.gather(
            fetch_metrics(session, url1, timeout),
            fetch_metrics(session, url2, timeout),
        )
    errors = [e for e in (e1, e2) if e]
    return m1, m2, errors


# --------------------------------------------------------------------------- #
# Настройки
# --------------------------------------------------------------------------- #

def _validate_patterns(patterns, field_name: str) -> None:
    """Проверяет, что все шаблоны в списке — валидные регулярные выражения."""
    for pattern in patterns:
        try:
            re.compile(pattern)
        except re.error as e:
            raise ValueError(
                f"Некорректное регулярное выражение в '{field_name}': {pattern!r} ({e})"
            ) from e


def load_settings(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        settings = json.load(f)

    for key in ("endpoint1", "endpoint2"):
        if not settings.get(key):
            raise ValueError(f"В settings отсутствует обязательное поле '{key}'")

    settings.setdefault("white_list", [])
    settings.setdefault("black_list", [])
    settings.setdefault("timeout", DEFAULT_TIMEOUT)

    _validate_patterns(settings["white_list"], "white_list")
    _validate_patterns(settings["black_list"], "black_list")

    return settings


# --------------------------------------------------------------------------- #
# Лог
# --------------------------------------------------------------------------- #

_UNSAFE_LOG_DATETIME_RE = re.compile(r"[^A-Za-z0-9_.-]")


def sanitize_log_datetime(value: str) -> str:
    """
    Приводит произвольную строку метки времени (например, вывод `date`) к
    виду, безопасному для использования в имени файла: убирает пробелы,
    `/`, `:` и прочие символы, которые могли бы превратить имя лога в путь
    (`../`) или сломаться в имени файла.
    """
    return _UNSAFE_LOG_DATETIME_RE.sub("_", value.strip())


def write_log(report: str, log_dir: Path = Path("log"), run_datetime: Optional[str] = None) -> Path:
    """
    Без `run_datetime`: каждый вызов создаёт новый файл с уникальной меткой
    времени (текущее поведение при одиночном запуске).

    С `run_datetime`: все вызовы одной серии (например, под `watch`,
    запущенные с одной и той же зафиксированной меткой времени) пишутся в
    один и тот же файл `log/run_<run_datetime>.log`, каждый запуск —
    отдельным блоком с собственным временем внутри файла.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    now = dt.now()

    if run_datetime:
        run_id = sanitize_log_datetime(run_datetime)
        log_path = log_dir / f"run_{run_id}.log"
        block = f"===== {now.strftime('%Y-%m-%d %H:%M:%S.%f')} =====\n{report}\n\n"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(block)
    else:
        run_id = now.strftime("%Y-%m-%d_%Hh%Mm%S-%f")
        log_path = log_dir / f"metrics_diff_{run_id}.log"
        log_path.write_text(report + "\n", encoding="utf-8")

    return log_path


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #

def parse_args(argv=None) -> argparse.Namespace:
    script = Path(__file__)
    default_settings = script.with_name(f"{script.stem}_conf.json")
    parser = argparse.ArgumentParser(
        description="Однократное сравнение Prometheus-метрик двух endpoint'ов."
    )
    parser.add_argument(
        "--settings", type=Path, default=default_settings,
        help=f"путь к JSON с настройками (по умолчанию: {default_settings.name})",
    )
    parser.add_argument(
        "--log-datetime", type=str, default=None,
        help=(
            "метка времени начала серии запусков (зафиксированная один раз, "
            "например перед `watch`); если задана — все запуски серии "
            "дописываются в один log/run_<метка>.log вместо файла на каждый "
            "запуск"
        ),
    )
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

    m1, m2, errors = asyncio.run(
        fetch_both(settings["endpoint1"], settings["endpoint2"], settings["timeout"])
    )
    result = compare_metrics(m1, m2, settings["white_list"], settings["black_list"])
    report = format_report(result, errors)

    print(report)
    log_path = write_log(report, run_datetime=args.log_datetime)
    print(f"[log] {log_path}", file=sys.stderr)

    return 1 if result.diffs else 0


if __name__ == "__main__":
    sys.exit(main())
