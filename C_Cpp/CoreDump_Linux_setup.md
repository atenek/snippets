##  Дамп памяти процесса **core dump** при его падении в Linux. 

Для включения **core dump** нужно настроить: 
  - лимиты, 
  - путь сохранения 
  - поведение ядра.

---

## 1. Разрешить core dump (ulimit)

По умолчанию он, как правило, отключён.

Проверить:

```bash
ulimit -c
```

Проверить в текущей сессии:

```bash
ulimit -c unlimited
```

---

## 2. Сделать настройку постоянной

Файл 
```bash
/etc/security/limits.conf
```

Добавить:
```
* soft core unlimited
* hard core unlimited
```

Для конкретного пользователя:
```
username soft core unlimited
username hard core unlimited
```

---

## 3. Проверить путь сохранения (core_pattern)

Linux может сохранять core dump в файл или передавать systemd.

Посмотреть текущую настройку:

```bash
cat /proc/sys/kernel/core_pattern
```

### Вариант A: обычный файл

Например:

```bash
 
```

Где:

* `%e` — имя программы
* `%p` — PID

Чтобы сделать постоянным:

```bash
sudo nano /etc/sysctl.conf
```

Добавь:

```
kernel.core_pattern=/tmp/core.%e.%p
```

Применить:

```bash
sudo sysctl -p
```

---

### Вариант B: через systemd (современные дистрибутивы)

Если `core_pattern` начинается с `|`, значит используется `systemd-coredump`.

Пример:

```
|/usr/lib/systemd/systemd-coredump ...
```

Тогда core dumps хранятся в журнале.

Посмотреть:

```bash
coredumpctl list
```

Информация:

```bash
coredumpctl info <PID>
```

Открыть в gdb:

```bash
coredumpctl gdb <PID>
```

---

## 4. Проверить права на запись

Программа должна иметь права записать файл в указанный каталог.

---

## 5. (Важно) Проверить setuid-бинарники

Для них core dump обычно отключён:

```bash
cat /proc/sys/fs/suid_dumpable
```

Разрешить (осторожно!):

```bash
echo 1 | sudo tee /proc/sys/fs/suid_dumpable
```

---

## 6. Протестировать

Например:

```c 
cat > fail.c
int main() {
    int *p = 0;
    *p = 42;
}
```

Скомпилировать и запустить:

```bash
gcc -g fail.c -o fail.bin
./fail.bin
```

После падения должен появиться core-файл.

---

## Частые проблемы

* `ulimit -c = 0` → дампы отключены
* systemd перехватывает дампы → использовать `coredumpctl`
* нет прав на запись
* контейнеры (Docker) → нужны доп. настройки (`--ulimit core=-1`)

---

