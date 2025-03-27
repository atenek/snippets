import sqlite3
import json
import csv

# Пример JSON-данных
json_users = '''
[
    {"id": 1, "name": "Alice"},
    {"id": 2, "name": "Bob"},
    {"id": 3, "name": "Charlie"}
]
'''

json_orders = '''
[
    {"order_id": 101, "user_id": 1, "amount": 250.5},
    {"order_id": 102, "user_id": 2, "amount": 450.0},
    {"order_id": 103, "user_id": 1, "amount": 300.0},
    {"order_id": 104, "user_id": 3, "amount": 125.75}
]
'''

# Загружаем данные из JSON в Python объекты
users_data = json.loads(json_users)
orders_data = json.loads(json_orders)


conn = sqlite3.connect(":memory:")  # база в памяти !!!
cursor = conn.cursor()
cursor.execute("PRAGMA foreign_keys = ON") # поддержка внешних ключей

cursor.execute("""
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
)
""")

# columns = ", ".join(f"{key} TEXT" for key in data_list[0].keys())
# cursor.execute(f"CREATE TABLE IF NOT EXISTS {table_name} ({columns})")

# columns = ", ".join(f"{key} TEXT" for key in data.keys())  # Все храним как TEXT
# cursor.execute(f"CREATE TABLE IF NOT EXISTS {table_name} ({columns})")

cursor.execute("""
CREATE TABLE orders (
    order_id INTEGER PRIMARY KEY,
    user_id INTEGER,
    amount REAL NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
)
""")

for user in users_data:
    cursor.execute("INSERT INTO users (id, name) VALUES (?, ?)",
                   (user["id"], user["name"]))

for order in orders_data:
    cursor.execute("INSERT INTO orders (order_id, user_id, amount) VALUES (?, ?, ?)",
                   (order["order_id"], order["user_id"], order["amount"]))

conn.commit()

join_query = """
SELECT orders.order_id, users.name, orders.amount
FROM orders
JOIN users ON orders.user_id = users.id
"""

cursor.execute(join_query)

for row in cursor.fetchall():
    print(f"Order ID: {row[0]}, User: {row[1]}, Amount: {row[2]}")

with open("output1.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    cursor.execute(f"SELECT * FROM orders")
    writer.writerow([desc[0] for desc in cursor.description])
    writer.writerows(cursor.fetchall())

query = "SELECT column1, column2 FROM table_name WHERE condition;"

with open("output2.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    cursor.execute(join_query)
    writer.writerow([desc[0] for desc in cursor.description])
    writer.writerows(cursor.fetchall())

conn.close()

