"""filesync — выборочный backup/sync файлов с удалённого хоста по SSH.

Набор утилит (см. wiki/todo/architecture.md):
  * get  (getfile)  — бэкап заданного набора файлов        remote -> local
  * diff (diffile) — сравнение + подтягивание дельты       remote -> local
  * put  (putfile)  — накат копии + установка прав          local  -> remote

Общее ядро — модуль `core`. Контракт обмена — manifest.json/csv.
"""

import logging

# Дисциплина библиотеки: набор не настраивает логирование на импорте, только
# точка входа (main → core.configure_logging). NullHandler гасит предупреждение
# «No handlers could be found», если core используют как библиотеку. См.
# wiki/docs/logging.md.
logging.getLogger("filesync").addHandler(logging.NullHandler())

__version__ = "0.1.0"
