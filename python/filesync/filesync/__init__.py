"""filesync — выборочный backup/sync файлов с удалённого хоста по SSH.

Набор утилит (см. wiki/todo/architecture.md):
  * get  (getfile)  — бэкап заданного набора файлов        remote -> local
  * diff (diffile) — сравнение + подтягивание дельты       remote -> local
  * put  (putfile)  — накат копии + установка прав          local  -> remote

Общее ядро — модуль `core`. Контракт обмена — manifest.json/csv.
"""

__version__ = "0.1.0"
