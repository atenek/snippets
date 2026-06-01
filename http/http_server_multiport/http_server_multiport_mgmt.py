"""
    MultiPortHTTPServer - управляемый сервер с rule-based архитектурой
    TCP/UDP сервисы: http, tcp_echo, tcp_logger, udp_echo, udp_logger
"""
import http.server
import socketserver
import socket
import json
import signal
import threading
import urllib.parse
import argparse
import os
import glob
import logging
from abc import ABC
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from datetime import datetime
import time
import sys

start_time = datetime.now()
RUN_ID = f"{start_time.strftime('%Y-%m-%d_%H-%M-%S')}.{f'{start_time.microsecond}'[:3]:03}"

HOSTNAME = socket.gethostname()
PORT_RANGE = (62224, 62228)
MGMT_PORT = 62228
RULESETS_DIR = './rulesets'
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

if HOSTNAME == "CAB-WSN-0054280":
    IP = '127.0.0.1'
else:
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
    response_code: int
    response_body: Any  # str for hc/text rules, dict for data/json rules
    response_headers: Dict[str, str] = field(default_factory=dict)


@dataclass
class Ruleset:
    name: str
    rules: List[Rule]

    def match(self, method: str, path: str) -> Optional[Rule]:
        for rule in self.rules:
            if (rule.method == '*' or rule.method == method) and \
               (rule.path == '*' or rule.path == path):
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
                        headers = dict(resp.get('headers', {}))
                        # Content-Type may appear at response level (new format)
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


# ── Service base class ────────────────────────────────────────────────────────

class PortService(ABC):
    def start(self): pass
    def stop(self): pass
    def is_running(self) -> bool: return False
    def get_log_file(self) -> Optional[str]: return None


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


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True
    timeout = 1.0


# ── HTTPService ───────────────────────────────────────────────────────────────

def _make_ruleset_handler_class(ruleset: Ruleset):
    class RulesetHTTPHandler(http.server.BaseHTTPRequestHandler):
        _ruleset = ruleset

        def log_message(self, format, *args):
            log.debug(f"[HTTP:{self.server.server_address[1]}] {format % args}")

        def _handle(self):
            # Consume request body to avoid connection issues
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length > 0:
                self.rfile.read(content_length)

            parsed = urllib.parse.urlparse(self.path)
            rule = self.__class__._ruleset.match(self.command, parsed.path)
            if rule is None:
                body = b"Not Found"
                self.send_response(404)
                self.send_header('Content-Type', 'text/plain')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
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

        def do_GET(self): self._handle()
        def do_POST(self): self._handle()
        def do_PUT(self): self._handle()
        def do_DELETE(self): self._handle()
        def do_PATCH(self): self._handle()
        def do_HEAD(self): self._handle()
        def do_OPTIONS(self): self._handle()

    return RulesetHTTPHandler


