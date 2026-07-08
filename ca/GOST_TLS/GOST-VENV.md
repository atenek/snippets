# GOST-VENV GOST-окружение проекта

`GOST-VENV` — это локальная, не требующая root активация `gost-engine` для системного `OpenSSL`.  
По духу это аналог python-`venv`. В систему ничего не ставится.
«Активация» — лишь переменные окружения текущего процесса,
«Откат» удаление каталога `GOST_TLS/gost/`.
**GOST-VENV действует только на тот процесс, в котором активирован,
и на его потомков** — как и обычный venv.

## 1. Как openssl конфигурируется сам по себе (без VENV)

Утилита `openssl` (и библиотека libcrypto, которой пользуются curl, python
и т.д.) при старте читает **один** конфигурационный файл:

1. Если выставлена переменная окружения `OPENSSL_CONF` — берётся файл из неё.
2. Иначе — вкомпилированный путь по умолчанию: `<OPENSSLDIR>/openssl.cnf`,
   на Ubuntu это `/usr/lib/ssl/openssl.cnf` (посмотреть: `openssl version -d`).

В этом файле, среди прочего, объявляются **движки (engines)** и
**провайдеры** — подключаемые `.so`-модули с реализациями алгоритмов.
Системный `openssl.cnf` про ГОСТ ничего не знает, поэтому «голый» openssl:

- не умеет алгоритмы `gost2012_256/512`, `md_gost12_*`, `magma-*`, ...;
- в TLS не предлагает GOST-ciphersuites (`openssl ciphers 'aGOST'` пуст).

Пути поиска модулей тоже управляются переменными окружения:

| Переменная        | Что задаёт                             | Системное значение (Ubuntu 24.04)        |
| ----------------- | -------------------------------------- | ---------------------------------------- |
| `OPENSSL_CONF`    | конфигурационный файл                  | `/usr/lib/ssl/openssl.cnf`               |
| `OPENSSL_ENGINES` | каталог engine-модулей (`.so`)         | `/usr/lib/x86_64-linux-gnu/engines-3`    |
| `OPENSSL_MODULES` | каталог provider-модулей (OpenSSL 3.x) | `/usr/lib/x86_64-linux-gnu/ossl-modules` |

Ключевая идея: **OpenSSL расширяется без пересборки** — достаточно подсунуть
свой конфиг через `OPENSSL_CONF`, а в нём указать путь к движку.

## 2. Принцип устройства GOST-VENV GOST-окружения проекта

Всё «окружение» — это каталог `GOST_TLS/gost/`:

```
GOST_TLS/gost/
├── env.sh                      # активация в текущем шелле (source)
├── openssl_gost.cnf.template   # ШАБЛОН конфига (@@GOST_DIR@@) — править его
├── openssl_gost.cnf            # рендер шаблона (абсолютные пути) — не править
├── engines-3/gost.so           # сам gost-engine (взят из пакета libengine-gost-openssl)
└── ossl-modules/gostprov.so    # gost-provider (задел на будущее, не используется)
```

Принципы:

1. **Никаких изменений системы.** Движок лежит внутри проекта, root не нужен,
   откат — `rm -rf GOST_TLS/gost/` и не выставлять переменные
   (см. `GOST_TLS/INSTRUCTION.md`, как это было установлено).
2. **Надстройка, а не замена.** `openssl_gost.cnf` первой строкой делает
   `.include /usr/lib/ssl/openssl.cnf` — вся системная конфигурация
   (TLS-политики, провайдеры) сохраняется, ГОСТ _добавляется_ сверху.
3. **Активация = три переменные окружения** (`OPENSSL_CONF`,
   `OPENSSL_ENGINES`, `OPENSSL_MODULES`). Никаких демонов, никакого состояния
   на диске, кроме самого каталога.
4. **Область действия — процесс.** Переменные наследуются дочерними
   процессами, но не «соседями»: сервер, активировавший GOST себе, никак не
   влияет на curl в другом окне терминала.
5. **Переносимость через рендер.** В конфиге путь к движку (`dynamic_path`)
   обязан быть абсолютным, поэтому хранится шаблон с плейсхолдером
   `@@GOST_DIR@@`, а рендер актуализируется автоматически при каждом
   GOST-запуске CA (`ca_lib.gost_env()`). Перенос каталога проекта окружение
   не ломает.

## 3. Взаимодействие GOST-VENV с конфигурацией openssl

Активация подменяет конфигурационный файл: `OPENSSL_CONF` указывает на
`GOST_TLS/gost/openssl_gost.cnf` вместо системного. Тот включает системный
конфиг и дополнительно регистрирует движок:

