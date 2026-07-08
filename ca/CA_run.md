# CA

## Режимы работы (криптопрофили)

CA выпускает сертификаты в одном из криптопрофилей:

| Профиль | Ключ | Подпись (digest) | Хранилище |
|---|---|---|---|
| `classic` (по умолчанию) | RSA-4096 | SHA-256 | `certificates/{root,im,ee}/` |
| `gost-256` | ГОСТ Р 34.10-2012 (256 бит) | Стрибог-256 (`md_gost12_256`) | `certificates/gost/{root,im,ee}/` |
| `gost-512` | ГОСТ Р 34.10-2012 (512 бит) | Стрибог-512 (`md_gost12_512`) | `certificates/gost/{root,im,ee}/` |

Профиль задаётся параметром `--profile`; без него при интерактивном запуске
предлагается меню (Enter — `classic`). Для gost-профилей дополнительно доступен
`--paramset` (по умолчанию `A`; для gost-256 — `A,B,C,D,TCA,TCB,TCC,TCD`,
для gost-512 — `A,B,C`).

Профиль выпускаемого сертификата всегда совпадает с профилем подписанта:
хранилища classic и gost раздельны, подписант предлагается только из хранилища
выбранного профиля. Гибридные цепочки (например, gost-ee под classic-im)
невозможны.

GOST-профили работают через gost-engine из `GOST_TLS/gost/` (установка описана
в `GOST_TLS/INSTRUCTION.md`); скрипты сами выставляют окружение openssl и
проверяют доступность engine перед работой. Нестандартное расположение engine
задаётся переменной окружения `GOST_ENGINE_DIR`.

## Root CA

### Выпуск самоподписанного корневого сертификата.

```sh
python3 rootCA/mgmt/rootCA_init.py                          # интерактивно (меню профиля)
python3 rootCA/mgmt/rootCA_init.py --cn root                # classic
python3 rootCA/mgmt/rootCA_init.py --cn groot --profile gost-256
python3 rootCA/mgmt/rootCA_init.py --cn groot --profile gost-512
```

## Intermediate CA

### Выпуск промежуточного сертификата, подписанного выбранным корневым CA.

```sh
python3 imCA/mgmt/imCA_init.py
python3 imCA/mgmt/imCA_init.py --cn gim --profile gost-256
python3 imCA/mgmt/imCA_init.py --cn gim --profile gost-512
```

## End Entity

### Выпуск конечного сертификата, подписанного выбранным промежуточным CA.

```sh
python3 endentity/mgmt/endentity_init.py
python3 endentity/mgmt/endentity_init.py --cn galex --profile gost-256
python3 endentity/mgmt/endentity_init.py --cn galex --profile gost-512
```

Для gost-профилей в меню шаблонов предлагаются только `*_gost.cnf`
(серверный / клиентский / клиент-серверный), для classic — прежние шаблоны.

### Просмотр сертификата

```sh
CERT_PATH=/home/alex/Prj/2_dev/python/ca/certificates/gost/ee/endentity_cert/certs/galex-01.crt
python3 utils/cert_view.py $CERT_PATH
python3 utils/cert_view.py --gost $CERT_PATH
```

Просмотр GOST-сертификата — с флагом `--gost` (openssl выполняется под
GOST-окружением); без флага GOST-режим пробуется автоматически, если системный
openssl не смог разобрать объект:

```sh
python3 utils/cert_view.py --gost certificates/gost/ee/endentity_cert/certs/galex-01.crt
```

## Смоук-тесты

```sh
./GOST_TLS/check_gost_tls.sh     # самотест установки gost-engine (10 проверок)
./utils/check_gost_ca.sh         # тестовая gost-цепочка root->im->ee + verify + TLS 1.2 handshake
```

`check_gost_ca.sh` не требует ввода и не трогает рабочее `certificates/`:
хранилище подменяется переменной окружения `CA_CERT_BASE` (временный каталог).
