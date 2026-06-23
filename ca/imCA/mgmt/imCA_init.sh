#!/bin/bash

BASE_DIR=~/opensslCA
IM_CA_DIR=$BASE_DIR/imCA
ROOT_CA_DIR=$BASE_DIR/rootCA
ROOTCERT_FILE=$ROOT_CA_DIR/certs/ca.cert.crt
IM_CA_CFG_FILE=$IM_CA_DIR/mgmt/openssl_imCA.cnf
IM_PRIVATEKEY_FILE=$IM_CA_DIR/private/im.key.crt
IM_CSR_FILE=$IM_CA_DIR/csr/im.csr.crt
IM_CERT_FILE=$IM_CA_DIR/certs/im.cert.crt
IM_CERT_CA_CHAIN_FILE=$IM_CA_DIR/certs/imCA-rootCA_chain.cert.crt

cd $IM_CA_DIR
mkdir certs crl csr newcerts private
chmod 700 private
touch index.txt
echo 1000 > serial
echo 1000 > crlnumber

echo -e "\n======= Create Intermediate Private Key =======\n"

openssl genrsa -aes256 -out $IM_PRIVATEKEY_FILE 4096

echo -e "\n========== Create Intermediate CSR ===========\n"

openssl req -config $IM_CA_CFG_FILE -new -sha256 \
 -key $IM_PRIVATEKEY_FILE -out $IM_CSR_FILE

echo -e "\n======== Sign Intermediate CSR, Create certificate =========\n"

openssl ca -config $IM_CA_CFG_FILE -extensions x509_ext_intermediate \
-days 3652 -notext -md sha256 \
-in $IM_CSR_FILE \
-out $IM_CERT_FILE

echo -e "\n====== Verify Intermediate certificate from Root ======\n"

openssl verify -CAfile $ROOTCERT_FILE $IM_CERT_FILE

if [ $? -eq 0 ] && [ -f $IM_CERT_FILE ]; then
  echo -e "\n==== Create Im-Root certificate chain ====\n"
  if [ -f $IM_CERT_CA_CHAIN_FILE ]; then 
    chmod u+w $IM_CERT_CA_CHAIN_FILE  
  fi  
  cat $IM_CERT_FILE $ROOTCERT_FILE > $IM_CERT_CA_CHAIN_FILE
  chmod 444 $IM_CERT_CA_CHAIN_FILE
fi 

echo -e "\nDone."