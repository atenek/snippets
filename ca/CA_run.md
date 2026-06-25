# CA

## Root CA

### Выпуск самоподписанного корневого сертификата.
 
```sh
rootCA/mgmt/rootCA_init.py
```

## Intermediate CA

### Выпуск промежуточного сертификата, подписанного выбранным корневым CA.

```sh
imCA/mgmt/imCA_init.py
```

## End Entity

### Выпуск конечного сертификата, подписанного выбранным промежуточным CA.

```sh
endentity/mgmt/endentity_init.py
```


### Просмотр сертификата

```sh
CERT_PATH=~/Prj/2_dev/python/ca/certificates/ee/endentity_cert/certs/endentity_cert-01.crt
utils/cert_view.py $CERT_PATH
```