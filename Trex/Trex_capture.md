## 1. Встроенный захват пакетов в TRex

TRex имеет встроенный packet capture, работающий прямо на портах DPDK — без tcpdump и без остановки генерации.

### Через интерактивную консоль TRex

```bash
# Запускаем TRex в одном терминале
./t-rex-64 -f profile.py -c 4 --iom 0

# В другом терминале подключаемся к консоли
./trex-console
```

```python
# Внутри trex-console:

# Захват на Port 0 (исходящие запросы)
capture = client.start_capture(
    rx_ports=[0],      # входящие на порт 0
    tx_ports=[0],      # исходящие с порта 0
    limit=100,         # количество пакетов
    bpf_filter="udp"  # BPF-фильтр
)

# Захват на Port 1 (входящие ответы от RS)
capture = client.start_capture(
    rx_ports=[1],
    limit=100,
    bpf_filter="udp"
)

# Сохраняем в pcap
client.stop_capture(capture["id"], "/tmp/capture_port1.pcap")
```

Файл `.pcap` потом открывается в Wireshark — там видно все IP/MAC заголовки.

### Через Python API напрямую

```python
from trex_stl_lib.api import *

c = STLClient()
c.connect()
c.start(ports=[0])

# Включаем захват
capture_id = c.start_capture(
    rx_ports=[0, 1],
    tx_ports=[0],
    limit=200,
    bpf_filter="udp port 5000"
)["id"]

import time
time.sleep(5)  # даём поработать

# Снимаем и сохраняем
c.stop_capture(capture_id, "/tmp/test_capture.pcap")
c.stop()
c.disconnect()
```

---

## 2. Что видно в дампе — и что проверяем

### На Port 0 (tx) — проверяем запросы

```
Ethernet: src=MAC_Port0, dst=MAC_LB_ext
IP: src=CLIENT_IP, dst=VIP
UDP: sport=1234, dport=5000
```

Если `dst MAC` не тот — LB не примет пакет. Если `src IP` не тот — RS не знает, куда слать ответ.

### На Port 1 (rx) — проверяем ответы (DSR)

```
Ethernet: src=MAC_RS, dst=MAC_Port1
IP: src=VIP, dst=CLIENT_IP
UDP: sport=5000, dport=1234
```

Если пакеты сюда не приходят — DSR не работает. Если `src IP` не VIP — RS отвечает неправильным адресом.

---

## 3. Встроенная статистика TRex

Это первое, на что смотрят до захвата пакетов.

```python
# В trex-console
tui          # текстовый UI с live-статистикой
portattr     # атрибуты портов
stats        # сводная статистика

# Или программно
stats = c.get_stats()
print(stats[0])   # Port 0: opackets, obytes, ierrors...
print(stats[1])   # Port 1: ipackets, ibytes, ierrors...
```

Ключевые счётчики для DSR-теста:

| Счётчик | Порт | Что означает |
|---|---|---|
| `opackets` | 0 | отправлено запросов |
| `ipackets` | 1 | получено ответов (DSR работает) |
| `ierrors` | 0 или 1 | ошибки приёма |
| `tx_bps` / `rx_bps` | 0 / 1 | скорость в обоих направлениях |

Если `opackets[0]` растёт, а `ipackets[1]` = 0 — ответы не возвращаются, DSR сломан.

---

## 4. Внешние методы диагностики

TRex работает на DPDK и **обходит ядро Linux** — поэтому `tcpdump` на интерфейсах TRex не работает. Дампить нужно на других узлах.

### На LB — зеркалирование или tcpdump

```bash
# На входном интерфейсе LB — видим запросы от TRex
tcpdump -i eth0 -n "udp and dst 10.0.0.1" -w /tmp/lb_input.pcap

# На выходном интерфейсе LB — видим IPIP к RS
tcpdump -i eth1 -n "ip proto 4" -w /tmp/lb_ipip.pcap
# proto 4 = IPIP
```

### На RealServer

```bash
# На физическом интерфейсе — видим входящий IPIP
tcpdump -i eth0 -n "ip proto 4" -w /tmp/rs_input.pcap

# На loopback/tunnel — видим декапсулированный UDP
tcpdump -i tunl0 -n "udp" -w /tmp/rs_decap.pcap

# Исходящий ответ (src = VIP)
tcpdump -i eth0 -n "src 10.0.0.1" -w /tmp/rs_output.pcap
```

### Проверка маршрутизации ответа

```bash
# На RS — убедиться, что ответы уходят в сторону TRex Port 1
ip route get CLIENT_IP
# должен показать интерфейс смотрящий в сторону TRex Port 1

# Убедиться что VIP есть на loopback
ip addr show lo | grep VIP
```

---

## 5. Типовой порядок troubleshooting для DSR+IPIP

```
1. TRex stats: opackets[0] растёт?
   └─ Нет → проблема в генерации, смотрим профиль

2. tcpdump на LB eth0: пакеты приходят с правильным dst=VIP?
   └─ Нет → проблема в dst MAC или маршрутизации до LB

3. tcpdump на LB eth1: уходит IPIP (proto 4) к RS_PHY_IP?
   └─ Нет → LB не балансирует, смотрим конфиг LB

4. tcpdump на RS eth0 (proto 4): IPIP приходит?
   └─ Нет → проблема в сети между LB и RS

5. tcpdump на RS tunl0/lo: UDP виден после декапсуляции?
   └─ Нет → IPIP не декапсулируется, смотрим ip_forward и tunl0

6. tcpdump на RS eth0 (src=VIP): ответы уходят?
   └─ Нет → VIP не поднят на loopback RS или нет маршрута к CLIENT_IP

7. TRex stats: ipackets[1] растёт?
   └─ Нет → ответы уходят не туда (маршрут до CLIENT_IP ведёт не на Port 1 TRex)
   └─ Да → DSR работает корректно
```

Захват пакетов через TRex удобен для проверки шагов 1 и 7 — того, что реально улетает и прилетает на портах генератора. Всё между ними диагностируется внешними инструментами на самих узлах.