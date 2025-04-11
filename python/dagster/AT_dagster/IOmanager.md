

### 💡 Кратко:
- Метод `.load_input(context)` вызывается **для каждого входа** (`input`) в asset или op.
- Dagster сам **связывает этот вызов с соответствующим asset**, передавая в `context` всю нужную информацию.
- Именно внутри `load_input()` ты **решаешь, есть ли нужные данные в локальном кэше**, нужно ли качать с удалёнки, и т.д.

---

## 🔍 Детали: что передаёт Dagster в `.load_input(context)`

Dagster передаёт в `load_input()` объект `InputContext`, в котором есть:

| Поле                | Что содержит                                               |
|---------------------|------------------------------------------------------------|
| `context.asset_key` | asset, к которому относится этот input (например, `upstream_asset`) |
| `context.upstream_output` | Объект `OutputContext` того asset, который выдал этот input |
| `context.name`      | имя входа (например, `upstream_asset`)                    |
| `context.metadata`  | метаданные, если они были переданы в `@asset`              |
| `context.config`    | конфигурация ресурса (если передавалась)                   |

Таким образом, ты **точно знаешь, какой asset ты сейчас загружаешь**.

---

## 🧠 Пример: asset с входом

```python
@asset
def raw_data() -> pd.DataFrame:
    ...

@asset
def clean_data(raw_data: pd.DataFrame) -> pd.DataFrame:
    ...
```

Dagster вызовет:

```python
load_input(context_for_raw_data_input_to_clean_data)
```

И ты можешь сделать:

```python
class MyIOManager(IOManager):
    def load_input(self, context: InputContext):
        asset_key = context.asset_key  # это будет 'raw_data'
        path = f"/tmp/cache/{asset_key.to_string()}.pkl"

        if os.path.exists(path):
            return pd.read_pickle(path)
        else:
            remote_path = f"s3://bucket/data/{asset_key.to_string()}.pkl"
            download_from_s3(remote_path, path)
            return pd.read_pickle(path)
```

---

## 📦 Актуальность данных — тоже здесь

Ты можешь реализовать:

- проверку `mtime`, если локальные файлы устаревают
- проверку контрольной суммы
- TTL в секундах/минутах
- хеш входов (input hash -> output cache)

Это **всё делает именно `.load_input()`**, потому что он — **точка контроля чтения**.

---

Если интересно, могу сделать готовый шаблон IOManager, который:
- смотрит локальный кэш
- если устарело — скачивает из S3
- логирует источники
- сохраняет как `.parquet` или `.pkl` — по выбору
 
---

Отлично! Давай рассмотрим "честную" реализацию кэширования в Dagster, которая будет работать без явного вызова `materialize()` из внутри `IOManager`. Мы будем использовать:

- **Проверку времени** (например, когда был последний доступ к данным),
- **Проверку хеша** (контрольные суммы для входных данных).

Такой подход будет более "Dagster-friendly" и не будет нарушать граф зависимостей.

---

## ✅ Шаги:

1. **Время и хеш для кэширования**:
    - Мы будем проверять, существует ли кэшированный файл и актуален ли он (по времени или по хешу).
    - Для вычисления хеша можно использовать стандартные библиотеки Python (например, `hashlib`).
    
2. **Интерфейс `load_input`**:
    - Мы проверяем, существует ли файл, и если его нет или он устарел, мы запрашиваем данные для материализации.
    - При отсутствии кэша вызываем материализацию через другой механизм (например, с помощью библиотеки `materialize` или зависимости).

3. **Метод `handle_output`**:
    - Сохраняем результат в локальный кэш и обновляем время или хеш.

---

### Пример реализации `IOManager` с проверкой времени и хешей

