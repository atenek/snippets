#!/usr/bin/env python3
"""
Скрипт опроса Prometheus метрик с заданного IP и сохранения в CSV.

Опрашивает http://<IP>:2345/metrics каждые 300 мс.
Формирует CSV-файл metrics.csv:
  - Первый столбец: timestamp в формате "%Y-%m-%d %H:%M:%S.%f".
  - Остальные столбцы: все уникальные метрики, встреченные хотя бы в одном ответе.
  - Если метрика отсутствовала в каком-то опросе, значение - "None".
При выходе (Ctrl-C, Ctrl-D или SIGTERM) данные сохраняются.
"""


import csv
import datetime
import re
import signal
import sys
import threading
import time
import urllib.request
from datetime import datetime as dt


RUN_ID = f"{dt.now().strftime('%Y-%m-%d_%Hh%Mm%S-%f')}"
IP = "127.0.0.1"
URL = f"http://{IP}:9191/metrics"
CSV_FILENAME = f"data/metrics_{RUN_ID}.csv"
INTERVAL = 0.5                # 500 мс


all_metrics = set()           # все уникальные ключи метрик
data = []                     # список словарей для строк CSV
running = True                # флаг выполнения

def signal_handler(sig, frame):
    """Обработчик сигналов (Ctrl-C, SIGTERM)."""
    global running
    print("\nЗавершение работы...", file=sys.stderr)
    running = False

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def stdin_listener():
    """Отслеживает EOF в stdin (Ctrl-D)."""
    global running
    try:
        while running:
            line = sys.stdin.readline()
            if not line:      # EOF
                running = False
                break
    except EOFError:
        running = False

# Запускаем слушатель stdin в фоновом потоке
threading.Thread(target=stdin_listener, daemon=True).start()

def parse_metrics(text: str) -> dict:
    """
    Парсит текстовое представление Prometheus метрик.
    Возвращает словарь {metric_name{labels}: value_str}.
    """
    metrics = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        # Парсим имя, опциональные метки и значение
        m = re.match(
            r'^(?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)'
            r'(?:\{(?P<labels>[^}]*)\})?'
            r'\s+'
            r'(?P<value>NaN|[+-]?Inf|[0-9.eE+-]+)',
            line
        )
        if not m:
            continue
        name = m.group('name')
        labels_str = m.group('labels')
        value = m.group('value')

        if labels_str:
            # Извлекаем пары label="value" и сортируем для стабильного ключа
            pairs = re.findall(r'(\w+)="((?:[^"\\]|\\.)*)"', labels_str)
            pairs.sort(key=lambda x: x[0])
            label_parts = [f'{k}="{v}"' for k, v in pairs]
            key = f"{name}{{{','.join(label_parts)}}}"
        else:
            key = name
        metrics[key] = value
    return metrics

try:
    while running:
        start_time = time.perf_counter()
        now = datetime.datetime.now()
        timestamp_str = now.strftime("%Y-%m-%d %H:%M:%S.%f")

        # Попытка получить метрики
        try:
            with urllib.request.urlopen(URL, timeout=1) as resp:
                resp_text = resp.read().decode('utf-8')
        except Exception as e:
            print(f"Ошибка запроса: {e}", file=sys.stderr)
            elapsed = time.perf_counter() - start_time
            time.sleep(max(0, INTERVAL - elapsed))
            continue

        current_metrics = parse_metrics(resp_text)

        # Обновляем глобальный набор всех встречавшихся метрик
        all_metrics.update(current_metrics.keys())

        # Формируем строку данных
        row = {'timestamp': timestamp_str}
        for m in all_metrics:
            row[m] = current_metrics.get(m, 'None')

        data.append(row)

        # Выдерживаем интервал
        elapsed = time.perf_counter() - start_time
        time.sleep(max(0, INTERVAL - elapsed))

except KeyboardInterrupt:
    # Дублирующая обработка на случай, если signal не перехватился
    pass

finally:
    # Сохранение CSV
    if data:
        columns = ['timestamp'] + sorted(all_metrics)
        with open(CSV_FILENAME, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=columns, restval='None')
            writer.writeheader()
            writer.writerows(data)
        print(f"Данные сохранены в {CSV_FILENAME}", file=sys.stderr)
    else:
        print("Нет данных для сохранения.", file=sys.stderr)
