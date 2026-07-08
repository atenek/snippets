#!/usr/bin/env python3
"""Выпуск конечного (end-entity) сертификата.

При запуске интерактивно предлагает выбрать шаблон конфигурации
(*.cnf рядом со скриптом: клиентский / серверный / клиент-серверный) и
промежуточный сертификат для подписи.

Имя сертификата (CN) задаётся параметром --cn; оно используется как CN в
конфиге и как префикс имён создаваемых файлов. Если параметр не задан,
имя запрашивается интерактивно в начале работы (до запуска редактора).

Криптопрофиль задаётся параметром --profile (classic — по умолчанию;
gost-256 / gost-512 — ГОСТ Р 34.10-2012 через gost-engine). Если параметр
не задан и запуск интерактивный, профиль предлагается меню. Шаблоны и
подписант предлагаются только выбранного профиля.

    python3 endentity/mgmt/endentity_init.py --cn alex
    python3 endentity/mgmt/endentity_init.py --cn galex --profile gost-256
"""
import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "lib"))

import ca_lib  # noqa: E402

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Выпуск конечного (end-entity) сертификата.")
    parser.add_argument(
        "--cn",
        help="Имя сертификата (CN) — также префикс имён файлов. "
             "Если не задано, будет запрошено интерактивно.",
    )
    parser.add_argument(
        "--profile", choices=ca_lib.PROFILE_NAMES,
        help="Криптопрофиль (по умолчанию classic; без параметра при "
             "интерактивном запуске предлагается меню).",
    )
    parser.add_argument(
        "--paramset",
        help="Paramset ГОСТ-ключа (только с gost-профилем; по умолчанию A).",
    )
    args = parser.parse_args()

    profile = ca_lib.resolve_profile(args.profile, args.paramset)
    # CN либо из параметра, либо запрашиваем у пользователя до запуска редактора.
    cn = ca_lib.sanitize_cn(args.cn) if args.cn else ca_lib.prompt_cn()

    # main_ee сам найдёт *.cnf выбранного профиля в HERE и предложит выбрать шаблон.
    ca_lib.guard(ca_lib.main_ee, HERE, cn, profile)
