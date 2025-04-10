В Dagster объекты `AssetKey`, `AssetsDefinition` и связанные с ними структуры позволяют работать с asset'ами декларативно и программно. Вот как можно:

---

## ✅ Получить `AssetKey` и имя объекта asset

Если у тебя есть функция или объект `@asset`, то:

```python
@asset
def my_asset():
    ...
```

Тогда:

```python
from dagster import AssetKey

print(my_asset.key)             # -> AssetKey(['my_asset'])
print(my_asset.key.to_string()) # -> 'my_asset'
print(my_asset.key.path)        # -> ['my_asset']
```

---

## ✅ Получить объект asset по ключу

Если у тебя есть `Definitions`, и ты хочешь найти asset по `AssetKey`:

```python
defs = Definitions(assets=[asset1, asset2, asset3])

# Получить словарь: AssetKey -> asset definition
asset_dict = {asset.key: asset for asset in defs.get_asset_definitions()}

# Теперь можно искать:
target_asset = asset_dict.get(AssetKey(["my_asset"]))
```

---

## 📘 Советы

### 🔹 Что такое `AssetKey`
`AssetKey` — это просто путь (список строк), который идентифицирует asset. Dagster использует его как ключ в своей системе.

```python
AssetKey(["user_data", "raw"])  # asset с вложенной структурой
AssetKey(["raw_data"])          # простой ключ
```

### 🔹 Как преобразовать строку в AssetKey

```python
AssetKey.from_user_string("my_asset")       # → AssetKey(['my_asset'])
AssetKey.from_user_string("users/raw")      # → AssetKey(['users', 'raw'])
```

---

## ✅ Как это использовать?

Если ты хочешь, например:
- по имени найти asset
- отфильтровать asset'ы
- связать asset с IOManager
- сделать селективную материализацию

Ты будешь использовать `.key` и `AssetKey`.

---

Отлично! Вот подробный пример, как по списку строк-имен собрать только нужные `@asset` для `materialize()`.

---

## 🎯 Цель:
Допустим у тебя есть несколько asset'ов:

```python
@asset
def asset_a(): ...

@asset
def asset_b(): ...

@asset
def asset_c(): ...
```

Ты определяешь их в `Definitions`:

```python
defs = Definitions(assets=[asset_a, asset_b, asset_c])
```

А потом, **по списку строк** (например, из CLI или UI) хочешь выбрать, какие asset'ы материализовать:

```python
asset_names = ["asset_a", "asset_c"]  # ← можно получать динамически
```

---

## ✅ Код: фильтрация по имени

```python
from dagster import AssetKey

# 1. Словарь: AssetKey -> объект asset
assets_by_key = {asset.key: asset for asset in defs.get_asset_definitions()}

# 2. Преобразуем имена в AssetKey
keys_to_materialize = [AssetKey.from_user_string(name) for name in asset_names]

# 3. Получаем соответствующие asset'ы
assets_to_materialize = [
    assets_by_key[key] for key in keys_to_materialize if key in assets_by_key
]
```

---

## ✅ Запуск materialize

```python
from dagster import materialize

materialize(assets_to_materialize)
```

---

## 📦 Альтернатива: через `defs.asset_graph`

Если хочешь работать с графом зависимостей:

```python
from dagster._core.definitions.declarative_automaterialize import AssetGraph

graph = defs.asset_graph

for name in asset_names:
    key = AssetKey.from_user_string(name)
    deps = graph.get_parents(key)
    print(f"Asset {name} зависит от: {[d.to_string() for d in deps]}")
```

---

## ⚙️ Возможное расширение:

Если хочешь:
- добавить зависимые asset'ы автоматически (всё дерево)
- учитывать вложенные пути (`"users/raw"`)

— тоже можно сделать. Напиши, и я покажу как.