#!/usr/bin/env python3
"""
TCP session load generator с измерением RTT установления соединения.

Использование:
    python3 tcp_load.py --host 10.0.0.1 --port 80 --rate 1000 --duration 60

Параметры:
    --host        IP/хост цели
    --port        порт цели
    --rate        сколько новых сессий открывать в секунду (CPS)
    --duration    сколько секунд длится тест
    --hold        сколько секунд держать каждую сессию открытой (0 = закрыть сразу)
    --send-data   отправлять ли простой HTTP GET после коннекта
    --timeout     таймаут установления соединения, сек
    --csv         путь к CSV-файлу для сохранения RTT по каждой сессии (опционально)
"""

import argparse
import asyncio
import time
import csv as csv_module
import sys


class Stats:
    def __init__(self):
        self.attempted = 0
        self.connected = 0
        self.failed = 0
        self.active = 0
        self.max_active = 0
        self.rtts = []          # список RTT (в мс) успешных соединений
        self.errors = {}        # тип ошибки -> количество

    def add_error(self, err_type):
        self.errors[err_type] = self.errors.get(err_type, 0) + 1

    def report_line(self):
        avg_rtt = sum(self.rtts) / len(self.rtts) if self.rtts else 0
        print(
            f"\r[{time.strftime('%H:%M:%S')}] "
            f"attempted={self.attempted} connected={self.connected} "
            f"failed={self.failed} active={self.active} "
            f"max_active={self.max_active} avg_rtt={avg_rtt:.1f}ms",
            end="", flush=True
        )


def percentile(data, p):
    if not data:
        return 0
    data = sorted(data)
    k = (len(data) - 1) * (p / 100)
    f = int(k)
    c = min(f + 1, len(data) - 1)
    if f == c:
        return data[f]
    return data[f] + (data[c] - data[f]) * (k - f)


async def open_session(host, port, hold_time, send_data, timeout, stats, csv_writer):
    stats.attempted += 1
    start = time.perf_counter()

    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout
        )
    except asyncio.TimeoutError:
        stats.failed += 1
        stats.add_error("timeout")
        return
    except ConnectionRefusedError:
        stats.failed += 1
        stats.add_error("connection_refused")
        return
    except OSError as e:
        stats.failed += 1
        stats.add_error(f"os_error:{e.errno}")
        return
    except Exception as e:
        stats.failed += 1
        stats.add_error(type(e).__name__)
        return

    rtt_ms = (time.perf_counter() - start) * 1000
    stats.connected += 1
    stats.active += 1
    stats.max_active = max(stats.max_active, stats.active)
    stats.rtts.append(rtt_ms)

    if csv_writer:
        csv_writer.writerow([time.time(), rtt_ms])

    try:
        if send_data:
            req = f"GET / HTTP/1.0\r\nHost: {host}\r\n\r\n".encode()
            writer.write(req)
            await writer.drain()

        if hold_time > 0:
            await asyncio.sleep(hold_time)
        else:
            await asyncio.sleep(0.01)
    except Exception:
        pass
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass
        stats.active -= 1


async def rate_limited_loop(host, port, rate, duration, hold_time, send_data, timeout, stats, csv_writer):
    interval = 1.0 / rate if rate > 0 else 0
    end_time = time.monotonic() + duration
    tasks = []

    while time.monotonic() < end_time:
        task = asyncio.create_task(
            open_session(host, port, hold_time, send_data, timeout, stats, csv_writer)
        )
        tasks.append(task)
        stats.report_line()
        await asyncio.sleep(interval)

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


def print_final_report(stats, duration):
    print("\n\n=== Итоговая статистика ===")
    print(f"Всего попыток:        {stats.attempted}")
    print(f"Успешных подключений: {stats.connected} "
          f"({(stats.connected/stats.attempted*100 if stats.attempted else 0):.1f}%)")
    print(f"Неудачных:            {stats.failed} "
          f"({(stats.failed/stats.attempted*100 if stats.attempted else 0):.1f}%)")
    print(f"Пиковая concurrency:   {stats.max_active}")
    print(f"Средний CPS (факт):   {stats.attempted / duration:.1f}")

    if stats.errors:
        print("\nОшибки по типам:")
        for err, count in sorted(stats.errors.items(), key=lambda x: -x[1]):
            print(f"  {err}: {count}")

    if stats.rtts:
        rtts = stats.rtts
        print("\nRTT установления соединения (мс):")
        print(f"  min:    {min(rtts):.2f}")
        print(f"  avg:    {sum(rtts)/len(rtts):.2f}")
        print(f"  max:    {max(rtts):.2f}")
        print(f"  p50:    {percentile(rtts, 50):.2f}")
        print(f"  p90:    {percentile(rtts, 90):.2f}")
        print(f"  p95:    {percentile(rtts, 95):.2f}")
        print(f"  p99:    {percentile(rtts, 99):.2f}")
    else:
        print("\nНи одного успешного соединения — RTT недоступен.")


def main():
    parser = argparse.ArgumentParser(description="TCP session load generator с RTT статистикой")
    parser.add_argument("--host", required=True, help="Целевой хост/IP")
    parser.add_argument("--port", type=int, required=True, help="Целевой порт")
    parser.add_argument("--rate", type=int, default=1000, help="Сессий в секунду (CPS)")
    parser.add_argument("--duration", type=int, default=30, help="Длительность теста, сек")
    parser.add_argument("--hold", type=float, default=0, help="Сколько держать сессию открытой, сек")
    parser.add_argument("--send-data", action="store_true", help="Отправлять простой HTTP GET после коннекта")
    parser.add_argument("--timeout", type=float, default=3, help="Таймаут установления соединения, сек")
    parser.add_argument("--csv", type=str, default=None, help="Путь к CSV для сохранения RTT по каждой сессии")
    args = parser.parse_args()

    try:
        import resource
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        target = min(100000, hard)
        resource.setrlimit(resource.RLIMIT_NOFILE, (target, hard))
    except Exception:
        pass

    stats = Stats()
    csv_file = None
    csv_writer = None
    if args.csv:
        csv_file = open(args.csv, "w", newline="")
        csv_writer = csv_module.writer(csv_file)
        csv_writer.writerow(["timestamp", "rtt_ms"])

    print(f"Старт теста: {args.host}:{args.port}, rate={args.rate}/сек, "
          f"duration={args.duration}с, hold={args.hold}с, timeout={args.timeout}с")

    try:
        asyncio.run(
            rate_limited_loop(
                args.host, args.port, args.rate, args.duration,
                args.hold, args.send_data, args.timeout, stats, csv_writer
            )
        )
    except KeyboardInterrupt:
        print("\nПрервано пользователем")
    finally:
        if csv_file:
            csv_file.close()

    print_final_report(stats, args.duration)


if __name__ == "__main__":
    main()