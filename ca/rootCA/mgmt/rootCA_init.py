#!/usr/bin/env python3
"""Выпуск корневого (root) сертификата CA. Самоподписанный.

Имя сертификата (CN) задаётся параметром --cn; оно используется как CN в
конфиге и как префикс имён создаваемых файлов. Если параметр не задан, имя
запрашивается интерактивно с предложением по умолчанию "root" (Enter — принять).

    python3 rootCA/mgmt/rootCA_init.py --cn root
"""
import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "lib"))

import ca_lib  # noqa: E402

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Выпуск корневого (root) сертификата CA.")
    parser.add_argument(
        "--cn",
        help="Имя сертификата (CN) — также префикс имён файлов. "
             "Если не задано, будет запрошено интерактивно (по умолчанию 'root').",
    )
    args = parser.parse_args()

    cn = ca_lib.sanitize_cn(args.cn) if args.cn else ca_lib.prompt_cn(default="root")

    ca_lib.guard(ca_lib.main_root, HERE / "openssl_rootCA.cnf", cn)
