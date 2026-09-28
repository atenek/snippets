#!/usr/bin/env python3
"""
lbtest.py — HTTP/1.1-клиент для теста балансировщика.

Открывает и удерживает N одновременных TCP/HTTP-сессий через LB.
Каждая сессия — отдельное TCP-соединение (одна корутина), которое:
  * mode=stream    — качает (большой) файл с ограничением скорости, чтобы
                     соединение жило долго; после окончания файла запрос
                     повторяется в том же соединении (keep-alive);
  * mode=keepalive — шлёт запросы в одном соединении с паузой --interval.
При обрыве сессия переподключается с экспоненциальной задержкой, так что
число активных соединений держится около целевого.

Зависимостей нет (stdlib). Если установлен uvloop — используется он.

Пример:
  python3 lbtest.py --url http://10.0.0.10/big.iso --conns 5000 \
      --ramp 200 --rate 20k --rcvbuf 16384 --duration 3600
"""
import argparse
import asyncio
import collections
import random
import resource
import signal
import socket
import sys
import time
from urllib.parse import urlsplit

IP_BIND_ADDRESS_NO_PORT = getattr(socket, "IP_BIND_ADDRESS_NO_PORT", 24)


# ---------------------------------------------------------------- utils
def parse_size(s: str) -> int:
    s = s.strip().lower()
    mult = {"k": 1024, "m": 1024 ** 2, "g": 1024 ** 3}
    if s and s[-1] in mult:
        return int(float(s[:-1]) * mult[s[-1]])
    return int(s)


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


class Target:
    def __init__(self, url: str):
        u = urlsplit(url)
        if u.scheme != "http":
            sys.exit(f"поддерживается только http://, получено: {url}")
        self.host = u.hostname
        self.port = u.port or 80
        self.path = (u.path or "/") + (f"?{u.query}" if u.query else "")
        self.host_header = u.netloc
        self.ip = socket.gethostbyname(self.host)  # резолвим один раз (IPv4)

    def request(self, ua: str) -> bytes:
        return (
            f"GET {self.path} HTTP/1.1\r\n"
            f"Host: {self.host_header}\r\n"
            f"User-Agent: {ua}\r\n"
            f"Accept: */*\r\n"
            f"Connection: keep-alive\r\n\r\n"
        ).encode()


class Stats:
    def __init__(self):
        self.active = 0          # установленные соединения
        self.connecting = 0      # в процессе connect()
        self.connects = 0        # всего успешных connect
        self.requests = 0
        self.responses = 0
        self.bytes = 0
        self.connect_time = 0.0  # сумма времени установления TCP
        self.errors = collections.Counter()
        self.status = collections.Counter()
        self.backend_active = collections.Counter()  # сессий на бэкенд сейчас
        self.backend_resp = collections.Counter()    # ответов от бэкенда всего


class Throttle:
    """Ограничение скорости чтения одной сессии (байт/с)."""

    def __init__(self, rate: int):
        self.rate = rate
        self.reset()

    def reset(self):
        self.t0 = time.monotonic()
        self.n = 0

    async def consume(self, n: int):
        if self.rate <= 0:
            return
        self.n += n
        delay = self.n / self.rate - (time.monotonic() - self.t0)
        if delay > 0:
            await asyncio.sleep(delay)


# ---------------------------------------------------------------- HTTP
async def read_headers(reader, timeout):
    raw = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout)
    lines = raw.decode("latin-1").split("\r\n")
    code = int(lines[0].split(" ", 2)[1])
    headers = {}
    for line in lines[1:]:
        if line:
            k, _, v = line.partition(":")
            headers[k.strip().lower()] = v.strip()
    return code, headers


async def read_exact_throttled(reader, size, chunk, throttle, stats, timeout):
    while size > 0:
        data = await asyncio.wait_for(reader.read(min(chunk, size)), timeout)
        if not data:
            raise ConnectionResetError("EOF в теле ответа")
        size -= len(data)
        stats.bytes += len(data)
        await throttle.consume(len(data))


