"""Общая библиотека для helper-скриптов работы с сертификатами.

Это тонкая обёртка над внешним вызовом `openssl`: она готовит каталоги-хранилища,
рендерит конфиг openssl (без sed, обычной подстановкой плейсхолдеров), даёт выбрать
подписывающий сертификат и собирает корректные параметры для вызова openssl.

Иерархия:

    certificates/
        root/root_cert/          # самоподписанные корневые серты
        im/im_cert/              # промежуточные серты (подписаны выбранным root)
        ee/endentity_cert/       # конечные серты (подписаны выбранным im)

Каждый каталог CA содержит стандартную структуру БД openssl `ca`
(certs/ crl/ csr/ newcerts/ private/ index.txt serial crlnumber).
"""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Корень проекта: lib/ -> <project>
PROJECT_ROOT = Path(__file__).resolve().parents[1]
CERT_BASE = PROJECT_ROOT / "certificates"

ROOT_DIR = CERT_BASE / "root" / "root_cert"
IM_DIR = CERT_BASE / "im" / "im_cert"
EE_DIR = CERT_BASE / "ee" / "endentity_cert"

ROOT_PREFIX = "root_cert"
IM_PREFIX = "im_cert"
EE_PREFIX = "endentity_cert"


# --------------------------------------------------------------------------- #
#  Низкоуровневые помощники
# --------------------------------------------------------------------------- #
def banner(text: str) -> None:
    print(f"\n====== {text} ======\n", flush=True)


def run(cmd) -> subprocess.CompletedProcess:
    """Запустить внешнюю команду, унаследовав stdin/stdout (для интерактива openssl)."""
    printable = " ".join(str(c) for c in cmd)
    print(f"$ {printable}", flush=True)
    return subprocess.run([str(c) for c in cmd], check=True)


def die(msg: str) -> "NoReturn":  # noqa: F821
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


# --------------------------------------------------------------------------- #
#  Инициализация хранилища CA
# --------------------------------------------------------------------------- #
def ensure_ca_dirs(base: Path) -> None:
    """Создать структуру каталогов CA (идемпотентно)."""
    for sub in ("certs", "crl", "csr", "newcerts", "private"):
        (base / sub).mkdir(parents=True, exist_ok=True)
    os.chmod(base / "private", 0o700)


def init_ca_db(base: Path) -> None:
    """Инициализировать БД openssl `ca`, если её ещё нет.

    Дальше index.txt / serial / crlnumber полностью ведёт сам `openssl ca` —
    вручную мы их не трогаем.
    """
    index = base / "index.txt"
    if not index.exists():
        print("Создаю новую базу CA...")
        index.touch()
        (base / "serial").write_text("1000\n")
        (base / "crlnumber").write_text("1000\n")
    # unique_subject=no — иначе openssl не даст переподписать серт с тем же subject.
    attr = base / "index.txt.attr"
    if not attr.exists():
        attr.write_text("unique_subject = no\n")


# --------------------------------------------------------------------------- #
#  Нумерация выпускаемых сертификатов (независима от serial у openssl ca)
# --------------------------------------------------------------------------- #
def next_index(certs_dir: Path, prefix: str) -> tuple[int, str]:
    """Следующий порядковый номер по уже существующим certs/<prefix>-NN.crt."""
    highest = 0
    pat = re.compile(rf"^{re.escape(prefix)}-(\d+)\.crt$")
    if certs_dir.exists():
        for f in certs_dir.iterdir():
            m = pat.match(f.name)
            if m:
                highest = max(highest, int(m.group(1)))
    nxt = highest + 1
    return nxt, f"{nxt:02d}"


def index_of(cert_path: Path, prefix: str) -> str:
    """Извлечь NN из имени <prefix>-NN.crt."""
    m = re.search(rf"{re.escape(prefix)}-(\d+)\.crt$", cert_path.name)
    return m.group(1) if m else "00"


