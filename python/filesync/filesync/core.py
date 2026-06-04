"""Общее ядро набора filesync.

Содержит то, что переиспользуют все утилиты (см. wiki/todo/architecture.md §5):
  * SSH/sudo-слой (run_remote) с раздельным захватом stdout/stderr;
  * remote-примитивы: find (раскрытие), батч stat+md5sum+readlink (метаданные),
    потоковый tar (передача);
  * модель сессии и именование;
  * модель записи manifest и её сериализация в JSON и CSV;
  * единые статусы и обработка недоступности.

Зависимостей вне stdlib нет. Удалённые команды требуют sudo (NOPASSWD),
см. wiki/todo/done/getfile.md §13.
"""

from __future__ import annotations

import csv
import datetime as _dt
import fnmatch
import hashlib
import json
import logging
import logging.config
import os
import re
import shlex
import subprocess
import sys
import time
from typing import Iterable

SCHEMA_VERSION = "1.0"

log = logging.getLogger("filesync.core")


# --------------------------------------------------------------------------
# Логирование (logging + dictConfig) — см. wiki/docs/logging.md, wiki/todo/logging.md
# --------------------------------------------------------------------------

# Имя каталога логов захардкожено — ключами запуска не настраивается (требование ТЗ).
LOG_DIR_NAME = "logs"

# Корень проекта = родитель пакета filesync/ (этот файл — filesync/core.py).
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# CLI-значение --logging -> числовой уровень logging. NONE = выключено.
_LOG_LEVELS: dict[str, int | None] = {
    "NONE": None,
    "ERROR": logging.ERROR,
    "WARN": logging.WARNING,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
}
LOG_CHOICES = ["NONE", "ERROR", "WARN", "WARNING", "INFO", "DEBUG"]


def _run_dir_name() -> str:
    """Имя каталога запуска: run<ГГГГ-ММ-ДД_ЧЧ-ММ-СС>.<мс> (сортируемо, без коллизий)."""
    now = _dt.datetime.now()
    return now.strftime("run%Y-%m-%d_%H-%M-%S") + f".{now.microsecond // 1000:03d}"


def configure_logging(level: str, *, command: str = "filesync",
                      log_root: str | None = None) -> str | None:
    """Настроить логирование набора по выбранному уровню (--logging).

    Зовётся ОДИН раз из main() утилиты, до основной работы. Два хендлера:
      * file    — полный аудит запуска в logs/run.../<command>.log (уровень = level);
      * console — только проблемы в stderr (уровень max(level, WARNING)).

    `log_root` — внутренний параметр для тестов (по умолчанию — logs/ в корне
    проекта); это НЕ CLI-ключ (имя каталога захардкожено).

    Возвращает путь к каталогу запуска (logs/run.../), либо None при NONE.
    """
    name = (level or "INFO").upper()
    lvl = _LOG_LEVELS.get(name, logging.INFO)
    logging.Formatter.converter = time.gmtime  # время логов — в UTC (как session.json)

    logger = logging.getLogger("filesync")
    # снять ранее добавленные file/console-хендлеры (NullHandler оставить)
    for h in list(logger.handlers):
        if not isinstance(h, logging.NullHandler):
            logger.removeHandler(h)
            h.close()

    if lvl is None:  # NONE — каталог не создаём, вывод глушим
        logger.setLevel(logging.CRITICAL + 1)
        logger.propagate = False
        return None

    run_dir = os.path.join(log_root or os.path.join(PROJECT_ROOT, LOG_DIR_NAME),
                           _run_dir_name())
    os.makedirs(run_dir, exist_ok=True)
    log_path = os.path.join(run_dir, f"{command}.log")
    console_level = max(lvl, logging.WARNING)  # консоль не флудит пер-объектными INFO

    logging.config.dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "plain": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"},
            "detailed": {"format": "%(asctime)s %(levelname)s %(name)s "
                                   "%(module)s:%(lineno)d: %(message)s"},
        },
        "handlers": {
            "file": {"class": "logging.FileHandler", "filename": log_path,
                     "encoding": "utf-8", "errors": "backslashreplace",
                     "formatter": "detailed", "level": logging.getLevelName(lvl)},
            "console": {"class": "logging.StreamHandler", "stream": "ext://sys.stderr",
                        "formatter": "plain", "level": logging.getLevelName(console_level)},
        },
        "loggers": {
            "filesync": {"level": logging.getLevelName(lvl),
                         "handlers": ["file", "console"], "propagate": False},
        },
    })
    log.debug("logging configured: level=%s console=%s dir=%r",
              name, logging.getLevelName(console_level), run_dir)
    return run_dir


