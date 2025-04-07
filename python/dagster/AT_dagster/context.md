# Контекст

В Dagster "контекст" (`context`) — это объект, который передаётся в функции `op`, `asset`, `resource`, `io_manager`, `sensor`, `schedule`   
и других компонентов во время их выполнения.  
Он предоставляет доступ к **контексту выполнения**, то есть к информации о текущем запуске, ресурсах, конфигурации, логгерам и т.д.

---

## 🔍 Контекст чего?

**Контекст — это объект, описывающий окружение выполнения определённого компонента Dagster.**

Например:
- В `@asset` — контекст описывает окружение, в котором исполняется этот asset.
- В `@op` — контекст связан с выполнением операции внутри graph/pipeline.
- В `io_manager` — контекст связан с записью или чтением данных.

---

## 🧩 Типы контекста

В зависимости от того, где используется, тип контекста будет отличаться:

| Где используется        | Тип контекста                         |
|-------------------------|----------------------------------------|
| `@asset`                | `AssetExecutionContext`               |
| `@op`                   | `OpExecutionContext`                  |
| `@io_manager.handle_output` | `OutputContext`                    |
| `@io_manager.load_input`    | `InputContext`                     |
| `@sensor`               | `SensorEvaluationContext`             |
| `@schedule`             | `ScheduleEvaluationContext`           |
| `@resource`             | `InitResourceContext` (при инициализации ресурса) |

---

## 📦 Что содержит контекст?

Примеры полей и методов (на `AssetExecutionContext` / `OpExecutionContext`):
- `context.log`: логгер
- `context.resources`: доступ к ресурсам
- `context.run_id`: ID текущего run'а
- `context.asset_key` / `context.op.name`: имя текущего asset'а или op
- `context.config`: конфигурация из `run_config.yaml`
- `context.has_tag()` / `context.get_tag()`: доступ к меткам
- `context.add_output_metadata()`: прикрепление метаданных

---

## 🔧 Пример

```python
from dagster import asset, AssetExecutionContext

@asset
def my_asset(context: AssetExecutionContext):
    context.log.info("Выполняется asset!")
    my_config = context.op_config
    my_resource = context.resources.my_api_client
```

---

## 💡 Резюме

- Контекст — это **инструмент доступа ко всему окружению, в котором работает компонент Dagster**.
- Он **разный для разных компонентов** (asset, op, io_manager и т.д.).
- Его можно использовать для логирования, доступа к ресурсам, конфигурации и метаданным.

---

Отличные вопросы — ты хочешь докопаться до сути Dagster, и это очень правильный подход.

---

## 🔧 Кто создаёт экземпляр `context`?

Экземпляры контекстов создаются **Dagster runtime-ом**, то есть системой исполнения (`dagster._core.execution`), когда запускается pipeline / job.

Создание контекста происходит:
- в рантайме выполнения pipeline-а/job-а
- в зависимости от того, **что сейчас исполняется** (op, asset, sensor и т.д.)

Например:
- при запуске job-а Dagster создает `OpExecutionContext` для каждого op
- при запуске asset job-а — `AssetExecutionContext`
- когда вызывается `io_manager.handle_output()` — создаётся `OutputContext`

Контексты создаются во внутренних слоях кода Dagster. Например, `OpExecutionContext` создается в `dagster._core.execution.context.system`.

---

## 🔍 Где (в каком scope/объекте) создаётся context?

Контексты создаются **в рамках pipeline/job run-а**, в execution plan.

Примеры:
- `DagsterEvent` → `StepExecutionContext` → `OpExecutionContext`
- Для `asset`, обёрнутый job выполняется и на каждый asset создается свой `AssetExecutionContext`
- `InputContext` и `OutputContext` создаются при передаче данных между ops/assets

Фреймворк **генерирует эти объекты во время построения и исполнения execution graph**. Это часть **внутреннего движка orchestration-а**.

---

## 🔢 Сколько контекстов существует?

Если упрощать, то можно выделить такие **основные типы контекстов**, каждый со своим назначением:

### 1. **Во время выполнения job'а:**
- `OpExecutionContext` — при выполнении `@op`
- `AssetExecutionContext` — при выполнении `@asset`

### 2. **Внутри `io_manager`'а:**
- `InputContext` — когда загружаются входные данные
- `OutputContext` — когда сохраняются выходные данные

### 3. **Для ресурсов:**
- `InitResourceContext` — при инициализации ресурса

### 4. **Для schedule/sensor:**
- `ScheduleEvaluationContext`
- `SensorEvaluationContext`

### 5. **Системные:**
- `StepExecutionContext`, `PlanOrchestrationContext`, `DagsterRunContext`, и т.д. — используются внутри Dagster runtime для оркестрации.