# --------------------------------------------------------------------------- #
#  Конфиг openssl: рендеринг шаблона без sed
# --------------------------------------------------------------------------- #
def render_config(template: Path, dest: Path, mapping: dict) -> None:
    """Скопировать шаблон .cnf, подставив плейсхолдеры @@KEY@@ значениями mapping."""
    if not template.exists():
        die(f"Не найден шаблон конфигурации: {template}")
    text = template.read_text()
    for key, value in mapping.items():
        text = text.replace(f"@@{key}@@", str(value))
    leftover = re.findall(r"@@[A-Z_]+@@", text)
    if leftover:
        die(f"В конфиге остались незаполненные плейсхолдеры: {sorted(set(leftover))}")
    dest.write_text(text)
    print(f"Конфиг подготовлен: {dest}")


def edit_config(path: Path) -> None:
    """Остановиться и дать пользователю отредактировать конфиг (vim / $EDITOR)."""
    editor = os.environ.get("EDITOR", "vim")
    if shutil.which(editor) is None:
        print(f"(!) Редактор '{editor}' не найден — пропускаю ручную правку {path}")
        return
    print(f"\n>>> Открываю {path} в {editor} для проверки/правки...")
    subprocess.run([editor, str(path)], check=True)


# --------------------------------------------------------------------------- #
#  Выбор шаблона конфигурации
# --------------------------------------------------------------------------- #
def _template_hint(template: Path) -> str:
    """Первая содержательная строка-комментарий шаблона как краткое описание."""
    try:
        for line in template.read_text().splitlines():
            s = line.strip()
            if s.startswith("#") and len(s) > 1:
                return s.lstrip("#").strip()
    except OSError:
        pass
    return ""


def choose_template(mgmt_dir: Path, pattern: str = "*.cnf") -> Path:
    """Показать список шаблонов *.cnf рядом со скриптом и дать выбрать один.

    Возвращает путь к выбранному шаблону. Падает, если шаблонов нет.
    Дальше выбранный шаблон копируется и редактируется в render_config/edit_config.
    """
    templates = sorted(mgmt_dir.glob(pattern))
    if not templates:
        die(f"Не найдено ни одного шаблона {pattern} в {mgmt_dir}.")

    print(f"\nДоступные шаблоны конфигурации ({pattern}):")
    for i, t in enumerate(templates, 1):
        print(f"  [{i}] {t.name}   {_template_hint(t)}")

    if len(templates) == 1:
        choice = templates[0]
        print(f"\nДоступен один шаблон — выбран автоматически: {choice.name}")
    else:
        while True:
            raw = input(f"Выберите номер [1-{len(templates)}]: ").strip()
            if raw.isdigit() and 1 <= int(raw) <= len(templates):
                choice = templates[int(raw) - 1]
                break
            print("Некорректный ввод, повторите.")

    print(f"\nВыбран шаблон: {choice}")
    return choice


# --------------------------------------------------------------------------- #
#  Выбор подписывающего сертификата
# --------------------------------------------------------------------------- #
def _subject(cert: Path) -> str:
    try:
        out = subprocess.run(
            ["openssl", "x509", "-in", str(cert), "-noout", "-subject"],
            check=True, capture_output=True, text=True,
        )
        return out.stdout.strip()
    except subprocess.CalledProcessError:
        return "(не удалось прочитать subject)"


