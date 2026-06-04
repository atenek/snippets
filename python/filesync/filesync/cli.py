"""Единый вход набора filesync: подкоманды get | diff | put (см. wiki/todo/architecture.md).

Использование:
    python -m filesync get  <filelist> <hostname> [--prefix P] [--suffix S] [--exclude [FILE]] ...
    python -m filesync diff <baseline_session> [hostname] ...
    python -m filesync put  <session> [hostname] --target-root ROOT ...
"""

from __future__ import annotations

import sys

try:
    from . import getfile, diffile, putfile
except ImportError:  # запуск как отдельный скрипт
    import getfile, diffile, putfile  # type: ignore

USAGE = "usage: filesync {get|diff|put} ..."


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(USAGE)
        return 0 if argv else 1

    cmd, rest = argv[0], argv[1:]
    if cmd == "get":
        return getfile.main(rest)
    if cmd == "diff":
        return diffile.main(rest)
    if cmd == "put":
        return putfile.main(rest)
    print(f"error: unknown subcommand '{cmd}'\n{USAGE}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
