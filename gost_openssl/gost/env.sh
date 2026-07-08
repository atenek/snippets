#!/usr/bin/env bash
# Activate GOST support for the openssl CLI in the current shell:
#     source gost/env.sh
# After sourcing, `openssl` will have the GOST engine loaded.
GOST_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export OPENSSL_CONF="$GOST_ROOT/openssl_gost.cnf"
export OPENSSL_ENGINES="$GOST_ROOT/engines-3"
export OPENSSL_MODULES="$GOST_ROOT/ossl-modules"
echo "GOST-TLS activated. OPENSSL_CONF=$OPENSSL_CONF"
echo "Check with: openssl engine gost -c -t"