```ini
.include /usr/lib/ssl/openssl.cnf      # 1) всё системное — как было

openssl_conf = openssl_init            # 2) точка входа инициализации

[openssl_init]
engines = engine_section               # 3) + секция движков

[engine_section]
gost = gost_section

[gost_section]
engine_id = gost
dynamic_path = <GOST_DIR>/engines-3/gost.so   # абсолютный путь (из @@GOST_DIR@@)
default_algorithms = ALL               # ГОСТ-алгоритмы — для всех операций
CRYPT_PARAMS = id-tc26-gost-28147-param-Z     # S-box, совместимый с КриптоПро
```

Дальше всё происходит само: любой процесс, использующий libcrypto (openssl
CLI, curl, python `ssl`), при инициализации читает этот конфиг, подгружает
`gost.so`, и в нём появляются ГОСТ-алгоритмы и GOST-TLS-ciphersuites
(только TLS 1.2 — ограничение engine-механизма).

Благодаря абсолютному `dynamic_path` переменная `OPENSSL_ENGINES` строго
говоря избыточна, но выставляется для полноты (например, для
`openssl engine -t gost` по id без конфига).

### Два способа активации — один механизм

| Кто активирует            | Как                                       | На кого действует                                             |
| ------------------------- | ----------------------------------------- | ------------------------------------------------------------- |
| Пользователь в шелле      | `source GOST_TLS/gost/env.sh`             | текущий шелл и всё, что из него запущено (curl, openssl, ...) |
| Скрипты CA и HTTPS-сервер | `ca_lib.gost_env()` → `env=` в subprocess | только сами эти процессы и их вызовы openssl                  |

`gost_env()` делает то же, что `env.sh` (плюс перерендеривает конфиг из
шаблона), но возвращает словарь окружения, не трогая сессию пользователя.
**Поэтому запущенный GOST-сервер не означает, что ГОСТ есть у вашего
клиента**: для curl / `openssl s_client` окружение активируется отдельно,
в шелле клиента. Симптом неактивированного клиента — обрыв рукопожатия
`sslv3 alert handshake failure` (alert 40): у сервера только GOST-шифры,
у клиента их нет, общего шифра не нашлось.

## 4. Как активировать GOST-VENV

В текущем шелле (действует до закрытия шелла, на сессию):

```sh
source GOST_TLS/gost/env.sh
# GOST-TLS activated. OPENSSL_CONF=/home/alex/Prj/2_dev/python/ca/GOST_TLS/gost/openssl_gost.cnf
```

Разово, для одной команды (без изменения сессии):

```sh
env OPENSSL_CONF=$PWD/GOST_TLS/gost/openssl_gost.cnf openssl ciphers -v 'aGOST'
```

Скриптам CA и серверу `server_https/gost_https_server.py` ничего активировать не нужно, 
они делают это сами через `ca_lib.gost_env()`.
Для запуска отдельных команд bash `openssl s_client` или `curl` для поддержки gost активация требуется.

```sh
source GOST_TLS/gost/env.sh
echo | openssl s_client -connect 127.0.0.1:8443
curl -sk -o /dev/null -w '%{certs}' https://127.0.0.1:8443/health
```

Деактивация — снять переменные (или просто открыть новый шелл):

```sh
unset OPENSSL_CONF OPENSSL_ENGINES OPENSSL_MODULES
```

## 5. Как понять, что GOST-VENV активирован

Быстрая проверка переменных (у активированного шелла путь указывает внутрь
проекта):

```sh
echo "$OPENSSL_CONF"
# /home/alex/Prj/2_dev/python/ca/GOST_TLS/gost/openssl_gost.cnf
```

Проверка, что движок реально загружается (главный тест, его же выполняет
fail-fast `ca_lib.check_gost_engine`):

```sh
openssl engine gost -c -t
# (gost) Reference implementation of GOST engine
#  [gost89, gost89-cnt, ..., md_gost12_256, md_gost12_512,
#   gost2001, gost2012_256, gost2012_512, ...]
#      [ available ]
```

Без активации та же команда отвечает `invalid engine "gost"`.

Проверка, что GOST дошёл до TLS (появились ciphersuites; TLS 1.3-сьюты
openssl печатает всегда, поэтому фильтруем):

```sh
openssl ciphers -v 'aGOST' | grep GOST
# GOST2012-MAGMA-MAGMAOMAC           TLSv1.2 Kx=GOST18 ...
# GOST2012-KUZNYECHIK-KUZNYECHIKOMAC TLSv1.2 Kx=GOST18 ...
# без VENV: Error in cipher list / no cipher match
```

Проверка «в бою» — ГОСТ-хэш считается:

```sh
echo -n test | openssl dgst -md_gost12_256    # без VENV: unknown option
```

Тест окружения 10 проверок, (включая живое GOST-TLS-рукопожатие):

```sh
./GOST_TLS/check_gost_tls.sh
```

Smoke всей цепочки CA + TLS: `./utils/check_gost_ca.sh`.
