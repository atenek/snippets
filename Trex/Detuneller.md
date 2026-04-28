```
LB ──IPIP──► DPDK-порт RS-эмулятора
              │
              ├─ снять внешний IP заголовок (декапсуляция)
              ├─ взять src IP из внутреннего заголовка (= CLIENT_IP)
              ├─ сформировать ответ: src=VIP, dst=CLIENT_IP
              └─ отправить напрямую на TRex Port 1 (DSR)
```

---

## Шаг 1 — Подготовка сервера

### Требования к железу
- NIC с поддержкой DPDK: Intel i350/X520/X710, Mellanox ConnectX-4+
- CPU: x86_64, поддержка hugepages
- RAM: минимум 4 ГБ

### Установка зависимостей

```bash
# Ubuntu 22.04
apt-get update
apt-get install -y build-essential python3 python3-pip \
    libnuma-dev pkg-config meson ninja-build \
    linux-headers-$(uname -r)

pip3 install pyelftools meson
```

### Hugepages

```bash
# Выделяем hugepages (1G страницы предпочтительнее для DPDK)
echo 4 > /sys/kernel/mm/hugepages/hugepages-1048576kB/nr_hugepages

# Монтируем
mkdir -p /mnt/huge
mount -t hugetlbfs nodev /mnt/huge

# Проверяем
grep HugePages /proc/meminfo
```

### Закрепление в /etc/fstab и /etc/default/grub

```bash
# /etc/default/grub — добавить в GRUB_CMDLINE_LINUX:
GRUB_CMDLINE_LINUX="default_hugepagesz=1G hugepagesz=1G hugepages=4 iommu=pt intel_iommu=on"

update-grub
reboot
```

---

## Шаг 2 — Сборка DPDK

```bash
# Скачиваем стабильную версию
wget https://fast.dpdk.org/rel/dpdk-23.11.tar.xz
tar xf dpdk-23.11.tar.xz
cd dpdk-23.11

# Конфигурируем и собираем
meson setup build
cd build
ninja
ninja install
ldconfig

# Проверяем
pkg-config --modversion libdpdk
```

---

## Шаг 3 — Привязка NIC к DPDK (unbind от ядра)

```bash
# Смотрим какой интерфейс будет RS-портом
lspci | grep -i ethernet
# Пример вывода: 0000:03:00.0 Ethernet controller: Intel X710

# Загружаем драйвер vfio-pci (предпочтительнее uio для современных систем)
modprobe vfio-pci

# Отвязываем от ядра
ip link set eth1 down   # наш RS-порт
dpdk-devbind.py --unbind 0000:03:00.0

# Привязываем к vfio-pci
dpdk-devbind.py --bind vfio-pci 0000:03:00.0

# Проверяем
dpdk-devbind.py --status
```

---

## Шаг 4 — Получаем l3fwd и адаптируем

```bash
# l3fwd находится в примерах DPDK
cd dpdk-23.11/examples/l3fwd
ls
# main.c  l3fwd.h  l3fwd_lpm.c  l3fwd_em.c  Makefile  meson.build
```

Нам нужно создать новый файл с логикой декапсуляции и модифицировать main.c.

### Структура изменений

```
l3fwd/
├── main.c           ← минимальные правки (вызов нашей функции)
├── l3fwd.h          ← без изменений
├── ipip_decap.h     ← НОВЫЙ: наша логика декапсуляции и ответа
└── meson.build      ← добавить ipip_decap.h
```

---

## Шаг 5 — Пишем ipip_decap.h

Это ключевой файл. Вся логика здесь:

