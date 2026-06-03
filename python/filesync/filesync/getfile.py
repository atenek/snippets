"""getfile — резервное копирование заданного набора файлов (remote -> local).

Реализация по wiki/todo/getfile.md. Фазы: expand -> metadata -> transfer -> verify
-> запись manifest(.json/.csv)+session.json (RO) -> статистика.
"""

from __future__ import annotations

import argparse
import os
import re
import sys

try:
    from . import core
except ImportError:  # запуск как отдельный скрипт
    import core  # type: ignore

DEFAULT_PATH = "../backup_files/"


# --------------------------------------------------------------------------
# Ввод
# --------------------------------------------------------------------------

def read_filelist(path: str) -> list[str]:
    """Прочитать список путей: одна строка = один путь; '#' и пустые — пропуск."""
    out: list[str] = []
    seen: set[str] = set()
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            # нормализация: убрать хвостовой '/' (кроме корня) для дедупликации
            if len(s) > 1:
                s = s.rstrip("/") or "/"
            if s not in seen:
                seen.add(s)
                out.append(s)
    return out


def _sanitize_label(label: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", label).strip("_")


def session_dirname(host: str, label: str) -> str:
    from datetime import datetime
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    base = f"{host}__{ts}"
    return f"{base}__{label}" if label else base


def _write_restore_list(manifest: list[dict], path: str) -> None:
    """Editable-таблица override атрибутов для put: '<perms> <owner> <group> <path>'.
    Пользователь правит первые три поля ('-' = взять из metadata); путь — остаток
    строки (допускает пробелы). Файл писать обычным (editable), не RO."""
    with open(path, "w", encoding="utf-8") as f:
        f.write("# filesync restore overrides. Отредактируйте perms/owner/group; '-' = как в metadata.\n")
        f.write("# Применить: filesync put <session> --apply-list restore.txt --target-root ... --yes\n")
        f.write("# <perms> <owner> <group> <remote_path>\n")
        for rec in manifest:
            s = rec["source"]
            if s["type"] not in ("regular_file", "directory", "symlink") or not s["metadata_complete"]:
                continue
            perms = "-" if s["type"] == "symlink" else (s["permissions_octal"] or "-")
            owner = s["owner"] or "-"
            group = s["group"] or "-"
            f.write(f"{perms} {owner} {group} {s['remote_path']}\n")


# --------------------------------------------------------------------------
# Классификация и верификация
# --------------------------------------------------------------------------

def _classify(rec: dict, enum_denied: bool) -> None:
    """Предварительный copy.status по метаданным (до transfer)."""
    s, c = rec["source"], rec["copy"]
    if not s["metadata_complete"]:
        c["status"] = "no_permission"
        c["unreadable_reason"] = "stat_failed"
        return
    t = s["type"]
    if t == "regular_file":
        if s["md5_remote"]:
            c["status"] = "success"
            s["content_captured"] = True
        else:
            c["status"] = "no_permission"
            c["unreadable_reason"] = "permission_denied"
    elif t == "symlink":
        c["status"] = "success"
    elif t == "directory":
        c["status"] = "metadata_only"
        s["contents_enumerated"] = not enum_denied
        if enum_denied:
            c["unreadable_reason"] = "enumeration_denied"
            c["error"] = "directory contents could not be enumerated"
    else:  # block/char/fifo/socket/unknown
        c["status"] = "metadata_only"


def _ancestors(path: str) -> list[str]:
    """Цепочка родительских каталогов пути (без корня '/')."""
    out: list[str] = []
    p = os.path.dirname(path.rstrip("/"))
    while p and p != "/":
        out.append(p)
        p = os.path.dirname(p)
    return out


def _capture_ancestors(host: str, records: dict) -> None:
    """Дозаписать в records родительские каталоги всех объектов (для faithful
    восстановления цепочки). Корень '/' не пишем. В payload НЕ кладём —
    только metadata + restore.txt; зеркало создаст их при распаковке детей."""
    wanted: set[str] = set()
    for p in list(records):
        for a in _ancestors(p):
            if a not in records:
                wanted.add(a)
    wanted -= set(records)
    if not wanted:
        return
    anc = sorted(wanted)
    meta = core.collect_metadata(host, anc)
    for path, m in zip(anc, meta):
        if path in records:
            continue
        rec = core.new_record(host, path)
        if m is not None:
            rec["source"].update(m)
            rec["source"]["metadata_complete"] = True
        _classify(rec, enum_denied=False)
        records[path] = rec


def _verify(rec: dict, files_dir: str, saved_epoch: int, saved_iso: str) -> None:
    """Сверка локальной копии с метаданными (см. getfile.md §10)."""
    s, d, c, v = rec["source"], rec["destination"], rec["copy"], rec["verify"]

    if c["status"] in ("not_found", "failed", "no_permission"):
        v["status"] = "skipped"
        return

    lp = os.path.join(files_dir, s["remote_path"].lstrip("/"))
    d["local_path"] = lp
    d["saved_at_epoch"] = saved_epoch
    d["saved_at_iso"] = saved_iso

    t = s["type"]
    if t == "regular_file":
        if not os.path.isfile(lp) or os.path.islink(lp):
            c["status"] = "failed"
            c["error"] = "not present after extract"
            v["status"] = "missing"
            return
        try:
            local_md5 = core.read_local_md5(lp)
        except OSError as exc:
            v["status"] = "no_md5"
            v["error"] = f"local copy unreadable: {exc}"
            return
        v["md5_local"] = local_md5
        if s["md5_remote"] is None:
            v["status"] = "no_md5"
        elif local_md5 == s["md5_remote"]:
            v["status"] = "ok"
        else:
            v["status"] = "md5_mismatch"
    elif t == "symlink":
        if not os.path.islink(lp):
            v["status"] = "missing"
        elif os.readlink(lp) == s["symlink_target"]:
            v["status"] = "present"
        else:
            v["status"] = "md5_mismatch"
            v["error"] = "symlink target differs"
    elif t == "directory":
        v["status"] = "present" if (os.path.isdir(lp) and not os.path.islink(lp)) else "missing"
    else:  # спец-файлы: локальная распаковка не от root могла не воссоздать узел
        if os.path.lexists(lp):
            v["status"] = "present"
        else:
            v["status"] = "skipped"
            v["error"] = "special file not recreated (non-root extraction)"


# --------------------------------------------------------------------------
# Основной поток
# --------------------------------------------------------------------------

def run(filelist: str, host: str, label: str, base_path: str) -> int:
    if not os.path.isfile(filelist):
        print(f"error: filelist not found: {filelist}", file=sys.stderr)
        return 1

    input_paths = read_filelist(filelist)
    if not input_paths:
        print(f"error: filelist is empty: {filelist}", file=sys.stderr)
        return 1

    sess_name = session_dirname(host, _sanitize_label(label))
    session_dir = os.path.join(base_path, sess_name)
    files_dir = os.path.join(session_dir, "files")
    meta_dir = os.path.join(session_dir, "metadata")
    os.makedirs(files_dir, exist_ok=True)
    os.makedirs(meta_dir, exist_ok=True)
    # имя payload дублирует имя сессии (host__date__message) — см. README/step_by_step
    payload_name = sess_name + ".tar"
    payload_path = os.path.join(session_dir, payload_name)

    start_epoch, start_iso = core.utc_now()
    print(f"Session: {session_dir}")
    print(f"Host:    {host}   |   items in list: {len(input_paths)}")

    # --- expand + metadata --------------------------------------------------
    try:
        records, not_found, enum_denied, other_errs = core.build_records(host, input_paths)
    except core.RemoteError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for line in other_errs:
        print(f"warning: {line}", file=sys.stderr)

    input_set = set(input_paths)        # для статистики dirs_expanded
    existing = list(records)            # найденные пути (в порядке обхода)
    for path in existing:
        _classify(records[path], enum_denied=path in enum_denied)

    # родительская цепочка → metadata + restore.txt (не в payload)
    _capture_ancestors(host, records)

    # каталоги, в которые find не смог зайти, но которых нет в stdout -> мин. запись
    for path in enum_denied:
        if path not in records:
            rec = core.new_record(host, path)
            rec["source"]["type"] = "directory"
            rec["source"]["contents_enumerated"] = False
            rec["copy"]["status"] = "metadata_only"
            rec["copy"]["unreadable_reason"] = "enumeration_denied"
            records[path] = rec

    # not_found -> запись
    for path in not_found:
        rec = core.new_record(host, path)
        rec["copy"]["status"] = "not_found"
        records[path] = rec
    # пути из списка, не попавшие ни в existing, ни в ошибки
    for path in input_paths:
        if path not in records:
            rec = core.new_record(host, path)
            rec["copy"]["status"] = "not_found"
            records[path] = rec

    # --- transfer -----------------------------------------------------------
    if existing:
        for path in existing:
            records[path]["destination"]["in_payload"] = True
        rc, tar_err = core.transfer_payload(host, existing, payload_path)
        if rc != 0 and tar_err.strip():
            # tar мог частично отработать; не фатально — поймаем на verify
            print(f"warning: tar (remote): {tar_err.strip()}", file=sys.stderr)
        ec, ex_err = core.extract_payload(payload_path, files_dir)
        if ec != 0 and ex_err.strip():
            print(f"warning: tar (local extract): {ex_err.strip()}", file=sys.stderr)

    # --- verify -------------------------------------------------------------
    saved_epoch, saved_iso = core.utc_now()
    for rec in records.values():
        _verify(rec, files_dir, saved_epoch, saved_iso)

    # --- запись -------------------------------------------------------------
    manifest = [records[p] for p in sorted(records)]
    stats = _compute_stats(manifest, input_set)
    finish_epoch, finish_iso = core.utc_now()

    session = {
        "schema_version": core.SCHEMA_VERSION,
        "kind": "get",
        "hostname": host,
        "label": label,
        "filelist": os.path.abspath(filelist),
        "session_dir": os.path.abspath(session_dir),
        "payload": payload_name,
        "started_at_iso": start_iso,
        "finished_at_iso": finish_iso,
        "stats": stats,
    }

    manifest_json = os.path.join(meta_dir, "manifest.json")
    manifest_csv = os.path.join(meta_dir, "manifest.csv")
    session_json = os.path.join(meta_dir, "session.json")
    core.write_manifest_json(manifest, manifest_json)
    core.write_manifest_csv(manifest, manifest_csv)
    core.write_json(session, session_json)
    # restore.txt — editable-слой override прав/владельца/группы для put (НЕ RO)
    _write_restore_list(manifest, os.path.join(session_dir, "restore.txt"))
    # RO — последним шагом: метаданные + payload (getfile.md §9.7)
    core.set_readonly(manifest_json, manifest_csv, session_json, payload_path)

    _print_summary(host, label, session_dir, stats)
    return _exit_code(stats)


def _compute_stats(manifest: list[dict], input_set: set[str]) -> dict:
    by_copy: dict[str, int] = {}
    by_verify: dict[str, int] = {}
    dirs_unreadable = 0
    dirs_expanded = 0
    for rec in manifest:
        s, c, v = rec["source"], rec["copy"], rec["verify"]
        by_copy[c["status"]] = by_copy.get(c["status"], 0) + 1
        by_verify[v["status"]] = by_verify.get(v["status"], 0) + 1
        if s["contents_enumerated"] is False:
            dirs_unreadable += 1
        if s["type"] == "directory" and s["remote_path"] in input_set:
            dirs_expanded += 1
    return {
        "total": len(manifest),
        "dirs_expanded": dirs_expanded,
        "success": by_copy.get("success", 0),
        "metadata_only": by_copy.get("metadata_only", 0),
        "dirs_unreadable": dirs_unreadable,
        "no_permission": by_copy.get("no_permission", 0),
        "not_found": by_copy.get("not_found", 0),
        "failed": by_copy.get("failed", 0),
        "verify_ok": by_verify.get("ok", 0),
        "verify_present": by_verify.get("present", 0),
        "verify_missing": by_verify.get("missing", 0),
        "verify_mismatch": by_verify.get("md5_mismatch", 0),
    }


def _print_summary(host: str, label: str, session_dir: str, st: dict) -> None:
    line = "=" * 49
    sep = "-" * 49
    print()
    print(line)
    print(f"  Host:    {host}")
    print(f"  Label:   {label}")
    print(f"  Session: {session_dir}")
    print(sep)
    print(f"  Processed:        {st['total']}")
    print(f"    Copied OK:      {st['success']}")
    print(f"    Metadata only:  {st['metadata_only']}")
    if st["dirs_unreadable"]:
        print(f"    Dir unreadable: {st['dirs_unreadable']}   <-- содержимое могло быть пропущено")
    print(f"    No permission:  {st['no_permission']}")
    print(f"    Not found:      {st['not_found']}")
    print(f"    Failed:         {st['failed']}")
    print(sep)
    print("  Verification:")
    print(f"    OK:             {st['verify_ok']}")
    print(f"    Present:        {st['verify_present']}")
    print(f"    Missing:        {st['verify_missing']}")
    print(f"    MD5 mismatch:   {st['verify_mismatch']}")
    print(line)


def _exit_code(st: dict) -> int:
    problems = (
        st["failed"] + st["not_found"] + st["no_permission"]
        + st["verify_missing"] + st["verify_mismatch"] + st["dirs_unreadable"]
    )
    return 2 if problems else 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="getfile",
        description="Backup заданного набора файлов с удалённого хоста (remote -> local).",
    )
    p.add_argument("filelist", help="путь к локальному файлу со списком удалённых путей")
    p.add_argument("hostname", help="имя хоста или IP (запись в ~/.ssh/config)")
    p.add_argument("-m", "--message", default="", help="метка (alias) в имени папки сессии")
    p.add_argument("-p", "--path", default=DEFAULT_PATH,
                   help=f"базовая директория для сохранения (default: {DEFAULT_PATH})")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run(args.filelist, args.hostname, args.message, args.path)


if __name__ == "__main__":
    sys.exit(main())