def choose_signing_cert(base: Path, prefix: str) -> tuple[Path, Path]:
    """Показать список <prefix>-NN.crt и дать выбрать подписывающий серт.

    Возвращает (cert_path, key_path). Падает, если сертов нет или нет ключа.
    """
    certs_dir = base / "certs"
    private_dir = base / "private"
    pat = re.compile(rf"^{re.escape(prefix)}-(\d+)\.crt$")
    certs = sorted(
        (f for f in certs_dir.iterdir() if pat.match(f.name)) if certs_dir.exists() else [],
        key=lambda p: int(pat.match(p.name).group(1)),
    )
    if not certs:
        die(f"Не найдено ни одного сертификата {prefix}-*.crt в {certs_dir}.\n"
            f"Сначала выпустите вышестоящий сертификат.")

    print(f"\nДоступные сертификаты для подписи ({prefix}):")
    for i, c in enumerate(certs, 1):
        print(f"  [{i}] {c.name}   {_subject(c)}")

    if len(certs) == 1:
        choice = certs[0]
        print(f"\nДоступен один сертификат — выбран автоматически: {choice.name}")
    else:
        while True:
            raw = input(f"Выберите номер [1-{len(certs)}]: ").strip()
            if raw.isdigit() and 1 <= int(raw) <= len(certs):
                choice = certs[int(raw) - 1]
                break
            print("Некорректный ввод, повторите.")

    nn = index_of(choice, prefix)
    key = private_dir / f"{prefix}-{nn}.key"
    if not key.exists():
        die(f"Для {choice.name} не найден приватный ключ: {key}")
    print(f"\nПодписывающий CA:\n  Сертификат: {choice}\n  Ключ:       {key}")
    return choice, key


# --------------------------------------------------------------------------- #
#  Высокоуровневые операции
# --------------------------------------------------------------------------- #
def gen_private_key(path: Path) -> None:
    banner(f"Генерация приватного ключа {path.name}")
    run(["openssl", "genrsa", "-aes256", "-out", path, "4096"])
    os.chmod(path, 0o400)


def write_chain(chain_path: Path, parts: list[Path]) -> None:
    """Собрать PEM-цепочку из нескольких сертификатов (cat) и сделать read-only."""
    if chain_path.exists():
        os.chmod(chain_path, 0o644)
    chain_path.write_text("".join(p.read_text() for p in parts))
    os.chmod(chain_path, 0o444)
    print(f"Цепочка сертификатов создана: {chain_path}")


def show_summary(cert: Path) -> None:
    banner("Проверка")
    out = subprocess.run(
        ["openssl", "x509", "-in", str(cert), "-noout", "-subject", "-issuer", "-dates"],
        check=True, capture_output=True, text=True,
    )
    print(out.stdout.strip())


# --------------------------------------------------------------------------- #
#  main_* — точки входа для трёх скриптов
# --------------------------------------------------------------------------- #
def main_root(template_cnf: Path) -> None:
    base = ROOT_DIR
    ensure_ca_dirs(base)
    init_ca_db(base)

    _, pad = next_index(base / "certs", ROOT_PREFIX)
    key = base / "private" / f"{ROOT_PREFIX}-{pad}.key"
    cert = base / "certs" / f"{ROOT_PREFIX}-{pad}.crt"
    cfg = base / f"openssl_rootCA_{ROOT_PREFIX}-{pad}.cnf"

    banner(f"Создание корневого сертификата {ROOT_PREFIX}-{pad}")
    gen_private_key(key)

    render_config(template_cnf, cfg, {"CA_DIR": base})
    edit_config(cfg)

    banner(f"Выпуск самоподписанного корневого сертификата {ROOT_PREFIX}-{pad}")
    run([
        "openssl", "req", "-config", cfg,
        "-key", key,
        "-new", "-x509", "-days", "5475", "-sha256",
        "-extensions", "x509_ext_root",
        "-out", cert,
    ])

    show_summary(cert)
    print(f"\nГотово. Корневой сертификат: {cert}")


