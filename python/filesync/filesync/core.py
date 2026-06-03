"""Общее ядро набора filesync.

Содержит то, что переиспользуют все утилиты (см. wiki/todo/architecture.md §5):
  * SSH/sudo-слой (run_remote) с раздельным захватом stdout/stderr;
  * remote-примитивы: find (раскрытие), батч stat+md5sum+readlink (метаданные),
    потоковый tar (передача);
  * модель сессии и именование;
  * модель записи manifest и её сериализация в JSON и CSV;
  * единые статусы и обработка недоступности.

Зависимостей вне stdlib нет. Удалённые команды требуют sudo (NOPASSWD),
см. wiki/todo/getfile.md §13.
"""

from __future__ import annotations

import csv
import datetime as _dt
import hashlib
import json
import os
import re
import shlex
import subprocess
from typing import Iterable

SCHEMA_VERSION = "1.0"

# --------------------------------------------------------------------------
# SSH-слой
# --------------------------------------------------------------------------

# BatchMode=yes — никаких интерактивных запросов (только ключи из ~/.ssh/config).
SSH_BASE = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10"]


class RemoteError(RuntimeError):
    """Ошибка выполнения удалённой команды (на уровне ssh/транспорта)."""


def run_remote(
    host: str,
    remote_cmd: str,
    input_bytes: bytes | None = None,
    stdout_path: str | None = None,
    timeout: float | None = None,
) -> tuple[int, bytes, bytes]:
    """Выполнить команду на удалённом хосте по SSH.

    `remote_cmd` передаётся как единая строка — её разбирает удалённый shell,
    поэтому пути внутри неё должны быть уже корректно квотированы (shlex.quote).

    Если задан `stdout_path` — поток stdout пишется прямо в этот файл (для tar),
    и в возвращаемом кортеже stdout будет b"".
    """
    args = SSH_BASE + [host, remote_cmd]
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
# mindepth 0 (включая сами стартовые пути) — поведение find по умолчанию,
# поэтому флаг не указываем: иначе GNU find шлёт warning в stderr.
_FIND_SCRIPT = 'export LC_ALL=C\nexec find "$@" -print0\n'

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


def expand_paths(host: str, input_paths: list[str]) -> tuple[list[str], set[str], set[str], list[str]]:
    """Раскрыть входные пути на remote.

    Возвращает: (existing, not_found, enum_denied, other_errors).
      existing      — все найденные объекты (файлы + раскрытое содержимое директорий);
      not_found     — пути, которых нет на remote;
      enum_denied   — каталоги, в которые find не смог зайти даже под sudo;
      other_errors  — прочие строки ошибок find (для предупреждения).
    """
    if not input_paths:
        return [], set(), set(), []

    cmd = (
        "sudo -n bash -c " + shlex.quote(_FIND_SCRIPT) + " filesync "
        + " ".join(shlex.quote(p) for p in input_paths)
    )
    rc, out, err = run_remote(host, cmd)

    existing: list[str] = []
    seen: set[str] = set()
    for chunk in out.split(b"\0"):
        if not chunk:
            continue
        p = _decode(chunk)
        if p not in seen:
            seen.add(p)
            existing.append(p)

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

    return existing, not_found, enum_denied, other


def collect_metadata(host: str, paths: list[str]) -> list[dict | None]:
    """Собрать метаданные для `paths` одним SSH-вызовом.

    Возвращает список, выровненный по `paths`: для каждого пути — словарь
    распарсенных полей, либо None при STATFAIL (метаданные недоступны).
    """
    if not paths:
        return []

    payload = b"".join(path_to_bytes(p) + b"\0" for p in paths)
    cmd = "sudo -n bash -c " + shlex.quote(_META_SCRIPT)
    rc, out, err = run_remote(host, cmd, input_bytes=payload)

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

def transfer_payload(host: str, paths: list[str], payload_path: str) -> tuple[int, str]:
    """Создать payload.tar потоком `sudo tar` по null-списку `paths`."""
    if not paths:
        return 0, ""
    payload = b"".join(path_to_bytes(p) + b"\0" for p in paths)
    cmd = (
        "sudo -n tar --create --numeric-owner --sparse --no-recursion "
        "--null --files-from=- --file=-"
    )
    rc, _out, err = run_remote(host, cmd, input_bytes=payload, stdout_path=payload_path)
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


def build_records(host: str, input_paths: list[str]):
    """Раскрыть пути и собрать метаданные → словарь {remote_path: record}.

    Записи содержат заполненный `source` (+ `metadata_complete`); классификация
    `copy.status` остаётся за утилитой (get/diff). Возвращает
    (records, not_found, enum_denied, other_errors).
    """
    existing, not_found, enum_denied, other_errs = expand_paths(host, input_paths)
    meta = collect_metadata(host, existing)
    records: dict[str, dict] = {}
    for path, m in zip(existing, meta):
        rec = new_record(host, path)
        if m is not None:
            rec["source"].update(m)
            rec["source"]["metadata_complete"] = True
        records[path] = rec
    return records, not_found, enum_denied, other_errs


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
