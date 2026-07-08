# server_https — тестовый HTTPS-сервер с GOST-TLS (user_story_003)

Простой сервер для проверки сертификатов, выпущенных этим CA в криптопрофилях
**gost-256** и **gost-512**. Отвечает `200 OK` на `GET /health`, предъявляет
клиенту цепочку ee+im+root. Только stdlib python + bash/curl, всё крипто —
gost-engine из `GOST_TLS/` (сервер сам выставляет `OPENSSL_CONF/ENGINES/MODULES`
через `ca_lib.gost_env()`, отдельной активации не требует).

Сервер не различает gost-256 и gost-512: алгоритм определяется самим
сертификатом, TLS-ciphersuites GOST согласуются автоматически (только TLS 1.2 —
ограничение engine, см. `GOST_TLS/`).

## Предпосылки

Выпущенная gost-цепочка root → im → ee с **серверным** шаблоном
(`openssl_endentity_server_gost.cnf` или `..._clientserver_gost.cnf` —
в них есть `extendedKeyUsage = serverAuth` и `subjectAltName`):

```sh
python3 rootCA/mgmt/rootCA_init.py     --profile gost-256 --cn myroot
python3 imCA/mgmt/imCA_init.py         --profile gost-256 --cn myim
python3 endentity/mgmt/endentity_init.py --profile gost-256 --cn myserver
```

Для gost-512 — то же с `--profile gost-512`.

## Запуск сервера

```sh
# Сертификат по умолчанию — свежайший ee из certificates/gost/ee/endentity_cert
python3 server_https/gost_https_server.py

# Явно указать сертификат/ключ, адрес и порт
python3 server_https/gost_https_server.py \
    --cert /home/alex/Prj/2_dev/python/ca/certificates/gost/ee/endentity_cert/certs/galex-01.crt \
    --key  /home/alex/Prj/2_dev/python/ca/certificates/gost/ee/endentity_cert/private/galex-01.key \
    --host 0.0.0.0 --port 8443
```

Если рядом с сертификатом лежит `<имя>-chain.crt`, сервер предъявляет всю
цепочку — клиенту для проверки достаточно одного корневого сертификата.
Тестовое хранилище (как в смоук-тестах) подставляется env `CA_CERT_BASE`.
Passphrase ключа (если ключ зашифрован) спрашивается на старте.

## Проверка клиентом (curl)

curl использует системный OpenSSL, поэтому GOST-окружение нужно активировать
и в шелле клиента (иначе handshake не состоится — у клиента нет GOST-шифров):

```sh
source GOST_TLS/gost/env.sh
```

### GET /health

```sh
# Быстрая проверка без валидации сертификата
curl -k https://127.0.0.1:8443/health

# Полная проверка: доверие от корня CA + имя сервера из subjectAltName.
# В шаблоне server_gost SAN = server1.lbosse.ru и др.; --resolve направляет
# это имя на адрес тестового сервера.
curl --cacert certificates/gost/root/root_cert/certs/myroot-01.crt \
     --resolve server1.lbosse.ru:8443:127.0.0.1 \
     https://server1.lbosse.ru:8443/health
```

Ответ: `200 ok`, HTTP-код 200. Любой другой путь — 404.

### Получение сертификата сервера

```sh
# Вся предъявленная цепочка (ee+im+root) в PEM — writeout-переменная %{certs}
curl -sk -o /dev/null -w '%{certs}' https://127.0.0.1:8443/health > server_cert.pem

# Альтернатива через openssl (только листовой сертификат)
echo | openssl s_client -connect 127.0.0.1:8443 2>/dev/null | openssl x509 > server_cert.pem
```

### Просмотр полученного сертификата

```sh
# Утилитой проекта (кратко: -s; полностью: без -s)
python3 utils/cert_view.py -s --gost server_cert.pem

# Напрямую openssl: subject, издатель, алгоритм подписи, SAN
openssl x509 -in server_cert.pem -noout -subject -issuer -ext subjectAltName
openssl x509 -in server_cert.pem -noout -text | grep "GOST"
```

В подписи должно быть `GOST R 34.10-2012 with GOST R 34.11-2012 (256 bit)`
(или `512 bit` для профиля gost-512); в логе сервера на каждый запрос
печатается согласованный GOST-шифр (например, `GOST2012-MAGMA-MAGMAOMAC`).