Так что:
- **Типов контекста — ~6–10**
- **Экземпляров контекста** создается по количеству объектов в job'е/asset graph. Например:
  - Если в job'е 5 ops — будет создано 5 `OpExecutionContext`
  - Если asset зависит от другого — на каждую стадию будет свой `InputContext` и `OutputContext`

---

## 📦 Пример на практике

```python
@asset
def my_asset(context: AssetExecutionContext):
    print(type(context))  # <class 'dagster._core.execution.context.asset.AssetExecutionContext'>
```

Этот `context` создаётся на каждый запуск asset'а в рамках job'а. Если ты вызовешь `my_asset()` напрямую, без orchestration — `context` не создаётся автоматически.

---

Как **на самом деле создаётся `OpExecutionContext`** (и не только он) внутри Dagster.  
Это даст полное представление, что там "под капотом".

---

## 🔩 Путь создания `OpExecutionContext`

Dagster не создаёт `OpExecutionContext` напрямую — он строится **из более низкоуровневого `StepExecutionContext`**, который в свою очередь строится внутри execution engine.

---

### 📍 1. Начальная точка: `execute_run`

Файл: `dagster._core.execution.api`

```python
def execute_run(pipeline, ...):
    ...
    execute_run_iterator(...)
```

---

### 📍 2. План выполнения

Файл: `dagster._core.execution.plan.plan.py`

```python
plan = create_execution_plan(job_def, ...)
```

Он создаёт список шагов исполнения — `ExecutionPlan`, содержащий `ExecutionStep`'ы.

---

### 📍 3. Вызов каждого шага (step)

Файл: `dagster._core.execution.plan.plan_orchestration.py`

```python
for step in execution_plan:
    step_context = plan_context.for_step(step)
    execute_step(step_context, ...)
```

Здесь создаётся **`StepExecutionContext`** — это базовый контекст исполнения для любого шага (`op`, `asset`, и т.д.)

---

### 📍 4. Преобразование в `OpExecutionContext`

Файл: `dagster._core.execution.context.invocation.py`

```python
def build_op_context(...):
    # используем StepExecutionContext внутри
    return OpExecutionContext(...)
```

Dagster создает `OpExecutionContext` как "view" (обёртку) над `StepExecutionContext`. Он адаптирует его под вызов `@op`.

---

## 🧠 Что внутри `StepExecutionContext`

Вот что он содержит:

- `resources`: инициализированные ресурсы
- `log_manager`: логгер
- `run_config`: конфигурация запуска
- `run_id`: ID запуска
- `pipeline_def`, `op_def`
- `step`: текущий step (определяет имя `op`, входы/выходы)
- `intermediate_storage`, `input/output managers`

Это и есть **ядро "контекста исполнения"**.

---

## 📦 Как создаётся `AssetExecutionContext`?

Он оборачивает `OpExecutionContext`, но добавляет:
- `asset_key`
- `code_version`
- `partition_key`
- Метаданные, специфичные для asset'ов

См. `dagster._core.execution.context.asset.AssetExecutionContext`

---

## 🛠 Иерархия классов

```
[DagsterRun] ──▶ [PlanOrchestrationContext]
                    │
                    └──▶ [StepExecutionContext]
                              │
                              ├──▶ [OpExecutionContext]
                              └──▶ [InputContext], [OutputContext]
```

---


Точный стеку вызовов при старте `job`, показать как ресурсы инжектируются в context или как `run_config` попадает внутрь.

**пошагово**, как происходит запуск `job` в Dagster, как создаётся `context`, как туда попадают ресурсы и `run_config`, и что именно вызывается внутри.

---

## 🧭 Общий план
Вот ключевые этапы:

1. `job.execute_in_process()` или запуск через `dagster dev` CLI
2. Построение `ExecutionPlan`
3. Создание `PlanOrchestrationContext`
4. Создание `StepExecutionContext`
5. Из него — `OpExecutionContext`, `AssetExecutionContext`
6. Вызов функции `@op` / `@asset` с этим `context`
7. После исполнения — `OutputContext` → `io_manager.handle_output()`

---

## 🔁 1. Старт: `job.execute_in_process`

```python
result = my_job.execute_in_process(
    run_config={...},
    resources={"my_api": MockClient()},
)
```

🔹 Тут создаётся `InProcessExecutor`, и вызывается:

```python
dagster._core.execution.api.execute_in_process(...)
```

---

## 🔧 2. Создание ExecutionPlan

Внутри `execute_in_process`:

```python
execution_plan = create_execution_plan(
    job_def,
    run_config=run_config,
    ...
)
```

📌 План — это список `ExecutionStep`'ов. Каждый step соответствует `@op` или `@asset`.

---

## 🧪 3. План оркестрации → `PlanOrchestrationContext`

Создаётся объект `PlanOrchestrationContext`, содержащий:

