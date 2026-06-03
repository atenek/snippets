# getfile — описание и руководство

Резервное копирование **заданного набора** файлов/директорий с удалённого Linux-хоста на локальную машину по SSH, с метаданными и MD5-верификацией.

> Это пользовательское руководство. Полная спецификация (формат метаданных, edge-кейсы) — в [ТЗ getfile](../todo/getfile.md).

---

## Что делает

1. Читает локальный список путей (`filelist`).
2. Подключается к удалённому хосту по SSH (запись в `~/.ssh/config`).
3. Раскрывает директории (`sudo find`), собирает метаданные (`sudo stat`/`md5sum`/`readlink`), забирает данные одним `sudo tar`.
4. Складывает результат в директорию сессии: browsable-зеркало `files/`, архив `payload.tar`, метаданные `manifest.json` + `manifest.csv` + `session.json`.
5. Верифицирует локальные копии по MD5 и печатает статистику.

Файлы, недоступные текущему пользователю, забираются через `sudo` на удалённой стороне.

---

## Предпосылки

**Локально:** `python3` (3.10+), `ssh`, `tar`.

**На удалённом хосте:**
- запись в `~/.ssh/config` с ключевой аутентификацией (без пароля);
- `sudo` **без пароля** (NOPASSWD) для: `find`, `stat`, `tar`, `md5sum`, `readlink`. Пример строки sudoers:
  ```
  backupuser ALL=(ALL) NOPASSWD: /usr/bin/find, /usr/bin/stat, /usr/bin/tar, /usr/bin/md5sum, /usr/bin/readlink
  ```

---

## Запуск

Из корня репозитория. Три равнозначных способа:

```bash
# 1) через единый вход (подкоманда get)
python -m filesync get <filelist> <hostname> [-m МЕТКА] [-p ПАПКА]

# 2) напрямую модулем
python filesync/getfile.py <filelist> <hostname> [-m МЕТКА] [-p ПАПКА]

# 3) с виртуальным окружением проекта
./.venv/bin/python -m filesync get <filelist> <hostname>
```

### Аргументы

| Аргумент | Обяз. | По умолчанию | Описание |
|---|---|---|---|
| `filelist` | да | — | локальный файл со списком удалённых путей |
| `hostname` | да | — | имя хоста/IP (запись в `~/.ssh/config`) |
| `-m`, `--message` | нет | `""` | метка (alias) в имени папки сессии |
| `-p`, `--path` | нет | `../backup_files/` | базовая директория для сохранения |

### Примеры

```bash
# минимально
python -m filesync get ./files.txt prod-01

# с меткой и своим каталогом
python -m filesync get ./files.txt prod-01 -m before_update -p /data/backups/
```

---

## Формат filelist

Одна строка = один абсолютный путь на удалённом хосте. Пустые строки и строки, начинающиеся с `#`, игнорируются.

```
# конфигурация nginx
/etc/nginx/nginx.conf
/etc/nginx/conf.d/

# системные файлы
/etc/hosts
/etc/shadow
```

---

## Что создаётся

```
{папка}/{hostname}__{ГГГГ-ММ-ДД_ЧЧ-ММ-СС}__{метка}/
├── files/            # browsable-зеркало (распаковано не от root)
├── payload.tar       # точный архив (для restore: tar -xp --numeric-owner -C /target)
└── metadata/         # read-only (0444)
    ├── session.json  # параметры и статистика сессии
    ├── manifest.json # метаданные всех объектов (авторитетный)
    └── manifest.csv  # та же информация плоско — для Calc/Excel/pandas
```

Файлы метаданных создаются **только для чтения** — они не предназначены для правки.

---

## Коды возврата

| Код | Значение |
|---|---|
| `0` | всё успешно, пропусков нет |
| `1` | ошибка запуска (нет filelist / пустой / SSH недоступен) |
| `2` | завершено, но есть пропуски: `not_found` / `no_permission` / `failed` / непройденная верификация / недоступные каталоги |

---

## Пример вывода

```
=================================================
  Host:    prod-01
  Label:   before_update
  Session: /data/backups/prod-01__2026-06-02_14-30-00__before_update
-------------------------------------------------
  Processed:        25
    Copied OK:      22
    Metadata only:   2
    No permission:   1
    Not found:       0
    Failed:          0
-------------------------------------------------
  Verification:
    OK:             22
    Present:         2
    Missing:         0
    MD5 mismatch:    0
=================================================
```

---

## Типичные проблемы

| Симптом | Причина / решение |
|---|---|
| `error: ... ssh ... Permission denied` | хост не в `~/.ssh/config` или нет ключа |
| `find failed: sudo: a password is required` | не настроен `NOPASSWD` для нужных команд |
| всё в `no_permission` | sudo не отрабатывает на remote — проверьте sudoers |
| `local tar not available` | поставьте `tar` на локальной машине |
| `Dir unreadable` в сводке | каталог не удалось перечислить даже под sudo (FUSE/NFS/MAC) — содержимое могло быть пропущено |

---

## Проверка качества

Поведение `get` покрыто автотестом — см. [руководство test_getfile](test_getfile.md).
