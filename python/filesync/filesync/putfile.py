"""putfile — развёртывание сессии на удалённую машину (local -> remote).

Единая форма:  put <session> [HOST] --target-root ROOT

Источник данных — всегда папка сессии:
  * контент берётся из `files/` (подхватывает локальные правки);
  * `restore.txt` задаёт ВЫБОР объектов (восстанавливаются только перечисленные)
    и их атрибуты (`<perms> <owner> <group> <path>`; '-' = из metadata);
  * недостающие родительские каталоги создаются `mkdir -p` без смены атрибутов;
  * `payload.tar` самим put НЕ используется (это «холодный» архив).

Спец-объекты (устройства/fifo/сокеты) через put не восстанавливаются — только
вручную из `payload.tar`. Безопасность: --target-root обязателен; '/' только с
--yes; защита от path traversal; запись требует подтверждения. См. wiki/todo/putfile.md.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sys

try:
    from . import core
except ImportError:  # запуск как отдельный скрипт
    import core  # type: ignore

_RESTORE_CSV_COLUMNS = ["restore_target", "restore_action",
                        "restore_status", "restore_md5_after", "restore_error"]


def _restore_extractor(rec: dict) -> dict:
    r = rec.get("restore", {})
    return {
        "restore_target": r.get("target_path"),
        "restore_action": r.get("action"),
        "restore_status": r.get("status"),
        "restore_md5_after": r.get("md5_remote_after"),
        "restore_error": r.get("error"),
    }


# --------------------------------------------------------------------------
# restore.txt (выбор + атрибуты)
# --------------------------------------------------------------------------

def _parse_restore_list(path: str) -> list[tuple[str, str, str, str]]:
    """restore.txt -> [(remote_path, perms, owner, group)] в порядке файла."""
    out: list[tuple[str, str, str, str]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            parts = line.rstrip("\n").split(None, 3)
            if len(parts) < 4:
                continue
            perms, owner, group, p = parts
            out.append((p, perms, owner, group))
    return out


def _selection_from_manifest(manifest: list[dict]) -> list[tuple[str, str, str, str]]:
    """Фолбэк, если restore.txt нет: все объекты с атрибутами из metadata."""
    out = []
    for rec in manifest:
        s = rec["source"]
        if s["type"] in ("regular_file", "directory", "symlink") and s["metadata_complete"]:
            out.append((s["remote_path"], "-", "-", "-"))
    return out


# --------------------------------------------------------------------------
# Пути / безопасность
# --------------------------------------------------------------------------

def _safe_target(target_root: str, remote_path: str) -> str | None:
    root = os.path.normpath(target_root)
    tp = os.path.normpath(os.path.join(root, remote_path.lstrip("/")))
    if tp == root or tp.startswith(root + os.sep):
        return tp
    return None


# --------------------------------------------------------------------------
# Удалённые операции
# --------------------------------------------------------------------------

def _remote_meta(host: str, paths: list[str]) -> dict[str, dict | None]:
    metas = core.collect_metadata(host, paths)
    return {p: m for p, m in zip(paths, metas)}


def _backup_existing(host: str, targets: list[str], out_path: str) -> tuple[int, str]:
    data = b"".join(core.path_to_bytes(p) + b"\0" for p in targets)
    cmd = ("sudo -n tar --create --numeric-owner --sparse --no-recursion "
           "--null --files-from=- --file=-")
    rc, _out, err = core.run_remote(host, cmd, input_bytes=data, stdout_path=out_path)
    return rc, core._decode(err)


def _apply(host: str, files_dir: str, recs: list[dict], set_times: bool) -> list[str]:
    """Развернуть объекты из files/ + установить атрибуты. Возвращает warnings."""
    warns: list[str] = []
    dirs = [r for r in recs if r["source"]["type"] == "directory"]
    leaves = [r for r in recs if r["source"]["type"] in ("regular_file", "symlink")]
    others = [r for r in recs if r["source"]["type"] not in ("directory", "regular_file", "symlink")]
    for r in others:
        warns.append(f"{r['source']['type']} '{r['source']['remote_path']}' "
                     f"пропущен (восстановите вручную из payload.tar)")

    # 1) каталоги (от корня к листьям) — mkdir -p создаёт и недостающих родителей
    for r in sorted(dirs, key=lambda r: r["source"]["remote_path"].count("/")):
        core.run_remote(host, f"sudo -n mkdir -p {shlex.quote(r['restore']['target_path'])}")

    # 2) файлы и симлинки (родители создаются нейтрально через mkdir -p)
    for r in leaves:
        s = r["source"]
        tp = r["restore"]["target_path"]
        core.run_remote(host, f"sudo -n mkdir -p {shlex.quote(os.path.dirname(tp))}")
        if s["type"] == "regular_file":
            lp = os.path.join(files_dir, s["remote_path"].lstrip("/"))
            try:
                with open(lp, "rb") as f:
                    data = f.read()
            except OSError as exc:
                warns.append(f"{s['remote_path']}: нет контента в files/ ({exc})")
                r["restore"]["status"] = "failed"
                r["restore"]["error"] = "no local content"
                continue
            core.run_remote(host, f"sudo -n tee {shlex.quote(tp)} >/dev/null", input_bytes=data)
        else:  # symlink
            core.run_remote(host, f"sudo -n ln -sfn {shlex.quote(s['symlink_target'])} {shlex.quote(tp)}")

    # 3) атрибуты: chown -> chmod (-> mtime); mtime каталогов — последними
    for r in leaves + dirs:
        _set_attrs(host, r, set_times)
    if set_times:
        for r in dirs:
            _touch(host, r)
    return warns


def _set_attrs(host: str, rec: dict, set_times: bool) -> None:
    s = rec["source"]
    tp = rec["restore"]["target_path"]
    is_link = s["type"] == "symlink"
    owner = s["owner"] if (s["owner"] and s["owner"] != "UNKNOWN") else s["uid"]
    group = s["group"] if (s["group"] and s["group"] != "UNKNOWN") else s["gid"]
    if owner is not None and group is not None:
        h = "-h " if is_link else ""
        core.run_remote(host, f"sudo -n chown {h}{owner}:{group} {shlex.quote(tp)}")
    if not is_link and s["permissions_octal"]:
        core.run_remote(host, f"sudo -n chmod {s['permissions_octal']} {shlex.quote(tp)}")
    if set_times and s["type"] != "directory":
        _touch(host, rec)


def _touch(host: str, rec: dict) -> None:
    s = rec["source"]
    iso = s.get("mtime_iso")
    if not iso:
        return
    h = "-h " if s["type"] == "symlink" else ""
    core.run_remote(host, f"sudo -n touch {h}-d {shlex.quote(iso)} {shlex.quote(rec['restore']['target_path'])}")


def _verify_remote(host: str, recs: list[dict]) -> None:
    targets = [r["restore"]["target_path"] for r in recs
               if r["restore"]["action"] != "skip" and r["restore"]["status"] != "failed"]
    meta = _remote_meta(host, targets) if targets else {}
    for r in recs:
        res = r["restore"]
        if res["action"] == "skip" or res["status"] == "failed":
            res["status"] = res["status"] or "skipped"
            continue
        s = r["source"]
        m = meta.get(res["target_path"])
        if m is None:
            res["status"] = "failed"
            res["error"] = "not present after apply"
            continue
        res["md5_remote_after"] = m.get("md5_remote")
        owner_ok = (m.get("uid") == s["uid"]) or (m.get("owner") == s["owner"])
        group_ok = (m.get("gid") == s["gid"]) or (m.get("group") == s["group"])
        perms_ok = (s["type"] == "symlink") or (m.get("permissions_octal") == s["permissions_octal"])
        if s["type"] == "regular_file" and s["md5_remote"] is not None and m.get("md5_remote") != s["md5_remote"]:
            res["status"] = "content_mismatch"
        elif not (owner_ok and group_ok and perms_ok):
            res["status"] = "attr_mismatch"
        else:
            res["status"] = "ok"


# --------------------------------------------------------------------------
# Основной поток
# --------------------------------------------------------------------------

def run(session: str, host: str | None, target_root: str, dry_run: bool, yes: bool,
        backup_existing: bool, set_times: bool) -> int:
    meta_dir = os.path.join(session, "metadata")
    try:
        with open(os.path.join(meta_dir, "manifest.json"), encoding="utf-8") as f:
            manifest = json.load(f)
        with open(os.path.join(meta_dir, "session.json"), encoding="utf-8") as f:
            sess = json.load(f)
    except (OSError, ValueError) as exc:
        print(f"error: cannot read session: {exc}", file=sys.stderr)
        return 1

    host = host or sess.get("hostname")
    if not host:
        print("error: hostname not given and not in session.json", file=sys.stderr)
        return 1

    target_root = os.path.normpath(target_root)
    if not target_root.startswith("/"):
        print("error: --target-root must be absolute", file=sys.stderr)
        return 1
    if target_root == "/" and not yes:
        print("error: refusing to restore to '/' without --yes", file=sys.stderr)
        return 1

    files_dir = os.path.join(session, "files")
    if not os.path.isdir(files_dir):
        print("error: no files/ in session", file=sys.stderr)
        return 1

    # выбор + атрибуты: из restore.txt (или весь манифест, если его нет)
    restore_txt = os.path.join(session, "restore.txt")
    if os.path.isfile(restore_txt):
        selection = _parse_restore_list(restore_txt)
    else:
        print("warning: restore.txt not found — восстанавливаю весь манифест", file=sys.stderr)
        selection = _selection_from_manifest(manifest)

    by_path = {rec["source"]["remote_path"]: rec for rec in manifest}
    recs: list[dict] = []
    seen: set[str] = set()
    for p, perms, owner, group in selection:
        if p in seen:
            continue
        seen.add(p)
        rec = by_path.get(p)
        if rec is None:
            print(f"warning: restore.txt: '{p}' нет в манифесте — пропуск", file=sys.stderr)
            continue
        s = rec["source"]
        # эффективные атрибуты (override поверх metadata)
        if perms != "-" and s["type"] != "symlink":
            s["permissions_octal"] = perms
        if owner != "-":
            s["owner"], s["uid"] = owner, None
        if group != "-":
            s["group"], s["gid"] = group, None
        # контент из files/ → пересчёт md5 для верификации
        if s["type"] == "regular_file":
            lp = os.path.join(files_dir, p.lstrip("/"))
            if os.path.isfile(lp) and not os.path.islink(lp):
                try:
                    s["md5_remote"] = core.read_local_md5(lp)
                except OSError:
                    pass
        tp = _safe_target(target_root, p)
        rec["restore"] = {"target_path": tp, "action": None, "status": None,
                          "md5_remote_after": None, "error": None}
        if tp is None:
            rec["restore"].update(action="skip", status="skipped",
                                  error="path escapes target-root")
        recs.append(rec)

    valid = [r for r in recs if r["restore"]["target_path"] is not None]
    target_paths = [r["restore"]["target_path"] for r in valid]

    print(f"Target host: {host}")
    print(f"Target root: {target_root}")
    print(f"Session:     {session}")
    existing_map = _remote_meta(host, target_paths) if target_paths else {}
    overwrite_targets = []
    for r in valid:
        tp = r["restore"]["target_path"]
        if existing_map.get(tp) is not None:
            r["restore"]["action"] = "overwrite"
            overwrite_targets.append(tp)
        else:
            r["restore"]["action"] = "create"

    _print_plan(recs)
    if dry_run:
        print("\n[dry-run] ничего не изменено.")
        return 0

    if not yes:
        if sys.stdin.isatty():
            if input("\nПрименить изменения на удалённый хост? [y/N] ").strip().lower() not in ("y", "yes"):
                print("отменено.")
                return 0
        else:
            print("error: требуется --yes (или --dry-run) для применения", file=sys.stderr)
            return 3

    from datetime import datetime
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    runlog = os.path.join(os.path.dirname(os.path.abspath(session.rstrip("/"))),
                          f"{host}__{ts}__restore")
    os.makedirs(runlog, exist_ok=True)

    if backup_existing and overwrite_targets:
        bkp = os.path.join(runlog, "backup_existing.tar")
        rc, err = _backup_existing(host, overwrite_targets, bkp)
        if rc != 0 and err.strip():
            print(f"warning: backup-existing: {err.strip()}", file=sys.stderr)
        else:
            print(f"backup of existing targets: {bkp}")

    core.run_remote(host, f"sudo -n mkdir -p {shlex.quote(target_root)}")
    for w in _apply(host, files_dir, valid, set_times):
        print(f"warning: {w}", file=sys.stderr)

    _verify_remote(host, recs)

    rj = os.path.join(runlog, "restore.json")
    rc_csv = os.path.join(runlog, "restore.csv")
    core.write_manifest_json(recs, rj)
    core.write_manifest_csv(recs, rc_csv, extra_columns=_RESTORE_CSV_COLUMNS,
                            extra_extractor=_restore_extractor)
    core.set_readonly(rj, rc_csv)

    stats = _compute_stats(recs)
    _print_summary(host, target_root, runlog, stats)
    return 2 if (stats["failed"] or stats["content_mismatch"] or stats["attr_mismatch"]) else 0


# --------------------------------------------------------------------------
# Вывод
# --------------------------------------------------------------------------

def _print_plan(recs: list[dict]) -> None:
    print(f"\nПлан (из restore.txt — только перечисленные объекты): {len(recs)}")
    for r in recs:
        s = r["source"]
        a = r["restore"]["action"] or "skip"
        owner = f"{s['owner'] or '?'}:{s['group'] or '?'}"
        perms = "-" if s["type"] == "symlink" else (s["permissions_octal"] or "----")
        print(f"  [{a:9}] {perms} {owner:>13} {r['restore']['target_path']}")
    counts = {"create": 0, "overwrite": 0, "skip": 0}
    for r in recs:
        counts[r["restore"]["action"] or "skip"] = counts.get(r["restore"]["action"] or "skip", 0) + 1
    print(f"  -> create={counts.get('create',0)} overwrite={counts.get('overwrite',0)} "
          f"skip={counts.get('skip',0)}")


def _compute_stats(recs: list[dict]) -> dict:
    by: dict[str, int] = {}
    for r in recs:
        by[r["restore"]["status"]] = by.get(r["restore"]["status"], 0) + 1
    return {
        "total": len(recs), "ok": by.get("ok", 0), "skipped": by.get("skipped", 0),
        "attr_mismatch": by.get("attr_mismatch", 0),
        "content_mismatch": by.get("content_mismatch", 0), "failed": by.get("failed", 0),
    }


def _print_summary(host: str, target_root: str, runlog: str, st: dict) -> None:
    line = "=" * 49
    sep = "-" * 49
    print()
    print(line)
    print(f"  Restore -> {host}:{target_root}")
    print(f"  Journal: {runlog}")
    print(sep)
    print(f"  Objects:          {st['total']}")
    print(f"    OK:             {st['ok']}")
    print(f"    Skipped:        {st['skipped']}")
    print(f"    Attr mismatch:  {st['attr_mismatch']}")
    print(f"    Content mismatch:{st['content_mismatch']}")
    print(f"    Failed:         {st['failed']}")
    print(line)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="putfile",
        description="Накатить сессию на удалённый хост (local -> remote). "
                    "Выбор и атрибуты — из restore.txt сессии, контент — из files/.")
    p.add_argument("session", help="локальная сессия (files/ + restore.txt + metadata/)")
    p.add_argument("hostname", nargs="?", default=None,
                   help="целевой хост (по умолчанию из session.json)")
    p.add_argument("--target-root", required=True,
                   help="корень назначения на remote (напр. / или /srv/restore)")
    p.add_argument("--dry-run", action="store_true", help="показать план без записи")
    p.add_argument("--yes", action="store_true", help="подтвердить реальное применение")
    p.add_argument("--backup-existing", action="store_true",
                   help="сохранить перезаписываемые цели до изменения")
    p.add_argument("--no-set-times", action="store_true", help="не восстанавливать mtime")
    return p


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    return run(a.session, a.hostname, a.target_root, a.dry_run, a.yes,
               a.backup_existing, set_times=not a.no_set_times)


if __name__ == "__main__":
    sys.exit(main())
