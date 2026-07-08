"""Общая библиотека для helper-скриптов работы с сертификатами.

Это тонкая обёртка над внешним вызовом `openssl`: она готовит каталоги-хранилища,
рендерит конфиг openssl (без sed, обычной подстановкой плейсхолдеров), даёт выбрать
подписывающий сертификат и собирает корректные параметры для вызова openssl.

Иерархия (для каждого криптопрофиля — своё дерево, см. CryptoProfile):

    certificates/
        root/root_cert/          # classic: самоподписанные корневые серты
        im/im_cert/              # classic: промежуточные (подписаны выбранным root)
        ee/endentity_cert/       # classic: конечные (подписаны выбранным im)
        gost/root/root_cert/     # gost-256 / gost-512: то же, но ГОСТ-алгоритмы
        gost/im/im_cert/
        gost/ee/endentity_cert/

Каждый каталог CA содержит стандартную структуру БД openssl `ca`
(certs/ crl/ csr/ newcerts/ private/ index.txt serial crlnumber).

Криптопрофили:
    classic  — RSA-4096, подпись SHA-256 (как исторически);
    gost-256 — ГОСТ Р 34.10-2012 (256 бит) + Стрибог-256 (md_gost12_256);
    gost-512 — ГОСТ Р 34.10-2012 (512 бит) + Стрибог-512 (md_gost12_512).
GOST-профили работают через gost-engine из GOST_TLS/gost/ (см. INSTRUCTION.md):
все вызовы openssl выполняются с окружением OPENSSL_CONF/ENGINES/MODULES,
указывающим внутрь проекта (переопределяется переменной GOST_ENGINE_DIR).
Гибридные цепочки (gost-ee под classic-im и наоборот) исключены раздельными
деревьями хранилища.
"""

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# Корень проекта: lib/ -> <project>
PROJECT_ROOT = Path(__file__).resolve().parents[1]
# Хранилище сертификатов; CA_CERT_BASE — переопределение для смоук-тестов.
CERT_BASE = Path(os.environ.get("CA_CERT_BASE", PROJECT_ROOT / "certificates"))

ROOT_DIR = "root_cert"
IM_DIR = "im_cert"
EE_DIR = "endentity_cert"

# Каталог локальной установки gost-engine (по умолчанию — внутри проекта).
GOST_DIR_DEFAULT = PROJECT_ROOT / "GOST_TLS" / "gost"


# --------------------------------------------------------------------------- #
#  Криптопрофили
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CryptoProfile:
    """Именованный набор всех алгоритмо-зависимых параметров выпуска."""
    name: str             # classic | gost-256 | gost-512
    md: str               # digest подписи: sha256 | md_gost12_256 | md_gost12_512
    keygen: tuple         # аргументы openssl генерации ключа (без -aes256/-out)
    template_suffix: str  # суффикс шаблонов .cnf: "" (classic) | "_gost"
    env: dict | None      # окружение openssl; None — системное (classic)

    @property
    def is_gost(self) -> bool:
        return self.name != "classic"


PROFILE_NAMES = ("classic", "gost-256", "gost-512")

# Допустимые paramset ГОСТ-ключей (gost-engine, ГОСТ Р 34.10-2012).
GOST_PARAMSETS = {
    "gost-256": ("A", "B", "C", "D", "TCA", "TCB", "TCC", "TCD"),
    "gost-512": ("A", "B", "C"),
}


def gost_dir() -> Path:
    """Каталог установки gost-engine (переопределяется env GOST_ENGINE_DIR)."""
    return Path(os.environ.get("GOST_ENGINE_DIR", GOST_DIR_DEFAULT)).resolve()


def _render_gost_conf(gdir: Path) -> Path:
    """Отрендерить openssl_gost.cnf из шаблона: dynamic_path — внутрь gdir.

    Рендер идемпотентный (файл перезаписывается только при изменении), поэтому
    dynamic_path всегда указывает на текущее расположение проекта — перенос
    каталога проекта GOST-режим не ломает.
    """
    template = gdir / "openssl_gost.cnf.template"
    conf = gdir / "openssl_gost.cnf"
    if not template.exists():
        if conf.exists():
            # Нестандартная установка (GOST_ENGINE_DIR) без шаблона — как есть.
            return conf
        die(f"Не найден шаблон GOST-конфига: {template}\n"
            f"Об установке gost-engine см. GOST_TLS/INSTRUCTION.md.")
    text = template.read_text().replace("@@GOST_DIR@@", str(gdir))
    leftover = re.findall(r"@@[A-Z_]+@@", text)
    if leftover:
        die(f"В GOST-конфиге остались незаполненные плейсхолдеры: {sorted(set(leftover))}")
    if not conf.exists() or conf.read_text() != text:
        conf.write_text(text)
        print(f"GOST-конфиг обновлён: {conf}")
    return conf


