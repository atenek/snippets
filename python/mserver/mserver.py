"""
    MultiPortHTTPServer - управляемый сервер с rule-based архитектурой
    TCP/UDP сервисы: http, tcp_echo, tcp_logger, udp_echo, udp_logger
"""
import http.server
import socketserver
import socket
import json
import mimetypes
import html
import signal
import threading
import urllib.parse
import argparse
import os
import glob
import logging
import ssl
import struct
from abc import ABC
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from datetime import datetime
import time
import sys

start_time = datetime.now()
RUN_ID = f"{start_time.strftime('%Y-%m-%d_%H-%M-%S')}.{start_time.microsecond:03d}"

HOSTNAME = socket.gethostname()
MGMT_PORT = 62032
RULESETS_DIR = './rulesets'
CERTS_DIR = './certs'
STARTUP_CONFIG_PATH = './startup-config.json'
LOGS_DIR = './logs'
RUNS_SERVER_DIR = './runs/server'

os.makedirs(RUNS_SERVER_DIR, exist_ok=True)
_log_path = os.path.join(RUNS_SERVER_DIR, f"run_{RUN_ID}.log")
_fmt = logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s")
_fh  = logging.FileHandler(_log_path, encoding='utf-8')
_fh.setFormatter(_fmt)
_ch  = logging.StreamHandler(sys.stdout)
_ch.setFormatter(_fmt)
log = logging.getLogger('srv')
log.setLevel(logging.DEBUG)
log.addHandler(_fh)
log.addHandler(_ch)
log.info(f"Log: {_log_path}")


try:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("3.4.5.6", 80))
    IP = s.getsockname()[0]
    s.close()
except Exception:
    IP = '0.0.0.0'


# ── Data Model ────────────────────────────────────────────────────────────────

@dataclass
class Rule:
    method: str
    path: str
    # regular response fields (used when service_type is None)
    response_code: int = 0
    response_body: Any = None
    response_headers: Dict[str, str] = field(default_factory=dict)
    # static_serve / static_list fields
    service_type: Optional[str] = None   # "static_serve" | "static_list"
    files_dir: Optional[str] = None
    # rate limit is OFF by default; applied only when explicitly requested
    # via "?rate=" (or, optionally, default_rate_kb set in the ruleset).
    default_rate_kb: Optional[int] = None   # None → no default limit
    max_rate_kb: Optional[int] = None       # None → no upper cap


@dataclass
class Ruleset:
    name: str
    rules: List[Rule]

    def match(self, method: str, path: str) -> Optional[Rule]:
        for rule in self.rules:
            method_ok = rule.method == '*' or rule.method == method
            path_ok = (
                rule.path == '*' or
                rule.path == path or
                (rule.path.endswith('/*') and path.startswith(rule.path[:-1]))
            )
            if method_ok and path_ok:
                return rule
        return None


class RulesetRegistry:
    def __init__(self):
        self._rulesets: Dict[str, Ruleset] = {}

    def load_from_dir(self, path: str):
        for filepath in sorted(glob.glob(os.path.join(path, '*.json'))):

            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                # Support both a single ruleset dict and an array of rulesets
                entries = data if isinstance(data, list) else [data]
                for entry in entries:
                    name = entry['name']
                    rules = []
                    for r in entry['rules']:
                        resp = r['response']
                        if 'service' in resp:
                            rules.append(Rule(
                                method=r['method'],
                                path=r['path'],
                                service_type=resp['service'],
                                files_dir=resp.get('files_dir', './static'),
                                default_rate_kb=(int(resp['default_rate_kb'])
                                                 if 'default_rate_kb' in resp else None),
                                max_rate_kb=(int(resp['max_rate_kb'])
                                             if 'max_rate_kb' in resp else None),
                            ))
                        else:
                            headers = dict(resp.get('headers', {}))
                            if 'Content-Type' in resp:
                                headers['Content-Type'] = resp['Content-Type']
                            rules.append(Rule(
                                method=r['method'],
                                path=r['path'],
                                response_code=resp['code'],
                                response_body=resp['body'],
                                response_headers=headers,
                            ))
                    self._rulesets[name] = Ruleset(name=name, rules=rules)
                    log.info(f"Loaded ruleset '{name}' ({len(rules)} rules) from {filepath}")
            except Exception as e:
                log.warning(f"Could not load ruleset {filepath}: {e}")

    def get(self, name: str) -> Optional[Ruleset]:
        return self._rulesets.get(name)

    def list_names(self) -> List[str]:
        return list(self._rulesets.keys())


@dataclass
class ServiceConfig:
    protocol: str
    port: int
    mode: Optional[str]
    ruleset: Optional[str] = None
    hosts: Optional[List[Dict[str, str]]] = None


@dataclass
class TlsHost:
    """Резолвленная запись hosts: сертификат + опц. ruleset для одного SNI."""
    sni: str
    crt_path: str
    key_path: str
    ruleset: Optional[Ruleset] = None


# ── Service base class ────────────────────────────────────────────────────────

class PortService(ABC):
    _error: Optional[str] = None
    def start(self): pass
    def stop(self): pass
    def is_running(self) -> bool: return False
    def get_log_file(self) -> Optional[str]: return None
    def get_error(self) -> Optional[str]: return self._error


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_run_id() -> str:
    return datetime.now().strftime('%Y%m%d_%H%M%S')


