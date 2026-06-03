"""diffile — дифференциальное сравнение и подтягивание изменений (remote -> local).

Реализация по wiki/todo/diffile.md. Берёт локальную baseline-сессию (вывод get),
идёт на хост, сравнивает текущее состояние с локальной копией, формирует отчёт
о расхождениях и подтягивает изменившиеся/новые файлы в новую diff-сессию.
Baseline не модифицируется.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys

try:
    from . import core, getfile
except ImportError:  # запуск как отдельный скрипт
    import core, getfile  # type: ignore

# поля метаданных, расхождение по которым => metadata_modified
_META_FIELDS = ["uid", "gid", "permissions_octal", "symlink_target"]

# дополнительные колонки CSV (поверх core.CSV_COLUMNS)
_DIFF_CSV_COLUMNS = ["diff_status", "baseline_md5", "remote_md5",
                     "changed_fields", "baseline_drift", "pulled"]


def _diff_extractor(rec: dict) -> dict:
    d = rec.get("diff", {})
    return {
        "diff_status": d.get("status"),
        "baseline_md5": d.get("baseline_md5"),
        "remote_md5": d.get("remote_md5"),
        "changed_fields": ";".join(d.get("changed_fields", []) or []),
        "baseline_drift": d.get("baseline_drift"),
        "pulled": d.get("pulled"),
    }


# --------------------------------------------------------------------------
# Загрузка baseline
# --------------------------------------------------------------------------

def _load_baseline(session_dir: str):
    meta = os.path.join(session_dir, "metadata")
    with open(os.path.join(meta, "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    with open(os.path.join(meta, "session.json"), encoding="utf-8") as f:
        session = json.load(f)
    return manifest, session


def _warn_if_writable(*paths: str) -> None:
    """Метаданные baseline сохраняются RO (0444). Если на них стоит бит записи —
    их могли изменить вручную; diff должен опираться на неизменные метаданные."""
    for p in paths:
        try:
            mode = os.stat(p).st_mode
        except OSError:
            continue
        if mode & 0o222:
            print(f"warning: metadata is writable (not read-only), may have been "
                  f"modified — diff trusts it as-is: {p}", file=sys.stderr)


def _baseline_local_md5(manifest: list[dict], files_dir: str):
    """Пересчитать MD5 локальных файлов baseline + отметить baseline_drift."""
    local_md5: dict[str, str | None] = {}
    drift: dict[str, bool] = {}
    for rec in manifest:
        s = rec["source"]
        if s["type"] != "regular_file":
            continue
        p = s["remote_path"]
        lp = os.path.join(files_dir, p.lstrip("/"))
        m = None
        if os.path.isfile(lp) and not os.path.islink(lp):
            try:
                m = core.read_local_md5(lp)
            except OSError:
                m = None
        local_md5[p] = m
        drift[p] = (m is not None and s["md5_remote"] is not None and m != s["md5_remote"])
    return local_md5, drift


# --------------------------------------------------------------------------
# Сравнение
# --------------------------------------------------------------------------

def _classify_diff(rec: dict, base_by_path: dict, base_md5: dict,
                   base_drift: dict, check_mtime: bool) -> None:
    s = rec["source"]
    p = s["remote_path"]
    diff = {
        "status": None,
        "baseline_md5": base_md5.get(p),
        "remote_md5": s["md5_remote"],
        "changed_fields": [],
        "baseline_drift": base_drift.get(p, False),
        "pulled": False,
    }
    rec["diff"] = diff

    if not s["metadata_complete"]:
        diff["status"] = "unreadable"
        return
    if p not in base_by_path:
        diff["status"] = "new_on_remote"
        return

    base = base_by_path[p]["source"]
    fields = _META_FIELDS + (["mtime_epoch"] if check_mtime else [])
    changed = [f for f in fields if s.get(f) != base.get(f)]
    content_diff = (s["type"] == "regular_file"
                    and s["md5_remote"] != base_md5.get(p))
    if content_diff:
        diff["changed_fields"] = ["md5_remote"] + changed
        diff["status"] = "content_modified"
    elif changed:
        diff["changed_fields"] = changed
        diff["status"] = "metadata_modified"
    else:
        diff["status"] = "unchanged"


# --------------------------------------------------------------------------
# Верификация подтянутого
# --------------------------------------------------------------------------

def _verify_pulled(rec: dict, files_dir: str, saved_epoch: int, saved_iso: str) -> None:
    s, d, v = rec["source"], rec["destination"], rec["verify"]
    lp = os.path.join(files_dir, s["remote_path"].lstrip("/"))
    d["local_path"] = lp
    d["in_payload"] = True
    d["saved_at_epoch"] = saved_epoch
    d["saved_at_iso"] = saved_iso
    t = s["type"]
    if t == "regular_file":
        if not os.path.isfile(lp) or os.path.islink(lp):
            v["status"] = "missing"
            return
        try:
            lm = core.read_local_md5(lp)
        except OSError as exc:
            v["status"] = "no_md5"
            v["error"] = f"local copy unreadable: {exc}"
            return
        v["md5_local"] = lm
        v["status"] = "ok" if lm == s["md5_remote"] else "md5_mismatch"
    elif t == "symlink":
        v["status"] = "present" if (os.path.islink(lp) and os.readlink(lp) == s["symlink_target"]) else "missing"
    else:
        v["status"] = "present" if os.path.lexists(lp) else "skipped"


# --------------------------------------------------------------------------
# Основной поток
# --------------------------------------------------------------------------

def run(baseline_session: str, host: str | None, label: str,
        base_path: str | None, filelist: str | None,
        pull: bool, check_mtime: bool) -> int:
    if not os.path.isdir(baseline_session):
        print(f"error: baseline session not found: {baseline_session}", file=sys.stderr)
        return 1
    try:
        baseline_manifest, baseline_sess = _load_baseline(baseline_session)
    except (OSError, ValueError) as exc:
        print(f"error: cannot read baseline metadata: {exc}", file=sys.stderr)
        return 1
    _meta = os.path.join(baseline_session, "metadata")
    _warn_if_writable(os.path.join(_meta, "manifest.json"),
                      os.path.join(_meta, "session.json"))

    host = host or baseline_sess.get("hostname")
    if not host:
        print("error: hostname not given and not in baseline session.json", file=sys.stderr)
        return 1
    filelist = filelist or baseline_sess.get("filelist")
    base_path = base_path or os.path.dirname(os.path.abspath(baseline_session.rstrip("/")))
    base_files = os.path.join(baseline_session, "files")

    base_by_path = {r["source"]["remote_path"]: r for r in baseline_manifest}
    base_md5, base_drift = _baseline_local_md5(baseline_manifest, base_files)

    # пути для повторного раскрытия
    if filelist and os.path.isfile(filelist):
        input_paths = getfile.read_filelist(filelist)
    else:
        input_paths = sorted(base_by_path)
        if filelist:
            print(f"warning: filelist {filelist} not found; re-expanding baseline paths",
                  file=sys.stderr)

    # diff-сессия
    sess_name = getfile.session_dirname(host, getfile._sanitize_label(label)) + "__diff"
    diff_session = os.path.join(base_path, sess_name)
    files_dir = os.path.join(diff_session, "files")
    meta_dir = os.path.join(diff_session, "metadata")
    os.makedirs(files_dir, exist_ok=True)
    os.makedirs(meta_dir, exist_ok=True)
    payload_name = sess_name + ".tar"
    payload_path = os.path.join(diff_session, payload_name)

    start_epoch, start_iso = core.utc_now()
    print(f"Diff session: {diff_session}")
    print(f"Baseline:     {baseline_session}")
    print(f"Host:         {host}")

    # текущее состояние remote
    try:
        current, not_found, enum_denied, other_errs = core.build_records(host, input_paths)
    except core.RemoteError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for line in other_errs:
        print(f"warning: {line}", file=sys.stderr)

    diff_records: dict[str, dict] = {}
    for p, rec in current.items():
        _classify_diff(rec, base_by_path, base_md5, base_drift, check_mtime)
        if p in enum_denied:
            rec["source"]["contents_enumerated"] = False
        diff_records[p] = rec

    # удалённые на remote (есть в baseline, нет в текущем)
    for p, base in base_by_path.items():
        if p not in diff_records:
            rec = copy.deepcopy(base)
            rec["diff"] = {"status": "deleted_on_remote", "baseline_md5": base_md5.get(p),
                           "remote_md5": None, "changed_fields": [],
                           "baseline_drift": base_drift.get(p, False), "pulled": False}
            rec["destination"] = {"local_path": None, "in_payload": False,
                                  "saved_at_epoch": None, "saved_at_iso": None}
            rec["verify"] = {"status": "skipped", "md5_local": None, "error": None}
            diff_records[p] = rec

    # подтягивание
    pull_paths = [p for p, rec in diff_records.items()
                  if rec["diff"]["status"] in ("content_modified", "new_on_remote")]
    if pull and pull_paths:
        rc, tar_err = core.transfer_payload(host, pull_paths, payload_path)
        if rc != 0 and tar_err.strip():
            print(f"warning: tar (remote): {tar_err.strip()}", file=sys.stderr)
        ec, ex_err = core.extract_payload(payload_path, files_dir)
        if ec != 0 and ex_err.strip():
            print(f"warning: tar (local extract): {ex_err.strip()}", file=sys.stderr)
        saved_epoch, saved_iso = core.utc_now()
        for p in pull_paths:
            diff_records[p]["diff"]["pulled"] = True
            _verify_pulled(diff_records[p], files_dir, saved_epoch, saved_iso)

    # запись
    manifest = [diff_records[p] for p in sorted(diff_records)]
    stats = _compute_stats(manifest)
    finish_epoch, finish_iso = core.utc_now()
    session = {
        "schema_version": core.SCHEMA_VERSION, "kind": "diff",
        "hostname": host, "label": label, "payload": payload_name,
        "baseline_session": os.path.abspath(baseline_session),
        "filelist": os.path.abspath(filelist) if filelist and os.path.isfile(filelist) else filelist,
        "started_at_iso": start_iso, "finished_at_iso": finish_iso, "stats": stats,
    }
    mj = os.path.join(meta_dir, "manifest.json")
    mc = os.path.join(meta_dir, "manifest.csv")
    sj = os.path.join(meta_dir, "session.json")
    rep = os.path.join(meta_dir, "diff_report.txt")
    core.write_manifest_json(manifest, mj)
    core.write_manifest_csv(manifest, mc, extra_columns=_DIFF_CSV_COLUMNS, extra_extractor=_diff_extractor)
    core.write_json(session, sj)
    _write_report(rep, manifest, baseline_session, host)
    core.set_readonly(mj, mc, sj, rep, payload_path)

    _print_summary(baseline_session, host, stats)
    return 2 if (stats["unreadable"] or stats["verify_mismatch"]) else 0


def _compute_stats(manifest: list[dict]) -> dict:
    by: dict[str, int] = {}
    pulled = vok = vmis = 0
    for rec in manifest:
        st = rec["diff"]["status"]
        by[st] = by.get(st, 0) + 1
        if rec["diff"]["pulled"]:
            pulled += 1
            if rec["verify"]["status"] == "ok":
                vok += 1
            elif rec["verify"]["status"] == "md5_mismatch":
                vmis += 1
    return {
        "compared": len(manifest),
        "unchanged": by.get("unchanged", 0),
        "content_modified": by.get("content_modified", 0),
        "metadata_modified": by.get("metadata_modified", 0),
        "new_on_remote": by.get("new_on_remote", 0),
        "deleted_on_remote": by.get("deleted_on_remote", 0),
        "unreadable": by.get("unreadable", 0),
        "pulled": pulled, "verify_ok": vok, "verify_mismatch": vmis,
    }


def _write_report(path: str, manifest: list[dict], baseline: str, host: str) -> None:
    order = ["content_modified", "new_on_remote", "deleted_on_remote",
             "metadata_modified", "unreadable"]
    groups: dict[str, list[str]] = {k: [] for k in order}
    for rec in manifest:
        st = rec["diff"]["status"]
        if st in groups:
            groups[st].append(rec["source"]["remote_path"])
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"Diff report\n  baseline: {baseline}\n  host: {host}\n\n")
        for k in order:
            f.write(f"[{k}] ({len(groups[k])})\n")
            for p in groups[k]:
                f.write(f"  {p}\n")
            f.write("\n")


def _print_summary(baseline: str, host: str, st: dict) -> None:
    line = "=" * 49
    sep = "-" * 49
    print()
    print(line)
    print(f"  Diff vs baseline: {os.path.basename(baseline.rstrip('/'))}")
    print(f"  Host: {host}")
    print(sep)
    print(f"  Compared:           {st['compared']}")
    print(f"    Unchanged:        {st['unchanged']}")
    print(f"    Content changed:  {st['content_modified']}   <- pulled")
    print(f"    Metadata changed: {st['metadata_modified']}")
    print(f"    New on remote:    {st['new_on_remote']}   <- pulled")
    print(f"    Deleted on remote:{st['deleted_on_remote']}")
    print(f"    Unreadable:       {st['unreadable']}")
    print(sep)
    print(f"  Pulled & verified:  {st['verify_ok']} / {st['pulled']}")
    print(line)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="diffile",
        description="Сравнить локальную копию с удалённой и подтянуть дельту (remote -> local).")
    p.add_argument("baseline_session", help="путь к локальной сессии getfile (baseline)")
    p.add_argument("hostname", nargs="?", default=None,
                   help="имя хоста (по умолчанию из baseline session.json)")
    p.add_argument("-m", "--message", default="", help="метка diff-сессии")
    p.add_argument("-p", "--path", default=None, help="базовая директория для diff-сессии")
    p.add_argument("-f", "--filelist", default=None,
                   help="список путей для повторного раскрытия (по умолчанию из baseline)")
    p.add_argument("--no-pull", action="store_true", help="только отчёт, без скачивания")
    p.add_argument("--check-mtime", action="store_true", help="учитывать mtime как расхождение")
    return p


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    return run(a.baseline_session, a.hostname, a.message, a.path, a.filelist,
               pull=not a.no_pull, check_mtime=a.check_mtime)


if __name__ == "__main__":
    sys.exit(main())