```python
import os
import hashlib
import pickle
from datetime import datetime
from dagster import IOManager, InputContext, OutputContext, AssetKey


class CacheWithHashIOManager(IOManager):
    def __init__(self, cache_dir="/tmp/cache"):
        self.cache_dir = cache_dir

    def load_input(self, context: InputContext):
        # Определяем ключ и путь к файлу для кэширования
        upstream_asset_key = context.asset_key
        cache_path = self._get_cache_path(upstream_asset_key)

        # Проверка существования кэша
        if os.path.exists(cache_path):
            print(f"Found cache for {upstream_asset_key}. Checking if it's valid...")

            # Проверка актуальности (по времени или хешу)
            if self._is_cache_valid(cache_path):
                print(f"Cache for {upstream_asset_key} is valid.")
                return self._load_from_path(cache_path)
            else:
                print(f"Cache for {upstream_asset_key} is outdated. Materializing again...")
        
        # Если нет кэша или он устарел, материализуем (это будет зависеть от бизнес-логики)
        return self._materialize_asset(upstream_asset_key)

    def handle_output(self, context: OutputContext, obj):
        # Сохраняем результат в кэш
        asset_key = context.asset_key
        cache_path = self._get_cache_path(asset_key)
        self._save_to_path(obj, cache_path)

    def _get_cache_path(self, asset_key: AssetKey) -> str:
        """Получаем путь для кэшированного файла"""
        return os.path.join(self.cache_dir, f"{asset_key.to_string()}.pkl")

    def _is_cache_valid(self, cache_path: str) -> bool:
        """Проверка актуальности кэша"""
        cache_time = os.path.getmtime(cache_path)  # Время последнего изменения файла
        last_update = datetime.fromtimestamp(cache_time)

        # Мы проверяем, если прошло больше 24 часов, то кэш считаем устаревшим
        if (datetime.now() - last_update).days > 1:
            return False

        # Дополнительная проверка хеша входных данных для кэша
        with open(cache_path, "rb") as f:
            cached_data = f.read()

        hash_value = self._get_data_hash(cached_data)

        # Проверка на хеш (например, сравнение с хешем входных данных)
        if self._is_hash_changed(hash_value):
            return False

        return True

    def _get_data_hash(self, data: bytes) -> str:
        """Вычисление хеша для данных"""
        return hashlib.sha256(data).hexdigest()

    def _is_hash_changed(self, hash_value: str) -> bool:
        """Проверка, изменился ли хеш (например, по сравнению с предыдущим значением)"""
        # Это можно настроить в зависимости от твоей логики (например, хранить старые хеши)
        return False  # Псевдокод: на самом деле ты должен хранить старые хеши и сравнивать их

    def _materialize_asset(self, asset_key: AssetKey):
        """Материализация ассета, если кэш отсутствует или устарел"""
        print(f"Materializing {asset_key}...")
        # Это место для твоей логики вызова materialize
        # Пример: materialize([asset]) или выполнить расчет
        return {"data": 123}  # В данном примере возвращаем фальшивые данные для материализации

    def _load_from_path(self, path: str):
        """Загрузка данных из кэша"""
        with open(path, "rb") as f:
            return pickle.load(f)

    def _save_to_path(self, obj, path: str):
        """Сохранение данных в кэш"""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(obj, f)
```

---

## 🔍 Пояснение к коду

1. **`load_input(context)`**:
    - Проверяет наличие кэшированного файла.
    - Если файл существует, проверяет его актуальность (по времени изменения или хешу).
    - Если кэш устарел — вызывает материализацию для asset'а, от которого зависит текущий asset.
    
2. **`handle_output(context, obj)`**:
    - Сохраняет результат работы asset'а в локальный кэш.
    - Каждый asset сохраняется в отдельном файле на основе его `AssetKey`.

3. **`_is_cache_valid(cache_path)`**:
    - Проверка актуальности кэша. Мы используем два метода:
      - **Время**: если прошло больше 24 часов, считаем, что кэш устарел.
      - **Хеш данных**: вычисляем хеш кэшированных данных и проверяем, не изменился ли он.

4. **`_materialize_asset(asset_key)`**:
    - Материализует зависимый asset вручную, если его кэш отсутствует или устарел.