def gost_env() -> dict:
    """Окружение openssl с активированным gost-engine (копия os.environ).

    Выставляет OPENSSL_CONF / OPENSSL_ENGINES / OPENSSL_MODULES на каталог
    gost_dir() — аналог `source GOST_TLS/gost/env.sh`, но без изменения
    текущей сессии.
    """
    gdir = gost_dir()
    engine = gdir / "engines-3" / "gost.so"
    if not engine.exists():
        die(f"Не найден gost-engine: {engine}\n"
            f"Об установке см. GOST_TLS/INSTRUCTION.md.")
    conf = _render_gost_conf(gdir)
    env = os.environ.copy()
    env["OPENSSL_CONF"] = str(conf)
    env["OPENSSL_ENGINES"] = str(gdir / "engines-3")
    env["OPENSSL_MODULES"] = str(gdir / "ossl-modules")
    return env


def check_gost_engine(env: dict) -> None:
    """Fail-fast: убедиться, что gost-engine загружается под данным окружением."""
    try:
        out = subprocess.run(
            ["openssl", "engine", "gost", "-c"],
            env=env, capture_output=True, text=True, check=True,
        )
        loaded = "gost2012_256" in out.stdout
    except (OSError, subprocess.CalledProcessError):
        loaded = False
    if not loaded:
        die("gost-engine не загружается (`openssl engine gost -c`).\n"
            "Проверьте установку: GOST_TLS/INSTRUCTION.md, "
            "самотест — GOST_TLS/check_gost_tls.sh.")


def check_gost_inprocess(env: dict) -> None:
    """Fail-fast: убедиться, что `import ssl` ЭТОГО интерпретатора переживает
    загрузку gost-engine (OPENSSL_CONF из env).

    Питон со статически влинкованным OpenSSL (например, uv-сборка
    python-build-standalone) при чтении GOST-конфига dlopen-ит gost.so,
    слинкованный с системным libcrypto: вторая копия libcrypto в одном
    процессе роняет интерпретатор (segfault). Проба в дочернем процессе
    превращает этот крах в понятную ошибку.
    """
    probe = subprocess.run([sys.executable, "-c", "import ssl"],
                           env=env, capture_output=True)
    if probe.returncode != 0:
        die(f"Интерпретатор {sys.executable} несовместим с gost-engine:\n"
            f"`import ssl` под GOST-окружением завершился аварийно "
            f"(код {probe.returncode}).\n"
            "Обычная причина — python со статически влинкованным OpenSSL "
            "(uv-сборка); запустите системным питоном:\n"
            "  /usr/bin/python3 server_https/gost_https_server.py")


def get_profile(name: str, paramset: str | None = None) -> CryptoProfile:
    """Собрать криптопрофиль по имени; для GOST — с проверкой engine (fail-fast)."""
    if name == "classic":
        if paramset:
            die("--paramset применим только к gost-профилям (--profile gost-256/gost-512).")
        return CryptoProfile("classic", "sha256", ("genrsa",), "", None)
    if name not in GOST_PARAMSETS:
        die(f"Неизвестный криптопрофиль: {name}. Допустимо: {', '.join(PROFILE_NAMES)}.")
    ps = (paramset or "A").upper()
    valid = GOST_PARAMSETS[name]
    if ps not in valid:
        die(f"Недопустимый paramset '{ps}' для {name}. Допустимо: {', '.join(valid)}.")
    bits = name.split("-")[1]
    env = gost_env()
    check_gost_engine(env)
    return CryptoProfile(
        name=name,
        md=f"md_gost12_{bits}",
        keygen=("genpkey", "-algorithm", f"gost2012_{bits}", "-pkeyopt", f"paramset:{ps}"),
        template_suffix="_gost",
        env=env,
    )


