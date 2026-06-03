# Описания и руководства (docs)

Пользовательские руководства по компонентам набора filesync: что делает, как запускать, варианты вызова, примеры, типичные проблемы.

Спецификации (ТЗ) лежат отдельно — в [../todo/](../todo/).

## Содержание

| Компонент | Руководство | ТЗ |
|---|---|---|
| **getfile** — backup заданного набора (remote → local) | [getfile.md](getfile.md) | [../todo/done/getfile.md](../todo/done/getfile.md) |
| **mkfixture** — генератор тестового дерева + оракул (на remote) | [mkfixture.md](mkfixture.md) | [../todo/done/mkfixture.md](../todo/done/mkfixture.md) |
| **test_getfile** — e2e-автотест для get | [test_getfile.md](test_getfile.md) | [../todo/done/test_getfile.md](../todo/done/test_getfile.md) |
| **diffile** — сравнение + подтягивание дельты (remote → local) | — | [../todo/done/diffile.md](../todo/done/diffile.md) |
| **putfile** — накат копии + установка прав (local → remote) | — | [../todo/done/putfile.md](../todo/done/putfile.md) |

## Сценарии и use-cases

- [usercases/](usercases/) — краткие кейсы (get / diff / put / get→правка→put): команды, результат, ключи и дефолты.
- [step_by_step.md](step_by_step.md) — подробный поток: забрать → отредактировать (контент в `files/` + права/владелец/группа в `restore.txt`) → накатить.

## На будущее (спроектировано, реализация позже)

- [opt_attr_fast_path.md](../todo/opt_attr_fast_path.md) — оптимизация put: заливать только изменённый контент, неизменённый брать из payload.
- [../todo/done/exclude_rules.md](../todo/done/exclude_rules.md) — спецификация правил исключения (ignore). **v1 реализован в `get`** (см. [UC5](usercases/uc5-get-exclude.md)); фаза 2 (негация `!`, `**`) — позже.

## Быстрый старт

```bash
# backup (get)
python -m filesync get ./files.txt <hostname> --prefix clusterA --suffix метка -p ./backups/

# дельта от baseline (diff)
python -m filesync diff ./backups/<session> <hostname> --suffix delta

# накат на хост (put): выбор+атрибуты из restore.txt сессии, контент из files/
python -m filesync put ./backups/<session> <hostname> --target-root /srv/restore --yes

# автотест get (нужен выделенный тестовый хост)
python3 -m venv .venv && ./.venv/bin/python -m pip install pytest
FILESYNC_TEST_HOST=testbox ./.venv/bin/pytest tests/test_getfile.py -v
```
