# test_getfile — описание и руководство

Сквозной (e2e) автотест утилиты `get` на `pytest`: разворачивает фикстуру на удалённом хосте через [mkfixture](mkfixture.md), забирает её утилитой `get` и сверяет `manifest` с оракулом ожиданий.

> Полная спецификация — в [ТЗ test_getfile](../todo/done/test_getfile.md).

---

## Что делает

| Фаза | Действие |
|---|---|
| SETUP | копирует `mkfixture.py` на удалённый хост, запускает `sudo python3 mkfixture.py`, забирает `expectations.json` и `filelist.txt` **в обход get** |
| EXERCISE | запускает `get` с этим `filelist` против тестового хоста |
| VERIFY | сверяет `manifest.json` с оракулом: типы, права (4 цифры), uid/gid + имена (вкл. `UNKNOWN`), размер, MD5, target симлинков, mtime, статусы; полнота раскрытия директорий; отсутствие лишних записей; целостность `files/`; RO-режим метаданных |
| TEARDOWN | `mkfixture --clean` на хосте + удаление локальной тестовой сессии |

---

## Предпосылки

- **venv с pytest** (см. ниже);
- **выделенный тестовый хост** (НЕ прод!) с записью в `~/.ssh/config` и `sudo` без пароля;
- на хосте: `python3`, `find`, `stat`, `tar`, `md5sum`.

Без переменной `FILESYNC_TEST_HOST` тест помечается **skipped** (не падает).

---

## Подготовка venv

Один раз из корня репозитория:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install pytest
```

---

## Запуск

```bash
# основной вариант
FILESYNC_TEST_HOST=testbox ./.venv/bin/pytest tests/test_getfile.py -v

# с активацией окружения
source .venv/bin/activate
FILESYNC_TEST_HOST=testbox pytest tests/test_getfile.py -v

# оставить артефакты для разбора (не удалять при teardown)
FILESYNC_TEST_HOST=testbox FILESYNC_TEST_KEEP=1 ./.venv/bin/pytest tests/test_getfile.py -v

# без хоста — тесты будут SKIPPED
./.venv/bin/pytest tests/test_getfile.py -v
```

### Переменные окружения

| Переменная | По умолчанию | Описание |
|---|---|---|
| `FILESYNC_TEST_HOST` | — (**обязательна**) | алиас тестового хоста из `~/.ssh/config` |
| `FILESYNC_TEST_ROOT` | `/tmp/filesync_fixture` | корень фикстуры на удалённом хосте |
| `FILESYNC_TEST_KEEP` | `0` | `1` — не удалять артефакты после прогона |

---

## Состав тестов

| Тест | Проверяет |
|---|---|
| `test_all_cases_present` | каждый активный кейс оракула есть в manifest |
| `test_no_unexpected_entries` | в manifest нет лишних записей (биективность) |
| `test_metadata_matches_oracle` | совпадение полей метаданных по каждому кейсу |
| `test_content_integrity` | MD5 файлов в `files/` и target симлинков |
| `test_metadata_files_readonly` | `manifest.json/.csv`, `session.json` — RO `0444` |

---

## Стратегия

`get` — фундамент набора, поэтому покрыт автотестом. `diff`/`put` отдельных автотестов пока не имеют: они проверяются вручную на базе уже доверенного `get` (см. [architecture.md §6](../todo/architecture.md)).

---

## Типичные проблемы

| Симптом | Причина / решение |
|---|---|
| все тесты `SKIPPED` | не задан `FILESYNC_TEST_HOST` |
| skip с `mkfixture on remote failed (sudo?)` | на хосте нет `NOPASSWD` sudo |
| `pytest: command not found` | не активирован venv / используйте `./.venv/bin/pytest` |
| мismatch по `uid/owner` | имена субъектов на хосте отличаются — оракул берёт фактические значения, проверьте, что mkfixture отработал под root |
