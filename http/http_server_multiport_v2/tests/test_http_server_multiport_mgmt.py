"""
pytest test suite for http_server_multiport_mgmt.py

Тест-сценарии загружаются из test_config/test-config.json (ключ "tests_configs").
Тестовые startup-конфиги — из test_config/startup/*.json.
Сервер стартует один раз на сессию без startup-config; каждый функциональный
тест перед проверкой применяет нужный ему конфиг через POST /mgmt.
Все HTTP-запросы и ответы пишутся в runs/tests/.

Покрытие:
  TestMgmtAPI          — GET /status, GET /rulesets, структура и состояние
  TestHTTPRules        — каждое правило каждого ruleset × сценарий:
                         hc-text, data-json (подстановка vars)
  TestStaticServe      — static_serve (download + rate) и static_list (листинг)
  TestTCPEcho          — short, large, multiple-connections
  TestTCPLogger        — файл, формат CONNECT/DISCONNECT, новый run_id
  TestUDPEcho          — одиночная и множественные датаграммы
  TestUDPLogger        — файл, формат timestamp/src/len/hex
  TestNullServices     — TCP-порт отклоняет соединение
  TestStartupConfigs   — каждый startup-конфиг из test_config/startup/
                         применяется и верифицируется через /mgmt + /status
  TestConfigSaveLoad   — save → load roundtrip
"""

import glob
import json
import logging
import os
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime as dt
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest
import requests

start_time = dt.now()
RUN_ID = f"{start_time.strftime('%Y-%m-%d_%H-%M-%S')}.{f'{start_time.microsecond}'[:3]:03}"

# ── Пути ──────────────────────────────────────────────────────────────────────

PROJECT_DIR        = Path(__file__).parent.parent
SERVER_SCRIPT      = PROJECT_DIR / "http_server_multiport_mgmt.py"
STARTUP_CONFIG     = PROJECT_DIR / "startup-config.json"
TEST_CONFIG        = PROJECT_DIR / "test_config" / "test-config.json"
STARTUP_CFGS_DIR   = PROJECT_DIR / "test_config" / "startup"
RULESETS_DIR       = PROJECT_DIR / "rulesets"
STATIC_DIR         = PROJECT_DIR / "static"
LOGS_DIR           = PROJECT_DIR / "logs"
SERVER_LOG_DIR     = PROJECT_DIR / "runs" / "server"
TEST_LOGS_DIR      = PROJECT_DIR / "runs" / "tests"

SERVER_IP              = "127.0.0.1"
MGMT_PORT              = 62228
SERVER_STARTUP_TIMEOUT = 4.0
SOCKET_TIMEOUT         = 5.0

# ── Logging ────────────────────────────────────────────────────────────────────

TEST_LOGS_DIR.mkdir(parents=True, exist_ok=True)
_log_file = TEST_LOGS_DIR / f"run_{RUN_ID}.log"

_fmt = logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s")
_fh  = logging.FileHandler(_log_file, encoding="utf-8")
_fh.setFormatter(_fmt)
_ch  = logging.StreamHandler(sys.stdout)
_ch.setFormatter(_fmt)
_ch.setLevel(logging.INFO)

log = logging.getLogger("srv_test")
log.setLevel(logging.DEBUG)
log.addHandler(_fh)
log.addHandler(_ch)
log.info(f"Log: {_log_file}")

# ── Загрузка конфигов ─────────────────────────────────────────────────────────

