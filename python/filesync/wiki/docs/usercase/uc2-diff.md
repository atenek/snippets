# UC2 — diff: сравнить локальную копию с хостом и подтянуть дельту

`HOST_LOCAL1 ↔ HOST2` (хост сравнения может отличаться от исходного)

## Действия пользователя

1. Иметь baseline-сессию (вывод get, см. [UC1](uc1-get.md)).
2. Запустить diff против хоста:
   ```bash
   python -m filesync diff ./backups/192.168.234.129__<дата>__message 192.168.234.129 --suffix delta
   ```
   Хост-аргумент переопределяет хост из baseline → можно сравнивать с **другим**
   хостом (`HOST2`). Без аргумента берётся хост из baseline.

## Ожидаемый результат (кратко)

Создаётся отдельная **diff-сессия** `..._delta__diff/` (baseline не меняется):
- `files/` + `*.tar` — **только** подтянутые (изменённые + новые);
- `metadata/manifest.json|.csv` — **полный** список с полем `diff` по каждому пути;
- `metadata/diff_report.txt` — сводка по группам.

В консоли: `unchanged / content changed (pulled) / metadata changed / new (pulled)
/ deleted / unreadable` и `pulled & verified N/M`.

Если файл метаданных baseline не RO — печатается предупреждение, что метаданные
могли быть изменены.

## Справочно: ключи и значения по умолчанию

| Ключ | По умолчанию | Описание |
|---|---|---|
| `baseline_session` (поз.) | — (обязателен) | путь к локальной сессии getfile |
| `hostname` (поз.) | из `baseline/metadata/session.json` | хост сравнения (здесь `192.168.234.129`) |
| `--prefix` / `--suffix` | `""` | префикс/суффикс имени diff-сессии |
| `-p`, `--path` | рядом с baseline | базовая папка для diff-сессии |
| `-f`, `--filelist` | из baseline `session.json` (иначе — пути baseline) | список для повторного раскрытия (новые файлы) |
| `--no-pull` | off (тянем дельту) | только отчёт, без скачивания |
| `--check-mtime` | off (mtime игнорируется) | считать разницу mtime расхождением метаданных |

Минимальный вызов: `python -m filesync diff ./backups/<session>` → хост и filelist
из baseline, дельта подтягивается, mtime не учитывается.

> diff только читает на хосте (`find/stat/tar/md5sum`); запись не выполняется.