async def read_body(reader, headers, chunk, throttle, stats, timeout) -> bool:
    """Читает тело. Возвращает True, если соединение можно переиспользовать."""
    if "content-length" in headers:
        await read_exact_throttled(reader, int(headers["content-length"]),
                                   chunk, throttle, stats, timeout)
        return True
    if "chunked" in headers.get("transfer-encoding", "").lower():
        while True:
            line = await asyncio.wait_for(reader.readuntil(b"\r\n"), timeout)
            size = int(line.split(b";")[0].strip(), 16)
            if size == 0:
                while (await asyncio.wait_for(reader.readuntil(b"\r\n"), timeout)) != b"\r\n":
                    pass  # trailers
                return True
            await read_exact_throttled(reader, size, chunk, throttle, stats, timeout)
            await asyncio.wait_for(reader.readexactly(2), timeout)
    # без длины — тело до закрытия соединения
    while True:
        data = await asyncio.wait_for(reader.read(chunk), timeout)
        if not data:
            return False
        stats.bytes += len(data)
        await throttle.consume(len(data))


# ---------------------------------------------------------------- session
async def open_conn(idx, t: Target, args):
    loop = asyncio.get_running_loop()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setblocking(False)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        if args.rcvbuf:
            # маленький буфер => ограничение скорости реально доходит до сервера
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, args.rcvbuf)
        if args.source_ip:
            src = args.source_ip[idx % len(args.source_ip)]
            try:
                sock.setsockopt(socket.SOL_IP, IP_BIND_ADDRESS_NO_PORT, 1)
            except OSError:
                pass
            sock.bind((src, 0))
        await loop.sock_connect(sock, (t.ip, t.port))
    except BaseException:
        sock.close()
        raise
    return await asyncio.open_connection(sock=sock, limit=256 * 1024)


async def session(idx, targets, args, stats: Stats, stop: asyncio.Event):
    t = targets[idx % len(targets)]
    req = t.request(args.user_agent)
    throttle = Throttle(args.rate)
    backoff = 0.5
    while not stop.is_set():
        writer = None
        backend = None
        try:
            stats.connecting += 1
            t0 = time.monotonic()
            try:
                reader, writer = await asyncio.wait_for(
                    open_conn(idx, t, args), args.connect_timeout)
            finally:
                stats.connecting -= 1
            stats.connect_time += time.monotonic() - t0
            stats.connects += 1
            stats.active += 1
            backoff = 0.5
            try:
                while not stop.is_set():
                    writer.write(req)
                    await writer.drain()
                    stats.requests += 1
                    code, h = await read_headers(reader, args.read_timeout)
                    stats.status[code] += 1

                    b = h.get(args.backend_header, "?")
                    if b != backend:
                        if backend is not None:
                            stats.backend_active[backend] -= 1
                        backend = b
                        stats.backend_active[backend] += 1
                    stats.backend_resp[b] += 1

                    throttle.reset()
                    reusable = await read_body(reader, h, args.chunk, throttle,
                                               stats, args.read_timeout)
                    stats.responses += 1
                    if not reusable or h.get("connection", "").lower() == "close":
                        break  # переподключимся
                    if args.interval > 0:
                        await asyncio.sleep(args.interval * random.uniform(0.8, 1.2))
            finally:
                stats.active -= 1
                if backend is not None:
                    stats.backend_active[backend] -= 1
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            stats.errors[type(e).__name__] += 1
            await asyncio.sleep(backoff * random.uniform(1, 2))
            backoff = min(backoff * 2, 30)
        finally:
            if writer is not None:
                writer.close()


# ---------------------------------------------------------------- report
async def reporter(stats: Stats, args, stop):
    t_start = time.monotonic()
    last_bytes, last_t = 0, t_start
    while not stop.is_set():
        await asyncio.sleep(args.report)
        now = time.monotonic()
        bps = (stats.bytes - last_bytes) / (now - last_t)
        last_bytes, last_t = stats.bytes, now
        avg_ct = stats.connect_time / stats.connects * 1000 if stats.connects else 0
        be = " ".join(f"{k}={v}" for k, v in sorted(stats.backend_active.items()) if v)
        err = " ".join(f"{k}={v}" for k, v in stats.errors.most_common(4))
        print(f"[{now - t_start:7.0f}s] active={stats.active}/{args.conns} "
              f"connecting={stats.connecting} connects={stats.connects} "
              f"avg_connect={avg_ct:.1f}ms resp={stats.responses} "
              f"rx={human(bps)}/s total={human(stats.bytes)} | "
              f"backends: {be or '-'} | errors: {err or '-'}", flush=True)


