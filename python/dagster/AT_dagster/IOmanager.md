

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