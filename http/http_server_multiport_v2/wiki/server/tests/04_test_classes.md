# Описание тест-классов

## TestMgmtAPI (14 тестов)

Тестирует Management API: структуру ответов, применение конфигов, валидацию.

| Тест | Что проверяет |
|---|---|
| `test_status_structure` | GET /status → 200, ключи server/rulesets_loaded/services, ip совпадает |
| `test_rulesets_structure` | GET /rulesets → 200, поля name/rules_count в каждом элементе |
| `test_rulesets_count_matches_files` | rules_count из /rulesets == len(rules) в JSON-файле |
| `test_all_rulesets_from_files_are_loaded` | Все rulesets/*.json загружены на сервере |
| `test_all_test_config_rulesets_loaded` | Все rulesets из test-config.json загружены |
| `test_mgmt_apply_and_status_reflect` | POST /mgmt → /status сразу отражает новый режим |
| `test_mgmt_null_stops_service` | mode=null → listening=False |
| `test_mgmt_hot_swap_ruleset` | Смена ruleset без остановки порта |
| `test_mgmt_validation_invalid_format` | service="62224" (без proto:) → 400 |
| `test_mgmt_validation_port_out_of_range` | port=9999 → 400 |
| `test_mgmt_validation_http_without_ruleset` | mode=http без ruleset → 400 |
| `test_mgmt_validation_unknown_ruleset` | ruleset="rules_nonexistent" → 400 |
| `test_mgmt_validation_udp_mode_on_tcp` | udp_echo на tcp-порту → 400 |
| `test_mgmt_validation_duplicate_service` | один service дважды → 400 |
| `test_favicon_returns_204` | GET /favicon.ico → 204 |
| `test_unknown_endpoint_returns_404` | GET /unknown-xyz → 404 |

---

## TestHTTPRules (параметризованный)

Для каждого обычного правила (с `response.code`) каждого HTTP-сервиса каждого сценария.

**Правила с `response.service` пропускаются** — они тестируются в TestStaticServe/TestStaticList.

| Тест | Что проверяет |
|---|---|
| `test_rule_match` | Код ответа, Content-Type, тело (text или JSON); переменные подставлены |
| `test_unmatched_path` | Путь не совпадает ни с одним rule → catch-all или 404 |

**hc-text правила** (body=string): `resp.text == exp_body`, Content-Type содержит `text/plain`.

**data-json правила** (body=dict):
- Content-Type = `application/json`
- Ответ = `{"body": {...}}`
- Все ключи присутствуют
- Поля без `$` совпадают точно
- Поля с `$` не содержат `$` в значении (переменная подставлена)

---

## TestStaticServe (10 тестов, параметризованный)

Тестирует `response.service = "static_serve"` — раздачу файлов с rate limit.

| Тест | Что проверяет |
|---|---|
| `test_download_existing_file` | GET /download/test_text.txt → 200; контент совпадает с диском; Content-Length корректен |
| `test_download_binary_file` | GET /download/test_binary.bin → 200; бинарный контент без искажений |
| `test_download_headers` | Content-Disposition (имя файла), X-Rate-Limit, Content-Length присутствуют |
| `test_download_default_rate_in_header` | Без ?rate= → X-Rate-Limit содержит default_rate_kb из ruleset |
| `test_download_custom_rate_param` | ?rate=50 → X-Rate-Limit: 50 KB/s |
| `test_download_rate_capped_at_max` | ?rate=99999 → X-Rate-Limit: max_rate_kb (500) |
| `test_download_missing_file` | GET несуществующего файла → 404 |
| `test_path_traversal_blocked` | /download/../startup-config.json → 404 (os.path.basename блокирует) |
| `test_empty_path_fallback_to_listing` | GET /download/ (пустое имя) → 200 JSON листинг |
| `test_regular_rules_coexist` | Обычные правила (/health) работают рядом со static_serve |

---

## TestStaticList (3 теста, параметризованный)

Тестирует `response.service = "static_list"` — JSON листинг директории.

| Тест | Что проверяет |
|---|---|
| `test_list_returns_200_json` | GET /files → 200, Content-Type: application/json, поля files/count |
| `test_list_contains_expected_files` | Набор файлов совпадает с реальным содержимым `files_dir` |
| `test_list_entry_fields` | Каждый элемент имеет name, size (int≥0), type, modified |

---

## TestTCPEcho (параметризованный)

| Тест | Что проверяет |
|---|---|
| `test_echo_short` | Короткая строка → получена обратно байт-в-байт |
| `test_echo_large` | 8 KB буфер → полностью эхируется |
| `test_echo_multiple_connections` | 3 последовательных соединения — каждое эхируется независимо |

---

## TestTCPLogger (параметризованный)

| Тест | Что проверяет |
|---|---|
| `test_log_file_created` | После подключения файл `logs/tcp_<port>_*.log` существует |
| `test_log_format` | Файл содержит `=== CONNECT`, `=== DISCONNECT`, `src=`, raw payload |
| `test_new_log_file_after_reassign` | Переназначение режима → новый run_id в имени файла |

---

## TestUDPEcho (параметризованный)

| Тест | Что проверяет |
|---|---|
| `test_echo_datagram` | Одна датаграмма → возвращена без изменений |
| `test_echo_multiple_datagrams` | 5 датаграмм подряд — каждая эхируется независимо |

---

## TestUDPLogger (параметризованный)

| Тест | Что проверяет |
|---|---|
| `test_log_file_created` | Файл `logs/udp_<port>_*.log` появляется после датаграммы |
| `test_log_format` | Строка содержит `src=`, `len=`, `data=`, hex-представление payload |

---

## TestNullServices (параметризованный)

| Тест | Что проверяет |
|---|---|
| `test_tcp_port_closed` | После mode=null TCP-соединение бросает OSError (connection refused) |

---

## TestStartupConfigs (6 тестов)

По одному тесту на каждый файл из `test_config/startup/`.

| Тест | Что проверяет |
|---|---|
| `test_config_is_applicable` | Конфиг применяется через POST /mgmt (успех 200), /status совпадает с файлом |

Для конфигов с множеством сервисов таймаут на POST /mgmt масштабируется: `max(5, N*2+3)` секунд.

---

## TestConfigSaveLoad (3 теста)

| Тест | Что проверяет |
|---|---|
| `test_save_returns_success` | POST /config/save → 200 success |
| `test_save_load_roundtrip` | Apply → save → apply другой конфиг → load → /status совпадает с сохранённым |
| `test_load_missing_config_returns_404` | POST /config/load когда файла нет → 404 |

`test_save_load_roundtrip` использует таймаут 20с для `/config/load` (остановка + запуск сервисов занимает ~2–4с).