def main_im(template_cnf: Path) -> None:
    im_base = IM_DIR
    ensure_ca_dirs(im_base)
    init_ca_db(im_base)

    # Выбор корневого сертификата для подписи.
    root_cert, root_key = choose_signing_cert(ROOT_DIR, ROOT_PREFIX)

    _, pad = next_index(im_base / "certs", IM_PREFIX)
    key = im_base / "private" / f"{IM_PREFIX}-{pad}.key"
    csr = im_base / "csr" / f"{IM_PREFIX}-{pad}.csr"
    cert = im_base / "certs" / f"{IM_PREFIX}-{pad}.crt"
    chain = im_base / "certs" / f"{IM_PREFIX}-{pad}-chain.crt"
    cfg = im_base / f"openssl_imCA_{IM_PREFIX}-{pad}.cnf"

    banner(f"Создание промежуточного сертификата {IM_PREFIX}-{pad}")
    gen_private_key(key)

    render_config(template_cnf, cfg, {
        "CA_DIR": im_base,
        "SIGNING_KEY": root_key,
        "SIGNING_CERT": root_cert,
    })
    edit_config(cfg)

    banner("Создание запроса (CSR) промежуточного CA")
    run(["openssl", "req", "-config", cfg, "-new", "-sha256", "-key", key, "-out", csr])

    banner("Подписание CSR корневым сертификатом")
    run([
        "openssl", "ca", "-config", cfg,
        "-extensions", "x509_ext_intermediate",
        "-days", "3652", "-notext", "-md", "sha256",
        "-in", csr, "-out", cert,
    ])

    banner("Проверка цепочки im <- root")
    run(["openssl", "verify", "-CAfile", root_cert, cert])

    write_chain(chain, [cert, root_cert])

    show_summary(cert)
    print(f"\nГотово. Промежуточный сертификат: {cert}")
    print(f"Файл цепочки (im+root): {chain}")


def main_ee(mgmt_dir: Path) -> None:
    ee_base = EE_DIR
    ensure_ca_dirs(ee_base)
    init_ca_db(ee_base)

    # Выбор шаблона конфигурации (клиентский / серверный / клиент-серверный ...).
    template_cnf = choose_template(mgmt_dir)

    # Выбор промежуточного сертификата для подписи.
    im_cert, im_key = choose_signing_cert(IM_DIR, IM_PREFIX)
    im_nn = index_of(im_cert, IM_PREFIX)
    im_chain = IM_DIR / "certs" / f"{IM_PREFIX}-{im_nn}-chain.crt"
    if not im_chain.exists():
        print(f"(!) Цепочка {im_chain.name} не найдена — для проверки использую сам im-серт.")
        im_chain = im_cert

    _, pad = next_index(ee_base / "certs", EE_PREFIX)
    key = ee_base / "private" / f"{EE_PREFIX}-{pad}.key"
    csr = ee_base / "csr" / f"{EE_PREFIX}-{pad}.csr"
    cert = ee_base / "certs" / f"{EE_PREFIX}-{pad}.crt"
    chain = ee_base / "certs" / f"{EE_PREFIX}-{pad}-chain.crt"
    cfg = ee_base / f"openssl_endentity_{EE_PREFIX}-{pad}.cnf"

    banner(f"Создание конечного сертификата {EE_PREFIX}-{pad}")
    gen_private_key(key)

    render_config(template_cnf, cfg, {
        "CA_DIR": ee_base,
        "SIGNING_KEY": im_key,
        "SIGNING_CERT": im_cert,
    })
    edit_config(cfg)

    banner("Создание запроса (CSR) конечного сертификата")
    run(["openssl", "req", "-config", cfg, "-new", "-sha256", "-key", key, "-out", csr])

    banner("Подписание CSR промежуточным сертификатом")
    run([
        "openssl", "ca", "-config", cfg,
        "-extensions", "x509_ext_ee",
        "-days", "365", "-notext", "-md", "sha256",
        "-in", csr, "-out", cert,
    ])

    banner("Проверка цепочки ee <- im <- root")
    run(["openssl", "verify", "-CAfile", im_chain, cert])

    # Полная цепочка: ee + im + root (im_chain уже = im + root).
    write_chain(chain, [cert, im_chain])

    show_summary(cert)
    print(f"\nГотово. Конечный сертификат: {cert}")
    print(f"Файл полной цепочки (ee+im+root): {chain}")


def guard(fn, template_cnf: Path) -> None:
    """Запустить main_* с аккуратной обработкой ошибок/прерывания."""
    try:
        fn(template_cnf)
    except KeyboardInterrupt:
        print("\nПрервано пользователем.", file=sys.stderr)
        sys.exit(130)
    except subprocess.CalledProcessError as e:
        die(f"Команда завершилась с ошибкой ({e.returncode}): "
            f"{' '.join(str(c) for c in e.cmd)}")
