#!/usr/bin/env bash
# lbmon.sh — live-статистика TCP-сессий клиента к VIP балансировщика (ss + awk).
# Использование: ./lbmon.sh <VIP> [порт=80] [интервал_сек=5]
VIP=${1:?укажите VIP}; PORT=${2:-80}; INT=${3:-5}
FILTER="( dst $VIP and dport = :$PORT )"
: > /tmp/lbmon.prev; t0=$(date +%s)
printf '%-8s %7s %6s %7s %10s %10s %10s %10s %10s\n' \
  время estab syn tw_wait "итого,MB" "Мбит/с" "KB/s/сес" "min_KB/s" "max_KB/s"
while :; do
  now=$(date +%s)
  # на каждое соединение: rcv-байты; скорость по сессии = delta с прошлого замера
  cur=$(ss -Htin state established "$FILTER" | awk '
      /^[0-9]/ || /ESTAB/ {peer=$4; key=$3}          # строка соединения: local peer
      /bytes_received:/ { match($0,/bytes_received:[0-9]+/);
                          print key, substr($0,RSTART+15,RLENGTH-15) }')
  syn=$(ss -Htn state syn-sent "$FILTER" | wc -l)
  tw=$(ss -Htn state time-wait "$FILTER" | wc -l)
  printf '%s\n' "$cur" > /tmp/lbmon.cur
  awk -v iv=$INT -v t=$((now-t0)) -v syn=$syn -v tw=$tw '
      FILENAME==ARGV[1] { if(NF==2) old[$1]=$2; next }
      NF==2 { n++; tot+=$2
              if ($1 in old) { d=($2-old[$1])/iv/1024; m++; sum+=d
                               if (min==""||d<min) min=d; if (d>max) max=d } }
      END { rate = (m? sum*1024*8/1e6 : 0)
            printf "%-8s %7d %6d %7d %10.0f %10.1f %10.1f %10.1f %10.1f\n",
                   t"s", n, syn, tw, tot/1048576, rate, (m?sum/m:0), min+0, max+0 }
  ' /tmp/lbmon.prev /tmp/lbmon.cur 2>/dev/null || true
  mv /tmp/lbmon.cur /tmp/lbmon.prev
  sleep "$INT"
done
