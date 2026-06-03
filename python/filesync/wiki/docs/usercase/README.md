# Use-cases

Краткие сценарии работы: действия и команды пользователя, ожидаемый результат,
справочник ключей и значений по умолчанию. Хост в примерах — `192.168.234.129`.

| # | Кейс | Поток | Файл |
|---|---|---|---|
| UC1 | **get** — забрать набор с хоста | HOST → local | [uc1-get.md](uc1-get.md) |
| UC2 | **diff** — сравнить копию с хостом + дельта | local ↔ HOST | [uc2-diff.md](uc2-diff.md) |
| UC3 | **put** — накатить копию на хост | local → HOST | [uc3-put.md](uc3-put.md) |
| UC4 | **get → правка → put** | HOST → local* → HOST | [uc4-get-modify-put.md](uc4-get-modify-put.md) |
| UC5 | **get с исключениями** (ignore) | HOST → local | [uc5-get-exclude.md](uc5-get-exclude.md) |

Подробный разбор UC4 с проверкой — в [../step_by_step.md](../step_by_step.md).
Исходный список кейсов — [../usercases.md](../usercases.md).