def choose_profile() -> str:
    """Интерактивно выбрать криптопрофиль (тем же меню, что шаблоны/подписанты).

    Если stdin — не терминал, без вопросов возвращается classic.
    """
    if not sys.stdin.isatty():
        return "classic"
    hints = {
        "classic": "RSA-4096 + SHA-256 (как раньше)",
        "gost-256": "ГОСТ Р 34.10-2012 (256) + Стрибог-256",
        "gost-512": "ГОСТ Р 34.10-2012 (512) + Стрибог-512",
    }
    print("\nДоступные криптопрофили:")
    for i, n in enumerate(PROFILE_NAMES, 1):
        mark = " (по умолчанию)" if n == "classic" else ""
        print(f"  [{i}] {n}{mark}   {hints[n]}")
    while True:
        raw = input(f"Выберите номер [1-{len(PROFILE_NAMES)}] (Enter — classic): ").strip()
        if not raw:
            return "classic"
        if raw.isdigit() and 1 <= int(raw) <= len(PROFILE_NAMES):
            return PROFILE_NAMES[int(raw) - 1]
        print("Некорректный ввод, повторите.")


def resolve_profile(name: str | None, paramset: str | None = None) -> CryptoProfile:
    """Профиль из --profile либо интерактивного меню (без терминала — classic)."""
    if name is None:
        name = choose_profile()
    return get_profile(name, paramset)


# --------------------------------------------------------------------------- #
#  Пути хранилищ (зависят от криптопрофиля: classic и gost — раздельные деревья)
# --------------------------------------------------------------------------- #
def _cert_base(profile: CryptoProfile) -> Path:
    return CERT_BASE / "gost" if profile.is_gost else CERT_BASE


def root_path(profile: CryptoProfile) -> Path:
    return _cert_base(profile) / "root" / ROOT_DIR


def im_path(profile: CryptoProfile) -> Path:
    return _cert_base(profile) / "im" / IM_DIR


def ee_path(profile: CryptoProfile) -> Path:
    return _cert_base(profile) / "ee" / EE_DIR


# --------------------------------------------------------------------------- #
#  Низкоуровневые помощники
# --------------------------------------------------------------------------- #
def banner(text: str) -> None:
    print(f"\n====== {text} ======\n", flush=True)


def run(cmd, env: dict | None = None) -> subprocess.CompletedProcess:
    """Запустить внешнюю команду, унаследовав stdin/stdout (для интерактива openssl).

    env=None — системное окружение (classic); для GOST передаётся profile.env.
    """
    printable = " ".join(str(c) for c in cmd)
    print(f"$ {printable}", flush=True)
    return subprocess.run([str(c) for c in cmd], check=True, env=env)


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


def choose_template(mgmt_dir: Path, profile: CryptoProfile) -> Path:
    """Показать список шаблонов *.cnf рядом со скриптом и дать выбрать один.

    Показываются только шаблоны выбранного криптопрофиля:
    gost — `*_gost.cnf`, classic — остальные `*.cnf`.
    Возвращает путь к выбранному шаблону. Падает, если шаблонов нет.
    Дальше выбранный шаблон копируется и редактируется в render_config/edit_config.
    """
    pattern = "*_gost.cnf" if profile.is_gost else "*.cnf (кроме *_gost.cnf)"
    templates = sorted(
        t for t in mgmt_dir.glob("*.cnf")
        if t.name.endswith("_gost.cnf") == profile.is_gost
    )
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
def _subject(cert: Path, env: dict | None = None) -> str:
    try:
        out = subprocess.run(
            ["openssl", "x509", "-in", str(cert), "-noout", "-subject"],
            check=True, capture_output=True, text=True, env=env,
        )
        return out.stdout.strip()
    except subprocess.CalledProcessError:
        return "(не удалось прочитать subject)"