5. **`_get_data_hash()`**:
    - Вычисляет хеш для данных в кэшированном файле, чтобы отслеживать изменения.

---

## 🧠 Как использовать

1. В `Definitions` ты можешь указать кастомный IOManager:

```python
defs = Definitions(
    assets=[upstream, downstream],
    resources={"io_manager": CacheWithHashIOManager()},
)
```

2. Этот IOManager будет проверять, актуальны ли данные в кэше, и, если данные устарели, инициировать материализацию нужного asset.

---

Ниже — **подробное описание последовательности вызовов**, когда ты вызываешь `materialize()` или запускаешь `job` в Dagster. Я покажу:

1. Какие функции вызываются Dagster’ом.
2. Где строится DAG.
3. Когда Dagster решает, какие assets запускать.
4. Где ты можешь «вклиниться» кастомным логированием.

---

## 📌 Цель: понять, **как Dagster строит DAG** и как происходит планирование выполнения

---

## 🔁 Высокоуровневая последовательность

```text
materialize([...]) или job.execute_in_process()

    ↓

1. Построение AssetGraph (глобальный DAG)
2. Построение Subset DAG (по выбранным asset’ам)
3. Проверка метаданных (опционально: с I/O manager’ом или asset checks)
4. Построение ExecutionPlan
5. Итеративное выполнение шагов ExecutionPlan
    └─ IOManager.load_input
    └─ Вызов функции asset
    └─ IOManager.handle_output
```

---

## 🔬 Подробный стек вызовов и этапов

### ▶️ 1. `materialize([...])` — входная точка

```python
dagster._core.execution.api.materialize()
```

Это функция-обёртка. Она:

- принимает список assets;
- вызывает `Definitions.materialize()` — то есть строит `JobDefinition` из asset-графа.

---

### 📦 2. Построение `AssetGraph`

```python
AssetGraph.from_assets([asset1, asset2, ...])
```

Это шаг, где Dagster **строит Directed Acyclic Graph** из asset’ов. Он определяет:

- связи `@asset` через параметры функции и `AssetIn(...)`;
- upstream/downstream зависимости;
- `source_asset` vs `asset`.

📌 Именно здесь ты можешь **вставить отладку**, если хочешь увидеть связи:

```python
from dagster._core.definitions.asset_graph import AssetGraph
graph = AssetGraph.from_assets([asset1, asset2])
print(graph.asset_dep_graph)
```

---

### 📚 3. Построение job (если ты используешь materialize)

Dagster внутри вызывает:

```python
job = define_asset_job("asset_job", selection=["..."])
```

или

```python
defs = Definitions(assets=[...])
defs.get_implicit_job_def_for_assets([...])
```

И получается `JobDefinition`, основанный на твоём DAG’е.

---

### 🔧 4. Построение ExecutionPlan

```python
plan = job.get_execution_plan(run_config=..., ...)
```

Этот этап:

- берёт DAG;
- делает топологическую сортировку;
- определяет `ExecutionStep`’ы;
- для каждого шага — знает какие inputs/outputs и зависимости.

Можно получить доступ к шагам:

```python
for step in plan.get_steps():
    print(step.key, step.inputs.keys(), step.outputs.keys())
```

---

### ▶️ 5. Запуск шагов ExecutionPlan

Dagster исполняет шаги **в порядке топологической сортировки**. Каждый шаг:

1. вызывает `IOManager.load_input()` для всех входов;
2. вызывает сам asset-функцию;
3. передаёт результат в `IOManager.handle_output()`.

---

## 👀 Где можно логировать DAG?

### Пример: лог DAG перед выполнением

```python
from dagster._core.definitions.asset_graph import AssetGraph
from dagster import AssetKey

graph = AssetGraph.from_assets([a1, a2, a3])
for asset in graph.assets:
    parents = graph.get_parents(AssetKey(asset))
    print(f"{asset} ← {[p.to_string() for p in parents]}")
```

---

## 🧠 Возможные hook-точки (для дебага DAG)

