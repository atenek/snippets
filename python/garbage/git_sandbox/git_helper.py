"""
    Git helper utilities — log, diff, compare, filter, view.
"""

import subprocess
from pathlib import Path
from hashlib import sha1 as s1

def log(n=10, path='.'):
    """Последние n коммитов в кратком формате."""
    r = subprocess.run(
        ['git', '-C', path, 'log', '--oneline', f'-{n}'],
        capture_output=True, text=True
    )
    return r.stdout

def diff(path='.', staged=False):
    """Изменения рабочего дерева (или индекса при staged=True)."""
    args = ['git', '-C', path, 'diff'] + (['--staged'] if staged else [])
    return subprocess.run(args, capture_output=True, text=True).stdout

def compare(ref1, ref2, path='.'):
    """Разница между двумя ревизиями."""
    return subprocess.run(
        ['git', '-C', path, 'diff', ref1, ref2],
        capture_output=True, text=True
    ).stdout

def grep(pattern, path='.'):
    """Коммиты с сообщением, совпадающим с шаблоном."""
    return subprocess.run(
        ['git', '-C', path, 'log', '--oneline', f'--grep={pattern}'],
        capture_output=True, text=True
    ).stdout

def view(ref='HEAD', path='.'):
    """Содержимое коммита."""
    return subprocess.run(
        ['git', '-C', path, 'show', ref],
        capture_output=True, text=True
    ).stdout

def win_view(ref='HEAD', path='.'):
    """Содержимое коммита с пословным diff."""
    return subprocess.run(
        ['git', '-C', path, 'show', ref, '--word-diff'],
        capture_output=True, text=True
    ).stdout

def check_commit_sha(ref='HEAD', path='.'):
    """Yield SHA-1 digests of commits reachable from ref."""
    r = subprocess.run(
        ['git', '-C', path, 'log', '--format=%H', ref],
        capture_output=True, text=True
    )
    for line in r.stdout.splitlines():
        if line.strip():
            yield s1(line.strip().encode()).digest()


def boxl_search_by_key():
    from getpass import getpass
    keyword = getpass('search key: ')
    matches = [
        ln for ln in boxl.read_text().splitlines()
        if keyword.lower() in ln.lower()
    ]
    for ln in matches[:10]:
        print(ln)
    return matches

if __name__ == "__main__":
    boxl = Path('data/dev_git.log')
    if boxl.is_file():
        boxl_search_by_key()
