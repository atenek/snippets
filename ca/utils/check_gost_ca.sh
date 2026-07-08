#!/usr/bin/env bash
# =====================================================================
#  check_gost_ca.sh — смоук-тест GOST-профиля CA (по образцу
#  GOST_TLS/check_gost_tls.sh, но через штатные скрипты выпуска).
# =====================================================================
#  Проверяет:
#    1. Выпуск тестовой цепочки root -> im -> ee в профиле gost-256
#       (хранилище — во временном каталоге через CA_CERT_BASE,
#        рабочее certificates/ не затрагивается)
#    2. openssl verify цепочки под GOST-окружением
#    3. Живой TLS 1.2 handshake s_server/s_client на ee-сертификате
#       с шифром GOST2012-KUZNYECHIK-KUZNYECHIKOMAC
#
#  Запуск:  ./utils/check_gost_ca.sh   (интерактивного ввода не требует)
# =====================================================================
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GOST_DIR="${GOST_ENGINE_DIR:-$ROOT/GOST_TLS/gost}"

W="$(mktemp -d)"
SERVER_PID=""
trap '[ -n "$SERVER_PID" ] && kill $SERVER_PID 2>/dev/null; rm -rf "$W"' EXIT

# Тестовое хранилище — в стороне от рабочего certificates/.
export CA_CERT_BASE="$W/certificates"
# Пропустить шаг ручной правки конфига в редакторе.
export EDITOR=true

PASS=0; FAIL=0
ok(){ echo "  [ OK ] $1"; PASS=$((PASS+1)); }
no(){ echo "  [FAIL] $1"; FAIL=$((FAIL+1)); }

cd "$ROOT"

# Скрипты выпуска интерактивные (часть вопросов задаёт python, часть — openssl ca),
# поэтому ответы подаются через pty (`script`): в каноническом режиме tty каждый
# читатель получает ровно одну строку, python не заглатывает чужие ответы из пайпа.
issue() {  # issue <лог> <ответы...> -- <команда...>
  local log="$1"; shift
  local answers=""
  while [ "$1" != "--" ]; do answers="$answers$1\n"; shift; done
  shift
  printf "$answers" | timeout 120 script -qec "$*" /dev/null >"$log" 2>&1
}

echo "== 1. Выпуск тестовой цепочки (профиль gost-256) =="
# Ответы root: n — ключ без passphrase, y — подтвердить subject.
if issue "$W/root.log" n y -- \
     python3 rootCA/mgmt/rootCA_init.py --profile gost-256 --cn smoke-root; then
  ok "root выпущен"
else
  no "root не выпущен (см. лог ниже)"; tail -20 "$W/root.log"
fi
# Ответы im: n — без passphrase, y — подтвердить subject, y+y — sign/commit openssl ca.
if issue "$W/im.log" n y y y -- \
     python3 imCA/mgmt/imCA_init.py --profile gost-256 --cn smoke-im; then
  ok "im выпущен"
else
  no "im не выпущен (см. лог ниже)"; tail -20 "$W/im.log"
fi
# Ответы ee: 3 — шаблон openssl_endentity_server_gost.cnf, дальше как для im.
if issue "$W/ee.log" 3 n y y y -- \
     python3 endentity/mgmt/endentity_init.py --profile gost-256 --cn smoke-ee; then
  ok "ee выпущен"
else
  no "ee не выпущен (см. лог ниже)"; tail -20 "$W/ee.log"
fi

ROOT_CRT="$CA_CERT_BASE/gost/root/root_cert/certs/smoke-root-01.crt"
IM_CRT="$CA_CERT_BASE/gost/im/im_cert/certs/smoke-im-01.crt"
IM_CHAIN="$CA_CERT_BASE/gost/im/im_cert/certs/smoke-im-01-chain.crt"
EE_CRT="$CA_CERT_BASE/gost/ee/endentity_cert/certs/smoke-ee-01.crt"
EE_KEY="$CA_CERT_BASE/gost/ee/endentity_cert/private/smoke-ee-01.key"
EE_CHAIN="$CA_CERT_BASE/gost/ee/endentity_cert/certs/smoke-ee-01-chain.crt"
for f in "$ROOT_CRT" "$IM_CRT" "$IM_CHAIN" "$EE_CRT" "$EE_KEY" "$EE_CHAIN"; do
  [ -f "$f" ] || { no "нет файла $f"; }
done

# Дальше — вызовы openssl под GOST-окружением (конфиг отрендерен на шаге 1).
export OPENSSL_CONF="$GOST_DIR/openssl_gost.cnf"
export OPENSSL_ENGINES="$GOST_DIR/engines-3"
export OPENSSL_MODULES="$GOST_DIR/ossl-modules"

echo "== 2. Алгоритмы и verify цепочки =="
openssl x509 -in "$EE_CRT" -noout -text 2>/dev/null | grep -q "GOST R 34.10-2012" \
  && ok "подпись ГОСТ Р 34.10-2012" || no "в ee-серте нет подписи ГОСТ"
openssl verify -CAfile "$ROOT_CRT" "$IM_CRT" >/dev/null 2>&1 \
  && ok "verify im <- root" || no "verify im <- root"
openssl verify -CAfile "$IM_CHAIN" "$EE_CRT" >/dev/null 2>&1 \
  && ok "verify ee <- im <- root" || no "verify ee <- im <- root"

echo "== 3. GOST-TLS live handshake (ee-сертификат) =="
PORT=$(( (RANDOM % 20000) + 40000 ))
openssl s_server -accept $PORT -cert "$EE_CRT" -key "$EE_KEY" \
  -cert_chain "$IM_CHAIN" -CAfile "$ROOT_CRT" \
  -cipher 'GOST2012-KUZNYECHIK-KUZNYECHIKOMAC' -tls1_2 -www -quiet >/dev/null 2>&1 &
SERVER_PID=$!
sleep 1
OUT=$(echo -e "GET / HTTP/1.0\r\n\r\n" | timeout 8 openssl s_client \
  -connect localhost:$PORT -CAfile "$ROOT_CRT" -tls1_2 2>&1)
echo "$OUT" | grep -q "Cipher is GOST2012-KUZNYECHIK" \
  && ok "TLS согласован GOST-шифр" || no "TLS GOST-шифр не согласован"
echo "$OUT" | grep -q "Verify return code: 0" \
  && ok "TLS сертификат проверен (verify 0)" || no "TLS verify != 0"

echo
echo "==================== RESULT: $PASS passed, $FAIL failed ===================="
[ "$FAIL" -eq 0 ]