def _substitute_session_vars(obj: Any, src_ip: str, src_port: str,
                              dst_ip: str, dst_port: str) -> Any:
    """Recursively replace $VAR / ${VAR} placeholders with real session values."""
    if isinstance(obj, str):
        return (obj
                .replace('${SRC_IP}', src_ip).replace('$SRC_IP', src_ip)
                .replace('${SRC_PORT}', src_port).replace('$SRC_PORT', src_port)
                .replace('${DST_IP}', dst_ip).replace('$DST_IP', dst_ip)
                .replace('${DST_PORT}', dst_port).replace('$DST_PORT', dst_port))
    if isinstance(obj, dict):
        return {k: _substitute_session_vars(v, src_ip, src_port, dst_ip, dst_port)
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [_substitute_session_vars(v, src_ip, src_port, dst_ip, dst_port)
                for v in obj]
    return obj


def _make_log_path(logs_dir: str, proto: str, port: int, run_id: str) -> str:
    return os.path.join(logs_dir, f"{proto}_{port}_{run_id}.log")


def _resolve_cert_path(path: str, certs_dir: str) -> str:
    """Абсолютный путь оставляем как есть, относительный — от certs_dir."""
    if os.path.isabs(path):
        return path
    return os.path.join(certs_dir, path)


def _build_tls_contexts(tls_hosts: List['TlsHost']) -> Dict[str, ssl.SSLContext]:
    """Строит SSLContext с загруженным сертификатом для каждой записи hosts.
    Вызывается и при первом запуске (_run), и при hot-swap (HTTPService.hot_swap);
    может кинуть ssl.SSLError/OSError на нечитаемой/несовместимой паре crt/key —
    вызывающий обязан вызвать это ДО мутации состояния живого сервиса."""
    contexts: Dict[str, ssl.SSLContext] = {}
    for h in tls_hosts:
        hctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        hctx.load_cert_chain(certfile=h.crt_path, keyfile=h.key_path)
        hctx.mserver_sni = h.sni
        contexts[h.sni] = hctx
    return contexts


def _select_tls_host(server_name: Optional[str], hosts: List['TlsHost']) -> 'TlsHost':
    """Первая запись, где sni == '*' или sni == server_name; иначе последняя (default)."""
    for h in hosts:
        if h.sni == '*' or h.sni == server_name:
            return h
    return hosts[-1]


def _resolve_tls_hosts(hosts: List[dict], certs_dir: str,
                       registry: RulesetRegistry) -> List['TlsHost']:
    """Строит TlsHost из сырых записей config.hosts (пути crt/key — от certs_dir,
    per-host ruleset — по имени из registry). Если ruleset указан, но не найден —
    бросает RuntimeError (не трактует молча как «нет override») — тот же класс
    бага, что уже был найден для ruleset порта, только для hosts[].ruleset."""
    result = []
    for h in hosts:
        host_ruleset = None
        if h.get('ruleset'):
            host_ruleset = registry.get(h['ruleset'])
            if host_ruleset is None:
                raise RuntimeError(f"host ruleset '{h['ruleset']}' (sni={h.get('sni')}) not found")
        result.append(TlsHost(
            sni=h['sni'],
            crt_path=_resolve_cert_path(h['crt'], certs_dir),
            key_path=_resolve_cert_path(h['key'], certs_dir),
            ruleset=host_ruleset,
        ))
    return result


# Upper bound for the "?delay=" query parameter, in milliseconds.
DELAY_MAX_MS = 60000


def _parse_delay_ms(params: Dict[str, list]) -> int:
    """Extract a non-negative response delay (ms) from query params.

    Honours "?delay=<ms>" on any request; value is clamped to [0, DELAY_MAX_MS].
    Invalid/absent values yield 0 (no delay).
    """
    if 'delay' not in params:
        return 0
    try:
        delay_ms = int(params['delay'][0])
    except (ValueError, IndexError):
        return 0
    if delay_ms < 0:
        return 0
    return min(delay_ms, DELAY_MAX_MS)


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True
    timeout = 1.0


# ── BandwidthLimiter ──────────────────────────────────────────────────────────

class BandwidthLimiter:
    """Per-connection token-bucket rate limiter (synchronous, thread-safe)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._connections: Dict[str, dict] = {}
        self._counter = 0

    def register(self, client_ip: str, rate_kb: int) -> str:
        with self._lock:
            self._counter += 1
            conn_id = f"conn_{self._counter}_{int(time.time())}"
            self._connections[conn_id] = {
                'ip': client_ip,
                'rate': rate_kb * 1024,
                'bytes_sent': 0,
                'last_check': time.time(),
            }
            return conn_id

    def unregister(self, conn_id: str):
        with self._lock:
            self._connections.pop(conn_id, None)

    def throttle(self, conn_id: str, chunk_size: int):
        wait = 0.0
        with self._lock:
            conn = self._connections.get(conn_id)
            if conn is None:
                return
            now = time.time()
            elapsed = now - conn['last_check']
            allowed = conn['rate'] * elapsed
            conn['bytes_sent'] += chunk_size
            conn['last_check'] = now
            if conn['bytes_sent'] > allowed:
                excess = conn['bytes_sent'] - allowed
                wait = min(excess / conn['rate'], 1.0)
                conn['bytes_sent'] = 0
                conn['last_check'] = time.time()
        if wait > 0.01:
            time.sleep(wait)


_bandwidth_limiter = BandwidthLimiter()


# ── RST fault injection ───────────────────────────────────────────────────────
#
# Каждую RST_EVERY_N-ю https-сессию закрываем «дефектно»: клиент штатно получает
# ответ, после чего сокет аварийно сбрасывается. Воспроизводит паттерн из дампа
# tcp_stream7: сервер отдаёт ответ → FIN (активное закрытие) → RST на
# запоздавший close_notify клиента.
#
# Механизм: на выбранной сессии в finish() (после flush ответа) взводим
# SO_LINGER{onoff=1, linger=0} и сами закрываем сокет — abortive close, при
# котором ядро шлёт RST вместо FIN. TLS-close (unwrap/close_notify) не делаем.
# Так RST формируется ядром, как в реальном дефекте tcp_stream7.
#
# RST_EVERY_N <= 0 (по умолчанию) полностью отключает инъекцию.
RST_EVERY_N = int(os.environ.get('MSERVER_RST_EVERY_N', '0'))
# Пауза между flush ответа и abortive-close: клиент успевает прочитать ответ
# до RST. Достаточно единиц миллисекунд на loopback; 50 мс — с запасом.
RST_DELIVERY_GRACE = 0.05
_rst_session_counter = 0
_rst_counter_lock = threading.Lock()


def _should_inject_rst() -> bool:
    """True для каждой RST_EVERY_N-й https-сессии (потокобезопасный счётчик)."""
    if RST_EVERY_N <= 0:
        return False
    global _rst_session_counter
    with _rst_counter_lock:
        _rst_session_counter += 1
        return _rst_session_counter % RST_EVERY_N == 0


# ── HTTPService ───────────────────────────────────────────────────────────────

def _make_http_handler_class():
    class RulesetHTTPHandler(http.server.BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            log.debug(f"[HTTP:{self.server.server_address[1]}] {format % args}")

        def setup(self):
            # Решение принимаем один раз на TCP-сессию (setup вызывается на
            # соединение, а не на запрос). Считаем только https-сессии.
            super().setup()
            self._inject_rst = False
            if isinstance(self.connection, ssl.SSLSocket) and _should_inject_rst():
                self._inject_rst = True
                log.debug(f"[HTTP:{self.server.server_address[1]}] RST-inject armed "
                          f"for {self.client_address[0]}:{self.client_address[1]}")

        def finish(self):
            # Сначала штатно сбрасываем буфер ответа (flush wfile) — клиент
            # гарантированно получает ответ ДО аварийного закрытия.
            try:
                super().finish()
            finally:
                if getattr(self, '_inject_rst', False):
                    self._arm_rst_close()
                    log.info(f"[https:{self.server.server_address[1]}] session "
                             f"{self.client_address[0]}:{self.client_address[1]} "
                             f"closed with RST")

        def _arm_rst_close(self):
            """Аварийно закрыть соединение — послать RST вместо FIN.

            SO_LINGER{onoff=1, linger=0} превращает close() в abortive release:
            ядро отбрасывает содержимое send-буфера и шлёт клиенту RST. TLS-close
            (unwrap/close_notify) намеренно не делаем. Воспроизводится дефект
            tcp_stream7: клиент видит ответ 200, затем обрыв соединения.

            Закрываем здесь, а не полагаемся на socketserver.shutdown_request:
            штатный путь сначала делает shutdown(SHUT_WR) → FIN, что нейтрализует
            linger (после FIN close() уже не пошлёт RST). Наш close() с linger=0
            отрабатывает первым; повторный close() из shutdown_request идемпотентен.

            Короткая пауза перед close() даёт клиенту вытянуть ответ из своего
            приёмного буфера ДО прихода RST (иначе abortive-close на loopback
            обгоняет доставку и клиент теряет ответ). Задержка заодно моделирует
            «запоздалость» close_notify из реального дампа."""
            try:
                self.connection.setsockopt(
                    socket.SOL_SOCKET, socket.SO_LINGER,
                    struct.pack('ii', 1, 0))
                time.sleep(RST_DELIVERY_GRACE)
                self.connection.close()
            except OSError as e:
                log.debug(f"RST-close failed: {e}")

        def _handle(self):
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length > 0:
                self.rfile.read(content_length)

            parsed = urllib.parse.urlparse(self.path)

            # "?delay=<ms>" applies to every request on this server, regardless
            # of the matched rule type (regular response, static_serve, ...).
            params = urllib.parse.parse_qs(parsed.query)
            delay_ms = _parse_delay_ms(params)
            if delay_ms > 0:
                time.sleep(delay_ms / 1000.0)

            # Читаем актуальный ruleset с сервера на каждый запрос — это
            # позволяет горячо подменять его без пересоздания сокета.
            # Для https с per-host ruleset выбираем ruleset по SNI соединения.
            ruleset = self.server.ruleset
            host_rulesets = getattr(self.server, 'host_rulesets', None)
            if host_rulesets:
                ctx = getattr(self.connection, 'context', None)
                sni = getattr(ctx, 'mserver_sni', None)
                if sni in host_rulesets:
                    ruleset = host_rulesets[sni]
            rule = ruleset.match(self.command, parsed.path)
            if rule is None:
                body = b"Not Found"
                self.send_response(404)
                self.send_header('Content-Type', 'text/plain')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if rule.service_type == 'static_serve':
                self._handle_static_serve(rule, parsed.path, parsed.query)
                return
            if rule.service_type == 'static_list':
                self._handle_static_list(rule)
                return

            src_ip, src_port = self.client_address
            dst_ip, dst_port = self.server.server_address
            headers = dict(rule.response_headers)

            if isinstance(rule.response_body, dict):
                substituted = _substitute_session_vars(
                    rule.response_body, str(src_ip), str(src_port),
                    str(dst_ip), str(dst_port)
                )
                body_bytes = json.dumps({"body": substituted}).encode('utf-8')
                headers.setdefault('Content-Type', 'application/json')
            else:
                body_str = _substitute_session_vars(
                    str(rule.response_body), str(src_ip), str(src_port),
                    str(dst_ip), str(dst_port)
                )
                body_bytes = body_str.encode('utf-8')
                headers.setdefault('Content-Type', 'text/plain')

            self.send_response(rule.response_code)
            for k, v in headers.items():
                self.send_header(k, v)
            self.send_header('Content-Length', str(len(body_bytes)))
            self.end_headers()
            self.wfile.write(body_bytes)

        def _handle_static_serve(self, rule: Rule, request_path: str, query: str):
            # derive files prefix from rule.path: "/download/*" → "/download/"
            prefix = rule.path[:-1]  # strip trailing '*'
            filename = request_path[len(prefix):]
            if not filename:
                # directory root → standard HTML autoindex of the folder
                self._handle_dir_index(rule, prefix)
                return

            files_dir = rule.files_dir or './static'
            safe_name = os.path.basename(filename)  # prevent path traversal
            filepath = os.path.join(files_dir, safe_name)

            if not os.path.isfile(filepath):
                body = f"File not found: {safe_name}".encode('utf-8')
                self.send_response(404)
                self.send_header('Content-Type', 'text/plain; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            # Rate limit is OFF unless explicitly requested. Priority:
            #   1. "?rate=<KB/s>" query parameter
            #   2. rule.default_rate_kb (only if set in the ruleset)
            #   3. otherwise unlimited (rate_kb = None)
            rate_kb: Optional[int] = rule.default_rate_kb
            params = urllib.parse.parse_qs(query)
            if 'rate' in params:
                try:
                    rate_kb = int(params['rate'][0])
                except (ValueError, IndexError):
                    pass
            if rate_kb is not None:
                if rule.max_rate_kb is not None:
                    rate_kb = min(rate_kb, rule.max_rate_kb)
                if rate_kb <= 0:
                    rate_kb = None  # 0/negative → treat as unlimited

            file_size = os.path.getsize(filepath)
            content_type, _ = mimetypes.guess_type(filepath)
            if content_type is None:
                content_type = 'application/octet-stream'

            client_ip = self.client_address[0]
            conn_id = (_bandwidth_limiter.register(client_ip, rate_kb)
                       if rate_kb is not None else None)
            try:
                self.send_response(200)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(file_size))
                self.send_header('Content-Disposition',
                                 f'attachment; filename="{safe_name}"')
                self.send_header('X-Rate-Limit',
                                 f'{rate_kb} KB/s' if rate_kb is not None
                                 else 'unlimited')
                self.end_headers()
                chunk_size = 8192
                with open(filepath, 'rb') as f:
                    while True:
                        chunk = f.read(chunk_size)
                        if not chunk:
                            break
                        if conn_id is not None:
                            _bandwidth_limiter.throttle(conn_id, len(chunk))
                        self.wfile.write(chunk)
            finally:
                if conn_id is not None:
                    _bandwidth_limiter.unregister(conn_id)

        def _handle_dir_index(self, rule: Rule, prefix: str):
            """Standard HTML directory listing for the static_serve root."""
            files_dir = rule.files_dir or './static'
            if not os.path.isdir(files_dir):
                body = (f"Directory not found: {files_dir}").encode('utf-8')
                self.send_response(404)
                self.send_header('Content-Type', 'text/plain; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            entries = []
            for fname in sorted(os.listdir(files_dir)):
                fpath = os.path.join(files_dir, fname)
                if not os.path.isfile(fpath):
                    continue
                href = urllib.parse.quote(prefix + fname)
                size = os.path.getsize(fpath)
                entries.append(
                    f'    <li><a href="{href}">{html.escape(fname)}</a>'
                    f' <span class="size">({size} bytes)</span></li>'
                )
            listing = "\n".join(entries) if entries else "    <li><em>empty</em></li>"
            title = html.escape(f"Index of {prefix}")
            page = (
                "<!DOCTYPE html>\n"
                "<html><head><meta charset=\"utf-8\">\n"
                f"<title>{title}</title></head>\n"
                "<body>\n"
                f"<h1>{title}</h1>\n"
                "<ul>\n"
                f"{listing}\n"
                "</ul>\n"
                "</body></html>\n"
            )
            body = page.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _handle_static_list(self, rule: Rule):
            files_dir = rule.files_dir or './static'
            if not os.path.isdir(files_dir):
                data: dict = {"files": [], "count": 0,
                              "error": f"Directory not found: {files_dir}"}
            else:
                files = []
                for fname in sorted(os.listdir(files_dir)):
                    fpath = os.path.join(files_dir, fname)
                    if os.path.isfile(fpath):
                        stat = os.stat(fpath)
                        ct, _ = mimetypes.guess_type(fpath)
                        files.append({
                            "name": fname,
                            "size": stat.st_size,
                            "type": ct or "application/octet-stream",
                            "modified": datetime.fromtimestamp(
                                stat.st_mtime).isoformat(),
                        })
                data = {"files": files, "count": len(files)}
            body = json.dumps(data, indent=2).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self): self._handle()
        def do_POST(self): self._handle()
        def do_PUT(self): self._handle()
        def do_DELETE(self): self._handle()
        def do_PATCH(self): self._handle()
        def do_HEAD(self): self._handle()
        def do_OPTIONS(self): self._handle()

    return RulesetHTTPHandler


class HTTPService(PortService):
    def __init__(self, port: int, ip: str, ruleset: Ruleset,
                 tls_hosts: Optional[List['TlsHost']] = None):
        self.port = port
        self.ip = ip
        self.ruleset = ruleset
        self.tls_hosts = tls_hosts
        self.host_rulesets: Dict[str, Ruleset] = {
            h.sni: h.ruleset for h in (tls_hosts or []) if h.ruleset is not None
        }
        self.contexts: Dict[str, ssl.SSLContext] = {}
        self._server: Optional[ThreadedTCPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._running = False

    def start(self):
        self._stop_event.clear()
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        time.sleep(0.1)

    def hot_swap(self, ruleset: Ruleset, tls_hosts: Optional[List['TlsHost']] = None):
        """Горячая подмена ruleset(-ов) и, для https, TLS hosts/сертификатов —
        без пересоздания слушающего сокета.

        Если tls_hosts не None, новые SSLContext строятся ДО мутации состояния
        (self.contexts/self.tls_hosts не трогаются, пока load_cert_chain не
        отработает успешно) — упавшая загрузка сертификата не оставляет сервис
        в частично применённом виде. Присваивание ссылок атомарно под GIL;
        _sni_callback и обработчик читают self.contexts/self.tls_hosts/
        self.ruleset/self.host_rulesets на каждый handshake/запрос, поэтому
        новые значения вступают в силу со следующего запроса/соединения, а уже
        открытые соединения и сам слушающий сокет не затрагиваются.
        """
        new_contexts = _build_tls_contexts(tls_hosts) if tls_hosts is not None else None

        self.ruleset = ruleset
        if tls_hosts is not None:
            self.tls_hosts = tls_hosts
            self.contexts = new_contexts
            self.host_rulesets = {h.sni: h.ruleset for h in tls_hosts if h.ruleset is not None}
        else:
            self.host_rulesets = {}
        if self._server is not None:
            self._server.ruleset = ruleset
            self._server.host_rulesets = self.host_rulesets

        msg = f"HTTPService port {self.port}: hot-swapped ruleset -> {ruleset.name}"
        if tls_hosts is not None:
            msg += f", tls hosts -> {[h.sni for h in tls_hosts]}"
        log.info(msg)

    def _sni_callback(self, sslsocket, server_name, _default_ctx):
        sslsocket.context = self.contexts[_select_tls_host(server_name, self.tls_hosts).sni]

    def _run(self):
        try:
            handler_class = _make_http_handler_class()
            self._server = ThreadedTCPServer((self.ip, self.port), handler_class)
            self._server.ruleset = self.ruleset
            self._server.host_rulesets = self.host_rulesets
            if self.tls_hosts:
                # Один SSLContext на запись hosts; слушающий сокет оборачиваем
                # контекстом ПОСЛЕДНЕЙ записи (default), на него вешаем
                # sni_callback (bound method, читает self.contexts/self.tls_hosts
                # на момент вызова — это и позволяет hot_swap() менять сертификаты
                # без пересоздания сокета). Контекст помечаем mserver_sni —
                # обработчик по нему выбирает per-host ruleset.
                self.contexts = _build_tls_contexts(self.tls_hosts)
                default_ctx = self.contexts[self.tls_hosts[-1].sni]
                default_ctx.sni_callback = self._sni_callback
                self._server.socket = default_ctx.wrap_socket(self._server.socket,
                                                              server_side=True)
            scheme = 'https' if self.tls_hosts else 'http'
            log.info(f"HTTPService started: {scheme}://{self.ip}:{self.port} ruleset={self.ruleset.name}")
            while not self._stop_event.is_set():
                self._server.handle_request()
        except Exception as e:
            self._error = str(e)
            if not self._stop_event.is_set():
                log.error(f"HTTPService error on port {self.port}: {e}")
        finally:
            if self._server:
                try:
                    self._server.server_close()
                except Exception:
                    pass
                self._server = None
            self._running = False

    def stop(self):
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)

    def is_running(self) -> bool:
        return self._running


# ── TCPEchoService ────────────────────────────────────────────────────────────

class TCPEchoService(PortService):
    def __init__(self, port: int, ip: str):
        self.port = port
        self.ip = ip
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def start(self):
        self._stop_event.clear()
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        time.sleep(0.1)

    def _run(self):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
                srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                srv.bind((self.ip, self.port))
                srv.listen(50)
                srv.settimeout(1.0)
                log.info(f"TCPEchoService started on port {self.port}")
                while not self._stop_event.is_set():
                    try:
                        conn, addr = srv.accept()
                        t = threading.Thread(target=self._handle_conn, args=(conn,), daemon=True)
                        t.start()
                    except socket.timeout:
                        continue
        except Exception as e:
            self._error = str(e)
            if not self._stop_event.is_set():
                log.error(f"TCPEchoService error on port {self.port}: {e}")
        finally:
            self._running = False

    def _handle_conn(self, conn: socket.socket):
        with conn:
            while True:
                try:
                    data = conn.recv(4096)
                    if not data:
                        break
                    conn.sendall(data)
                except Exception:
                    break

    def stop(self):
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)

    def is_running(self) -> bool:
        return self._running


# ── TCPLoggerService ──────────────────────────────────────────────────────────

class TCPLoggerService(PortService):
    def __init__(self, port: int, ip: str, logs_dir: str):
        self.port = port
        self.ip = ip
        self.logs_dir = logs_dir
        self.run_id = _make_run_id()
        self._log_file = _make_log_path(logs_dir, 'tcp', port, self.run_id)
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def start(self):
        self._stop_event.clear()
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        time.sleep(0.1)

    def _run(self):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
                srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                srv.bind((self.ip, self.port))
                srv.listen(50)
                srv.settimeout(1.0)
                log.info(f"TCPLoggerService started on port {self.port}, log={self._log_file}")
                while not self._stop_event.is_set():
                    try:
                        conn, addr = srv.accept()
                        t = threading.Thread(target=self._handle_conn, args=(conn, addr), daemon=True)
                        t.start()
                    except socket.timeout:
                        continue
        except Exception as e:
            self._error = str(e)
            if not self._stop_event.is_set():
                log.error(f"TCPLoggerService error on port {self.port}: {e}")
        finally:
            self._running = False

    def _handle_conn(self, conn: socket.socket, addr):
        src = f"{addr[0]}:{addr[1]}"
        ts_connect = datetime.now().isoformat(timespec='seconds')
        with open(self._log_file, 'ab') as f:
            f.write(f"=== CONNECT {ts_connect} src={src} ===\n".encode())
            with conn:
                while True:
                    try:
                        data = conn.recv(4096)
                        if not data:
                            break
                        f.write(data)
                        f.flush()
                    except Exception:
                        break
            ts_disconnect = datetime.now().isoformat(timespec='seconds')
            f.write(f"\n=== DISCONNECT {ts_disconnect} ===\n".encode())

    def stop(self):
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)

    def is_running(self) -> bool:
        return self._running

    def get_log_file(self) -> Optional[str]:
        return self._log_file


# ── UDPEchoService ────────────────────────────────────────────────────────────

class UDPEchoService(PortService):
    def __init__(self, port: int, ip: str):
        self.port = port
        self.ip = ip
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def start(self):
        self._stop_event.clear()
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        time.sleep(0.1)

    def _run(self):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind((self.ip, self.port))
                sock.settimeout(1.0)
                log.info(f"UDPEchoService started on port {self.port}")
                while not self._stop_event.is_set():
                    try:
                        data, addr = sock.recvfrom(65535)
                        sock.sendto(data, addr)
                    except socket.timeout:
                        continue
        except Exception as e:
            self._error = str(e)
            if not self._stop_event.is_set():
                log.error(f"UDPEchoService error on port {self.port}: {e}")
        finally:
            self._running = False

    def stop(self):
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)

    def is_running(self) -> bool:
        return self._running


# ── UDPLoggerService ──────────────────────────────────────────────────────────

class UDPLoggerService(PortService):
    def __init__(self, port: int, ip: str, logs_dir: str):
        self.port = port
        self.ip = ip
        self.logs_dir = logs_dir
        self.run_id = _make_run_id()
        self._log_file = _make_log_path(logs_dir, 'udp', port, self.run_id)
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def start(self):
        self._stop_event.clear()
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        time.sleep(0.1)

    def _run(self):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind((self.ip, self.port))
                sock.settimeout(1.0)
                log.info(f"UDPLoggerService started on port {self.port}, log={self._log_file}")
                with open(self._log_file, 'a', encoding='utf-8') as log_f:
                    while not self._stop_event.is_set():
                        try:
                            data, addr = sock.recvfrom(65535)
                            ts = datetime.now().isoformat(timespec='seconds')
                            src = f"{addr[0]}:{addr[1]}"
                            log_f.write(f"{ts} src={src} len={len(data)} data={data.hex()}\n")
                            log_f.flush()
                        except socket.timeout:
                            continue
        except Exception as e:
            self._error = str(e)
            if not self._stop_event.is_set():
                log.error(f"UDPLoggerService error on port {self.port}: {e}")
        finally:
            self._running = False

    def stop(self):
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)

    def is_running(self) -> bool:
        return self._running

    def get_log_file(self) -> Optional[str]:
        return self._log_file


# ── ManagedPort ───────────────────────────────────────────────────────────────

class ManagedPort:
    def __init__(self, protocol: str, port: int, ip: str, logs_dir: str,
                 certs_dir: str = CERTS_DIR):
        self.protocol = protocol
        self.port = port
        self.ip = ip
        self.logs_dir = logs_dir
        self.certs_dir = certs_dir
        self.config: Optional[ServiceConfig] = None
        self.service: Optional[PortService] = None
        self.lock = threading.RLock()

    def assign(self, config: ServiceConfig, registry: RulesetRegistry):
        with self.lock:
            # Мягкое изменение: тот же mode, порт уже слушает — горячая подмена
            # ruleset(-ов) и, для https, TLS hosts/сертификатов, без пересоздания
            # сокета. Пересоздание нужно только при смене mode (см. dev_task_003).
            if (config.mode in ('http', 'https')
                    and isinstance(self.service, HTTPService)
                    and self.service.is_running()
                    and self.config is not None
                    and self.config.mode == config.mode):
                port_ruleset = registry.get(config.ruleset)
                if port_ruleset is None:
                    raise RuntimeError(f"port {self.port}: ruleset '{config.ruleset}' not found")
                tls_hosts = (_resolve_tls_hosts(config.hosts, self.certs_dir, registry)
                            if config.mode == 'https' else None)
                self.service.hot_swap(port_ruleset, tls_hosts)
                self.config = config
                return

            if self.service and self.service.is_running():
                self.service.stop()
            self.service = None
            self.config = config

            if config.mode is None:
                return

            if config.mode == 'http':
                ruleset = registry.get(config.ruleset)
                if ruleset is None:
                    raise RuntimeError(f"port {self.port}: ruleset '{config.ruleset}' not found")
                self.service = HTTPService(self.port, self.ip, ruleset)
            elif config.mode == 'https':
                ruleset = registry.get(config.ruleset)
                if ruleset is None:
                    raise RuntimeError(f"port {self.port}: ruleset '{config.ruleset}' not found")
                tls_hosts = _resolve_tls_hosts(config.hosts, self.certs_dir, registry)
                self.service = HTTPService(self.port, self.ip, ruleset,
                                           tls_hosts=tls_hosts)
            elif config.mode == 'tcp_echo':
                self.service = TCPEchoService(self.port, self.ip)
            elif config.mode == 'tcp_logger':
                self.service = TCPLoggerService(self.port, self.ip, self.logs_dir)
            elif config.mode == 'udp_echo':
                self.service = UDPEchoService(self.port, self.ip)
            elif config.mode == 'udp_logger':
                self.service = UDPLoggerService(self.port, self.ip, self.logs_dir)

            if self.service:
                self.service.start()
                if not self.service.is_running():
                    err = self.service.get_error() or "service failed to start"
                    self.service = None
                    raise RuntimeError(f"port {self.port}: {err}")

    def stop(self):
        with self.lock:
            if self.service:
                self.service.stop()
                self.service = None

    def is_listening(self) -> bool:
        return self.service is not None and self.service.is_running()

    def get_status_dict(self) -> dict:
        if self.config is None or self.config.mode is None:
            return {"listening": False, "mode": None}
        result: dict = {"listening": self.is_listening(), "mode": self.config.mode}
        if self.config.mode in ('http', 'https') and self.config.ruleset:
            result["ruleset"] = self.config.ruleset
        if self.config.mode == 'https':
            result["hosts"] = self.config.hosts
        log_file = self.service.get_log_file() if self.service else None
        if log_file:
            result["log_file"] = log_file
        return result


# ── Global ServerRunner ref ───────────────────────────────────────────────────

_global_server_runner = None


def get_server_runner() -> Optional['ServerRunner']:
    return _global_server_runner


# ── Validation constants ──────────────────────────────────────────────────────

VALID_SERVICE_MODES: Dict[str, set] = {
    'tcp': {'http', 'https', 'tcp_echo', 'tcp_logger'},
    'udp': {'udp_echo', 'udp_logger'},
}


# ── Общая валидация/применение конфигурации сервисов ───────────────────────────
# Используется и POST /mgmt, и загрузкой startup-config (POST /config/load и
# старт сервера) — единая схема словаря {"tcp:PORT": {...}|null, ...}.

class ConfigValidationError(Exception):
    """Словарь целиком не прошёл валидацию. errors: {service_key: {"error":.., "details":..}}."""
    def __init__(self, errors: Dict[str, dict]):
        super().__init__("service configuration validation failed")
        self.errors = errors


def _validate_services_config(data: Any, runner: 'ServerRunner') -> Dict[str, 'ServiceConfig']:
    """Валидирует весь словарь целиком, собирая ВСЕ ошибки (не только первую).
    При любой ошибке — ConfigValidationError, ничего не возвращается частично.
    Ключи с префиксом "_" (например "_comment") пропускаются молча.
    Возвращает {service_key: ServiceConfig} только для валидных записей."""
    if not isinstance(data, dict):
        raise ConfigValidationError({
            "_": {"error": "Request body must be a JSON object", "details": ""}
        })

    errors: Dict[str, dict] = {}
    configs: Dict[str, ServiceConfig] = {}

    for key, entry in data.items():
        if key.startswith('_'):
            continue

        parts = key.split(':')
        if len(parts) != 2 or parts[0] not in ('tcp', 'udp') or not parts[1].isdigit():
            errors[key] = {"error": "Invalid service format",
                           "details": "Expected tcp:NNNNN or udp:NNNNN"}
            continue
        proto, port_str = parts[0], parts[1]
        port = int(port_str)

        if port == runner.mgmt_port:
            errors[key] = {"error": "Cannot configure management port", "details": ""}
            continue

        if entry is None:
            configs[key] = ServiceConfig(protocol=proto, port=port, mode=None)
            continue
        if not isinstance(entry, dict):
            errors[key] = {"error": "Service config must be an object or null", "details": ""}
            continue

        mode = entry.get('mode')
        if mode is not None:
            allowed = VALID_SERVICE_MODES.get(proto, set())
            if mode not in allowed:
                errors[key] = {"error": "Invalid mode for protocol",
                               "details": f"Mode '{mode}' not valid for {proto}"}
                continue

            if mode in ('http', 'https'):
                ruleset_name = entry.get('ruleset')
                if not ruleset_name:
                    errors[key] = {"error": f"Ruleset required for {mode} mode", "details": ""}
                    continue
                if runner.registry.get(ruleset_name) is None:
                    errors[key] = {"error": "Ruleset not found",
                                   "details": f"Ruleset '{ruleset_name}' is not loaded"}
                    continue

            if mode == 'https':
                hosts = entry.get('hosts')
                if not isinstance(hosts, list) or not hosts:
                    errors[key] = {"error": "hosts (non-empty list) required for https mode",
                                   "details": ""}
                    continue
                host_error = False
                for h in hosts:
                    if not isinstance(h, dict):
                        errors[key] = {"error": "hosts entry must be an object", "details": ""}
                        host_error = True
                        break
                    sni = h.get('sni')
                    crt = h.get('crt')
                    key_path_raw = h.get('key')
                    if not sni or not isinstance(sni, str):
                        errors[key] = {"error": "sni required in hosts entry", "details": ""}
                        host_error = True
                        break
                    if not crt or not key_path_raw:
                        errors[key] = {"error": "crt and key required in hosts entry",
                                       "details": f"sni={sni}"}
                        host_error = True
                        break
                    crt_path = _resolve_cert_path(crt, runner.certs_dir)
                    key_path = _resolve_cert_path(key_path_raw, runner.certs_dir)
                    if not os.path.isfile(crt_path):
                        errors[key] = {"error": "Certificate file not found", "details": crt_path}
                        host_error = True
                        break
                    if not os.path.isfile(key_path):
                        errors[key] = {"error": "Key file not found", "details": key_path}
                        host_error = True
                        break
                    host_ruleset = h.get('ruleset')
                    if host_ruleset is not None and runner.registry.get(host_ruleset) is None:
                        errors[key] = {"error": "Ruleset not found",
                                       "details": f"Ruleset '{host_ruleset}' is not loaded"}
                        host_error = True
                        break
                    try:
                        ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER).load_cert_chain(
                            certfile=crt_path, keyfile=key_path)
                    except ssl.SSLError as e:
                        errors[key] = {"error": "Invalid certificate/key pair",
                                       "details": f"sni={sni}: {e}"}
                        host_error = True
                        break
                if host_error:
                    continue

        configs[key] = ServiceConfig(protocol=proto, port=port, mode=mode,
                                     ruleset=entry.get('ruleset'), hosts=entry.get('hosts'))

    if errors:
        raise ConfigValidationError(errors)
    return configs


def _apply_services_config(configs: Dict[str, 'ServiceConfig'],
                           runner: 'ServerRunner') -> Dict[str, dict]:
    """Применяет уже провалидированные конфиги через runner.assign_service.
    Ошибки на этапе применения (напр. порт занят) — не фатальны для всего
    набора, попадают в results[key] как {"status": "error", ...}."""
    results: Dict[str, dict] = {}
    for service_key, config in configs.items():
        try:
            runner.assign_service(service_key, config)
            mp = runner.managed_ports[service_key]
            if config.mode is None:
                results[service_key] = {"status": "stopped"}
            else:
                entry: dict = {"status": "applied", "mode": config.mode}
                if config.mode in ('http', 'https'):
                    entry["ruleset"] = config.ruleset
                log_file = mp.service.get_log_file() if mp.service else None
                if log_file:
                    entry["log_file"] = log_file
                results[service_key] = entry
        except Exception as e:
            results[service_key] = {"status": "error", "error": str(e)}
    return results


# ── HTTP Management Handler ───────────────────────────────────────────────────

class CustomHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        log.debug(f"[MGMT] [{self.address_string()}] {format % args}")

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path

        if path == '/favicon.ico':
            self.send_response(204)
            self.end_headers()
            return
        if path == '/status':
            self.handle_status()
            return
        if path == '/rulesets':
            self.handle_rulesets()
            return

        self.send_error_response(404, "Not found")

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path

        if path == '/mgmt':
            self.handle_management_post()
            return
        if path == '/config/save':
            self.handle_config_save()
            return
        if path == '/config/load':
            self.handle_config_load()
            return

        self.send_error_response(404, "Not found")

    # ── GET /status ────────────────────────────────────────────────────────────

    def handle_status(self):
        runner = get_server_runner()
        if runner is None:
            self.send_error_response(503, "Server runner not available")
            return

        services = {key: mp.get_status_dict() for key, mp in runner.managed_ports.items()}
        self.send_json_response({
            "server": {"name": HOSTNAME, "ip": IP},
            "rulesets_loaded": runner.registry.list_names(),
            "services": services
        })

    # ── GET /rulesets ──────────────────────────────────────────────────────────

    def handle_rulesets(self):
        runner = get_server_runner()
        if runner is None:
            self.send_error_response(503, "Server runner not available")
            return

        rulesets_list = [
            {"name": name, "rules_count": len(runner.registry.get(name).rules)}
            for name in runner.registry.list_names()
        ]
        self.send_json_response({"rulesets": rulesets_list})

    # ── POST /mgmt ─────────────────────────────────────────────────────────────

    def handle_management_post(self):
        runner = get_server_runner()
        if runner is None:
            self.send_error_response(503, "Server runner not available")
            return

        body = self._read_body()
        if body is None:
            return

        try:
            data = json.loads(body.decode('utf-8'))
        except json.JSONDecodeError:
            self._send_validation_error("Invalid JSON in request body", {})
            return

        try:
            configs = _validate_services_config(data, runner)
        except ConfigValidationError as e:
            self._send_validation_error("Validation failed", e.errors)
            return

        results = _apply_services_config(configs, runner)
        self.send_json_response({"status": "success", "results": results})

    def _send_validation_error(self, message: str, errors: dict):
        body = (json.dumps({"status": "error", "message": message, "errors": errors}) + "\n").encode()
        self.send_response(400)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # ── POST /config/save ──────────────────────────────────────────────────────

    def handle_config_save(self):
        runner = get_server_runner()
        if runner is None:
            self.send_error_response(503, "Server runner not available")
            return
        try:
            runner.save_config(runner.startup_config_path)
            self.send_json_response({"status": "success",
                                     "message": f"Saved to {runner.startup_config_path}"})
        except Exception as e:
            self.send_error_response(500, f"Failed to save: {e}")

    # ── POST /config/load ──────────────────────────────────────────────────────

    def handle_config_load(self):
        runner = get_server_runner()
        if runner is None:
            self.send_error_response(503, "Server runner not available")
            return
        try:
            results = runner.load_config(runner.startup_config_path)
            self.send_json_response({"status": "success",
                                     "message": f"Loaded from {runner.startup_config_path}",
                                     "results": results})
        except FileNotFoundError:
            self.send_error_response(404, "startup-config.json not found")
        except ConfigValidationError as e:
            self._send_validation_error("Validation failed", e.errors)
        except Exception as e:
            self.send_error_response(500, f"Failed to load: {e}")

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _read_body(self) -> Optional[bytes]:
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                self.send_error_response(400, "Missing request body")
                return None
            return self.rfile.read(content_length)
        except Exception as e:
            self.send_error_response(500, f"Error reading request body: {e}")
            return None

    def send_json_response(self, data: Any, status: int = 200):
        body = (json.dumps(data, indent=2) + "\n").encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_error_response(self, code: int, message: str):
        body = (json.dumps({"status": "error", "message": message}) + "\n").encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


# ── ServerRunner ──────────────────────────────────────────────────────────────

class ServerRunner:
    def __init__(self, ip: str, rulesets_dir: str, startup_config_path: str,
                 logs_dir: str, mgmt_port: int, certs_dir: str = CERTS_DIR):
        self.ip = ip
        self.rulesets_dir = rulesets_dir
        self.startup_config_path = startup_config_path
        self.logs_dir = logs_dir
        self.mgmt_port = mgmt_port
        self.certs_dir = certs_dir

        self.registry = RulesetRegistry()
        self.managed_ports: Dict[str, ManagedPort] = {}
        self.shutdown_event = threading.Event()
        self.lock = threading.RLock()

    def assign_service(self, service_key: str, config: ServiceConfig):
        with self.lock:
            if service_key not in self.managed_ports:
                proto, port_str = service_key.split(':')
                self.managed_ports[service_key] = ManagedPort(
                    proto, int(port_str), self.ip, self.logs_dir, self.certs_dir
                )
            mp = self.managed_ports[service_key]
        mp.assign(config, self.registry)

    def save_config(self, path: str):
        data: dict = {}
        for key, mp in self.managed_ports.items():
            if mp.config is None or mp.config.mode is None:
                data[key] = None
            else:
                entry: dict = {"mode": mp.config.mode}
                if mp.config.ruleset:
                    entry["ruleset"] = mp.config.ruleset
                if mp.config.hosts:
                    entry["hosts"] = mp.config.hosts
                data[key] = entry
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        log.info(f"Config saved to {path}")

    def load_config(self, path: str) -> Dict[str, dict]:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        configs = _validate_services_config(data, self)  # ConfigValidationError пробрасывается
        results = _apply_services_config(configs, self)
        for key, result in results.items():
            if result.get('status') == 'error':
                log.error(f"Failed to apply service {key}: {result.get('error')}")
        log.info(f"Config loaded from {path}")
        return results

    def _run_mgmt_server(self):
        try:
            mgmt_server = ThreadedTCPServer((self.ip, self.mgmt_port), CustomHandler)
            mgmt_server.timeout = 1.0
            log.info(f"Management server started: http://{self.ip}:{self.mgmt_port}")
            while not self.shutdown_event.is_set():
                mgmt_server.handle_request()
            mgmt_server.server_close()
        except Exception as e:
            log.error(f"Management server error: {e}")

    def shutdown_all(self):
        if self.shutdown_event.is_set():
            return
        log.info("Shutting down all services...")
        self.shutdown_event.set()
        for mp in self.managed_ports.values():
            mp.stop()
        log.info("All services stopped")

    def start(self):
        global _global_server_runner
        _global_server_runner = self

        os.makedirs(self.logs_dir, exist_ok=True)

        if os.path.isdir(self.rulesets_dir):
            self.registry.load_from_dir(self.rulesets_dir)
        else:
            log.warning(f"Rulesets dir '{self.rulesets_dir}' not found")

        if os.path.isfile(self.startup_config_path):
            try:
                self.load_config(self.startup_config_path)
            except ConfigValidationError as e:
                log.error(f"Startup config '{self.startup_config_path}' failed validation, "
                         f"starting with no services configured: {e.errors}")
            except Exception as e:
                log.error(f"Failed to load startup config '{self.startup_config_path}', "
                         f"starting with no services configured: {e}")
        else:
            log.info(f"No startup-config at '{self.startup_config_path}'")

        mgmt_thread = threading.Thread(target=self._run_mgmt_server, daemon=True)
        mgmt_thread.start()

        def signal_handler(sig, frame):
            log.info(f"Received signal {sig}")
            self.shutdown_all()
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        log.info(f"Ready. Management: http://{self.ip}:{self.mgmt_port}")
        try:
            while not self.shutdown_event.is_set():
                self.shutdown_event.wait(1)
        except KeyboardInterrupt:
            self.shutdown_all()


def parse_args():
    parser = argparse.ArgumentParser(
        description='HTTP сервер с управлением портами (rule-based)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  python mserver.py
  python mserver.py --mgmt-port 62005
  python mserver.py --ip 127.0.0.1 --rulesets-dir ./my_rules
  python mserver.py --rst-every-n 3   # RST каждой 3-й https-сессии
"""
    )
    parser.add_argument('--ip', type=str, default=None,
                        help='IP адрес (по умолчанию: автоопределение)')
    parser.add_argument('--mgmt-port', type=int, default=MGMT_PORT,
                        help=f'Порт управления (по умолчанию: {MGMT_PORT})')
    parser.add_argument('--rulesets-dir', type=str, default=RULESETS_DIR,
                        help=f'Директория с rulesets (по умолчанию: {RULESETS_DIR})')
    parser.add_argument('--certs-dir', type=str, default=CERTS_DIR,
                        help=f'Директория с TLS-сертификатами (по умолчанию: {CERTS_DIR})')
    parser.add_argument('--startup-config', type=str, default=STARTUP_CONFIG_PATH,
                        help=f'Путь к startup-config (по умолчанию: {STARTUP_CONFIG_PATH})')
    parser.add_argument('--logs-dir', type=str, default=LOGS_DIR,
                        help=f'Директория для лог-файлов (по умолчанию: {LOGS_DIR})')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Подробный вывод')
    parser.add_argument('--rst-every-n', type=int, default=RST_EVERY_N,
                        help=f'RST-инъекция: закрывать аварийно каждую N-ю '
                             f'https-сессию (0 — выключить; по умолчанию: {RST_EVERY_N})')
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()

    if args.ip:
        IP = args.ip

    MGMT_PORT = args.mgmt_port
    RST_EVERY_N = args.rst_every_n

    log.info("MultiPortHTTPServer")
    log.info(f"  Management : http://{IP}:{MGMT_PORT}")
    if RST_EVERY_N > 0:
        log.info(f"  RST-inject : every {RST_EVERY_N} https session(s)")
    log.info(f"  Rulesets   : {args.rulesets_dir}")
    log.info(f"  Config     : {args.startup_config}")
    log.info(f"  Logs       : {args.logs_dir}")

    if args.verbose:
        log.debug(f"  IP: {IP}")

    runner = ServerRunner(
        ip=IP,
        rulesets_dir=args.rulesets_dir,
        startup_config_path=args.startup_config,
        logs_dir=args.logs_dir,
        mgmt_port=MGMT_PORT,
        certs_dir=args.certs_dir
    )
    runner.start()