- `resources` — создаются по `resource_defs` и `run_config['resources']`
- `log_manager`
- `instance` (DagsterInstance)
- `run_config` — весь словарь, переданный пользователем
- `execution_plan`

🔧 Это глобальный контекст одного запуска `job` (все шаги делят один `PlanOrchestrationContext`).

Файл: `dagster/_core/execution/context_creation_pipeline.py` → `initialize_console_manager` → `PlanOrchestrationContext`

---

## 🧱 4. Для каждого `step` → `StepExecutionContext`

Файл: `dagster/_core/execution/plan/plan_orchestration.py`

```python
step_context = plan_context.for_step(step)
```

Создаётся `StepExecutionContext`, из `PlanOrchestrationContext`, + специфичная инфа:

- `step`
- `inputs`, `outputs`
- текущий `op_def` / `asset_def`

---

## 🧩 5. Преобразование в OpExecutionContext

Если мы вызываем `@op`, Dagster вызывает:

```python
op_def.compute_fn(op_context, **inputs)
```

Где `op_context` — это `OpExecutionContext`, построенный на основе `StepExecutionContext`.

📌 Аналогично, при запуске `@asset`, используется `AssetExecutionContext`.

---

## 📥 Как ресурсы и run_config попадают в context?

Всё происходит **в момент построения `PlanOrchestrationContext`**, конкретно тут:

Файл: `dagster/_core/execution/context_creation_pipeline.py`

```python
resolved_run_config = ResolvedRunConfig.build(run_config)
resource_build_context = build_resources(...)
```

Dagster инициализирует все ресурсы, указанные в `resource_defs`, и сохраняет их в context:

```python
context.resources.my_resource
```

🔹 `resource_defs` берётся из job definition (`my_job = define_asset_job(..., resource_defs={...})`)

🔹 run_config['resources'] может передавать параметры этим ресурсам

---

## 🧪 Пример run_config

```yaml
resources:
  my_api:
    config:
      endpoint: "https://..."
```

Dagster вызовет `@resource(config_schema={...})` и передаст туда конфиг из `run_config`.

---

## 🔄 Вызов `@asset`

```python
@asset
def my_asset(context: AssetExecutionContext):
    data = context.resources.my_api.get_data()
```

Dagster вызывает твою функцию, передав туда `context`, созданный как описано выше.

---

## 📦 Куда дальше?


- как работают `io_manager` и откуда берёт метаданные
- Нарисовать схему/диаграмму вызовов
- Показать "почти настоящую" трассировку исполнения с логами и стеками




1. **как работает `io_manager`**, как он получает `InputContext` / `OutputContext` и откуда берёт метаданные.  
2. 🧭  **граф-схему (диаграмму) вызовов компонентов** — от `job` до `op` и `io_manager`.  
3. 🧪 В конце — **симулированный запуск** с логами и стеком вызовов, максимально приближённый к реальности.

---

# ✅ 1. Как работает `io_manager`

## 📌 Что такое `io_manager`?

`io_manager` — это компонент, отвечающий за **сохранение результатов из `op`/`asset` и загрузку входов** в другие `op`/`asset`.

Он реализует два метода:

```python
def handle_output(self, context: OutputContext, obj: Any)
def load_input(self, context: InputContext) -> Any
```

---

## 📥 Когда вызывается `handle_output`

Внутри job-а, когда `@op`/`@asset` возвращает значение, вызывается:

```python
io_manager.handle_output(context, result)
```

### 🔸 Как создаётся `OutputContext`?

Dagster строит `OutputContext` из `StepExecutionContext`, вот откуда:

- `step_key` (имя `op`)
- `name` — имя выходного значения (обычно `'result'`)
- `metadata` из `@asset(..., metadata={"x": "y"})` или `context.add_output_metadata`
- `asset_key` (если используется `@asset`)
- `config` — `output_manager.config` из `run_config` (если передано)
- `resource_config` — конфиг ресурса, если задан

---

## 📤 Когда вызывается `load_input`

Если `@op` принимает аргумент, и он зависит от другого `op`, то перед исполнением Dagster вызывает:

```python
io_manager.load_input(context)
```

И даёт ему `InputContext`, в котором:

- `upstream_output` — `OutputContext`, откуда данные пришли
- `asset_key` — если работает с asset
- `metadata` — из `run_config`, `asset`, `output`, `input`
- `dagster_type` — тип данных, если указан
- `config` — для input manager'а

---

## 💡 Пример

```python
@io_manager
class MyIOManager:
    def handle_output(self, context, obj):
        print(f"[handle_output] step: {context.step_key}")
        print(f"Metadata: {context.metadata}")
        save_to_disk(obj, context.asset_key.path)

    def load_input(self, context):
        print(f"[load_input] loading for: {context.name}")
        return load_from_disk(context.asset_key.path)
```

---