def final_report(stats: Stats):
    print("\n=== итог ===")
    print(f"успешных connect: {stats.connects}, запросов: {stats.requests}, "
          f"ответов: {stats.responses}, принято: {human(stats.bytes)}")
    print("коды ответов:", dict(stats.status))
    total = sum(stats.backend_resp.values()) or 1
    print("распределение ответов по бэкендам:")
    for k, v in stats.backend_resp.most_common():
        print(f"  {k:30s} {v:8d}  {v / total * 100:5.1f}%")
    print("ошибки:", dict(stats.errors) or "-")


# ---------------------------------------------------------------- main
def raise_nofile(need: int):
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    if soft < hard:
        resource.setrlimit(resource.RLIMIT_NOFILE, (hard, hard))
        soft = hard
    if soft < need:
        print(f"ВНИМАНИЕ: лимит открытых файлов {soft} < {need}. "
              f"Выполните 'ulimit -n {need * 2}'", file=sys.stderr)


async def main(args):
    targets = [Target(u) for u in args.url]
    stats = Stats()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    rep = asyncio.create_task(reporter(stats, args, stop))
    tasks = []
    # плавный набор соединений (не SYN-шторм)
    for i in range(args.conns):
        if stop.is_set():
            break
        tasks.append(asyncio.create_task(session(i, targets, args, stats, stop)))
        await asyncio.sleep(1 / args.ramp)

    if args.duration:
        try:
            await asyncio.wait_for(stop.wait(), args.duration)
        except asyncio.TimeoutError:
            stop.set()
    else:
        await stop.wait()

    for tk in tasks + [rep]:
        tk.cancel()
    await asyncio.gather(*tasks, rep, return_exceptions=True)
    final_report(stats)


def cli():
    p = argparse.ArgumentParser(description="Удержание N HTTP-сессий через LB")
    p.add_argument("--url", action="append", required=True,
                   help="URL (можно несколько раз — сессии распределятся по ним)")
    p.add_argument("--conns", type=int, default=5000, help="число сессий")
    p.add_argument("--ramp", type=float, default=200, help="новых соединений в секунду")
    p.add_argument("--mode", choices=("stream", "keepalive"), default="stream")
    p.add_argument("--rate", default="0",
                   help="лимит скорости чтения на сессию, байт/с (20k, 1m; 0 — без лимита)")
    p.add_argument("--interval", type=float, default=None,
                   help="пауза между запросами в соединении, с (keepalive: по умолч. 5)")
    p.add_argument("--chunk", default="64k", help="размер чтения")
    p.add_argument("--rcvbuf", default="0", help="SO_RCVBUF сокета (напр. 16k)")
    p.add_argument("--source-ip", action="append",
                   help="локальный IP для bind (можно несколько — больше портов)")
    p.add_argument("--backend-header", default="x-backend",
                   help="заголовок ответа, по которому видно реальный сервер")
    p.add_argument("--connect-timeout", type=float, default=10)
    p.add_argument("--read-timeout", type=float, default=60)
    p.add_argument("--duration", type=float, default=0, help="длительность теста, с (0 — до Ctrl+C)")
    p.add_argument("--report", type=float, default=5, help="период отчёта, с")
    p.add_argument("--user-agent", default="lbtest/1.0")
    a = p.parse_args()
    a.rate = parse_size(a.rate)
    a.chunk = parse_size(a.chunk)
    a.rcvbuf = parse_size(a.rcvbuf)
    a.backend_header = a.backend_header.lower()
    if a.interval is None:
        a.interval = 5.0 if a.mode == "keepalive" else 0.0
    return a


if __name__ == "__main__":
    args = cli()
    raise_nofile(args.conns + 256)
    try:
        import uvloop  # type: ignore
        uvloop.install()
    except ImportError:
        pass
    asyncio.run(main(args))
