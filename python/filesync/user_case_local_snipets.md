```shell
python3 -m filesync get local_snippets.txt --exclude .syncignore --local --prefix PREFIX_snippets_ --suffix _snippets_SUFFIX -p /tmp/snippets_backups/ --no-sudo
```

#ToDo-0
При запуске не применились правила исключений для [--exclude .syncignore]
путь и команда запуска указаны в строке ниже: 
alex@i5ubu24:~/Prj/snippets/python/filesync$ python3 -m filesync get local_snippets.txt --exclude .syncignore --local --prefix PREFIX_snippets_ --suffix _snippets_SUFFIX -p /tmp/snippets_backups/ --no-sudo

Проанализируй команду, проверь её корректность и доступность файлов указанных в ключах файлов при запуске из указанного пути ~/Prj/snippets/python/filesync 
проанализируй результат в /tmp/snippets_backups/PREFIX_snippets__i5ubu24__2026-06-03_17-30-44__snippets_SUFFIX/ 
согласно настройкам исключений быть не должно ветки с именем 
/tmp/snippets_backups/PREFIX_snippets__i5ubu24__2026-06-03_17-30-44__snippets_SUFFIX/files/home/alex/Prj/snippets/python/venv/
Но она есть. Проанализируй почему она появилась и не обработали правила исключений. 
Проверь почему нерабочий код успешно прошёл тесты

#ToDo-1
в restore.txt данные в поле <type> (dir / file / symlink) сократить до 1 символа (d / f / l)

#ToDo-2
Требуется добавить в утилиту filesync getfile.py логирование.
Для логирования использовать python logging с dict-настройкой

Предусмотреть ключ --logging и значения:
NONE  - логирование отключено
ERROR - логирование уровня WARN записи о ERROR-событиях
WARN  - логирование уровня WARN записи о WARN-событиях
INFO  - (default) логирование уровня INFO записи о факте сохранения данных или мета-информации для файлового объекта (f/d/l) 
DEBUG - логирование уровня DEBUG. Подробные записи о шагах обработки, проверках и решениях принимаемых на каждом шаге с информацией о причине решения.

Требуется проанализировать аспекты логирования. 
Составить правила (конвенкцию) для проекта о использовании логирования.
Отразить её в виде документа и составить ТехЗадание на реализацию логирования.

