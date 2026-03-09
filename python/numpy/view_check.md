# Проверка для переменной является ди она **view** или **настоящей (основной) копии данных**


## 1. Проверка значения атрибута `.base`

Атрибут `.base` указывает на **массив, на который ссылается view**.

* Если `.base is None` → массив **самостоятельный (владеет своими данными)**.
* Если `.base is not None` → массив — **view** на другой массив.

### Пример:

```python
import numpy as np

a = np.array([1, 2, 3, 4, 5])
b = a[1:4]       # view
c = a[1:4].copy()  # копия

print(b.base is a)    # True → b — view на a
print(c.base is None) # True → c — самостоятельная копия
```


## 2. Проверка через результата функции `np.shares_memory`

Функция `np.shares_memory(a, b)` проверяет, **делят ли массивы память**:

```python
np.shares_memory(a, b)  # True → view
np.shares_memory(a, c)  # False → копия
```


## 3. Проверка флага `a.flags.owndata`

Этот флаг показывает, владеет ли массив памятью:

```python
a.flags.owndata  # True → a владеет памятью
b.flags.owndata  # False → b — view
c.flags.owndata  # True → c — копия, владеет памятью
```


### Пример итог:

```python
a = np.arange(10)
b = a[2:5]        # view
c = a[2:5].copy() # копия

print("b is view:", b.base is a)            # True
print("c is copy:", c.base is None)         # True
print("b shares memory with a:", np.shares_memory(a, b))  # True
print("c owns data:", c.flags.owndata)      # True
```