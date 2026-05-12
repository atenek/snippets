#!/usr/bin/env python3
"""
check_sudo.py — проверка sudo-привилегий по файлу ожидаемых правил.

Формат входного файла:
  # Комментарии игнорируются
  user1,user2,%group  HOST=(runas) NOPASSWD: /usr/bin/cmd1, /usr/bin/cmd2
  username3           ALL=(ALL)    PASSWD:   /usr/bin/apt
  username4           ALL=(ALL)    NOPASSWD: ALL

Группы указываются с префиксом %, как в sudoers.

Использование:
  python3 check_sudo.py <input_file>
  python3 check_sudo.py <input_file> --only-fail   # показывать только несоответствия

cat /etc/sudoers
cat /etc/sudoers.d/*

"""

import re
import sys
import subprocess
import argparse
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


# ─────────────────────────────────────────────
# Структуры данных
# ─────────────────────────────────────────────

@dataclass
class SudoRule:
    runas: str
    nopasswd: bool
    commands: List[str]

@dataclass
class ExpectedEntry:
    raw_line: str
    line_no: int
    users: List[str]          # может содержать %group
    host: str
    runas: str
    nopasswd: bool
    commands: List[str]

@dataclass
class CmdResult:
    command: str
    status: str               # Ok | Fail | MISSING
    actual_rule: Optional[SudoRule] = None

@dataclass
class UserResult:
    user: str
    expected: ExpectedEntry
    found_in_sudo: bool       # False = sudo -l -U вернул ошибку / пользователь не найден
    nopasswd_ok: Optional[bool] = None
    runas_ok: Optional[bool] = None
    cmd_results: List[CmdResult] = field(default_factory=list)


# ─────────────────────────────────────────────
# Парсинг входного файла
# ─────────────────────────────────────────────

INPUT_RE = re.compile(
    r'^(?P<users>\S+)'               # user1,user2,%group
    r'\s+(?P<host>[\w.\-]+)'         # ALL или hostname
    r'=\((?P<runas>[^)]+)\)'         # =(runas)
    r'\s+(?P<passwd>NOPASSWD:|PASSWD:)'  # NOPASSWD: / PASSWD:
    r'\s*(?P<commands>.+)$',         # команды через запятую
    re.IGNORECASE
)

def parse_input_file(path: str) -> List[ExpectedEntry]:
    entries = []
    with open(path, encoding='utf-8') as fh:
        for line_no, raw in enumerate(fh, 1):
            line = raw.strip()
            if not line or line.startswith('#'):
                continue
            m = INPUT_RE.match(line)
            if not m:
                print(f"WARN line {line_no}: не удалось распарсить: {line!r}", file=sys.stderr)
                continue
            users    = [u.strip() for u in m.group('users').split(',')]
            host     = m.group('host')
            runas    = m.group('runas').strip()
            nopasswd = m.group('passwd').upper().startswith('NOPASSWD')
            commands = [c.strip() for c in m.group('commands').split(',') if c.strip()]
            entries.append(ExpectedEntry(
                raw_line=line, line_no=line_no,
                users=users, host=host, runas=runas,
                nopasswd=nopasswd, commands=commands,
            ))
    return entries


# ─────────────────────────────────────────────
# Получение реальных sudo-правил
# ─────────────────────────────────────────────

RULE_RE = re.compile(
    r'^\((?P<runas>[^)]+)\)\s+(?P<passwd>NOPASSWD:\s*|PASSWD:\s*)?(?P<cmds>.+)$'
)

def get_actual_rules(user: str) -> Tuple[bool, List[SudoRule]]:
    """
    Запускает sudo -l -U <user> и парсит вывод.
    Для групп (%group) запускает getent group и итерирует по членам.
    Возвращает (success, rules).
    """
    try:
        result = subprocess.run(
            ['sudo', '-l', '-U', user],
            capture_output=True, text=True
        )
    except FileNotFoundError:
        print("ERROR: sudo не найден в PATH", file=sys.stderr)
        sys.exit(1)

    # Пользователь не найден или не имеет sudo
    if result.returncode != 0:
        return False, []
    if 'not allowed to run sudo' in result.stdout or 'not allowed to sudo' in result.stdout:
        return True, []   # найден, но прав нет

    rules = []
    in_rules = False
    for line in result.stdout.splitlines():
        if 'may run the following' in line:
            in_rules = True
            continue
        if not in_rules:
            continue
        stripped = line.strip()
        if not stripped:
            continue
        m = RULE_RE.match(stripped)
        if m:
            marker   = m.group('passwd') or ''
            nopasswd = 'NOPASSWD' in marker.upper()
            cmds     = [c.strip() for c in m.group('cmds').split(',') if c.strip()]
            rules.append(SudoRule(
                runas=m.group('runas').strip(),
                nopasswd=nopasswd,
                commands=cmds,
            ))
    return True, rules


def get_group_members(group: str) -> List[str]:
    """Возвращает список пользователей группы через getent."""
    group = group.lstrip('%')
    try:
        result = subprocess.run(
            ['getent', 'group', group],
            capture_output=True, text=True
        )
        if result.returncode == 0 and result.stdout.strip():
            # формат: groupname:x:gid:user1,user2,...
            parts = result.stdout.strip().split(':')
            if len(parts) >= 4 and parts[3]:
                return parts[3].split(',')
    except FileNotFoundError:
        pass
    return []


