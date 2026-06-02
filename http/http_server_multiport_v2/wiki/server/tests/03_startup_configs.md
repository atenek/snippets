# Тестовые startup-конфиги

Директория: `test_config/startup/`

Каждый файл описывает набор сервисов, который применяется через `POST /mgmt` в тесте `TestStartupConfigs::test_config_is_applicable`. Конфиги служат двум целям:
1. **Документация** — показывают типовые конфигурации для разных режимов использования.
2. **Тестирование** — верифицируют, что каждая комбинация режимов применима и отражается в `/status`.

Формат совпадает с `startup-config.json` (см. [../04_startup_config.md](../04_startup_config.md)).

---

## startup_http_only.json

```json
{
  "tcp:62224": {"mode": "http", "ruleset": "rules_hc-text_200_ok"},
  "tcp:62225": {"mode": "http", "ruleset": "rules_hc-text_500_fail"},
  "tcp:62226": {"mode": "http", "ruleset": "rules_data-json_200_ok"},
  "tcp:62227": {"mode": "http", "ruleset": "rules_static_serve"}
}
```

**Назначение:** все порты в HTTP-режиме с разными rulesets.  
Покрывает: hc-text 200, hc-text 500, data-json, static_serve — всё на HTTP одновременно.  
Типичный сценарий: имитация нескольких разных бэкендов для LB.

---

## startup_echo_only.json

```json
{
  "tcp:62224": {"mode": "tcp_echo"}, "tcp:62225": {"mode": "tcp_echo"},
  "tcp:62226": {"mode": "tcp_echo"}, "udp:62224": {"mode": "udp_echo"},
  "udp:62225": {"mode": "udp_echo"}, "udp:62226": {"mode": "udp_echo"}
}
```

**Назначение:** все порты в echo-режиме (TCP и UDP).  
Покрывает: tcp_echo × 3, udp_echo × 3.  
Типичный сценарий: проверка TCP/UDP connectivity, измерение RTT, тест балансировщика.

---

## startup_logger_only.json

```json
{
  "tcp:62224": {"mode": "tcp_logger"}, "tcp:62225": {"mode": "tcp_logger"},
  "udp:62224": {"mode": "udp_logger"}, "udp:62225": {"mode": "udp_logger"}
}
```

**Назначение:** все порты в режиме логирования.  
Покрывает: tcp_logger × 2, udp_logger × 2.  
Типичный сценарий: захват трафика нескольких клиентов, анализ запросов до и после LB.

---

## startup_static_serve.json

```json
{
  "tcp:62224": {"mode": "http", "ruleset": "rules_static_serve"},
  "tcp:62225": {"mode": "http", "ruleset": "rules_hc-text_200_ok"}
}
```

**Назначение:** один порт — файловый сервер с rate limit, второй — обычный HTTP.  
Покрывает: static_serve + static_list на одном порту, совместно с regular HTTP.  
Типичный сценарий: раздача тестовых файлов клиентам с контролем скорости.

---

## startup_mixed.json

```json
{
  "tcp:62224": {"mode": "http",       "ruleset": "rules_hc-text_200_ok"},
  "tcp:62225": {"mode": "tcp_echo"},
  "tcp:62226": {"mode": "tcp_logger"},
  "udp:62224": {"mode": "udp_echo"},
  "udp:62225": {"mode": "udp_logger"},
  "tcp:62227": null
}
```

**Назначение:** одновременно все типы сервисов.  
Покрывает: http, tcp_echo, tcp_logger, udp_echo, udp_logger, null — по одному.  
Типичный сценарий: полная инициализация тест-стенда для разностороннего тестирования.

> **Примечание:** при применении через POST /mgmt таймаут увеличивается пропорционально числу сервисов (6 × 2 + 3 = 15с), т.к. каждый stop занимает до 1с.

---

## startup_all_null.json

```json
{
  "tcp:62224": null,
  "tcp:62225": null,
  "tcp:62226": null,
  "tcp:62227": null
}
```

**Назначение:** все сервисы остановлены.  
Покрывает: mode=null для всех портов.  
Типичный сценарий: сброс состояния перед новой конфигурацией.

---

## Отношение к production startup-config.json

| Файл | Назначение |
|---|---|
| `startup-config.json` | Production-конфиг: применяется при старте сервера автоматически |
| `test_config/startup/*.json` | Тестовые конфиги: применяются через `POST /mgmt` в тестах, не влияют на автостарт |

Тестовые конфиги не перезаписывают `startup-config.json`. Они применяются "на лету" через Management API.

---

## Добавление нового тестового startup-конфига

1. Создать JSON-файл в `test_config/startup/` в формате startup-config.
2. Тест `TestStartupConfigs::test_config_is_applicable` подхватит его автоматически.

```bash
cat > test_config/startup/startup_my_config.json << 'EOF'
{
  "_comment": "Описание конфига",
  "tcp:62224": {"mode": "http", "ruleset": "rules_hc-text_200_ok"},
  "tcp:62225": {"mode": "tcp_echo"}
}
EOF
```
