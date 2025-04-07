# Отладка в Dugster
## 1. Запуск ```job``` или ```asset``` из обычного Python-скрипта
Cамый простой и прямой способ отладки, вызов нужных ```asset```-функций вручную в скрипте.


```python
from my_dagster_project.assets import company_id, company_details, store_to_db

if __name__ == "__main__":
    id = company_id()
    details = company_details(id) 
    store_to_db(details)
#  📌 можно ставить любые breakpoints в PyCharm и отлаживать пошагово. 
```

🟢 Плюсы:  
- быстро  
- удобно  
- PyCharm работает как обычно  

🔴 Минусы:
- не используются настоящие механизмы Dagster (без графа и логирования)
- нет UI 
- не отслеживаются зависимости и контекст исполнения

## 2. Отладка ```job``` через отладчик PyCharm, используя ```execute_in_process```

Dagster позволяет выполнять ``job`` прямо из **Python** с полной поддержкой зависимостей и логирования в локальном процессе.

```python
from my_dagster_project.jobs import my_sync_job

if __name__ == "__main__":
    result = my_sync_job.execute_in_process()
    assert result.success
# 📌 Это самый рекомендуемый способ отладки “по-Dagster’овски”
#    полноценно работают точки останова и граф зависимостей 
```
🟢 Плюсы:  
работает ```@asset```, ```deps```, ```job```  
можно дебажить как обычный код  
работает в PyCharm, Jupyter, VSCode и т.д.  

🔴 Минусы:
нельзя дебажить из UI Dagster (Dagit)


## 3. Отладка через **Dagit** (**Dagster UI**) + внешнее подключение дебаггера
Dagster UI (Dagit) запускает код в отдельном процессе, и обычные breakpoint'ы из PyCharm туда не "видны".  
Но можно использовать внешний дебаггер, например debugpy (отладчик для VSCode/PyCharm)


```python
import debugpy

@asset
def company_id():
    print("Waiting for debugger attach...")
        #TODO Добавить в нужный asset:
    debugpy.listen(("0.0.0.0", 5678))
    debugpy.wait_for_client()  # остановится тут, пока ты не подключишься

    # теперь можно ставить breakpoint'ы 
    print("Debugger attached") 
    return 123
```

Далее:

- Запустить ```dagster dev```
- В Dagit нажать "Materialize" для company_id  
- В PyCharm выбрать “Attach to Process” (или Remote Debug)
  - host: localhost
  - port: 5678

Код остановится на debugpy.wait_for_client() — и ты сможешь пошагово отлаживать

🟢 Плюсы:
- полноценная отладка даже из Dagit UI
- можно тестировать в условиях, близких к боевым

🔴 Минусы:
- трудоемокость организации отладки (не получится запустить отлаку нажатием одной кнопки)
- нужно контролировать, чтобы отладка не ушла в пром 🙂