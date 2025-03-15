# Чтение данных из CSV-файла 

### CSV-файл содержит только данные без заголовков имен столбцов и индексов.
Cледует использовать pd.read_csv() с параметрами:  
```header=None``` в файле нет заголовков, и **pandas** автоматически присвоит столбцам числовые индексы (0, 1, 2, ...).  
```index_col=None``` **pandas** не будет считать первый столбец индексом.

```python
import pandas as pd

# Пример данных CSV (без заголовков)
data = """10,20,30
40,50,60
70,80,90"""

# Сохраним в файл (для примера)
with open("data.csv", "w") as f:
    f.write(data)

# Читаем файл без заголовков
df = pd.read_csv("data.csv", header=None)

print(df)
```

### CSV загружен как Python-строка  
```python
import pandas as pd
from io import StringIO

data=''' 
ID,A,B,C
1,10,20,30
2,40,50,60'''

df = pd.read_csv(StringIO(data), header=None)
```

### Задать заголовки вручную
Следует передать names=[...]
```python
import pandas as pd
df = pd.read_csv("data.csv", header=None, names=["A", "B", "C"])
```
Если нужно игнорировать первую строку ```skiprows=1```
```python
import pandas as pd
df = pd.read_csv("data.csv", header=None, names=["A", "B", "C"], skiprows=1)
```

Если нужно игнорировать первый (или любые другие) столбцы то можно использовать ```usecols=[1, 2, 3]```
```python
import pandas as pd
df = pd.read_csv("data.csv", usecols=[1, 2, 3])  # Загружаем только 1-й, 2-й и 3-й столбцы (нумерация с 0)
```

Если нужно исключить столбец по имени
```python
import pandas as pd
df = pd.read_csv("data.csv", usecols=["A", "B", "C"])
```

Если нужно заданный столбец использовать в качестве меток строк ```index_col="ID"```
```python
import pandas as pd
df = pd.read_csv("data.csv", index_col="ID")  # Указываем, что "ID" — это индекс
```

