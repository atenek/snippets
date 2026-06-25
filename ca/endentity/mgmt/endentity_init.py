#!/usr/bin/env python3
"""Выпуск конечного (end-entity) сертификата.

При запуске интерактивно предлагает выбрать промежуточный сертификат для подписи.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "lib"))

import ca_lib  # noqa: E402

if __name__ == "__main__":
    ca_lib.guard(ca_lib.main_ee, HERE / "openssl_endentity.cnf")
