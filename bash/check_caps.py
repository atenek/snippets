#!/usr/bin/env python3
"""
check_caps.py — проверка capabilities дочерних процессов заданного PID.

Использование:
  python3 check_caps.py <root_pid> <cap1,cap2,...>
  python3 check_caps.py <root_pid> <cap1,cap2,...> [OPTIONS]

Опции:
  --check  eff|prm|inh|bnd|amb  какой набор проверять (default: eff)
  --exact                        точное совпадение (не больше и не меньше)
  --only-fail                    показывать только несоответствия
  --depth  N                     глубина обхода дерева (default: без ограничений)

Примеры:
  # Проверить что все дочерние процессы PID 1234 имеют cap_net_raw и cap_net_admin
  python3 check_caps.py 1234 cap_net_raw,cap_net_admin

  # Точное совпадение — ровно эти capability и ничего лишнего
  python3 check_caps.py 1234 cap_net_raw,cap_net_admin --exact

  # Проверять Permitted вместо Effective
  python3 check_caps.py 1234 cap_sys_admin --check prm

  # Только первый уровень дочерних процессов
  python3 check_caps.py 1234 cap_net_raw --depth 1

Формат вывода:
  PID=1234  name=nginx  eff=cap_net_raw,cap_net_admin  missing=—  extra=—  => Ok
  PID=1235  name=worker  eff=cap_net_raw  missing=cap_net_admin  extra=—   => Fail
"""

import os
import re
import sys
import argparse
from typing import Dict, List, Optional, Set, Tuple


# ─────────────────────────────────────────────
# Таблица capabilities (Linux kernel 5.x / 6.x)
# ─────────────────────────────────────────────

CAP_NAMES: Dict[int, str] = {
    0:  'cap_chown',
    1:  'cap_dac_override',
    2:  'cap_dac_read_search',
    3:  'cap_fowner',
    4:  'cap_fsetid',
    5:  'cap_kill',
    6:  'cap_setgid',
    7:  'cap_setuid',
    8:  'cap_setpcap',
    9:  'cap_linux_immutable',
    10: 'cap_net_bind_service',
    11: 'cap_net_broadcast',
    12: 'cap_net_admin',
    13: 'cap_net_raw',
    14: 'cap_ipc_lock',
    15: 'cap_ipc_owner',
    16: 'cap_sys_module',
    17: 'cap_sys_rawio',
    18: 'cap_sys_chroot',
    19: 'cap_sys_ptrace',
    20: 'cap_sys_pacct',
    21: 'cap_sys_admin',
    22: 'cap_sys_boot',
    23: 'cap_sys_nice',
    24: 'cap_sys_resource',
    25: 'cap_sys_time',
    26: 'cap_sys_tty_config',
    27: 'cap_mknod',
    28: 'cap_lease',
    29: 'cap_audit_write',
    30: 'cap_audit_control',
    31: 'cap_setfcap',
    32: 'cap_mac_override',
    33: 'cap_mac_admin',
    34: 'cap_syslog',
    35: 'cap_wake_alarm',
    36: 'cap_block_suspend',
    37: 'cap_audit_read',
    38: 'cap_perfmon',
    39: 'cap_bpf',
    40: 'cap_checkpoint_restore',
}

CAP_BY_NAME: Dict[str, int] = {v: k for k, v in CAP_NAMES.items()}


# ─────────────────────────────────────────────
# Работа с capability масками
# ─────────────────────────────────────────────

def decode_mask(hex_str: str) -> Set[str]:
    """Hex-маску -> множество имён capability."""
    try:
        mask = int(hex_str, 16)
    except ValueError:
        return set()
    return {name for bit, name in CAP_NAMES.items() if mask & (1 << bit)}


def normalize_cap(name: str) -> Optional[str]:
    """Нормализует имя: net_raw / cap_net_raw / CAP_NET_RAW -> cap_net_raw."""
    name = name.lower().strip()
    if not name.startswith('cap_'):
        name = 'cap_' + name
    return name if name in CAP_BY_NAME else None


def parse_cap_list(raw: str) -> Tuple[List[str], List[str]]:
    """
    Парсит строку вида 'cap_net_raw,net_admin,cap_sys_admin'.
    Возвращает (valid_caps, unknown_caps).
    """
    valid, unknown = [], []
    for token in re.split(r'[,\s]+', raw):
        if not token:
            continue
        n = normalize_cap(token)
        if n:
            valid.append(n)
        else:
            unknown.append(token)
    return valid, unknown


# ─────────────────────────────────────────────
# Чтение /proc
# ─────────────────────────────────────────────

CAP_FIELD = {
    'eff': 'CapEff',
    'prm': 'CapPrm',
    'inh': 'CapInh',
    'bnd': 'CapBnd',
    'amb': 'CapAmb',
}


def read_proc_status(pid: int) -> Optional[Dict[str, str]]:
    """Читает /proc/<pid>/status, возвращает словарь полей."""
    try:
        with open(f'/proc/{pid}/status', encoding='utf-8', errors='replace') as f:
            info = {}
            for line in f:
                m = re.match(r'(\w+):\s+(.+)', line)
                if m:
                    info[m.group(1)] = m.group(2).strip()
        return info
    except (FileNotFoundError, PermissionError):
        return None


def read_cmdline(pid: int) -> str:
    """Читает /proc/<pid>/cmdline, возвращает строку команды."""
    try:
        with open(f'/proc/{pid}/cmdline', 'rb') as f:
            raw = f.read()
        # null-байты — разделители аргументов
        return raw.replace(b'\x00', b' ').decode('utf-8', errors='replace').strip()
    except (FileNotFoundError, PermissionError):
        return ''