def safe_path(p: str) -> str:
    """Путь, безопасный для логов: гасит не-UTF8 байты (surrogateescape) в \\xNN."""
    return p.encode("utf-8", "surrogateescape").decode("utf-8", "backslashreplace")

# --------------------------------------------------------------------------
# SSH-слой
# --------------------------------------------------------------------------

# BatchMode=yes — никаких интерактивных запросов (только ключи из ~/.ssh/config).
SSH_BASE = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10"]

def sudo_prefix(use_sudo: bool) -> str:
    return "sudo -n " if use_sudo else ""


# --------------------------------------------------------------------------
# Правила исключения (ignore), подмножество .gitignore — см. wiki/todo/done/exclude_rules.md
# --------------------------------------------------------------------------

class ExcludeRules:
    """Подмножество .gitignore:
      * bare-имя без '/' (venv, .idea, *.log) — совпадение с ЛЮБЫМ компонентом
        пути (на любой глубине; «в середине пути»);
      * хвостовой '/' (venv/) — только если объект каталог;
      * ведущий '/' (/cache) — якорь к верхнему уровню корня;
      * globs * ? [] (fnmatch). Без негации и ** (v1).
    """

    def __init__(self, patterns: list[str]):
        self.rules: list[tuple[str, str, bool, bool]] = []  # (orig, pat, anchored, dir_only)
        for raw in patterns:
            # Семантика .gitignore: одна строка = один паттерн. Пробелы внутри —
            # литеральные (часть имени), НЕ разделители; несколько паттернов через
            # пробел в одной строке git трактует как одно имя со спейсами и ничего
            # не матчит. Поэтому правило — по одному паттерну на строку.
            s = raw.strip()
            if not s or s.startswith("#"):
                continue
            if " " in s:
                # почти всегда — попытка задать несколько паттернов в строке (не
                # как в git). Не матчим молча — предупреждаем (см. exclude_rules.md §10).
                log.warning("ignore-паттерн содержит пробел и трактуется как одно имя "
                            "(один паттерн на строку, как в .gitignore): %r", s)
            orig, anchored = s, s.startswith("/")
            if anchored:
                s = s[1:]
            dir_only = s.endswith("/")
            if dir_only:
                s = s.rstrip("/")
            if s:
                self.rules.append((orig, s, anchored, dir_only))

    def __bool__(self) -> bool:
        return bool(self.rules)

    @property
    def patterns(self) -> list[str]:
        return [r[0] for r in self.rules]

    def match(self, rel: str, is_dir: bool) -> str | None:
        """Вернуть исходный паттерн, если `rel` (путь относительно корня) исключён."""
        comps = [c for c in rel.split("/") if c]
        if not comps:
            return None
        for orig, pat, anchored, dir_only in self.rules:
            if dir_only and not is_dir:
                continue
            if anchored:
                if fnmatch.fnmatch(comps[0], pat):
                    return orig
            elif any(fnmatch.fnmatch(c, pat) for c in comps):
                return orig
        return None


def load_exclude_rules(path: str) -> ExcludeRules:
    with open(path, encoding="utf-8") as f:
        return ExcludeRules(f.read().splitlines())


def _root_of(p: str, roots: list[str]) -> str:
    """Самая длинная запись filelist, являющаяся корнем пути p."""
    for r in roots:
        rr = r.rstrip("/")
        if p == rr or p.startswith(rr + "/"):
            return rr
    return ""


