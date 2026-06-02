# Тест-сценарии (test-config.json)

Файл: `test_config/test-config.json`  
Ключ: `tests_configs` — массив сценариев. Каждый сценарий — объект, где ключи — идентификаторы сервисов (`tcp:NNNNN` / `udp:NNNNN`), значения — конфигурация режима.

Поле `_comment` в каждом сценарии игнорируется тестами (мета-информация).

---

## Сценарий 0: tcp_echo + udp_echo на всех портах

```json
{
  "_comment": "Сценарий 0: tcp_echo + udp_echo на всех портах",
  "tcp:62224": {"mode": "tcp_echo"}, "udp:62224": {"mode": "udp_echo"},
  "tcp:62225": {"mode": "tcp_echo"}, "udp:62225": {"mode": "udp_echo"},
  "tcp:62226": {"mode": "tcp_echo"}, "udp:62226": {"mode": "udp_echo"},
  "tcp:62227": {"mode": "tcp_echo"}, "udp:62227": {"mode": "udp_echo"}
}
```

Тестирует TCP echo (8 портов × 3 теста = 24) и UDP echo (8 × 2 = 16).  
Максимальное покрытие echo-режимов.

---

## Сценарий 1: hc-text рулесеты (разные HTTP-коды)

```json
{
  "_comment": "Сценарий 1: hc-text рулесеты (text/plain, разные коды)",
  "tcp:62224": {"mode": "http", "ruleset": "rules_hc-text_200_ok"},
  "tcp:62225": {"mode": "http", "ruleset": "rules_hc-text_500_fail"},
  "tcp:62226": {"mode": "http", "ruleset": "rules_hc-text_201_maint"}
}
```

Тестирует HTTP text/plain ответы: код 200, 500, 201; тела "ok", "fail", "maint".  
Проверяется совпадение `resp.text == exp_body`.

---

## Сценарий 2: data-json рулесеты (JSON + подстановка переменных)

```json
{
  "_comment": "Сценарий 2: data-json рулесеты (application/json + подстановка переменных сессии)",
  "tcp:62224": {"mode": "http", "ruleset": "rules_data-json_200_ok"},
  "tcp:62225": {"mode": "http", "ruleset": "rules_data-json_500_fail"},
  "tcp:62226": {"mode": "http", "ruleset": "rules_data-json_201_maint"}
}
```

Тестирует JSON-тела с переменными `$SRC_IP`, `$SRC_PORT`, `$DST_IP`, `$DST_PORT`.  
Проверяется: Content-Type=application/json, все ключи присутствуют, переменные подставлены (нет `$` в значениях).

---

## Сценарий 3: смешанные hc+data рулесеты (LB-сценарий)

```json
{
  "_comment": "Сценарий 3: пары hc+data — основной сценарий тестирования LB",
  "tcp:62224": {"mode": "http", "ruleset": "rules_hc-text_500_ok_maint"},
  "tcp:62225": {"mode": "http", "ruleset": "rules_data-json_500_ok_maint"},
  "tcp:62226": {"mode": "http", "ruleset": "rules_hc-text_200_fail"},
  "tcp:62227": {"mode": "http", "ruleset": "rules_data-json_200_fail"}
}
```

Имитация типового LB-сценария: разные коды и тела на разных бэкендах.  
Тестирует сочетание `code=500 body=maint`, `code=200 body=fail`.

---

## Сценарий 4: логгеры

```json
{
  "_comment": "Сценарий 4: логгеры",
  "tcp:62224": {"mode": "tcp_logger"},
  "tcp:62225": {"mode": "tcp_logger"},
  "udp:62224": {"mode": "udp_logger"},
  "udp:62225": {"mode": "udp_logger"}
}
```

Тестирует tcp_logger и udp_logger: создание файлов, формат записей, уникальность run_id.

---

## Сценарий 5: все порты выключены

```json
{
  "_comment": "Сценарий 5: все порты выключены",
  "tcp:62224": {"mode": "off"},
  "tcp:62225": {"mode": "off"},
  "tcp:62226": {"mode": "off"}
}
```

`"mode": "off"` нормализуется в `null`. Тестирует что TCP-порт отклоняет соединения (connection refused).

---

## Сценарий 6: static file server с rate limit

```json
{
  "_comment": "Сценарий 6: static file server с rate limit",
  "tcp:62224": {"mode": "http", "ruleset": "rules_static_serve"}
}
```

Единственный сервис с ruleset `rules_static_serve`. Тестирует весь функционал:
- GET `/download/test_text.txt` → 200, контент совпадает
- GET `/download/test_binary.bin` → 200, бинарный контент без искажений
- X-Rate-Limit, Content-Disposition заголовки
- `?rate=50` применяется, `?rate=99999` обрезается до `max_rate_kb=500`
- Missing file → 404
- Path traversal заблокирован
- GET `/download/` (пустое имя) → листинг
- GET `/files` → JSON листинг с name/size/type/modified
- Обычные правила (/health) работают рядом со static_serve

---

## Добавление нового сценария

```json
{
  "_comment": "Сценарий N: описание",
  "tcp:62224": {"mode": "http", "ruleset": "rules_my_new_ruleset"},
  "tcp:62225": {"mode": "tcp_echo"}
}
```

Добавить в массив `tests_configs` в `test_config/test-config.json`. Тесты подхватят автоматически при следующем запуске.
