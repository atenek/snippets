## Просмотр всех capabilities с именами

### 1. Самый простой способ — `capsh --print`

```bash
capsh --print
```
```
Current: =ep
Bounding set =cap_chown,cap_dac_override,cap_net_raw,...
Ambient set =
Securebits: 00/0x0/1'b0
 secure-noroot: no (unlocked)
uid=0(root)
gid=0(root)
```

---

### 2. Полный список всех известных capabilities ядру

```bash
capsh --print | grep Bounding
```

Или через `/proc/sys/kernel/cap_last_cap` — номер последней capability:

```bash
# Узнать сколько capabilities поддерживает текущее ядро
cat /proc/sys/kernel/cap_last_cap
# 40

# Вывести все capability с номерами через capsh
for i in $(seq 0 $(cat /proc/sys/kernel/cap_last_cap)); do
    echo "$i: $(capsh --decode=$(printf '%x' $((1 << i))) 2>/dev/null | grep -o 'cap_[a-z_]*')"
done
```

---

### 3. Через `man capabilities` — самый полный источник

```bash
man capabilities
```

---

### 4. Расшифровать hex-маску конкретного процесса

```bash
# Взять маску из /proc
grep CapEff /proc/<PID>/status
# CapEff: 000001fffeffffff

# Расшифровать
capsh --decode=000001fffeffffff
# 0x000001fffeffffff=cap_chown,cap_dac_override,...,cap_bpf,cap_checkpoint_restore
```

---

### 5. Прямо из заголовочного файла ядра — исчерпывающий источник

```bash
grep -E '#define CAP_' /usr/include/linux/capability.h
```
```
#define CAP_CHOWN            0
#define CAP_DAC_OVERRIDE     1
#define CAP_DAC_READ_SEARCH  2
#define CAP_FOWNER           3
...
#define CAP_CHECKPOINT_RESTORE 40
```

---

### 6. Одной командой — таблица номер + имя + описание из man

```bash
man capabilities | col -b | grep -E '^\s+CAP_' | head -50
```

---

### Итоговая шпаргалка

| Задача | Команда |
|---|---|
| Все caps текущего процесса | `capsh --print` |
| Расшифровать hex-маску | `capsh --decode=<hex>` |
| Все caps ядра с номерами | `grep CAP_ /usr/include/linux/capability.h` |
| Caps конкретного файла | `getcap /path/to/bin` |
| Caps конкретного процесса | `grep Cap /proc/<PID>/status` + `capsh --decode` |
| Количество caps в ядре | `cat /proc/sys/kernel/cap_last_cap` |


`grep Cap /proc/<PID>/status` + `capsh --decode`

Вариант 1 — bash однострочник

grep Cap /proc/<PID>/status | while read name hex; do
    printf "%-12s %s\n" "$name" "$(capsh --decode=$hex)"
done

Вариант 2 — с заголовком и выравниванием

PID=<PID>; grep Cap /proc/$PID/status | while read name hex; do
    caps=$(capsh --decode=$hex | cut -d= -f2)
    printf "%-14s %s\n    %s\n\n" "$name" "$hex" "${caps:--none-}"
done


Пакет для установки если нет `capsh`:
```bash
apt install libcap2-bin   # Debian/Ubuntu
yum install libcap        # RHEL/CentOS
```
