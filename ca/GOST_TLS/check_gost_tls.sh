#!/usr/bin/env bash
# =====================================================================
#  check_gost_tls.sh — end-to-end verification of GOST-TLS in OpenSSL
# =====================================================================
#  Verifies:
#    1. GOST engine loads and lists all required algorithms
#    2. Hash        — GOST R 34.11-2012 (Streebog 256/512)
#    3. Signature   — GOST R 34.10-2012 (keygen + sign + verify)
#    4. Ciphers     — GOST R 34.12/34.13-2015 (Magma, Kuznyechik) + 28147-89
#    5. GOST-TLS    — live TLS 1.2 handshake with GOST certificate
# =====================================================================
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export OPENSSL_CONF="$ROOT/gost/openssl_gost.cnf"
export OPENSSL_ENGINES="$ROOT/gost/engines-3"
export OPENSSL_MODULES="$ROOT/gost/ossl-modules"

W="$(mktemp -d)"
trap 'kill $SERVER_PID 2>/dev/null; rm -rf "$W"' EXIT
PASS=0; FAIL=0
ok(){ echo "  [ OK ] $1"; PASS=$((PASS+1)); }
no(){ echo "  [FAIL] $1"; FAIL=$((FAIL+1)); }

echo "== 1. Engine load =="
if openssl engine gost -c 2>/dev/null | grep -q gost2012_256; then
  ok "GOST engine loaded"; else no "GOST engine failed to load"; fi

echo "== 2. Hash: GOST R 34.11-2012 (Streebog) =="
# Known test vector for "The quick brown fox jumps over the lazy dog"
EXPECT=3e7dea7f2384b6c5a3d0e24aaa29c05e89ddd762145030ec22c71a6db8b2c1f4
GOT=$(echo -n "The quick brown fox jumps over the lazy dog" | openssl dgst -md_gost12_256 2>/dev/null | awk '{print $NF}')
[ "$GOT" = "$EXPECT" ] && ok "Streebog-256 matches known test vector" || no "Streebog-256 mismatch ($GOT)"
echo -n x | openssl dgst -md_gost12_512 >/dev/null 2>&1 && ok "Streebog-512 available" || no "Streebog-512 failed"

echo "== 3. Signature: GOST R 34.10-2012 =="
echo "sign me" > "$W/d.txt"
for PS in 256 512; do
  openssl genpkey -algorithm gost2012_$PS -pkeyopt paramset:A -out "$W/k$PS.pem" 2>/dev/null
  openssl pkey -in "$W/k$PS.pem" -pubout -out "$W/p$PS.pem" 2>/dev/null
  openssl dgst -md_gost12_$PS -sign "$W/k$PS.pem" -out "$W/s$PS.bin" "$W/d.txt" 2>/dev/null
  if openssl dgst -md_gost12_$PS -verify "$W/p$PS.pem" -signature "$W/s$PS.bin" "$W/d.txt" 2>/dev/null | grep -q "Verified OK"; then
    ok "gost2012_$PS sign+verify"; else no "gost2012_$PS sign+verify"; fi
done

echo "== 4. Ciphers: GOST 34.12/34.13-2015 + 28147-89 =="
for C in kuznyechik-cbc magma-cbc gost89; do
  echo -n secret | openssl enc -e -a -$C -k pw -iter 1 >/dev/null 2>&1 && ok "$C" || no "$C"
done

echo "== 5. GOST-TLS live handshake =="
openssl genpkey -algorithm gost2012_256 -pkeyopt paramset:A -out "$W/ca.key" 2>/dev/null
openssl req -x509 -new -key "$W/ca.key" -md_gost12_256 -days 1 -out "$W/ca.crt" -subj "/CN=GOST CA" 2>/dev/null
openssl genpkey -algorithm gost2012_256 -pkeyopt paramset:A -out "$W/srv.key" 2>/dev/null
openssl req -new -key "$W/srv.key" -md_gost12_256 -out "$W/srv.csr" -subj "/CN=localhost" 2>/dev/null
openssl x509 -req -in "$W/srv.csr" -CA "$W/ca.crt" -CAkey "$W/ca.key" -CAcreateserial \
  -md_gost12_256 -days 1 -out "$W/srv.crt" 2>/dev/null
PORT=$(( (RANDOM % 20000) + 40000 ))
openssl s_server -accept $PORT -cert "$W/srv.crt" -key "$W/srv.key" -CAfile "$W/ca.crt" \
  -cipher 'GOST2012-KUZNYECHIK-KUZNYECHIKOMAC' -tls1_2 -www -quiet >/dev/null 2>&1 &
SERVER_PID=$!
sleep 1
OUT=$(echo -e "GET / HTTP/1.0\r\n\r\n" | timeout 8 openssl s_client -connect localhost:$PORT -CAfile "$W/ca.crt" -tls1_2 2>&1)
echo "$OUT" | grep -q "Cipher is GOST2012-KUZNYECHIK" && ok "TLS negotiated GOST cipher" || no "TLS GOST cipher"
echo "$OUT" | grep -q "Verify return code: 0" && ok "TLS certificate verified" || no "TLS cert verify"

echo
echo "==================== RESULT: $PASS passed, $FAIL failed ===================="
[ "$FAIL" -eq 0 ]
