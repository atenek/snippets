"""
MultiPort HTTP Client - Load Balancer traffic tester

Sends HTTP requests to configured endpoints at specified TPS rates.
Each request uses a new TCP session bound to the configured source IP/port.
Records client-side and server-side session data to a CSV file.
"""

import argparse
import csv
import errno as _errno
import http.client
import json
import logging
import os
import random
import signal
import socket
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Tuple

# ── Dirs / Run ID ─────────────────────────────────────────────────────────────

RUNS_CLIENT_DIR = './runs/client'
os.makedirs(RUNS_CLIENT_DIR, exist_ok=True)

_start_time = datetime.now()
RUN_ID = f"{_start_time.strftime('%Y-%m-%d_%H-%M-%S')}.{f'{_start_time.microsecond}'[:3]:03}"

# ── Logging ───────────────────────────────────────────────────────────────────

_log_path = os.path.join(RUNS_CLIENT_DIR, f"run_{RUN_ID}.log")
_fmt = logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s")
_fh = logging.FileHandler(_log_path, encoding='utf-8')
_fh.setFormatter(_fmt)
_ch = logging.StreamHandler(sys.stdout)
_ch.setFormatter(_fmt)
log = logging.getLogger('cli')
log.setLevel(logging.DEBUG)
log.addHandler(_fh)
log.addHandler(_ch)


# ── Config ────────────────────────────────────────────────────────────────────

@dataclass
class EndpointConfig:
    src_ip: str
    src_port_min: int
    src_port_max: int       # equals src_port_min when a single port is configured
    dst_ip: str
    dst_port: int
    path: str
    tps: float
    method: str = 'GET'
    timeout: Optional[float] = None     # per-endpoint override; falls back to --timeout

    def pick_src_port(self) -> int:
        if self.src_port_min == self.src_port_max:
            return self.src_port_min
        return random.randint(self.src_port_min, self.src_port_max)

    @property
    def label(self) -> str:
        return f"{self.src_ip}->{self.dst_ip}:{self.dst_port}{self.path}"


def _parse_src_port(value) -> Tuple[int, int]:
    """
    '1024..4096' -> (1024, 4096)
    '8080'       -> (8080, 8080)
    8080         -> (8080, 8080)
    """
    s = str(value).strip()
    if '..' in s:
        lo, hi = s.split('..', 1)
        return int(lo), int(hi)
    v = int(s)
    return v, v


def load_config(path: str) -> List[EndpointConfig]:
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    configs: List[EndpointConfig] = []
    for i, item in enumerate(data):
        try:
            port_min, port_max = _parse_src_port(item['SRC_PORT'])
            configs.append(EndpointConfig(
                src_ip=str(item['SRC_IP']),
                src_port_min=port_min,
                src_port_max=port_max,
                dst_ip=str(item['DST_IP']),
                dst_port=int(item['DST_PORT']),
                path=str(item['path']),
                tps=float(item['tps']),
                method=str(item.get('method', 'GET')).upper(),
                timeout=float(item['timeout']) if 'timeout' in item else None,
            ))
        except (KeyError, ValueError) as e:
            log.error(f"Config item {i} invalid: {e}  item={item}")
            sys.exit(1)
    return configs


# ── CSV Writer ────────────────────────────────────────────────────────────────

CSV_FIELDS = [
    'req_timestamp', 'resp_timestamp', 'timedelta_ms',
    'path',
    'Cl_SRC_IP', 'Cl_SRC_PORT', 'Cl_DST_IP', 'Cl_DST_PORT',
    'RS_SRC_IP', 'RS_SRC_PORT', 'RS_DST_IP', 'RS_DST_PORT',
    'status_code', 'Content-Type', 'Body',
    'conn_event',
]


class CsvWriter:
    def __init__(self, path: str):
        self._lock = threading.Lock()
        self._file = open(path, 'w', newline='', encoding='utf-8')
        self._writer = csv.DictWriter(
            self._file, fieldnames=CSV_FIELDS,
            delimiter=';', extrasaction='ignore',
        )
        self._writer.writeheader()
        self._file.flush()
        log.info(f"CSV output: {path}")

    def write(self, row: dict):
        with self._lock:
            self._writer.writerow(row)
            self._file.flush()

    def close(self):
        with self._lock:
            try:
                self._file.close()
            except Exception:
                pass


# ── TCP socket with source binding ────────────────────────────────────────────