def _load_json(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def _load_rulesets() -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for fp in glob.glob(str(RULESETS_DIR / "*.json")):
        try:
            data = _load_json(Path(fp))
            entries = data if isinstance(data, list) else [data]
            for entry in entries:
                result[entry["name"]] = entry
        except Exception as e:
            log.warning(f"Cannot load ruleset {fp}: {e}")
    return result

_TEST_CONFIGS: List[Dict] = (
    [c for c in _load_json(TEST_CONFIG).get("tests_configs", []) if not isinstance(c, str)]
    if TEST_CONFIG.exists() else []
)
_RULESETS: Dict[str, Any] = _load_rulesets()

# ── Нормализация ───────────────────────────────────────────────────────────────

_VALID_MODES: Dict[str, set] = {
    "tcp": {"http", "tcp_echo", "tcp_logger"},
    "udp": {"udp_echo", "udp_logger"},
}

def _norm_mode(scfg: Optional[Dict]) -> Optional[str]:
    if scfg is None:
        return None
    m = scfg.get("mode")
    return None if m in (None, "off") else m

def _resolve_ruleset(ref: str) -> str:
    p = Path(ref)
    if p.suffix == ".json" or len(p.parts) > 1:
        return p.stem
    return ref

def _is_valid(proto: str, mode: Optional[str]) -> bool:
    if mode is None:
        return True
    return mode in _VALID_MODES.get(proto, set())

def _iter_scenario_services(mode_filter: Optional[str]):
    for cfg_idx, scenario in enumerate(_TEST_CONFIGS):
        for svc, scfg in scenario.items():
            if svc.startswith("_"):
                continue
            proto, port_str = svc.split(":")
            mode = _norm_mode(scfg)
            if not _is_valid(proto, mode):
                log.warning(f"cfg{cfg_idx} {svc}: mode='{scfg.get('mode')}' "
                            f"недопустим для {proto}, пропущен")
                continue
            if mode_filter == "__null__":
                if mode is None:
                    yield cfg_idx, svc, proto, int(port_str), scfg
            elif mode_filter is None or mode == mode_filter:
                yield cfg_idx, svc, proto, int(port_str), scfg

# ── Построение параметров ──────────────────────────────────────────────────────

def _mk_params(items, id_fn=None) -> List:
    return [
        pytest.param(*t, id=(id_fn(*t) if id_fn else f"cfg{t[0]}_{t[1]}"))
        for t in items
    ]

def _or_skip(params: List, width: int) -> List:
    return params or [pytest.param(
        *(None,) * width, id="skip",
        marks=pytest.mark.skip("Нет подходящих сервисов в test-config"),
    )]

def _http_rule_params() -> List:
    """Один pytest.param на правило × HTTP-сервис × сценарий.
    Правила с response.service (static_serve/static_list) пропускаются — они
    тестируются в TestStaticServe.
    """
    params = []
    for cfg_idx, svc, proto, port, scfg in _iter_scenario_services("http"):
        ruleset_name = _resolve_ruleset(scfg.get("ruleset", ""))
        rules = _RULESETS.get(ruleset_name, {}).get("rules", [])
        for rule_idx, rule in enumerate(rules):
            resp_def = rule["response"]
            if "service" in resp_def:
                continue  # static_serve / static_list — тестируется в TestStaticServe
            r_method = rule["method"] if rule["method"] != "*" else "GET"
            if rule["path"] == "*":
                earlier = {r["path"] for r in rules[:rule_idx] if r["path"] != "*"}
                r_path = f"/wildcard-test-{rule_idx}"
                while r_path in earlier:
                    r_path += "x"
            else:
                r_path = rule["path"]
            exp_ct = (resp_def.get("Content-Type") or
                      resp_def.get("headers", {}).get("Content-Type"))
            params.append(pytest.param(
                cfg_idx, svc, port, r_method, r_path,
                resp_def["code"],
                resp_def["body"],
                resp_def.get("headers", {}),
                exp_ct,
                ruleset_name,
                id=f"cfg{cfg_idx}__{svc}__r{rule_idx}__{r_method}_{r_path.replace('/', '_')}",
            ))
    return params

def _http_svc_params() -> List:
    params = []
    for cfg_idx, svc, proto, port, scfg in _iter_scenario_services("http"):
        ruleset_name = _resolve_ruleset(scfg.get("ruleset", ""))
        params.append(pytest.param(cfg_idx, svc, port, ruleset_name,
                                   id=f"cfg{cfg_idx}__{svc}"))
    return params

def _static_serve_params() -> List:
    """HTTP-сервисы, в rulesets которых есть хотя бы одно правило static_serve."""
    params = []
    seen: set = set()
    for cfg_idx, svc, proto, port, scfg in _iter_scenario_services("http"):
        ruleset_name = _resolve_ruleset(scfg.get("ruleset", ""))
        rules = _RULESETS.get(ruleset_name, {}).get("rules", [])
        for rule in rules:
            resp = rule["response"]
            if resp.get("service") == "static_serve":
                key = (cfg_idx, svc)
                if key in seen:
                    continue
                seen.add(key)
                params.append(pytest.param(
                    cfg_idx, svc, port, ruleset_name,
                    rule["path"],
                    resp.get("files_dir", "./static"),
                    resp.get("default_rate_kb", 100),
                    resp.get("max_rate_kb", 1024),
                    id=f"cfg{cfg_idx}__{svc}__static_serve",
                ))
    return params

def _static_list_params() -> List:
    """HTTP-сервисы, в rulesets которых есть правило static_list."""
    params = []
    seen: set = set()
    for cfg_idx, svc, proto, port, scfg in _iter_scenario_services("http"):
        ruleset_name = _resolve_ruleset(scfg.get("ruleset", ""))
        rules = _RULESETS.get(ruleset_name, {}).get("rules", [])
        for rule in rules:
            resp = rule["response"]
            if resp.get("service") == "static_list":
                key = (cfg_idx, svc)
                if key in seen:
                    continue
                seen.add(key)
                params.append(pytest.param(
                    cfg_idx, svc, port, ruleset_name,
                    rule["path"],
                    resp.get("files_dir", "./static"),
                    id=f"cfg{cfg_idx}__{svc}__static_list",
                ))
    return params

def _startup_cfg_params() -> List:
    params = []
    if STARTUP_CFGS_DIR.exists():
        for f in sorted(STARTUP_CFGS_DIR.glob("*.json")):
            params.append(pytest.param(f, id=f.stem))
    return params

_HTTP_RULE_PARAMS    = _http_rule_params()
_HTTP_SVC_PARAMS     = _http_svc_params()
_STATIC_SERVE_PARAMS = _static_serve_params()
_STATIC_LIST_PARAMS  = _static_list_params()
_TCP_ECHO_PARAMS     = _mk_params(_iter_scenario_services("tcp_echo"))
_TCP_LOGGER_PARAMS   = _mk_params(_iter_scenario_services("tcp_logger"))
_UDP_ECHO_PARAMS     = _mk_params(_iter_scenario_services("udp_echo"))
_UDP_LOGGER_PARAMS   = _mk_params(_iter_scenario_services("udp_logger"))
_NULL_PARAMS         = _mk_params(_iter_scenario_services("__null__"))
_STARTUP_CFG_PARAMS  = _startup_cfg_params()

# ── Фикстура сервера ───────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def server():
    """Запустить сервер один раз на сессию, остановить в конце."""
    log.info("=" * 64)
    log.info(f"Запуск сервера: {SERVER_SCRIPT}")
    proc = subprocess.Popen(
        [sys.executable, str(SERVER_SCRIPT), "--ip", SERVER_IP],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(PROJECT_DIR),
    )

    deadline = time.time() + SERVER_STARTUP_TIMEOUT
    ready = False
    while time.time() < deadline:
        try:
            with socket.create_connection((SERVER_IP, MGMT_PORT), timeout=0.5):
                ready = True
                break
        except OSError:
            time.sleep(0.1)

    if not ready:
        proc.terminate()
        out, _ = proc.communicate(timeout=5)
        pytest.fail(f"Сервер не поднялся за {SERVER_STARTUP_TIMEOUT}s\n{out}")

    time.sleep(0.5)
    _srv_logs = (sorted(SERVER_LOG_DIR.glob("run_*.log"),
                        key=lambda p: p.stat().st_mtime, reverse=True)
                 if SERVER_LOG_DIR.exists() else [])
    if _srv_logs:
        log.info(f"Server log: {_srv_logs[0]}")
    log.info(f"Сервер готов: http://{SERVER_IP}:{MGMT_PORT}")
    log.info("=" * 64)

    yield proc

    log.info("=" * 64)
    log.info("Остановка сервера")
    proc.terminate()
    try:
        out, _ = proc.communicate(timeout=5)
        log.debug(f"stdout сервера:\n{out}")
    except subprocess.TimeoutExpired:
        proc.kill()
    log.info("Сервер остановлен")
    log.info("=" * 64)

# ── HTTP-хелпер с полным логированием ─────────────────────────────────────────

def _req(method: str, url: str, **kwargs) -> requests.Response:
    log.info(f">>> {method}  {url}  {kwargs.get('json', '')}")
    try:
        resp = requests.request(method, url, timeout=SOCKET_TIMEOUT, **kwargs)
        log.info(f"<<< {resp.status_code}  body={resp.text[:200]!r}")
        return resp
    except Exception as exc:
        log.error(f"<<< ERROR  {exc}")
        raise

def _apply_service(svc: str, mode: Optional[str], ruleset_name: Optional[str] = None):
    entry: Dict[str, Any] = {"service": svc, "mode": mode}
    if mode == "http" and ruleset_name:
        entry["ruleset"] = ruleset_name
    resp = _req("POST", f"http://{SERVER_IP}:{MGMT_PORT}/mgmt", json=[entry])
    assert resp.status_code == 200, f"POST /mgmt вернул {resp.status_code}"
    data = resp.json()
    assert data["status"] == "success", f"POST /mgmt: {data}"
    time.sleep(0.15)

# ── Management API ─────────────────────────────────────────────────────────────

class TestMgmtAPI:
    """Структура ответов /status и /rulesets."""

    def test_status_structure(self, server):
        """/status возвращает 200 и содержит необходимые ключи."""
        resp = _req("GET", f"http://{SERVER_IP}:{MGMT_PORT}/status")
        assert resp.status_code == 200
        data = resp.json()
        for key in ("server", "rulesets_loaded", "services"):
            assert key in data, f"Ключ '{key}' отсутствует в /status"
        assert data["server"]["ip"] == SERVER_IP
        log.info(f"Сервисы в /status: {list(data['services'].keys())}")

    def test_rulesets_structure(self, server):
        """/rulesets возвращает 200 и массив с name и rules_count."""
        resp = _req("GET", f"http://{SERVER_IP}:{MGMT_PORT}/rulesets")
        assert resp.status_code == 200
        data = resp.json()
        assert "rulesets" in data
        for entry in data["rulesets"]:
            assert "name" in entry and "rules_count" in entry

    def test_rulesets_count_matches_files(self, server):
        """rules_count из /rulesets совпадает с числом правил в локальном файле."""
        resp = _req("GET", f"http://{SERVER_IP}:{MGMT_PORT}/rulesets")
        assert resp.status_code == 200
        for entry in resp.json()["rulesets"]:
            name, reported = entry["name"], entry["rules_count"]
            if name in _RULESETS:
                actual = len(_RULESETS[name]["rules"])
                assert reported == actual, \
                    f"Ruleset '{name}': /rulesets сообщает {reported}, в файле {actual}"

    def test_all_rulesets_from_files_are_loaded(self, server):
        """Все рулесеты из файлов в rulesets/ загружены на сервере."""
        resp = _req("GET", f"http://{SERVER_IP}:{MGMT_PORT}/rulesets")
        assert resp.status_code == 200
        loaded = {r["name"] for r in resp.json()["rulesets"]}
        for name in _RULESETS:
            assert name in loaded, f"Ruleset '{name}' не загружен на сервере"

    def test_all_test_config_rulesets_loaded(self, server):
        """Все rulesets из test-config.json загружены на сервере."""
        resp = _req("GET", f"http://{SERVER_IP}:{MGMT_PORT}/rulesets")
        assert resp.status_code == 200
        loaded = {r["name"] for r in resp.json()["rulesets"]}
        for cfg_idx, svc, proto, port, scfg in _iter_scenario_services("http"):
            rs_name = _resolve_ruleset(scfg.get("ruleset", ""))
            assert rs_name in loaded, \
                f"cfg{cfg_idx} {svc}: ruleset '{rs_name}' не загружен"

    def test_mgmt_apply_and_status_reflect(self, server):
        """POST /mgmt применяет режим, /status отражает изменение."""
        svc = "tcp:62224"
        _apply_service(svc, "http", "rules_hc-text_200_ok")
        resp = _req("GET", f"http://{SERVER_IP}:{MGMT_PORT}/status")
        info = resp.json()["services"].get(svc, {})
        assert info.get("mode") == "http"
        assert info.get("ruleset") == "rules_hc-text_200_ok"
        assert info.get("listening") is True

    def test_mgmt_null_stops_service(self, server):
        """mode=null останавливает сервис, listening=False."""
        svc = "tcp:62227"
        _apply_service(svc, "http", "rules_hc-text_200_ok")
        _apply_service(svc, None)
        resp = _req("GET", f"http://{SERVER_IP}:{MGMT_PORT}/status")
        info = resp.json()["services"].get(svc, {})
        assert info.get("mode") is None
        assert info.get("listening") is False

    def test_mgmt_hot_swap_ruleset(self, server):
        """Смена ruleset без остановки сервиса."""
        svc = "tcp:62224"
        _apply_service(svc, "http", "rules_hc-text_200_ok")
        _apply_service(svc, "http", "rules_hc-text_500_fail")
        resp = _req("GET", f"http://{SERVER_IP}:{MGMT_PORT}/status")
        info = resp.json()["services"].get(svc, {})
        assert info.get("ruleset") == "rules_hc-text_500_fail"

    def test_mgmt_validation_invalid_format(self, server):
        """Неверный формат service → 400."""
        resp = _req("POST", f"http://{SERVER_IP}:{MGMT_PORT}/mgmt",
                    json=[{"service": "62224", "mode": "tcp_echo"}])
        assert resp.status_code == 400

    def test_mgmt_validation_port_out_of_range(self, server):
        """Порт вне диапазона → 400."""
        resp = _req("POST", f"http://{SERVER_IP}:{MGMT_PORT}/mgmt",
                    json=[{"service": "tcp:9999", "mode": "tcp_echo"}])
        assert resp.status_code == 400

    def test_mgmt_validation_http_without_ruleset(self, server):
        """mode=http без ruleset → 400."""
        resp = _req("POST", f"http://{SERVER_IP}:{MGMT_PORT}/mgmt",
                    json=[{"service": "tcp:62224", "mode": "http"}])
        assert resp.status_code == 400

    def test_mgmt_validation_unknown_ruleset(self, server):
        """Несуществующий ruleset → 400."""
        resp = _req("POST", f"http://{SERVER_IP}:{MGMT_PORT}/mgmt",
                    json=[{"service": "tcp:62224", "mode": "http",
                           "ruleset": "rules_nonexistent_xyz"}])
        assert resp.status_code == 400

    def test_mgmt_validation_udp_mode_on_tcp(self, server):
        """udp_echo на tcp-порту → 400."""
        resp = _req("POST", f"http://{SERVER_IP}:{MGMT_PORT}/mgmt",
                    json=[{"service": "tcp:62224", "mode": "udp_echo"}])
        assert resp.status_code == 400

    def test_mgmt_validation_duplicate_service(self, server):
        """Дублирующийся service в одном запросе → 400."""
        resp = _req("POST", f"http://{SERVER_IP}:{MGMT_PORT}/mgmt",
                    json=[{"service": "tcp:62224", "mode": "tcp_echo"},
                          {"service": "tcp:62224", "mode": "tcp_echo"}])
        assert resp.status_code == 400

    def test_favicon_returns_204(self, server):
        """/favicon.ico → 204."""
        resp = _req("GET", f"http://{SERVER_IP}:{MGMT_PORT}/favicon.ico")
        assert resp.status_code == 204

    def test_unknown_endpoint_returns_404(self, server):
        """Несуществующий endpoint → 404."""
        resp = _req("GET", f"http://{SERVER_IP}:{MGMT_PORT}/unknown-xyz")
        assert resp.status_code == 404

# ── HTTP ruleset ───────────────────────────────────────────────────────────────

class TestHTTPRules:
    """Для каждого правила каждого HTTP-сервиса × сценарий: код, тело, заголовки."""

    @pytest.mark.parametrize(
        "cfg_idx,svc,port,method,path,exp_code,exp_body,exp_headers,exp_content_type,ruleset_name",
        _or_skip(_HTTP_RULE_PARAMS, 10),
    )
    def test_rule_match(self, server,
                        cfg_idx, svc, port, method, path,
                        exp_code, exp_body, exp_headers, exp_content_type, ruleset_name):
        """Запрос (method, path) возвращает ожидаемый код, Content-Type и тело."""
        _apply_service(svc, "http", ruleset_name)
        resp = _req(method, f"http://{SERVER_IP}:{port}{path}")
        assert resp.status_code == exp_code, \
            f"cfg{cfg_idx} {svc} {method} {path}: ожидали {exp_code}, получили {resp.status_code}"

        if exp_content_type:
            actual_ct = resp.headers.get("Content-Type", "")
            assert exp_content_type in actual_ct, \
                (f"cfg{cfg_idx} {svc}: Content-Type: "
                 f"ожидали {exp_content_type!r}, получили {actual_ct!r}")

        if isinstance(exp_body, dict):
            actual_ct = resp.headers.get("Content-Type", "")
            assert "application/json" in actual_ct, \
                f"cfg{cfg_idx} {svc}: Content-Type должен быть application/json"
            body_json = resp.json()
            assert "body" in body_json
            actual_inner = body_json["body"]
            for key in exp_body:
                assert key in actual_inner
            for key, exp_val in exp_body.items():
                if "$" not in str(exp_val):
                    assert actual_inner[key] == exp_val
            for key, exp_val in exp_body.items():
                if "$" in str(exp_val):
                    assert "$" not in str(actual_inner[key]), \
                        f"cfg{cfg_idx} {svc}: body[{key!r}]: переменная не подставлена"
        else:
            assert resp.text == exp_body, \
                f"cfg{cfg_idx} {svc} {method} {path}: body={resp.text!r}, ожидали={exp_body!r}"

        for h_name, h_value in exp_headers.items():
            actual = resp.headers.get(h_name)
            assert actual == h_value

    @pytest.mark.parametrize(
        "cfg_idx,svc,port,ruleset_name",
        _or_skip(_HTTP_SVC_PARAMS, 4),
    )
    def test_unmatched_path(self, server, cfg_idx, svc, port, ruleset_name):
        """Путь без совпадения → catch-all (если есть) или 404."""
        _apply_service(svc, "http", ruleset_name)
        rules = _RULESETS.get(ruleset_name, {}).get("rules", [])
        explicit = {r["path"] for r in rules if r["path"] not in ("*",) and
                    "service" not in r["response"]}
        test_path = "/no-such-endpoint-xyz"
        while test_path in explicit:
            test_path += "x"

        resp = _req("GET", f"http://{SERVER_IP}:{port}{test_path}")
        catch_all = next(
            (r for r in rules
             if r["path"] == "*" and "service" not in r["response"]),
            None
        )
        if catch_all:
            exp = catch_all["response"]
            assert resp.status_code == exp["code"], \
                f"cfg{cfg_idx} {svc}: catch-all ожидали {exp['code']}, получили {resp.status_code}"
        else:
            assert resp.status_code == 404

# ── Static file server ─────────────────────────────────────────────────────────

class TestStaticServe:
    """static_serve: раздача файлов из директории с ограничением скорости."""

    @pytest.mark.parametrize(
        "cfg_idx,svc,port,ruleset_name,rule_path,files_dir,default_rate_kb,max_rate_kb",
        _or_skip(_STATIC_SERVE_PARAMS, 8),
    )
    def test_download_existing_file(self, server,
                                    cfg_idx, svc, port, ruleset_name, rule_path,
                                    files_dir, default_rate_kb, max_rate_kb):
        """Скачивание существующего файла → 200, Content-Length, контент совпадает."""
        _apply_service(svc, "http", ruleset_name)
        prefix = rule_path[:-1]  # "/download/*" → "/download/"
        target_file = "test_text.txt"
        expected = (PROJECT_DIR / files_dir / target_file).read_bytes()

        resp = _req("GET", f"http://{SERVER_IP}:{port}{prefix}{target_file}")
        assert resp.status_code == 200, \
            f"cfg{cfg_idx} {svc}: ожидали 200, получили {resp.status_code}"
        assert resp.content == expected, \
            f"cfg{cfg_idx} {svc}: контент файла не совпадает"
        assert "Content-Length" in resp.headers, "Нет заголовка Content-Length"
        assert int(resp.headers["Content-Length"]) == len(expected)
        log.info(f"cfg{cfg_idx} {svc}: {target_file} скачан, {len(expected)} байт OK")

    @pytest.mark.parametrize(
        "cfg_idx,svc,port,ruleset_name,rule_path,files_dir,default_rate_kb,max_rate_kb",
        _or_skip(_STATIC_SERVE_PARAMS, 8),
    )
    def test_download_binary_file(self, server,
                                  cfg_idx, svc, port, ruleset_name, rule_path,
                                  files_dir, default_rate_kb, max_rate_kb):
        """Скачивание бинарного файла — контент без искажений."""
        _apply_service(svc, "http", ruleset_name)
        prefix = rule_path[:-1]
        target_file = "test_binary.bin"
        expected = (PROJECT_DIR / files_dir / target_file).read_bytes()

        resp = _req("GET", f"http://{SERVER_IP}:{port}{prefix}{target_file}",
                    stream=False)
        assert resp.status_code == 200
        assert resp.content == expected, \
            f"cfg{cfg_idx} {svc}: бинарный контент не совпадает"
        log.info(f"cfg{cfg_idx} {svc}: {target_file} ({len(expected)} байт) OK")

    @pytest.mark.parametrize(
        "cfg_idx,svc,port,ruleset_name,rule_path,files_dir,default_rate_kb,max_rate_kb",
        _or_skip(_STATIC_SERVE_PARAMS, 8),
    )
    def test_download_headers(self, server,
                              cfg_idx, svc, port, ruleset_name, rule_path,
                              files_dir, default_rate_kb, max_rate_kb):
        """Ответ содержит Content-Disposition, X-Rate-Limit, Content-Length."""
        _apply_service(svc, "http", ruleset_name)
        prefix = rule_path[:-1]
        target_file = "test_text.txt"

        resp = _req("GET", f"http://{SERVER_IP}:{port}{prefix}{target_file}")
        assert resp.status_code == 200
        assert "Content-Disposition" in resp.headers, "Нет Content-Disposition"
        assert target_file in resp.headers["Content-Disposition"], \
            f"Имя файла отсутствует в Content-Disposition"
        assert "X-Rate-Limit" in resp.headers, "Нет X-Rate-Limit"
        assert "Content-Length" in resp.headers, "Нет Content-Length"
        log.info(f"cfg{cfg_idx} {svc}: заголовки: "
                 f"X-Rate-Limit={resp.headers['X-Rate-Limit']!r}, "
                 f"Content-Disposition={resp.headers['Content-Disposition']!r}")

    @pytest.mark.parametrize(
        "cfg_idx,svc,port,ruleset_name,rule_path,files_dir,default_rate_kb,max_rate_kb",
        _or_skip(_STATIC_SERVE_PARAMS, 8),
    )
    def test_download_default_rate_in_header(self, server,
                                             cfg_idx, svc, port, ruleset_name, rule_path,
                                             files_dir, default_rate_kb, max_rate_kb):
        """Без ?rate= — X-Rate-Limit равен default_rate_kb из ruleset."""
        _apply_service(svc, "http", ruleset_name)
        prefix = rule_path[:-1]
        resp = _req("GET", f"http://{SERVER_IP}:{port}{prefix}test_text.txt")
        assert resp.status_code == 200
        rate_header = resp.headers.get("X-Rate-Limit", "")
        assert str(default_rate_kb) in rate_header, \
            f"cfg{cfg_idx} {svc}: X-Rate-Limit={rate_header!r}, ожидали {default_rate_kb} KB/s"

    @pytest.mark.parametrize(
        "cfg_idx,svc,port,ruleset_name,rule_path,files_dir,default_rate_kb,max_rate_kb",
        _or_skip(_STATIC_SERVE_PARAMS, 8),
    )
    def test_download_custom_rate_param(self, server,
                                        cfg_idx, svc, port, ruleset_name, rule_path,
                                        files_dir, default_rate_kb, max_rate_kb):
        """?rate=50 применяется и отражается в X-Rate-Limit."""
        _apply_service(svc, "http", ruleset_name)
        prefix = rule_path[:-1]
        requested_rate = 50
        resp = _req("GET",
                    f"http://{SERVER_IP}:{port}{prefix}test_text.txt?rate={requested_rate}")
        assert resp.status_code == 200
        rate_header = resp.headers.get("X-Rate-Limit", "")
        assert str(requested_rate) in rate_header, \
            f"cfg{cfg_idx} {svc}: X-Rate-Limit={rate_header!r}, ожидали {requested_rate}"

    @pytest.mark.parametrize(
        "cfg_idx,svc,port,ruleset_name,rule_path,files_dir,default_rate_kb,max_rate_kb",
        _or_skip(_STATIC_SERVE_PARAMS, 8),
    )
    def test_download_rate_capped_at_max(self, server,
                                         cfg_idx, svc, port, ruleset_name, rule_path,
                                         files_dir, default_rate_kb, max_rate_kb):
        """?rate=99999 обрезается до max_rate_kb из ruleset."""
        _apply_service(svc, "http", ruleset_name)
        prefix = rule_path[:-1]
        resp = _req("GET",
                    f"http://{SERVER_IP}:{port}{prefix}test_text.txt?rate=99999")
        assert resp.status_code == 200
        rate_header = resp.headers.get("X-Rate-Limit", "")
        assert str(max_rate_kb) in rate_header, \
            f"cfg{cfg_idx} {svc}: X-Rate-Limit={rate_header!r}, ожидали cap {max_rate_kb}"

    @pytest.mark.parametrize(
        "cfg_idx,svc,port,ruleset_name,rule_path,files_dir,default_rate_kb,max_rate_kb",
        _or_skip(_STATIC_SERVE_PARAMS, 8),
    )
    def test_download_missing_file(self, server,
                                   cfg_idx, svc, port, ruleset_name, rule_path,
                                   files_dir, default_rate_kb, max_rate_kb):
        """Запрос несуществующего файла → 404."""
        _apply_service(svc, "http", ruleset_name)
        prefix = rule_path[:-1]
        resp = _req("GET",
                    f"http://{SERVER_IP}:{port}{prefix}nonexistent_xyz_file.bin")
        assert resp.status_code == 404, \
            f"cfg{cfg_idx} {svc}: ожидали 404, получили {resp.status_code}"

    @pytest.mark.parametrize(
        "cfg_idx,svc,port,ruleset_name,rule_path,files_dir,default_rate_kb,max_rate_kb",
        _or_skip(_STATIC_SERVE_PARAMS, 8),
    )
    def test_path_traversal_blocked(self, server,
                                    cfg_idx, svc, port, ruleset_name, rule_path,
                                    files_dir, default_rate_kb, max_rate_kb):
        """Попытка path traversal не выходит за пределы files_dir."""
        _apply_service(svc, "http", ruleset_name)
        prefix = rule_path[:-1]
        # Попытка достучаться до startup-config.json через ../
        resp = _req("GET",
                    f"http://{SERVER_IP}:{port}{prefix}../startup-config.json")
        # Должно быть 404 (файл в корне, не в static/) или 200 только если
        # startup-config.json случайно лежит в static/ — в этом случае тест пропускается
        static_abs = (PROJECT_DIR / files_dir / "startup-config.json")
        if static_abs.exists():
            pytest.skip("startup-config.json находится в static/ — traversal не применим")
        assert resp.status_code == 404, \
            f"cfg{cfg_idx} {svc}: path traversal не заблокирован (ожидали 404)"

    @pytest.mark.parametrize(
        "cfg_idx,svc,port,ruleset_name,rule_path,files_dir,default_rate_kb,max_rate_kb",
        _or_skip(_STATIC_SERVE_PARAMS, 8),
    )
    def test_empty_path_fallback_to_listing(self, server,
                                            cfg_idx, svc, port, ruleset_name, rule_path,
                                            files_dir, default_rate_kb, max_rate_kb):
        """GET /download/ (без имени файла) возвращает листинг."""
        _apply_service(svc, "http", ruleset_name)
        prefix = rule_path[:-1]  # "/download/"
        resp = _req("GET", f"http://{SERVER_IP}:{port}{prefix}")
        assert resp.status_code == 200
        data = resp.json()
        assert "files" in data and "count" in data, \
            f"cfg{cfg_idx} {svc}: /download/ не вернул листинг: {data}"

    @pytest.mark.parametrize(
        "cfg_idx,svc,port,ruleset_name,rule_path,files_dir,default_rate_kb,max_rate_kb",
        _or_skip(_STATIC_SERVE_PARAMS, 8),
    )
    def test_regular_rules_coexist(self, server,
                                   cfg_idx, svc, port, ruleset_name, rule_path,
                                   files_dir, default_rate_kb, max_rate_kb):
        """Обычные правила ruleset работают рядом со static_serve."""
        _apply_service(svc, "http", ruleset_name)
        rules = _RULESETS.get(ruleset_name, {}).get("rules", [])
        regular = [r for r in rules if "service" not in r["response"]
                   and r["path"] != "*"]
        if not regular:
            pytest.skip(f"cfg{cfg_idx} {svc}: нет обычных правил в {ruleset_name}")
        rule = regular[0]
        method = rule["method"] if rule["method"] != "*" else "GET"
        path = rule["path"]
        resp = _req(method, f"http://{SERVER_IP}:{port}{path}")
        assert resp.status_code == rule["response"]["code"], \
            f"cfg{cfg_idx} {svc}: {path} → {resp.status_code}, ожидали {rule['response']['code']}"


class TestStaticList:
    """static_list: JSON-листинг файлов из директории."""

    @pytest.mark.parametrize(
        "cfg_idx,svc,port,ruleset_name,list_path,files_dir",
        _or_skip(_STATIC_LIST_PARAMS, 6),
    )
    def test_list_returns_200_json(self, server,
                                   cfg_idx, svc, port, ruleset_name,
                                   list_path, files_dir):
        """GET /files → 200 application/json."""
        _apply_service(svc, "http", ruleset_name)
        resp = _req("GET", f"http://{SERVER_IP}:{port}{list_path}")
        assert resp.status_code == 200
        assert "application/json" in resp.headers.get("Content-Type", "")
        data = resp.json()
        assert "files" in data and "count" in data

    @pytest.mark.parametrize(
        "cfg_idx,svc,port,ruleset_name,list_path,files_dir",
        _or_skip(_STATIC_LIST_PARAMS, 6),
    )
    def test_list_contains_expected_files(self, server,
                                          cfg_idx, svc, port, ruleset_name,
                                          list_path, files_dir):
        """Список файлов совпадает с реальным содержимым директории."""
        _apply_service(svc, "http", ruleset_name)
        abs_dir = PROJECT_DIR / files_dir
        if not abs_dir.is_dir():
            pytest.skip(f"Директория {files_dir} не существует")

        expected_names = {f.name for f in abs_dir.iterdir() if f.is_file()}
        resp = _req("GET", f"http://{SERVER_IP}:{port}{list_path}")
        assert resp.status_code == 200
        data = resp.json()
        actual_names = {f["name"] for f in data["files"]}
        assert actual_names == expected_names, \
            f"cfg{cfg_idx} {svc}: ожидали {expected_names}, получили {actual_names}"
        assert data["count"] == len(expected_names)

    @pytest.mark.parametrize(
        "cfg_idx,svc,port,ruleset_name,list_path,files_dir",
        _or_skip(_STATIC_LIST_PARAMS, 6),
    )
    def test_list_entry_fields(self, server,
                               cfg_idx, svc, port, ruleset_name,
                               list_path, files_dir):
        """Каждый элемент листинга имеет name, size, type, modified."""
        _apply_service(svc, "http", ruleset_name)
        resp = _req("GET", f"http://{SERVER_IP}:{port}{list_path}")
        assert resp.status_code == 200
        for entry in resp.json()["files"]:
            for field in ("name", "size", "type", "modified"):
                assert field in entry, \
                    f"cfg{cfg_idx} {svc}: поле '{field}' отсутствует в файловой записи"
            assert isinstance(entry["size"], int) and entry["size"] >= 0

# ── TCP echo ───────────────────────────────────────────────────────────────────

class TestTCPEcho:
    """tcp_echo: каждый отправленный байт должен вернуться назад."""

    @pytest.mark.parametrize(
        "cfg_idx,svc,proto,port,scfg",
        _or_skip(_TCP_ECHO_PARAMS, 5),
    )
    def test_echo_short(self, server, cfg_idx, svc, proto, port, scfg):
        """Короткий payload эхируется байт-в-байт."""
        _apply_service(svc, "tcp_echo")
        payload = f"hello-echo cfg{cfg_idx} {svc}".encode()
        with socket.create_connection((SERVER_IP, port), timeout=SOCKET_TIMEOUT) as s:
            s.sendall(payload)
            s.shutdown(socket.SHUT_WR)
            received = b"".join(iter(lambda: s.recv(4096), b""))
        assert received == payload

    @pytest.mark.parametrize(
        "cfg_idx,svc,proto,port,scfg",
        _or_skip(_TCP_ECHO_PARAMS, 5),
    )
    def test_echo_large(self, server, cfg_idx, svc, proto, port, scfg):
        """8 KB payload эхируется полностью."""
        _apply_service(svc, "tcp_echo")
        payload = b"B" * 8192
        with socket.create_connection((SERVER_IP, port), timeout=SOCKET_TIMEOUT) as s:
            s.sendall(payload)
            s.shutdown(socket.SHUT_WR)
            received = b"".join(iter(lambda: s.recv(4096), b""))
        assert received == payload, \
            f"cfg{cfg_idx} {svc}: large echo: sent {len(payload)}, got {len(received)}"

    @pytest.mark.parametrize(
        "cfg_idx,svc,proto,port,scfg",
        _or_skip(_TCP_ECHO_PARAMS, 5),
    )
    def test_echo_multiple_connections(self, server, cfg_idx, svc, proto, port, scfg):
        """Три независимых соединения — каждое эхируется корректно."""
        _apply_service(svc, "tcp_echo")
        for i in range(3):
            payload = f"conn{i}-cfg{cfg_idx}-{svc}".encode()
            with socket.create_connection((SERVER_IP, port), timeout=SOCKET_TIMEOUT) as s:
                s.sendall(payload)
                s.shutdown(socket.SHUT_WR)
                received = b"".join(iter(lambda: s.recv(4096), b""))
            assert received == payload, f"cfg{cfg_idx} {svc}: conn{i} mismatch"

# ── TCP logger ─────────────────────────────────────────────────────────────────

class TestTCPLogger:
    """tcp_logger: данные пишутся в лог-файл с правильным форматом."""

    @pytest.mark.parametrize(
        "cfg_idx,svc,proto,port,scfg",
        _or_skip(_TCP_LOGGER_PARAMS, 5),
    )
    def test_log_file_created(self, server, cfg_idx, svc, proto, port, scfg):
        """После подключения появляется лог-файл в logs/."""
        _apply_service(svc, "tcp_logger")
        payload = f"tcp-logger-probe cfg{cfg_idx} {svc}".encode()
        with socket.create_connection((SERVER_IP, port), timeout=SOCKET_TIMEOUT) as s:
            s.sendall(payload)
        time.sleep(0.4)
        log_files = list(LOGS_DIR.glob(f"tcp_{port}_*.log"))
        assert log_files, f"cfg{cfg_idx} {svc}: лог-файл не найден в {LOGS_DIR}"

    @pytest.mark.parametrize(
        "cfg_idx,svc,proto,port,scfg",
        _or_skip(_TCP_LOGGER_PARAMS, 5),
    )
    def test_log_format(self, server, cfg_idx, svc, proto, port, scfg):
        """Лог содержит CONNECT/DISCONNECT маркеры, src= и raw payload."""
        _apply_service(svc, "tcp_logger")
        payload = f"format-check cfg{cfg_idx} {svc} {time.time():.3f}".encode()
        with socket.create_connection((SERVER_IP, port), timeout=SOCKET_TIMEOUT) as s:
            s.sendall(payload)
        time.sleep(0.4)
        log_files = sorted(LOGS_DIR.glob(f"tcp_{port}_*.log"))
        assert log_files
        content = log_files[-1].read_bytes()
        assert b"=== CONNECT "    in content, "Нет маркера '=== CONNECT'"
        assert b"=== DISCONNECT " in content, "Нет маркера '=== DISCONNECT'"
        assert b"src="            in content, "Нет 'src=' в строке CONNECT"
        assert payload            in content, f"Payload {payload!r} не найден в логе"

    @pytest.mark.parametrize(
        "cfg_idx,svc,proto,port,scfg",
        _or_skip(_TCP_LOGGER_PARAMS, 5),
    )
    def test_new_log_file_after_reassign(self, server, cfg_idx, svc, proto, port, scfg):
        """После переназначения режима log_file получает новый Run-ID."""
        resp1 = _req("POST", f"http://{SERVER_IP}:{MGMT_PORT}/mgmt",
                     json=[{"service": svc, "mode": "tcp_logger"}])
        assert resp1.json()["status"] == "success"
        log_file_1 = resp1.json()["results"][0]["log_file"]

        _apply_service(svc, None)
        time.sleep(0.05)

        resp2 = _req("POST", f"http://{SERVER_IP}:{MGMT_PORT}/mgmt",
                     json=[{"service": svc, "mode": "tcp_logger"}])
        assert resp2.json()["status"] == "success"
        log_file_2 = resp2.json()["results"][0]["log_file"]

        assert log_file_1 != log_file_2, \
            f"cfg{cfg_idx} {svc}: Run-ID не изменился: {log_file_1!r} == {log_file_2!r}"

# ── UDP echo ───────────────────────────────────────────────────────────────────

class TestUDPEcho:
    """udp_echo: каждая датаграмма возвращается отправителю без изменений."""

    @pytest.mark.parametrize(
        "cfg_idx,svc,proto,port,scfg",
        _or_skip(_UDP_ECHO_PARAMS, 5),
    )
    def test_echo_datagram(self, server, cfg_idx, svc, proto, port, scfg):
        """Одиночная датаграмма эхируется."""
        _apply_service(svc, "udp_echo")
        payload = f"udp-echo cfg{cfg_idx} {svc}".encode()
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(SOCKET_TIMEOUT)
            s.sendto(payload, (SERVER_IP, port))
            received, addr = s.recvfrom(65535)
        assert received == payload

    @pytest.mark.parametrize(
        "cfg_idx,svc,proto,port,scfg",
        _or_skip(_UDP_ECHO_PARAMS, 5),
    )
    def test_echo_multiple_datagrams(self, server, cfg_idx, svc, proto, port, scfg):
        """Пять датаграмм подряд — каждая эхируется независимо."""
        _apply_service(svc, "udp_echo")
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(SOCKET_TIMEOUT)
            for i in range(5):
                payload = f"dgram{i}-cfg{cfg_idx}-{svc}".encode()
                s.sendto(payload, (SERVER_IP, port))
                received, _ = s.recvfrom(65535)
                assert received == payload, f"cfg{cfg_idx} {svc}: dgram{i} mismatch"

# ── UDP logger ─────────────────────────────────────────────────────────────────

class TestUDPLogger:
    """udp_logger: каждая датаграмма дописывается в лог-файл в hex-формате."""

    @pytest.mark.parametrize(
        "cfg_idx,svc,proto,port,scfg",
        _or_skip(_UDP_LOGGER_PARAMS, 5),
    )
    def test_log_file_created(self, server, cfg_idx, svc, proto, port, scfg):
        """После отправки датаграммы появляется лог-файл."""
        _apply_service(svc, "udp_logger")
        payload = f"udp-logger-probe cfg{cfg_idx} {svc}".encode()
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.sendto(payload, (SERVER_IP, port))
        time.sleep(0.3)
        log_files = list(LOGS_DIR.glob(f"udp_{port}_*.log"))
        assert log_files, f"cfg{cfg_idx} {svc}: лог-файл не найден"

    @pytest.mark.parametrize(
        "cfg_idx,svc,proto,port,scfg",
        _or_skip(_UDP_LOGGER_PARAMS, 5),
    )
    def test_log_format(self, server, cfg_idx, svc, proto, port, scfg):
        """Каждая строка лога содержит timestamp, src=, len=, data=<hex>."""
        _apply_service(svc, "udp_logger")
        payload = f"udp-fmt cfg{cfg_idx} {svc} {time.time():.3f}".encode()
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.sendto(payload, (SERVER_IP, port))
        time.sleep(0.3)
        log_files = sorted(LOGS_DIR.glob(f"udp_{port}_*.log"))
        assert log_files
        content = log_files[-1].read_text(encoding="utf-8")
        assert "src="        in content
        assert "len="        in content
        assert "data="       in content
        assert payload.hex() in content, f"Hex-payload не найден в логе"

# ── Null services ──────────────────────────────────────────────────────────────

class TestNullServices:
    """mode=off/null: TCP-порт должен отклонять соединения."""

    @pytest.mark.parametrize(
        "cfg_idx,svc,proto,port,scfg",
        _or_skip(_NULL_PARAMS, 5),
    )
    def test_tcp_port_closed(self, server, cfg_idx, svc, proto, port, scfg):
        """После применения mode=null TCP-соединение отклоняется."""
        if proto != "tcp":
            pytest.skip("connection-refused применимо только к TCP")
        _apply_service(svc, None)
        time.sleep(0.2)
        with pytest.raises(OSError):
            socket.create_connection((SERVER_IP, port), timeout=1.0)

# ── Startup configs ────────────────────────────────────────────────────────────

class TestStartupConfigs:
    """Каждый файл из test_config/startup/ применяется через POST /mgmt и верифицируется."""

    @pytest.mark.parametrize("config_path", _or_skip(_STARTUP_CFG_PARAMS, 1))
    def test_config_is_applicable(self, server, config_path):
        """Применить startup-конфиг через /mgmt, проверить /status."""
        cfg = _load_json(config_path)
        commands: List[Dict] = []
        for svc_key, svc_cfg in cfg.items():
            if svc_key.startswith("_"):
                continue
            entry: Dict[str, Any] = {
                "service": svc_key,
                "mode": svc_cfg.get("mode") if svc_cfg else None,
            }
            if svc_cfg and svc_cfg.get("mode") == "http":
                entry["ruleset"] = _resolve_ruleset(svc_cfg.get("ruleset", ""))
            commands.append(entry)

        if not commands:
            pytest.skip(f"{config_path.name}: нет команд для применения")

        # Таймаут пропорционален числу сервисов: stop(≤1s) + start(0.1s) каждый
        mgmt_timeout = max(SOCKET_TIMEOUT, len(commands) * 2 + 3)
        resp = requests.post(
            f"http://{SERVER_IP}:{MGMT_PORT}/mgmt",
            json=commands,
            timeout=mgmt_timeout,
        )
        assert resp.status_code == 200, \
            f"{config_path.name}: POST /mgmt → {resp.status_code}: {resp.text}"
        assert resp.json()["status"] == "success", resp.json()

        time.sleep(0.2)

        status_resp = _req("GET", f"http://{SERVER_IP}:{MGMT_PORT}/status")
        services = status_resp.json()["services"]

        for svc_key, svc_cfg in cfg.items():
            if svc_key.startswith("_"):
                continue
            exp_mode = svc_cfg.get("mode") if svc_cfg else None
            assert svc_key in services, \
                f"{config_path.name}: {svc_key} не найден в /status"
            info = services[svc_key]
            assert info["mode"] == exp_mode, \
                f"{config_path.name} {svc_key}: mode={info['mode']!r}, ожидали={exp_mode!r}"
            if exp_mode:
                assert info["listening"] is True, \
                    f"{config_path.name} {svc_key}: listening=False при mode={exp_mode!r}"
            if exp_mode == "http":
                exp_rs = _resolve_ruleset(svc_cfg.get("ruleset", ""))
                assert info.get("ruleset") == exp_rs, \
                    f"{config_path.name} {svc_key}: ruleset mismatch"
            if exp_mode in ("tcp_logger", "udp_logger"):
                assert "log_file" in info, \
                    f"{config_path.name} {svc_key}: нет log_file в /status"
        log.info(f"{config_path.name}: OK ({len(commands)} сервисов)")

# ── Config save / load ─────────────────────────────────────────────────────────

class TestConfigSaveLoad:
    """POST /config/save + POST /config/load: roundtrip сохраняет и восстанавливает состояние."""

    def test_save_returns_success(self, server):
        """POST /config/save возвращает success."""
        _apply_service("tcp:62224", "http", "rules_hc-text_200_ok")
        resp = _req("POST", f"http://{SERVER_IP}:{MGMT_PORT}/config/save")
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

    def test_save_load_roundtrip(self, server):
        """Apply → save → load → /status должен совпадать с исходным состоянием."""
        commands = [
            {"service": "tcp:62224", "mode": "http", "ruleset": "rules_hc-text_200_ok"},
            {"service": "tcp:62225", "mode": "tcp_echo"},
        ]
        resp = _req("POST", f"http://{SERVER_IP}:{MGMT_PORT}/mgmt", json=commands)
        assert resp.status_code == 200
        time.sleep(0.15)

        save_resp = _req("POST", f"http://{SERVER_IP}:{MGMT_PORT}/config/save")
        assert save_resp.status_code == 200

        # Изменить состояние
        _apply_service("tcp:62224", "http", "rules_hc-text_500_fail")
        time.sleep(0.1)

        # config/load останавливает и перезапускает сервисы → нужен увеличенный таймаут
        load_resp = requests.post(
            f"http://{SERVER_IP}:{MGMT_PORT}/config/load", timeout=20.0)
        assert load_resp.status_code == 200
        time.sleep(0.3)

        status_resp = _req("GET", f"http://{SERVER_IP}:{MGMT_PORT}/status")
        services = status_resp.json()["services"]
        assert services["tcp:62224"]["ruleset"] == "rules_hc-text_200_ok", \
            "После load: ruleset должен быть восстановлен"
        assert services["tcp:62225"]["mode"] == "tcp_echo"

    def test_load_missing_config_returns_404(self, server):
        """POST /config/load при отсутствующем файле → 404."""
        backup = PROJECT_DIR / "startup-config.json.bak"
        original = PROJECT_DIR / "startup-config.json"
        if original.exists():
            shutil.copy(str(original), str(backup))
            original.unlink()
        try:
            resp = _req("POST", f"http://{SERVER_IP}:{MGMT_PORT}/config/load")
            assert resp.status_code == 404, \
                f"Ожидали 404 при отсутствующем файле, получили {resp.status_code}"
        finally:
            if backup.exists():
                shutil.copy(str(backup), str(original))
                backup.unlink()