class HTTPService(PortService):
    def __init__(self, port: int, ip: str, ruleset: Ruleset):
        self.port = port
        self.ip = ip
        self.ruleset = ruleset
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

    def _run(self):
        try:
            handler_class = _make_ruleset_handler_class(self.ruleset)
            self._server = ThreadedTCPServer((self.ip, self.port), handler_class)
            log.info(f"HTTPService started: http://{self.ip}:{self.port} ruleset={self.ruleset.name}")
            while not self._stop_event.is_set():
                self._server.handle_request()
        except Exception as e:
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
    def __init__(self, protocol: str, port: int, ip: str, logs_dir: str):
        self.protocol = protocol
        self.port = port
        self.ip = ip
        self.logs_dir = logs_dir
        self.config: Optional[ServiceConfig] = None
        self.service: Optional[PortService] = None
        self.lock = threading.RLock()

    def assign(self, config: ServiceConfig, registry: RulesetRegistry):
        with self.lock:
            if self.service and self.service.is_running():
                self.service.stop()
            self.service = None
            self.config = config

            if config.mode is None:
                return

            if config.mode == 'http':
                ruleset = registry.get(config.ruleset)
                self.service = HTTPService(self.port, self.ip, ruleset)
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
        if self.config.mode == 'http' and self.config.ruleset:
            result["ruleset"] = self.config.ruleset
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
    'tcp': {'http', 'tcp_echo', 'tcp_logger'},
    'udp': {'udp_echo', 'udp_logger'},
}


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
            requests = json.loads(body.decode('utf-8'))
        except json.JSONDecodeError:
            self._send_validation_error("Invalid JSON in request body", [])
            return

        errors = self._validate_mgmt_requests(requests, runner)
        if errors:
            self._send_validation_error("Validation failed", errors)
            return

        results = []
        for req in requests:
            service_key = req['service']
            mode = req.get('mode')
            proto, port_str = service_key.split(':')
            port = int(port_str)
            config = ServiceConfig(
                protocol=proto, port=port, mode=mode, ruleset=req.get('ruleset')
            )
            try:
                runner.assign_service(service_key, config)
                mp = runner.managed_ports[service_key]

                if mode is None:
                    results.append({"service": service_key, "status": "stopped"})
                else:
                    entry: dict = {"service": service_key, "status": "applied", "mode": mode}
                    if mode == 'http':
                        entry["ruleset"] = req.get('ruleset')
                    log_file = mp.service.get_log_file() if mp.service else None
                    if log_file:
                        entry["log_file"] = log_file
                    results.append(entry)
            except Exception as e:
                results.append({"service": service_key, "status": "error", "error": str(e)})

        self.send_json_response({"status": "success", "results": results})

    def _validate_mgmt_requests(self, requests, runner) -> list:
        errors = []
        if not isinstance(requests, list):
            errors.append({"service": None, "error": "Request body must be a JSON array", "details": ""})
            return errors

        seen: set = set()
        for i, req in enumerate(requests):
            if not isinstance(req, dict):
                errors.append({"service": None, "error": f"Item {i} must be an object", "details": ""})
                continue

            service = req.get('service')
            if not isinstance(service, str):
                errors.append({"service": service, "error": "Service must be a string", "details": ""})
                continue

            parts = service.split(':')
            if len(parts) != 2 or parts[0] not in ('tcp', 'udp') or not parts[1].isdigit():
                errors.append({"service": service, "error": "Invalid service format",
                                "details": "Expected tcp:NNNNN or udp:NNNNN"})
                continue

            proto, port_str = parts[0], parts[1]
            port = int(port_str)

            if not (PORT_RANGE[0] <= port <= PORT_RANGE[1]):
                errors.append({"service": service, "error": "Port not in allowed range",
                                "details": f"Port {port} not in {PORT_RANGE[0]}-{PORT_RANGE[1]}"})
                continue

            if port == MGMT_PORT:
                errors.append({"service": service, "error": "Cannot configure management port", "details": ""})
                continue

            if service in seen:
                errors.append({"service": service, "error": "Duplicate service", "details": ""})
                continue
            seen.add(service)

            mode = req.get('mode')
            if mode is not None:
                allowed = VALID_SERVICE_MODES.get(proto, set())
                if mode not in allowed:
                    errors.append({"service": service, "error": "Invalid mode for protocol",
                                   "details": f"Mode '{mode}' not valid for {proto}"})
                    continue

                if mode == 'http':
                    ruleset_name = req.get('ruleset')
                    if not ruleset_name:
                        errors.append({"service": service, "error": "Ruleset required for http mode",
                                       "details": ""})
                        continue
                    if runner.registry.get(ruleset_name) is None:
                        errors.append({"service": service, "error": "Ruleset not found",
                                       "details": f"Ruleset '{ruleset_name}' is not loaded"})
                        continue

        return errors

    def _send_validation_error(self, message: str, errors: list):
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
            runner.load_config(runner.startup_config_path)
            self.send_json_response({"status": "success",
                                     "message": f"Loaded from {runner.startup_config_path}"})
        except FileNotFoundError:
            self.send_error_response(404, "startup-config.json not found")
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
                 logs_dir: str, port_range: tuple, mgmt_port: int):
        self.ip = ip
        self.rulesets_dir = rulesets_dir
        self.startup_config_path = startup_config_path
        self.logs_dir = logs_dir
        self.port_range = port_range
        self.mgmt_port = mgmt_port

        self.registry = RulesetRegistry()
        self.managed_ports: Dict[str, ManagedPort] = {}
        self.shutdown_event = threading.Event()
        self.lock = threading.RLock()

    def assign_service(self, service_key: str, config: ServiceConfig):
        with self.lock:
            if service_key not in self.managed_ports:
                proto, port_str = service_key.split(':')
                self.managed_ports[service_key] = ManagedPort(
                    proto, int(port_str), self.ip, self.logs_dir
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
                data[key] = entry
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        log.info(f"Config saved to {path}")

    def load_config(self, path: str):
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        for key, entry in data.items():
            proto, port_str = key.split(':')
            port = int(port_str)
            if entry is None:
                config = ServiceConfig(protocol=proto, port=port, mode=None)
            else:
                config = ServiceConfig(
                    protocol=proto,
                    port=port,
                    mode=entry.get('mode'),
                    ruleset=entry.get('ruleset')
                )
            self.assign_service(key, config)
        log.info(f"Config loaded from {path}")

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
            self.load_config(self.startup_config_path)
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
  python http_server_multiport_mgmt.py
  python http_server_multiport_mgmt.py --port-range 62001 62005 --mgmt-port 62005
  python http_server_multiport_mgmt.py --ip 127.0.0.1 --rulesets-dir ./my_rules
"""
    )
    parser.add_argument('--ip', type=str, default=None,
                        help='IP адрес (по умолчанию: автоопределение)')
    parser.add_argument('--port-range', type=int, nargs=2, default=list(PORT_RANGE),
                        metavar=('START', 'END'),
                        help=f'Диапазон управляемых портов (по умолчанию: {PORT_RANGE[0]} {PORT_RANGE[1]})')
    parser.add_argument('--mgmt-port', type=int, default=MGMT_PORT,
                        help=f'Порт управления (по умолчанию: {MGMT_PORT})')
    parser.add_argument('--rulesets-dir', type=str, default=RULESETS_DIR,
                        help=f'Директория с rulesets (по умолчанию: {RULESETS_DIR})')
    parser.add_argument('--startup-config', type=str, default=STARTUP_CONFIG_PATH,
                        help=f'Путь к startup-config (по умолчанию: {STARTUP_CONFIG_PATH})')
    parser.add_argument('--logs-dir', type=str, default=LOGS_DIR,
                        help=f'Директория для лог-файлов (по умолчанию: {LOGS_DIR})')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Подробный вывод')
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()

    if args.ip:
        IP = args.ip

    PORT_RANGE = tuple(args.port_range)
    MGMT_PORT = args.mgmt_port

    log.info("MultiPortHTTPServer")
    log.info(f"  Management : http://{IP}:{MGMT_PORT}")
    log.info(f"  Port range : {PORT_RANGE[0]}-{PORT_RANGE[1]}")
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
        port_range=PORT_RANGE,
        mgmt_port=MGMT_PORT
    )
    runner.start()
