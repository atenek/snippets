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


def ask_yes_no(prompt: str, default: bool = True) -> bool:
    """Спросить y/n. Пустой ввод -> default."""
    suffix = "[Y/n]" if default else "[y/N]"
    while True:
        raw = input(f"{prompt} {suffix}: ").strip().lower()
        if not raw:
            return default
        if raw in ("y", "yes", "д", "да"):
            return True
        if raw in ("n", "no", "н", "нет"):
            return False
        print("Введите y или n.")


# Допустимые символы CN, когда он используется как префикс имени файла.
_CN_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def sanitize_cn(cn: str) -> str:
    """Проверить имя сертификата (CN), пригодное как префикс имён файлов."""
    cn = (cn or "").strip()
    if not cn:
        die("Имя сертификата (CN) не задано.")
    if not _CN_RE.match(cn):
        die("Недопустимое имя сертификата (CN): разрешены буквы, цифры, '.', '_', '-'.")
    return cn


def prompt_cn(default: str | None = None) -> str:
    """Интерактивно запросить имя сертификата (CN) у пользователя.

    Если задан default, он предлагается в скобках: пустой ввод (Enter) принимает
    его, иначе пользователь вводит/правит своё значение.
    """
    suffix = f" [{default}]" if default else ""
    while True:
        raw = input(f"Введите имя сертификата (CN){suffix}: ").strip()
        if not raw and default:
            return default
        if raw and _CN_RE.match(raw):
            return raw
        print("Разрешены только буквы, цифры, '.', '_', '-'. Повторите.")


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
    # Имена файлов могут иметь cn-префикс ({cn}_{prefix}-NN.crt), поэтому ищем
    # стабильный суффикс {prefix}-NN.crt; цепочки (-chain.crt) исключаем.
    pat = re.compile(rf"{re.escape(prefix)}-(\d+)\.crt$")
    certs = sorted(
        (f for f in certs_dir.iterdir()
         if pat.search(f.name) and not f.name.endswith("-chain.crt"))
        if certs_dir.exists() else [],
        key=lambda p: (int(pat.search(p.name).group(1)), p.name),
    )
    if not certs:
        die(f"Не найдено ни одного сертификата *{prefix}-*.crt в {certs_dir}.\n"
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

    # Ключ лежит рядом под тем же именем: <stem>.key.
    key = private_dir / f"{choice.stem}.key"
    if not key.exists():
        die(f"Для {choice.name} не найден приватный ключ: {key}")
    print(f"\nПодписывающий CA:\n  Сертификат: {choice}\n  Ключ:       {key}")
    return choice, key


# --------------------------------------------------------------------------- #
#  Высокоуровневые операции
# --------------------------------------------------------------------------- #
def gen_private_key(path: Path, encrypt: bool | None = None) -> None:
    """Сгенерировать приватный RSA-ключ.

    encrypt=True  — зашифровать AES-256 (openssl спросит passphrase);
    encrypt=False — БЕЗ пароля (незащищённый ключ);
    encrypt=None  — спросить пользователя интерактивно (по умолчанию — с паролем).

    Без шифрования `-aes256` опускается: иначе openssl требует 4–1024 символа
    passphrase и падает на пустом вводе.
    """
    banner(f"Генерация приватного ключа {path.name}")
    if encrypt is None:
        encrypt = ask_yes_no(
            "Защитить приватный ключ паролем (passphrase)?", default=True
        )
    cmd = ["openssl", "genrsa"]
    if encrypt:
        cmd.append("-aes256")
    else:
        print("(!) Ключ создаётся БЕЗ пароля (passphrase).")
    cmd += ["-out", path, "4096"]
    run(cmd)
    os.chmod(path, 0o400)


def write_chain(chain_path: Path, parts: list[Path]) -> None:
    """Собрать PEM-цепочку из нескольких сертификатов (cat) и сделать read-only."""
    if chain_path.exists():
        os.chmod(chain_path, 0o644)
    chain_path.write_text("".join(p.read_text() for p in parts))
    os.chmod(chain_path, 0o444)
    print(f"Цепочка сертификатов создана: {chain_path}")


def review_csr(csr: Path) -> None:
    """Показать subject будущего сертификата (read-only) и спросить подтверждение.

    Заменяет прежний интерактивный DN-диалог openssl (теперь prompt = no):
    значения уже зафиксированы в конфиге, тут их только показываем.
    """
    banner("Проверка subject будущего сертификата")
    out = subprocess.run(
        ["openssl", "req", "-in", str(csr), "-noout", "-subject"],
        check=True, capture_output=True, text=True,
    )
    print(out.stdout.strip())
    if not ask_yes_no("\nПродолжить выпуск с этим subject?", default=True):
        die("Выпуск отменён пользователем.")


def review_selfsigned(cfg: Path, key: Path) -> None:
    """Показать subject будущего самоподписанного серта (root) и подтвердить.

    У root нет отдельного CSR (он выпускается `req -x509`), поэтому для
    предпросмотра во временный файл генерируется одноразовый CSR.
    """
    import tempfile
    fd, tmpname = tempfile.mkstemp(suffix=".csr")
    os.close(fd)
    tmp = Path(tmpname)
    try:
        subprocess.run(
            ["openssl", "req", "-config", str(cfg), "-new", "-key", str(key), "-out", str(tmp)],
            check=True, capture_output=True, text=True,
        )
        review_csr(tmp)
    finally:
        tmp.unlink(missing_ok=True)


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
def main_root(template_cnf: Path, cn: str) -> None:
    base = ROOT_DIR
    ensure_ca_dirs(base)
    init_ca_db(base)

    # Имя сертификата (CN) — и как CN в конфиге, и как префикс имён файлов.
    cn = sanitize_cn(cn)
    file_prefix = f"{cn}_{ROOT_PREFIX}"

    _, pad = next_index(base / "certs", file_prefix)
    key = base / "private" / f"{file_prefix}-{pad}.key"
    cert = base / "certs" / f"{file_prefix}-{pad}.crt"
    cfg = base / f"openssl_rootCA_{file_prefix}-{pad}.cnf"

    banner(f"Создание корневого сертификата {file_prefix}-{pad} (CN={cn})")
    gen_private_key(key)

    render_config(template_cnf, cfg, {"CA_DIR": base, "CN": cn})
    edit_config(cfg)

    # prompt = no: DN не запрашивается интерактивно — показываем subject для проверки.
    review_selfsigned(cfg, key)

    banner(f"Выпуск самоподписанного корневого сертификата {file_prefix}-{pad}")
    run([
        "openssl", "req", "-config", cfg,
        "-key", key,
        "-new", "-x509", "-days", "5475", "-sha256",
        "-extensions", "x509_ext_root",
        "-out", cert,
    ])

    show_summary(cert)
    print(f"\nГотово. Корневой сертификат: {cert}")


def main_im(template_cnf: Path, cn: str) -> None:
    im_base = IM_DIR
    ensure_ca_dirs(im_base)
    init_ca_db(im_base)

    # Имя сертификата (CN) — и как CN в конфиге, и как префикс имён файлов.
    cn = sanitize_cn(cn)
    file_prefix = f"{cn}_{IM_PREFIX}"

    # Выбор корневого сертификата для подписи.
    root_cert, root_key = choose_signing_cert(ROOT_DIR, ROOT_PREFIX)

    _, pad = next_index(im_base / "certs", file_prefix)
    key = im_base / "private" / f"{file_prefix}-{pad}.key"
    csr = im_base / "csr" / f"{file_prefix}-{pad}.csr"
    cert = im_base / "certs" / f"{file_prefix}-{pad}.crt"
    chain = im_base / "certs" / f"{file_prefix}-{pad}-chain.crt"
    cfg = im_base / f"openssl_imCA_{file_prefix}-{pad}.cnf"

    banner(f"Создание промежуточного сертификата {file_prefix}-{pad} (CN={cn})")
    gen_private_key(key)

    render_config(template_cnf, cfg, {
        "CA_DIR": im_base,
        "SIGNING_KEY": root_key,
        "SIGNING_CERT": root_cert,
        "CN": cn,
    })
    edit_config(cfg)

    banner("Создание запроса (CSR) промежуточного CA")
    run(["openssl", "req", "-config", cfg, "-new", "-sha256", "-key", key, "-out", csr])

    # prompt = no: DN не запрашивается интерактивно — показываем subject для проверки.
    review_csr(csr)

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


def main_ee(mgmt_dir: Path, cn: str) -> None:
    ee_base = EE_DIR
    ensure_ca_dirs(ee_base)
    init_ca_db(ee_base)

    # Имя сертификата (CN) используется и как CN в конфиге, и как префикс имён файлов.
    cn = sanitize_cn(cn)
    file_prefix = f"{cn}_{EE_PREFIX}"

    # Выбор шаблона конфигурации (клиентский / серверный / клиент-серверный ...).
    template_cnf = choose_template(mgmt_dir)

    # Выбор промежуточного сертификата для подписи.
    im_cert, im_key = choose_signing_cert(IM_DIR, IM_PREFIX)
    im_chain = im_cert.with_name(f"{im_cert.stem}-chain.crt")
    if not im_chain.exists():
        print(f"(!) Цепочка {im_chain.name} не найдена — для проверки использую сам im-серт.")
        im_chain = im_cert

    _, pad = next_index(ee_base / "certs", file_prefix)
    key = ee_base / "private" / f"{file_prefix}-{pad}.key"
    csr = ee_base / "csr" / f"{file_prefix}-{pad}.csr"
    cert = ee_base / "certs" / f"{file_prefix}-{pad}.crt"
    chain = ee_base / "certs" / f"{file_prefix}-{pad}-chain.crt"
    cfg = ee_base / f"openssl_endentity_{file_prefix}-{pad}.cnf"

    banner(f"Создание конечного сертификата {file_prefix}-{pad} (CN={cn})")
    gen_private_key(key)

    render_config(template_cnf, cfg, {
        "CA_DIR": ee_base,
        "SIGNING_KEY": im_key,
        "SIGNING_CERT": im_cert,
        "CN": cn,
    })
    edit_config(cfg)

    banner("Создание запроса (CSR) конечного сертификата")
    run(["openssl", "req", "-config", cfg, "-new", "-sha256", "-key", key, "-out", csr])

    # prompt = no: DN не запрашивается интерактивно — показываем subject для проверки.
    review_csr(csr)

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


def guard(fn, *args) -> None:
    """Запустить main_* с аккуратной обработкой ошибок/прерывания."""
    try:
        fn(*args)
    except KeyboardInterrupt:
        print("\nПрервано пользователем.", file=sys.stderr)
        sys.exit(130)
    except subprocess.CalledProcessError as e:
        die(f"Команда завершилась с ошибкой ({e.returncode}): "
            f"{' '.join(str(c) for c in e.cmd)}")
