#!/bin/bash

BASE_DIR=~/openssl_certs
ROOT_CA_DIR=$BASE_DIR/rootCA
PRIVATEKEY_FILE=$ROOT_CA_DIR/private/ca.key.crt
ROOTCERT_FILE=$ROOT_CA_DIR/certs/ca.cert.crt

cd $ROOT_CA_DIR
mkdir certs crl newcerts private
chmod 700 private
touch index.txt
echo 1000 > serial

echo -e '\n====== create root CA Private Key ======\n'

openssl genrsa -aes256 -out $PRIVATEKEY_FILE 4096

echo -e  "\n====== create root CA Certificate ======\n"

openssl req -config $ROOT_CA_DIR/mgmt/openssl_rootCA.cnf \
 -key $PRIVATEKEY_FILE \
 -new -x509 -days 7305 -sha256 -extensions x509_ext_root \
 -out $ROOTCERT_FILE

 echo -e  "\nDone."