def _connect(src_ip: str, src_port: int,
             dst_ip: str, dst_port: int,
             timeout: float = 10.0) -> socket.socket:
    """Create a new TCP socket bound to (src_ip, src_port) and connect."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, 'SO_REUSEPORT'):
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except OSError:
            pass
    sock.settimeout(timeout)
    sock.bind((src_ip, src_port))
    sock.connect((dst_ip, dst_port))
    return sock


# ── Connection event classification ──────────────────────────────────────────

def _classify_error(exc: Exception) -> str:
    """
    Map a socket/http exception to a short connection-event token:

      REFUSED  — port not listening; kernel replied with RST on SYN
                 (ConnectionRefusedError / ECONNREFUSED)
      TIMEOUT  — no response within the configured timeout
                 (socket.timeout / TimeoutError / ETIMEDOUT)
      RST      — TCP RST received after the connection was established
                 (ConnectionResetError / BrokenPipeError / ECONNRESET / EPIPE)
      FIN      — server closed the connection cleanly (sent FIN) before
                 delivering a complete HTTP response
                 (http.client.RemoteDisconnected)
      ERROR    — any other exception (DNS, routing, etc.)
    """
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return 'TIMEOUT'
    if isinstance(exc, ConnectionRefusedError):
        return 'REFUSED'
    if isinstance(exc, ConnectionResetError):
        return 'RST'
    if isinstance(exc, BrokenPipeError):
        return 'RST'
    if isinstance(exc, http.client.RemoteDisconnected):
        return 'FIN'
    if isinstance(exc, OSError) and exc.errno is not None:
        if exc.errno in (_errno.ECONNREFUSED,):
            return 'REFUSED'
        if exc.errno in (_errno.ECONNRESET, _errno.EPIPE):
            return 'RST'
        if exc.errno in (_errno.ETIMEDOUT,):
            return 'TIMEOUT'
    return 'ERROR'


# ── Single HTTP transaction ───────────────────────────────────────────────────

def _do_request(cfg: EndpointConfig) -> dict:
    """
    Perform one HTTP request over a freshly bound TCP session.
    Returns a dict with all CSV_FIELDS populated as available.
    """
    src_port = cfg.pick_src_port()
    req_ts = datetime.now()

    t = cfg.timeout
    row: dict = {
        'req_timestamp': req_ts.isoformat(timespec='milliseconds'),
        'path': cfg.path,
        'Cl_SRC_IP': cfg.src_ip,
        'Cl_SRC_PORT': src_port,
        'Cl_DST_IP': cfg.dst_ip,
        'Cl_DST_PORT': cfg.dst_port,
        'RS_SRC_IP': '', 'RS_SRC_PORT': '',
        'RS_DST_IP': '', 'RS_DST_PORT': '',
        'resp_timestamp': '', 'timedelta_ms': '',
        'status_code': '', 'Content-Type': '', 'Body': '',
        'conn_event': '',
    }

    try:
        sock = _connect(cfg.src_ip, src_port, cfg.dst_ip, cfg.dst_port, t)
        # Inject the pre-connected socket into HTTPConnection so it skips its
        # own connect() and does NOT reuse the connection (Connection: close).
        conn = http.client.HTTPConnection(cfg.dst_ip, cfg.dst_port, timeout=t)
        conn.sock = sock

        conn.request(cfg.method, cfg.path, headers={'Connection': 'close'})
        resp = conn.getresponse()
        resp_ts = datetime.now()
        body_bytes = resp.read()
        conn.close()

        timedelta_ms = (resp_ts - req_ts).total_seconds() * 1000
        content_type = resp.getheader('Content-Type', '')
        body_str = body_bytes.decode('utf-8', errors='replace').strip()

        row.update({
            'resp_timestamp': resp_ts.isoformat(timespec='milliseconds'),
            'timedelta_ms': f"{timedelta_ms:.3f}",
            'status_code': resp.status,
            'Content-Type': content_type,
            'Body': body_str,
        })

        # Extract RS session data from application/json response.
        # Server format: {"body": {"src_ip":..., "src_port":..., "dst_ip":..., "dst_port":...}}
        if 'application/json' in content_type and body_str:
            try:
                parsed = json.loads(body_str)
                body_obj = parsed.get('body', parsed) if isinstance(parsed, dict) else None
                if isinstance(body_obj, dict):
                    row['RS_SRC_IP'] = str(body_obj.get('src_ip', ''))
                    row['RS_SRC_PORT'] = str(body_obj.get('src_port', ''))
                    row['RS_DST_IP'] = str(body_obj.get('dst_ip', ''))
                    row['RS_DST_PORT'] = str(body_obj.get('dst_port', ''))
            except (json.JSONDecodeError, AttributeError):
                pass

    except Exception as exc:
        resp_ts = datetime.now()
        timedelta_ms = (resp_ts - req_ts).total_seconds() * 1000
        event = _classify_error(exc)
        row.update({
            'resp_timestamp': resp_ts.isoformat(timespec='milliseconds'),
            'timedelta_ms': f"{timedelta_ms:.3f}",
            'status_code': 'ERROR',
            'Body': str(exc),
            'conn_event': event,
        })
        log.warning(f"[{cfg.label}] src_port={src_port}  {event}: {exc}")

    return row


# ── Per-endpoint worker thread ────────────────────────────────────────────────

class EndpointWorker:
    """
    Runs in its own thread, sending requests to one endpoint at the
    configured TPS rate. Requests are sequential (one at a time) so
    that each new TCP session is fully closed before the next starts.
    When the request takes longer than 1/tps the next tick is skipped
    forward to avoid unbounded backlog.
    """

    def __init__(self, cfg: EndpointConfig, writer: CsvWriter,
                 stop: threading.Event):
        self._cfg = cfg
        self._writer = writer
        self._stop = stop
        self._interval = 1.0 / cfg.tps
        self._thread = threading.Thread(
            target=self._run, daemon=True,
            name=f"ep-{cfg.dst_port}{cfg.path}",
        )

    def start(self):
        self._thread.start()

    def join(self, timeout: Optional[float] = None):
        self._thread.join(timeout=timeout)

    def _run(self):
        log.info(
            f"Worker start  {self._cfg.label}  "
            f"tps={self._cfg.tps}  src_port="
            f"{'%d..%d' % (self._cfg.src_port_min, self._cfg.src_port_max) if self._cfg.src_port_min != self._cfg.src_port_max else self._cfg.src_port_min}"
        )
        next_tick = time.monotonic()
        while not self._stop.is_set():
            now = time.monotonic()
            wait = next_tick - now
            if wait > 0:
                self._stop.wait(timeout=wait)
                if self._stop.is_set():
                    break

            # Advance tick; skip over missed ticks if we fell behind
            next_tick += self._interval
            lag = time.monotonic() - next_tick
            if lag > 0:
                skipped = int(lag / self._interval) + 1
                next_tick += skipped * self._interval

            row = _do_request(self._cfg)
            self._writer.write(row)

        log.info(f"Worker stop   {self._cfg.label}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description='MultiPort HTTP Client — LB traffic tester',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python http_client_multiport_mgmt.py --config client-config.json
  python http_client_multiport_mgmt.py --config client-config.json --duration 60
  python http_client_multiport_mgmt.py --config client-config.json --output /tmp/out.csv

Config JSON format:
  [
    {
      "SRC_IP":   "192.168.2.15",
      "SRC_PORT": "1024..4096",
      "DST_IP":   "192.168.10.5",
      "DST_PORT": 62224,
      "path":     "/health",
      "tps":      12,
      "timeout":  5.0
    }
  ]

conn_event values (written to CSV on error):
  REFUSED  port not listening — RST received on SYN
  TIMEOUT  no response within timeout
  RST      TCP RST received after connection established
  FIN      server closed connection (FIN) before full HTTP response
  ERROR    other exception (routing, DNS, etc.)
""",
    )
    parser.add_argument(
        '--config', '-c', required=True,
        help='Path to JSON config file with endpoint list',
    )
    parser.add_argument(
        '--output', '-o', default=None,
        help=f'CSV output file (default: {RUNS_CLIENT_DIR}/client_run_<RUN_ID>.csv)',
    )
    parser.add_argument(
        '--duration', '-d', type=float, default=None,
        help='Run for this many seconds then stop (default: run until Ctrl+C)',
    )
    parser.add_argument(
        '--timeout', '-t', type=float, default=10.0,
        help='Per-request socket timeout in seconds (default: 10)',
    )
    parser.add_argument(
        '--verbose', '-v', action='store_true',
        help='Debug-level logging',
    )
    return parser.parse_args()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()

    if not args.verbose:
        log.setLevel(logging.INFO)
        _fh.setLevel(logging.DEBUG)     # always keep full detail in log file
        _ch.setLevel(logging.INFO)

    log.info(f"MultiPort HTTP Client  run={RUN_ID}")
    log.info(f"Log: {_log_path}")

    configs = load_config(args.config)
    for cfg in configs:
        if cfg.timeout is None:
            cfg.timeout = args.timeout
    log.info(f"Loaded {len(configs)} endpoint(s) from {args.config}")

    csv_path = args.output or os.path.join(RUNS_CLIENT_DIR, f"client_run_{RUN_ID}.csv")
    writer = CsvWriter(csv_path)

    stop_event = threading.Event()

    def _shutdown(sig=None, frame=None):
        log.info("Shutdown requested...")
        stop_event.set()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    workers = [
        EndpointWorker(cfg, writer, stop_event)
        for cfg in configs
    ]
    for w in workers:
        w.start()

    if args.duration is not None:
        log.info(f"Running for {args.duration}s ...")
        stop_event.wait(timeout=args.duration)
        stop_event.set()
    else:
        log.info("Running (Ctrl+C to stop) ...")
        stop_event.wait()

    for w in workers:
        w.join(timeout=5.0)

    writer.close()
    log.info(f"Done. CSV saved: {csv_path}")


if __name__ == '__main__':
    main()