# ─────────────────────────────────────────────
# Логика сравнения
# ─────────────────────────────────────────────

def runas_match(actual: str, expected: str) -> bool:
    """
    Сравнивает runas. ALL с любой стороны = совпадение.
    (ALL : ALL) — берём часть до двоеточия.
    """
    def primary(s):
        return s.split(':')[0].strip()

    a, e = primary(actual), primary(expected)
    return 'ALL' in (a, e) or a == e


def command_covered(cmd: str, rules: List[SudoRule]) -> Tuple[bool, Optional[SudoRule]]:
    """Ищет правило, которое покрывает данную команду."""
    for rule in rules:
        if 'ALL' in rule.commands or cmd in rule.commands:
            return True, rule
    return False, None


def check_entry_for_user(user: str, entry: ExpectedEntry) -> UserResult:
    found, actual_rules = get_actual_rules(user)
    res = UserResult(user=user, expected=entry, found_in_sudo=found)

    if not found:
        return res

    # Для каждой ожидаемой команды ищем покрывающее правило
    for cmd in entry.commands:
        covered, matching_rule = command_covered(cmd, actual_rules)
        if not covered:
            res.cmd_results.append(CmdResult(command=cmd, status='MISSING'))
            continue

        r_ok = runas_match(matching_rule.runas, entry.runas)
        n_ok = matching_rule.nopasswd == entry.nopasswd
        ok   = r_ok and n_ok
        res.cmd_results.append(CmdResult(
            command=cmd,
            status='Ok' if ok else 'Fail',
            actual_rule=matching_rule,
        ))

    return res


# ─────────────────────────────────────────────
# Форматирование вывода
# ─────────────────────────────────────────────

def format_result(res: UserResult) -> Optional[str]:
    user     = res.user
    expected = res.expected

    exp_np   = 'NOPASSWD' if expected.nopasswd else 'PASSWD'
    exp_host = expected.host
    exp_run  = expected.runas

    if not res.found_in_sudo:
        return (
            f"{user}  {exp_host}=({exp_run}) {exp_np}: "
            + ', '.join(expected.commands)
            + "  => USER NOT FOUND / sudo unavailable"
        )

    # Собираем итоговую строку по командам
    cmd_parts = []
    overall_statuses = []

    for cr in res.cmd_results:
        if cr.status == 'MISSING':
            cmd_parts.append(f"{cr.command}[MISSING]")
            overall_statuses.append('Fail')
        elif cr.status == 'Fail' and cr.actual_rule:
            act_np  = 'NOPASSWD' if cr.actual_rule.nopasswd else 'PASSWD'
            act_run = cr.actual_rule.runas
            # Разбираем что именно не так
            r_ok = runas_match(act_run, exp_run)
            n_ok = cr.actual_rule.nopasswd == expected.nopasswd
            diff = []
            if not r_ok:
                diff.append(f"runas={act_run}(expected={exp_run})")
            if not n_ok:
                diff.append(f"{act_np}(expected={exp_np})")
            cmd_parts.append(f"{cr.command}[Fail: {', '.join(diff)}]")
            overall_statuses.append('Fail')
        else:
            cmd_parts.append(f"{cr.command}[Ok]")
            overall_statuses.append('Ok')

    verdict = ', '.join(overall_statuses)
    return (
        f"{user}  {exp_host}=({exp_run}) {exp_np}: "
        + ', '.join(cmd_parts)
        + f"  => {verdict}"
    )


# ─────────────────────────────────────────────
# Точка входа
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Проверка sudo-привилегий по файлу ожидаемых правил'
    )
    parser.add_argument('input_file', help='Файл с ожидаемыми правилами')
    parser.add_argument(
        '--only-fail', action='store_true',
        help='Показывать только строки с несоответствиями'
    )
    args = parser.parse_args()

    entries = parse_input_file(args.input_file)
    if not entries:
        print("Нет правил для проверки.", file=sys.stderr)
        sys.exit(1)

    any_fail = False

    for entry in entries:
        for user in entry.users:
            # Группа — проверяем через членов группы
            if user.startswith('%'):
                members = get_group_members(user)
                if not members:
                    line = (
                        f"{user}  {entry.host}=({entry.runas}) "
                        f"{'NOPASSWD' if entry.nopasswd else 'PASSWD'}: "
                        + ', '.join(entry.commands)
                        + "  => GROUP NOT FOUND or EMPTY"
                    )
                    print(line)
                    any_fail = True
                    continue
                for member in members:
                    res  = check_entry_for_user(member, entry)
                    line = format_result(res)
                    if line is None:
                        continue
                    has_fail = 'Fail' in line or 'MISSING' in line or 'NOT FOUND' in line
                    if has_fail:
                        any_fail = True
                    if not args.only_fail or has_fail:
                        print(line)
            else:
                res  = check_entry_for_user(user, entry)
                line = format_result(res)
                if line is None:
                    continue
                has_fail = 'Fail' in line or 'MISSING' in line or 'NOT FOUND' in line
                if has_fail:
                    any_fail = True
                if not args.only_fail or has_fail:
                    print(line)

    sys.exit(1 if any_fail else 0)


if __name__ == '__main__':
    main()
