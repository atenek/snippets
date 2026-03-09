### **Просмотр содержимого Keystore и проверка наличия закрытого ключа**

В командной строке Bash можно использовать `keytool` для работы с Keystore.

#### **1. Просмотр всех записей в Keystore**

```sh
keytool -list -keystore mykeystore.jks
```

Это отобразит список доступных записей (сертификатов и ключей). Если у записи стоит пометка **PrivateKeyEntry**, значит у неё есть закрытый ключ.

Пример вывода:

```
mycert, 10 марта 2025, PrivateKeyEntry
anothercert, 5 апреля 2024, trustedCertEntry
```

Где:

- `PrivateKeyEntry` — запись содержит закрытый ключ.
- `trustedCertEntry` — запись содержит только сертификат.

#### **2. Проверка конкретной записи**

```sh
keytool -list -keystore mykeystore.jks -alias mycert -v
```

Здесь `-v` (verbose) покажет расширенную информацию.

Если в выводе есть строка:

```
Entry type: PrivateKeyEntry
```

то у сертификата есть закрытый ключ.

---

### **Получение сертификата и закрытого ключа**

Если нужно извлечь сертификат и закрытый ключ, используется `openssl`, но сначала нужно преобразовать JKS в формат **PKCS12**, так как `keytool` не позволяет извлекать закрытые ключи напрямую.

#### **1. Экспорт Keystore в PKCS12**

```sh
keytool -importkeystore -srckeystore mykeystore.jks -destkeystore mykeystore.p12 -srcstoretype JKS -deststoretype PKCS12 -deststorepass mypassword
```

После этого `mykeystore.p12` можно обработать с помощью `openssl`.

#### **2. Извлечение сертификата**

```sh
openssl pkcs12 -in mykeystore.p12 -nokeys -clcerts -out mycert.pem
```

#### **3. Извлечение закрытого ключа**

```sh
openssl pkcs12 -in mykeystore.p12 -nocerts -nodes -out mykey.pem
```

Опция `-nodes` убирает шифрование закрытого ключа (если этого не требуется, можно убрать эту опцию).

---

### **Вывод**

1. Используем `keytool -list` для просмотра записей.
2. Проверяем `PrivateKeyEntry`, чтобы убедиться в наличии закрытого ключа.
3. Конвертируем `JKS` → `PKCS12`.
4. Извлекаем сертификат и закрытый ключ с помощью `openssl`.