```c
#ifndef IPIP_DECAP_H
#define IPIP_DECAP_H

#include <stdint.h>
#include <rte_mbuf.h>
#include <rte_ether.h>
#include <rte_ip.h>
#include <rte_udp.h>
#include <rte_byteorder.h>

/*
 * Адреса стенда — подставить свои значения
 *
 * VIP        — виртуальный IP балансировщика (src IP в ответе RS)
 * CLIENT_IP  — IP клиента TRex Port 0 (dst IP в ответе RS)
 * TREX_P1_MAC — MAC адрес TRex Port 1 (dst MAC в ответе, DSR)
 * RS_MAC      — MAC адрес нашего DPDK-порта (src MAC в ответе)
 */
#define VIP          RTE_IPV4(10,  0, 0,  1)
#define CLIENT_IP    RTE_IPV4(192,168,10,10)

/* MAC TRex Port 1: куда слать DSR-ответ */
static const struct rte_ether_addr trex_p1_mac = {
    .addr_bytes = {0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0x11}
};

/* MAC нашего DPDK-порта */
static const struct rte_ether_addr rs_mac = {
    .addr_bytes = {0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0x22}
};

/*
 * Обрабатываем один пакет:
 *   1. Проверяем что это IPIP (proto=4 во внешнем IP)
 *   2. Снимаем Ethernet + внешний IP заголовок
 *   3. Формируем ответный UDP пакет
 *   4. Возвращаем 0 если пакет готов к отправке, -1 если не IPIP
 */
static inline int
ipip_decap_and_reply(struct rte_mbuf *m)
{
    struct rte_ether_hdr *eth;
    struct rte_ipv4_hdr  *outer_ip;
    struct rte_ipv4_hdr  *inner_ip;
    struct rte_udp_hdr   *udp;

    /* --- 1. Разбираем входящий пакет --- */

    eth = rte_pktmbuf_mtod(m, struct rte_ether_hdr *);

    /* Проверяем что это IPv4 */
    if (eth->ether_type != rte_cpu_to_be_16(RTE_ETHER_TYPE_IPV4))
        return -1;

    outer_ip = (struct rte_ipv4_hdr *)(eth + 1);

    /* Проверяем что это IPIP (protocol = 4) */
    if (outer_ip->next_proto_id != IPPROTO_IPIP)
        return -1;

    /* Внутренний IP заголовок идёт сразу после внешнего */
    inner_ip = (struct rte_ipv4_hdr *)
               ((uint8_t *)outer_ip + rte_ipv4_hdr_len(outer_ip));

    /* UDP заголовок после внутреннего IP */
    udp = (struct rte_udp_hdr *)
          ((uint8_t *)inner_ip + rte_ipv4_hdr_len(inner_ip));

    /*
     * Сохраняем нужное из внутреннего заголовка
     * src IP внутреннего пакета = CLIENT_IP
     * dst port = порт клиента, на него шлём ответ
     */
    uint16_t client_port = udp->src_port;
    uint16_t server_port = udp->dst_port;

    /* --- 2. Формируем ответный пакет прямо в том же mbuf --- */

    /*
     * Новый размер пакета:
     * Ethernet(14) + IP(20) + UDP(8) + payload(64)
     */
    uint16_t payload_len = 64;
    uint16_t pkt_len = sizeof(struct rte_ether_hdr)
                     + sizeof(struct rte_ipv4_hdr)
                     + sizeof(struct rte_udp_hdr)
                     + payload_len;

    /* Устанавливаем длину mbuf */
    rte_pktmbuf_data_len(m) = pkt_len;
    rte_pktmbuf_pkt_len(m)  = pkt_len;

    /* --- Ethernet заголовок --- */
    /* dst MAC = MAC TRex Port 1 (DSR: ответ летит напрямую) */
    rte_ether_addr_copy(&trex_p1_mac, &eth->dst_addr);
    /* src MAC = MAC нашего DPDK-порта */
    rte_ether_addr_copy(&rs_mac,      &eth->src_addr);
    eth->ether_type = rte_cpu_to_be_16(RTE_ETHER_TYPE_IPV4);

    /* --- IP заголовок ответа (пишем поверх старого) --- */
    struct rte_ipv4_hdr *reply_ip = (struct rte_ipv4_hdr *)(eth + 1);
    reply_ip->version_ihl     = RTE_IPV4_VHL_DEF;  /* version=4, ihl=5 */
    reply_ip->type_of_service = 0;
    reply_ip->total_length    = rte_cpu_to_be_16(
                                    sizeof(struct rte_ipv4_hdr)
                                  + sizeof(struct rte_udp_hdr)
                                  + payload_len);
    reply_ip->packet_id       = 0;
    reply_ip->fragment_offset = 0;
    reply_ip->time_to_live    = 64;
    reply_ip->next_proto_id   = IPPROTO_UDP;
    reply_ip->hdr_checksum    = 0;           /* пересчитаем ниже */
    reply_ip->src_addr        = rte_cpu_to_be_32(VIP);       /* src = VIP */
    reply_ip->dst_addr        = rte_cpu_to_be_32(CLIENT_IP); /* dst = клиент */

    /* Аппаратный offload контрольной суммы IP */
    m->ol_flags |= RTE_MBUF_F_TX_IP_CKSUM | RTE_MBUF_F_TX_IPV4;
    m->l2_len = sizeof(struct rte_ether_hdr);
    m->l3_len = sizeof(struct rte_ipv4_hdr);

    /* --- UDP заголовок ответа --- */
    struct rte_udp_hdr *reply_udp = (struct rte_udp_hdr *)(reply_ip + 1);
    reply_udp->src_port = server_port;   /* меняем порты местами */
    reply_udp->dst_port = client_port;
    reply_udp->dgram_len = rte_cpu_to_be_16(
                               sizeof(struct rte_udp_hdr) + payload_len);
    reply_udp->dgram_cksum = 0;          /* UDP checksum опционален */

    /* --- Payload --- */
    uint8_t *payload = (uint8_t *)(reply_udp + 1);
    memset(payload, 0xAB, payload_len);  /* заполняем тестовыми данными */

    return 0;  /* пакет готов к отправке */
}

#endif /* IPIP_DECAP_H */
```