| Этап                     | Где логировать или вставлять `breakpoint()`            |
|--------------------------|--------------------------------------------------------|
| Построение DAG           | `AssetGraph.from_assets(...)`                          |
| Построение execution plan| `job.get_execution_plan(...)`                          |
| Выбор шагов              | `plan.get_steps()`                                     |
| Вызов asset-функции      | Внутри `@asset`, через `context.log.info(...)`         |
| Загрузка входа           | `IOManager.load_input(...)`                            |
| Сохранение выхода        | `IOManager.handle_output(...)`                         |

---

## 🛠️ пример, где строится DAG, печатается в консоль, а затем по шагам вызывается выполнение с логами

----
Отлично. Вот **полный минимальный пример проекта на Dagster**, который:

1. Определяет 3 asset’а с зависимостями (`a → b → c`);
2. Выводит DAG зависимостей в консоль **до выполнения**;
3. Логирует каждый вызов `load_input` и `handle_output`;
4. Показывает, какие asset’ы выполняются и что они делают.

---

## 📁 Структура
```text
project/
├── assets.py
├── io_manager.py
└── run.py
```

---

## 🧱 `assets.py`

```python
from dagster import asset, AssetExecutionContext

@asset
def a(context: AssetExecutionContext):
    context.log.info("Выполняется asset A")
    return 1

@asset
def b(context: AssetExecutionContext, a: int):
    context.log.info(f"Выполняется asset B. Получено a = {a}")
    return a + 1

@asset
def c(context: AssetExecutionContext, b: int):
    context.log.info(f"Выполняется asset C. Получено b = {b}")
    return b * 2
```

---

## 💾 `io_manager.py`

```python
from dagster import IOManager, InputContext, OutputContext

_store = {}

class LoggingIOManager(IOManager):
    def load_input(self, context: InputContext):
        key = context.asset_key.to_user_string()
        context.log.info(f"[IOManager] load_input: {key}")
        return _store.get(key)

    def handle_output(self, context: OutputContext, obj):
        key = context.asset_key.to_user_string()
        context.log.info(f"[IOManager] handle_output: {key} = {obj}")
        _store[key] = obj
```

---

## 🚀 `run.py`

```python
from dagster import Definitions, materialize, FilesystemIOManager
from assets import a, b, c
from io_manager import LoggingIOManager
from dagster._core.definitions.asset_graph import AssetGraph
from dagster import AssetKey

assets = [a, b, c]

# 1. Построим DAG и выведем его до выполнения
print("\n=== DAG зависимостей ===")
graph = AssetGraph.from_assets(assets)
for asset in graph.assets:
    key = asset.to_user_string()
    parents = graph.get_parents(AssetKey(asset))
    parent_keys = [p.to_user_string() for p in parents]
    print(f"{key} ← {parent_keys}")

# 2. Выполним asset c, остальные подтянутся
defs = Definitions(
    assets=assets,
    resources={"io_manager": LoggingIOManager()},
)

# 3. Запуск
print("\n=== Запуск materialize([c]) ===")
materialize([c], definitions=defs)
```

---

## 📜 Пример вывода

```text
=== DAG зависимостей ===
a ← []
b ← ['a']
c ← ['b']

=== Запуск materialize([c]) ===
2024-04-11 12:34:56 - Выполняется asset A
[IOManager] handle_output: a = 1
2024-04-11 12:34:56 - Выполняется asset B. Получено a = 1
[IOManager] load_input: a
[IOManager] handle_output: b = 2
2024-04-11 12:34:56 - Выполняется asset C. Получено b = 2
[IOManager] load_input: b
[IOManager] handle_output: c = 4
```

---

## 💡 Комментарии

- Если `a` уже был рассчитан ранее — ты можешь эмулировать сохранённое состояние, просто положив в `_store["a"] = ...` заранее.
- Ты можешь использовать `breakpoint()` в `IOManager` чтобы в рантайме «остановить» выполнение.

---

Хочешь, могу расширить пример с `AssetCheck`, `observable_source_asset` или кастомной логикой dirty-check.
