самый надёжный способ — сделать **прокси-курсор** (или `cursor_factory`), который перехватывает *любые* вызовы `execute()` / `executemany()` и *все* методы получения данных (`fetchone`, `fetchall`, `fetchmany`).   
Плюс ловить исключения, чтобы фиксировать и ошибки тоже.

---

### Пример: универсальный логирующий курсор

```python
import psycopg2
from psycopg2.extensions import cursor

class LoggingCursor(cursor):
    def execute(self, query, vars=None):
        entry = {"query": query, "params": vars}
        try:
            result = super().execute(query, vars)
            entry["status"] = "ok"
        except Exception as e:
            entry["status"] = "error"
            entry["error"] = str(e)
            raise
        finally:
            # сохраняем в общий лог
            self.connection._query_log.append(entry)
        return result

    def executemany(self, query, vars_list):
        entry = {"query": query, "params": vars_list}
        try:
            result = super().executemany(query, vars_list)
            entry["status"] = "ok"
        except Exception as e:
            entry["status"] = "error"
            entry["error"] = str(e)
            raise
        finally:
            self.connection._query_log.append(entry)
        return result

    def fetchone(self):
        row = super().fetchone()
        self.connection._query_log[-1]["result"] = row
        return row

    def fetchall(self):
        rows = super().fetchall()
        self.connection._query_log[-1]["result"] = rows
        return rows

    def fetchmany(self, size=None):
        rows = super().fetchmany(size)
        self.connection._query_log[-1]["result"] = rows
        return rows


def connect_with_logging(**kwargs):
    conn = psycopg2.connect(cursor_factory=LoggingCursor, **kwargs)
    conn._query_log = []  # сюда будут писаться все операции
    return conn
```

---

### Использование

```python
conn = connect_with_logging(
    dbname="mydb",
    user="myuser",
    password="mypassword",
    host="localhost",
    port=5432
)

cur = conn.cursor()

# успешный SELECT
cur.execute("SELECT version();")
print(cur.fetchone())

# успешный INSERT
cur.execute("CREATE TEMP TABLE t (id int);")
cur.execute("INSERT INTO t VALUES (%s)", (123,))

# ошибка
try:
    cur.execute("SELECT * FROM no_such_table;")
except Exception:
    pass

print("Лог запросов:")
for entry in conn._query_log:
    print(entry)
```

---

### Пример содержимого лога:

```python
[
  {
    'query': 'SELECT version();',
    'params': None,
    'status': 'ok',
    'result': ('PostgreSQL 16.2 ...',)
  },
  {
    'query': 'CREATE TEMP TABLE t (id int);',
    'params': None,
    'status': 'ok'
  },
  {
    'query': 'INSERT INTO t VALUES (%s)',
    'params': (123,),
    'status': 'ok'
  },
  {
    'query': 'SELECT * FROM no_such_table;',
    'params': None,
    'status': 'error',
    'error': 'relation "no_such_table" does not exist'
  }
]
```


