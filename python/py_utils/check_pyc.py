#!/usr/bin/env python3
"""Проверяет, использует ли Python существующий .pyc или перекомпилирует его."""

import sys
import struct
import importlib.util
from datetime import datetime
from pathlib import Path


def _fmt_dt(ts: int) -> str:
    try:
        return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
    except (OSError, OverflowError):
        return '(неизвестно)'


def _row(cols: tuple, *values) -> str:
    parts = []
    for i, (v, w) in enumerate(zip(values, cols)):
        s = str(v)
        parts.append(f"{s:<{w}}" if w else s)
    return ''.join(parts)


def check_pyc(source_path: str) -> None:
    src = Path(source_path).resolve()

    if not src.exists():
        print(f"Ошибка: файл не найден: {source_path}")
        sys.exit(1)
    if src.suffix != '.py':
        print(f"Ошибка: ожидается .py файл, получен: {source_path}")
        sys.exit(1)

    pyc_path = Path(importlib.util.cache_from_source(str(src)))

    print(f"Источник : {src}")
    print(f"Кеш      : {pyc_path}")
    print()

    if not pyc_path.exists():
        print("Вывод: .pyc файл отсутствует — Python выполнит компиляцию.")
        return

    with open(pyc_path, 'rb') as f:
        header = f.read(16)

    if len(header) < 16:
        print(f"Ошибка: .pyc заголовок слишком мал ({len(header)} < 16 байт).")
        print("Вывод: .pyc повреждён — Python выполнит перекомпиляцию.")
        return

    pyc_magic     = header[0:4]
    flags         = struct.unpack('<I', header[4:8])[0]
    hash_based    = bool(flags & 0x1)
    current_magic = importlib.util.MAGIC_NUMBER
    src_stat      = src.stat()

    COLS = (24, 24, 24, 0)
    sep  = '-' * 82

    print(_row(COLS, 'Параметр', 'В .pyc', 'В .py (факт)', 'Результат'))
    print(sep)

    all_ok = True

    # --- Magic number ---
    magic_ok = pyc_magic == current_magic
    all_ok   = all_ok and magic_ok
    print(_row(COLS,
        'magic number',
        pyc_magic.hex(),
        current_magic.hex(),
        'OK' if magic_ok else 'НЕСОВПАДЕНИЕ',
    ))

    # --- Flags / режим валидации ---
    print(_row(COLS,
        'flags',
        hex(flags),
        '—',
        'hash-based' if hash_based else 'mtime-based',
    ))

    if hash_based:
        # Hash-based: Python 3.8+, создаётся явно через py_compile с CHECKED_HASH
        pyc_hash = header[8:16]
        try:
            import _imp
            with open(src, 'rb') as f:
                src_data = f.read()
            raw_magic = int.from_bytes(current_magic, 'little')
            src_hash  = _imp.source_hash(raw_magic, src_data)
            hash_ok   = pyc_hash == src_hash
            all_ok    = all_ok and hash_ok
            print(_row(COLS,
                'source hash',
                pyc_hash.hex(),
                src_hash.hex(),
                'OK' if hash_ok else 'НЕСОВПАДЕНИЕ',
            ))
        except Exception as e:
            all_ok = False
            print(_row(COLS, 'source hash', pyc_hash.hex(), '(ошибка вычисления)', str(e)))
    else:
        # Mtime-based: стандартный режим
        pyc_mtime = struct.unpack('<I', header[8:12])[0]
        pyc_size  = struct.unpack('<I', header[12:16])[0]
        src_mtime = int(src_stat.st_mtime) & 0xFFFFFFFF
        src_size  = src_stat.st_size & 0xFFFFFFFF

        mtime_ok = pyc_mtime == src_mtime
        size_ok  = pyc_size  == src_size
        all_ok   = all_ok and mtime_ok and size_ok

        print(_row(COLS,
            'mtime (сек)',
            str(pyc_mtime),
            str(src_mtime),
            'OK' if mtime_ok else 'НЕСОВПАДЕНИЕ',
        ))
        print(_row(COLS,
            '',
            f"({_fmt_dt(pyc_mtime)})",
            f"({_fmt_dt(src_mtime)})",
            '',
        ))
        print(_row(COLS,
            'size (байт)',
            str(pyc_size),
            str(src_size),
            'OK' if size_ok else 'НЕСОВПАДЕНИЕ',
        ))

    print()
    if all_ok:
        print("Вывод: все параметры совпадают — Python ИСПОЛЬЗУЕТ существующий .pyc.")
    else:
        print("Вывод: параметры не совпадают — Python ПЕРЕКОМПИЛИРУЕТ .pyc.")


if __name__ == '__main__':
    if len(sys.argv) != 2:
        script = Path(sys.argv[0]).name
        print(f"Использование: python3 {script} <path_to_source.py>")
        sys.exit(1)
    check_pyc(sys.argv[1])
