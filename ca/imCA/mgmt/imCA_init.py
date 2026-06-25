#!/usr/bin/env python3
"""Выпуск промежуточного (intermediate) сертификата CA.

При запуске интерактивно предлагает выбрать корневой сертификат для подписи.

Имя сертификата (CN) задаётся параметром --cn; оно используется как CN в
конфиге и как префикс имён создаваемых файлов. Если параметр не задан, имя
запрашивается интерактивно с предложением по умолчанию "im" (Enter — принять).

    python3 imCA/mgmt/imCA_init.py --cn im
"""
import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "lib"))

import ca_lib  # noqa: E402

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Выпуск промежуточного (intermediate) сертификата CA."
    )
    parser.add_argument(
        "--cn",
        help="Имя сертификата (CN) — также префикс имён файлов. "
             "Если не задано, будет запрошено интерактивно (по умолчанию 'im').",
    )
    args = parser.parse_args()

    cn = ca_lib.sanitize_cn(args.cn) if args.cn else ca_lib.prompt_cn(default="im")

    ca_lib.guard(ca_lib.main_im, HERE / "openssl_imCA.cnf", cn)
