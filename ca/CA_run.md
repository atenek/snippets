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
`--paramset` — набор эллиптических параметров ключа ГОСТ Р 34.10-2012.

### `--paramset`: набор параметров ключа ГОСТ

У gost-engine буквенные коды `A/B/C` для `gost2012_256` исторически означают
**старые** (2001-CryptoPro) кривые, а не native-2012: они добавлены для
совместимости со старой PKI-инфраструктурой на CryptoPro CSP, а не потому что
это правильный выбор по умолчанию. Настоящие 2012-параметры доступны только
под кодами с префиксом `TC`. Для `gost2012_512` такого разделения нет — там
`A/B/C` сразу означают native-2012 параметры.

| Профиль | `--paramset` | OID кривой | Стандарт |
|---|---|---|---|
| `gost-256` | `A` / `B` / `C` | `id-GostR3410-2001-CryptoPro-{A,B,C}-ParamSet` (`1.2.643.2.2.35.*`) | legacy, ГОСТ Р 34.10-2001 |
| `gost-256` | `TCA` / `TCB` / `TCC` / `TCD` (**по умолчанию `TCA`**) | `id-tc26-gost-3410-2012-256-paramSet{A,B,C,D}` (`1.2.643.7.1.2.1.1.*`) | ГОСТ Р 34.10-2012 |
| `gost-512` | `A` / `B` / `C` (**по умолчанию `A`**) | `id-tc26-gost-3410-12-512-paramSet{A,B,C}` (`1.2.643.7.1.2.1.2.*`) | ГОСТ Р 34.10-2012 |

Если нужна именно легаси-2001-совместимость для `gost-256` (например, для
интеграции со старым CryptoPro CSP), явно укажите `--paramset A` (или `B`/`C`) —
без флага всегда используется native-2012 `TCA`.

Проверить, какой OID реально попал в ключ/сертификат:
```sh
openssl asn1parse -in <cert.crt> | grep -i object
```

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
python3 rootCA/mgmt/rootCA_init.py --cn root-gost256 --profile gost-256
python3 rootCA/mgmt/rootCA_init.py --cn root-gost512 --profile gost-512
```

## Intermediate CA

### Выпуск промежуточного сертификата, подписанного выбранным корневым CA.

```sh
python3 imCA/mgmt/imCA_init.py
python3 imCA/mgmt/imCA_init.py --cn im-gost256 --profile gost-256
python3 imCA/mgmt/imCA_init.py --cn im-gost512 --profile gost-512
```

## End Entity

### Выпуск конечного сертификата, подписанного выбранным промежуточным CA.

```sh
python3 endentity/mgmt/endentity_init.py
python3 endentity/mgmt/endentity_init.py --cn rserv001-gost256 --profile gost-256
python3 endentity/mgmt/endentity_init.py --cn rserv002-gost512 --profile gost-512
```

Для gost-профилей в меню шаблонов предлагаются только `*_gost.cnf`
(серверный / клиентский / клиент-серверный), для classic — прежние шаблоны.

### Просмотр сертификата

```sh
CERT_PATH=/home/alex/Prj/2_dev/python/ca/certificates/gost/ee/endentity_cert/certs/galex-01.crt
python3 utils/cert_view.py $CERT_PATH
python3 utils/cert_view.py --gost $CERT_PATH
```

Просмотр GOST-сертификата — с флагом `--gost` (openssl выполняется под GOST-окружением); 
без флага GOST-режим пробуется автоматически, если системный openssl не смог разобрать объект:

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
