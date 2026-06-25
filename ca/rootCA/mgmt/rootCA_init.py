#!/usr/bin/env python3
"""Выпуск корневого (root) сертификата CA. Самоподписанный."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "lib"))

import ca_lib  # noqa: E402

if __name__ == "__main__":
    ca_lib.guard(ca_lib.main_root, HERE / "openssl_rootCA.cnf")