def _filter_excludes(existing: list[str], types: dict[str, str],
                     input_paths: list[str], rules: ExcludeRules):
    """Отфильтровать рекурсивно раскрытые пути по правилам.

    Верхнеуровневые записи filelist (явный выбор) НЕ фильтруются: явный файл —
    остаётся; явный каталог — корень, его потомки фильтруются. Совпавший каталог
    прунится вместе с поддеревом. Возвращает (kept, excluded{path:(typechar,pat)}).
    """
    input_set = set(p.rstrip("/") for p in input_paths)
    roots = sorted((p.rstrip("/") for p in input_paths), key=len, reverse=True)
    kept: list[str] = []
    excluded: dict[str, tuple[str, str]] = {}
    active_prune: str | None = None
    debug = log.isEnabledFor(logging.DEBUG)
    for p in sorted(existing):
        if p in input_set:
            kept.append(p)        # явная запись filelist — обход исключений (даже внутри pruned)
            if debug:
                log.debug("exclude: kept %r (явный вход filelist — обход исключений)", safe_path(p))
            continue
        if active_prune is not None and (p == active_prune or p.startswith(active_prune + "/")):
            if debug:
                log.debug("exclude: pruned %r (потомок исключённого %r)",
                          safe_path(p), safe_path(active_prune))
            continue  # потомок исключённого каталога — отбрасываем молча
        active_prune = None
        root = _root_of(p, roots)
        rel = p[len(root):].lstrip("/") if root else p.lstrip("/")
        is_dir = types.get(p) == "d"
        pat = rules.match(rel, is_dir)
        if pat is None:
            kept.append(p)
            if debug:
                log.debug("exclude: kept %r (rel=%r — нет совпадения)", safe_path(p), rel)
        else:
            excluded[p] = (types.get(p, "?"), pat)
            if is_dir:
                active_prune = p
            if debug:
                log.debug("exclude: excluded %r (rel=%r rule=%r%s)",
                          safe_path(p), rel, pat, ", prune" if is_dir else "")
    return kept, excluded


class RemoteError(RuntimeError):
    """Ошибка выполнения удалённой команды (на уровне ssh/транспорта)."""