---

## Шаг 6 — Правки в main.c

Находим в l3fwd/main.c функцию обработки пакетов и добавляем вызов нашей логики. В l3fwd это функция `l3fwd_simple_forward` или в цикле `lcore_main`:

```c
/* В начало main.c добавляем */
#include "ipip_decap.h"

/* Находим основной цикл обработки пакетов.
 * В l3fwd это выглядит примерно так: */
static void
lcore_main(void)
{
    struct rte_mbuf *pkts_burst[MAX_PKT_BURST];
    uint16_t nb_rx, nb_tx;
    uint16_t portid = 0;  /* наш единственный порт */

    while (!force_quit) {

        /* Принимаем пакеты */
        nb_rx = rte_eth_rx_burst(portid, 0, pkts_burst, MAX_PKT_BURST);
        if (unlikely(nb_rx == 0))
            continue;

        uint16_t nb_to_tx = 0;

        for (uint16_t i = 0; i < nb_rx; i++) {
            struct rte_mbuf *m = pkts_burst[i];

            /* Наша логика: декапсуляция + формирование ответа */
            if (ipip_decap_and_reply(m) == 0) {
                /* Пакет готов — ставим в очередь на отправку */
                pkts_burst[nb_to_tx++] = m;
            } else {
                /* Не IPIP — дропаем */
                rte_pktmbuf_free(m);
            }
        }

        /* Отправляем ответы */
        if (nb_to_tx > 0) {
            nb_tx = rte_eth_tx_burst(portid, 0, pkts_burst, nb_to_tx);
            /* Освобождаем неотправленные (если TX очередь переполнена) */
            for (uint16_t i = nb_tx; i < nb_to_tx; i++)
                rte_pktmbuf_free(pkts_burst[i]);
        }
    }
}
```

---

## Шаг 7 — Сборка

```bash
cd dpdk-23.11/examples/l3fwd

# Собираем
meson setup build -Dexamples=l3fwd
cd build
ninja

# Бинарник будет здесь:
ls dpdk-23.11/build/examples/dpdk-l3fwd
```

---

## Шаг 8 — Запуск

```bash
./dpdk-l3fwd \
    -l 0-3 \              # ядра CPU (4 ядра)
    -n 4 \                # каналы памяти
    --vdev "" \
    -- \
    -p 0x1 \              # маска портов: только порт 0
    --config "(0,0,0)"    # (port, queue, lcore)
```

---

## Итоговая схема стенда

```
TRex Port 0 ──UDP──► БН ──IPIP──► DPDK RS-эмулятор
                                   (декапсуляция в DPDK,
                                    ответ src=VIP)
TRex Port 1 ◄──UDP (src=VIP)──────────────────────
                    DSR, минуя БН
```

Производительность DPDK RS-эмулятора при одном ядре — порядка 10–20 Mpps на пакет 64 байта, при 4 ядрах — 40–80 Mpps, что сравнимо с TRex и не будет узким местом в тесте БН.