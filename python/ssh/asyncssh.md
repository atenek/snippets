```python
import asyncio
import asyncssh
from typing import List, Dict, Optional


async def try_connect(
    host: str,
    creds: List[Dict[str, str]],
    command: str = "uname -a"
) -> Optional[Dict]:
    """
    Пытается подключиться к host перебирая креды.
    creds — список словарей вида:
        {"username": "...", "password": "..."} или
        {"username": "...", "client_keys": "...", "passphrase": "..."}
    Возвращает словарь с host, stdout и cred при успехе, иначе None.
    """
    for cred in creds:
        try:
            conn = await asyncssh.connect(
                host,
                username=cred.get("username"),
                password=cred.get("password"),
                client_keys=[cred["client_keys"]] if "client_keys" in cred else None,
                passphrase=cred.get("passphrase"),
                known_hosts=None,  # отключаем проверку known_hosts
            )
            async with conn:
                result = await conn.run(command, check=True)
                print(f"[+] {host}: успешный логин {cred}")
                return {"host": host, "stdout": result.stdout, "cred": cred}
        except (OSError, asyncssh.Error) as exc:
            print(f"[-] {host}: неудача с {cred}: {exc}")
            continue

    print(f"[!] {host}: не удалось подключиться")
    return None


async def run_on_hosts(hosts_with_creds: Dict[str, List[Dict]]):
    tasks = [
        try_connect(host, creds)
        for host, creds in hosts_with_creds.items()
    ]
    results = await asyncio.gather(*tasks)
    return [r for r in results if r is not None]


async def main():
    # примеры данных: у каждого узла свой список кредов
    hosts_with_creds = {
        "host1.example.com": [
            {"username": "user1", "password": "badpass"},
            {"username": "user1", "password": "goodpass"},
        ],
        "host2.example.com": [
            {"username": "admin", "client_keys": "/home/alex/.ssh/id_rsa", "passphrase": "secret"},
            {"username": "admin", "password": "anotherpass"},
        ],
    }

    results = await run_on_hosts(hosts_with_creds)
    print("\n=== Итоги ===")
    for r in results:
        print(f"{r['host']} -> {r['cred']}:\n{r['stdout']}")


if __name__ == "__main__":
    asyncio.run(main())
```

В asyncssh.connect() логика такая:
 - username всегда нужен (явно или через текущего пользователя).
 - Если переданы и password, и client_keys/passphrase, то asyncssh попробует их по очереди в рамках одного подключения.
Сначала попытается использовать ключ /home/alex/.ssh/id_rsa с паролем wrong-passphrase.  
Если сервер отвергнет — попробует пароль mypass.  
Если и это не подошло — соединение закроется с ошибкой.

параметр client_keys в asyncssh.connect() — это список ключей.
Элементы списка могут быть двух типов:
 - путь до файла ключа (строка):
```python
client_keys=["/home/alex/.ssh/id_rsa", "/home/alex/.ssh/id_ed25519"]
```
В этом случае asyncssh сам загрузит ключи из файлов.
 - Объект ключа (asyncssh.SSHKey или asyncssh.PKCS11Key),

```python
key = asyncssh.read_private_key("/home/alex/.ssh/id_rsa", passphrase="secret")
client_keys=[key]
```

То есть client_keys может содержать пути или готовые объекты ключей, и их можно комбинировать.

```python
import os
import asyncssh
from typing import Union

def load_ssh_key(key: str, passphrase: Union[str, None] = None) -> asyncssh.SSHKey:
    """
    Загружает SSH-ключ из строки key.
    key может быть:
      - путем к файлу приватного ключа
      - самим приватным ключом в виде текста
    Возвращает объект asyncssh.SSHKey.
    """
    # Проверяем, есть ли такой файл
    if os.path.exists(key):
        # key — путь к файлу
        return asyncssh.read_private_key(key, passphrase=passphrase)
    
    # Проверяем, похоже ли содержимое на приватный ключ
    if "BEGIN" in key and "PRIVATE KEY" in key:
        return asyncssh.import_private_key(key, passphrase=passphrase)

    raise ValueError(f"Строка не похожа ни на путь, ни на приватный ключ: {key!r}")
```

```python
creds = {
    "host1.example.com": [
        {
            "username": "user1",
            "password": "pass1"
        },
        {
            "username": "user2",            
            "key": "/home/alex/.ssh/id1_rsa", 
            "passphrase": "secret1",
            "password": "pass2"
        },
        {
            "username": "user3",            
            "key": "/home/alex/.ssh/id2_rsa",
            "passphrase": "secret2",
            
        },
        {
            "username": "user4",
            "key": """-----BEGIN OPENSSH PRIVATE KEY-----
            ...
            -----END OPENSSH PRIVATE KEY-----""", 
            "passphrase": None,
            "password": "pass4"
        }
    ]
}
```

```python
import asyncio
import asyncssh
import os
from typing import List, Dict, Optional


def prepare_key(entry: Dict) -> Optional[asyncssh.SSHKey]:
    """
    Преобразует ключ из entry в объект asyncssh.SSHKey.
    key может быть:
      - путем к файлу
      - inline ключом
    """
    key_data = entry.get("key")
    if not key_data:
        return None

    passphrase = entry.get("passphrase")

    if os.path.exists(key_data):
        return asyncssh.read_private_key(key_data, passphrase=passphrase)

    if "BEGIN" in key_data and "PRIVATE KEY" in key_data:
        return asyncssh.import_private_key(key_data, passphrase=passphrase)

    raise ValueError(f"Непонятный формат ключа: {key_data[:30]}...")


async def try_connect(host: str, creds_list: List[Dict], command: str = "uname -a") -> Optional[Dict]:
    """
    Перебирает creds_list и пытается подключиться к host.
    Возвращает словарь с host, stdout и cred при успешном подключении.
    """
    for cred in creds_list:
        # подготовка ключа
        key_obj = prepare_key(cred) if "key" in cred else None

        try:
            conn = await asyncssh.connect(
                host,
                username=cred["username"],
                password=cred.get("password"),
                client_keys=[key_obj] if key_obj else None,
                known_hosts=None,
            )
            async with conn:
                result = await conn.run(command, check=True)
                print(f"[+] {host}: успешно с {cred}")
                return {"host": host, "stdout": result.stdout, "cred": cred}
        except (OSError, asyncssh.Error) as exc:
            print(f"[-] {host}: неудача с {cred['username']}: {exc}")
            continue

    print(f"[!] {host}: не удалось подключиться ни с одним кредом")
    return None


# пример запуска для одного хоста
async def main():
    creds = {
        "host1.example.com": [
            {"username": "user1", "password": "pass1"},
            {"username": "user2", "key": "/home/alex/.ssh/id1_rsa", "passphrase": "secret1", "password": "pass2"},
            {"username": "user3", "key": "/home/alex/.ssh/id2_rsa", "passphrase": "secret2"},
            {"username": "user4", "key": """-----BEGIN OPENSSH PRIVATE KEY-----
            ...
            -----END OPENSSH PRIVATE KEY-----""", "passphrase": None, "password": "pass4"}
        ]
    }

    results = []
    for host, entries in creds.items():
        r = await try_connect(host, entries)
        if r:
            results.append(r)

    print("\n=== Итоги ===")
    for r in results:
        print(f"{r['host']} -> {r['cred']['username']}:\n{r['stdout']}")


if __name__ == "__main__":
    asyncio.run(main())

```