def run_remote(
    host: str,
    remote_cmd: str,
    input_bytes: bytes | None = None,
    stdout_path: str | None = None,
    timeout: float | None = None,
    local: bool = False,
) -> tuple[int, bytes, bytes]:
    """Выполнить команду по SSH (`ssh host cmd`) или локально (`bash -c cmd`).

    `remote_cmd` передаётся как единая строка — её разбирает shell, поэтому пути
    внутри неё должны быть уже корректно квотированы (shlex.quote).

    `local=True` — исполнять на этой же машине без SSH (транспорт; задаётся явно,
    не зависит от строки `host`, которая остаётся лишь меткой/именем сессии).
    Если задан `stdout_path` — поток stdout пишется прямо в этот файл (для tar).
    """
    args = ["bash", "-c", remote_cmd] if local else SSH_BASE + [host, remote_cmd]
    try:
        if stdout_path is not None:
            with open(stdout_path, "wb") as out:
                proc = subprocess.run(
                    args, input=input_bytes, stdout=out,
                    stderr=subprocess.PIPE, timeout=timeout,
                )
            return proc.returncode, b"", proc.stderr
        proc = subprocess.run(
            args, input=input_bytes, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=timeout,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except FileNotFoundError as exc:  # ssh не найден
        raise RemoteError(f"ssh not available: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RemoteError(f"remote command timed out: {exc}") from exc


# --------------------------------------------------------------------------
# Кодирование путей
# --------------------------------------------------------------------------
# Имена в Linux — произвольные байты (кроме \0). surrogateescape позволяет
# гонять их через str без потерь.

def path_to_bytes(p: str) -> bytes:
    return p.encode("utf-8", "surrogateescape")


def bytes_to_path(b: bytes) -> str:
    return b.decode("utf-8", "surrogateescape")


def _decode(b: bytes) -> str:
    return b.decode("utf-8", "surrogateescape")


# --------------------------------------------------------------------------
# Remote-примитивы
# --------------------------------------------------------------------------

# find: раскрытие путей (файлы возвращают себя, директории — всё содержимое).
# mindepth 0 (включая стартовые пути) — поведение find по умолчанию.
# -printf '%y%p\0': первый байт записи — тип (d/f/l/b/c/p/s), далее путь, NUL —
# разделитель. Тип нужен для правил исключения (dir-only) без лишних stat.
_FIND_SCRIPT = "export LC_ALL=C\nexec find \"$@\" -printf '%y%p\\0'\n"

# Метаданные: один проход по null-списку путей из stdin.
# Путь НЕ эхосится обратно — записи выравниваются по порядку входных путей.
# Формат записи:  <stat-blob>\037<md5>\037<symlink-target>\000
# stat-blob:      19 полей через '|' (порядок ниже), либо строка STATFAIL.
_META_SCRIPT = (
    "export LC_ALL=C\n"
    "while IFS= read -r -d '' p; do\n"
    "  if st=$(stat -c "
    "'%F|%s|%a|%A|%u|%U|%g|%G|%d|%i|%h|%t|%T|%Y|%y|%X|%x|%Z|%z' -- \"$p\" 2>/dev/null); then\n"
    "    ftype=${st%%|*}\n"
    "    md5=''\n"
    "    link=''\n"
    "    case \"$ftype\" in\n"
    "      'regular file'|'regular empty file') "
    "md5=$(md5sum -- \"$p\" 2>/dev/null | cut -d' ' -f1) ;;\n"
    "      'symbolic link') link=$(readlink -- \"$p\" 2>/dev/null) ;;\n"
    "    esac\n"
    "    printf '%s\\037%s\\037%s\\000' \"$st\" \"$md5\" \"$link\"\n"
    "  else\n"
    "    printf 'STATFAIL\\037\\037\\000'\n"
    "  fi\n"
    "done\n"
)

# Тип объекта определяем по первому символу символьных прав `%A` —
# это locale-независимо (в отличие от текста `%F`).
_TYPE_FROM_MODE = {
    "-": "regular_file",
    "d": "directory",
    "l": "symlink",
    "b": "block_device",
    "c": "char_device",
    "p": "fifo",
    "s": "socket",
}
# Текстовый `%F` — резервный источник (на случай нестандартного `%A`).
_TYPE_MAP = {
    "regular file": "regular_file",
    "regular empty file": "regular_file",
    "directory": "directory",
    "symbolic link": "symlink",
    "block special file": "block_device",
    "character special file": "char_device",
    "fifo": "fifo",
    "socket": "socket",
}

_FIND_ERR_RE = re.compile(r"^find: '(?P<path>.*)': (?P<msg>.*)$")


def expand_paths(host: str, input_paths: list[str], use_sudo: bool = True,
                 local: bool = False, exclude: "ExcludeRules | None" = None):
    """Раскрыть входные пути на remote.

    Возвращает: (existing, not_found, enum_denied, other_errors, excluded).
      existing      — найденные объекты (после применения правил исключения);
      not_found     — пути, которых нет на remote;
      enum_denied   — каталоги, в которые find не смог зайти даже под sudo;
      other_errors  — прочие строки ошибок find (для предупреждения);
      excluded      — {path: (typechar, pattern)} отброшенные правилами (точки prune).
    """
    if not input_paths:
        return [], set(), set(), [], {}

    cmd = (
        sudo_prefix(use_sudo) + "bash -c " + shlex.quote(_FIND_SCRIPT) + " filesync "
        + " ".join(shlex.quote(p) for p in input_paths)
    )
    rc, out, err = run_remote(host, cmd, local=local)

    existing: list[str] = []
    types: dict[str, str] = {}
    seen: set[str] = set()
    for chunk in out.split(b"\0"):
        if not chunk:
            continue
        tch = chunk[:1].decode("ascii", "replace")   # тип: d/f/l/b/c/p/s
        p = _decode(chunk[1:])
        if p not in seen:
            seen.add(p)
            existing.append(p)
            types[p] = tch

    not_found: set[str] = set()
    enum_denied: set[str] = set()
    other: list[str] = []
    for line in _decode(err).splitlines():
        m = _FIND_ERR_RE.match(line)
        if not m:
            if line.strip():
                other.append(line)
            continue
        path, msg = m.group("path"), m.group("msg")
        if "No such file or directory" in msg:
            not_found.add(path)
        elif "Permission denied" in msg:
            enum_denied.add(path)
        else:
            other.append(line)

    # find c rc!=0 при недоступных подкаталогах — это НЕ фатально (см. getfile.md §7).
    if rc != 0 and not (not_found or enum_denied) and not existing:
        raise RemoteError(f"find failed: {_decode(err).strip()}")

    log.debug("expand: входов=%d, найдено=%d, find rc=%d, not_found=%d, enum_denied=%d",
              len(input_paths), len(existing), rc, len(not_found), len(enum_denied))

    excluded: dict[str, tuple[str, str]] = {}
    if exclude:
        before = len(existing)
        existing, excluded = _filter_excludes(existing, types, input_paths, exclude)
        log.debug("expand: после фильтра исключений оставлено=%d, исключено=%d (было %d)",
                  len(existing), len(excluded), before)

    return existing, not_found, enum_denied, other, excluded


def collect_metadata(host: str, paths: list[str], use_sudo: bool = True, local: bool = False) -> list[dict | None]:
    """Собрать метаданные для `paths` одним SSH-вызовом.

    Возвращает список, выровненный по `paths`: для каждого пути — словарь
    распарсенных полей, либо None при STATFAIL (метаданные недоступны).
    """
    if not paths:
        return []

    payload = b"".join(path_to_bytes(p) + b"\0" for p in paths)
    cmd = sudo_prefix(use_sudo) + "bash -c " + shlex.quote(_META_SCRIPT)
    rc, out, err = run_remote(host, cmd, input_bytes=payload, local=local)

    records = [r for r in out.split(b"\0") if r != b""]
    result: list[dict | None] = []
    for raw in records:
        fields = raw.split(b"\x1f")
        blob = _decode(fields[0]) if fields else ""
        if blob == "STATFAIL" or "|" not in blob:
            result.append(None)
            continue
        md5 = _decode(fields[1]) if len(fields) > 1 else ""
        link = _decode(fields[2]) if len(fields) > 2 else ""
        result.append(_parse_stat_blob(blob, md5, link))

    # Выравнивание: если remote вернул меньше записей — добиваем None.
    while len(result) < len(paths):
        result.append(None)
    return result[: len(paths)]


def _parse_stat_blob(blob: str, md5: str, link: str) -> dict:
    """Разобрать stat-blob (19 полей через '|') в словарь полей source."""
    f = blob.split("|")
    type_desc = f[0]
    mode_char = f[3][:1] if len(f) > 3 else ""
    ftype = _TYPE_FROM_MODE.get(mode_char) or _TYPE_MAP.get(type_desc, "unknown")

    def _int(x: str):
        try:
            return int(x)
        except (ValueError, TypeError):
            return None

    perms_octal = (f[2] or "").zfill(4)

    device_major = device_minor = None
    if ftype in ("block_device", "char_device"):
        try:
            device_major = int(f[11], 16)
            device_minor = int(f[12], 16)
        except (ValueError, IndexError):
            pass

    symlink_target = link if ftype == "symlink" and link != "" else None
    md5_remote = md5 if (ftype == "regular_file" and md5) else None

    return {
        "type": ftype,
        "size_bytes": _int(f[1]),
        "permissions_octal": perms_octal,
        "permissions_symbolic": f[3],
        "uid": _int(f[4]),
        "owner": f[5],
        "gid": _int(f[6]),
        "group": f[7],
        "device": _int(f[8]),
        "inode": _int(f[9]),
        "hard_links": _int(f[10]),
        "device_major": device_major,
        "device_minor": device_minor,
        "symlink_target": symlink_target,
        "symlink_target_absolute": (symlink_target.startswith("/") if symlink_target else None),
        "mtime_epoch": _int(f[13]),
        "mtime_iso": _stat_time_to_iso(f[14]),
        "atime_epoch": _int(f[15]),
        "atime_iso": _stat_time_to_iso(f[16]),
        "ctime_epoch": _int(f[17]),
        "ctime_iso": _stat_time_to_iso(f[18]),
        "md5_remote": md5_remote,
    }


def _stat_time_to_iso(s: str) -> str | None:
    """'2026-06-02 10:00:00.123456789 +0000' -> '2026-06-02T10:00:00.123456789+00:00'."""
    s = (s or "").strip()
    if not s:
        return None
    parts = s.split(" ")
    if len(parts) != 3:
        return None
    date_part, time_part, tz_part = parts
    iso = f"{date_part}T{time_part}"
    if len(tz_part) == 5 and tz_part[0] in "+-":
        iso += f"{tz_part[:3]}:{tz_part[3:]}"
    else:
        iso += tz_part
    return iso


# --------------------------------------------------------------------------
# Передача данных (tar)
# --------------------------------------------------------------------------
# На create НЕ используем --absolute-names: tar срезает ведущий '/', складывая
# относительные имена. На extract складываем под files/ (тоже без
# --absolute-names) — это безопасно (никакой записи по абсолютным путям).
# payload.tar при этом остаётся пригодным для restore: `tar -x -C /target`.

def transfer_payload(host: str, paths: list[str], payload_path: str, use_sudo: bool = True, local: bool = False) -> tuple[int, str]:
    """Создать payload.tar потоком `tar` по null-списку `paths`."""
    if not paths:
        return 0, ""
    payload = b"".join(path_to_bytes(p) + b"\0" for p in paths)
    cmd = (
        sudo_prefix(use_sudo) + "tar --create --numeric-owner --sparse --no-recursion "
        "--null --files-from=- --file=-"
    )
    rc, _out, err = run_remote(host, cmd, input_bytes=payload, stdout_path=payload_path, local=local)
    return rc, _decode(err)


def extract_payload(payload_path: str, files_dir: str) -> tuple[int, str]:
    """Распаковать payload.tar в browsable-зеркало files/ (локально, не от root)."""
    os.makedirs(files_dir, exist_ok=True)
    try:
        proc = subprocess.run(
            ["tar", "--extract", "--file", payload_path, "-C", files_dir],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise RemoteError(f"local tar not available: {exc}") from exc
    return proc.returncode, proc.stderr.decode("utf-8", "surrogateescape")


# --------------------------------------------------------------------------
# Модель записи manifest
# --------------------------------------------------------------------------

def new_record(host: str, remote_path: str) -> dict:
    """Пустая запись manifest со всеми полями (см. getfile.md §9.2)."""
    name = os.path.basename(remote_path) or remote_path
    return {
        "schema_version": SCHEMA_VERSION,
        "source": {
            "hostname": host,
            "remote_path": remote_path,
            "name": name,
            "type": None,
            "size_bytes": None,
            "permissions_octal": None,
            "permissions_symbolic": None,
            "uid": None, "owner": None,
            "gid": None, "group": None,
            "device": None, "inode": None, "hard_links": None,
            "device_major": None, "device_minor": None,
            "symlink_target": None, "symlink_target_absolute": None,
            "mtime_epoch": None, "mtime_iso": None,
            "atime_epoch": None, "atime_iso": None,
            "ctime_epoch": None, "ctime_iso": None,
            "md5_remote": None,
            "metadata_complete": False,
            "content_captured": False,
            "contents_enumerated": None,
        },
        "destination": {
            "local_path": None,
            "in_payload": False,
            "saved_at_epoch": None,
            "saved_at_iso": None,
        },
        "copy": {"status": None, "error": None, "unreadable_reason": None},
        "verify": {"status": "skipped", "md5_local": None, "error": None},
    }


def build_records(host: str, input_paths: list[str], use_sudo: bool = True,
                  local: bool = False, exclude: "ExcludeRules | None" = None):
    """Раскрыть пути и собрать метаданные → словарь {remote_path: record}.

    Записи содержат заполненный `source` (+ `metadata_complete`); классификация
    `copy.status` остаётся за утилитой (get/diff). Возвращает
    (records, not_found, enum_denied, other_errors, excluded).
    """
    existing, not_found, enum_denied, other_errs, excluded = expand_paths(
        host, input_paths, use_sudo, local, exclude)
    meta = collect_metadata(host, existing, use_sudo, local)
    records: dict[str, dict] = {}
    for path, m in zip(existing, meta):
        rec = new_record(host, path)
        if m is not None:
            rec["source"].update(m)
            rec["source"]["metadata_complete"] = True
        records[path] = rec
    return records, not_found, enum_denied, other_errs, excluded


def utc_now() -> tuple[int, str]:
    now = _dt.datetime.now(_dt.timezone.utc)
    return int(now.timestamp()), now.isoformat()


def md5_file(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_local_md5(path: str) -> str:
    """MD5 файла в зеркале. Копия могла распаковаться без owner-read
    (напр. mode 000) — зеркало best-effort, поэтому добираем owner-read."""
    try:
        return md5_file(path)
    except PermissionError:
        os.chmod(path, os.stat(path).st_mode | 0o400)
        return md5_file(path)


# --------------------------------------------------------------------------
# Сериализация manifest: JSON + CSV (см. getfile.md §9.6)
# --------------------------------------------------------------------------

CSV_COLUMNS = [
    "remote_path", "name", "type", "size_bytes",
    "permissions_octal", "permissions_symbolic",
    "uid", "owner", "gid", "group",
    "device", "inode", "hard_links", "device_major", "device_minor",
    "symlink_target", "mtime_iso", "atime_iso", "ctime_iso", "md5_remote",
    "metadata_complete", "content_captured", "contents_enumerated",
    "local_path", "in_payload", "saved_at_iso",
    "copy_status", "copy_unreadable_reason", "copy_error",
    "verify_status", "verify_md5_local", "verify_error",
]


def _csv_value(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def flatten_record(rec: dict) -> dict:
    """Плоский словарь базовых колонок записи (для CSV)."""
    s, d, c, v = rec["source"], rec["destination"], rec["copy"], rec["verify"]
    flat = {
        "remote_path": s["remote_path"], "name": s["name"], "type": s["type"],
        "size_bytes": s["size_bytes"], "permissions_octal": s["permissions_octal"],
        "permissions_symbolic": s["permissions_symbolic"],
        "uid": s["uid"], "owner": s["owner"], "gid": s["gid"], "group": s["group"],
        "device": s["device"], "inode": s["inode"], "hard_links": s["hard_links"],
        "device_major": s["device_major"], "device_minor": s["device_minor"],
        "symlink_target": s["symlink_target"], "mtime_iso": s["mtime_iso"],
        "atime_iso": s["atime_iso"], "ctime_iso": s["ctime_iso"],
        "md5_remote": s["md5_remote"], "metadata_complete": s["metadata_complete"],
        "content_captured": s["content_captured"], "contents_enumerated": s["contents_enumerated"],
        "local_path": d["local_path"], "in_payload": d["in_payload"],
        "saved_at_iso": d["saved_at_iso"], "copy_status": c["status"],
        "copy_unreadable_reason": c["unreadable_reason"], "copy_error": c["error"],
        "verify_status": v["status"], "verify_md5_local": v["md5_local"],
        "verify_error": v["error"],
    }
    return flat


def write_manifest_json(manifest: list[dict], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        f.write("\n")


def write_manifest_csv(manifest: list[dict], path: str,
                       extra_columns: list[str] | None = None,
                       extra_extractor=None) -> None:
    """CSV-проекция манифеста (RFC 4180). Утилиты (diff) могут добавить свои
    колонки через `extra_columns` + `extra_extractor(rec) -> dict`."""
    cols = list(CSV_COLUMNS) + list(extra_columns or [])
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for rec in manifest:
            base = flatten_record(rec)
            row = [_csv_value(base[c]) for c in CSV_COLUMNS]
            if extra_columns:
                ex = extra_extractor(rec) if extra_extractor else {}
                row += [_csv_value(ex.get(c)) for c in extra_columns]
            w.writerow(row)


def write_json(obj, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def set_readonly(*paths: str) -> None:
    """RO (0444) на файлы метаданных — последним шагом (getfile.md §9.7)."""
    for p in paths:
        try:
            os.chmod(p, 0o444)
        except OSError:
            pass