def get_all_procs() -> Dict[int, Dict[str, str]]:
    """Снимок всех процессов из /proc."""
    procs = {}
    try:
        entries = list(os.scandir('/proc'))
    except PermissionError:
        return procs
    for entry in entries:
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        info = read_proc_status(pid)
        if info is None:
            continue
        info['_cmdline'] = read_cmdline(pid) or info.get('Name', f'pid{pid}')
        procs[pid] = info
    return procs


def get_descendants(root_pid: int, procs: Dict[int, Dict],
                    max_depth: Optional[int] = None) -> List[Tuple[int, int]]:
    """
    BFS-обход дерева дочерних процессов.
    Возвращает список (pid, depth).
    """
    result = []
    # queue: (pid, depth)
    queue = [(root_pid, 0)]
    visited: Set[int] = {root_pid}

    while queue:
        current, depth = queue.pop(0)
        if max_depth is not None and depth >= max_depth:
            continue
        for pid, info in procs.items():
            if pid in visited:
                continue
            if info.get('PPid') == str(current):
                visited.add(pid)
                result.append((pid, depth + 1))
                queue.append((pid, depth + 1))

    return result


# ─────────────────────────────────────────────
# Сравнение и форматирование
# ─────────────────────────────────────────────

def check_process(pid: int, info: Dict[str, str],
                  expected: Set[str], cap_field: str,
                  exact: bool) -> Dict:
    """Сравнивает фактические capabilities процесса с ожидаемыми."""
    hex_val = info.get(cap_field, '0000000000000000')
    actual  = decode_mask(hex_val)

    missing = expected - actual          # ожидали, но нет
    extra   = actual - expected if exact else set()  # лишние (только при --exact)
    ok      = not missing and not extra

    return {
        'pid':     pid,
        'name':    info.get('Name', f'pid{pid}'),
        'cmdline': info.get('_cmdline', ''),
        'ppid':    info.get('PPid', '?'),
        'hex':     hex_val,
        'actual':  actual,
        'missing': missing,
        'extra':   extra,
        'ok':      ok,
    }


def format_caps(caps: Set[str]) -> str:
    if not caps:
        return '—'
    return ','.join(sorted(caps))


def format_result(r: Dict, depth: int, cap_set_name: str) -> str:
    indent = '  ' * depth
    status = 'Ok' if r['ok'] else 'Fail'

    # Короткое имя набора
    label = cap_set_name.upper()

    line = (
        f"{indent}PID={r['pid']}  ppid={r['ppid']}  name={r['name']}\n"
        f"{indent}  cmd     : {r['cmdline'][:120]}\n"
        f"{indent}  {label}(hex) : {r['hex']}\n"
        f"{indent}  {label}(dec) : {format_caps(r['actual'])}\n"
        f"{indent}  missing : {format_caps(r['missing'])}\n"
        f"{indent}  extra   : {format_caps(r['extra'])}\n"
        f"{indent}  => {status}"
    )
    return line


# ─────────────────────────────────────────────
# Точка входа
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Проверка capabilities дочерних процессов',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('root_pid', type=int,
                        help='PID корневого процесса')
    parser.add_argument('capabilities',
                        help='Ожидаемые capability через запятую: cap_net_raw,cap_net_admin')
    parser.add_argument('--check', choices=['eff', 'prm', 'inh', 'bnd', 'amb'],
                        default='eff',
                        help='Какой набор проверять (default: eff = CapEff)')
    parser.add_argument('--exact', action='store_true',
                        help='Точное совпадение — запрещены лишние capabilities')
    parser.add_argument('--only-fail', action='store_true',
                        help='Показывать только несоответствия')
    parser.add_argument('--depth', type=int, default=None,
                        help='Максимальная глубина обхода дерева (default: без ограничений)')
    args = parser.parse_args()

    # Парсим ожидаемые capability
    expected_list, unknown = parse_cap_list(args.capabilities)
    if unknown:
        print(f"WARN: неизвестные capability проигнорированы: {', '.join(unknown)}",
              file=sys.stderr)
    if not expected_list:
        print("ERROR: не указано ни одной известной capability", file=sys.stderr)
        sys.exit(1)

    expected = set(expected_list)
    cap_field = CAP_FIELD[args.check]

    print(f"Root PID    : {args.root_pid}")
    print(f"Check set   : {args.check.upper()} ({cap_field})")
    print(f"Expected    : {format_caps(expected)}")
    print(f"Mode        : {'exact' if args.exact else 'subset (missing only)'}")
    print(f"Max depth   : {args.depth if args.depth else 'unlimited'}")
    print('─' * 70)

    # Проверяем что root_pid существует
    procs = get_all_procs()
    if args.root_pid not in procs:
        print(f"ERROR: PID {args.root_pid} не найден в /proc", file=sys.stderr)
        sys.exit(1)

    # Обходим дерево
    descendants = get_descendants(args.root_pid, procs, max_depth=args.depth)

    if not descendants:
        print(f"У процесса PID={args.root_pid} нет дочерних процессов.")
        sys.exit(0)

    any_fail = False
    total = 0
    fail_count = 0

    for pid, depth in descendants:
        info = procs.get(pid)
        if info is None:
            # Процесс исчез пока мы работали
            continue

        total += 1
        result = check_process(pid, info, expected, cap_field, args.exact)
        if not result['ok']:
            any_fail = True
            fail_count += 1

        if not args.only_fail or not result['ok']:
            print(format_result(result, depth - 1, args.check))
            print()

    print('─' * 70)
    print(f"Итого: {total} процессов, Ok: {total - fail_count}, Fail: {fail_count}")

    sys.exit(1 if any_fail else 0)


if __name__ == '__main__':
    main()
