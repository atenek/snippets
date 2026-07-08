# Настройка OpenSSL для поддержки GOST-TLS

Пошаговая инструкция по включению российских криптоалгоритмов ГОСТ в
OpenSSL 3.0 на базе [gost-engine](https://github.com/gost-engine/engine).

## Окружение

| Параметр | Значение |
|----------|----------|
| ОС | Ubuntu 24.04.3 LTS |
| OpenSSL | 3.0.13 (системный, `/usr/bin/openssl`) |
| ENGINESDIR | `/usr/lib/x86_64-linux-gnu/engines-3` |
| Движок ГОСТ | `libengine-gost-openssl` 3.0.2 (gost-engine) |

Установка выполнена **локально в каталог проекта, без прав root и без
изменения системных файлов** — всё включается через переменные окружения
и легко откатывается удалением каталога `gost/`.

## Обеспечиваемые компоненты

| Требование | Алгоритмы движка |
|------------|------------------|
| Электронная подпись — ГОСТ Р 34.10‑2012 | `gost2012_256`, `gost2012_512` (+ legacy `gost2001`) |
| Хэш‑функции — ГОСТ Р 34.11‑2012 | `md_gost12_256`, `md_gost12_512` (Streebog) |
| Шифрование — ГОСТ Р 34.12/34.13‑2015 | `magma-*`, `kuznyechik-*` (Магма, Кузнечик) |
| Шифрование — ГОСТ 28147‑89 | `gost89`, `gost89-cnt`, `gost-mac` |

---

## Шаг 1. Получить движок GOST для OpenSSL 3.0

В репозитории Ubuntu 24.04 (`noble/universe`) есть готовый пакет
`libengine-gost-openssl` — это собранный gost-engine, совместимый с
OpenSSL 3.0. Он содержит и engine (`gost.so`), и provider (`gostprov.so`).

Скачиваем пакет **без установки в систему** (не требует sudo):

```bash
cd /home/alex/Prj/2_dev/python/gost_tls
apt-get download libengine-gost-openssl
dpkg-deb -x libengine-gost-openssl_*.deb extract/
```

> Альтернатива — установить системно (нужен root):
> `sudo apt install libengine-gost-openssl`, тогда движок попадёт прямо
> в `ENGINESDIR` и шаги с путями упрощаются.
>
> Альтернатива — собрать из исходников gost-engine:
> ```bash
> git clone https://github.com/gost-engine/engine
> cd engine && git submodule update --init
> mkdir build && cd build
> cmake -DCMAKE_BUILD_TYPE=Release ..
> cmake --build . --config Release
> ```

## Шаг 2. Разложить движок в каталог проекта

```bash
mkdir -p gost/engines-3 gost/ossl-modules
cp extract/usr/lib/x86_64-linux-gnu/engines-3/gost.so       gost/engines-3/
cp extract/usr/lib/x86_64-linux-gnu/ossl-modules/gostprov.so gost/ossl-modules/
# Проверить, что зависимости .so разрешаются:
ldd gost/engines-3/gost.so | grep -i "not found" || echo OK
```

## Шаг 3. Создать конфиг OpenSSL с регистрацией движка

Файл [gost/openssl_gost.cnf](gost/openssl_gost.cnf) подключает системный
`openssl.cnf` и дополнительно регистрирует движок:

```ini
.include /usr/lib/ssl/openssl.cnf

openssl_conf = openssl_init

[openssl_init]
engines = engine_section

[engine_section]
gost = gost_section

[gost_section]
engine_id = gost
dynamic_path = /home/alex/Prj/2_dev/python/gost_tls/gost/engines-3/gost.so
default_algorithms = ALL
CRYPT_PARAMS = id-tc26-gost-28147-param-Z
```

> Важно: в engine-конфиге OpenSSL 3.0 допустимы только команды, которые
> реально понимает движок (`default_algorithms`, `CRYPT_PARAMS`).
> Несуществующие ключи (например `default_gost`) приводят к
> `FATAL: Startup failure`.

## Шаг 4. Активировать GOST в текущей сессии

```bash
source gost/env.sh          # выставляет OPENSSL_CONF / OPENSSL_ENGINES
openssl engine gost -c -t   # должно показать список ГОСТ-алгоритмов и [ available ]
```

Ожидаемый вывод — строка `(gost) Reference implementation of GOST engine`
со списком `gost2012_256, md_gost12_256, kuznyechik-cbc, magma-cbc, …` и
пометкой `[ available ]`.

---

## Шаг 5. Проверка работы (verification)

Полная автоматическая проверка одной командой:

```bash
./check_gost_tls.sh
```

Скрипт последовательно проверяет все требуемые компоненты и завершает
живым TLS‑рукопожатием на ГОСТ‑шифрах. Ожидаемый результат:

```
== 1. Engine load ==
  [ OK ] GOST engine loaded
== 2. Hash: GOST R 34.11-2012 (Streebog) ==
  [ OK ] Streebog-256 matches known test vector
  [ OK ] Streebog-512 available
== 3. Signature: GOST R 34.10-2012 ==
  [ OK ] gost2012_256 sign+verify
  [ OK ] gost2012_512 sign+verify
== 4. Ciphers: GOST 34.12/34.13-2015 + 28147-89 ==
  [ OK ] kuznyechik-cbc
  [ OK ] magma-cbc
  [ OK ] gost89
== 5. GOST-TLS live handshake ==
  [ OK ] TLS negotiated GOST cipher
  [ OK ] TLS certificate verified

==================== RESULT: 10 passed, 0 failed ====================
```

### Ручная проверка отдельных компонентов

**Хэш (ГОСТ Р 34.11‑2012):**
```bash
echo -n "The quick brown fox jumps over the lazy dog" | openssl dgst -md_gost12_256
# 3e7dea7f2384b6c5a3d0e24aaa29c05e89ddd762145030ec22c71a6db8b2c1f4  (эталон)
```

**Подпись (ГОСТ Р 34.10‑2012):**
```bash
openssl genpkey -algorithm gost2012_256 -pkeyopt paramset:A -out key.pem
openssl pkey -in key.pem -pubout -out pub.pem
openssl dgst -md_gost12_256 -sign key.pem -out sig.bin data.txt
openssl dgst -md_gost12_256 -verify pub.pem -signature sig.bin data.txt   # Verified OK
```

**Шифрование (Кузнечик / Магма / 28147‑89):**
```bash
echo -n secret | openssl enc -e -a -kuznyechik-cbc -k pass -iter 1
echo -n secret | openssl enc -e -a -magma-cbc      -k pass -iter 1
echo -n secret | openssl enc -e -a -gost89         -k pass -iter 1
```

**GOST‑TLS ciphersuites, доступные libssl:**
```bash
openssl ciphers -v 'aGOST'
# GOST2012-MAGMA-MAGMAOMAC             TLSv1.2 Kx=GOST18 ...
# GOST2012-KUZNYECHIK-KUZNYECHIKOMAC   TLSv1.2 Kx=GOST18 ...
# GOST2012-GOST8912-GOST8912           TLSv1   Kx=GOST   Au=GOST12 ...
```

**Живое TLS‑рукопожатие на ГОСТ:**
```bash
# 1) ГОСТ-сертификаты (CA + сервер)
openssl genpkey -algorithm gost2012_256 -pkeyopt paramset:A -out ca.key
openssl req -x509 -new -key ca.key -md_gost12_256 -days 365 -out ca.crt -subj "/CN=GOST CA"
openssl genpkey -algorithm gost2012_256 -pkeyopt paramset:A -out srv.key
openssl req -new -key srv.key -md_gost12_256 -out srv.csr -subj "/CN=localhost"
openssl x509 -req -in srv.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
        -md_gost12_256 -days 365 -out srv.crt

# 2) сервер
openssl s_server -accept 44344 -cert srv.crt -key srv.key -CAfile ca.crt \
        -cipher 'GOST2012-KUZNYECHIK-KUZNYECHIKOMAC' -tls1_2 -www &

# 3) клиент
echo | openssl s_client -connect localhost:44344 -CAfile ca.crt -tls1_2 | grep -E "Cipher is|Verify"
# New, TLSv1.2, Cipher is GOST2012-KUZNYECHIK-KUZNYECHIKOMAC
# Verify return code: 0 (ok)
```

---

## Откат / удаление

Ничего в системе не менялось. Достаточно:
```bash
rm -rf gost/ extract/ libengine-gost-openssl_*.deb
```
и не выставлять переменные `OPENSSL_CONF` / `OPENSSL_ENGINES`.

## Структура каталога

```
gost_tls/
├── INSTRUCTION.md            # эта инструкция
├── check_gost_tls.sh         # автоматическая проверка (10 тестов)
└── gost/
    ├── env.sh                # source gost/env.sh — активация в сессии
    ├── openssl_gost.cnf      # конфиг с регистрацией движка
    ├── engines-3/gost.so     # движок GOST (engine)
    └── ossl-modules/gostprov.so  # provider для OpenSSL 3.0 (опционально)
```