def choose_signing_cert(base: Path, prefix: str,
                        env: dict | None = None) -> tuple[Path, Path]:
    """Показать список <prefix>-NN.crt и дать выбрать подписывающий серт.

    base — хранилище уровня-подписанта ВЫБРАННОГО профиля (root_path/im_path),
    поэтому в списке только сертификаты этого профиля — гибридные цепочки
    исключены. Возвращает (cert_path, key_path). Падает, если сертов нет
    или нет ключа.
    """
    certs_dir = base / "certs"
    private_dir = base / "private"
    # Имена файлов могут иметь cn-префикс ({cn}_{prefix}-NN.crt), поэтому ищем
    # стабильный суффикс {prefix}-NN.crt; цепочки (-chain.crt) исключаем.
    pat = re.compile(r".*-(\d+)\.crt$")
    certs = sorted(
        (f for f in certs_dir.iterdir()
         if pat.search(f.name) and not f.name.endswith("-chain.crt"))
        if certs_dir.exists() else [],
        key=lambda p: (int(pat.search(p.name).group(1)), p.name),
    )
    if not certs:
        die(f"Не найдено ни одного сертификата *dd.crt в {certs_dir}.\n"
            f"Сначала выпустите вышестоящий сертификат (в этом же криптопрофиле).")

    print(f"\nДоступные сертификаты для подписи ({prefix}):")
    for i, c in enumerate(certs, 1):
        print(f"  [{i}] {c.name}   {_subject(c, env=env)}")

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
def gen_private_key(path: Path, profile: CryptoProfile,
                    encrypt: bool | None = None) -> None:
    """Сгенерировать приватный ключ по криптопрофилю.

    classic — `openssl genrsa [-aes256] 4096`;
    gost-*  — `openssl genpkey -algorithm gost2012_* -pkeyopt paramset:<PS> [-aes256]`
              (шифрование — PBE поверх PKCS#8, passphrase спросит openssl).

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
    cmd = ["openssl", *profile.keygen]
    if encrypt:
        cmd.append("-aes256")
    else:
        print("(!) Ключ создаётся БЕЗ пароля (passphrase).")
    cmd += ["-out", path]
    if profile.name == "classic":
        cmd.append("4096")
    run(cmd, env=profile.env)
    os.chmod(path, 0o400)


def write_chain(chain_path: Path, parts: list[Path]) -> None:
    """Собрать PEM-цепочку из нескольких сертификатов (cat) и сделать read-only."""
    if chain_path.exists():
        os.chmod(chain_path, 0o644)
    chain_path.write_text("".join(p.read_text() for p in parts))
    os.chmod(chain_path, 0o444)
    print(f"Цепочка сертификатов создана: {chain_path}")


def review_csr(csr: Path, env: dict | None = None) -> None:
    """Показать subject будущего сертификата (read-only) и спросить подтверждение.

    Заменяет прежний интерактивный DN-диалог openssl (теперь prompt = no):
    значения уже зафиксированы в конфиге, тут их только показываем.
    """
    banner("Проверка subject будущего сертификата")
    out = subprocess.run(
        ["openssl", "req", "-in", str(csr), "-noout", "-subject"],
        check=True, capture_output=True, text=True, env=env,
    )
    print(out.stdout.strip())
    if not ask_yes_no("\nПродолжить выпуск с этим subject?", default=True):
        die("Выпуск отменён пользователем.")


def review_selfsigned(cfg: Path, key: Path, env: dict | None = None) -> None:
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
            check=True, capture_output=True, text=True, env=env,
        )
        review_csr(tmp, env=env)
    finally:
        tmp.unlink(missing_ok=True)


def show_summary(cert: Path, env: dict | None = None) -> None:
    banner("Проверка")
    out = subprocess.run(
        ["openssl", "x509", "-in", str(cert), "-noout", "-subject", "-issuer", "-dates"],
        check=True, capture_output=True, text=True, env=env,
    )
    print(out.stdout.strip())


# --------------------------------------------------------------------------- #
#  main_* — точки входа для трёх скриптов
# --------------------------------------------------------------------------- #
def main_root(mgmt_dir: Path, cn: str, profile: CryptoProfile) -> None:
    base = root_path(profile)
    ensure_ca_dirs(base)
    init_ca_db(base)

    # Шаблон уровня root для выбранного профиля.
    template_cnf = mgmt_dir / f"openssl_rootCA{profile.template_suffix}.cnf"

    # Имя сертификата (CN) — и как CN в конфиге, и как префикс имён файлов.
    cn = sanitize_cn(cn)
    file_prefix = f"{cn}"

    _, pad = next_index(base / "certs", file_prefix)
    key = base / "private" / f"{file_prefix}-{pad}.key"
    cert = base / "certs" / f"{file_prefix}-{pad}.crt"
    cfg = base / f"openssl_rootCA_{file_prefix}-{pad}.cnf"

    banner(f"Создание корневого сертификата {file_prefix}-{pad} "
           f"(CN={cn}, профиль {profile.name})")
    gen_private_key(key, profile)

    render_config(template_cnf, cfg, {"CA_DIR": base, "CN": cn, "MD": profile.md})
    edit_config(cfg)

    # prompt = no: DN не запрашивается интерактивно — показываем subject для проверки.
    review_selfsigned(cfg, key, env=profile.env)

    banner(f"Выпуск самоподписанного корневого сертификата {file_prefix}-{pad}")
    run([
        "openssl", "req", "-config", cfg,
        "-key", key,
        "-new", "-x509", "-days", "5475", f"-{profile.md}",
        "-extensions", "x509_ext_root",
        "-out", cert,
    ], env=profile.env)

    show_summary(cert, env=profile.env)
    print(f"\nГотово. Корневой сертификат: {cert}")


def main_im(mgmt_dir: Path, cn: str, profile: CryptoProfile) -> None:
    im_base = im_path(profile)
    ensure_ca_dirs(im_base)
    init_ca_db(im_base)

    # Шаблон уровня im для выбранного профиля.
    template_cnf = mgmt_dir / f"openssl_imCA{profile.template_suffix}.cnf"

    # Имя сертификата (CN) — и как CN в конфиге, и как префикс имён файлов.
    cn = sanitize_cn(cn)
    file_prefix = f"{cn}"

    # Выбор корневого сертификата для подписи (только того же профиля).
    root_cert, root_key = choose_signing_cert(root_path(profile), ROOT_DIR,
                                              env=profile.env)

    _, pad = next_index(im_base / "certs", file_prefix)
    key = im_base / "private" / f"{file_prefix}-{pad}.key"
    csr = im_base / "csr" / f"{file_prefix}-{pad}.csr"
    cert = im_base / "certs" / f"{file_prefix}-{pad}.crt"
    chain = im_base / "certs" / f"{file_prefix}-{pad}-chain.crt"
    cfg = im_base / f"openssl_imCA_{file_prefix}-{pad}.cnf"

    banner(f"Создание промежуточного сертификата {file_prefix}-{pad} "
           f"(CN={cn}, профиль {profile.name})")
    gen_private_key(key, profile)

    render_config(template_cnf, cfg, {
        "CA_DIR": im_base,
        "SIGNING_KEY": root_key,
        "SIGNING_CERT": root_cert,
        "CN": cn,
        "MD": profile.md,
    })
    edit_config(cfg)

    banner("Создание запроса (CSR) промежуточного CA")
    run(["openssl", "req", "-config", cfg, "-new", f"-{profile.md}",
         "-key", key, "-out", csr], env=profile.env)

    # prompt = no: DN не запрашивается интерактивно — показываем subject для проверки.
    review_csr(csr, env=profile.env)

    banner("Подписание CSR корневым сертификатом")
    run([
        "openssl", "ca", "-config", cfg,
        "-extensions", "x509_ext_intermediate",
        "-days", "3652", "-notext", "-md", profile.md,
        "-in", csr, "-out", cert,
    ], env=profile.env)

    banner("Проверка цепочки im <- root")
    run(["openssl", "verify", "-CAfile", root_cert, cert], env=profile.env)

    write_chain(chain, [cert, root_cert])

    show_summary(cert, env=profile.env)
    print(f"\nГотово. Промежуточный сертификат: {cert}")
    print(f"Файл цепочки (im+root): {chain}")


def main_ee(mgmt_dir: Path, cn: str, profile: CryptoProfile) -> None:
    ee_base = ee_path(profile)
    ensure_ca_dirs(ee_base)
    init_ca_db(ee_base)

    # Имя сертификата (CN) используется и как CN в конфиге, и как префикс имён файлов.
    cn = sanitize_cn(cn)
    file_prefix = f"{cn}"

    # Выбор шаблона конфигурации (клиентский / серверный / клиент-серверный ...)
    # среди шаблонов выбранного криптопрофиля.
    template_cnf = choose_template(mgmt_dir, profile)

    # Выбор промежуточного сертификата для подписи (только того же профиля).
    im_cert, im_key = choose_signing_cert(im_path(profile), IM_DIR, env=profile.env)
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

    banner(f"Создание конечного сертификата {file_prefix}-{pad} "
           f"(CN={cn}, профиль {profile.name})")
    gen_private_key(key, profile)

    render_config(template_cnf, cfg, {
        "CA_DIR": ee_base,
        "SIGNING_KEY": im_key,
        "SIGNING_CERT": im_cert,
        "CN": cn,
        "MD": profile.md,
    })
    edit_config(cfg)

    banner("Создание запроса (CSR) конечного сертификата")
    run(["openssl", "req", "-config", cfg, "-new", f"-{profile.md}",
         "-key", key, "-out", csr], env=profile.env)

    # prompt = no: DN не запрашивается интерактивно — показываем subject для проверки.
    review_csr(csr, env=profile.env)

    banner("Подписание CSR промежуточным сертификатом")
    run([
        "openssl", "ca", "-config", cfg,
        "-extensions", "x509_ext_ee",
        "-days", "365", "-notext", "-md", profile.md,
        "-in", csr, "-out", cert,
    ], env=profile.env)

    banner("Проверка цепочки ee <- im <- root")
    run(["openssl", "verify", "-CAfile", im_chain, cert], env=profile.env)

    # Полная цепочка: ee + im + root (im_chain уже = im + root).
    write_chain(chain, [cert, im_chain])

    show_summary(cert, env=profile.env)
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
